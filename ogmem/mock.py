"""
In-process mock clients for demo mode and testing.

Imported by both production code (demo mode) and tests.
Do NOT put real network clients here.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Optional


class MockStorage:
    """In-memory blob store — no 0G Storage network required."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def upload(self, data: dict) -> str:
        import json
        raw = json.dumps(data, sort_keys=True).encode()
        return self._put(raw)

    def upload_encrypted(self, data: dict, encryption_key: bytes) -> str:
        import json
        from .encryption import encrypt
        raw = json.dumps(data, sort_keys=True).encode()
        return self._put(encrypt(raw, encryption_key))

    def download(self, blob_id: str) -> Optional[dict]:
        import json
        raw = self._get(blob_id)
        if raw is None:
            return None
        try:
            return json.loads(raw.rstrip(b"\x00"))
        except Exception:
            return None

    def download_encrypted(self, blob_id: str, encryption_key: bytes) -> Optional[dict]:
        import json
        from .encryption import decrypt
        raw = self._get(blob_id)
        if raw is None:
            return None
        try:
            return json.loads(decrypt(raw, encryption_key))
        except Exception:
            return None

    def exists(self, blob_id: str) -> bool:
        return blob_id.lstrip("0x") in self._store

    def _put(self, raw: bytes) -> str:
        blob_id = hashlib.sha256(raw).hexdigest()
        self._store[blob_id] = raw
        return blob_id

    def _get(self, blob_id: str) -> Optional[bytes]:
        return self._store.get(blob_id.lstrip("0x"))


class MockCompute:
    """Deterministic mock embeddings — no sentence-transformers or GPU required."""

    EMBEDDING_DIM = 384

    def embed(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        result = []
        i = 0
        while len(result) < self.EMBEDDING_DIM:
            val = (seed ^ (seed >> (i + 3)) ^ (i * 2654435761)) & 0xFFFFFFFF
            result.append(float(val % 1000) / 1000.0 - 0.5)
            seed = val
            i += 1
        mag = math.sqrt(sum(x * x for x in result[:self.EMBEDDING_DIM]))
        return [x / mag for x in result[:self.EMBEDDING_DIM]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def similarity_search(
        self, query_vec: list[float], candidate_vecs: list[list[float]], top_k: int = 3
    ) -> list[tuple[int, float]]:
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            ma = math.sqrt(sum(x * x for x in a))
            mb = math.sqrt(sum(x * x for x in b))
            return dot / (ma * mb) if ma and mb else 0.0

        scores = [(i, cosine(query_vec, v)) for i, v in enumerate(candidate_vecs)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class MockDA:
    """In-memory DA commitment log — no gRPC or Docker DA node required."""

    def __init__(self):
        self._log: list[dict] = []

    def post_write_commitment(
        self, agent_id: str, blob_id: str, merkle_root: str, timestamp: Optional[int] = None
    ) -> str:
        tx = hashlib.sha256(f"write:{blob_id}:{merkle_root}".encode()).hexdigest()
        self._log.append({
            "type": "memory_write",
            "da_tx_hash": tx,
            "agent_id": agent_id,
            "blob_id": blob_id,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
        })
        return tx

    def post_read_commitment(
        self,
        agent_id: str,
        query_hash: str,
        blob_ids: list[str],
        scores: list[float],
        merkle_root: str,
        timestamp: Optional[int] = None,
    ) -> str:
        tx = hashlib.sha256(f"read:{query_hash}:{merkle_root}".encode()).hexdigest()
        self._log.append({
            "type": "memory_read",
            "da_tx_hash": tx,
            "agent_id": agent_id,
            "query_hash": query_hash,
            "blob_ids": blob_ids,
            "scores": scores,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
        })
        return tx

    def post_agent_turn(
        self,
        agent_id: str,
        user_message: str,
        assistant_reply: str,
        memories_retrieved: list[str],
        tool_calls: list[dict],
        write_blob_ids: list[str],
        merkle_root: str,
        latency_ms: int = 0,
        timestamp: Optional[int] = None,
    ) -> str:
        tx = hashlib.sha256(
            f"turn:{agent_id}:{user_message[:32]}:{merkle_root}".encode()
        ).hexdigest()
        self._log.append({
            "type": "agent_turn",
            "da_tx_hash": tx,
            "agent_id": agent_id,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
        })
        return tx

    def fetch_commitment(self, da_tx_hash: str) -> Optional[dict]:
        for e in self._log:
            if e["da_tx_hash"] == da_tx_hash:
                return e
        return None

    def fetch_agent_history(self, agent_id: str) -> list[dict]:
        return [e for e in self._log if e["agent_id"] == agent_id]


class MockChain:
    """In-memory chain state — no RPC or wallet required."""

    def __init__(self):
        self._history: list[dict] = []
        self.agent_address: str = "0x" + "a" * 40

    def update_root(self, merkle_root: str, da_tx_hash: str) -> str:
        tx = hashlib.sha256(f"chain:{merkle_root}:{da_tx_hash}".encode()).hexdigest()
        self._history.append({
            "merkle_root": merkle_root,
            "da_tx_hash": da_tx_hash,
            "chain_tx_hash": tx,
            "block_number": len(self._history) + 1,
            "timestamp": int(time.time()),
        })
        return tx

    def get_latest_root(self, agent_address: str):
        if not self._history:
            return None
        from .chain import MemoryState
        last = self._history[-1]
        return MemoryState(
            merkle_root=last["merkle_root"],
            block_number=last["block_number"],
            da_tx_hash=last["da_tx_hash"],
            timestamp=last["timestamp"],
        )

    def get_historical_root(self, agent_address: str, block_number: int):
        for entry in reversed(self._history):
            if entry["block_number"] <= block_number:
                from .chain import MemoryState
                return MemoryState(
                    merkle_root=entry["merkle_root"],
                    block_number=entry["block_number"],
                    da_tx_hash=entry["da_tx_hash"],
                    timestamp=entry["timestamp"],
                )
        return None

    def get_all_roots(self, agent_address: str):
        from .chain import MemoryState
        return [
            MemoryState(
                merkle_root=e["merkle_root"],
                block_number=e["block_number"],
                da_tx_hash=e["da_tx_hash"],
                timestamp=e["timestamp"],
            )
            for e in self._history
        ]

    def mint_memory_nft(self) -> str:
        return "0x" + hashlib.sha256(b"nft").hexdigest()

    def grant_access(self, agent_address: str, shard_blob_ids=None) -> str:
        return "0x" + hashlib.sha256(f"grant:{agent_address}".encode()).hexdigest()

    def revoke_access(self, agent_address: str) -> str:
        return "0x" + hashlib.sha256(f"revoke:{agent_address}".encode()).hexdigest()

    def check_access(self, owner: str, agent: str, blob_id: str) -> bool:
        return True

    def get_memory_token_id(self, agent_address: str) -> int:
        return 1
