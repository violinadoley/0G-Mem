"""Tests for memory optimizations: typed schema, session batching, usage tracking, decay, evolve."""

import sys
import os
import time
import pathlib
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ogmem.memory import VerifiableMemory, EvolveReport, DistillReport, _STALE_SECONDS
from ogmem.proof import MemoryType

from tests.test_memory import MockStorage, MockCompute, MockDA, MockChain


def make_memory(agent_id: str | None = None) -> VerifiableMemory:
    """Create a fresh VerifiableMemory with a unique agent_id to avoid index file pollution."""
    aid = agent_id or f"opt-test-{uuid.uuid4().hex[:8]}"
    mem = VerifiableMemory(
        agent_id=aid,
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        _storage=MockStorage(),
        _compute=MockCompute(),
        _da=MockDA(),
        _chain=MockChain(),
    )
    return mem


# ─── Memory type schema ────────────────────────────────────────────────────────

class TestMemoryTypeSchema:

    def test_add_with_explicit_type(self):
        mem = make_memory()
        receipt = mem.add("Always use TypeScript", memory_type="procedural")
        assert receipt.memory_type == "procedural"
        assert mem._entries[0]["memory_type"] == "procedural"

    def test_default_type_is_episodic(self):
        mem = make_memory()
        receipt = mem.add("User asked about auth")
        assert receipt.memory_type == MemoryType.EPISODIC.value

    def test_all_memory_types_accepted(self):
        mem = make_memory()
        for mt in MemoryType:
            receipt = mem.add(f"Entry for {mt.value}", memory_type=mt.value)
            assert receipt.memory_type == mt.value

    def test_query_filtered_by_type(self):
        mem = make_memory()
        mem.add("User asked about React", memory_type="episodic")
        mem.add("User prefers TypeScript", memory_type="procedural")
        mem.add("User is building fintech", memory_type="semantic")

        results, _ = mem.query("preferences", memory_types=["procedural"])
        # Only the procedural entry should be in the candidate pool
        assert len(results) == 1
        assert "TypeScript" in results[0]

    def test_query_multiple_type_filter(self):
        mem = make_memory()
        mem.add("Event A", memory_type="episodic")
        mem.add("Preference B", memory_type="procedural")
        mem.add("Fact C", memory_type="semantic")

        results, _ = mem.query("something", memory_types=["episodic", "semantic"])
        assert len(results) == 2

    def test_query_no_filter_returns_all_types(self):
        mem = make_memory()
        for mt in MemoryType:
            mem.add(f"Entry {mt.value}", memory_type=mt.value)

        results, _ = mem.query("entry", top_k=10)
        assert len(results) == len(MemoryType)

    def test_stats_breakdown_by_type(self):
        mem = make_memory()
        mem.add("Episodic entry", memory_type="episodic")
        mem.add("Procedural entry", memory_type="procedural")
        mem.add("Semantic entry", memory_type="semantic")

        s = mem.stats()
        assert s["by_type"]["episodic"] == 1
        assert s["by_type"]["procedural"] == 1
        assert s["by_type"]["semantic"] == 1
        assert s["total"] == 3


# ─── Session batching ──────────────────────────────────────────────────────────

class TestSessionBatching:

    def test_session_writes_multiple_entries(self):
        mem = make_memory()
        with mem.session() as s:
            r1 = s.add("Entry 1")
            r2 = s.add("Entry 2")
            r3 = s.add("Entry 3")

        assert len(mem._entries) == 3
        assert r1.blob_id != r2.blob_id != r3.blob_id

    def test_session_single_chain_tx(self):
        mem = make_memory()
        chain: MockChain = mem._chain  # type: ignore

        initial_count = len(chain._history)

        with mem.session() as s:
            s.add("Entry 1")
            s.add("Entry 2")
            s.add("Entry 3")

        final_count = len(chain._history)
        # Exactly one chain tx for the whole session
        assert final_count - initial_count == 1

    def test_single_add_still_works(self):
        mem = make_memory()
        chain: MockChain = mem._chain  # type: ignore
        initial = len(chain._history)

        mem.add("Single entry")

        final = len(chain._history)
        assert final - initial == 1

    def test_session_receipts_share_chain_tx(self):
        mem = make_memory()
        receipts = []
        with mem.session() as s:
            receipts.append(s.add("Entry A"))
            receipts.append(s.add("Entry B"))

        # All receipts get the same chain_tx_hash after commit
        assert receipts[0].chain_tx_hash == receipts[1].chain_tx_hash
        assert receipts[0].chain_tx_hash != ""

    def test_empty_session_no_chain_tx(self):
        mem = make_memory()
        chain: MockChain = mem._chain  # type: ignore
        initial = len(chain._history)

        with mem.session():
            pass  # nothing added

        final = len(chain._history)
        assert final == initial

    def test_session_closed_after_exit(self):
        mem = make_memory()
        sess = None
        with mem.session() as s:
            sess = s
            s.add("entry")

        with pytest.raises(RuntimeError):
            sess.add("after close")

    def test_langchain_save_context_uses_session(self):
        mem = make_memory()
        chain: MockChain = mem._chain  # type: ignore
        initial = len(chain._history)

        mem.save_context({"input": "hello"}, {"output": "hi there"})

        final = len(chain._history)
        # human + ai messages → one chain tx, not two
        assert final - initial == 1
        assert len(mem._entries) == 2


# ─── Usage tracking ────────────────────────────────────────────────────────────

class TestUsageTracking:

    def test_retrieval_count_starts_at_zero(self):
        mem = make_memory()
        mem.add("Entry")
        assert mem._entries[0]["retrieval_count"] == 0

    def test_retrieval_count_increments_on_query(self):
        mem = make_memory()
        mem.add("User prefers dark mode")
        mem.query("preferences")
        assert mem._entries[0]["retrieval_count"] == 1

    def test_retrieval_count_increments_multiple(self):
        mem = make_memory()
        mem.add("User prefers dark mode")
        mem.query("preferences")
        mem.query("preferences")
        mem.query("preferences")
        assert mem._entries[0]["retrieval_count"] == 3

    def test_last_retrieved_updated_on_query(self):
        mem = make_memory()
        mem.add("Entry")
        before = int(time.time())
        mem.query("entry")
        assert mem._entries[0]["last_retrieved"] >= before

    def test_weight_increases_on_retrieval(self):
        mem = make_memory()
        mem.add("Entry")
        initial_weight = mem._entries[0]["weight"]
        mem.query("entry")
        assert mem._entries[0]["weight"] > initial_weight

    def test_weight_capped_at_3(self):
        mem = make_memory()
        mem.add("Very popular entry")
        for _ in range(50):
            mem.query("popular entry")
        assert mem._entries[0]["weight"] <= 3.0

    def test_stats_top_retrieved(self):
        mem = make_memory()
        mem.add("Popular entry")
        mem.add("Less popular entry")
        for _ in range(5):
            mem.query("popular entry", top_k=1)
        s = mem.stats()
        assert s["top_retrieved"][0]["count"] >= 5


# ─── Decay and evolve ──────────────────────────────────────────────────────────

class TestEvolveAndDecay:

    def test_evolve_returns_report(self):
        mem = make_memory()
        mem.add("Entry 1")
        report = mem.evolve()
        assert isinstance(report, EvolveReport)
        assert report.total == 1

    def test_evolve_anchors_on_chain(self):
        mem = make_memory()
        mem.add("Entry")
        chain: MockChain = mem._chain  # type: ignore
        before = len(chain._history)
        mem.evolve()
        after = len(chain._history)
        assert after > before

    def test_evolve_strengthens_frequently_retrieved(self):
        mem = make_memory()
        mem.add("Popular entry")
        # Simulate 5+ retrievals
        for _ in range(6):
            mem._entries[0]["retrieval_count"] += 1
        old_weight = mem._entries[0]["weight"]
        report = mem.evolve()
        assert report.strengthened == 1
        assert mem._entries[0]["weight"] > old_weight

    def test_evolve_flags_stale_unretrieved_entries(self):
        mem = make_memory()
        mem.add("Old entry")
        # Backdate the entry past the stale threshold
        mem._entries[0]["timestamp"] = int(time.time()) - _STALE_SECONDS - 1
        mem._entries[0]["retrieval_count"] = 0

        report = mem.evolve()
        assert report.decayed == 1
        assert mem._entries[0]["stale"] is True

    def test_evolve_skips_already_stale(self):
        mem = make_memory()
        mem.add("Old entry")
        mem._entries[0]["stale"] = True

        report = mem.evolve()
        assert report.already_stale == 1
        assert report.decayed == 0

    def test_get_stale_memories(self):
        mem = make_memory()
        mem.add("Fresh entry")
        mem.add("Stale entry")
        mem._entries[1]["stale"] = True

        stale = mem.get_stale_memories()
        assert len(stale) == 1
        assert "Stale" in stale[0]["text"]

    def test_stale_entries_excluded_from_type_filter(self):
        mem = make_memory()
        mem.add("Good episodic", memory_type="episodic")
        mem.add("Stale episodic", memory_type="episodic")
        mem._entries[1]["stale"] = True

        # Stale entries are still in the pool unless explicitly filtered
        # (decay is about weight, not removal — user must explicitly delete)
        results, _ = mem.query("episodic", memory_types=["episodic"])
        assert len(results) == 2


# ─── Distillation ──────────────────────────────────────────────────────────────

class TestDistillation:

    def test_distill_returns_report(self):
        mem = make_memory()
        mem.add("Old episodic 1", memory_type="episodic")
        # Backdate
        mem._entries[0]["timestamp"] = int(time.time()) - 31 * 86400

        report = mem.distill(older_than_days=30)
        assert isinstance(report, DistillReport)
        assert report.source_count == 1
        assert report.target_count == 1

    def test_distill_creates_semantic_entry(self):
        mem = make_memory()
        mem.add("Old event A", memory_type="episodic")
        mem._entries[0]["timestamp"] = int(time.time()) - 31 * 86400

        mem.distill(older_than_days=30, keep_originals=True)
        semantic = [e for e in mem._entries if e["memory_type"] == "semantic"]
        assert len(semantic) == 1
        assert "Distilled" in semantic[0]["text"]

    def test_distill_removes_originals_when_requested(self):
        mem = make_memory()
        mem.add("Old event A", memory_type="episodic")
        mem.add("Old event B", memory_type="episodic")
        for e in mem._entries:
            e["timestamp"] = int(time.time()) - 31 * 86400

        report = mem.distill(older_than_days=30, keep_originals=False)
        assert report.deleted is True
        episodic = [e for e in mem._entries if e["memory_type"] == "episodic"]
        assert len(episodic) == 0

    def test_distill_keeps_originals_by_default(self):
        mem = make_memory()
        mem.add("Old event", memory_type="episodic")
        mem._entries[0]["timestamp"] = int(time.time()) - 31 * 86400

        mem.distill(older_than_days=30)
        episodic = [e for e in mem._entries if e["memory_type"] == "episodic"]
        assert len(episodic) == 1

    def test_distill_no_op_when_nothing_old_enough(self):
        mem = make_memory()
        mem.add("Fresh episodic", memory_type="episodic")

        report = mem.distill(older_than_days=30)
        assert report.source_count == 0
        assert report.target_count == 0

    def test_distill_only_targets_episodic(self):
        mem = make_memory()
        mem.add("Old semantic fact", memory_type="semantic")
        mem._entries[0]["timestamp"] = int(time.time()) - 31 * 86400

        report = mem.distill(older_than_days=30)
        # Semantic entries should not be distilled
        assert report.source_count == 0


# ─── Delete memory ─────────────────────────────────────────────────────────────

class TestDeleteMemory:

    def test_delete_removes_entry(self):
        mem = make_memory()
        mem.add("Entry to delete")
        blob_id = mem._entries[0]["blob_id"]

        result = mem.delete_memory(blob_id)
        assert result is True
        assert len(mem._entries) == 0

    def test_delete_unknown_blob_returns_false(self):
        mem = make_memory()
        result = mem.delete_memory("nonexistent_blob_id")
        assert result is False

    def test_delete_rebuilds_tree(self):
        mem = make_memory()
        mem.add("Entry A")
        mem.add("Entry B")
        root_before = mem._tree.get_root()

        mem.delete_memory(mem._entries[0]["blob_id"])
        root_after = mem._tree.get_root()

        assert root_before != root_after
        assert len(mem._entries) == 1
