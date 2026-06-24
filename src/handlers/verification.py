"""
verification.py — Verification flow with session memory, admin notifications,
rate limiting, typing indicators, and onboarding follow-up.
"""

from __future__ import annotations
import asyncio
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
)

from src.core.settings import (
    PARTNER_LINK,
    MENTOR_CONTACT,
    VIP_PRICE,
    BEGINNERS_GROUP_LINK,
    ADVANCED_GROUP_LINK,
    SWING_TRADING_LINK,
    MENTOR_NAME,  # FIXED: Imported MENTOR_NAME to resolve NameErrors
    PAYMENT_DETAILS,
    SIGNAL_PRICE_1MONTH,
    SIGNAL_PRICE_2MONTH,
    SIGNAL_PRICE_6MONTH,
    SIGNAL_PRICE_1YEAR,
    DIFFERENT_BROKER_PRICE,
    VIP_ONE_ON_ONE_PRICE,
    VIP_GROUP_PRICE,
    VIP_ONE_ON_ONE_PAYMENT_LINK,
    VIP_GROUP_PAYMENT_LINK,
)

from src.core.logging import logger
from src.db.database import (
    save_verification,
    log_failed_attempt,
    get_user,
    save_incomplete_flow,
    clear_incomplete_flow,
)
from src.middleware.rate_limit import is_rate_limited
from src.handlers.admin import (
    notify_admin,
    verified_message,
    failed_verification_message,
    # vip_inquiry_message,
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

# Configuration Key Constants
MENTORSHIP_KEY = "mentorship_type"


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Show typing indicator briefly before responding."""
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(0.8)


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

    # Check if already verified
    db_user = get_user(query.from_user.id)
    if (
        db_user
        and db_user["verified_email"]
        and db_user["mentorship_type"] == "beginners"
    ):
        await query.edit_message_text(
            f"✅ You're already verified for *Beginners Mentorship*!\n\n"
            f"Tap below to go to your group 👇",
            parse_mode="Markdown",
            reply_markup=verified_beginners(),
        )
        return

    # FIXED: Wrapped string in .format() call to handle multi-tenant configuration variables
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
            f"✅ You're already verified for *Exness VIP Signals*!\n\n"
            f"Tap below to go to your group 👇",
            parse_mode="Markdown",
            reply_markup=verified_advanced(),
        )
        return

    # FIXED: Configured message layout formatting for modular deployments
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

    # FIXED: Extracted MENTOR_NAME via layout parsing pipeline
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
                    "🔄 Using A Different Broker",
                    callback_data="different_broker_entry",
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


# ── Not registered ────────────────────────────────────────────────────────────


async def not_registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # FIXED: Added variable parsing for dynamic affiliate setup
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

    # FIXED: Integrated programmatic variable injection
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

    # Typing indicator
    await _typing(context, update.effective_chat.id)
    await update.message.reply_text("⏳ Checking your account...")

    logger.info("verify_attempt", user_id=user.id, email=email, mentorship=mentorship)
    client = await exness.find_client_by_email(email)

    if client:
        logger.info("verify_success", user_id=user.id, email=email)

        # Save to DB
        save_verification(user.id, email, mentorship)
        clear_incomplete_flow(user.id)

        # Notify admin
        await notify_admin(
            context.bot,
            verified_message(user.first_name, user.username, email, mentorship),
        )

        if mentorship == "beginners":
            group_word, success_kb, group_url = (
                "Beginners",
                verified_beginners(),
                BEGINNERS_GROUP_LINK,
            )
        elif mentorship == "advanced":
            group_word, success_kb, group_url = (
                "EXNESS VIP SIGNALS",
                verified_advanced(),
                ADVANCED_GROUP_LINK,
            )
        else:
            group_word, success_kb, group_url = (
                "Swing Trading",
                verified_swing(),
                SWING_TRADING_LINK,
            )

        # FIXED: Added structural format engine parsing to ensure names render correctly
        await update.message.reply_text(
            "✅ *Verified! Welcome to {MENTOR_NAME} {group_word} Mentorship!*\n\n"
            "Your Exness account (`{email}`) is linked to {MENTOR_NAME}. 🎉\n\n"
            "Now login to your exness and create a new trading account\n\n"
            "Deposit funds to trade my signals else you'll be kicked out of the group\n\n"
            "Tap below to join your group and start learning!".format(
                MENTOR_NAME=MENTOR_NAME, group_word=group_word, email=email
            ),
            parse_mode="Markdown",
            reply_markup=success_kb,
        )

        # Onboarding follow-up after short delay
        await asyncio.sleep(3)
        await update.message.reply_text(
            "🎯 *Quick start guide for you:*\n\n"
            "1️⃣ Join your group using the button above\n"
            "2️⃣ Read the 📌 pinned message in the group\n"
            "3️⃣ Review the group rules and guidelines\n"
            "4️⃣ Check the weekly class schedule\n\n"
            "Any questions? We've got you covered 👇",
            parse_mode="Markdown",
            reply_markup=onboarding(group_url),
        )

    else:
        logger.info("verify_not_found", user_id=user.id, email=email)
        log_failed_attempt(user.id, email)
        context.user_data["last_email"] = email

        # Notify admin of failed attempt
        await notify_admin(
            context.bot,
            failed_verification_message(user.first_name, user.username, email),
        )

        # FIXED: Injected dynamic variable parsing for global multi-client tracking
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

    # FIXED: Resolved layout variable placeholders
    await query.edit_message_text(
        f"⚠️ *Looks like `{last_email}` is under a different partner.*\n\n"
        "No worries! Here's how to switch to {MENTOR_NAME}:\n\n"
        "1️⃣ Log in to your *Exness Personal Area*\n"
        "2️⃣ Go to *Profile → Live Chat*\n"
        "3️⃣ Type: `Change partner`\n"
        "4️⃣ Click the link the Exness bot sends\n"
        '5️⃣ Select *"Rebate"* as reason\n'
        f"6️⃣ Paste this partner link:\n`{PARTNER_LINK}`\n\n"
        "Done? Tap below to verify again 👇".format(MENTOR_NAME=MENTOR_NAME),
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
            f"⏳ Re-checking `{last_email}`...",
            parse_mode="Markdown",
        )
        await _typing(context, query.message.chat_id)
        client = await exness.find_client_by_email(last_email)
        user = query.from_user

        if client:
            logger.info("reverify_success", user_id=user.id, email=last_email)
            save_verification(user.id, last_email, mentorship)
            await notify_admin(
                context.bot,
                verified_message(
                    user.first_name, user.username, last_email, mentorship
                ),
            )
            group_word = "Beginners" if mentorship == "beginners" else "Advanced"
            group_url = (
                BEGINNERS_GROUP_LINK
                if mentorship == "beginners"
                else ADVANCED_GROUP_LINK
            )
            success_kb = (
                verified_beginners()
                if mentorship == "beginners"
                else verified_advanced()
            )
            context.user_data.pop("last_email", None)

            # FIXED: Formatted output mapping rules
            await query.edit_message_text(
                "✅ *All set! Welcome to {MENTOR_NAME} {group_word} Mentorship!*\n\n"
                "`{last_email}` is now linked to {MENTOR_NAME}. 🎉\n\n"
                "Tap below to join your group!".format(
                    MENTOR_NAME=MENTOR_NAME,
                    group_word=group_word,
                    last_email=last_email,
                ),
                parse_mode="Markdown",
                reply_markup=success_kb,
            )

            await asyncio.sleep(3)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "🎯 *Quick start guide for you:*\n\n"
                    "1️⃣ Join your group using the button above\n"
                    "2️⃣ Read the 📌 pinned message in the group\n"
                    "3️⃣ Introduce yourself to the community\n"
                    "4️⃣ Check the weekly class schedule\n\n"
                    "Any questions? We've got you covered 👇"
                ),
                parse_mode="Markdown",
                reply_markup=onboarding(group_url),
            )
        else:
            logger.info("reverify_still_not_linked", user_id=user.id, email=last_email)
            # FIXED: Injected config metrics parameters dynamically
            await query.edit_message_text(
                "❌ `{last_email}` still isn't showing under {MENTOR_NAME}.\n\n"
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
    client = await exness.find_client_by_email(email)

    if client:
        logger.info("reverify_success", user_id=user.id, email=email)
        save_verification(user.id, email, mentorship)
        await notify_admin(
            context.bot,
            verified_message(user.first_name, user.username, email, mentorship),
        )
        group_word = "Beginners" if mentorship == "beginners" else "Advanced"
        group_url = (
            BEGINNERS_GROUP_LINK if mentorship == "beginners" else ADVANCED_GROUP_LINK
        )
        success_kb = (
            verified_beginners() if mentorship == "beginners" else verified_advanced()
        )

        # FIXED: Swapped raw placeholders via explicit parsing calls
        await update.message.reply_text(
            "✅ *Verified! Welcome to {MENTOR_NAME} {group_word} Mentorship!*\n\n"
            "Tap below to join your group! 🎉".format(
                MENTOR_NAME=MENTOR_NAME, group_word=group_word
            ),
            parse_mode="Markdown",
            reply_markup=success_kb,
        )
        await asyncio.sleep(3)
        await update.message.reply_text(
            "🎯 *Quick start guide for you:*\n\n"
            "1️⃣ Join your group using the button above\n"
            "2️⃣ Read the 📌 pinned message in the group\n"
            "3️⃣ Introduce yourself to the community\n"
            "4️⃣ Check the weekly class schedule\n\n"
            "Any questions? We've got you covered 👇",
            parse_mode="Markdown",
            reply_markup=onboarding(group_url),
        )
    else:
        context.user_data["last_email"] = email
        log_failed_attempt(user.id, email)
        # FIXED: Resolved text configurations securely
        await update.message.reply_text(
            "❌ `{email}` still isn't linked to {MENTOR_NAME}.\n\n"
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

    package_key = query.data  # "vip_one_on_one" or "vip_group"

    if package_key == "vip_one_on_one":
        package_label = "One-on-One Mentorship"
        package_price = VIP_ONE_ON_ONE_PRICE
    else:
        package_label = "Group Mentorship"
        package_price = VIP_GROUP_PRICE

    context.user_data["vip_package_key"] = package_key
    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        package_key,
    )
    context.user_data["vip_package_label"] = package_label
    context.user_data["vip_package_price"] = package_price

    # Notify admin of new VIP inquiry
    # user = query.from_user
    # await notify_admin(
    #     context.bot,
    #     vip_inquiry_message(user.first_name, user.username),
    # )

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
    """Receive phone, notify admin, send payment link to user."""
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
    package_key = context.user_data.get("vip_package_key", "")

    logger.info(
        "vip_mentorship_request",
        user_id=user.id,
        name=name,
        phone=phone,
        package=package_label,
    )

    # Notify admin with full details
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

    # Determine payment link based on package
    if package_key == "vip_one_on_one":
        payment_link = VIP_ONE_ON_ONE_PAYMENT_LINK
    else:
        payment_link = VIP_GROUP_PAYMENT_LINK

    # Build reply keyboard
    keyboard_buttons = []
    if payment_link:
        keyboard_buttons.append(
            [InlineKeyboardButton("💳 Proceed to Payment", url=payment_link)]
        )
    keyboard_buttons.append(
        [InlineKeyboardButton("📩 Contact Mentor", url=MENTOR_CONTACT)]
    )
    keyboard_buttons.append(
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    )

    await update.message.reply_text(
        (
            "✅ *Thanks {name}! You're one step away.*\n\n"
            "📦 *Package:* {package_label}\n"
            "💰 *Price:* {package_price}\n\n"
            "Tap below to proceed with your payment. "
            "Once done, contact {MENTOR_NAME} directly to confirm "
            "and get onboarded. 🎉"
        ).format(
            name=name,
            package_label=package_label,
            package_price=package_price,
            MENTOR_NAME=MENTOR_NAME,
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard_buttons),
    )
    clear_incomplete_flow(id)
    return ConversationHandler.END


# -- Different Broker Flow


async def different_broker_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Entry point - explain the different broker subscription"""
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
    """User taps Subscribe - collect their name."""
    query = update.callback_query
    await query.answer()

    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "different_broker",
    )

    await query.edit_message_text(
        (
            "📝 *Subscription Details*\n\n"
            "Please share a few details to proceed.\n\n"
            "What's your *full name*?"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]],
        ),
    )
    return AWAITING_BROKER_NAME


async def receive_broker_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receive name, ask for mobile number."""
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
    """Receive phone, show payment details and notify admin"""
    phone = update.message.text.strip()
    user = update.effective_user

    if len(phone) < 6:
        await update.message.reply_text(
            "⚠️ Please enter a valid mobile number (with country code):"
        )
        return AWAITING_BROKER_PHONE
    name = context.user_data.get("broker_name", "N/A")

    logger.info(
        "broker_subscription_request",
        user_id=user.id,
        name=name,
        phone=phone,
    )

    # Notify admin
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


# VIP Signal Subscription

SIGNAL_PACKAGE_LABELS = {
    "Signal_1month": "1 Month",
    "Signal_2month": "2 Months",
    "Signal_6month": "6 Months",
    "Signal_1year": "1 Year",
    # If your keyboards.py outputs keys starting with 'subscribe_'
    "subscribe_1month": "1 Month",
    "subscribe_2month": "2 Months",
    "subscribe_6month": "6 Months",
    "subscribe_1year": "1 Year",
}

SIGNAL_PACKAGE_PRICES = {
    "Signal_1month": SIGNAL_PRICE_1MONTH,
    "Signal_2month": SIGNAL_PRICE_2MONTH,
    "Signal_6month": SIGNAL_PRICE_6MONTH,
    "Signal_1year": SIGNAL_PRICE_1YEAR,
    "subscribe_1month": SIGNAL_PRICE_1MONTH,
    "subscribe_2month": SIGNAL_PRICE_2MONTH,
    "subscribe_6month": SIGNAL_PRICE_6MONTH,
    "subscribe_1year": SIGNAL_PRICE_1YEAR,
}

SIGNAL_PACKAGE_KEY = "signal_package"


async def vip_signal_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show package options when "Join VIP Signal" is selected."""
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
    """User tapped a package - start collecting name and display price."""

    query = update.callback_query
    await query.answer()

    package_key = query.data  # e.g., "subscribe_1month"

    # 1. Resolve Package Label
    package_label = SIGNAL_PACKAGE_LABELS.get(package_key)
    if not package_label:
        logger.warning(
            f"Key mismatch for label! Keyboard sent raw data: '{package_key}'"
        )
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

    # 2. Resolve Dynamic Price
    package_price = SIGNAL_PACKAGE_PRICES.get(package_key, "TBD")
    if package_price == "TBD":
        logger.warning(
            f"Key mismatch for price! Keyboard sent raw data: '{package_key}'"
        )
        # Quick fallback check if keys don't match dictionary perfectly
        clean_key = package_key.lower()
        if "1month" in clean_key:
            package_price = SIGNAL_PRICE_1MONTH
        elif "2month" in clean_key:
            package_price = SIGNAL_PRICE_2MONTH
        elif "6month" in clean_key:
            package_price = SIGNAL_PRICE_6MONTH
        elif "1year" in clean_key:
            package_price = SIGNAL_PRICE_1YEAR

    # Store details in session memory for the final step
    context.user_data[SIGNAL_PACKAGE_KEY] = package_label
    save_incomplete_flow(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name,
        "vip_signal",
    )
    context.user_data["signal_package_price"] = package_price

    # 3. Edit message to display Package, Price, and request Full Name
    await query.edit_message_text(
        text=(
            f"📋 *Subscription Details*\n"
            f"📦 *Plan:* {package_label}\n"
            f"💰 *Price:* {package_price}\n\n"
            f"To proceed with your registration, please answer the questions below.\n\n"
            f"What is your *full name*? 👇"
        ),
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
    """Receive name, ask for mobile number."""
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(
            "⚠️ Please enter a valid full name:",
        )
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
    """Receive phone number, show payment details."""
    phone = update.message.text.strip()
    user = update.effective_user

    if len(phone) < 6:
        await update.message.reply_text(
            "⚠️ Please enter a valid phone number (with country code):",
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

    # Notify admin of new signal subscription request
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
    ),
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
