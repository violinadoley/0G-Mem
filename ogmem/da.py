"""0G DA client — posts read/write commitments via gRPC."""

import hashlib
import json
import pathlib
import time
from typing import Optional


class DAError(Exception):
    """Raised when a 0G DA operation fails with no fallback."""


def _try_import_grpc():
    """Try to import gRPC stubs — returns (grpc, pb2, pb2_grpc) or None."""
    import sys
    import pathlib
    # Ensure repo root is on sys.path so `proto` package is always importable
    # regardless of working directory (local vs Railway vs Docker).
    _repo_root = str(pathlib.Path(__file__).parent.parent)
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    try:
        import grpc
        from proto import disperser_pb2, disperser_pb2_grpc
        return grpc, disperser_pb2, disperser_pb2_grpc
    except ImportError:
        return None


class DAClient:
    """
    Client for 0G DA — the immutable audit log layer.

    Every write commitment: {agent_id, blob_id, merkle_root, timestamp}
    Every read commitment:  {agent_id, query_hash, blob_ids, scores, merkle_root, timestamp}

    Requires a running 0G DA node (gRPC). No fallback — raises DAError on failure.
    Run the DA node with: docker-compose up -d (see README).
    """

    def __init__(self, disperser_rpc: str, persist_path: Optional[str] = None):
        """
        Args:
            disperser_rpc: gRPC address of the DA disperser, e.g. "localhost:51001".
                           Must be non-empty — no local mode fallback.
            persist_path:  Path to persist submitted commitments to disk (optional).
                           Enables DA history to survive process restarts.
        """
        if not disperser_rpc:
            raise DAError(
                "disperser_rpc is required. "
                "Start the 0G DA node with: docker-compose up -d\n"
                "See README: https://github.com/violinadoley/0g-Mem#running-the-da-node-optional"
            )
        self.disperser_rpc = disperser_rpc
        self._persist_path = persist_path
        self._submitted: list[dict] = []  # store for fetch_commitment / fetch_agent_history
        self._grpc_available: Optional[bool] = None  # lazily detected
        if persist_path:
            self._load_submitted()

    def post_write_commitment(
        self,
        agent_id: str,
        blob_id: str,
        merkle_root: str,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Post a write commitment to 0G DA.

        Returns da_tx_hash — unique identifier for this commitment.
        """
        commitment = {
            "type": "memory_write",
            "agent_id": agent_id,
            "blob_id": blob_id,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
            "version": "1.0",
        }
        return self._submit(commitment)

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
        """
        Post a full agent turn trace to 0G DA.

        Stores hashes of user message and reply (not plaintext) for privacy.
        Returns da_tx_hash.
        """
        commitment = {
            "type": "agent_turn",
            "agent_id": agent_id,
            "user_message_hash": hashlib.sha256(user_message.encode()).hexdigest(),
            "assistant_reply_hash": hashlib.sha256(assistant_reply.encode()).hexdigest(),
            "memories_retrieved_count": len(memories_retrieved),
            "memories_retrieved_hashes": [
                hashlib.sha256(m.encode()).hexdigest()[:16] for m in memories_retrieved
            ],
            "tool_calls": [
                {
                    "name": tc.get("name", ""),
                    "args_hash": hashlib.sha256(
                        json.dumps(tc.get("arguments", {}), sort_keys=True).encode()
                    ).hexdigest()[:16],
                }
                for tc in tool_calls
            ],
            "write_blob_ids": write_blob_ids,
            "merkle_root": merkle_root,
            "latency_ms": latency_ms,
            "timestamp": timestamp or int(time.time()),
            "version": "1.0",
        }
        return self._submit(commitment)

    def post_read_commitment(
        self,
        agent_id: str,
        query_hash: str,
        blob_ids: list[str],
        scores: list[float],
        merkle_root: str,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Post a read commitment to 0G DA.

        This is the immutable proof that a retrieval happened.
        Returns da_tx_hash.
        """
        commitment = {
            "type": "memory_read",
            "agent_id": agent_id,
            "query_hash": query_hash,
            "blob_ids": blob_ids,
            "scores": scores,
            "merkle_root": merkle_root,
            "timestamp": timestamp or int(time.time()),
            "version": "1.0",
        }
        return self._submit(commitment)

    def fetch_commitment(self, da_tx_hash: str) -> Optional[dict]:
        """
        Fetch a specific commitment by its DA transaction hash.
        Used during audit report generation.
        """
        # Check local store first
        for entry in self._submitted:
            if entry.get("da_tx_hash") == da_tx_hash:
                return entry.get("commitment")

        # Try live gRPC retrieval if it's a grpc: hash
        if da_tx_hash.startswith("grpc:") and self.disperser_rpc:
            raw = self._grpc_retrieve(da_tx_hash)
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass

        return None

    def fetch_agent_history(self, agent_id: str) -> list[dict]:
        """
        Fetch all commitments for a given agent_id from 0G DA.
        Used to reconstruct the full audit timeline.
        """
        history = [
            e for e in self._submitted if e.get("commitment", {}).get("agent_id") == agent_id
        ]
        return [
            {"da_tx_hash": e["da_tx_hash"], **e["commitment"]}
            for e in history
        ]

    def _submit(self, commitment: dict) -> str:
        """Submit commitment to 0G DA via gRPC. Raises DAError on failure."""
        if not self._is_grpc_available():
            raise DAError(
                "gRPC dependencies not installed. Run: pip install grpcio grpcio-tools\n"
                "Then regenerate proto stubs: python -m grpc_tools.protoc ..."
            )

        serialized = json.dumps(commitment, sort_keys=True).encode()
        da_tx_hash = self._grpc_disperse(serialized)
        if not da_tx_hash:
            raise DAError(
                f"0G DA dispersal failed. Check that the DA node is running at: "
                f"{self.disperser_rpc}\n"
                "Start with: docker-compose up -d"
            )

        self._submitted.append({
            "da_tx_hash": da_tx_hash,
            "commitment": commitment,
            "submitted_at": int(time.time()),
        })
        self._save_submitted()
        return da_tx_hash

    def _load_submitted(self) -> None:
        """Load persisted DA commitments from disk."""
        try:
            p = pathlib.Path(str(self._persist_path))
            if p.exists():
                self._submitted = json.loads(p.read_text())
        except Exception:
            self._submitted = []

    def _save_submitted(self) -> None:
        """Persist DA commitments to disk (keeps last 1000 entries)."""
        if not self._persist_path:
            return
        try:
            p = pathlib.Path(str(self._persist_path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._submitted[-1000:]))
        except Exception:
            pass

    def _is_grpc_available(self) -> bool:
        if self._grpc_available is None:
            self._grpc_available = _try_import_grpc() is not None
        return self._grpc_available

    def _grpc_disperse(self, data: bytes) -> Optional[str]:
        """Submit bytes via gRPC DisperseBlob. Returns "grpc:<request_id_hex>" or None."""
        imports = _try_import_grpc()
        if not imports:
            return None
        grpc, pb2, pb2_grpc = imports
        try:
            channel = grpc.insecure_channel(self.disperser_rpc)
            stub = pb2_grpc.DisperserStub(channel)
            response = stub.DisperseBlob(
                pb2.DisperseBlobRequest(data=data),
                timeout=30,
            )
            request_id_hex = response.request_id.hex()
            channel.close()
            return f"grpc:{request_id_hex}"
        except Exception:
            return None

    def _grpc_retrieve(self, da_tx_hash: str) -> Optional[bytes]:
        """Poll GetBlobStatus then call RetrieveBlob. Returns raw bytes or None."""
        imports = _try_import_grpc()
        if not imports:
            return None
        grpc, pb2, pb2_grpc = imports
        try:
            request_id_hex = da_tx_hash.removeprefix("grpc:")
            request_id = bytes.fromhex(request_id_hex)

            channel = grpc.insecure_channel(self.disperser_rpc)
            stub = pb2_grpc.DisperserStub(channel)

            status_resp = stub.GetBlobStatus(
                pb2.BlobStatusRequest(request_id=request_id),
                timeout=15,
            )
            if status_resp.status not in (pb2.BlobStatus.CONFIRMED, pb2.BlobStatus.FINALIZED):
                channel.close()
                return None

            header = status_resp.info.blob_header
            retrieve_resp = stub.RetrieveBlob(
                pb2.RetrieveBlobRequest(
                    storage_root=header.storage_root,
                    epoch=header.epoch,
                    quorum_id=header.quorum_id,
                ),
                timeout=15,
            )
            channel.close()
            return retrieve_resp.data
        except Exception:
            return None
