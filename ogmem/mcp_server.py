"""
0G Mem MCP Server

Exposes VerifiableMemory as a Model Context Protocol server over stdio.
Any MCP-compatible host (Claude Desktop, Cursor, Zed, Continue, Cline)
can spawn this process and use it as a memory tool.

Usage:
    python -m ogmem.mcp_server

Required env vars:
    AGENT_KEY   — wallet private key (derives encryption key)

Optional env vars:
    AGENT_ID    — logical agent name (default: wallet address)
    NETWORK     — 0g-testnet | custom (default: 0g-testnet)
    OPENAI_API_KEY — for LLM-assisted summary/distill (optional)
"""

import asyncio
import json
import os
import sys
from functools import partial
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "MCP SDK not installed. Run: pip install 'ogmem[mcp]'",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from .memory import VerifiableMemory
    from .proof import QueryProof
except ImportError:
    # mcp dev runs the file directly without package context — add repo root to path
    import pathlib as _pathlib
    sys.path.insert(0, str(_pathlib.Path(__file__).parent.parent))
    from ogmem.memory import VerifiableMemory  # type: ignore[no-redef]
    from ogmem.proof import QueryProof  # type: ignore[no-redef]

# ── Bootstrap ─────────────────────────────────────────────────────────────────

_AGENT_KEY = os.environ.get("AGENT_KEY", "")
_AGENT_ID = os.environ.get("AGENT_ID", "")
_NETWORK = os.environ.get("NETWORK", "0g-testnet")
_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

if not _AGENT_KEY:
    print(
        "Error: AGENT_KEY environment variable is required.",
        file=sys.stderr,
    )
    sys.exit(1)

# Derive wallet address from key so agent_id matches the Telegram bot
# (which also uses wallet address). Override with AGENT_ID if explicitly set.
if not _AGENT_ID:
    try:
        from eth_account import Account
        _AGENT_ID = Account.from_key(_AGENT_KEY).address
    except Exception:
        _AGENT_ID = "mcp-agent"

memory = VerifiableMemory(
    agent_id=_AGENT_ID,
    private_key=_AGENT_KEY,
    network=_NETWORK,
    openai_api_key=_OPENAI_KEY,
)

# ── MCP server ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="0g-mem",
    instructions=(
        "You have access to a verifiable, encrypted, on-chain memory store powered by 0G Labs. "
        "Use memory_add to persist important information. "
        "Use memory_query to recall relevant memories before answering questions. "
        "Every write is encrypted client-side and anchored with a Merkle proof on 0G Chain. "
        "The memory persists across sessions and is portable across all tools that share the same AGENT_KEY."
    ),
)

# ── Async helper ──────────────────────────────────────────────────────────────

async def _run_sync(fn, *args, **kwargs):
    """Run a synchronous SDK call in a thread pool so we don't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, *args, **kwargs))


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
async def memory_add(text: str, memory_type: str = "episodic") -> dict:
    """
    Store a memory entry on 0G decentralised storage.

    The entry is encrypted client-side with AES-256-GCM before upload.
    A SHA-256 Merkle root is anchored on 0G Chain and the write commitment
    is posted to 0G DA. Returns a receipt with verifiable hashes.

    Args:
        text: The memory content to store.
        memory_type: One of episodic / semantic / procedural / working.
    """
    receipt = await _run_sync(memory.add, text, memory_type)
    return {
        "blob_id": receipt.blob_id,
        "merkle_root": receipt.merkle_root if isinstance(receipt.merkle_root, str) else receipt.merkle_root.hex() if receipt.merkle_root else "",
        "da_tx_hash": receipt.da_tx_hash,
        "chain_tx_hash": receipt.chain_tx_hash,
        "memory_type": receipt.memory_type,
        "timestamp": receipt.timestamp,
    }


@mcp.tool()
async def memory_query(query: str, top_k: int = 5) -> dict:
    """
    Search memory using semantic similarity and return matching entries with proof.

    Embeds the query locally, computes cosine similarity over cached embeddings,
    fetches and decrypts matched blobs from 0G Storage, and returns results with
    a full Merkle inclusion proof for each blob.

    Args:
        query: Natural language search query.
        top_k: Maximum number of results to return (1–20).
    """
    top_k = max(1, min(20, top_k))
    results, proof = await _run_sync(memory.query, query, top_k)
    return {
        "results": results,
        "count": len(results),
        "proof": {
            "agent_id": proof.agent_id,
            "query_hash": proof.query_hash,
            "blob_ids": proof.blob_ids,
            "scores": proof.scores,
            "merkle_root": proof.merkle_root if isinstance(proof.merkle_root, str) else proof.merkle_root.hex() if proof.merkle_root else "",
            "da_read_tx": proof.da_read_tx,
            "chain_block": proof.chain_block,
            "timestamp": proof.timestamp,
        },
    }


@mcp.tool()
async def memory_stats() -> dict:
    """
    Return a summary of the current memory state without fetching any blobs.

    Reads the local index and on-chain state. Fast — no network calls to 0G Storage.
    """
    stats = await _run_sync(memory.stats)
    chain_state = await _run_sync(memory._chain.get_latest_root, memory._chain.agent_address)
    return {
        "total_entries": stats["total"],
        "by_type": stats["by_type"],
        "stale_count": stats["stale"],
        "top_retrieved": stats["top_retrieved"],
        "conflicts_detected": len(stats.get("conflicts", [])),
        "merkle_root": chain_state.merkle_root if chain_state else "",
        "last_chain_block": chain_state.block_number if chain_state else 0,
        "last_updated": chain_state.timestamp if chain_state else 0,
        "agent_id": memory.agent_id,
    }


@mcp.tool()
async def memory_summary() -> str:
    """
    Generate a plain-English portrait of all stored memories.

    If OPENAI_API_KEY is set, uses an LLM to produce a narrative summary.
    Otherwise falls back to structured text grouping memories by type.
    Useful as a context-loading tool at the start of a conversation.
    """
    summary_fn = None
    if _OPENAI_KEY:
        try:
            from openai import OpenAI  # type: ignore[import]
            client = OpenAI(api_key=_OPENAI_KEY)

            def _llm(prompt: str) -> str:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                )
                return resp.choices[0].message.content or ""

            summary_fn = _llm
        except Exception:
            pass

    return await _run_sync(memory.summary, summary_fn)


@mcp.tool()
async def memory_distill(older_than_days: int = 7, keep_originals: bool = True) -> dict:
    """
    Compress old episodic memories into a single semantic entry.

    Finds episodic entries older than older_than_days, writes a distilled
    semantic summary, and optionally removes the originals from the index.
    The new entry is anchored on-chain.

    Args:
        older_than_days: Only compress entries older than this many days.
        keep_originals: If False, remove the source episodic entries after distilling.
    """
    distill_fn = None
    if _OPENAI_KEY:
        try:
            from openai import OpenAI  # type: ignore[import]
            _dc = OpenAI(api_key=_OPENAI_KEY)

            def _distill_llm(prompt: str) -> str:
                resp = _dc.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                )
                return resp.choices[0].message.content or ""

            distill_fn = _distill_llm
        except Exception:
            pass

    report = await _run_sync(
        memory.distill,
        older_than_days,
        keep_originals,
        distill_fn,
    )
    return {
        "source_entries_compressed": report.source_count,
        "semantic_entries_created": report.target_count,
        "originals_deleted": report.deleted,
        "message": (
            f"Distilled {report.source_count} episodic memories into {report.target_count} semantic entry."
            if report.source_count > 0
            else "No episodic entries old enough to distill yet."
        ),
    }


@mcp.tool()
async def memory_evolve() -> dict:
    """
    Run a memory reweighting pass (RL-inspired evolution).

    - Frequently retrieved memories get their weight boosted.
    - Memories not retrieved for 45+ days get flagged as stale.
    - The post-evolution state is anchored on-chain.

    Returns a summary of what changed.
    """
    report = await _run_sync(memory.evolve)
    return {
        "total_memories": report.total,
        "strengthened": report.strengthened,
        "newly_stale": report.decayed,
        "already_stale": report.already_stale,
        "summary": report.summary(),
    }


@mcp.tool()
async def memory_delete(blob_id: str) -> dict:
    """
    Remove a memory entry from the local index by its blob_id.

    Note: The encrypted blob remains on 0G Storage (immutable) and the
    Merkle root history on 0G Chain is preserved. This only removes the
    entry from local retrieval — the on-chain audit trail is intact.

    Args:
        blob_id: The blob_id returned when the memory was added.
    """
    removed = await _run_sync(memory.delete_memory, blob_id)
    return {
        "success": removed,
        "blob_id": blob_id,
        "message": (
            f"Removed {blob_id} from local index. On-chain history is preserved."
            if removed
            else f"No entry found with blob_id {blob_id}."
        ),
    }


@mcp.tool()
async def memory_verify(proof_json: str) -> dict:
    """
    Verify a QueryProof — confirm retrieval integrity on 0G Chain.

    Accepts the JSON string of a QueryProof object (as returned by memory_query).
    Verifies each Merkle inclusion proof and confirms the root matches the
    on-chain anchor at the given block number.

    Args:
        proof_json: JSON string of a QueryProof object.
    """
    try:
        proof_dict = json.loads(proof_json)
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"Invalid JSON: {e}"}

    try:
        proof = QueryProof(
            agent_id=proof_dict.get("agent_id", ""),
            query_hash=proof_dict.get("query_hash", ""),
            blob_ids=proof_dict.get("blob_ids", []),
            scores=proof_dict.get("scores", []),
            merkle_proofs=proof_dict.get("merkle_proofs", []),
            merkle_root=proof_dict.get("merkle_root", ""),
            da_read_tx=proof_dict.get("da_read_tx", ""),
            chain_block=proof_dict.get("chain_block", 0),
            timestamp=proof_dict.get("timestamp", 0),
        )
    except Exception as e:
        return {"valid": False, "error": f"Invalid proof structure: {e}"}

    valid = await _run_sync(memory.verify_proof, proof)
    return {
        "valid": valid,
        "agent_id": proof.agent_id,
        "chain_block": proof.chain_block,
        "merkle_root": proof.merkle_root if isinstance(proof.merkle_root, str) else proof.merkle_root.hex() if proof.merkle_root else "",
        "blob_count": len(proof.blob_ids),
        "message": "Proof verified on-chain." if valid else "Proof verification failed.",
    }


@mcp.tool()
async def memory_sync() -> dict:
    """
    Rebuild the local memory index from the DA history file.

    Reads all memory_write commitments logged by the DA client on this machine,
    fetches any blobs not already in the local index, and merges them in.
    Useful when the same wallet has written memories from another process on
    the same machine (e.g. MCP server starting after the Telegram bot wrote
    memories on the same host).

    For cross-machine sync (e.g. Railway → local), use memory_pull_index instead.
    """
    report = await _run_sync(memory.sync)
    return {
        "added": report.added,
        "skipped": report.skipped,
        "failed": report.failed,
        "message": report.message or f"Sync complete: +{report.added} new, {report.skipped} already present, {report.failed} failed.",
    }


@mcp.tool()
async def memory_push_index() -> dict:
    """
    Upload a snapshot of the full memory index to 0G Storage and anchor it on-chain.

    After pushing, any other machine or process running with the same AGENT_KEY
    can call memory_pull_index() to discover and download this snapshot.
    Use this on the machine that has the most up-to-date memory (e.g. the
    Telegram bot on Railway) before switching to a new environment.

    Returns the index_blob_id — the content address of the uploaded snapshot.
    """
    index_blob_id = await _run_sync(memory.push_index)
    return {
        "success": True,
        "index_blob_id": index_blob_id,
        "entry_count": len(memory._entries),
        "message": f"Index snapshot pushed. blob_id: {index_blob_id[:16]}... ({len(memory._entries)} entries)",
    }


@mcp.tool()
async def memory_pull_index(index_blob_id: str = "") -> dict:
    """
    Download and merge a memory index snapshot from 0G Storage.

    If index_blob_id is provided, fetches that snapshot directly.
    Otherwise scans the on-chain history to find the latest snapshot
    uploaded by memory_push_index() — enabling cross-machine sync
    (e.g. Telegram bot on Railway → local MCP server).

    Call this on the machine that is out of date (e.g. the local MCP server)
    to catch up with memories written elsewhere.

    Args:
        index_blob_id: Specific snapshot blob_id to pull. Leave empty to
                       auto-discover the latest snapshot from on-chain history.
    """
    report = await _run_sync(memory.pull_index, index_blob_id or None)
    return {
        "added": report.added,
        "skipped": report.skipped,
        "failed": report.failed,
        "message": report.message or f"Pull complete: +{report.added} new, {report.skipped} already present.",
    }


@mcp.tool()
async def memory_grant_access(agent_address: str, shard_blob_ids: Optional[list] = None) -> dict:
    """
    Grant another agent on-chain access to this memory store.

    Calls MemoryNFT.grantAccess on 0G Chain. If shard_blob_ids is provided,
    grants access only to those specific blobs (shard-level access).
    If empty, grants full access to all memories.

    Args:
        agent_address: Wallet address of the agent to grant access to.
        shard_blob_ids: Optional list of blob_ids for shard-level access.
                        Leave empty for full access.
    """
    tx_hash = await _run_sync(
        memory.grant_access,
        agent_address,
        shard_blob_ids or None,
    )
    access_type = "shard-level" if shard_blob_ids else "full"
    return {
        "success": True,
        "agent_address": agent_address,
        "access_type": access_type,
        "chain_tx_hash": tx_hash,
        "message": f"Granted {access_type} access to {agent_address}. Tx: {tx_hash}",
    }


@mcp.tool()
async def memory_revoke_access(agent_address: str) -> dict:
    """
    Revoke all on-chain access grants for an agent.

    Calls MemoryNFT.revokeAccess on 0G Chain. Clears all grants immediately —
    the agent will no longer be able to read any memories.

    Args:
        agent_address: Wallet address of the agent to revoke.
    """
    tx_hash = await _run_sync(memory.revoke_access, agent_address)
    return {
        "success": True,
        "agent_address": agent_address,
        "chain_tx_hash": tx_hash,
        "message": f"Revoked all access for {agent_address}. Tx: {tx_hash}",
    }


# ── Resources ─────────────────────────────────────────────────────────────────


@mcp.resource("memory://stats")
async def resource_stats() -> str:
    """Current on-chain memory state snapshot."""
    stats = await _run_sync(memory.stats)
    chain_state = await _run_sync(memory._chain.get_latest_root, memory._chain.agent_address)
    data = {
        "agent_id": memory.agent_id,
        "total_entries": stats["total"],
        "by_type": stats["by_type"],
        "stale": stats["stale"],
        "merkle_root": chain_state.merkle_root if chain_state else "",
        "last_chain_block": chain_state.block_number if chain_state else 0,
    }
    return json.dumps(data, indent=2)


@mcp.resource("memory://entries")
async def resource_entries() -> str:
    """
    Full list of memory entries (text + metadata).

    Warning: Fetches and decrypts all blobs — may be slow for large stores.
    Use memory_query for targeted retrieval.
    """
    entries = [
        {
            "blob_id": e["blob_id"],
            "text": e["text"],
            "memory_type": e.get("memory_type", "episodic"),
            "timestamp": e.get("timestamp", 0),
            "retrieval_count": e.get("retrieval_count", 0),
            "weight": e.get("weight", 1.0),
            "stale": e.get("stale", False),
        }
        for e in memory._entries
    ]
    return json.dumps(entries, indent=2)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
