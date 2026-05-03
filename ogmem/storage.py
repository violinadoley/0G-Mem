"""0G Storage client — upload/download blobs via the Node.js SDK bridge."""

import json
import pathlib
import subprocess
from typing import Optional

# Max entries kept in the local download cache
_LOCAL_CACHE_MAX = 2000


class StorageError(Exception):
    """Raised when a 0G Storage operation fails with no fallback."""


import requests
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from .encryption import encrypt, decrypt

# Path to the Node.js bridge script
_BRIDGE_SCRIPT = pathlib.Path(__file__).parent.parent / "scripts" / "zg_storage.js"

# FixedPriceFlow contract ABI — submit + market()
FLOW_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "length", "type": "uint256"},
                    {"internalType": "bytes", "name": "tags", "type": "bytes"},
                    {
                        "components": [
                            {"internalType": "bytes32", "name": "root", "type": "bytes32"},
                            {"internalType": "uint256", "name": "height", "type": "uint256"},
                        ],
                        "internalType": "struct SubmissionNode[]",
                        "name": "nodes",
                        "type": "tuple[]",
                    },
                ],
                "internalType": "struct Submission",
                "name": "submission",
                "type": "tuple",
            }
        ],
        "name": "submit",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
            {"internalType": "uint256", "name": "", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "market",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# FixedPrice market contract ABI — pricePerSector
MARKET_ABI = [
    {
        "inputs": [],
        "name": "pricePerSector",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]




class StorageClient:
    """Uploads and downloads memory blobs via the 0G FixedPriceFlow protocol."""

    def __init__(
        self,
        indexer_rpc: str,
        flow_contract: str,
        private_key: str,
        chain_rpc: str,
        cache_path: Optional[str] = None,
    ):
        self.indexer_rpc = indexer_rpc.rstrip("/")
        self.flow_contract_address = flow_contract
        self.private_key = private_key
        self._chain_rpc = chain_rpc
        self._cache_path = pathlib.Path(cache_path) if cache_path else None
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        self.w3 = Web3(Web3.HTTPProvider(chain_rpc))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.account = self.w3.eth.account.from_key(private_key)
        self.flow = self.w3.eth.contract(
            address=Web3.to_checksum_address(flow_contract),
            abi=FLOW_ABI,
        )

        # Fallback local blob cache — used when Node.js bridge is unavailable.
        # Persisted to disk (cache_path) so blobs survive process restarts.
        self._local_store: dict[str, str] = {}  # blob_id -> hex-encoded bytes
        if self._cache_path:
            self._load_cache()

    def upload(self, data: dict) -> str:
        """Upload a memory blob. Returns blob_id (Merkle root hex)."""
        serialized = json.dumps(data, sort_keys=True).encode()
        return self._upload_bytes(serialized)

    def download(self, blob_id: str) -> Optional[dict]:
        """Download a blob by its Merkle root. Returns deserialized dict or None."""
        raw = self._download_bytes(blob_id)
        if raw is None:
            return None
        try:
            return json.loads(raw.rstrip(b"\x00"))
        except Exception:
            return None

    def upload_encrypted(self, data: dict, encryption_key: bytes) -> str:
        """AES-256-GCM encrypt, then upload. Returns blob_id of the encrypted blob."""
        plaintext = json.dumps(data, sort_keys=True).encode()
        ciphertext = encrypt(plaintext, encryption_key)
        return self._upload_bytes(ciphertext)

    def download_encrypted(self, blob_id: str, encryption_key: bytes) -> Optional[dict]:
        """Download and decrypt a blob. Returns dict or None on failure."""
        raw = self._download_bytes(blob_id)
        if raw is None:
            return None
        try:
            decrypted = decrypt(raw, encryption_key)
            return json.loads(decrypted)
        except Exception:
            return None

    def exists(self, blob_id: str) -> bool:
        """Return True if the blob exists in 0G Storage.

        The indexer returns the blob content on success (no 'code' key),
        and {"code": <non-zero>, "message": "..."} on failure.
        """
        try:
            resp = self.session.get(
                f"{self.indexer_rpc}/file",
                params={"root": blob_id},
                timeout=10,
            )
            data = resp.json()
            # Non-zero code → not found / error; absent code → file content returned
            if isinstance(data, dict) and data.get("code", 0) != 0:
                return False
            return resp.status_code == 200
        except Exception:
            return False

    def _get_price_per_sector(self) -> int:
        """Fetch pricePerSector from the market contract linked to the Flow contract."""
        try:
            market_addr = self.flow.functions.market().call()
            market = self.w3.eth.contract(
                address=Web3.to_checksum_address(market_addr),
                abi=MARKET_ABI,
            )
            return market.functions.pricePerSector().call()
        except Exception:
            return 0  # some testnet deployments have free storage

    def _upload_bytes(self, raw: bytes) -> str:
        """Upload via Node.js bridge. Raises StorageError if upload fails."""
        if len(raw) == 0:
            raise ValueError("Cannot upload empty blob")

        try:
            result = subprocess.run(
                ["node", str(_BRIDGE_SCRIPT), "upload",
                 self.private_key, self.indexer_rpc,
                 self._chain_rpc, raw.hex()],
                capture_output=True, text=True, timeout=120,
            )
            # SDK writes debug logs to stdout; our result is always the last JSON line
            lines = result.stdout.strip().splitlines()
            if not lines:
                raise StorageError(
                    f"0G Storage upload failed: no output from Node.js bridge.\n"
                    f"stderr: {result.stderr.strip()}"
                )
            out = json.loads(lines[-1])
            if out.get("ok"):
                return out["root_hash"].removeprefix("0x")
            raise StorageError(
                f"0G Storage upload failed: {out.get('error', 'unknown error')}"
            )
        except StorageError:
            raise
        except FileNotFoundError:
            raise StorageError(
                "Node.js is not installed or not in PATH. "
                "0G Mem requires Node.js to upload blobs to 0G Storage. "
                "Install Node.js: https://nodejs.org"
            )
        except subprocess.TimeoutExpired:
            raise StorageError(
                "0G Storage upload timed out after 120s. "
                "Check that the 0G Storage indexer is reachable at: "
                f"{self.indexer_rpc}"
            )
        except Exception as e:
            raise StorageError(f"0G Storage upload failed: {e}") from e

    def _download_bytes(self, blob_id: str) -> bytes:
        """Download raw bytes. Checks local cache first, then 0G Storage. Raises StorageError on failure."""
        clean_id = blob_id.removeprefix("0x")

        # Check local download cache (blobs already fetched this session)
        if clean_id in self._local_store:
            return bytes.fromhex(self._local_store[clean_id])

        try:
            result = subprocess.run(
                ["node", str(_BRIDGE_SCRIPT), "download",
                 self.private_key, self.indexer_rpc,
                 self._chain_rpc, clean_id],
                capture_output=True, text=True, timeout=60,
            )
            lines = result.stdout.strip().splitlines()
            if not lines:
                raise StorageError(
                    f"0G Storage download failed: no output from Node.js bridge.\n"
                    f"stderr: {result.stderr.strip()}"
                )
            out = json.loads(lines[-1])
            if out.get("ok"):
                raw = bytes.fromhex(out["data"])
                # Cache the downloaded blob for this session
                self._local_store[clean_id] = out["data"]
                self._save_cache()
                return raw
            raise StorageError(
                f"0G Storage download failed for blob {blob_id}: "
                f"{out.get('error', 'unknown error')}"
            )
        except StorageError:
            raise
        except FileNotFoundError:
            raise StorageError(
                "Node.js is not installed or not in PATH. "
                "0G Mem requires Node.js to download blobs from 0G Storage. "
                "Install Node.js: https://nodejs.org"
            )
        except subprocess.TimeoutExpired:
            raise StorageError(
                f"0G Storage download timed out after 60s for blob {blob_id}. "
                f"Check that the 0G Storage indexer is reachable at: {self.indexer_rpc}"
            )
        except Exception as e:
            raise StorageError(f"0G Storage download failed for blob {blob_id}: {e}") from e

    def _load_cache(self) -> None:
        """Load persisted local blob cache from disk."""
        try:
            if self._cache_path and self._cache_path.exists():
                self._local_store = json.loads(self._cache_path.read_text())
        except Exception:
            self._local_store = {}

    def _save_cache(self) -> None:
        """Persist local blob cache to disk, keeping only the most recent entries."""
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Trim to max entries (keep most recently inserted = last N keys)
            store = self._local_store
            if len(store) > _LOCAL_CACHE_MAX:
                keys = list(store.keys())
                store = {k: store[k] for k in keys[-_LOCAL_CACHE_MAX:]}
                self._local_store = store
            self._cache_path.write_text(json.dumps(store))
        except Exception:
            pass
