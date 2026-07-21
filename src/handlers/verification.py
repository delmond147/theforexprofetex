"""
verification.py — Verification flow with session memory, admin notifications,
rate limiting, typing indicators, and onboarding follow-up.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from src.services.exness_client import exness
from src.handlers.keyboards import (
    back_to_menu,
    register_with_partner,
    account_not_found_options,
    change_partner_guide,
    verified_beginners,
    verified_advanced,
    verified_swing,
    onboarding,
    main_menu,
    vip_signal_packages,
    signal_payment_proof,
    different_broker_payment,
    vip_mentorship_packages,
    vip_payment_methods,
    pending_mt5_keyboard,
)

from src.core.settings import (
    PARTNER_LINK,
    MENTOR_CONTACT,
    VIP_PRICE,
    BEGINNERS_GROUP_LINK,
    ADVANCED_GROUP_LINK,
    SWING_TRADING_LINK,
    MENTOR_NAME,
    SIGNAL_PRICE_1MONTH,
    SIGNAL_PRICE_2MONTH,
    SIGNAL_PRICE_6MONTH,
    SIGNAL_PRICE_1YEAR,
    DIFFERENT_BROKER_PRICE,
    PAYMENT_DETAILS,
    VIP_ONE_ON_ONE_PRICE,
    VIP_GROUP_PRICE,
    PAYMENT_METHOD_1_NAME,
    PAYMENT_METHOD_1_BANK,
    PAYMENT_METHOD_1_ACCOUNT_NAME,
    PAYMENT_METHOD_1_ACCOUNT_NUMBER,
    PAYMENT_METHOD_2_NAME,
    PAYMENT_METHOD_2_NETWORK,
    PAYMENT_METHOD_2_NUMBER,
    PAYMENT_METHOD_2_ACCOUNT_NAME,
    PAYMENT_METHOD_3_NAME,
    PAYMENT_METHOD_3_NETWORK,
    PAYMENT_METHOD_3_WALLET,
    MT5_GRACE_DAYS,
    MT5_MIN_DEPOSIT,
    LABEL_BEGINNERS,
    LABEL_ADVANCED,
    LABEL_SWING,
)

from src.core.logging import logger
from src.db.database import (
    save_verification,
    log_failed_attempt,
    get_user,
    save_incomplete_flow,
    clear_incomplete_flow,
    set_mt5_pending,
    set_mt5_verified,
)
from src.middleware.rate_limit import is_rate_limited
from src.handlers.admin import (
    notify_admin,
    verified_message,
    failed_verification_message,
)

# ConversationHandler states
AWAITING_EMAIL = 1
AWAITING_REVERIFY_EMAIL = 2
AWAITING_SIGNAL_NAME = 3
AWAITING_SIGNAL_PHONE = 4
AWAITING_BROKER_NAME = 5
AWAITING_BROKER_PHONE = 6
AWAITING_VIP_NAME = 7
AWAITING_VIP_PHONE = 8
AWAITING_VIP_PAYMENT_METHOD = 9

# Configuration Key Constants
MENTORSHIP_KEY = "mentorship_type"

# Signal package mappings
SIGNAL_PACKAGE_LABELS = {
    "signal_1month": "1 Month",
    "signal_2month": "2 Months",
    "signal_6month": "6 Months",
    "signal_1year": "1 Year",
}

SIGNAL_PACKAGE_PRICES = {
    "signal_1month": SIGNAL_PRICE_1MONTH,
    "signal_2month": SIGNAL_PRICE_2MONTH,
    "signal_6month": SIGNAL_PRICE_6MONTH,
    "signal_1year": SIGNAL_PRICE_1YEAR,
}

SIGNAL_PACKAGE_KEY = "signal_package"


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Show typing indicator briefly before responding."""
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(0.8)


# ── MT5 status check callback ─────────────────────────────────────────────────


async def check_mt5_status_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User taps 'Check MT5 Status' — re-runs MT5 + funding check."""
    query = update.callback_query
    await query.answer()

    telegram_id = query.from_user.id
    db_user = get_user(telegram_id)

    if not db_user or not db_user["verified_email"]:
        await query.edit_message_text(
            "⚠️ No pending verification found. Please tap /start to begin.",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    email = db_user["verified_email"]
    mentorship = db_user["mentorship_type"] or "advanced"

    await query.edit_message_text(
        "⏳ Re-checking your MT5 account...",
        parse_mode="Markdown",
    )

    try:
        is_funded, mt5_account_id = await asyncio.wait_for(
            exness.check_mt5_funded(email, min_deposit=MT5_MIN_DEPOSIT),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.error("mt5_recheck_timeout", email=email)
        await query.edit_message_text(
            "⏳ The check is taking longer than expected. Please try again in a moment.",
            parse_mode="Markdown",
            reply_markup=pending_mt5_keyboard(),
        )
        return

    if is_funded and mt5_account_id:
        set_mt5_verified(telegram_id, mt5_account_id)

        await notify_admin(
            context.bot,
            verified_message(
                query.from_user.first_name,
                query.from_user.username,
                email,
                mentorship,
            ),
        )

        if mentorship == "beginners":
            group_word, success_kb, group_url = (
                LABEL_BEGINNERS,
                verified_beginners(),
                BEGINNERS_GROUP_LINK,
            )
        elif mentorship == "advanced":
            group_word, success_kb, group_url = (
                LABEL_ADVANCED,
                verified_advanced(),
                ADVANCED_GROUP_LINK,
            )
        else:
            group_word, success_kb, group_url = (
                LABEL_SWING,
                verified_swing(),
                SWING_TRADING_LINK,
            )

        await query.edit_message_text(
            (
                "🎉 *All checks passed! Welcome to {MENTOR_NAME}!*\n\n"
                "✅ Exness account linked\n"
                "✅ MT5 account active\n"
                "✅ Deposit confirmed\n\n"
                "Tap below to join your group 👇"
            ).format(MENTOR_NAME=MENTOR_NAME),
            parse_mode="Markdown",
            reply_markup=success_kb,
        )

        await asyncio.sleep(3)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "🎯 *Quick start guide:*\n\n"
                "1️⃣ Join your group using the button above\n"
                "2️⃣ Read the 📌 pinned message\n"
                "3️⃣ Review the group rules\n"
                "4️⃣ Check the weekly schedule\n\n"
                "Any questions? We've got you covered 👇"
            ),
            parse_mode="Markdown",
            reply_markup=onboarding(group_url),
        )

    else:
        await query.edit_message_text(
            "❌ *MT5 account not funded yet.*\n\n"
            "We still can't detect a funded MT5 account under your email.\n\n"
            "Please make sure you have:\n"
            "1️⃣ Created an MT5 account on Exness\n"
            "2️⃣ Deposited at least *$10*\n"
            "3️⃣ Placed at least one trade\n\n"
            "Then tap *Check MT5 Status* again. 👇",
            parse_mode="Markdown",
            reply_markup=pending_mt5_keyboard(),
        )


# ── Mentorship entry points ───────────────────────────────────────────────────


async def beginners_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data[MENTORSHIP_KEY] = "beginners"
    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "beginners",
    )

    db_user = get_user(query.from_user.id)
    if (
        db_user
        and db_user["verified_email"]
        and db_user["mentorship_type"] == "beginners"
    ):
        await query.edit_message_text(
            "✅ You're already verified for *Beginners Mentorship*!\n\n"
            "Tap below to go to your group 👇",
            parse_mode="Markdown",
            reply_markup=verified_beginners(),
        )
        return

    await query.edit_message_text(
        "📗 *Free Beginners Mentorship*\n\n"
        "Great choice! {MENTOR_NAME}'s beginners program covers everything "
        "you need to start trading with confidence — from the basics to your "
        "first live trade. 🚀\n\n"
        "To join, your Exness account must be under *{MENTOR_NAME}'s partner link*.\n\n"
        "Do you already have an Exness account?".format(MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=_registered_or_not_kb(),
    )


async def advanced_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data[MENTORSHIP_KEY] = "advanced"
    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "advanced",
    )

    db_user = get_user(query.from_user.id)
    if (
        db_user
        and db_user["verified_email"]
        and db_user["mentorship_type"] == "advanced"
    ):
        await query.edit_message_text(
            "✅ You're already verified for *Exness VIP Signals*!\n\n"
            "Tap below to go to your group 👇",
            parse_mode="Markdown",
            reply_markup=verified_advanced(),
        )
        return

    await query.edit_message_text(
        "📚 *EXNESS VIP SIGNAL SERVICE*\n\n"
        "Ready to go deeper? {MENTOR_NAME}'s Exness VIP group is the place for you!, "
        "A community to achieve consistent profitability. 📊\n\n"
        "To join, your Exness account must be under *{MENTOR_NAME}'s partner link*.\n\n"
        "Do you already have an Exness account?".format(MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=_registered_or_not_kb(),
    )


async def swing_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data[MENTORSHIP_KEY] = "swing"
    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "swing",
    )

    db_user = get_user(query.from_user.id)
    if db_user and db_user["verified_email"] and db_user["mentorship_type"] == "swing":
        await query.edit_message_text(
            "✅ You're already verified for *Swing Trading*!\n\n"
            "Tap below to go to your channel 👇",
            parse_mode="Markdown",
            reply_markup=verified_swing(),
        )
        return

    await query.edit_message_text(
        "📉 *Swing Trading Private Telegram*\n\n"
        "Get exclusive swing trade setups, entries, and analysis "
        "directly from {MENTOR_NAME}. 📊\n\n"
        "To join, your Exness account must be under "
        "*{MENTOR_NAME}'s partner link*.\n\n"
        "Do you already have an Exness account?".format(MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=_registered_or_not_kb(),
    )


def _registered_or_not_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, I have an Exness account",
                    callback_data="already_registered",
                )
            ],
            [
                InlineKeyboardButton(
                    "🆕 No, I'm new to Exness", callback_data="not_registered"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Using A Different Broker", callback_data="different_broker"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


# ── Not registered ────────────────────────────────────────────────────────────


async def not_registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🆕 *No worries, let's set you up!*\n\n"
        "Create your free Exness account using {MENTOR_NAME}'s link below. "
        "This links your account to the mentorship automatically. ✅\n\n"
        "Once registered, come back and tap *'I've registered — verify me'*.".format(
            MENTOR_NAME=MENTOR_NAME
        ),
        parse_mode="Markdown",
        reply_markup=register_with_partner(),
    )


# ── Already registered — ask for email ───────────────────────────────────────


async def already_registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📧 *What's your Exness registered email?*\n\n"
        "I'll verify your account is linked to {MENTOR_NAME}. "
        "Type your email below and hit send 👇".format(MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        ),
    )
    return AWAITING_EMAIL


# ── Receive and verify email ──────────────────────────────────────────────────


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    user = update.effective_user
    mentorship = context.user_data.get(MENTORSHIP_KEY, "beginners")

    # Rate limit check
    if is_rate_limited(user.id):
        await update.message.reply_text(
            "⏳ Too many attempts. Please wait 10 minutes and try again, "
            "or contact support if you need help.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🆘 Get Support", url=MENTOR_CONTACT)],
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Menu", callback_data="main_menu"
                        )
                    ],
                ]
            ),
        )
        return ConversationHandler.END

    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "⚠️ That doesn't look right. Please enter a valid email "
            "(e.g. `yourname@gmail.com`):",
            parse_mode="Markdown",
        )
        return AWAITING_EMAIL

    await _typing(context, update.effective_chat.id)
    await update.message.reply_text("⏳ Checking your account...")

    logger.info("verify_attempt", user_id=user.id, email=email, mentorship=mentorship)

    # Step 1: Affiliation check
    try:
        client = await asyncio.wait_for(
            exness.find_client_by_email(email),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.error("affiliation_check_timeout", email=email)
        await update.message.reply_text(
            "⏳ The check is taking too long. Please try again in a moment.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
            ),
        )
        return ConversationHandler.END

    if client:
        logger.info("verify_success", user_id=user.id, email=email)
        save_verification(user.id, email, mentorship)
        clear_incomplete_flow(user.id)

        await update.message.reply_text(
            "✅ *Account verified under {MENTOR_NAME}!*\n\n"
            "⏳ Now checking your MT5 trading account...".format(
                MENTOR_NAME=MENTOR_NAME
            ),
            parse_mode="Markdown",
        )

        # Step 2: MT5 + deposit check with timeout
        try:
            is_funded, mt5_account_id = await asyncio.wait_for(
                exness.check_mt5_funded(email, min_deposit=MT5_MIN_DEPOSIT),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.error("mt5_check_timeout", email=email)
            is_funded, mt5_account_id = False, None

        if is_funded and mt5_account_id:
            # ✅ Full verification passed
            set_mt5_verified(user.id, mt5_account_id)

            await notify_admin(
                context.bot,
                verified_message(user.first_name, user.username, email, mentorship),
            )

            if mentorship == "beginners":
                group_word, success_kb, group_url = (
                    LABEL_BEGINNERS,
                    verified_beginners(),
                    BEGINNERS_GROUP_LINK,
                )
            elif mentorship == "advanced":
                group_word, success_kb, group_url = (
                    LABEL_ADVANCED,
                    verified_advanced(),
                    ADVANCED_GROUP_LINK,
                )
            else:
                group_word, success_kb, group_url = (
                    LABEL_SWING,
                    verified_swing(),
                    SWING_TRADING_LINK,
                )

            await update.message.reply_text(
                (
                    "🎉 *All checks passed! Welcome to {MENTOR_NAME}!*\n\n"
                    "✅ Exness account linked\n"
                    "✅ MT5 account active\n"
                    "✅ Deposit confirmed\n\n"
                    "Tap below to join your group 👇"
                ).format(MENTOR_NAME=MENTOR_NAME),
                parse_mode="Markdown",
                reply_markup=success_kb,
            )

            await asyncio.sleep(3)
            await update.message.reply_text(
                "🎯 *Quick start guide:*\n\n"
                "1️⃣ Join your group using the button above\n"
                "2️⃣ Read the 📌 pinned message\n"
                "3️⃣ Review the group rules\n"
                "4️⃣ Check the weekly schedule\n\n"
                "Any questions? We've got you covered 👇",
                parse_mode="Markdown",
                reply_markup=onboarding(group_url),
            )

        else:
            # ⏳ MT5 not funded — set grace period
            deadline = (datetime.utcnow() + timedelta(days=MT5_GRACE_DAYS)).isoformat()
            set_mt5_pending(user.id, deadline)

            await notify_admin(
                context.bot,
                (
                    "⏳ *Pending MT5 Verification*\n\n"
                    f"👤 {user.first_name} (@{user.username or 'no username'})\n"
                    f"📧 {email}\n"
                    f"📋 Affiliation: ✅ Confirmed\n"
                    f"💻 MT5: ❌ Not found or not funded\n"
                    f"⏰ Deadline: {MT5_GRACE_DAYS} days"
                ),
            )

            # Check if MT5 exists but unfunded (use cached result from check_mt5_funded)
            try:
                accounts = await asyncio.wait_for(
                    exness.get_client_accounts(email),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                accounts = []

            has_mt5 = any(a.get("platform", "").lower() == "mt5" for a in accounts)

            if has_mt5:
                msg = (
                    "✅ *Exness account verified!*\n\n"
                    "⚠️ *Almost there!* We found your MT5 account but it "
                    "doesn't have any trading activity yet.\n\n"
                    "To complete your verification:\n"
                    "1️⃣ Log into your Exness Personal Area\n"
                    "2️⃣ Fund your MT5 account (minimum *$10*)\n"
                    "3️⃣ Place at least one trade\n\n"
                    f"⏰ You have *{MT5_GRACE_DAYS} days* to complete this.\n\n"
                    "Tap below to check your status once funded 👇"
                )
            else:
                msg = (
                    "✅ *Exness account verified!*\n\n"
                    "⚠️ *One more step required!*\n\n"
                    "You need to create an MT5 trading account on Exness "
                    "and make a deposit to complete your verification.\n\n"
                    "Here's how:\n"
                    "1️⃣ Log into your Exness Personal Area\n"
                    "2️⃣ Go to *My Accounts → Create Account*\n"
                    "3️⃣ Select *MT5* as the platform\n"
                    "4️⃣ Fund your account (minimum *$10*)\n"
                    "5️⃣ Place at least one trade\n\n"
                    f"⏰ You have *{MT5_GRACE_DAYS} days* to complete this.\n\n"
                    "Tap below to check your status once funded 👇"
                )

            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=pending_mt5_keyboard(),
            )

    else:
        logger.info("verify_not_found", user_id=user.id, email=email)
        log_failed_attempt(user.id, email)
        context.user_data["last_email"] = email

        await notify_admin(
            context.bot,
            failed_verification_message(user.first_name, user.username, email),
        )

        await update.message.reply_text(
            "🔍 We couldn't find `{email}` under {MENTOR_NAME}.\n\n"
            "Do you already have an Exness account with this email?".format(
                email=email, MENTOR_NAME=MENTOR_NAME
            ),
            parse_mode="Markdown",
            reply_markup=account_not_found_options(),
        )

    return ConversationHandler.END


# ── User confirms account exists but not linked ───────────────────────────────


async def has_account_not_linked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    last_email = context.user_data.get("last_email", "your account")

    await query.edit_message_text(
        "⚠️ *Looks like {last_email} is under a different partner.*\n\n"
        "No worries! Here's how to switch to {MENTOR_NAME}:\n\n"
        "1️⃣ Log in to your *Exness Personal Area*\n"
        "2️⃣ Go to *Profile → Live Chat*\n"
        "3️⃣ Type: `Change partner`\n"
        "4️⃣ Click the link the Exness bot sends\n"
        "5️⃣ Select *Rebate* as reason\n"
        "6️⃣ Paste this partner link:\n{PARTNER_LINK}\n\n"
        "Done? Tap below to verify again 👇".format(
            last_email=last_email,
            MENTOR_NAME=MENTOR_NAME,
            PARTNER_LINK=PARTNER_LINK,
        ),
        parse_mode="Markdown",
        reply_markup=change_partner_guide(),
    )


# ── Re-verify after partner change ────────────────────────────────────────────


async def reverify_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    last_email = context.user_data.get("last_email")
    mentorship = context.user_data.get(MENTORSHIP_KEY, "beginners")

    if last_email:
        await query.edit_message_text(
            "⏳ Re-checking `{last_email}`...".format(last_email=last_email),
            parse_mode="Markdown",
        )
        await _typing(context, query.message.chat_id)

        try:
            client = await asyncio.wait_for(
                exness.find_client_by_email(last_email),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            await query.edit_message_text(
                "⏳ Check timed out. Please try again.",
                parse_mode="Markdown",
                reply_markup=change_partner_guide(),
            )
            return ConversationHandler.END

        user = query.from_user

        if client:
            logger.info("reverify_success", user_id=user.id, email=last_email)
            context.user_data.pop("last_email", None)
            save_verification(user.id, last_email, mentorship)

            try:
                is_funded, mt5_account_id = await asyncio.wait_for(
                    exness.check_mt5_funded(last_email, min_deposit=MT5_MIN_DEPOSIT),
                    timeout=20.0,
                )
            except asyncio.TimeoutError:
                is_funded, mt5_account_id = False, None

            if is_funded and mt5_account_id:
                set_mt5_verified(user.id, mt5_account_id)
                await notify_admin(
                    context.bot,
                    verified_message(
                        user.first_name, user.username, last_email, mentorship
                    ),
                )

                if mentorship == "beginners":
                    group_word, success_kb, group_url = (
                        LABEL_BEGINNERS,
                        verified_beginners(),
                        BEGINNERS_GROUP_LINK,
                    )
                elif mentorship == "advanced":
                    group_word, success_kb, group_url = (
                        LABEL_ADVANCED,
                        verified_advanced(),
                        ADVANCED_GROUP_LINK,
                    )
                else:
                    group_word, success_kb, group_url = (
                        LABEL_SWING,
                        verified_swing(),
                        SWING_TRADING_LINK,
                    )

                await query.edit_message_text(
                    (
                        "🎉 *All checks passed! Welcome to {MENTOR_NAME}!*\n\n"
                        "✅ Exness account linked\n"
                        "✅ MT5 account active\n"
                        "✅ Deposit confirmed\n\n"
                        "Tap below to join your group 👇"
                    ).format(MENTOR_NAME=MENTOR_NAME),
                    parse_mode="Markdown",
                    reply_markup=success_kb,
                )

                await asyncio.sleep(3)
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=(
                        "🎯 *Quick start guide:*\n\n"
                        "1️⃣ Join your group using the button above\n"
                        "2️⃣ Read the 📌 pinned message\n"
                        "3️⃣ Review the group rules\n"
                        "4️⃣ Check the weekly schedule\n\n"
                        "Any questions? We've got you covered 👇"
                    ),
                    parse_mode="Markdown",
                    reply_markup=onboarding(group_url),
                )
            else:
                deadline = (
                    datetime.utcnow() + timedelta(days=MT5_GRACE_DAYS)
                ).isoformat()
                set_mt5_pending(user.id, deadline)
                await query.edit_message_text(
                    "✅ *Account re-verified!*\n\n"
                    "⚠️ MT5 account not funded yet.\n\n"
                    "Please fund your MT5 account (minimum *$10*) "
                    "and place at least one trade.\n\n"
                    f"⏰ You have *{MT5_GRACE_DAYS} days* to complete this.\n\n"
                    "Tap below to check your status once funded 👇",
                    parse_mode="Markdown",
                    reply_markup=pending_mt5_keyboard(),
                )
        else:
            logger.info("reverify_still_not_linked", user_id=user.id, email=last_email)
            await query.edit_message_text(
                "{last_email} still isn't showing under {MENTOR_NAME}.\n\n"
                "Partner changes can take a few minutes. "
                "Wait a bit and try again, or contact support if it persists.".format(
                    last_email=last_email, MENTOR_NAME=MENTOR_NAME
                ),
                parse_mode="Markdown",
                reply_markup=change_partner_guide(),
            )
        return ConversationHandler.END

    else:
        await query.edit_message_text(
            "📧 Enter your Exness email and I'll re-check:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
            ),
        )
        return AWAITING_REVERIFY_EMAIL


async def receive_reverify_email(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    email = update.message.text.strip()
    user = update.effective_user
    mentorship = context.user_data.get(MENTORSHIP_KEY, "beginners")

    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "⚠️ Please enter a valid email address:",
            parse_mode="Markdown",
        )
        return AWAITING_REVERIFY_EMAIL

    await _typing(context, update.effective_chat.id)
    await update.message.reply_text("⏳ Checking...")

    try:
        client = await asyncio.wait_for(
            exness.find_client_by_email(email),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⏳ Check timed out. Please try again.",
            reply_markup=change_partner_guide(),
        )
        return ConversationHandler.END

    if client:
        logger.info("reverify_success", user_id=user.id, email=email)
        save_verification(user.id, email, mentorship)

        try:
            is_funded, mt5_account_id = await asyncio.wait_for(
                exness.check_mt5_funded(email, min_deposit=MT5_MIN_DEPOSIT),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            is_funded, mt5_account_id = False, None

        if is_funded and mt5_account_id:
            set_mt5_verified(user.id, mt5_account_id)
            await notify_admin(
                context.bot,
                verified_message(user.first_name, user.username, email, mentorship),
            )

            if mentorship == "beginners":
                group_word, success_kb, group_url = (
                    LABEL_BEGINNERS,
                    verified_beginners(),
                    BEGINNERS_GROUP_LINK,
                )
            elif mentorship == "advanced":
                group_word, success_kb, group_url = (
                    LABEL_ADVANCED,
                    verified_advanced(),
                    ADVANCED_GROUP_LINK,
                )
            else:
                group_word, success_kb, group_url = (
                    LABEL_SWING,
                    verified_swing(),
                    SWING_TRADING_LINK,
                )

            await update.message.reply_text(
                (
                    "🎉 *All checks passed! Welcome to {MENTOR_NAME}!*\n\n"
                    "✅ Exness account linked\n"
                    "✅ MT5 account active\n"
                    "✅ Deposit confirmed\n\n"
                    "Tap below to join your group 👇"
                ).format(MENTOR_NAME=MENTOR_NAME),
                parse_mode="Markdown",
                reply_markup=success_kb,
            )
            await asyncio.sleep(3)
            await update.message.reply_text(
                "🎯 *Quick start guide:*\n\n"
                "1️⃣ Join your group using the button above\n"
                "2️⃣ Read the 📌 pinned message\n"
                "3️⃣ Review the group rules\n"
                "4️⃣ Check the weekly schedule\n\n"
                "Any questions? We've got you covered 👇",
                parse_mode="Markdown",
                reply_markup=onboarding(group_url),
            )
        else:
            deadline = (datetime.utcnow() + timedelta(days=MT5_GRACE_DAYS)).isoformat()
            set_mt5_pending(user.id, deadline)
            await update.message.reply_text(
                "✅ *Account verified!*\n\n"
                "⚠️ MT5 account not funded yet.\n\n"
                "Please fund your MT5 account (minimum *$10*) "
                "and place at least one trade.\n\n"
                f"⏰ You have *{MT5_GRACE_DAYS} days* to complete this.\n\n"
                "Tap below to check your status once funded 👇",
                parse_mode="Markdown",
                reply_markup=pending_mt5_keyboard(),
            )
    else:
        context.user_data["last_email"] = email
        log_failed_attempt(user.id, email)
        await update.message.reply_text(
            "{email} still isn't linked to {MENTOR_NAME}.\n\n"
            "Please wait a few minutes after the partner change and try again.".format(
                email=email, MENTOR_NAME=MENTOR_NAME
            ),
            parse_mode="Markdown",
            reply_markup=change_partner_guide(),
        )

    return ConversationHandler.END


# ── Re-entry: try a different email ──────────────────────────────────────────


async def restart_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📧 Enter your Exness registered email:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        ),
    )
    return AWAITING_EMAIL


# ── VIP Mentorship ────────────────────────────────────────────────────────────


async def vip_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show VIP package options."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        (
            "💎 *{MENTOR_NAME} VIP Mentorship*\n\n"
            "Take your trading to the next level with direct access "
            "to {MENTOR_NAME}. Choose your preferred package below 👇\n\n"
            "👤 *One-on-One* — {one_price}\n"
            "Personalised coaching sessions tailored just for you.\n\n"
            "👥 *Group Mentorship* — {group_price}\n"
            "Learn alongside other serious traders in a structured program."
        ).format(
            MENTOR_NAME=MENTOR_NAME,
            one_price=VIP_ONE_ON_ONE_PRICE,
            group_price=VIP_GROUP_PRICE,
        ),
        parse_mode="Markdown",
        reply_markup=vip_mentorship_packages(),
    )


async def vip_package_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """User selected a VIP package — collect their name."""
    query = update.callback_query
    await query.answer()

    package_key = query.data

    if package_key == "vip_one_on_one":
        package_label = "One-on-One Mentorship"
        package_price = VIP_ONE_ON_ONE_PRICE
    else:
        package_label = "Group Mentorship"
        package_price = VIP_GROUP_PRICE

    context.user_data["vip_package_key"] = package_key
    context.user_data["vip_package_label"] = package_label
    context.user_data["vip_package_price"] = package_price

    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        package_key,
    )

    await query.edit_message_text(
        (
            "💎 *{package_label}* — {package_price}\n\n"
            "Great choice! Let's get your details to proceed.\n\n"
            "What is your *full name*? 👇"
        ).format(
            package_label=package_label,
            package_price=package_price,
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        ),
    )
    return AWAITING_VIP_NAME


async def receive_vip_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive name, ask for phone number."""
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text("⚠️ Please enter your full name:")
        return AWAITING_VIP_NAME

    context.user_data["vip_name"] = name

    await update.message.reply_text(
        f"Thanks, {name}! 😊\n\n"
        "Now please share your *mobile number* (with country code):",
        parse_mode="Markdown",
    )
    return AWAITING_VIP_PHONE


async def receive_vip_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive phone, notify admin, ask for payment method."""
    phone = update.message.text.strip()
    user = update.effective_user

    if len(phone) < 6:
        await update.message.reply_text(
            "⚠️ Please enter a valid mobile number (with country code):"
        )
        return AWAITING_VIP_PHONE

    name = context.user_data.get("vip_name", "N/A")
    package_label = context.user_data.get("vip_package_label", "N/A")
    package_price = context.user_data.get("vip_package_price", "N/A")

    context.user_data["vip_phone"] = phone

    logger.info(
        "vip_mentorship_request",
        user_id=user.id,
        name=name,
        phone=phone,
        package=package_label,
    )

    await notify_admin(
        context.bot,
        (
            "💎 *New VIP Mentorship Request!*\n\n"
            f"👤 Name: {name}\n"
            f"📱 Phone: {phone}\n"
            f"📦 Package: {package_label}\n"
            f"💰 Price: {package_price}\n"
            f"🆔 Telegram: @{user.username or 'no username'}\n\n"
            "_Please follow up and confirm payment._"
        ),
    )

    await update.message.reply_text(
        (
            "✅ *Got it, {name}!*\n\n"
            "📦 *Package:* {package_label}\n"
            "💰 *Price:* {package_price}\n\n"
            "How would you like to make your payment? "
            "Choose a method below 👇"
        ).format(
            name=name,
            package_label=package_label,
            package_price=package_price,
        ),
        parse_mode="Markdown",
        reply_markup=vip_payment_methods(),
    )
    return AWAITING_VIP_PAYMENT_METHOD


async def receive_vip_payment_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """User selected a payment method — send each detail as a copyable field."""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    method_key = query.data
    name = context.user_data.get("vip_name", "N/A")
    package_label = context.user_data.get("vip_package_label", "N/A")
    package_price = context.user_data.get("vip_package_price", "N/A")
    chat_id = query.message.chat_id

    if method_key == "vip_payment_method_1":
        method_name = PAYMENT_METHOD_1_NAME
        fields = [
            ("🏦 Bank", PAYMENT_METHOD_1_BANK),
            ("👤 Account Name", PAYMENT_METHOD_1_ACCOUNT_NAME),
            ("🔢 Account Number", PAYMENT_METHOD_1_ACCOUNT_NUMBER),
        ]
    elif method_key == "vip_payment_method_2":
        method_name = PAYMENT_METHOD_2_NAME
        fields = [
            ("📡 Network", PAYMENT_METHOD_2_NETWORK),
            ("👤 Name", PAYMENT_METHOD_2_ACCOUNT_NAME),
            ("📱 Number", PAYMENT_METHOD_2_NUMBER),
        ]
    elif method_key == "vip_payment_method_3":
        method_name = PAYMENT_METHOD_3_NAME
        fields = [
            ("🌐 Network", PAYMENT_METHOD_3_NETWORK),
            ("🪙 Wallet Address", PAYMENT_METHOD_3_WALLET),
        ]
    else:
        await query.edit_message_text(
            "⚠️ Invalid payment method. Please try again.",
            reply_markup=vip_payment_methods(),
        )
        return AWAITING_VIP_PAYMENT_METHOD

    await notify_admin(
        context.bot,
        (
            "💳 *VIP Payment Method Selected*\n\n"
            f"👤 {name} (@{user.username or 'no username'})\n"
            f"📦 {package_label} — {package_price}\n"
            f"💳 Method: {method_name}\n\n"
            "_Awaiting payment proof._"
        ),
    )

    clear_incomplete_flow(user.id)

    await query.edit_message_text(
        (
            "💳 *{method_name} Payment Details*\n\n"
            "📦 *Package:* {package_label}\n"
            "💰 *Amount:* {package_price}\n\n"
            "Tap any value below to copy it instantly 👇"
        ).format(
            method_name=method_name,
            package_label=package_label,
            package_price=package_price,
        ),
        parse_mode="Markdown",
    )

    for label, value in fields:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{label}\n`{value}`",
            parse_mode="Markdown",
        )
        await asyncio.sleep(0.3)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"💰 Amount\n`{package_price}`",
        parse_mode="Markdown",
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ Once payment is made, tap below to send your proof to "
            f"*{MENTOR_NAME}*. You'll be onboarded within 24 hours. 🎉"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📩 Send Payment Proof", url=MENTOR_CONTACT)],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
            ]
        ),
    )

    return ConversationHandler.END


# ── Different Broker Flow ─────────────────────────────────────────────────────


async def different_broker_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text=(
            "🔄 *Using a Different Broker?*\n\n"
            "No problem! You can still join the {MENTOR_NAME} VIP group "
            "with your current broker.\n\n"
            "💰 *Monthly Subscription Fee:* {price}/month\n\n"
            "This gives you full access to:\n"
            "• VIP trade signals 📈\n"
            "• Exclusive education materials 📚\n"
            "• {MENTOR_NAME} community support 👥\n\n"
            "Tap below to proceed with payment 👇"
        ).format(MENTOR_NAME=MENTOR_NAME, price=DIFFERENT_BROKER_PRICE),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"💳 Subscribe — {DIFFERENT_BROKER_PRICE}/month",
                        callback_data="broker_subscribe",
                    )
                ],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
            ]
        ),
    )


async def broker_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "different_broker",
    )

    await query.edit_message_text(
        "📝 *Subscription Details*\n\n"
        "Please share a few details to proceed.\n\n"
        "What's your *full name*?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        ),
    )
    return AWAITING_BROKER_NAME


async def receive_broker_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text("⚠️ Please enter your full name:")
        return AWAITING_BROKER_NAME

    context.user_data["broker_name"] = name

    await update.message.reply_text(
        f"Thanks, {name}! 😊\n\n"
        "Now please share your *mobile number* (with country code):",
        parse_mode="Markdown",
    )
    return AWAITING_BROKER_PHONE


async def receive_broker_phone(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    phone = update.message.text.strip()
    user = update.effective_user

    if len(phone) < 6:
        await update.message.reply_text(
            "⚠️ Please enter a valid mobile number (with country code):"
        )
        return AWAITING_BROKER_PHONE

    name = context.user_data.get("broker_name", "N/A")

    logger.info("broker_subscription_request", user_id=user.id, name=name, phone=phone)

    await notify_admin(
        context.bot,
        (
            "🔄 *New Different Broker Subscription Request!*\n\n"
            f"👤 Name: {name}\n"
            f"📱 Phone: {phone}\n"
            f"💰 Fee: {DIFFERENT_BROKER_PRICE}/month\n"
            f"🆔 Telegram: @{user.username or 'no username'}\n\n"
            "_Please verify payment and add to VIP group._"
        ),
    )

    await update.message.reply_text(
        (
            "✅ *Thanks {name}!*\n\n"
            "Here are the payment details for your "
            "*{price}/month* subscription:\n\n"
            "{payment_details}\n\n"
            "📲 Once payment is made, tap below to send your proof. "
            "{MENTOR_NAME} will verify and add you to the VIP group "
            "within 24 hours. 🎉"
        ).format(
            name=name,
            price=DIFFERENT_BROKER_PRICE,
            payment_details=PAYMENT_DETAILS,
            MENTOR_NAME=MENTOR_NAME,
        ),
        parse_mode="Markdown",
        reply_markup=different_broker_payment(),
    )
    clear_incomplete_flow(user.id)
    return ConversationHandler.END


# ── VIP Signal Subscription ───────────────────────────────────────────────────


async def vip_signal_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        (
            "📈 *{MENTOR_NAME} VIP Signal*\n\n"
            "Get daily trade signals straight to your phone — entries, "
            "stop loss, and take profit, sent in real time. 🔥\n\n"
            "Choose your subscription plan below 👇"
        ).format(MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=vip_signal_packages(),
    )


async def signal_package_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    package_key = query.data

    package_label = SIGNAL_PACKAGE_LABELS.get(package_key)
    if not package_label:
        clean_key = package_key.lower()
        if "1month" in clean_key:
            package_label = "1 Month"
        elif "2month" in clean_key:
            package_label = "2 Months"
        elif "6month" in clean_key:
            package_label = "6 Months"
        elif "1year" in clean_key:
            package_label = "1 Year"
        else:
            package_label = package_key.replace("_", " ").title()

    package_price = SIGNAL_PACKAGE_PRICES.get(package_key, SIGNAL_PRICE_1MONTH)

    context.user_data[SIGNAL_PACKAGE_KEY] = package_label
    context.user_data["signal_package_price"] = package_price

    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "vip_signal",
    )

    await query.edit_message_text(
        f"📋 *Subscription Details*\n"
        f"📦 *Plan:* {package_label}\n"
        f"💰 *Price:* {package_price}\n\n"
        f"To proceed, please answer the questions below.\n\n"
        f"What is your *full name*? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❌ Cancel Registration", callback_data="main_menu"
                    )
                ]
            ]
        ),
    )
    return AWAITING_SIGNAL_NAME


async def receive_signal_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text("⚠️ Please enter a valid full name:")
        return AWAITING_SIGNAL_NAME

    context.user_data["signal_name"] = name

    await update.message.reply_text(
        f"Thanks, {name}! 😊\n\n"
        "Now please share your *mobile number* (with country code):",
        parse_mode="Markdown",
    )
    return AWAITING_SIGNAL_PHONE


async def receive_signal_phone(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    phone = update.message.text.strip()
    user = update.effective_user

    if len(phone) < 6:
        await update.message.reply_text(
            "⚠️ Please enter a valid phone number (with country code):"
        )
        return AWAITING_SIGNAL_PHONE

    name = context.user_data.get("signal_name", "N/A")
    package_label = context.user_data.get(SIGNAL_PACKAGE_KEY, "N/A")

    logger.info(
        "signal_subscription_request",
        user_id=user.id,
        name=name,
        phone=phone,
        package=package_label,
    )

    await notify_admin(
        context.bot,
        (
            "📈 *New VIP Signal Subscription Request!*\n\n"
            f"👤 Name: {name}\n"
            f"📱 Phone: {phone}\n"
            f"💼 Package: {package_label}\n"
            f"🆔 Telegram: @{user.username or 'no username'}\n"
        ),
    )

    await update.message.reply_text(
        (
            "✅ *Thanks {name}!*\n\n"
            "Here are the payment details for your *{package_label}* plan:\n\n"
            "{payment_details}\n\n"
            "📲 Once you've made the payment, tap below to send your proof. "
            "You'll be added to the signal group shortly after confirmation. 🎉"
        ).format(
            name=name,
            package_label=package_label,
            payment_details=PAYMENT_DETAILS,
        ),
        parse_mode="Markdown",
        reply_markup=signal_payment_proof(),
    )
    clear_incomplete_flow(user.id)
    return ConversationHandler.END


# ── Cancel fallback ───────────────────────────────────────────────────────────


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user:
        clear_incomplete_flow(update.effective_user.id)
    await update.message.reply_text(
        "No problem! Tap /start whenever you're ready. 😊",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END
