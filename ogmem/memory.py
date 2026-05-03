"""VerifiableMemory: cryptographically provable agent memory on 0G."""

import hashlib
import json
import os
import pathlib
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, Generator

from .chain import ChainClient
from .compute import ComputeClient
from .config import NETWORKS, NetworkConfig
from .da import DAClient
from .encryption import derive_encryption_key
from .merkle import MerkleTree
from .proof import AuditReport, MemoryType, Operation, QueryProof, WriteReceipt
from .storage import StorageClient

# Decay threshold — memories unretrieved for this many days are flagged stale
_STALE_DAYS = 45
_STALE_SECONDS = _STALE_DAYS * 86400

# Data directory for all persistent local state
_DATA_DIR = pathlib.Path.home() / ".0g"


@dataclass
class EvolveReport:
    """Summary of a memory.evolve() pass."""
    strengthened: int    # memories whose weight increased
    decayed: int         # memories newly flagged as stale
    already_stale: int   # memories that were already stale
    total: int

    def summary(self) -> str:
        return (
            f"Evolved {self.total} memories: "
            f"{self.strengthened} strengthened, "
            f"{self.decayed} newly stale, "
            f"{self.already_stale} already stale"
        )


@dataclass
class DistillReport:
    """Summary of a memory.distill() compression pass."""
    source_count: int     # episodic entries compressed
    target_count: int     # semantic facts produced
    deleted: bool         # whether originals were deleted


@dataclass
class SyncReport:
    """Summary of a memory.sync() / pull_index() pass."""
    added: int            # entries merged into local index
    skipped: int          # entries already present
    failed: int = 0       # entries that could not be fetched
    message: str = ""     # human-readable status


class MemorySession:
    """
    Buffers memory writes and commits a single chain tx when closed.

    Usage:
        with memory.session() as s:
            s.add("text 1")
            s.add("text 2")
        # → one chain tx anchors both writes
    """

    def __init__(self, memory: "VerifiableMemory"):
        self._mem = memory
        self._receipts: list[WriteReceipt] = []
        self._open = True

    def add(
        self,
        text: str,
        memory_type: str = MemoryType.EPISODIC.value,
        metadata: dict | None = None,
    ) -> WriteReceipt:
        """Buffer a write — storage + DA happen immediately, chain tx is deferred."""
        if not self._open:
            raise RuntimeError("Session is already closed.")
        receipt = self._mem._add_buffered(text, memory_type, metadata)
        self._receipts.append(receipt)
        return receipt

    def _commit(self) -> str | None:
        """Anchor all buffered writes with a single chain tx."""
        self._open = False
        if not self._receipts:
            return None
        merkle_root = self._mem._tree.get_root()
        last_da = self._receipts[-1].da_tx_hash
        chain_tx_hash = self._mem._chain.update_root(
            merkle_root=merkle_root,
            da_tx_hash=last_da,
        )
        for r in self._receipts:
            r.chain_tx_hash = chain_tx_hash
            r.merkle_root = merkle_root
        return chain_tx_hash


class VerifiableMemory:
    """Agent memory stored on 0G Storage with Merkle proofs anchored on-chain."""

    def __init__(
        self,
        agent_id: str,
        private_key: str,
        network: str = "0g-testnet",
        registry_contract_address: Optional[str] = None,
        nft_contract_address: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        encrypted: bool = True,
        _storage: Optional[StorageClient] = None,
        _compute: Optional[ComputeClient] = None,
        _da: Optional[DAClient] = None,
        _chain: Optional[ChainClient] = None,
    ):
        self.agent_id = agent_id
        self._private_key = private_key
        self._tree = MerkleTree()
        self._entries: list[dict] = []
        self._last_proof: Optional[QueryProof] = None

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Sanitise agent_id for use as a filename (wallet addr is safe; others may not be)
        _safe_id = agent_id.replace("/", "_").replace("\\", "_")[:64]
        self._index_path = _DATA_DIR / f"memory_{_safe_id}.json"
        self._load_index()

        self._encrypted = encrypted
        self._enc_key: Optional[bytes] = derive_encryption_key(private_key) if encrypted else None

        net: NetworkConfig = NETWORKS[network]

        storage_cache = str(_DATA_DIR / f"storage_{_safe_id}.json")
        self._storage = _storage or StorageClient(
            indexer_rpc=net.storage_indexer_rpc,
            flow_contract=net.flow_contract_address,
            private_key=private_key,
            chain_rpc=net.rpc_url,
            cache_path=storage_cache,
        )
        self._compute = _compute or ComputeClient(
            serving_broker_url=net.serving_broker_url,
            openai_api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"),
        )
        da_persist = str(_DATA_DIR / f"da_{_safe_id}.json")
        self._da = _da or DAClient(disperser_rpc=net.da_disperser_rpc, persist_path=da_persist)
        self._chain = _chain or ChainClient(
            rpc_url=net.rpc_url,
            private_key=private_key,
            registry_contract_address=(
                registry_contract_address
                or net.memory_registry_address
                or _PLACEHOLDER_REGISTRY
            ),
            nft_contract_address=nft_contract_address or net.memory_nft_address or None,
        )

    # ─── Public write API ──────────────────────────────────────────────────────

    def add(
        self,
        text: str,
        memory_type: str = MemoryType.EPISODIC.value,
        metadata: dict | None = None,
    ) -> WriteReceipt:
        """
        Store a memory entry on 0G Storage and anchor its Merkle root on-chain.

        Args:
            text: Memory content.
            memory_type: One of episodic / semantic / procedural / working.
            metadata: Optional free-form metadata dict.
        """
        receipt = self._add_buffered(text, memory_type, metadata)
        chain_tx_hash = self._chain.update_root(
            merkle_root=receipt.merkle_root,
            da_tx_hash=receipt.da_tx_hash,
        )
        receipt.chain_tx_hash = chain_tx_hash
        return receipt

    @contextmanager
    def session(self) -> Generator[MemorySession, None, None]:
        """
        Context manager that batches multiple writes into a single chain tx.

        Example:
            with memory.session() as s:
                s.add("preference 1", memory_type="procedural")
                s.add("preference 2", memory_type="procedural")
            # → only one on-chain transaction
        """
        sess = MemorySession(self)
        try:
            yield sess
        finally:
            sess._commit()

    # ─── Internal buffered write ───────────────────────────────────────────────

    def _add_buffered(
        self,
        text: str,
        memory_type: str = MemoryType.EPISODIC.value,
        metadata: dict | None = None,
    ) -> WriteReceipt:
        """Write to storage + DA, update local index. Chain tx is caller's responsibility."""
        timestamp = int(time.time())
        embedding = self._compute.embed(text)

        entry_data = {
            "agent_id": self.agent_id,
            "text": text,
            "embedding": embedding,
            "timestamp": timestamp,
            "memory_type": memory_type,
            "metadata": metadata or {},
        }

        if self._encrypted and self._enc_key:
            blob_id = self._storage.upload_encrypted(entry_data, self._enc_key)
        else:
            blob_id = self._storage.upload(entry_data)

        self._tree.add_leaf(blob_id)
        merkle_root = self._tree.get_root()

        self._entries.append({
            "blob_id": blob_id,
            "embedding": embedding,
            "text": text,
            "memory_type": memory_type,
            "timestamp": timestamp,
            "retrieval_count": 0,
            "last_retrieved": 0,
            "stale": False,
            "weight": 1.0,
        })
        self._save_index()

        da_tx_hash = self._da.post_write_commitment(
            agent_id=self.agent_id,
            blob_id=blob_id,
            merkle_root=merkle_root,
            timestamp=timestamp,
        )

        return WriteReceipt(
            agent_id=self.agent_id,
            blob_id=blob_id,
            merkle_root=merkle_root,
            da_tx_hash=da_tx_hash,
            chain_tx_hash="",
            memory_type=memory_type,
            timestamp=timestamp,
        )

    # ─── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        text: str,
        top_k: int = 3,
        memory_types: list[str] | None = None,
    ) -> tuple[list[str], QueryProof]:
        """
        Search memory and return (results, proof).

        Args:
            text: Natural language query.
            top_k: Maximum number of results to return.
            memory_types: Optional filter — e.g. ["procedural", "semantic"].
        """
        candidates = self._entries
        if memory_types:
            candidates = [e for e in self._entries if e.get("memory_type") in memory_types]

        if not candidates:
            return [], self._empty_proof(text)

        timestamp = int(time.time())
        query_hash = hashlib.sha256(text.encode()).hexdigest()

        query_vec = self._compute.embed(text)
        candidate_vecs = [e["embedding"] for e in candidates]
        matches = self._compute.similarity_search(query_vec, candidate_vecs, top_k=top_k)

        results = []
        blob_ids = []
        scores = []
        merkle_proofs = []

        for idx, score in matches:
            entry = candidates[idx]

            # Update usage stats
            global_idx = self._entries.index(entry)
            self._entries[global_idx]["retrieval_count"] += 1
            self._entries[global_idx]["last_retrieved"] = timestamp
            self._entries[global_idx]["stale"] = False
            new_weight = min(3.0, self._entries[global_idx]["weight"] + 0.1)
            self._entries[global_idx]["weight"] = round(new_weight, 2)

            results.append(entry["text"])
            blob_ids.append(entry["blob_id"])
            scores.append(round(score, 6))
            try:
                mp = self._tree.get_proof(entry["blob_id"])
                merkle_proofs.append({
                    "leaf": mp.leaf,
                    "siblings": mp.siblings,
                    "directions": mp.directions,
                    "root": mp.root,
                })
            except ValueError:
                merkle_proofs.append({})

        self._save_index()

        merkle_root = self._tree.get_root()
        chain_state = self._chain.get_latest_root(self._chain.agent_address)
        chain_block = chain_state.block_number if chain_state else 0

        da_read_tx = self._da.post_read_commitment(
            agent_id=self.agent_id,
            query_hash=query_hash,
            blob_ids=blob_ids,
            scores=scores,
            merkle_root=merkle_root,
            timestamp=timestamp,
        )

        proof = QueryProof(
            agent_id=self.agent_id,
            query_hash=query_hash,
            blob_ids=blob_ids,
            scores=scores,
            merkle_proofs=merkle_proofs,
            merkle_root=merkle_root,
            da_read_tx=da_read_tx,
            chain_block=chain_block,
            timestamp=timestamp,
        )
        self._last_proof = proof
        return results, proof

    # ─── Memory evolution ──────────────────────────────────────────────────────

    def evolve(self) -> EvolveReport:
        """
        RL-inspired memory reweighting pass.

        - Memories retrieved frequently get their weight boosted.
        - Memories not retrieved for _STALE_DAYS days get flagged stale.
        - Evolution event is anchored on-chain.
        """
        now = int(time.time())
        strengthened = 0
        decayed = 0
        already_stale = 0

        for entry in self._entries:
            if entry.get("stale"):
                already_stale += 1
                continue

            age = now - entry.get("timestamp", now)
            last_retrieved = entry.get("last_retrieved", 0)
            retrieval_count = entry.get("retrieval_count", 0)
            time_since_retrieval = now - last_retrieved if last_retrieved else age

            if time_since_retrieval > _STALE_SECONDS and retrieval_count == 0:
                entry["stale"] = True
                entry["weight"] = max(0.1, entry.get("weight", 1.0) - 0.3)
                decayed += 1
            elif retrieval_count >= 5:
                entry["weight"] = min(3.0, entry.get("weight", 1.0) + 0.2)
                strengthened += 1

        self._save_index()

        # Anchor the post-evolution state on-chain
        merkle_root = self._tree.get_root()
        da_tx_hash = self._da.post_write_commitment(
            agent_id=self.agent_id,
            blob_id="evolve:" + merkle_root[:16],
            merkle_root=merkle_root,
            timestamp=now,
        )
        self._chain.update_root(merkle_root=merkle_root, da_tx_hash=da_tx_hash)

        return EvolveReport(
            strengthened=strengthened,
            decayed=decayed,
            already_stale=already_stale,
            total=len(self._entries),
        )

    def distill(
        self,
        older_than_days: int = 7,
        keep_originals: bool = True,
        inference_fn=None,
    ) -> DistillReport:
        """
        Compress old episodic memories into a single semantic entry.

        Finds episodic entries older than older_than_days, writes a distilled
        semantic summary, and optionally removes the originals.

        Args:
            inference_fn: Optional callable(prompt: str) -> str. When provided,
                          uses the LLM to summarize instead of naive concatenation.
        """
        cutoff = int(time.time()) - older_than_days * 86400
        to_compress = [
            e for e in self._entries
            if e.get("memory_type") == MemoryType.EPISODIC.value
            and e.get("timestamp", 0) < cutoff
        ]

        if not to_compress:
            return DistillReport(source_count=0, target_count=0, deleted=False)

        combined = "\n".join(f"- {e['text']}" for e in to_compress)

        if inference_fn is not None:
            prompt = (
                f"Summarize these {len(to_compress)} episodic memories into "
                f"3-5 concise factual statements the agent should remember long-term:\n\n"
                f"{combined}\n\n"
                "Output only the statements, one per line."
            )
            try:
                summary_text = inference_fn(prompt)
            except Exception:
                summary_text = f"[Distilled from {len(to_compress)} episodic entries]\n{combined}"
        else:
            summary_text = f"[Distilled from {len(to_compress)} episodic entries]\n{combined}"

        self._add_buffered(
            text=summary_text,
            memory_type=MemoryType.SEMANTIC.value,
            metadata={"distilled_from": len(to_compress), "distilled_at": int(time.time())},
        )

        if not keep_originals:
            blob_ids_to_remove = {e["blob_id"] for e in to_compress}
            self._entries = [e for e in self._entries if e["blob_id"] not in blob_ids_to_remove]
            self._rebuild_tree()
            self._save_index()

        merkle_root = self._tree.get_root()
        da_tx_hash = self._da.post_write_commitment(
            agent_id=self.agent_id,
            blob_id="distill:" + merkle_root[:16],
            merkle_root=merkle_root,
            timestamp=int(time.time()),
        )
        self._chain.update_root(merkle_root=merkle_root, da_tx_hash=da_tx_hash)

        return DistillReport(
            source_count=len(to_compress),
            target_count=1,
            deleted=not keep_originals,
        )

    def get_stale_memories(self) -> list[dict]:
        """Return all entries currently flagged as stale."""
        return [e for e in self._entries if e.get("stale")]

    # ─── Cross-instance sync ───────────────────────────────────────────────────

    def sync(self) -> "SyncReport":
        """
        Rebuild the local index from the DA history file.

        Reads all memory_write commitments from the local DA persist file,
        fetches any blobs not already in the local index, and merges them in.
        Solves same-machine consistency (e.g. MCP server starting after the
        Telegram bot has written memories on the same machine).

        Returns a SyncReport with counts of added and skipped entries.
        """
        history = self._da.fetch_agent_history(self.agent_id)
        existing_blob_ids = {e["blob_id"] for e in self._entries}

        added = 0
        skipped = 0
        failed = 0

        for event in sorted(history, key=lambda x: x.get("timestamp", 0)):
            if event.get("type") != "memory_write":
                continue
            blob_id = event.get("blob_id", "")
            # Skip synthetic blob_ids from evolve/distill operations
            if not blob_id or blob_id.startswith("evolve:") or blob_id.startswith("distill:"):
                continue
            if blob_id in existing_blob_ids:
                skipped += 1
                continue

            try:
                if self._encrypted and self._enc_key:
                    data = self._storage.download_encrypted(blob_id, self._enc_key)
                else:
                    data = self._storage.download(blob_id)

                if not data or "text" not in data:
                    failed += 1
                    continue

                # Use stored embedding if present, recompute if not
                embedding = data.get("embedding") or self._compute.embed(data["text"])

                entry = {
                    "blob_id": blob_id,
                    "embedding": embedding,
                    "text": data["text"],
                    "memory_type": data.get("memory_type", MemoryType.EPISODIC.value),
                    "timestamp": data.get("timestamp", event.get("timestamp", 0)),
                    "retrieval_count": 0,
                    "last_retrieved": 0,
                    "stale": False,
                    "weight": 1.0,
                }
                self._entries.append(entry)
                self._tree.add_leaf(blob_id)
                existing_blob_ids.add(blob_id)
                added += 1

            except Exception:
                failed += 1

        if added > 0:
            self._save_index()

        return SyncReport(added=added, skipped=skipped, failed=failed)

    def push_index(self) -> str:
        """
        Upload an encrypted snapshot of the full memory index to 0G Storage
        and anchor its blob ID on-chain.

        Any other instance with the same AGENT_KEY can call pull_index() to
        discover and download this snapshot — enabling cross-machine sync
        (e.g. Telegram bot on Railway → local MCP server).

        Returns the index_blob_id (content address on 0G Storage).
        """
        snapshot = {
            "type": "index_snapshot",
            "agent_id": self.agent_id,
            "pushed_at": int(time.time()),
            "entry_count": len(self._entries),
            "entries": [
                {
                    "blob_id": e["blob_id"],
                    "text": e["text"],
                    "embedding": e["embedding"],
                    "memory_type": e.get("memory_type", MemoryType.EPISODIC.value),
                    "timestamp": e.get("timestamp", 0),
                    "retrieval_count": e.get("retrieval_count", 0),
                    "last_retrieved": e.get("last_retrieved", 0),
                    "stale": e.get("stale", False),
                    "weight": e.get("weight", 1.0),
                }
                for e in self._entries
            ],
        }

        if self._encrypted and self._enc_key:
            index_blob_id = self._storage.upload_encrypted(snapshot, self._enc_key)
        else:
            index_blob_id = self._storage.upload(snapshot)

        # Anchor on-chain: store the index blob ID in the da_tx_hash field so
        # any machine with the same key can discover it via chain history.
        current_root = self._tree.get_root()
        self._chain.update_root(
            merkle_root=current_root,
            da_tx_hash=index_blob_id,
        )

        return index_blob_id

    def pull_index(self, index_blob_id: str | None = None) -> "SyncReport":
        """
        Download and merge index snapshots from 0G Storage.

        If index_blob_id is provided, fetches that snapshot directly.
        Otherwise scans the on-chain history and merges ALL snapshots found,
        so no memories are missed regardless of which instance pushed them.

        Returns a SyncReport with counts of added and skipped entries.
        """
        # Resolve blob_ids to process
        if index_blob_id:
            blob_ids_to_pull = [index_blob_id]
        else:
            discovered = self._discover_latest_index_blob()
            if not discovered:
                return SyncReport(added=0, skipped=0, failed=0,
                                  message="No index snapshot found on-chain.")
            blob_ids_to_pull = discovered

        existing_blob_ids = {e["blob_id"] for e in self._entries}
        added = 0
        skipped = 0
        failed = 0

        for blob_id in blob_ids_to_pull:
            if self._encrypted and self._enc_key:
                snapshot = self._storage.download_encrypted(blob_id, self._enc_key)
            else:
                snapshot = self._storage.download(blob_id)

            if not snapshot or snapshot.get("type") != "index_snapshot":
                failed += 1
                continue

            for entry in snapshot.get("entries", []):
                eid = entry.get("blob_id", "")
                if not eid or eid in existing_blob_ids:
                    skipped += 1
                    continue

                if not entry.get("embedding") and entry.get("text"):
                    entry["embedding"] = self._compute.embed(entry["text"])

                self._entries.append({
                    "blob_id": eid,
                    "embedding": entry.get("embedding", []),
                    "text": entry.get("text", ""),
                    "memory_type": entry.get("memory_type", MemoryType.EPISODIC.value),
                    "timestamp": entry.get("timestamp", 0),
                    "retrieval_count": entry.get("retrieval_count", 0),
                    "last_retrieved": entry.get("last_retrieved", 0),
                    "stale": entry.get("stale", False),
                    "weight": entry.get("weight", 1.0),
                })
                self._tree.add_leaf(eid)
                existing_blob_ids.add(eid)
                added += 1

        if added > 0:
            self._save_index()

        snapshots_count = len(blob_ids_to_pull)
        return SyncReport(
            added=added,
            skipped=skipped,
            failed=failed,
            message=f"Merged {snapshots_count} snapshot(s): +{added} new, {skipped} already present.",
        )

    def _discover_latest_index_blob(self) -> list[str] | None:
        """
        Scan on-chain history to find the latest index snapshot blob ID.
        push_index() stores the index blob_id in the da_tx_hash field of
        an updateRoot call — we scan backwards to find the most recent one.
        """
        all_roots = self._chain.get_all_roots(self._chain.agent_address)
        # Collect all valid snapshot blob_ids (deduplicated)
        seen: set[str] = set()
        snapshot_blob_ids: list[str] = []
        for state in reversed(all_roots):
            candidate_blob_id = state.da_tx_hash
            if not candidate_blob_id or len(candidate_blob_id) < 16:
                continue
            if candidate_blob_id in seen:
                continue
            seen.add(candidate_blob_id)
            try:
                if self._encrypted and self._enc_key:
                    data = self._storage.download_encrypted(candidate_blob_id, self._enc_key)
                else:
                    data = self._storage.download(candidate_blob_id)
                if data and data.get("type") == "index_snapshot":
                    snapshot_blob_ids.append(candidate_blob_id)
            except Exception:
                continue
        return snapshot_blob_ids or None

    def delete_memory(self, blob_id: str) -> bool:
        """
        Remove a memory entry by blob_id from the local index.
        Returns True if found and removed.
        """
        before = len(self._entries)
        self._entries = [e for e in self._entries if e["blob_id"] != blob_id]
        if len(self._entries) < before:
            self._rebuild_tree()
            self._save_index()
            return True
        return False

    def stats(self) -> dict:
        """Return a summary of the current memory state."""
        total = len(self._entries)
        by_type = {mt.value: 0 for mt in MemoryType}
        for e in self._entries:
            mt = e.get("memory_type", MemoryType.EPISODIC.value)
            if mt in by_type:
                by_type[mt] += 1
        stale = sum(1 for e in self._entries if e.get("stale"))
        top = sorted(self._entries, key=lambda e: e.get("retrieval_count", 0), reverse=True)[:3]
        conflicts = self._detect_conflicts()
        return {
            "total": total,
            "by_type": by_type,
            "stale": stale,
            "top_retrieved": [{"text": e["text"][:60], "count": e["retrieval_count"]} for e in top],
            "conflicts": conflicts,
        }

    def _detect_conflicts(self) -> list[dict]:
        """Detect potentially conflicting procedural memories via keyword overlap."""
        procedural = [e for e in self._entries if e.get("memory_type") == MemoryType.PROCEDURAL.value]
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "i", "you", "my", "to", "of", "and"}
        conflicts = []
        for i, e1 in enumerate(procedural):
            for e2 in procedural[i + 1:]:
                w1 = set(e1["text"].lower().split()) - stopwords
                w2 = set(e2["text"].lower().split()) - stopwords
                common = w1 & w2
                if len(common) >= 3:
                    conflicts.append({
                        "entry1": e1["blob_id"],
                        "entry2": e2["blob_id"],
                        "text1": e1["text"][:60],
                        "text2": e2["text"][:60],
                        "overlap": sorted(common)[:5],
                    })
                if len(conflicts) >= 10:
                    return conflicts
        return conflicts

    def summary(self, inference_fn=None) -> str:
        """
        Generate a plain-English portrait of the agent's memory.

        Args:
            inference_fn: Optional callable(prompt: str) -> str for LLM-based summary.
                          Falls back to structured text if not provided or on failure.
        """
        by_type: dict[str, list[str]] = {mt.value: [] for mt in MemoryType}
        for e in self._entries:
            mt = e.get("memory_type", MemoryType.EPISODIC.value)
            if mt in by_type:
                by_type[mt].append(e["text"])

        if inference_fn is not None:
            facts = "\n".join(
                f"[{mt}] {t[:100]}"
                for mt, texts in by_type.items()
                for t in texts[:5]
                if texts
            )
            if facts:
                prompt = (
                    "Based on these agent memories, write a 2-3 sentence plain-English portrait "
                    "of who this user is, what they care about, and their key preferences:\n\n"
                    f"{facts}"
                )
                try:
                    return inference_fn(prompt)
                except Exception:
                    pass

        # Structured fallback
        parts = []
        if by_type.get(MemoryType.PROCEDURAL.value):
            parts.append("Preferences: " + "; ".join(
                t[:50] for t in by_type[MemoryType.PROCEDURAL.value][:3]
            ))
        if by_type.get(MemoryType.SEMANTIC.value):
            parts.append("Known facts: " + "; ".join(
                t[:50] for t in by_type[MemoryType.SEMANTIC.value][:3]
            ))
        n_ep = len(by_type.get(MemoryType.EPISODIC.value, []))
        if n_ep:
            parts.append(f"{n_ep} episodic memories")
        return " | ".join(parts) if parts else "No memories yet."

    # ─── Proof & audit ─────────────────────────────────────────────────────────

    def last_proof(self) -> Optional[QueryProof]:
        return self._last_proof

    def verify_proof(self, proof: QueryProof) -> bool:
        """Verify Merkle inclusion proofs and confirm the root matches the on-chain anchor."""
        from .merkle import MerkleTree, MerkleProof

        for blob_id, mp_dict in zip(proof.blob_ids, proof.merkle_proofs):
            if not mp_dict:
                return False
            if blob_id != mp_dict.get("leaf"):
                return False
            mp = MerkleProof(
                leaf=mp_dict["leaf"],
                siblings=mp_dict["siblings"],
                directions=mp_dict["directions"],
                root=mp_dict["root"],
            )
            if not MerkleTree.verify(mp):
                return False
            if mp.root != proof.merkle_root:
                return False

        on_chain = self._chain.get_historical_root(
            self._chain.agent_address,
            proof.chain_block,
        )
        if on_chain and on_chain.merkle_root != proof.merkle_root:
            return False

        return True

    def export_audit(self, from_block: int = 0, to_block: int = -1) -> AuditReport:
        """Reconstruct the agent's full memory history from 0G DA commitments."""
        history = self._da.fetch_agent_history(self.agent_id)
        history.sort(key=lambda x: x.get("timestamp", 0))

        operations = []
        total_writes = 0
        total_reads = 0
        from_timestamp = history[0]["timestamp"] if history else int(time.time())
        to_timestamp = history[-1]["timestamp"] if history else int(time.time())

        for event in history:
            if event["type"] == "memory_write":
                total_writes += 1
                if self._encrypted and self._enc_key:
                    blob = self._storage.download_encrypted(event["blob_id"], self._enc_key)
                else:
                    blob = self._storage.download(event["blob_id"])
                content_preview = (blob["text"][:100] + "...") if blob else "[unavailable]"
                operations.append(Operation(
                    op_type="write",
                    timestamp=event["timestamp"],
                    agent_id=self.agent_id,
                    blob_id=event["blob_id"],
                    content_preview=content_preview,
                    memory_type=event.get("memory_type"),
                    merkle_root=event["merkle_root"],
                    da_tx_hash=event.get("da_tx_hash"),
                ))
            elif event["type"] == "memory_read":
                total_reads += 1
                operations.append(Operation(
                    op_type="read",
                    timestamp=event["timestamp"],
                    agent_id=self.agent_id,
                    query_hash=event["query_hash"],
                    retrieved_blob_ids=event["blob_ids"],
                    similarity_scores=event["scores"],
                    merkle_root_used=event["merkle_root"],
                    da_read_tx=event.get("da_tx_hash"),
                ))

        chain_history = self._chain.get_all_roots(self._chain.agent_address)
        roots_history = [
            {"merkle_root": s.merkle_root, "block_number": s.block_number, "timestamp": s.timestamp}
            for s in chain_history
        ]

        return AuditReport(
            agent_id=self.agent_id,
            from_block=from_block,
            to_block=to_block,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            total_writes=total_writes,
            total_reads=total_reads,
            operations=operations,
            merkle_roots_history=roots_history,
        )

    # ─── NFT / access control ──────────────────────────────────────────────────

    def mint_memory_nft(self) -> str:
        return self._chain.mint_memory_nft()

    def grant_access(self, agent_address: str, shard_blob_ids: list[str] | None = None) -> str:
        return self._chain.grant_access(agent_address, shard_blob_ids)

    def revoke_access(self, agent_address: str) -> str:
        return self._chain.revoke_access(agent_address)

    def check_access(self, agent_address: str, blob_id: str) -> bool:
        return self._chain.check_access(self._chain.agent_address, agent_address, blob_id)

    def memory_token_id(self) -> int:
        return self._chain.get_memory_token_id(self._chain.agent_address)

    # ─── LangChain compatibility ────────────────────────────────────────────────

    @property
    def memory_variables(self) -> list[str]:
        return ["history"]

    def load_memory_variables(self, inputs: dict) -> dict:
        query = inputs.get("input", "")
        if not query:
            return {"history": ""}
        results, _ = self.query(query, top_k=5)
        return {"history": "\n".join(results)}

    def save_context(self, inputs: dict, outputs: dict) -> None:
        """LangChain hook — batches human+AI turn into one chain tx."""
        human = inputs.get("input", "")
        ai = outputs.get("response", outputs.get("output", ""))
        with self.session() as s:
            if human:
                s.add(f"Human: {human}", memory_type=MemoryType.EPISODIC.value)
            if ai:
                s.add(f"AI: {ai}", memory_type=MemoryType.EPISODIC.value)

    def clear(self) -> None:
        self._tree = MerkleTree()
        self._entries = []
        self._last_proof = None

    # ─── Internal helpers ──────────────────────────────────────────────────────

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text())
                self._entries = data.get("entries", [])
                for entry in self._entries:
                    entry.setdefault("memory_type", MemoryType.EPISODIC.value)
                    entry.setdefault("retrieval_count", 0)
                    entry.setdefault("last_retrieved", 0)
                    entry.setdefault("stale", False)
                    entry.setdefault("weight", 1.0)
                    self._tree.add_leaf(entry["blob_id"])
            except Exception:
                self._entries = []

    def _save_index(self) -> None:
        self._index_path.write_text(json.dumps({"entries": self._entries}, indent=2))

    def _rebuild_tree(self) -> None:
        self._tree = MerkleTree()
        for entry in self._entries:
            self._tree.add_leaf(entry["blob_id"])

    def _empty_proof(self, text: str) -> QueryProof:
        return QueryProof(
            agent_id=self.agent_id,
            query_hash=hashlib.sha256(text.encode()).hexdigest(),
            blob_ids=[],
            scores=[],
            merkle_proofs=[],
            merkle_root=self._tree.get_root(),
            da_read_tx="",
            chain_block=0,
        )


_PLACEHOLDER_REGISTRY = "0x0000000000000000000000000000000000000001"
