"""0G Mem — Verifiable, Private, Owned Agent Memory on 0G Labs."""

from .memory import VerifiableMemory, SyncReport
from .proof import AuditReport, QueryProof, WriteReceipt, MemoryType
from .encryption import derive_encryption_key
from .inference import ZeroGInferenceClient, ChatMessage
from .storage import StorageError
from .da import DAError

__all__ = [
    "VerifiableMemory",
    "WriteReceipt",
    "QueryProof",
    "AuditReport",
    "MemoryType",
    "SyncReport",
    "derive_encryption_key",
    "ZeroGInferenceClient",
    "ChatMessage",
    "StorageError",
    "DAError",
]
__version__ = "0.2.0"
