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
INACTIVITY_DAYS: int = int(os.environ.get("INACTIVITY_DAYS", "30"))
WARNING_DAYS: int = int(
    os.environ.get("WARNING_DAYS", "7")
)  # days before removal after warning
MT5_GRACE_DAYS: int = int(os.environ.get("MT5_GRACE_DAYS", "2"))


DIFFERENT_BROKER_PRICE: str = os.environ.get("DIFFERENT_BROKER_PRICE", "$35")

# ── VIP Mentorship Packages ───────────────────────────────────────────────────
VIP_ONE_ON_ONE_PRICE: str = os.environ.get("VIP_ONE_ON_ONE_PRICE", "$1200")
VIP_GROUP_PRICE: str = os.environ.get("VIP_GROUP_PRICE", "$250")
VIP_ONE_ON_ONE_PAYMENT_LINK: str = os.environ.get("VIP_ONE_ON_ONE_PAYMENT_LINK", "")
VIP_GROUP_PAYMENT_LINK: str = os.environ.get("VIP_GROUP_PAYMENT_LINK", "")

MENTORSHIP_ADVANCED_LABEL: str = os.environ.get(
    "MENTORSHIP_ADVANCED_LABEL", "EXNESS VIP SIGNALS"
)
# ── Mentorship Labels (dynamic per client) ────────────────────────────────────
LABEL_BEGINNERS: str = os.environ.get("LABEL_BEGINNERS", "EXNESS VIP SIGNALS")
LABEL_ADVANCED: str = os.environ.get("LABEL_ADVANCED", "Advanced Mentorship")
LABEL_SWING: str = os.environ.get("LABEL_SWING", "Swing Trading")
LABEL_VIP: str = os.environ.get("LABEL_VIP", "VIP Mentorship")
LABEL_SIGNAL: str = os.environ.get("LABEL_SIGNAL", "VIP Signal")
LABEL_INNER_CIRCLE: str = os.environ.get("LABEL_INNER_CIRCLE", "Inner Circle Community")
LABEL_DIFFERENT_BROKER: str = os.environ.get(
    "LABEL_DIFFERENT_BROKER", "Using Different Broker?"
)

# ── Payment Method 1 — Bank Transfer ─────────────────────────────────────────
PAYMENT_METHOD_1_NAME: str = os.environ.get("PAYMENT_METHOD_1_NAME", "Bank Transfer")
PAYMENT_METHOD_1_BANK: str = os.environ.get("PAYMENT_METHOD_1_BANK", "Your Bank Name")
PAYMENT_METHOD_1_ACCOUNT_NAME: str = os.environ.get(
    "PAYMENT_METHOD_1_ACCOUNT_NAME", "Your Name"
)
PAYMENT_METHOD_1_ACCOUNT_NUMBER: str = os.environ.get(
    "PAYMENT_METHOD_1_ACCOUNT_NUMBER", "0000000000"
)

# ── Payment Method 2 — Mobile Money ──────────────────────────────────────────
PAYMENT_METHOD_2_NAME: str = os.environ.get("PAYMENT_METHOD_2_NAME", "Mobile Money")
PAYMENT_METHOD_2_NETWORK: str = os.environ.get("PAYMENT_METHOD_2_NETWORK", "MTN")
PAYMENT_METHOD_2_NUMBER: str = os.environ.get("PAYMENT_METHOD_2_NUMBER", "0000000000")
PAYMENT_METHOD_2_ACCOUNT_NAME: str = os.environ.get(
    "PAYMENT_METHOD_2_ACCOUNT_NAME", "Your Name"
)

# ── Payment Method 3 — Crypto ─────────────────────────────────────────────────
PAYMENT_METHOD_3_NAME: str = os.environ.get("PAYMENT_METHOD_3_NAME", "Crypto (USDT)")
PAYMENT_METHOD_3_NETWORK: str = os.environ.get("PAYMENT_METHOD_3_NETWORK", "TRC20")
PAYMENT_METHOD_3_WALLET: str = os.environ.get(
    "PAYMENT_METHOD_3_WALLET", "Your Wallet Address"
)

# ── MT5 Verification ──────────────────────────────────────────────────────────
MT5_GRACE_DAYS: int = int(os.environ.get("MT5_GRACE_DAYS", "5"))
MT5_MIN_DEPOSIT: float = float(os.environ.get("MT5_MIN_DEPOSIT", "10.0"))
INACTIVITY_DAYS: int = int(os.environ.get("INACTIVITY_DAYS", "30"))
PARTNER_SWITCH_WARNING_HOURS: int = int(
    os.environ.get("PARTNER_SWITCH_WARNING_HOURS", "24")
)

MT5_MIN_DEPOSIT: float = float(os.environ.get("MT5_MIN_DEPOSIT", "10.0"))

# # ── Payment Method 4 — Crypto ─────────────────────────────────────────────────
# PAYMENT_METHOD_4_NAME: str = os.environ.get("PAYMENT_METHOD_4_NAME", "Crypto (USDT)")
# PAYMENT_METHOD_4_NETWORK: str = os.environ.get("PAYMENT_METHOD_4_NETWORK", "TRC20")
# PAYMENT_METHOD_4_WALLET: str = os.environ.get(
#     "PAYMENT_METHOD_4_WALLET", "Your Wallet Address"
# )
