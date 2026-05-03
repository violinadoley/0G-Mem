"""Memory read/write/audit/verify endpoints."""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from api.dependencies import get_memory
from api.models import (
    AddRequest, AddResponse,
    QueryRequest, QueryResponse,
    StateResponse,
    VerifyRequest, VerifyResponse,
    GrantRequest, GrantResponse,
    RevokeRequest, RevokeResponse,
)
from ogmem.proof import QueryProof

router = APIRouter(prefix="/memory", tags=["memory"])


def _auth(
    x_wallet_address: Optional[str],
    x_signature: Optional[str],
    x_auth_message: Optional[str],
):
    """Validate that all three auth headers are present and return the memory instance."""
    if not x_wallet_address:
        raise HTTPException(status_code=401, detail="X-Wallet-Address header is required.")
    if not x_signature:
        raise HTTPException(status_code=401, detail="X-Signature header is required.")
    if not x_auth_message:
        raise HTTPException(status_code=401, detail="X-Auth-Message header is required.")
    return get_memory(x_wallet_address, x_signature, x_auth_message)


@router.post("/{agent_id}/add", response_model=AddResponse)
def add_memory(
    agent_id: str,
    body: AddRequest,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Write a memory entry to 0G Storage and anchor its Merkle root on-chain."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        receipt = memory.add(body.text, memory_type=body.memory_type, metadata=body.metadata)
        return AddResponse(
            agent_id=receipt.agent_id,
            blob_id=receipt.blob_id,
            merkle_root=receipt.merkle_root,
            da_tx_hash=receipt.da_tx_hash,
            chain_tx_hash=receipt.chain_tx_hash,
            memory_type=receipt.memory_type,
            timestamp=receipt.timestamp,
            encrypted=memory._encrypted,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/query", response_model=QueryResponse)
def query_memory(
    agent_id: str,
    body: QueryRequest,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Semantic similarity search. Returns top-k results and a cryptographic proof."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        results, proof = memory.query(body.text, top_k=body.top_k, memory_types=body.memory_types)
        return QueryResponse(results=results, proof=proof.__dict__)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/state", response_model=StateResponse)
def get_state(
    agent_id: str,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Current Merkle root + chain state for an agent."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        chain_state = memory._chain.get_latest_root(memory._chain.agent_address)
        token_id = memory.memory_token_id()
        return StateResponse(
            agent_id=agent_id,
            merkle_root=chain_state.merkle_root if chain_state else "",
            block_number=chain_state.block_number if chain_state else 0,
            da_tx_hash=chain_state.da_tx_hash if chain_state else "",
            timestamp=chain_state.timestamp if chain_state else 0,
            memory_count=len(memory._entries),
            nft_token_id=token_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/audit")
def get_audit(
    agent_id: str,
    from_block: int = 0,
    to_block: int = -1,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Full EU AI Act Article 12 compliant audit report (JSON)."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        report = memory.export_audit(from_block=from_block, to_block=to_block)
        return json.loads(report.to_json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/verify", response_model=VerifyResponse)
def verify_proof(
    agent_id: str,
    body: VerifyRequest,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """
    Verify a QueryProof. Stateless — callable by any third party.
    Auth headers are optional for verify; a public agent_id path param suffices
    to look up the chain state. We still accept auth headers for consistency.
    """
    # For verify we allow unauthenticated access — proof verification is public.
    # If auth headers are present we validate them; otherwise we use a read-only
    # instantiation via AGENT_KEY with the provided agent_id.
    if x_wallet_address and x_signature and x_auth_message:
        memory = _auth(x_wallet_address, x_signature, x_auth_message)
    else:
        import os
        from ogmem.memory import VerifiableMemory
        from ogmem.config import NETWORKS
        agent_key = os.environ.get("AGENT_KEY")
        if not agent_key:
            raise HTTPException(status_code=500, detail="AGENT_KEY not configured.")
        net = NETWORKS["0g-testnet"]
        memory = VerifiableMemory(
            agent_id=agent_id,
            private_key=agent_key,
            network="0g-testnet",
            registry_contract_address=os.environ.get(
                "MEMORY_REGISTRY_ADDRESS", net.memory_registry_address
            ),
            nft_contract_address=os.environ.get(
                "MEMORY_NFT_ADDRESS", net.memory_nft_address
            ),
            encrypted=True,
        )
    try:
        proof = QueryProof(**body.proof)
        valid = memory.verify_proof(proof)
        return VerifyResponse(
            valid=valid,
            message="Proof is valid — retrieval verified on 0G Chain." if valid
                    else "Proof is invalid — data may have been tampered with.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid proof format: {e}")


@router.post("/{agent_id}/grant", response_model=GrantResponse)
def grant_access(
    agent_id: str,
    body: GrantRequest,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Grant an agent full or shard-level access to memory (on-chain)."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        tx = memory.grant_access(
            body.agent_address,
            shard_blob_ids=body.shard_blob_ids or None,
        )
        return GrantResponse(
            chain_tx_hash=tx,
            agent_address=body.agent_address,
            access_type="shard" if body.shard_blob_ids else "full",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/revoke", response_model=RevokeResponse)
def revoke_access(
    agent_id: str,
    body: RevokeRequest,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Revoke all access for an agent — effective immediately on-chain."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        tx = memory.revoke_access(body.agent_address)
        return RevokeResponse(chain_tx_hash=tx, agent_address=body.agent_address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/stats")
def get_stats(
    agent_id: str,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Memory stats — total count, breakdown by type, stale count, top retrieved."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        return memory.stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/evolve")
def evolve_memory(
    agent_id: str,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """
    Run RL-inspired memory reweighting: strengthen frequently used memories,
    flag stale ones. Anchors post-evolution state on-chain.
    """
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        report = memory.evolve()
        return {
            "strengthened": report.strengthened,
            "decayed": report.decayed,
            "already_stale": report.already_stale,
            "total": report.total,
            "summary": report.summary(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/distill")
def distill_memory(
    agent_id: str,
    older_than_days: int = 30,
    keep_originals: bool = True,
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Compress old episodic memories into semantic facts."""
    memory = _auth(x_wallet_address, x_signature, x_auth_message)
    try:
        report = memory.distill(older_than_days=older_than_days, keep_originals=keep_originals)
        return {
            "source_count": report.source_count,
            "target_count": report.target_count,
            "deleted": report.deleted,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
