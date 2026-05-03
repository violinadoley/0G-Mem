"""Integration tests for VerifiableMemory using mock 0G clients (no network required)."""

import sys
import os
import hashlib
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ogmem.memory import VerifiableMemory
from ogmem.proof import WriteReceipt, QueryProof, AuditReport
from ogmem.merkle import MerkleTree


class MockStorage:
    """Simulates 0G Storage — in-memory blob store."""
    def __init__(self):
        self._store = {}

    def upload(self, data: dict) -> str:
        import json
        serialized = json.dumps(data, sort_keys=True).encode()
        blob_id = hashlib.sha256(serialized).hexdigest()
        self._store[blob_id] = data
        return blob_id

    def download(self, blob_id: str):
        return self._store.get(blob_id)

    def upload_encrypted(self, data: dict, encryption_key: bytes) -> str:
        import json
        from ogmem.encryption import encrypt
        plaintext = json.dumps(data, sort_keys=True).encode()
        ciphertext = encrypt(plaintext, encryption_key)
        blob_id = hashlib.sha256(ciphertext).hexdigest()
        self._store[blob_id] = data  # store plaintext for easy retrieval in tests
        return blob_id

    def download_encrypted(self, blob_id: str, encryption_key: bytes):
        return self._store.get(blob_id)

    def exists(self, blob_id: str) -> bool:
        return blob_id in self._store


class MockCompute:
    """Simulates 0G Compute — deterministic local embeddings."""
    EMBEDDING_DIM = 64  # smaller for tests

    def embed(self, text: str) -> list[float]:
        import math
        seed = hashlib.sha256(text.encode()).digest()
        result = []
        i = 0
        while len(result) < self.EMBEDDING_DIM:
            chunk = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
            for j in range(0, len(chunk) - 1, 2):
                val = (chunk[j] * 256 + chunk[j + 1]) / 65535.0
                result.append(val - 0.5)
            i += 1
        mag = math.sqrt(sum(x * x for x in result[:self.EMBEDDING_DIM]))
        return [x / mag for x in result[:self.EMBEDDING_DIM]]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def similarity_search(self, query_vec, candidate_vecs, top_k=3):
        import math
        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            ma = math.sqrt(sum(x*x for x in a))
            mb = math.sqrt(sum(x*x for x in b))
            return dot / (ma * mb) if ma and mb else 0.0

        scores = [(i, cosine(query_vec, v)) for i, v in enumerate(candidate_vecs)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class MockDA:
    """Simulates 0G DA — in-memory commitment log."""
    def __init__(self):
        self._log = []

    def post_write_commitment(self, agent_id, blob_id, merkle_root, timestamp=None):
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

    def post_read_commitment(self, agent_id, query_hash, blob_ids, scores, merkle_root, timestamp=None):
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
        self, agent_id, user_message, assistant_reply, memories_retrieved,
        tool_calls, write_blob_ids, merkle_root, latency_ms=0, timestamp=None,
    ):
        import hashlib as _h
        tx = _h.sha256(f"turn:{agent_id}:{user_message[:32]}:{merkle_root}".encode()).hexdigest()
        self._log.append({
            "type": "agent_turn",
            "da_tx_hash": tx,
            "agent_id": agent_id,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
        })
        return tx

    def fetch_commitment(self, da_tx_hash):
        for e in self._log:
            if e["da_tx_hash"] == da_tx_hash:
                return e
        return None

    def fetch_agent_history(self, agent_id):
        return [e for e in self._log if e["agent_id"] == agent_id]


class MockChain:
    """Simulates 0G Chain MemoryRegistry — in-memory state."""
    def __init__(self):
        self._history = []
        self.agent_address = "0xMockAgent1234"

    def update_root(self, merkle_root, da_tx_hash):
        self._history.append({
            "merkle_root": merkle_root,
            "block_number": len(self._history) + 100,
            "da_tx_hash": da_tx_hash,
            "timestamp": int(time.time()),
        })
        return hashlib.sha256(f"chain:{merkle_root}".encode()).hexdigest()

    def get_latest_root(self, agent_address):
        if not self._history:
            return None
        from ogmem.chain import MemoryState
        s = self._history[-1]
        return MemoryState(**s)

    def get_historical_root(self, agent_address, index):
        from ogmem.chain import MemoryState
        if not self._history:
            return None
        if index < 0:
            index = len(self._history) + index
        if 0 <= index < len(self._history):
            return MemoryState(**self._history[index])
        return None

    def get_all_roots(self, agent_address):
        from ogmem.chain import MemoryState
        return [MemoryState(**s) for s in self._history]


def make_memory(agent_id="test-agent") -> VerifiableMemory:
    """VerifiableMemory with all mock clients. encrypted=False for deterministic blob_ids."""
    import pathlib
    # Clear persisted index so tests start with a clean slate
    _safe_id = agent_id.replace("/", "_").replace("\\", "_")[:64]
    data_dir = pathlib.Path.home() / ".0g"
    (data_dir / f"memory_{_safe_id}.json").unlink(missing_ok=True)
    # Also remove old-style index if present
    pathlib.Path(f".ogmem_index_{agent_id}.json").unlink(missing_ok=True)

    return VerifiableMemory(
        agent_id=agent_id,
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        encrypted=False,
        _storage=MockStorage(),  # type: ignore[arg-type]
        _compute=MockCompute(),  # type: ignore[arg-type]
        _da=MockDA(),  # type: ignore[arg-type]
        _chain=MockChain(),  # type: ignore[arg-type]
    )


class TestWrite:
    def test_add_returns_write_receipt(self):
        mem = make_memory()
        receipt = mem.add("user prefers formal tone")
        assert isinstance(receipt, WriteReceipt)
        assert receipt.blob_id
        assert receipt.merkle_root
        assert receipt.da_tx_hash
        assert receipt.chain_tx_hash
        assert receipt.agent_id == "test-agent"

    def test_blob_id_is_deterministic(self):
        mem = make_memory()
        r1 = mem.add("same text")
        # Reset and add same text — blob_id should match
        mem2 = make_memory()
        r2 = mem2.add("same text")
        assert r1.blob_id == r2.blob_id

    def test_merkle_root_changes_on_each_add(self):
        mem = make_memory()
        r1 = mem.add("first memory")
        r2 = mem.add("second memory")
        assert r1.merkle_root != r2.merkle_root

    def test_multiple_adds_accumulate(self):
        mem = make_memory()
        for i in range(5):
            mem.add(f"memory entry {i}")
        assert len(mem._entries) == 5

    def test_da_write_logged(self):
        mem = make_memory()
        receipt = mem.add("test entry")
        history = mem._da.fetch_agent_history("test-agent")
        assert len(history) == 1
        assert history[0]["type"] == "memory_write"
        assert history[0]["blob_id"] == receipt.blob_id

    def test_chain_root_anchored(self):
        mem = make_memory()
        receipt = mem.add("anchor test")
        state = mem._chain.get_latest_root(mem._chain.agent_address)
        assert state is not None
        assert state.merkle_root == receipt.merkle_root


class TestQuery:
    def test_query_returns_results_and_proof(self):
        mem = make_memory()
        mem.add("the sky is blue")
        results, proof = mem.query("what color is the sky?")
        assert isinstance(results, list)
        assert isinstance(proof, QueryProof)

    def test_query_on_empty_memory(self):
        mem = make_memory()
        results, proof = mem.query("anything")
        assert results == []
        assert proof.blob_ids == []

    def test_query_returns_relevant_results(self):
        mem = make_memory()
        mem.add("user prefers formal English responses")
        mem.add("user is located in New York")
        mem.add("user works in finance")
        results, _proof = mem.query("what does the user prefer?")
        assert len(results) > 0
        # The formal preference entry should be among top results
        assert any("formal" in r or "prefer" in r for r in results)

    def test_proof_has_merkle_proofs(self):
        mem = make_memory()
        mem.add("test memory for proof")
        _results, proof = mem.query("test memory")
        assert len(proof.merkle_proofs) > 0
        assert proof.merkle_root
        assert proof.da_read_tx

    def test_da_read_logged(self):
        mem = make_memory()
        mem.add("log test entry")
        mem.query("log test")
        history = mem._da.fetch_agent_history("test-agent")
        read_events = [e for e in history if e["type"] == "memory_read"]
        assert len(read_events) == 1

    def test_query_hash_is_sha256_of_query(self):
        mem = make_memory()
        mem.add("some memory")
        query_text = "some query"
        _, proof = mem.query(query_text)
        expected_hash = hashlib.sha256(query_text.encode()).hexdigest()
        assert proof.query_hash == expected_hash

    def test_last_proof_set_after_query(self):
        mem = make_memory()
        mem.add("test")
        assert mem.last_proof() is None
        mem.query("test")
        assert mem.last_proof() is not None

    def test_top_k_respected(self):
        mem = make_memory()
        for i in range(10):
            mem.add(f"memory item {i}")
        _, proof = mem.query("memory item", top_k=3)
        assert len(proof.blob_ids) <= 3


class TestProofVerification:
    def test_verify_valid_proof(self):
        mem = make_memory()
        mem.add("verifiable memory entry")
        _, proof = mem.query("verifiable memory")
        assert mem.verify_proof(proof) is True

    def test_verify_proof_after_multiple_writes(self):
        mem = make_memory()
        for i in range(5):
            mem.add(f"entry {i}")
        _, proof = mem.query("entry 2")
        assert mem.verify_proof(proof) is True

    def test_tampered_proof_fails_verification(self):
        mem = make_memory()
        mem.add("tamper test")
        _, proof = mem.query("tamper test")
        # Tamper with the merkle root
        proof.merkle_root = "deadbeef" * 8
        assert mem.verify_proof(proof) is False

    def test_tampered_blob_id_fails_verification(self):
        mem = make_memory()
        mem.add("original content")
        _, proof = mem.query("original")
        # Tamper with blob_id
        if proof.blob_ids:
            proof.blob_ids[0] = "fakeblobid" * 4
        assert mem.verify_proof(proof) is False

    def test_proof_serialization_roundtrip(self):
        mem = make_memory()
        mem.add("serialize test")
        _, proof = mem.query("serialize")
        json_str = proof.to_json()
        restored = QueryProof.from_json(json_str)
        assert mem.verify_proof(restored) is True


class TestAuditReport:
    def test_audit_report_covers_all_operations(self):
        mem = make_memory()
        mem.add("first entry")
        mem.add("second entry")
        mem.query("first")
        mem.query("second")
        report = mem.export_audit()
        assert report.total_writes == 2
        assert report.total_reads == 2

    def test_audit_report_is_eu_ai_act_compliant(self):
        mem = make_memory()
        mem.add("compliance test")
        mem.query("compliance")
        report = mem.export_audit()
        assert report.eu_ai_act_compliant is True
        assert len(report.eu_ai_act_articles) > 0

    def test_audit_report_operations_in_order(self):
        mem = make_memory()
        mem.add("first")
        mem.add("second")
        report = mem.export_audit()
        writes = [op for op in report.operations if op.op_type == "write"]
        assert len(writes) == 2

    def test_audit_report_to_json(self):
        import json
        mem = make_memory()
        mem.add("json test")
        report = mem.export_audit()
        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["agent_id"] == "test-agent"
        assert data["eu_ai_act_compliant"] is True

    def test_audit_summary(self):
        mem = make_memory()
        mem.add("summary test")
        report = mem.export_audit()
        summary = report.summary()
        assert "test-agent" in summary
        assert "Writes" in summary


class TestLangChainCompat:
    def test_memory_variables(self):
        mem = make_memory()
        assert "history" in mem.memory_variables

    def test_save_and_load_context(self):
        mem = make_memory()
        mem.save_context(
            inputs={"input": "Hello, what's the weather?"},
            outputs={"response": "It's sunny today."}
        )
        assert len(mem._entries) == 2
        result = mem.load_memory_variables({"input": "weather"})
        assert "history" in result
        assert isinstance(result["history"], str)

    def test_clear_resets_state(self):
        mem = make_memory()
        mem.add("something to forget")
        mem.query("something")
        mem.clear()
        assert len(mem._entries) == 0
        assert mem.last_proof() is None

    def test_load_memory_variables_empty(self):
        mem = make_memory()
        result = mem.load_memory_variables({"input": "test"})
        assert result == {"history": ""}


class TestEndToEnd:
    def test_full_pipeline(self):
        """
        Complete end-to-end: write → query → verify → audit.
        Simulates exactly what the legal assistant demo does.
        """
        mem = make_memory(agent_id="e2e-test")

        # Ingest contract clauses
        clauses = [
            "Section 3.1: Liability cap is $1M per incident.",
            "Section 4.2: 30 days notice required for termination.",
            "Section 5.1: Confidentiality lasts 3 years post-termination.",
        ]
        receipts = [mem.add(c) for c in clauses]

        # All writes should have unique blob_ids and roots
        blob_ids = [r.blob_id for r in receipts]
        assert len(set(blob_ids)) == len(clauses)

        # Query and verify each
        questions = [
            ("What is the liability cap?", "Liability"),
            ("How much notice to terminate?", "termination"),
            ("How long is confidentiality?", "Confidentiality"),
        ]

        for question, _expected_keyword in questions:
            results, proof = mem.query(question, top_k=1)
            assert len(results) > 0
            assert mem.verify_proof(proof), f"Proof failed for: {question}"

        # Full audit
        report = mem.export_audit()
        assert report.total_writes == 3
        assert report.total_reads == 3
        assert report.eu_ai_act_compliant is True

        # All Merkle roots in history should be different (each write changes root)
        roots = [s.merkle_root for s in mem._chain.get_all_roots("")]
        assert len(roots) == 3
        assert len(set(roots)) == 3  # all unique

    def test_multiple_agents_isolated(self):
        """Two agents share no memory state."""
        agent_a = make_memory("agent-alpha")
        agent_b = make_memory("agent-beta")

        agent_a.add("agent A's secret memory")
        agent_b.add("agent B's private context")

        results_a, _ = agent_a.query("secret memory")
        results_b, _ = agent_b.query("private context")

        # Each agent only sees their own memory
        assert any("secret" in r for r in results_a)
        assert any("private" in r for r in results_b)

        # Agent A should not find agent B's memory
        results_cross, _ = agent_a.query("private context")
        # All results come from agent A's store only
        for r in results_cross:
            assert "agent B" not in r


# ── New feature tests ──────────────────────────────────────────────────────────

class TestLLMDistillation:

    def test_distill_without_inference_fn_uses_concatenation(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "old-1", "text": "User likes Python", "embedding": [0.1] * 384,
            "memory_type": "episodic", "timestamp": int(time.time()) - 40 * 86400,
            "retrieval_count": 0, "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        report = mem.distill(older_than_days=30)
        assert report.source_count == 1
        # Naive concatenation: distilled entry exists
        semantic = [e for e in mem._entries if e["memory_type"] == "semantic"]
        assert len(semantic) == 1
        assert "Distilled" in semantic[0]["text"]

    def test_distill_with_inference_fn_uses_llm(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "old-2", "text": "User loves TypeScript", "embedding": [0.2] * 384,
            "memory_type": "episodic", "timestamp": int(time.time()) - 40 * 86400,
            "retrieval_count": 0, "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        called_with = []
        def mock_llm(prompt):
            called_with.append(prompt)
            return "User is a TypeScript developer."

        report = mem.distill(older_than_days=30, inference_fn=mock_llm)
        assert report.source_count == 1
        assert len(called_with) == 1
        assert "episodic" in called_with[0].lower() or "memories" in called_with[0].lower()
        semantic = [e for e in mem._entries if e["memory_type"] == "semantic"]
        assert semantic[0]["text"] == "User is a TypeScript developer."

    def test_distill_inference_fn_failure_falls_back(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "old-3", "text": "User prefers dark mode", "embedding": [0.3] * 384,
            "memory_type": "episodic", "timestamp": int(time.time()) - 40 * 86400,
            "retrieval_count": 0, "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        def failing_llm(_prompt):
            raise RuntimeError("LLM unavailable")

        report = mem.distill(older_than_days=30, inference_fn=failing_llm)
        assert report.source_count == 1
        semantic = [e for e in mem._entries if e["memory_type"] == "semantic"]
        assert len(semantic) == 1  # fallback still produced one entry


class TestConflictDetection:

    def test_stats_includes_conflicts_key(self):
        mem = make_memory()
        stats = mem.stats()
        assert "conflicts" in stats
        assert isinstance(stats["conflicts"], list)

    def test_no_conflicts_when_no_procedural(self):
        mem = make_memory()
        mem.add("User message", memory_type="episodic")
        stats = mem.stats()
        assert stats["conflicts"] == []

    def test_detects_conflicting_procedural_memories(self):
        mem = make_memory()
        mem._entries.extend([
            {
                "blob_id": "p1", "text": "User prefers Python for data analysis projects",
                "embedding": [0.1] * 384, "memory_type": "procedural",
                "timestamp": int(time.time()), "retrieval_count": 0,
                "last_retrieved": 0, "stale": False, "weight": 1.0,
            },
            {
                "blob_id": "p2", "text": "User prefers TypeScript for data analysis projects",
                "embedding": [0.2] * 384, "memory_type": "procedural",
                "timestamp": int(time.time()), "retrieval_count": 0,
                "last_retrieved": 0, "stale": False, "weight": 1.0,
            },
        ])
        stats = mem.stats()
        assert len(stats["conflicts"]) >= 1
        conflict = stats["conflicts"][0]
        assert "entry1" in conflict
        assert "entry2" in conflict
        assert "overlap" in conflict


class TestMemorySummary:

    def test_summary_no_memories(self):
        mem = make_memory()
        result = mem.summary()
        assert "No memories" in result

    def test_summary_structured_fallback(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "s1", "text": "User is a Python developer",
            "embedding": [0.1] * 384, "memory_type": "procedural",
            "timestamp": int(time.time()), "retrieval_count": 0,
            "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        result = mem.summary()
        assert "Preferences" in result
        assert "Python" in result

    def test_summary_with_inference_fn(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "s2", "text": "User loves TypeScript and React",
            "embedding": [0.2] * 384, "memory_type": "procedural",
            "timestamp": int(time.time()), "retrieval_count": 0,
            "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        called = []
        def mock_llm(prompt):
            called.append(prompt)
            return "A TypeScript/React developer."

        result = mem.summary(inference_fn=mock_llm)
        assert len(called) == 1
        assert result == "A TypeScript/React developer."

    def test_summary_inference_fn_fallback_on_error(self):
        mem = make_memory()
        mem._entries.append({
            "blob_id": "s3", "text": "User prefers vim keybindings",
            "embedding": [0.3] * 384, "memory_type": "procedural",
            "timestamp": int(time.time()), "retrieval_count": 0,
            "last_retrieved": 0, "stale": False, "weight": 1.0,
        })
        def bad_fn(_p):
            raise RuntimeError("no")

        result = mem.summary(inference_fn=bad_fn)
        assert isinstance(result, str)
        assert len(result) > 0


class TestDAAgentTurn:

    def test_post_agent_turn_returns_hash(self):
        da = MockDA()
        h = da.post_agent_turn(
            agent_id="test", user_message="hi", assistant_reply="hello",
            memories_retrieved=["mem1"], tool_calls=[], write_blob_ids=["b1"],
            merkle_root="abc123", latency_ms=50,
        )
        assert isinstance(h, str)
        assert len(h) > 0

    def test_post_agent_turn_logged(self):
        da = MockDA()
        da.post_agent_turn(
            agent_id="test", user_message="hi", assistant_reply="hello",
            memories_retrieved=[], tool_calls=[], write_blob_ids=[],
            merkle_root="root", latency_ms=0,
        )
        turns = [e for e in da._log if e.get("type") == "agent_turn"]
        assert len(turns) == 1


class TestNewTools:

    def test_run_python_basic(self):
        from runtime.tools import _run_python
        result = _run_python("print(2 + 2)")
        assert result == "4"

    def test_run_python_timeout(self):
        from runtime.tools import _run_python
        result = _run_python("import time; time.sleep(999)", timeout=1)
        assert "Timeout" in result or "timeout" in result.lower()

    def test_run_python_error(self):
        from runtime.tools import _run_python
        result = _run_python("raise ValueError('test error')")
        assert "Error" in result or "ValueError" in result

    def test_read_file_not_found(self):
        from runtime.tools import _read_file
        result = _read_file("/nonexistent/path/file.txt")
        assert "not found" in result.lower()

    def test_write_and_read_file(self, tmp_path):
        from runtime.tools import _write_file, _read_file
        p = str(tmp_path / "test.txt")
        write_result = _write_file(p, "hello world")
        assert "Written" in write_result
        read_result = _read_file(p)
        assert read_result == "hello world"

    def test_diff_texts_no_change(self):
        from runtime.tools import _diff_texts
        result = _diff_texts("same", "same")
        assert result == "(no changes)"

    def test_diff_texts_with_change(self):
        from runtime.tools import _diff_texts
        result = _diff_texts("foo\nbar\n", "foo\nbaz\n")
        assert "-bar" in result
        assert "+baz" in result
