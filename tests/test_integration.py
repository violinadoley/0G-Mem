"""
Real end-to-end integration tests against 0G testnet.

Requirements (all set in .env):
    AGENT_KEY    — wallet private key with OG balance
    MEMORY_REGISTRY_ADDRESS
    MEMORY_NFT_ADDRESS

These tests hit real 0G Chain (Galileo testnet, chain ID 16602) and
real 0G Storage (indexer-storage-testnet-turbo.0g.ai).

No mocks. No demo mode. Skip cleanly when credentials are absent.
"""

import os
import sys
import time
import uuid
from pathlib import Path

import pytest

# Load .env automatically if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Credential guards ──────────────────────────────────────────────────────────

AGENT_KEY = os.environ.get("AGENT_KEY", "")
REGISTRY_ADDR = os.environ.get(
    "MEMORY_REGISTRY_ADDRESS", "0xEDF95D9CFb157F5F38C1125B7DFB3968E05d2c4b"
)
NFT_ADDR = os.environ.get(
    "MEMORY_NFT_ADDRESS", "0x70ad85300f522A41689954a4153744BF6E57E488"
)

needs_key = pytest.mark.skipif(not AGENT_KEY, reason="AGENT_KEY not set")

from ogmem.config import NETWORKS
NET = NETWORKS["0g-testnet"]


# ── Chain integration ──────────────────────────────────────────────────────────

class TestChainIntegration:

    @needs_key
    def test_rpc_reachable(self):
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(NET.rpc_url))
        assert w3.is_connected(), f"RPC unreachable: {NET.rpc_url}"

    @needs_key
    def test_wallet_has_balance(self):
        from web3 import Web3
        from eth_account import Account
        w3 = Web3(Web3.HTTPProvider(NET.rpc_url))
        addr = Account.from_key(AGENT_KEY).address
        balance = w3.eth.get_balance(addr)
        assert balance > 0, f"Wallet {addr} has 0 OG — needs testnet funds"
        print(f"\n  Wallet: {addr}  Balance: {balance / 1e18:.4f} OG")

    @needs_key
    def test_chain_write_read_root(self):
        """Write a Merkle root on-chain and read it back."""
        from ogmem.chain import ChainClient

        client = ChainClient(
            rpc_url=NET.rpc_url,
            private_key=AGENT_KEY,
            registry_contract_address=REGISTRY_ADDR,
            nft_contract_address=NFT_ADDR,
        )

        test_root = uuid.uuid4().hex.zfill(64)
        test_da_hash = "local:" + uuid.uuid4().hex

        tx_hash = client.update_root(test_root, test_da_hash)
        # web3 may return hash with or without 0x prefix — accept both
        clean = tx_hash.lstrip("0x")
        assert len(clean) == 64, f"Bad tx_hash length ({len(clean)}): {tx_hash}"
        print(f"\n  Chain tx: 0x{clean}")

        state = client.get_latest_root(client.agent_address)
        assert state is not None, "get_latest_root returned None"
        assert state.block_number > 0
        print(f"  Block: {state.block_number}  Root: {state.merkle_root[:16]}...")

    @needs_key
    def test_chain_history_grows(self):
        """Two writes → history length increases by at least 1."""
        from ogmem.chain import ChainClient
        from web3 import Web3

        client = ChainClient(
            rpc_url=NET.rpc_url,
            private_key=AGENT_KEY,
            registry_contract_address=REGISTRY_ADDR,
        )

        w3 = Web3(Web3.HTTPProvider(NET.rpc_url))
        registry = w3.eth.contract(
            address=Web3.to_checksum_address(REGISTRY_ADDR),
            abi=__import__("ogmem.config", fromlist=["MEMORY_REGISTRY_ABI"]).MEMORY_REGISTRY_ABI,
        )
        before = registry.functions.historyLength(client.agent_address).call()

        client.update_root(uuid.uuid4().hex.zfill(64), "local:" + uuid.uuid4().hex)

        after = registry.functions.historyLength(client.agent_address).call()
        assert after == before + 1, f"History length: {before} → {after}"


# ── Storage integration ────────────────────────────────────────────────────────

class TestStorageIntegration:

    @needs_key
    def test_storage_upload_download_roundtrip(self):
        """Upload a blob to 0G Storage and download it back."""
        from ogmem.storage import StorageClient

        client = StorageClient(
            indexer_rpc=NET.storage_indexer_rpc,
            flow_contract=NET.flow_contract_address,
            private_key=AGENT_KEY,
            chain_rpc=NET.rpc_url,
        )

        payload = {
            "test": True,
            "text": f"integration-test-{uuid.uuid4().hex[:8]}",
            "timestamp": int(time.time()),
        }

        blob_id = client.upload(payload)
        assert blob_id and len(blob_id) > 0, "upload returned empty blob_id"
        print(f"\n  Uploaded blob_id: {blob_id[:16]}...")

        # Allow a few seconds for storage node propagation after chain finality
        time.sleep(5)
        downloaded = client.download(blob_id)
        assert downloaded is not None, f"download returned None for blob_id {blob_id}"
        assert downloaded["text"] == payload["text"], (
            f"Roundtrip mismatch: {downloaded['text']} != {payload['text']}"
        )
        print(f"  Download OK: {downloaded['text']}")

    @needs_key
    def test_storage_encrypted_roundtrip(self):
        """Upload an AES-256-GCM encrypted blob, download and decrypt."""
        from ogmem.storage import StorageClient
        from ogmem.encryption import derive_encryption_key

        client = StorageClient(
            indexer_rpc=NET.storage_indexer_rpc,
            flow_contract=NET.flow_contract_address,
            private_key=AGENT_KEY,
            chain_rpc=NET.rpc_url,
        )

        enc_key = derive_encryption_key(AGENT_KEY)
        secret = {"secret": f"encrypted-{uuid.uuid4().hex[:8]}"}

        blob_id = client.upload_encrypted(secret, enc_key)
        assert blob_id, "encrypted upload returned empty blob_id"

        result = client.download_encrypted(blob_id, enc_key)
        assert result is not None, "encrypted download returned None"
        assert result["secret"] == secret["secret"]
        print(f"\n  Encrypted roundtrip OK: {result['secret']}")

    @needs_key
    def test_storage_exists(self):
        """exists() returns True for a just-uploaded blob."""
        from ogmem.storage import StorageClient

        client = StorageClient(
            indexer_rpc=NET.storage_indexer_rpc,
            flow_contract=NET.flow_contract_address,
            private_key=AGENT_KEY,
            chain_rpc=NET.rpc_url,
        )

        payload = {"probe": uuid.uuid4().hex}
        blob_id = client.upload(payload)
        # Allow a few seconds for indexer propagation
        time.sleep(3)
        assert client.exists(blob_id), f"exists() returned False for {blob_id}"


# ── Full VerifiableMemory integration ──────────────────────────────────────────

class TestMemoryIntegration:

    def _make_real_memory(self, agent_id: str | None = None) -> "VerifiableMemory":
        from ogmem.memory import VerifiableMemory
        aid = agent_id or f"integ-{uuid.uuid4().hex[:8]}"
        return VerifiableMemory(
            agent_id=aid,
            private_key=AGENT_KEY,
            network="0g-testnet",
            registry_contract_address=REGISTRY_ADDR,
            nft_contract_address=NFT_ADDR,
            encrypted=True,
        )

    @needs_key
    def test_add_anchors_on_chain(self):
        """add() stores the blob in 0G Storage and anchors root on-chain."""
        mem = self._make_real_memory()
        receipt = mem.add("Integration test memory — always TypeScript", memory_type="procedural")

        assert receipt.blob_id, "No blob_id on receipt"
        assert len(receipt.chain_tx_hash.lstrip("0x")) == 64, f"Bad chain_tx: {receipt.chain_tx_hash}"
        assert receipt.merkle_root, "No merkle_root on receipt"
        print(f"\n  blob_id:       {receipt.blob_id[:16]}...")
        print(f"  chain_tx_hash: 0x{receipt.chain_tx_hash.lstrip('0x')}")
        print(f"  merkle_root:   {receipt.merkle_root[:16]}...")

    @needs_key
    def test_add_and_query_returns_entry(self):
        """add() then query() returns the stored text."""
        mem = self._make_real_memory()
        unique = f"integration-query-test-{uuid.uuid4().hex[:8]}"
        mem.add(unique, memory_type="semantic")

        results, proof = mem.query(unique, top_k=1)
        assert len(results) >= 1, "query returned no results"
        assert unique in results[0], f"Expected '{unique}' in results, got: {results}"
        print(f"\n  Query hit: {results[0][:60]}")

    @needs_key
    def test_session_batching_single_chain_tx(self):
        """Session with 3 adds → exactly 1 new chain tx."""
        from ogmem.chain import ChainClient
        from web3 import Web3

        mem = self._make_real_memory()

        w3 = Web3(Web3.HTTPProvider(NET.rpc_url))
        from ogmem.config import MEMORY_REGISTRY_ABI
        registry = w3.eth.contract(
            address=Web3.to_checksum_address(REGISTRY_ADDR),
            abi=MEMORY_REGISTRY_ABI,
        )
        before = registry.functions.historyLength(mem._chain.agent_address).call()

        with mem.session() as s:
            s.add("Session entry 1", memory_type="episodic")
            s.add("Session entry 2", memory_type="episodic")
            s.add("Session entry 3", memory_type="episodic")

        after = registry.functions.historyLength(mem._chain.agent_address).call()
        assert after == before + 1, (
            f"Expected 1 chain tx, got {after - before} (before={before}, after={after})"
        )
        assert len(mem._entries) >= 3
        print(f"\n  3 adds → 1 chain tx (history: {before} → {after})")

    @needs_key
    def test_proof_verification(self):
        """Query proof is valid after a real write."""
        mem = self._make_real_memory()
        content = f"provable-memory-{uuid.uuid4().hex[:8]}"
        mem.add(content, memory_type="semantic")

        results, proof = mem.query(content, top_k=1)
        assert mem.verify_proof(proof), "Proof verification failed after real write"
        print(f"\n  Proof verified. merkle_root: {proof.merkle_root[:16]}...")

    @needs_key
    def test_memory_type_schema_persisted(self):
        """memory_type is stored correctly and survives round-trip."""
        mem = self._make_real_memory()
        mem.add("Always use TypeScript", memory_type="procedural")
        mem.add("Building fintech app", memory_type="semantic")

        stats = mem.stats()
        assert stats["by_type"]["procedural"] >= 1
        assert stats["by_type"]["semantic"] >= 1

    @needs_key
    def test_evolve_anchors_real_chain_tx(self):
        """evolve() produces a real chain transaction."""
        from web3 import Web3
        from ogmem.config import MEMORY_REGISTRY_ABI

        mem = self._make_real_memory()
        mem.add("Entry to evolve", memory_type="episodic")

        w3 = Web3(Web3.HTTPProvider(NET.rpc_url))
        registry = w3.eth.contract(
            address=Web3.to_checksum_address(REGISTRY_ADDR),
            abi=MEMORY_REGISTRY_ABI,
        )
        before = registry.functions.historyLength(mem._chain.agent_address).call()

        report = mem.evolve()
        assert report.total >= 1

        after = registry.functions.historyLength(mem._chain.agent_address).call()
        assert after > before, "evolve() did not anchor on-chain"
        print(f"\n  evolve(): {report.summary()} (chain history: {before}→{after})")

    @needs_key
    def test_distill_creates_semantic_from_episodic(self):
        """distill() compresses old episodics into a semantic entry."""
        import time as t
        mem = self._make_real_memory()

        mem.add("Old event A", memory_type="episodic")
        mem.add("Old event B", memory_type="episodic")
        # Backdate so they qualify for distillation
        for e in mem._entries:
            e["timestamp"] = int(t.time()) - 31 * 86400

        report = mem.distill(older_than_days=30, keep_originals=False)
        assert report.source_count == 2
        assert report.target_count == 1
        semantic = [e for e in mem._entries if e["memory_type"] == "semantic"]
        assert len(semantic) >= 1
        print(f"\n  distill(): {report.source_count} episodic → {report.target_count} semantic")


# ── Embeddings (local sentence-transformers) ───────────────────────────────────

class TestEmbeddingsReal:

    def test_local_embeddings_work(self):
        """sentence-transformers should embed without any network call."""
        from ogmem.compute import ComputeClient
        client = ComputeClient(serving_broker_url="", openai_api_key=None)
        vec = client.embed("hello world")
        assert len(vec) == 384, f"Expected 384-dim vector, got {len(vec)}"
        assert abs(sum(v**2 for v in vec) - 1.0) < 0.01, "Vector not normalized"

    def test_similarity_search_ranks_correctly(self):
        from ogmem.compute import ComputeClient
        client = ComputeClient(serving_broker_url="")
        v1 = client.embed("TypeScript is great")
        v2 = client.embed("TypeScript is awesome")
        v3 = client.embed("I love cats")
        query = client.embed("TypeScript")
        results = client.similarity_search(query, [v1, v2, v3], top_k=2)
        top_indices = [r[0] for r in results]
        assert 0 in top_indices and 1 in top_indices, (
            f"Expected TypeScript entries in top-2, got indices {top_indices}"
        )


# ── DA layer ───────────────────────────────────────────────────────────────────

class TestDAIntegration:

    def test_da_post_write_commitment_returns_hash(self):
        """DA client returns a deterministic local hash when gRPC is unavailable."""
        from ogmem.da import DAClient
        client = DAClient(disperser_rpc="")  # no gRPC node configured
        da_hash = client.post_write_commitment(
            agent_id="test-agent",
            blob_id="abc123",
            merkle_root="dead" * 16,
        )
        assert da_hash.startswith("local:"), f"Unexpected hash: {da_hash}"

    def test_da_fetch_own_commitment(self):
        """fetch_commitment returns what we just posted (local store)."""
        from ogmem.da import DAClient
        client = DAClient(disperser_rpc="")
        da_hash = client.post_write_commitment("agent1", "blob1", "root1")
        result = client.fetch_commitment(da_hash)
        assert result is not None
        assert result["blob_id"] == "blob1"

    def test_da_agent_history(self):
        """fetch_agent_history returns all commitments for an agent."""
        from ogmem.da import DAClient
        client = DAClient(disperser_rpc="")
        client.post_write_commitment("agent-x", "blob-a", "root-a")
        client.post_write_commitment("agent-x", "blob-b", "root-b")
        client.post_write_commitment("agent-y", "blob-c", "root-c")

        history = client.fetch_agent_history("agent-x")
        assert len(history) == 2
        blob_ids = {e["blob_id"] for e in history}
        assert blob_ids == {"blob-a", "blob-b"}
