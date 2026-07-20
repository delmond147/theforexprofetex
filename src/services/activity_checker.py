"""
activity_checker.py — Scheduled jobs:
1. Daily activity check + partner switch detection
2. MT5 verification check (every 6 hours)
3. Incomplete flow reminders (every 4 hours)
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from src.core.settings import (
    ADMIN_CHAT_ID,
    VIP_GROUP_ID,
    INACTIVITY_DAYS,
    WARNING_DAYS,
    MENTOR_NAME,
    MENTOR_CONTACT,
    LABEL_BEGINNERS,
    LABEL_ADVANCED,
    LABEL_SWING,
    MT5_GRACE_DAYS,
    MT5_MIN_DEPOSIT,
    PARTNER_SWITCH_WARNING_HOURS,
    BEGINNERS_GROUP_LINK,
    ADVANCED_GROUP_LINK,
    SWING_TRADING_LINK,
)
from src.db.database import (
    get_all_verified_users,
    get_warned_users_past_deadline,
    get_pending_mt5_users,
    get_deadline_exceeded_mt5_users,
    get_partner_switch_removal_due,
    get_users_to_remind,
    mark_warning_sent,
    mark_removed,
    mark_active,
    mark_inactive,
    mark_partner_switch_warned,
    mark_reminded,
    clear_incomplete_flow,
    set_mt5_verified,
)
from src.services.exness_client import exness
from src.core.logging import logger

# ── Helpers ───────────────────────────────────────────────────────────────────


async def notify_admin_message(bot: Bot, message: str) -> None:
    """Send notification to admin."""
    if not ADMIN_CHAT_ID:
        return
    try:
        await bot.send_message(
            chat_id=int(ADMIN_CHAT_ID),
            text=message,
            parse_mode="Markdown",
        )
    except TelegramError as e:
        logger.error("admin_notify_failed", error=str(e))


async def check_user_activity(email: str) -> tuple[bool, str | None]:
    """
    Check if a client has traded in the last INACTIVITY_DAYS.
    Returns (is_active, last_trade_date).
    """
    try:
        results = await exness.get_client_accounts(email)
        if not results:
            return False, None

        latest_trade = None
        for account in results:
            trade_date = account.get("client_account_last_trade")
            if trade_date:
                if not latest_trade or trade_date > latest_trade:
                    latest_trade = trade_date

        if not latest_trade:
            return False, None

        trade_dt = datetime.fromisoformat(latest_trade)
        now = (
            datetime.now(timezone.utc)
            if trade_dt.tzinfo is not None
            else datetime.utcnow()
        )
        days_since = (now - trade_dt).days
        return days_since <= INACTIVITY_DAYS, latest_trade

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
                f"If no activity is detected, your access will be removed automatically.\n\n"
                f"Need help getting back on track? Tap below 👇"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🆘 Contact Support", url=MENTOR_CONTACT)],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]
            ),
        )
        return True
    except TelegramError as e:
        logger.error("warning_send_failed", telegram_id=telegram_id, error=str(e))
        return False


async def remove_user(bot: Bot, telegram_id: int, first_name: str, email: str) -> None:
    """Remove user — notify them, kick from group, update DB."""
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=(
                f"❌ *Access Removed*\n\n"
                f"Hi {first_name}, your access to the {MENTOR_NAME} VIP group "
                f"has been removed.\n\n"
                f"To regain access, tap /start and go through verification again. 📈"
            ),
            parse_mode="Markdown",
        )
    except TelegramError:
        pass

    if VIP_GROUP_ID:
        try:
            await bot.ban_chat_member(
                chat_id=int(VIP_GROUP_ID),
                user_id=telegram_id,
            )
            await asyncio.sleep(1)
            await bot.unban_chat_member(
                chat_id=int(VIP_GROUP_ID),
                user_id=telegram_id,
            )
            logger.info("user_kicked_from_group", telegram_id=telegram_id)
        except TelegramError as e:
            logger.error("kick_failed", telegram_id=telegram_id, error=str(e))

    mark_removed(telegram_id)
    logger.info("user_removed", telegram_id=telegram_id, email=email)


# ── Main scheduled jobs ───────────────────────────────────────────────────────


async def run_activity_check(bot: Bot) -> None:
    """
    Daily job at 3AM UTC:
    1. Remove users past partner switch 24h deadline
    2. Remove users past inactivity warning deadline
    3. Check all verified users for partner switch
    4. Check all verified users for trading activity
    5. Send admin summary
    """
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    logger.info("activity_check_started", time=now)

    warned_count = 0
    removed_count = 0
    inactive_count = 0
    active_count = 0
    switched_count = 0
    removal_list = []

    # ── Step 1: Remove users past partner switch deadline ─────────────────────
    for user in get_partner_switch_removal_due():
        await remove_user(
            bot,
            user["telegram_id"],
            user["first_name"] or "Trader",
            user["verified_email"],
        )
        removal_list.append(
            f"• {user['first_name']} (@{user['username'] or 'no username'}) "
            f"— partner switch — {user['verified_email']}"
        )
        removed_count += 1
        await asyncio.sleep(0.5)

    # ── Step 2: Remove users past inactivity warning deadline ─────────────────
    for user in get_warned_users_past_deadline(WARNING_DAYS):
        await remove_user(
            bot,
            user["telegram_id"],
            user["first_name"] or "Trader",
            user["verified_email"],
        )
        removal_list.append(
            f"• {user['first_name']} (@{user['username'] or 'no username'}) "
            f"— inactive — {user['verified_email']}"
        )
        removed_count += 1
        await asyncio.sleep(0.5)

    # ── Step 3: Check all verified users ─────────────────────────────────────
    verified_users = get_all_verified_users()

    for user in verified_users:
        telegram_id = user["telegram_id"]
        email = user["verified_email"]
        first_name = user["first_name"] or "Trader"

        # Partner switch check
        affiliation = await exness.check_partner_affiliation(email)
        still_linked = (
            isinstance(affiliation, dict) and affiliation.get("affiliation") is True
        )

        if not still_linked:
            if not user["partner_switch_warned_at"]:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=(
                            f"⚠️ *Important Notice from {MENTOR_NAME}*\n\n"
                            f"Hi {first_name}! 👋\n\n"
                            f"We detected that your Exness account is no longer "
                            f"linked under {MENTOR_NAME}.\n\n"
                            f"Please switch back within "
                            f"*{PARTNER_SWITCH_WARNING_HOURS} hours* "
                            f"to keep your group access.\n\n"
                            f"If no action is taken you will be automatically removed."
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "🔗 Switch Back to Partner", url=MENTOR_CONTACT
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        "✅ I've switched back — verify me",
                                        callback_data="already_registered",
                                    )
                                ],
                            ]
                        ),
                    )
                    mark_partner_switch_warned(telegram_id)
                    switched_count += 1
                    logger.info(
                        "partner_switch_warning_sent",
                        telegram_id=telegram_id,
                        email=email,
                    )
                except TelegramError as e:
                    logger.error(
                        "partner_switch_warn_failed",
                        telegram_id=telegram_id,
                        error=str(e),
                    )
            continue  # skip activity check for switched users

        # Activity check
        is_active, last_trade = await check_user_activity(email)

        if is_active:
            mark_active(telegram_id, last_trade or "unknown")
            active_count += 1
        else:
            mark_inactive(telegram_id)
            inactive_count += 1
            if not user["warning_sent_at"]:
                sent = await send_warning(bot, telegram_id, first_name)
                if sent:
                    mark_warning_sent(telegram_id)
                    warned_count += 1

        await asyncio.sleep(0.3)

    # ── Step 4: Admin summary ─────────────────────────────────────────────────
    if ADMIN_CHAT_ID:
        summary = (
            f"📊 *Daily Activity Check Complete*\n\n"
            f"🕐 {now}\n\n"
            f"✅ Active: {active_count}\n"
            f"⚠️ Partner switch warnings: {switched_count}\n"
            f"⚠️ Inactivity warnings: {warned_count}\n"
            f"❌ Removed: {removed_count}\n"
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
        switched=switched_count,
    )


async def run_mt5_check(bot: Bot) -> None:
    """
    Every 6 hours:
    - Remove users whose MT5 grace period has expired
    - Grant access to users who have now funded their MT5
    """
    logger.info("mt5_check_started")
    granted = 0
    removed = 0

    # Remove users past MT5 deadline
    for user in get_deadline_exceeded_mt5_users():
        telegram_id = user["telegram_id"]
        first_name = user["first_name"] or "Trader"
        email = user["verified_email"]

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"❌ *Access Removed — MT5 Verification Incomplete*\n\n"
                    f"Hi {first_name}, your {MT5_GRACE_DAYS}-day window to "
                    f"create and fund your MT5 account has passed.\n\n"
                    f"To regain access:\n"
                    f"1️⃣ Create an MT5 account on Exness\n"
                    f"2️⃣ Fund it with minimum $10\n"
                    f"3️⃣ Place at least one trade\n"
                    f"4️⃣ Tap /start to verify again 📈"
                ),
                parse_mode="Markdown",
            )
        except TelegramError:
            pass

        mark_removed(telegram_id)
        removed += 1

        await notify_admin_message(
            bot,
            (
                f"❌ *MT5 Deadline Passed — User Removed*\n\n"
                f"👤 {first_name} (@{user['username'] or 'no username'})\n"
                f"📧 {email}\n"
                f"⏰ Did not create/fund MT5 within {MT5_GRACE_DAYS} days"
            ),
        )
        await asyncio.sleep(0.5)

    # Check pending users who might now be funded
    for user in get_pending_mt5_users():
        telegram_id = user["telegram_id"]
        email = user["verified_email"]
        first_name = user["first_name"] or "Trader"
        mentorship = user["mentorship_type"] or "advanced"

        is_funded, mt5_account_id = await exness.check_mt5_funded(
            email, min_deposit=MT5_MIN_DEPOSIT
        )

        if is_funded and mt5_account_id:
            set_mt5_verified(telegram_id, mt5_account_id)

            group_url = {
                "beginners": BEGINNERS_GROUP_LINK,
                "advanced": ADVANCED_GROUP_LINK,
                "swing": SWING_TRADING_LINK,
            }.get(mentorship, ADVANCED_GROUP_LINK)

            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"🎉 *MT5 Verification Complete!*\n\n"
                        f"Hi {first_name}! Your MT5 account is now active "
                        f"and funded. You're all set! ✅\n\n"
                        f"Tap below to join your group 👇"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("🎉 Join Group", url=group_url)],
                            [
                                InlineKeyboardButton(
                                    "🏠 Main Menu", callback_data="main_menu"
                                )
                            ],
                        ]
                    ),
                )
                granted += 1
            except TelegramError as e:
                logger.error("mt5_grant_failed", telegram_id=telegram_id, error=str(e))

            await notify_admin_message(
                bot,
                (
                    f"✅ *MT5 Verified — Group Access Granted*\n\n"
                    f"👤 {first_name} (@{user['username'] or 'no username'})\n"
                    f"📧 {email}\n"
                    f"💻 MT5 Account: {mt5_account_id}"
                ),
            )

        await asyncio.sleep(0.3)

    logger.info("mt5_check_complete", granted=granted, removed=removed)


async def run_reminder_check(bot: Bot) -> None:
    """
    Every 4 hours:
    Sends reminders to users who started a flow but didn't complete it.
    Stops after 7 days (42 reminders at 4-hour intervals).
    """
    users = get_users_to_remind(hours=4, max_reminders=42)
    logger.info("reminder_check_started", count=len(users))

    flow_messages = {
        "beginners": f"📗 your *{LABEL_BEGINNERS}* registration",
        "advanced": f"📚 your *{LABEL_ADVANCED}* registration",
        "swing": f"📉 your *{LABEL_SWING}* access",
        "vip_one_on_one": f"💎 your *One-on-One VIP Mentorship* booking",
        "vip_group": f"💎 your *Group VIP Mentorship* booking",
        "vip_signal": f"📈 your *VIP Signal* subscription",
        "different_broker": f"🔄 your *broker subscription* signup",
    }

    for user in users:
        telegram_id = user["telegram_id"]
        first_name = user["first_name"] or "Trader"
        flow_type = user["flow_type"]
        reminder_num = user["reminder_count"] + 1

        flow_label = flow_messages.get(flow_type, "your registration")

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"👋 Hey {first_name}!\n\n"
                    f"You started {flow_label} but didn't finish. 😊\n\n"
                    f"Tap below to pick up where you left off — "
                    f"it only takes a minute! 🚀"
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

            if reminder_num >= 42:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=(
                            f"👋 Hey {first_name}, this is our last reminder.\n\n"
                            f"Whenever you're ready, just tap /start "
                            f"and we'll be right here. 😊📈"
                        ),
                    )
                except TelegramError:
                    pass
                clear_incomplete_flow(telegram_id)
                logger.info("reminder_limit_reached", telegram_id=telegram_id)

        except TelegramError as e:
            logger.error("reminder_failed", telegram_id=telegram_id, error=str(e))
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                clear_incomplete_flow(telegram_id)

        await asyncio.sleep(0.3)

    logger.info("reminder_check_complete", count=len(users))
