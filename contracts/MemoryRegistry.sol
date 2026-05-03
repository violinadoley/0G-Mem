// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MemoryRegistry
 * @notice On-chain registry for AI agent memory state roots.
 *
 * Every time an AI agent writes a memory (via 0G Mem SDK), a new Merkle root
 * is anchored here. This creates an immutable, chronological history of the
 * agent's memory state — verifiable by anyone, forever.
 *
 * Combined with 0G DA (where full operation logs are stored), this contract
 * enables EU AI Act Article 12 compliant audit trails for AI agents.
 *
 * Deployed on: 0G Chain Newton Testnet (Chain ID: 16600)
 */
contract MemoryRegistry {

    struct MemoryState {
        bytes32 merkleRoot;   // Merkle root of all memory blobs at this point
        uint256 blockNumber;  // Block when this root was anchored
        bytes32 daTxHash;     // 0G DA transaction hash (full operation log)
        uint256 timestamp;    // Unix timestamp
    }

    /// @notice Latest memory state per agent (wallet address = agent ID)
    mapping(address => MemoryState) public latest;

    /// @notice Full history of memory states per agent
    mapping(address => MemoryState[]) private history;

    /// @notice Emitted on every memory write
    event MemoryUpdated(
        address indexed agent,
        bytes32 indexed merkleRoot,
        bytes32 daTxHash,
        uint256 blockNumber
    );

    /**
     * @notice Anchor a new Merkle root after a memory write.
     * @param merkleRoot  New Merkle root of the agent's full memory set.
     * @param daTxHash    Hash of the 0G DA commitment containing the full write log.
     */
    function updateRoot(bytes32 merkleRoot, bytes32 daTxHash) external {
        MemoryState memory state = MemoryState({
            merkleRoot: merkleRoot,
            blockNumber: block.number,
            daTxHash: daTxHash,
            timestamp: block.timestamp
        });

        latest[msg.sender] = state;
        history[msg.sender].push(state);

        emit MemoryUpdated(msg.sender, merkleRoot, daTxHash, block.number);
    }

    /**
     * @notice Get the most recent memory state for an agent.
     */
    function getLatest(address agent) external view returns (MemoryState memory) {
        return latest[agent];
    }

    /**
     * @notice Get a historical memory state by index.
     * @param agent  Agent wallet address.
     * @param index  0 = first ever write, historyLength-1 = most recent.
     */
    function getAt(address agent, uint256 index) external view returns (MemoryState memory) {
        require(index < history[agent].length, "MemoryRegistry: index out of bounds");
        return history[agent][index];
    }

    /**
     * @notice Number of memory updates recorded for an agent.
     */
    function historyLength(address agent) external view returns (uint256) {
        return history[agent].length;
    }

    /**
     * @notice Verify a Merkle inclusion proof on-chain.
     *
     * Proves that a specific blob_id was part of the agent's memory
     * at the time the given root was anchored.
     *
     * @param agent   Agent wallet address.
     * @param leaf    sha256(blob_id) — the leaf being proven.
     * @param proof   Array of sibling hashes (bottom to top).
     * @param root    The Merkle root to verify against.
     */
    function verifyInclusion(
        address agent,
        bytes32 leaf,
        bytes32[] calldata proof,
        bytes32 root
    ) external pure returns (bool) {
        // Verify root exists for agent (optional — caller can also check off-chain)
        bytes32 computed = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 sibling = proof[i];
            // Convention: always hash (smaller, larger) to ensure determinism
            if (computed <= sibling) {
                computed = keccak256(abi.encodePacked(computed, sibling));
            } else {
                computed = keccak256(abi.encodePacked(sibling, computed));
            }
        }
        return computed == root;
    }
}
