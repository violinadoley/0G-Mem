// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MemoryNFT
 * @notice ERC-7857 inspired NFT representing a user's verifiable memory collection.
 *
 * One NFT per user = one portable memory identity. Memory is a wallet-owned asset,
 * not a platform account.
 *
 * Ownership model:
 *   - User mints ONE token — their "memory passport"
 *   - Token ID is tied to the owner's wallet address
 *   - Transferring the NFT transfers all memory ownership
 *
 * Access control (memory shards):
 *   - Owner grants any agent FULL access or access to specific blob IDs (shards)
 *   - Grants are revocable on-chain at any time
 *   - Any app can verify agent access without trusting 0G Mem
 *
 * Compatible with ERC-7857 (Intelligent Asset NFT) concept.
 *
 * Deployed on: 0G Chain (EVM-compatible, Chain ID: 16601)
 */
contract MemoryNFT {

    // ─── ERC-721 minimal implementation ────────────────────────────────────

    string public name = "0G Mem";
    string public symbol = "ZGMEM";

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;

    uint256 private _totalSupply;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);

    function ownerOf(uint256 tokenId) public view returns (address) {
        address owner = _owners[tokenId];
        require(owner != address(0), "MemoryNFT: token does not exist");
        return owner;
    }

    function balanceOf(address owner) public view returns (uint256) {
        require(owner != address(0), "MemoryNFT: zero address");
        return _balances[owner];
    }

    function totalSupply() public view returns (uint256) {
        return _totalSupply;
    }

    function transferFrom(address from, address to, uint256 tokenId) public {
        require(ownerOf(tokenId) == from, "MemoryNFT: wrong owner");
        require(
            msg.sender == from || msg.sender == _tokenApprovals[tokenId],
            "MemoryNFT: not authorized"
        );
        require(to != address(0), "MemoryNFT: zero address");

        // Transfer clears all access grants — new owner starts fresh
        _clearAllGrants(tokenId);

        _balances[from]--;
        _balances[to]++;
        _owners[tokenId] = to;

        // Update ownerToToken mapping
        delete ownerToToken[from];
        ownerToToken[to] = tokenId;

        delete _tokenApprovals[tokenId];
        emit Transfer(from, to, tokenId);
    }

    function approve(address to, uint256 tokenId) public {
        require(ownerOf(tokenId) == msg.sender, "MemoryNFT: not owner");
        _tokenApprovals[tokenId] = to;
        emit Approval(msg.sender, to, tokenId);
    }

    // ─── Memory NFT logic ──────────────────────────────────────────────────

    /// @notice One token per wallet address
    mapping(address => uint256) public ownerToToken;

    /// @notice Full memory access grants: tokenId → agent → granted
    mapping(uint256 => mapping(address => bool)) public agentFullAccess;

    /// @notice Shard-level access grants: tokenId → agent → blobId → granted
    mapping(uint256 => mapping(address => mapping(bytes32 => bool))) public shardAccess;

    /// @notice Track blob IDs granted per agent (needed to clear on revoke)
    mapping(uint256 => mapping(address => bytes32[])) private _agentShards;

    /// @notice Track all agents ever granted (for revoke-all / enumeration)
    mapping(uint256 => address[]) private _grantedAgents;

    event MemoryMinted(uint256 indexed tokenId, address indexed owner);
    event AccessGranted(
        uint256 indexed tokenId,
        address indexed owner,
        address indexed agent,
        bytes32[] shardIds   // empty = full access
    );
    event AccessRevoked(uint256 indexed tokenId, address indexed owner, address indexed agent);

    /**
     * @notice Mint your memory NFT. One per wallet, forever.
     * @return tokenId The minted token ID.
     */
    function mint() external returns (uint256) {
        require(ownerToToken[msg.sender] == 0, "MemoryNFT: already minted");

        _totalSupply++;
        uint256 tokenId = _totalSupply;

        _owners[tokenId] = msg.sender;
        _balances[msg.sender]++;
        ownerToToken[msg.sender] = tokenId;

        emit Transfer(address(0), msg.sender, tokenId);
        emit MemoryMinted(tokenId, msg.sender);

        return tokenId;
    }

    /**
     * @notice Grant an agent access to your memory.
     *
     * @param agent    The agent's wallet address.
     * @param shardIds Specific blob IDs to grant. Pass empty array for full access.
     *
     * Full access: agent can read any of your memory blobs.
     * Shard access: agent can only read the specific blob IDs listed.
     */
    function grantAccess(address agent, bytes32[] calldata shardIds) external {
        uint256 tokenId = ownerToToken[msg.sender];
        require(tokenId != 0, "MemoryNFT: mint your memory NFT first");
        require(_owners[tokenId] == msg.sender, "MemoryNFT: not owner");
        require(agent != address(0), "MemoryNFT: zero agent address");

        if (shardIds.length == 0) {
            agentFullAccess[tokenId][agent] = true;
        } else {
            for (uint256 i = 0; i < shardIds.length; i++) {
                shardAccess[tokenId][agent][shardIds[i]] = true;
                _agentShards[tokenId][agent].push(shardIds[i]);
            }
        }

        _grantedAgents[tokenId].push(agent);
        emit AccessGranted(tokenId, msg.sender, agent, shardIds);
    }

    /**
     * @notice Revoke ALL access for an agent (full + all shards).
     * @param agent The agent's wallet address.
     */
    function revokeAccess(address agent) external {
        uint256 tokenId = ownerToToken[msg.sender];
        require(tokenId != 0, "MemoryNFT: no memory NFT");
        require(_owners[tokenId] == msg.sender, "MemoryNFT: not owner");

        // Clear full access
        agentFullAccess[tokenId][agent] = false;

        // Clear all shard-level access grants for this agent
        bytes32[] storage shards = _agentShards[tokenId][agent];
        for (uint256 i = 0; i < shards.length; i++) {
            shardAccess[tokenId][agent][shards[i]] = false;
        }
        delete _agentShards[tokenId][agent];

        emit AccessRevoked(tokenId, msg.sender, agent);
    }

    /**
     * @notice Check if an agent has access to a specific memory blob.
     *
     * Returns true if:
     *   - Agent has full access, OR
     *   - Agent has shard-level access to this specific blobId
     *
     * @param owner  The memory owner's wallet address.
     * @param agent  The agent being checked.
     * @param blobId The 0G Storage blob ID (content hash) to check.
     */
    function hasAccess(
        address owner,
        address agent,
        bytes32 blobId
    ) external view returns (bool) {
        uint256 tokenId = ownerToToken[owner];
        if (tokenId == 0) return false;
        if (_owners[tokenId] != owner) return false;  // NFT was transferred

        return agentFullAccess[tokenId][agent] || shardAccess[tokenId][agent][blobId];
    }

    /**
     * @notice Check if an agent has full (unrestricted) access.
     */
    function hasFullAccess(address owner, address agent) external view returns (bool) {
        uint256 tokenId = ownerToToken[owner];
        if (tokenId == 0) return false;
        if (_owners[tokenId] != owner) return false;
        return agentFullAccess[tokenId][agent];
    }

    /**
     * @notice Get the token ID for a wallet address (0 if not minted).
     */
    function getTokenId(address owner) external view returns (uint256) {
        return ownerToToken[owner];
    }

    /**
     * @notice Number of agents ever granted access for a token.
     * Note: includes revoked agents (use hasAccess to check current status).
     */
    function grantedAgentCount(uint256 tokenId) external view returns (uint256) {
        return _grantedAgents[tokenId].length;
    }

    // ─── Internal ──────────────────────────────────────────────────────────

    function _clearAllGrants(uint256 tokenId) internal {
        address[] storage agents = _grantedAgents[tokenId];
        for (uint256 i = 0; i < agents.length; i++) {
            address agent = agents[i];
            agentFullAccess[tokenId][agent] = false;

            // Clear all shard-level grants for this agent
            bytes32[] storage shards = _agentShards[tokenId][agent];
            for (uint256 j = 0; j < shards.length; j++) {
                shardAccess[tokenId][agent][shards[j]] = false;
            }
            delete _agentShards[tokenId][agent];
        }
        delete _grantedAgents[tokenId];
    }
}
