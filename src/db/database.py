"""
database.py — SQLite-backed user session memory and secure credential storage.
"""

from __future__ import annotations
import sqlite3
import os
from datetime import datetime
from src.core.logging import logger

DB_PATH = os.environ.get("DB_PATH", "data/theforexprophetess.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id     INTEGER PRIMARY KEY,
                username        TEXT,
                first_name      TEXT,
                verified_email  TEXT,
                mentorship_type TEXT,
                verified_at     TEXT,
                joined_at       TEXT DEFAULT (datetime('now')),
                last_active_check TEXT,
                warning_sent_at TEXT,
                removed         INTEGER DEFAULT 0,
                mt5_verified    INTEGER DEFAULT 0,
                mt5_check_deadline TEXT,
                mt5_account_id  TEXT
            );

            CREATE TABLE IF NOT EXISTS verification_attempts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER,
                email           TEXT,
                success         INTEGER,
                attempted_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bot_config (
                key             TEXT PRIMARY KEY,
                value           TEXT,
                updated_at      TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS activity_log(
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER,
                email           TEXT,
                last_trade_date     TEXT,
                is_active       INTEGER,
                checked_at      TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS incomplete_flows (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                flow_type TEXT,
                started_at TEXT DEFAULT (datetime('now')),
                last_reminded TEXT,
                reminder_count INTEGER DEFAULT 0
            );
        """)

        # Check if mt5 columns exist (for migration of existing databases)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if "mt5_verified" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN mt5_verified INTEGER DEFAULT 0")
        if "mt5_check_deadline" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN mt5_check_deadline TEXT")
        if "mt5_account_id" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN mt5_account_id TEXT")

    logger.info("db_initialized", path=DB_PATH)


# ── User helpers ──────────────────────────────────────────────────────────────


def upsert_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """,
            (telegram_id, username, first_name),
        )


def save_verification(
    telegram_id: int,
    email: str,
    mentorship_type: str,
) -> None:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET verified_email  = ?,
                mentorship_type = ?,
                verified_at     = ?,
                removed         = 0,
                warning_sent_at = NULL,
                mt5_verified    = 1,
                mt5_check_deadline = NULL
            WHERE telegram_id = ?
        """,
            (email, mentorship_type, now, telegram_id),
        )
        conn.execute(
            """
            INSERT INTO verification_attempts (telegram_id, email, success)
            VALUES (?, ?, 1)
        """,
            (telegram_id, email),
        )


def log_failed_attempt(telegram_id: int, email: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO verification_attempts (telegram_id, email, success)
            VALUES (?, ?, 0)
        """,
            (telegram_id, email),
        )


def get_user(telegram_id: int) -> sqlite3.Row | None:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_all_user_ids() -> list[int]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        return [row["telegram_id"] for row in rows]


def get_all_verified_users() -> list[sqlite3.Row]:
    """Return all verified non-removed users for activity checking."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE verified_email IS NOT NULL
                AND removed = 0
        """).fetchall()


def get_warned_users_past_deadline(days: int) -> list[sqlite3.Row]:
    """Return users warned more than N days ago - ready for removal."""
    with _get_conn() as conn:
        return conn.execute(f"""
            SELECT * FROM users
            WHERE warning_sent_at IS NOT NULL
                AND removed = 0
                AND datetime(warning_sent_at, '+{days} days') <= datetime('now')
        """).fetchall()


def mark_warning_sent(telegram_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users SET warning_sent_at = ?
            WHERE telegram_id = ?
            """,
            (now, telegram_id),
        )


def mark_removed(telegram_id: int) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET removed = 1,
                verified_email = NULL,
                warning_sent_at = NULL,
                mt5_verified = 0,
                mt5_check_deadline = NULL,
                mt5_account_id = NULL
            WHERE telegram_id = ?
        """,
            (telegram_id,),
        )


def save_pending_verification(
    telegram_id: int,
    email: str,
    mentorship_type: str,
    deadline_hours: int,
    mt5_account_id: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    from datetime import timedelta

    deadline = (datetime.utcnow() + timedelta(hours=deadline_hours)).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET verified_email  = ?,
                mentorship_type = ?,
                verified_at     = ?,
                removed         = 0,
                warning_sent_at = NULL,
                mt5_verified    = 0,
                mt5_check_deadline = ?,
                mt5_account_id = ?
            WHERE telegram_id = ?
        """,
            (email, mentorship_type, now, deadline, mt5_account_id, telegram_id),
        )
        conn.execute(
            """
            INSERT INTO verification_attempts (telegram_id, email, success)
            VALUES (?, ?, 1)
        """,
            (telegram_id, email),
        )


def mark_mt5_verified(telegram_id: int, mt5_account_id: str | None = None) -> None:
    with _get_conn() as conn:
        if mt5_account_id:
            conn.execute(
                """
                UPDATE users
                SET mt5_verified = 1,
                    mt5_check_deadline = NULL,
                    mt5_account_id = ?
                WHERE telegram_id = ?
            """,
                (mt5_account_id, telegram_id),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET mt5_verified = 1,
                    mt5_check_deadline = NULL
                WHERE telegram_id = ?
            """,
                (telegram_id,),
            )


def get_pending_mt5_users() -> list[sqlite3.Row]:
    """Return all users who are pending MT5/deposit verification."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE verified_email IS NOT NULL
                AND mt5_verified = 0
                AND removed = 0
        """).fetchall()


def mark_active(telegram_id: int, last_trade_date: str) -> None:
    """Clear warning if user becomes active again."""
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET last_active_check = ?,
                warning_sent_at = NULL
            WHERE telegram_id = ?
        """,
            (now, telegram_id),
        )
        conn.execute(
            """
            INSERT INTO activity_log (telegram_id, email, last_trade_date, is_active)
            SELECT ?, verified_email, ?, 1 FROM  users WHERE telegram_id = ?
        """,
            (telegram_id, last_trade_date, telegram_id),
        )


def mark_inactive(telegram_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users SET last_active_check = ? WHERE telegram_id = ?
            
        """,
            (now, telegram_id),
        )
        conn.execute(
            """
            INSERT INTO activity_log (telegram_id, email, last_trade_date, is_active)
            SELECT ?, verified_email, NULL, 0 FROM users WHERE telegram_id = ?
        """,
            (telegram_id, telegram_id),
        )


# ── Bot config / credential storage ──────────────────────────────────────────


def set_config(key: str, value: str) -> None:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO bot_config (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = excluded.updated_at
        """,
            (key, value, now),
        )


def get_config(key: str) -> str | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM bot_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None


def delete_config(key: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM bot_config WHERE key = ?", (key,))


def count_recent_attempts(telegram_id: int, minutes: int = 10) -> int:
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM verification_attempts
            WHERE telegram_id = ?
            AND attempted_at >= datetime('now', ? || ' minutes')
        """,
            (telegram_id, f"-{minutes}"),
        ).fetchone()
        return row["cnt"] if row else 0


# -- Incomplete flow tracking --------------------------------------------


def save_incomplete_flow(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    flow_type: str,
) -> None:
    """Record that a user started a flow but hasn't completed it."""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO incomplete_flows (telegram_id, username, first_name, flow_type, started_at, reminder_count)
            VALUES (?, ?, ?, ?, datetime('now'), 0)
            ON CONFLICT(telegram_id) DO UPDATE SET
                flow_type       = excluded.flow_type,
                started_at      = excluded.started_at,
                reminder_count  = 0,
                last_reminded   = NULL
        """,
            (telegram_id, username, first_name, flow_type),
        )


def clear_incomplete_flow(telegram_id: int) -> None:
    """Remove incomplete flow record when user completes or cancels."""
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM incomplete_flows WHERE telegram_id = ?", (telegram_id,)
        )


def get_users_to_remind(hours: int = 4, max_reminders: int = 42) -> list[sqlite3.Row]:
    """
    Return users due for a reminder.
    Default: every 4 hours for 7 days (42 reminders max).
    Also stops if flow was started more than 7 days ago.
    """
    with _get_conn() as conn:
        return conn.execute(f"""
            SELECT * FROM incomplete_flows 
            WHERE reminder_count < {max_reminders}
                AND datetime(started_at, '+7 days') > datetime('now')
                AND (
                    last_reminded IS NULL
                    OR datetime(last_reminded, '+{hours} hours') <= datetime('now')
                    )
            """).fetchall()


def mark_reminded(telegram_id: int) -> None:
    """Update last reminded time and increment counter."""
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE incomplete_flows
            SET last_reminded = datetime('now'),
                reminder_count = reminder_count + 1
            WHERE telegram_id = ?
        """,
            (telegram_id,),
        )


# ── MT5 verification helpers ──────────────────────────────────────────────────


def set_mt5_pending(telegram_id: int, deadline: str) -> None:
    """Mark user as pending MT5 verification with a deadline."""
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET mt5_verified       = 0,
                mt5_check_deadline = ?
            WHERE telegram_id = ?
        """,
            (deadline, telegram_id),
        )


def set_mt5_verified(telegram_id: int, mt5_account_id: str) -> None:
    """Mark user as having a funded MT5 account."""
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET mt5_verified    = 1,
                mt5_account_id  = ?,
                mt5_check_deadline = NULL
            WHERE telegram_id = ?
        """,
            (mt5_account_id, telegram_id),
        )


def get_pending_mt5_users() -> list[sqlite3.Row]:
    """Return users who are verified but pending MT5 + deposit check."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE verified_email   IS NOT NULL
              AND mt5_verified      = 0
              AND mt5_check_deadline IS NOT NULL
              AND removed           = 0
        """).fetchall()


def get_deadline_exceeded_mt5_users() -> list[sqlite3.Row]:
    """Return users whose MT5 grace period has expired."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE verified_email    IS NOT NULL
              AND mt5_verified       = 0
              AND mt5_check_deadline IS NOT NULL
              AND removed            = 0
              AND datetime(mt5_check_deadline) <= datetime('now')
        """).fetchall()


# ── Partner switch helpers ────────────────────────────────────────────────────


def mark_partner_switch_warned(telegram_id: int) -> None:
    """Record when a partner switch warning was sent."""
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE users SET partner_switch_warned_at = ?
            WHERE telegram_id = ?
        """,
            (now, telegram_id),
        )


def get_partner_switch_removal_due() -> list[sqlite3.Row]:
    """Return users warned about partner switch whose 24h deadline has passed."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE partner_switch_warned_at IS NOT NULL
              AND removed = 0
              AND datetime(partner_switch_warned_at, '+24 hours') <= datetime('now')
        """).fetchall()


def get_all_verified_users() -> list[sqlite3.Row]:
    """Return all verified non-removed users for activity checking."""
    with _get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE verified_email IS NOT NULL
              AND removed = 0
        """).fetchall()
