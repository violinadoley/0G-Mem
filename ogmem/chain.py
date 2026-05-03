"""0G Chain client — anchors Merkle roots via MemoryRegistry on 0G Chain (EVM, Chain ID 16600)."""

from dataclasses import dataclass
from typing import Optional

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from .config import MEMORY_REGISTRY_ABI, MEMORY_NFT_ABI


@dataclass
class MemoryState:
    merkle_root: str
    block_number: int
    da_tx_hash: str
    timestamp: int


class ChainClient:
    """Interacts with MemoryRegistry and MemoryNFT contracts on 0G Chain."""

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        registry_contract_address: str,
        nft_contract_address: Optional[str] = None,
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        # 0G Chain uses POA — needed for correct block header parsing
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self.account = self.w3.eth.account.from_key(private_key)
        self.registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(registry_contract_address),
            abi=MEMORY_REGISTRY_ABI,
        )
        self.nft = None
        if nft_contract_address:
            self.nft = self.w3.eth.contract(
                address=Web3.to_checksum_address(nft_contract_address),
                abi=MEMORY_NFT_ABI,
            )

    def update_root(self, merkle_root: str, da_tx_hash: str) -> str:
        """Anchor a Merkle root on-chain. Returns chain_tx_hash."""
        merkle_root_bytes = bytes.fromhex(merkle_root.removeprefix("0x").zfill(64))
        # da_tx_hash may be a "local:..." hash from offline DA mode — hash it to bytes32
        da_clean = da_tx_hash.removeprefix("0x")
        if ":" in da_tx_hash:
            import hashlib
            da_tx_hash_bytes = hashlib.sha256(da_tx_hash.encode()).digest()
        else:
            da_tx_hash_bytes = bytes.fromhex(da_clean.zfill(64))

        fn = self.registry.functions.updateRoot(merkle_root_bytes, da_tx_hash_bytes)
        gas = fn.estimate_gas({"from": self.account.address})
        # 0G Chain min tip is 2 Gwei; use 4 Gwei to be safe
        gas_price = max(self.w3.eth.gas_price, 4_000_000_000)
        tx = fn.build_transaction({  # type: ignore[arg-type]
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "gas": int(gas * 1.3),  # 30% buffer
            "gasPrice": gas_price,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        return receipt["transactionHash"].hex()

    def get_latest_root(self, agent_address: str) -> Optional[MemoryState]:
        try:
            state = self.registry.functions.getLatest(
                Web3.to_checksum_address(agent_address)
            ).call()
            return MemoryState(
                merkle_root=state[0].hex(),
                block_number=state[1],
                da_tx_hash=state[2].hex(),
                timestamp=state[3],
            )
        except Exception:
            return None

    def get_historical_root(self, agent_address: str, index: int) -> Optional[MemoryState]:
        """Get a historical memory state by index (0 = first ever, -1 = latest)."""
        try:
            if index < 0:
                length = self.registry.functions.historyLength(
                    Web3.to_checksum_address(agent_address)
                ).call()
                index = length + index

            state = self.registry.functions.getAt(
                Web3.to_checksum_address(agent_address),
                index,
            ).call()
            return MemoryState(
                merkle_root=state[0].hex(),
                block_number=state[1],
                da_tx_hash=state[2].hex(),
                timestamp=state[3],
            )
        except Exception:
            return None

    def get_all_roots(self, agent_address: str) -> list[MemoryState]:
        """Get the full history of Merkle root anchors for an agent."""
        try:
            length = self.registry.functions.historyLength(
                Web3.to_checksum_address(agent_address)
            ).call()
            states = []
            for i in range(length):
                state = self.get_historical_root(agent_address, i)
                if state:
                    states.append(state)
            return states
        except Exception:
            return []

    def mint_memory_nft(self) -> str:
        """Mint the caller's memory NFT. Returns chain_tx_hash."""
        self._require_nft()
        assert self.nft is not None
        fn = self.nft.functions.mint()
        gas = fn.estimate_gas({"from": self.account.address})
        tx = fn.build_transaction({  # type: ignore[arg-type]
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "gas": int(gas * 1.3),
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt["transactionHash"].hex()

    def grant_access(self, agent_address: str, shard_blob_ids: list[str] | None = None) -> str:
        """Grant agent access on-chain. Pass shard_blob_ids for scoped access. Returns chain_tx_hash."""
        self._require_nft()
        assert self.nft is not None
        shard_bytes = []
        if shard_blob_ids:
            shard_bytes = [
                bytes.fromhex(bid.removeprefix("0x").zfill(64))
                for bid in shard_blob_ids
            ]
        grant_fn = self.nft.functions.grantAccess(
            Web3.to_checksum_address(agent_address),
            shard_bytes,
        )
        gas = grant_fn.estimate_gas({"from": self.account.address})
        tx = grant_fn.build_transaction({  # type: ignore[arg-type]
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "gas": int(gas * 1.3),
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt["transactionHash"].hex()

    def revoke_access(self, agent_address: str) -> str:
        """Revoke all on-chain access for an agent. Returns chain_tx_hash."""
        self._require_nft()
        assert self.nft is not None
        revoke_fn = self.nft.functions.revokeAccess(
            Web3.to_checksum_address(agent_address),
        )
        gas = revoke_fn.estimate_gas({"from": self.account.address})
        tx = revoke_fn.build_transaction({  # type: ignore[arg-type]
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "gas": int(gas * 1.3),
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt["transactionHash"].hex()

    def check_access(self, owner_address: str, agent_address: str, blob_id: str) -> bool:
        """Return True if agent_address has on-chain access to blob_id."""
        self._require_nft()
        assert self.nft is not None
        blob_bytes = bytes.fromhex(blob_id.removeprefix("0x").zfill(64))
        try:
            return self.nft.functions.hasAccess(
                Web3.to_checksum_address(owner_address),
                Web3.to_checksum_address(agent_address),
                blob_bytes,
            ).call()
        except Exception:
            return False

    def get_memory_token_id(self, owner_address: str) -> int:
        """Get the memory NFT token ID for a wallet (0 if not minted)."""
        self._require_nft()
        assert self.nft is not None
        try:
            return self.nft.functions.getTokenId(
                Web3.to_checksum_address(owner_address)
            ).call()
        except Exception:
            return 0

    def _require_nft(self) -> None:
        if self.nft is None:
            raise RuntimeError(
                "MemoryNFT contract address not provided. "
                "Pass nft_contract_address= when creating ChainClient."
            )

    @property
    def agent_address(self) -> str:
        return self.account.address
