"""Proof data structures for 0G Mem."""

import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from enum import Enum

from .merkle import MerkleProof


class MemoryType(str, Enum):
    """Structured memory type classification."""
    EPISODIC   = "episodic"    # things that happened
    SEMANTIC   = "semantic"    # things the agent knows about the user
    PROCEDURAL = "procedural"  # how the user likes things done
    WORKING    = "working"     # current task context


@dataclass
class WriteReceipt:
    """Returned after a successful memory write."""
    agent_id: str
    blob_id: str           # 0G Storage content hash (root hash)
    merkle_root: str       # Updated Merkle root after this write
    da_tx_hash: str        # 0G DA transaction hash (immutable write log)
    chain_tx_hash: str     # 0G Chain transaction hash (root anchor)
    memory_type: str = MemoryType.EPISODIC.value
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


@dataclass
class QueryProof:
    """Cryptographic proof of a memory retrieval event, verifiable against 0G Chain + DA."""
    agent_id: str
    query_hash: str            # sha256(query_text)
    blob_ids: list[str]
    scores: list[float]
    merkle_proofs: list[dict]  # inclusion proof per blob_id
    merkle_root: str           # root at query time, anchored on-chain
    da_read_tx: str            # DA tx hash of this retrieval
    chain_block: int           # block where root was anchored
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> "QueryProof":
        return cls(**json.loads(data))


@dataclass
class Operation:
    """A single read or write event in the audit log."""
    op_type: str          # "write" or "read"
    timestamp: int
    agent_id: str

    # Write fields
    blob_id: Optional[str] = None
    content_preview: Optional[str] = None   # first 100 chars of memory text
    memory_type: Optional[str] = None
    merkle_root: Optional[str] = None
    da_tx_hash: Optional[str] = None
    chain_tx_hash: Optional[str] = None

    # Read fields
    query_preview: Optional[str] = None     # first 100 chars of query
    query_hash: Optional[str] = None
    retrieved_blob_ids: Optional[list] = None
    similarity_scores: Optional[list] = None
    da_read_tx: Optional[str] = None
    merkle_root_used: Optional[str] = None


@dataclass
class AuditReport:
    """Full audit report covering all memory reads and writes for an agent."""
    agent_id: str
    from_block: int
    to_block: int
    from_timestamp: int
    to_timestamp: int
    total_writes: int
    total_reads: int
    operations: list[Operation]
    merkle_roots_history: list[dict]
    eu_ai_act_compliant: bool = True
    eu_ai_act_articles: list[str] = field(
        default_factory=lambda: ["Article 12 - Logging", "Article 13 - Transparency"]
    )
    generated_at: int = field(default_factory=lambda: int(time.time()))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def summary(self) -> str:
        return (
            f"Agent: {self.agent_id}\n"
            f"Period: block {self.from_block} → {self.to_block}\n"
            f"Writes: {self.total_writes} | Reads: {self.total_reads}\n"
            f"EU AI Act Article 12 Compliant: {self.eu_ai_act_compliant}\n"
            f"Verifiable by: anyone with 0G Chain + DA access"
        )
