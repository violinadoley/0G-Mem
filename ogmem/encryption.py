"""AES-256-GCM encryption with HKDF-SHA256 key derivation from wallet private key."""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


_NONCE_SIZE = 12   # AES-GCM standard nonce: 96 bits
_SALT = b"0g-memory-v1-encryption"
_INFO = b"memory-blob-encryption-key"


def derive_encryption_key(private_key_hex: str) -> bytes:
    """Derive a 32-byte AES-256 key from a wallet private key via HKDF-SHA256."""
    raw = bytes.fromhex(private_key_hex.lstrip("0x").zfill(64))
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=_INFO,
    )
    return hkdf.derive(raw)


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM encrypt. Output: nonce (12B) || ciphertext || tag (16B)."""
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-256-GCM decrypt. Raises InvalidTag if data was tampered with."""
    nonce = ciphertext[:_NONCE_SIZE]
    body = ciphertext[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, body, None)
