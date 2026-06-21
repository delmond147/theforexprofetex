"""
admin.py — Admin notifications, broadcast, and credential management commands.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from telegram import Update, Bot
from telegram.ext import ContextTypes, ConversationHandler

# Import MENTOR_NAME alongside ADMIN_CHAT_ID for multi-client dynamic rendering
from src.core.settings import ADMIN_CHAT_ID, MENTOR_NAME
from src.core.vault import encrypt
from src.db.database import (
    get_all_user_ids,
    set_config,
    delete_config,
    get_config,
)
from src.services.exness_client import exness
from src.core.logging import logger

# Conversation states for guided credential setup
AWAITING_API_EMAIL = 10
AWAITING_API_PASSWORD = 11

# ── Admin guard ───────────────────────────────────────────────────────────────


def _is_admin(user_id: int) -> bool:
    if not ADMIN_CHAT_ID:
        return False
    return user_id == int(ADMIN_CHAT_ID)


# ── /setcredentials ───────────────────────────────────────────────────────────


async def set_credentials_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Step 1 — Ask for email."""
    user = update.effective_user

    if not _is_admin(user.id):
        return ConversationHandler.END

    await update.message.reply_text(
        "🔐 *Credential Setup — Step 1 of 2*\n\n"
        "Please enter your *Exness affiliate email address*:\n\n"
        "_This message will be deleted after you reply._",
        parse_mode="Markdown",
    )
    return AWAITING_API_EMAIL


async def set_credentials_email(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Step 2 — Receive email, ask for password."""
    user = update.effective_user
    email = update.message.text.strip()

    # Delete the email message immediately
    try:
        await update.message.delete()
    except Exception:
        pass

    if "@" not in email or "." not in email:
        await context.bot.send_message(
            chat_id=user.id,
            text="⚠️ That doesn't look like a valid email. Please try again:",
        )
        return AWAITING_API_EMAIL

    # Store temporarily in context, not DB yet
    context.user_data["temp_api_email"] = email

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "✅ Email received.\n\n"
            "🔐 *Credential Setup — Step 2 of 2*\n\n"
            "Now enter your *Exness affiliate password*:\n\n"
            "_This message will be deleted immediately._"
        ),
        parse_mode="Markdown",
    )
    return AWAITING_API_PASSWORD


async def set_credentials_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Step 3 — Receive password, encrypt and save both."""
    user = update.effective_user
    password = update.message.text.strip()

    # Delete password message immediately
    try:
        await update.message.delete()
    except Exception:
        pass

    email = context.user_data.pop("temp_api_email", None)

    if not email:
        await context.bot.send_message(
            chat_id=user.id,
            text="⚠️ Something went wrong. Please start again with /setcredentials",
        )
        return ConversationHandler.END

    try:
        set_config("api_login", encrypt(email))
        set_config("api_password", encrypt(password))
        exness._token = None

        await context.bot.send_message(
            chat_id=user.id,
            text="⏳ Saved. Testing API connection...",
        )

        ok = await exness.authenticate()

        if ok:
            logger.info("credentials_set_and_verified", admin=user.id)
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "✅ *All done! Credentials saved and verified.*\n\n"
                    "🔒 Both messages have been deleted.\n"
                    "The bot is now connected to the Exness API."
                ),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "⚠️ *Credentials saved but login failed.*\n\n"
                    "Please check your email and password are correct "
                    "and try `/setcredentials` again."
                ),
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error("set_credentials_error", error=str(e))
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Something went wrong. Please try again.",
        )

    return ConversationHandler.END


# /settoken


async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /settoken <jwt_token>
    Mentor pastes their JWT token directly from Swagger UI.
    Message is deleted immediately after saving.
    """
    user = update.effective_user

    # Delete the message immediately
    try:
        await update.message.delete()
    except Exception:
        pass

    if not _is_admin(user.id):
        return

    if not context.args:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "⚠️ *Usage:* `/settoken your_jwt_token_here`\n\n"
                "Get your token from the Swagger UI Authorize dialog at:\n"
                "`https://my.exnessaffiliates.com/api/schema/swagger-ui/`\n\n"
                "1️⃣ Log in to Swagger\n"
                "2️⃣ Click *Authorize*\n"
                "3️⃣ Copy the token shown in the value field\n"
                "4️⃣ Send `/settoken <paste token here>`"
            ),
            parse_mode="Markdown",
        )
        return

    # Join full arguments to safely extract token text if spacing varies
    token = " ".join(context.args).strip()

    # Remove "JWT " prefix if mentor accidentally included it
    if token.upper().startswith("JWT "):
        token = token[4:].strip()

    try:
        set_config("api_jwt_token", encrypt(token))
        # Apply immediately to the running client
        from src.services.exness_client import exness

        exness._token = token

        logger.info("jwt_token_set", admin=user.id)

        # Test it immediately
        result = await exness.check_partner_allocation("test@test.com")
        # We just want to confirm no auth error — 404 is fine here
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "✅ *Token saved and active!*\n\n"
                "🔒 Your message has been deleted.\n"
                "The bot is now using your JWT token for all API calls."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("set_token_error", error=str(e))
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Something went wrong saving the token. Please try again.",
        )


async def clear_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cleartoken — Wipes the stored JWT token instantly."""
    user = update.effective_user
    if not _is_admin(user.id):
        return

    delete_config("api_jwt_token")
    from src.services.exness_client import exness

    exness._token = None

    logger.info("jwt_token_cleared", admin=user.id)
    await update.message.reply_text(
        "🔒 *Token cleared.*\n\n" "Use `/settoken your_token` to set a new one.",
        parse_mode="Markdown",
    )


# ── /clearcredentials ─────────────────────────────────────────────────────────


async def clear_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /clearcredentials — Wipes stored credentials from the DB instantly.
    The mentor can run this at any time to revoke bot API access.
    """
    user = update.effective_user

    if not _is_admin(user.id):
        return

    delete_config("api_login")
    delete_config("api_password")
    exness._token = None

    logger.info("credentials_cleared", admin=user.id)
    await update.message.reply_text(
        "🔒 *Credentials cleared.*\n\n"
        "The bot no longer has access to the Exness API. "
        "Use `/setcredentials email password` to restore access.",
        parse_mode="Markdown",
    )


# ── /checkapi ─────────────────────────────────────────────────────────────────


async def check_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/checkapi — Tests the current API connection."""
    user = update.effective_user

    if not _is_admin(user.id):
        return

    if not exness.has_credentials():
        await update.message.reply_text(
            "⚠️ No credentials stored yet.\n\n"
            "Use `/setcredentials email password` to set them.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("⏳ Testing API connection...")
    ok = await exness.authenticate()

    if ok:
        await update.message.reply_text(
            "✅ *API connection is working!*\n\n"
            "The bot is authenticated and ready to verify users.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ *API connection failed.*\n\n"
            "Your credentials may have changed. "
            "Use `/setcredentials email password` to update them.",
            parse_mode="Markdown",
        )


# ── Admin notifications ───────────────────────────────────────────────────────


async def notify_admin(bot: Bot, message: str) -> None:
    if not ADMIN_CHAT_ID:
        return
    try:
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message,
            parse_mode="Markdown",
        )
        logger.info("admin_notified")
    except Exception as e:
        logger.error("admin_notify_failed", error=str(e))


def verified_message(
    first_name: str,
    username: str | None,
    email: str,
    mentorship: str,
) -> str:
    handle = f"@{username}" if username else "no username"
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return (
        "🔔 *New Verified Member!*\n\n"
        f"👤 {first_name} ({handle})\n"
        f"📧 {email}\n"
        f"📚 {mentorship.capitalize()} Mentorship\n"
        f"🕐 {now}"
    )


def failed_verification_message(
    first_name: str,
    username: str | None,
    email: str,
) -> str:
    handle = f"@{username}" if username else "no username"
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return (
        "⚠️ *Failed Verification Attempt*\n\n"
        f"👤 {first_name} ({handle})\n"
        f"📧 {email}\n"
        f"🕐 {now}"
    )


def vip_inquiry_message(first_name: str, username: str | None) -> str:
    handle = f"@{username}" if username else "no username"
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return (
        "💎 *New VIP Inquiry!*\n\n"
        f"👤 {first_name} ({handle})\n"
        f"🕐 {now}"
        "_This user has expressed interest in the VIP Mentorship. Follow up with them to provide more details._"
    )


def new_user_message(first_name: str, username: str | None) -> str:
    handle = f"@{username}" if username else "no username"
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return "👋 *New User Started Bot*\n\n" f"👤 {first_name} ({handle})\n" f"🕐 {now}"


# ── /broadcast ────────────────────────────────────────────────────────────────


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_admin(user.id):
        await update.message.reply_text(
            "⛔ You are not authorised to use this command."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/broadcast Your message here`",
            parse_mode="Markdown",
        )
        return

    message = " ".join(context.args)
    user_ids = get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("No users to broadcast to yet.")
        return

    await update.message.reply_text(f"📡 Broadcasting to {len(user_ids)} users...")

    success, failed = 0, 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                # FIXED: Changed hardcoded brand name to dynamic MENTOR_NAME variable
                text=f"📢 *Message from {MENTOR_NAME}:*\n\n{message}",
                parse_mode="Markdown",
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Broadcast complete.\n" f"• Sent: {success}\n" f"• Failed: {failed}"
    )
    logger.info("broadcast_done", success=success, failed=failed)
