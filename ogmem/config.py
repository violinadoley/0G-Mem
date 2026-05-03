"""Network configuration for 0G Mem SDK."""

from dataclasses import dataclass


@dataclass
class NetworkConfig:
    # 0G Chain (EVM)
    chain_id: int
    rpc_url: str
    explorer_url: str

    # 0G Storage
    storage_indexer_rpc: str
    flow_contract_address: str

    # 0G DA
    da_disperser_rpc: str  # gRPC endpoint

    # 0G Serving (inference)
    serving_broker_url: str

    # Deployed contracts
    memory_registry_address: str = ""
    memory_nft_address: str = ""


NETWORKS = {
    # 0G Galileo Testnet (v3) — current active testnet
    "0g-testnet": NetworkConfig(
        chain_id=16602,
        rpc_url="https://evmrpc-testnet.0g.ai",
        explorer_url="https://chainscan-galileo.0g.ai",
        # Storage indexer — discovers nodes and handles file upload/download REST API
        storage_indexer_rpc="https://indexer-storage-testnet-turbo.0g.ai",
        # Flow contract — on-chain file submission registry (updated for Galileo)
        flow_contract_address="0x22E03a6A89B950F1c82ec5e74F8eCa321a105296",
        # DA: run local DA client via Docker (see docker-compose.yml), then set to "localhost:51001"
        da_disperser_rpc="localhost:51001",
        serving_broker_url="https://broker-testnet.0g.ai",
        memory_registry_address="0xEDF95D9CFb157F5F38C1125B7DFB3968E05d2c4b",
        memory_nft_address="0x70ad85300f522A41689954a4153744BF6E57E488",
    ),
    # 0G Newton Testnet (v2) — kept for reference
    "0g-newton": NetworkConfig(
        chain_id=16600,
        rpc_url="https://evmrpc-testnet.0g.ai",
        explorer_url="https://chainscan-newton.0g.ai",
        storage_indexer_rpc="https://rpc-storage-testnet.0g.ai",
        flow_contract_address="0xbD2C3F0E65eDF5582141C35969d66e34629cC768",
        da_disperser_rpc="disperser-dev.0g.ai:443",
        serving_broker_url="https://broker-testnet.0g.ai",
    ),
}

# MemoryNFT contract ABI — ERC-7857 inspired, deployed on 0G Chain
MEMORY_NFT_ABI = [
    {
        "inputs": [],
        "name": "mint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "bytes32[]", "name": "shardIds", "type": "bytes32[]"},
        ],
        "name": "grantAccess",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "agent", "type": "address"}],
        "name": "revokeAccess",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "bytes32", "name": "blobId", "type": "bytes32"},
        ],
        "name": "hasAccess",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "agent", "type": "address"},
        ],
        "name": "hasFullAccess",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "getTokenId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "ownerToToken",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
        ],
        "name": "MemoryMinted",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "agent", "type": "address"},
            {"indexed": False, "internalType": "bytes32[]", "name": "shardIds", "type": "bytes32[]"},
        ],
        "name": "AccessGranted",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "agent", "type": "address"},
        ],
        "name": "AccessRevoked",
        "type": "event",
    },
]

MEMORY_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
            {"internalType": "bytes32", "name": "daTxHash", "type": "bytes32"},
        ],
        "name": "updateRoot",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "agent", "type": "address"}],
        "name": "getLatest",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
                    {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
                    {"internalType": "bytes32", "name": "daTxHash", "type": "bytes32"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                ],
                "internalType": "struct MemoryRegistry.MemoryState",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "uint256", "name": "index", "type": "uint256"},
        ],
        "name": "getAt",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
                    {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
                    {"internalType": "bytes32", "name": "daTxHash", "type": "bytes32"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                ],
                "internalType": "struct MemoryRegistry.MemoryState",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "agent", "type": "address"}],
        "name": "historyLength",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "agent", "type": "address"},
            {"indexed": False, "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
            {"indexed": False, "internalType": "bytes32", "name": "daTxHash", "type": "bytes32"},
        ],
        "name": "MemoryUpdated",
        "type": "event",
    },
]
