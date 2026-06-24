"""
activity_checker.py — Daily scheduled job that:
1. Checks all verified users against Exness API for trading activity
2. Warns inactive users (no trades in INACTIVITY_DAYS)
3. Removes users who ignored warning past WARNING_DAYS deadline
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from telegram import Bot
from telegram.error import TelegramError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.settings import (
    BOT_TOKEN,
    ADMIN_CHAT_ID,
    VIP_GROUP_ID,
    INACTIVITY_DAYS,
    WARNING_DAYS,
    MENTOR_NAME,
    ADMIN_CHAT_ID,
    VIP_GROUP_ID,
    INACTIVITY_DAYS,
    WARNING_DAYS,
    MENTOR_NAME,
    MENTOR_CONTACT,
    LABEL_BEGINNERS,
    LABEL_ADVANCED,
    LABEL_SWING,
)
from src.db.database import (
    get_all_verified_users,
    get_warned_users_past_deadline,
    mark_warning_sent,
    mark_removed,
    mark_active,
    mark_inactive,
)
from src.services.exness_client import exness
from src.core.logging import logger


async def check_user_activity(email: str) -> tuple[bool, str | None]:
    """
    Check if a client has traded in the last INACTIVITY_DAYS.
    Uses GET /api/reports/clients/accounts/ filtered by email.
    Returns (is_active, last_trade_date).
    """
    try:
        data = await exness._get(
            "/reports/clients/accounts/", params={"search": email, "page_size": 10}
        )
        if not isinstance(data, dict):
            return True, None  # assume active if API fails

        results = data.get("data") or data.get("results") or []
        if not results:
            return False, None

        # Find most recent trade date across all accounts
        latest_trade = None
        for account in results:
            trade_date = account.get("client_account_last_trade")
            if trade_date:
                if not latest_trade or trade_date > latest_trade:
                    latest_trade = trade_date

        if not latest_trade:
            return False, None

        # Check if within inactivity window
        trade_dt = datetime.fromisoformat(latest_trade)
        days_since = (datetime.utcnow() - trade_dt).days
        is_active = days_since <= INACTIVITY_DAYS

        return is_active, latest_trade

    except Exception as e:
        logger.error("activity_check_failed", email=email, error=str(e))
        return True, None  # assume active on error


async def send_warning(bot: Bot, telegram_id: int, first_name: str) -> bool:
    """Send inactivity warning to user."""
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f"⚠️ *Inactivity Notice from {MENTOR_NAME}*\n\n"
                f"Hi {first_name}! 👋\n\n"
                f"We noticed you haven't made any trades on your Exness account "
                f"in the last {INACTIVITY_DAYS} days.\n\n"
                f"To keep your access to the {MENTOR_NAME} VIP group, "
                f"please make at least one trade within the next "
                f"*{WARNING_DAYS} days*.\n\n"
                f"If no activity is detected after {WARNING_DAYS} days, "
                f"your access will be removed automatically.\n\n"
                f"Need help getting back on track? Tap below 👇"
            ),
            parse_mode="Markdown",
            reply_markup=__import__("telegram").InlineKeyboardMarkup(
                [
                    [
                        __import__("telegram").InlineKeyboardButton(
                            "🆘 Contact Support",
                            url=__import__(
                                "src.core.settings", fromlist=["MENTOR_CONTACT"]
                            ).MENTOR_CONTACT,
                        )
                    ],
                    [
                        __import__("telegram").InlineKeyboardButton(
                            "🏠 Main Menu", callback_data="main_menu"
                        )
                    ],
                ]
            ),
        )
        return True
    except TelegramError as e:
        logger.error("warning_send_failed", telegram_id=telegram_id, error=str(e))
        return False


async def remove_user(bot: Bot, telegram_id: int, first_name: str, email: str) -> None:
    """Remove user — notify them, kick from group if VIP_GROUP_ID set, notify admin."""
    # 1. Notify user
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f"❌ *Access Removed*\n\n"
                f"Hi {first_name}, your access to the {MENTOR_NAME} VIP group "
                f"has been removed due to inactivity on your Exness account.\n\n"
                f"To regain access, simply start trading again on Exness "
                f"and verify your account again using /start. 📈"
            ),
            parse_mode="Markdown",
        )
    except TelegramError:
        pass

    # 2. Kick from Telegram group if GROUP_ID is configured
    if VIP_GROUP_ID:
        try:
            await bot.ban_chat_member(
                chat_id=int(VIP_GROUP_ID),
                user_id=telegram_id,
            )
            # Unban immediately so they can rejoin later after re-verification
            await asyncio.sleep(1)
            await bot.unban_chat_member(
                chat_id=int(VIP_GROUP_ID),
                user_id=telegram_id,
            )
            logger.info("user_kicked_from_group", telegram_id=telegram_id)
        except TelegramError as e:
            logger.error("kick_failed", telegram_id=telegram_id, error=str(e))

    # 3. Mark removed in DB
    mark_removed(telegram_id)
    logger.info("user_removed", telegram_id=telegram_id, email=email)


async def run_activity_check(bot: Bot) -> None:
    """
    Main scheduled job — runs daily.
    1. Remove users past warning deadline
    2. Check all verified users for activity
    3. Warn newly inactive users
    """
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    logger.info("activity_check_started", time=now)

    warned_count = 0
    removed_count = 0
    inactive_count = 0
    active_count = 0
    removal_list = []

    # ── Step 1: Remove users past warning deadline ────────────────────────────
    overdue = get_warned_users_past_deadline(WARNING_DAYS)
    for user in overdue:
        await remove_user(
            bot,
            user["telegram_id"],
            user["first_name"] or "Trader",
            user["verified_email"],
        )
        removal_list.append(
            f"• {user['first_name']} (@{user['username'] or 'no username'}) "
            f"— {user['verified_email']}"
        )
        removed_count += 1
        await asyncio.sleep(0.5)

    # ── Step 2: Check activity for all verified users ─────────────────────────
    verified_users = get_all_verified_users()

    for user in verified_users:
        telegram_id = user["telegram_id"]
        email = user["verified_email"]
        first_name = user["first_name"] or "Trader"

        is_active, last_trade = await check_user_activity(email)

        if is_active:
            mark_active(telegram_id, last_trade or "unknown")
            active_count += 1
        else:
            mark_inactive(telegram_id)
            inactive_count += 1

            # Only warn if not already warned
            if not user["warning_sent_at"]:
                sent = await send_warning(bot, telegram_id, first_name)
                if sent:
                    mark_warning_sent(telegram_id)
                    warned_count += 1

        await asyncio.sleep(0.3)  # respect Telegram rate limits

    # ── Step 3: Notify admin with summary ────────────────────────────────────
    if ADMIN_CHAT_ID:
        summary = (
            f"📊 *Daily Activity Check Complete*\n\n"
            f"🕐 {now}\n\n"
            f"✅ Active users: {active_count}\n"
            f"⚠️ Inactive (warned): {warned_count}\n"
            f"❌ Removed today: {removed_count}\n"
            f"👥 Total checked: {len(verified_users)}\n"
        )
        if removal_list:
            summary += "\n*Removed users:*\n" + "\n".join(removal_list)

        try:
            await bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=summary,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.error("admin_summary_failed", error=str(e))

    logger.info(
        "activity_check_complete",
        active=active_count,
        warned=warned_count,
        removed=removed_count,
    )


async def run_reminder_check(bot: Bot) -> None:
    """
    Runs every 2 hours.
    sends reminder message to users who started but didn't complete a flow.
    stops after 3 reminders per flow.
    """

    from src.db.database import (
        get_users_to_remind,
        mark_reminded,
        clear_incomplete_flow,
    )
    from src.core.settings import MENTOR_NAME, MENTOR_CONTACT

    users = get_users_to_remind(hours=2)
    logger.info("reminder_check_started", count=len(users))

    for user in users:
        telegram_id = user["telegram_id"]
        first_name = user["first_name"] or "Trader"
        flow_type = user["flow_type"]
        reminder_num = user["reminder_count"] + 1

        # Build remind message based on flow type

        flow_messages = {
            "beginners": f"📗 your *{LABEL_BEGINNERS}* registration",
            "advanced": f"📚 your *{LABEL_ADVANCED}* registration",
            "swing": f"📉 your *{LABEL_SWING}* access",
            "vip_one_on_one": f"💎 your *One-on-One VIP Mentorship* booking",
            "vip_group": f"💎 your *Group VIP Mentorship* booking",
            "vip_signal": f"📈 your *VIP Signal* subscription",
            "different_broker": f"🔄 your *broker subscription* signup",
        }

        flow_label = flow_messages.get(flow_type, "your registration")

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"👋 Hey {first_name}!\n\n"
                    f"You started {flow_label} but didn't finish. 😊\n\n"
                    f"Tap below to pick up where you left off — "
                    f"it only takes a minute to complete! 🚀"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "▶️ Continue", callback_data="main_menu"
                            )
                        ],
                        [InlineKeyboardButton("🆘 Need Help?", url=MENTOR_CONTACT)],
                    ]
                ),
            )
            mark_reminded(telegram_id)
            logger.info(
                "reminder_sent",
                telegram_id=telegram_id,
                flow=flow_type,
                reminder_num=reminder_num,
            )

            # Stope after 3 reminders
            if reminder_num >= 20:
                clear_incomplete_flow(telegram_id)
                logger.info("reminder_limit_reached", telegram_id=telegram_id)

        except TelegramError as e:
            logger.error("reminder_failed", telegram_id=telegram_id, error=str(e))
            # if user blocked the bot, clear their record
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                clear_incomplete_flow(telegram_id)

        await asyncio.sleep(0.3)
    logger.info("reminder_check_complete", sent=len(users))
