"""AES-256-GCM encryption for secrets at rest (API keys, webhooks).

Values are stored as base64(nonce || ciphertext). The master key is derived
from settings.master_key via SHA-256 so any passphrase length works.
"""
import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .settings import get_settings

_NONCE_LEN = 12


def _key() -> bytes:
    return hashlib.sha256(get_settings().master_key.encode()).digest()


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    raw = base64.b64decode(token)
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(_key()).decrypt(nonce, ct, None).decode()


def mask(value: str, keep: int = 4) -> str:
    """Display form for stored secrets: 'sk-a***xyz9'."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}***{value[-keep:]}"
