"""
rate_limit.py — Prevents abuse of the email verification flow.

Checks SQLite attempt history. If a user submits more than MAX_ATTEMPTS
emails within WINDOW_MINUTES, they are blocked temporarily.
"""

from __future__ import annotations
from src.db.database import count_recent_attempts

MAX_ATTEMPTS = 5
WINDOW_MINUTES = 10


def is_rate_limited(telegram_id: int) -> bool:
    """Return True if the user has exceeded the attempt limit."""
    return count_recent_attempts(telegram_id, WINDOW_MINUTES) >= MAX_ATTEMPTS
