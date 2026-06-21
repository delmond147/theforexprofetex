"""
signals.py — Admin command to send trade signals and announcements
to all verified active users.
"""

from __future__ import annotations
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from src.core.settings import ADMIN_CHAT_ID, MENTOR_NAME
from src.db.database import get_all_verified_users
from src.core.logging import logger


def _is_admin(user_id: int) -> bool:
    if not ADMIN_CHAT_ID:
        return False
    return user_id == int(ADMIN_CHAT_ID)


async def send_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /signal <message>
    Sends a trade signal to all verified active users.
    Admin only.

    Usage: /signal EURUSD BUY 1.0850 | SL: 1.0800 | TP: 1.0950
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "📈 *Usage:* `/signal your signal here`\n\n"
            "Example:\n"
            "`/signal EURUSD BUY @ 1.0850 | SL: 1.0800 | TP: 1.0950`",
            parse_mode="Markdown",
        )
        return

    signal_text = " ".join(context.args)
    verified_users = get_all_verified_users()

    if not verified_users:
        await update.message.reply_text("No verified users to send signal to.")
        return

    await update.message.reply_text(
        f"📡 Sending signal to {len(verified_users)} verified users..."
    )

    success, failed = 0, 0
    for db_user in verified_users:
        try:
            await context.bot.send_message(
                chat_id=db_user["telegram_id"],
                text=(
                    f"📈 *{MENTOR_NAME} Trade Signal*\n\n"
                    f"{signal_text}\n\n"
                    f"_Sent by {MENTOR_NAME}_"
                ),
                parse_mode="Markdown",
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Signal sent!\n" f"• Delivered: {success}\n" f"• Failed: {failed}"
    )
    logger.info("signal_sent", success=success, failed=failed)


async def send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /announce <message>
    Sends an announcement to all verified users.
    Admin only.
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "📢 *Usage:* `/announce your announcement here`",
            parse_mode="Markdown",
        )
        return

    message = " ".join(context.args)
    verified_users = get_all_verified_users()

    if not verified_users:
        await update.message.reply_text("No verified users to announce to.")
        return

    await update.message.reply_text(
        f"📡 Sending announcement to {len(verified_users)} users..."
    )

    success, failed = 0, 0
    for db_user in verified_users:
        try:
            await context.bot.send_message(
                chat_id=db_user["telegram_id"],
                text=(f"📢 *Announcement from {MENTOR_NAME}*\n\n" f"{message}"),
                parse_mode="Markdown",
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Announcement sent!\n" f"• Delivered: {success}\n" f"• Failed: {failed}"
    )
    logger.info("announcement_sent", success=success, failed=failed)


async def check_inactive_now(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /checkinactive — Manually trigger the activity check.
    Admin only.
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    await update.message.reply_text("⏳ Running activity check now...")
    from src.services.activity_checker import run_activity_check

    await run_activity_check(context.bot)
    await update.message.reply_text(
        "✅ Activity check complete. Check your inbox for the summary."
    )


async def list_verified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /listusers — Shows count and list of all verified users.
    Admin only.
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    verified_users = get_all_verified_users()

    if not verified_users:
        await update.message.reply_text("No verified users yet.")
        return

    lines = [f"👥 *Verified Users ({len(verified_users)} total)*\n"]
    for u in verified_users:
        handle = f"@{u['username']}" if u["username"] else "no username"
        warned = "⚠️" if u["warning_sent_at"] else "✅"
        lines.append(
            f"{warned} {u['first_name']} ({handle})\n"
            f"   📧 {u['verified_email']}\n"
            f"   📚 {(u['mentorship_type'] or 'unknown').capitalize()}"
        )

    # Split into chunks if too long
    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n_...list truncated. Too many users._"

    await update.message.reply_text(text, parse_mode="Markdown")
