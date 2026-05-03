"""Shared dependencies — memory instance cache, signature-based auth."""

import os
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException

from ogmem.memory import VerifiableMemory
from ogmem.config import NETWORKS

_memory_instances: dict[str, VerifiableMemory] = {}


def verify_signature(wallet_address: str, signature: str, message: str) -> bool:
    """
    Verify that `signature` was produced by `wallet_address` signing `message`.
    Uses eth_account (available via web3.py / eth-account package).
    Returns True if valid, raises HTTPException(401) if not.
    """
    try:
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=signature)
        if recovered.lower() != wallet_address.lower():
            raise HTTPException(
                status_code=401,
                detail="Signature verification failed: signer does not match wallet address.",
            )
        return True
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Signature verification error: {exc}",
        )


def _build_expected_message(wallet_address: str) -> list[str]:
    """
    Return a list of acceptable message prefixes. We accept any message that
    starts with the standard prefix so that slight timestamp differences do not
    block legitimate requests — the signature itself is the proof of ownership.
    """
    return [
        f"0G Mem authentication | Wallet: {wallet_address}",
    ]


def get_memory(
    wallet_address: str,
    signature: str,
    message: str,
) -> VerifiableMemory:
    """
    Authenticate via wallet signature and return a VerifiableMemory instance
    keyed to `wallet_address`.

    The API's own AGENT_KEY is used for all blockchain operations; the user's
    private key never leaves the browser.
    """
    # --- Verify the MetaMask signature ---
    if not message.startswith(f"0G Mem authentication | Wallet: {wallet_address}"):
        raise HTTPException(
            status_code=401,
            detail="Message format invalid. Expected '0G Mem authentication | Wallet: <address> | Timestamp: ...'",
        )
    verify_signature(wallet_address, signature, message)

    # --- Resolve the server-side signing key ---
    agent_key = os.environ.get("AGENT_KEY")
    if not agent_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: AGENT_KEY environment variable is not set.",
        )

    # --- Return cached or fresh VerifiableMemory instance ---
    cache_key = wallet_address.lower()
    if cache_key not in _memory_instances:
        net = NETWORKS["0g-testnet"]
        _memory_instances[cache_key] = VerifiableMemory(
            agent_id=wallet_address,
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
    return _memory_instances[cache_key]
