"""
signals.py — Admin command to send trade signals and announcements
to all verified active users.
"""

from __future__ import annotations
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.settings import (
    ADMIN_CHAT_ID,
    MENTOR_NAME,
    VIP_GROUP_ID,
    MT5_GRACE_DAYS,
    MENTOR_CONTACT,
)
from src.db.database import (
    get_all_verified_users,
    get_verified_but_no_mt5,
    set_mt5_pending,
    mark_removed,
)
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
    """/checkinactive — Manually trigger the activity check."""
    user = update.effective_user
    if not _is_admin(user.id):
        return

    await update.message.reply_text("⏳ Running activity check now...")
    try:
        from src.services.activity_checker import run_activity_check

        await run_activity_check(context.bot)
        await update.message.reply_text(
            "✅ Activity check complete. Check your inbox for the summary."
        )
    except Exception as e:
        logger.error("checkinactive_command_failed", error=str(e), exc_info=True)
        await update.message.reply_text(
            f"❌ Activity check failed with error:\n\n`{str(e)}`",
            parse_mode="Markdown",
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


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/checkstatus — Shows current DB state for debugging."""
    user = update.effective_user
    if not _is_admin(user.id):
        return

    from src.db.database import get_all_verified_users, get_pending_mt5_users

    verified = get_all_verified_users()
    pending = get_pending_mt5_users()

    await update.message.reply_text(
        f"📊 *Current Bot Status*\n\n"
        f"✅ Verified users: {len(verified)}\n"
        f"⏳ Pending MT5: {len(pending)}\n\n"
        f"*Verified users:*\n"
        + "\n".join(
            [
                f"• {u['first_name']} — {u['verified_email']} "
                f"(MT5: {'✅' if u['mt5_verified'] else '❌'}, "
                f"Removed: {'✅' if u['removed'] else '❌'})"
                for u in verified
            ]
            or ["None"]
        ),
        parse_mode="Markdown",
    )


async def kick_unverified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /kickunverified — Kicks all users who never completed MT5 verification.
    They must re-verify MT5 status to get a new one-time group link.
    Admin only.
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    users = get_verified_but_no_mt5()

    if not users:
        await update.message.reply_text(
            "✅ No users found without MT5 verification. Everyone is compliant."
        )
        return

    await update.message.reply_text(
        f"⏳ Found *{len(users)}* users without MT5 verification.\n\n"
        f"Kicking them from the group and resetting their status...",
        parse_mode="Markdown",
    )

    kicked = 0
    notified = 0
    failed = 0

    for db_user in users:
        telegram_id = db_user["telegram_id"]
        first_name = db_user["first_name"] or "Trader"
        email = db_user["verified_email"]

        # Step 1: Kick from Telegram group
        if VIP_GROUP_ID:
            try:
                await context.bot.ban_chat_member(
                    chat_id=int(VIP_GROUP_ID),
                    user_id=telegram_id,
                )
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(
                    chat_id=int(VIP_GROUP_ID),
                    user_id=telegram_id,
                )
                kicked += 1
                logger.info(
                    "kickunverified_kicked", telegram_id=telegram_id, email=email
                )
            except TelegramError as e:
                logger.error(
                    "kickunverified_kick_failed", telegram_id=telegram_id, error=str(e)
                )
                failed += 1

        # Step 2: Reset MT5 status — set a new deadline
        deadline = (datetime.utcnow() + timedelta(days=MT5_GRACE_DAYS)).isoformat()
        set_mt5_pending(telegram_id, deadline)

        # Step 3: Notify the user
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"⚠️ *Important Notice from {MENTOR_NAME}*\n\n"
                    f"Hi {first_name}! 👋\n\n"
                    f"We've updated our verification requirements. "
                    f"To remain in the {MENTOR_NAME} VIP group, all members "
                    f"must have a *new MT5 trading account* created under "
                    f"{MENTOR_NAME}'s partner link with an active deposit.\n\n"
                    f"Your access has been temporarily removed until you "
                    f"complete this step.\n\n"
                    f"Here's what to do:\n"
                    f"1️⃣ Log into your *Exness Personal Area*\n"
                    f"2️⃣ Create a *new MT5 account* (after switching to "
                    f"{MENTOR_NAME}'s partner link)\n"
                    f"3️⃣ Fund the account (minimum *$10*)\n"
                    f"4️⃣ Place at least one trade\n"
                    f"5️⃣ Tap /start and tap *'Check MT5 Status'*\n\n"
                    f"⏰ You have *{MT5_GRACE_DAYS} days* to complete this "
                    f"and get your new group access link.\n\n"
                    f"Any questions? Tap below 👇"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Check MT5 Status", callback_data="check_mt5_status"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔗 Open Exness Personal Area",
                                url="https://my.exness.com",
                            )
                        ],
                        [InlineKeyboardButton("🆘 Get Support", url=MENTOR_CONTACT)],
                    ]
                ),
            )
            notified += 1
        except TelegramError as e:
            logger.error(
                "kickunverified_notify_failed", telegram_id=telegram_id, error=str(e)
            )

        await asyncio.sleep(0.5)

    # Send summary to admin
    await update.message.reply_text(
        f"✅ *Kick Unverified Complete*\n\n"
        f"👥 Total found: {len(users)}\n"
        f"🦵 Kicked from group: {kicked}\n"
        f"📩 Notified: {notified}\n"
        f"❌ Failed to kick: {failed}\n\n"
        f"All affected users have been notified and given "
        f"{MT5_GRACE_DAYS} days to complete MT5 verification.",
        parse_mode="Markdown",
    )
    logger.info(
        "kickunverified_complete",
        total=len(users),
        kicked=kicked,
        notified=notified,
        failed=failed,
    )
