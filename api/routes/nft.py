"""MemoryNFT endpoints — mint, ownership."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from api.dependencies import get_memory
from api.models import MintResponse

router = APIRouter(prefix="/nft", tags=["nft"])


@router.post("/mint", response_model=MintResponse)
def mint_nft(
    x_wallet_address: Optional[str] = Header(default=None),
    x_signature: Optional[str] = Header(default=None),
    x_auth_message: Optional[str] = Header(default=None),
):
    """Mint the caller's memory NFT on 0G Chain. One per wallet."""
    if not x_wallet_address:
        raise HTTPException(status_code=401, detail="X-Wallet-Address header is required.")
    if not x_signature:
        raise HTTPException(status_code=401, detail="X-Signature header is required.")
    if not x_auth_message:
        raise HTTPException(status_code=401, detail="X-Auth-Message header is required.")

    memory = get_memory(x_wallet_address, x_signature, x_auth_message)
    try:
        tx = memory.mint_memory_nft()
        token_id = memory.memory_token_id()
        return MintResponse(
            chain_tx_hash=tx,
            token_id=token_id,
            owner=memory._chain.agent_address,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
