"""Tests for proof data structures."""

import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ogmem.proof import WriteReceipt, QueryProof, AuditReport, Operation


def test_write_receipt_serialization():
    r = WriteReceipt(
        agent_id="agent-1",
        blob_id="abc123",
        merkle_root="root456",
        da_tx_hash="da789",
        chain_tx_hash="chain000",
    )
    assert r.agent_id == "agent-1"
    assert isinstance(r.timestamp, int)
    j = r.to_json()
    data = json.loads(j)
    assert data["blob_id"] == "abc123"


def test_query_proof_roundtrip():
    proof = QueryProof(
        agent_id="agent-1",
        query_hash="qhash",
        blob_ids=["b1", "b2"],
        scores=[0.95, 0.80],
        merkle_proofs=[{"leaf": "b1", "siblings": [], "directions": [], "root": "r"}],
        merkle_root="mroot",
        da_read_tx="datx",
        chain_block=42,
    )
    restored = QueryProof.from_json(proof.to_json())
    assert restored.agent_id == proof.agent_id
    assert restored.scores == proof.scores
    assert restored.chain_block == 42


def test_audit_report_summary_contains_key_info():
    report = AuditReport(
        agent_id="my-agent",
        from_block=0,
        to_block=100,
        from_timestamp=1000,
        to_timestamp=2000,
        total_writes=5,
        total_reads=3,
        operations=[],
        merkle_roots_history=[],
    )
    summary = report.summary()
    assert "my-agent" in summary
    assert "5" in summary
    assert "3" in summary
    assert "True" in summary


def test_audit_report_json_serializable():
    op = Operation(
        op_type="write",
        timestamp=int(time.time()),
        agent_id="a1",
        blob_id="b1",
        content_preview="hello...",
        merkle_root="r1",
        da_tx_hash="da1",
    )
    report = AuditReport(
        agent_id="a1",
        from_block=0, to_block=10,
        from_timestamp=0, to_timestamp=100,
        total_writes=1, total_reads=0,
        operations=[op],
        merkle_roots_history=[],
    )
    data = json.loads(report.to_json())
    assert data["total_writes"] == 1
    assert data["operations"][0]["op_type"] == "write"
