"""
vault.py — Encrypts and decrypts sensitive values using Fernet symmetric encryption.

Without SECRET_KEY, stored credentials in the DB are completely unreadable.
"""

from __future__ import annotations
import os
from cryptography.fernet import Fernet, InvalidToken
from src.core.logging import logger


def _get_fernet() -> Fernet:
    key = os.environ.get("SECRET_KEY")
    if not key:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            'Generate one with: python -c "from cryptography.fernet import '
            'Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns base64 encoded encrypted string."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    """Decrypt an encrypted string. Returns None if decryption fails."""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception) as e:
        logger.error("decryption_failed", error=str(e))
        return None
