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
from src.services.exness_client import exness
from src.services.activity_checker import remove_user

from src.core.settings import (
    ADMIN_CHAT_ID,
    MENTOR_NAME,
    VIP_GROUP_ID,
    MT5_GRACE_DAYS,
    MENTOR_CONTACT,
    INACTIVITY_DAYS,
    VIP_GROUP_ID,
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


async def mt5_status_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /mt5status — Shows MT5 verification and trading activity status
    for all verified members. Highlights inactive traders.
    Admin only.
    """
    user = update.effective_user
    if not _is_admin(user.id):
        return

    from src.db.database import get_all_verified_users
    from src.services.exness_client import exness
    from src.core.settings import INACTIVITY_DAYS
    from datetime import datetime, timedelta

    verified_users = get_all_verified_users()

    if not verified_users:
        await update.message.reply_text("No verified users found.")
        return

    await update.message.reply_text(
        f"⏳ Checking MT5 status for *{len(verified_users)}* members...\n\n"
        f"This may take a moment.",
        parse_mode="Markdown",
    )

    active_list = []
    inactive_list = []
    no_mt5_list = []
    error_list = []

    for db_user in verified_users:
        telegram_id = db_user["telegram_id"]
        email = db_user["verified_email"]
        first_name = db_user["first_name"] or "Unknown"
        username = f"@{db_user['username']}" if db_user["username"] else "no username"
        mt5_verified = db_user["mt5_verified"]

        if not mt5_verified:
            no_mt5_list.append(f"• {first_name} ({username})\n  📧 {email}")
            await asyncio.sleep(0.2)
            continue

        try:
            accounts = await asyncio.wait_for(
                exness.get_client_accounts(email),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            error_list.append(f"• {first_name} ({username}) — timeout")
            continue
        except Exception as e:
            error_list.append(f"• {first_name} ({username}) — {str(e)[:50]}")
            continue

        mt5_accounts = [a for a in accounts if a.get("platform", "").lower() == "mt5"]

        if not mt5_accounts:
            no_mt5_list.append(f"• {first_name} ({username})\n  📧 {email}")
            await asyncio.sleep(0.2)
            continue

        # Check last trade date
        latest_trade = None
        for account in mt5_accounts:
            trade_date = account.get("client_account_last_trade")
            if trade_date:
                if not latest_trade or trade_date > latest_trade:
                    latest_trade = trade_date

        if latest_trade:
            try:
                trade_dt = datetime.fromisoformat(latest_trade)
                days_since = (datetime.utcnow() - trade_dt).days

                if days_since <= INACTIVITY_DAYS:
                    active_list.append(
                        f"• {first_name} ({username})\n"
                        f"  📅 Last trade: {latest_trade[:10]} "
                        f"({days_since}d ago)"
                    )
                else:
                    inactive_list.append(
                        f"• {first_name} ({username})\n"
                        f"  📧 {email}\n"
                        f"  📅 Last trade: {latest_trade[:10]} "
                        f"({days_since}d ago) ⚠️"
                    )
            except Exception:
                active_list.append(
                    f"• {first_name} ({username}) — trade date parse error"
                )
        else:
            inactive_list.append(
                f"• {first_name} ({username})\n"
                f"  📧 {email}\n"
                f"  📅 No trades found ⚠️"
            )

        await asyncio.sleep(0.3)

    # ── Send summary report ───────────────────────────────────────────────────
    summary = (
        f"📊 *MT5 Status Report*\n\n"
        f"✅ Actively trading: {len(active_list)}\n"
        f"⚠️ Inactive ({INACTIVITY_DAYS}+ days): {len(inactive_list)}\n"
        f"❌ No MT5 account: {len(no_mt5_list)}\n"
        f"🔴 Errors: {len(error_list)}\n"
        f"👥 Total checked: {len(verified_users)}"
    )
    await update.message.reply_text(summary, parse_mode="Markdown")

    # ── Active traders ────────────────────────────────────────────────────────
    if active_list:
        text = "✅ *Actively Trading Members:*\n\n" + "\n\n".join(active_list)
        if len(text) > 4000:
            text = text[:4000] + "\n\n_...truncated_"
        await update.message.reply_text(text, parse_mode="Markdown")

    # ── Inactive traders ──────────────────────────────────────────────────────
    if inactive_list:
        text = (
            f"⚠️ *Inactive Members ({INACTIVITY_DAYS}+ days no trades):*\n\n"
            + "\n\n".join(inactive_list)
        )
        if len(text) > 4000:
            text = text[:4000] + "\n\n_...truncated_"

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🦵 Kick All Inactive Now",
                            callback_data="confirm_kick_inactive",
                        )
                    ],
                ]
            ),
        )

    # ── No MT5 ────────────────────────────────────────────────────────────────
    if no_mt5_list:
        text = "❌ *No MT5 Account / Not Verified:*\n\n" + "\n\n".join(no_mt5_list)
        if len(text) > 4000:
            text = text[:4000] + "\n\n_...truncated_"
        await update.message.reply_text(text, parse_mode="Markdown")

    # ── Errors ────────────────────────────────────────────────────────────────
    if error_list:
        await update.message.reply_text(
            "🔴 *Failed to check:*\n\n" + "\n".join(error_list),
            parse_mode="Markdown",
        )


async def confirm_kick_inactive_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handles the 'Kick All Inactive Now' button from /mt5status.
    Kicks all inactive members immediately.
    """
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_admin(user.id):
        return

    await query.edit_message_text(
        "⏳ Kicking all inactive members...",
        parse_mode="Markdown",
    )

    verified_users = get_all_verified_users()
    kicked = 0
    failed = 0

    for db_user in verified_users:
        telegram_id = db_user["telegram_id"]
        email = db_user["verified_email"]
        first_name = db_user["first_name"] or "Trader"
        mt5_verified = db_user["mt5_verified"]

        if not mt5_verified:
            continue

        try:
            accounts = await asyncio.wait_for(
                exness.get_client_accounts(email),
                timeout=15.0,
            )
        except Exception:
            failed += 1
            continue

        mt5_accounts = [a for a in accounts if a.get("platform", "").lower() == "mt5"]

        is_inactive = True
        for account in mt5_accounts:
            trade_date = account.get("client_account_last_trade")
            if trade_date:
                try:
                    trade_dt = datetime.fromisoformat(trade_date)
                    days_since = (datetime.utcnow() - trade_dt).days
                    if days_since <= INACTIVITY_DAYS:
                        is_inactive = False
                        break
                except Exception:
                    pass

        if is_inactive:
            await remove_user(
                query.message.bot,
                telegram_id,
                first_name,
                email,
            )
            kicked += 1

        await asyncio.sleep(0.3)

    await query.message.reply_text(
        f"✅ *Done!*\n\n"
        f"🦵 Kicked: {kicked}\n"
        f"❌ Failed: {failed}\n\n"
        f"All kicked members have been notified and must re-verify "
        f"to get a new group access link.",
        parse_mode="Markdown",
    )
    logger.info("kick_inactive_complete", kicked=kicked, failed=failed)
