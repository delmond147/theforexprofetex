"""
settings.py — All configuration loaded from environment variables.
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return val


# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
WEBHOOK_URL: str = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_PORT: int = int(os.environ.get("PORT", "8443"))
MENTOR_NAME: str = os.environ.get("MENTOR_NAME", "1BigMarathon")

# ── Exness API ────────────────────────────────────────────────────────────────
API_BASE: str = os.environ.get("API_BASE", "https://my.exnessaffiliates.com/api")
# Added structural property extractions to keep client dependencies decoupled from core codebase
EXNESS_API_KEY: str = os.environ.get("EXNESS_API_KEY", "")
EXNESS_PARTNER_ID: str = os.environ.get("EXNESS_PARTNER_ID", "")

# ── Encryption ────────────────────────────────────────────────────────────────
SECRET_KEY: str = _require("SECRET_KEY")

# ── Partner & Group Links ─────────────────────────────────────────────────────
PARTNER_LINK: str = _require("PARTNER_LINK")
BEGINNERS_GROUP_LINK: str = os.environ.get(
    "BEGINNERS_GROUP_LINK", "https://t.me/your_beginners_group"
)
ADVANCED_GROUP_LINK: str = os.environ.get(
    "ADVANCED_GROUP_LINK", "https://t.me/your_advanced_group"
)
SWING_TRADING_LINK: str = os.environ.get(
    "SWING_TRADING_LINK", "https://t.me/your_swing_channel"
)
INNER_CIRCLE_LINK: str = os.environ.get(
    "INNER_CIRCLE_LINK", "https://t.me/your_inner_circle"
)
MENTOR_CONTACT: str = os.environ.get(
    "MENTOR_CONTACT", "https://t.me/your_telegram_username"
)
VIP_PRICE: str = os.environ.get("VIP_PRICE", "$100")

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "your_admin")

# FIXED: Cast ADMIN_CHAT_ID to an integer or None to prevent Telegram API type runtime failures
_raw_admin_chat_id = os.environ.get("ADMIN_CHAT_ID", "")
ADMIN_CHAT_ID: int | None = (
    int(_raw_admin_chat_id)
    if _raw_admin_chat_id.strip().replace("-", "").isdigit()
    else None
)


# ── VIP Signal Subscription ───────────────────────────────────────────────────
SIGNAL_PRICE_1MONTH: str = os.environ.get("SIGNAL_PRICE_1MONTH", "$15")
SIGNAL_PRICE_2MONTH: str = os.environ.get("SIGNAL_PRICE_2MONTH", "$25")
SIGNAL_PRICE_6MONTH: str = os.environ.get("SIGNAL_PRICE_6MONTH", "$50")
SIGNAL_PRICE_1YEAR: str = os.environ.get("SIGNAL_PRICE_1YEAR", "$100")

# Payment details shown after user provides name/number
PAYMENT_DETAILS: str = os.environ.get(
    "PAYMENT_DETAILS",
    "Bank: Your Bank Name\nAccount Name: Your Name\nAccount Number: 0000000000",
)

# -- Group Management --------------------------------------------

# ── Group Management ──────────────────────────────────────────────────────────
VIP_GROUP_INVITE_LINK: str = os.environ.get("VIP_GROUP_INVITE_LINK", "")
VIP_GROUP_ID: str = os.environ.get("VIP_GROUP_ID", "")  # numeric group ID for kicking
INACTIVITY_DAYS: int = int(os.environ.get("INACTIVITY_DAYS", "60"))
WARNING_DAYS: int = int(
    os.environ.get("WARNING_DAYS", "7")
)  # days before removal after warning


DIFFERENT_BROKER_PRICE: str = os.environ.get("DIFFERENT_BROKER_PRICE", "$35")

# ── VIP Mentorship Packages ───────────────────────────────────────────────────
VIP_ONE_ON_ONE_PRICE: str = os.environ.get("VIP_ONE_ON_ONE_PRICE", "$1200")
VIP_GROUP_PRICE: str = os.environ.get("VIP_GROUP_PRICE", "$250")
VIP_ONE_ON_ONE_PAYMENT_LINK: str = os.environ.get("VIP_ONE_ON_ONE_PAYMENT_LINK", "")
VIP_GROUP_PAYMENT_LINK: str = os.environ.get("VIP_GROUP_PAYMENT_LINK", "")
