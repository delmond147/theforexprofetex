"""
faq.py — FAQ flow with individual question buttons.
"""

from __future__ import annotations
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# FIXED: Imported MENTOR_NAME to prevent runtime NameErrors
from src.core.settings import PARTNER_LINK, MENTOR_NAME

FAQ_ITEMS = {
    "faq_who": (
        "👩‍💼 *Who is {MENTOR_NAME}?*",
        "{MENTOR_NAME} is a professional forex trader and mentor dedicated to "
        "helping everyday people learn how to trade profitably. With years of "
        "live market experience, {MENTOR_NAME} makes trading simple, practical, and accessible. 📈",
    ),
    "faq_free": (
        "🆓 *Is the Marathon Forex University really free?*",
        "Yes! Joining the Marathon Forex University programs are completely free "
        "as long as your Exness trading account is registered under {MENTOR_NAME}'s "
        "partner link. That's all it takes to unlock full access. ✅",
    ),
    "faq_broker": (
        "🏦 *What broker do we use?*",
        "We use *Exness* — one of the world's most trusted forex brokers with "
        "ultra-fast execution, low spreads, and instant withdrawals. "
        "You can open a free account at {PARTNER_LINK} using {MENTOR_NAME}'s partner link.",
    ),
    "faq_change_partner": (
        "🔄 *How do I change my Exness partner?*",
        "If your Exness account is under a different partner, here's how to switch:\n\n"
        "1️⃣ Log in to your Exness Personal Area\n"
        "2️⃣ Go to Profile → Live Chat\n"
        "3️⃣ Type: `Change partner`\n"
        "4️⃣ Follow the link the Exness bot sends\n"
        "5️⃣ Select *Rebate* as the reason\n"
        "6️⃣ Enter {MENTOR_NAME}'s partner link ({PARTNER_LINK})\n\n"
        "The change usually takes a few minutes. ⏳",
    ),
    "faq_verify_time": (
        "⏱ *How long does verification take?*",
        "Verification is instant! Once you submit your email, the bot checks "
        "your Exness account in seconds. If you just changed your partner, "
        "it may take up to 10 minutes to reflect — just tap *'Verify me again'* after waiting. 😊",
    ),
    "faq_vip": (
        "💎 *What's included in VIP Mentorship?*",
        "The VIP Mentorship includes:\n\n"
        "• Market Structure\n"
        "• Liquidity Concepts\n"
        "• Time and Price Concepts\n"
        "• Candle Range Theory\n"
        "• Entry Confirmations\n"
        "• Risk Management & Psychology\n"
        "• Direct WhatsApp/Telegram access to {MENTOR_NAME}\n"
        "• Lifetime access to VIP group resources\n\n"
        "Investment: {VIP_PRICE} one-time. Limited spots available. 🔥",
    ),
}


def faq_main_keyboard() -> InlineKeyboardMarkup:
    # FIXED: Added f-string configuration to render the dynamic client name on the button interface
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"👩‍💼 Who is {MENTOR_NAME}?", callback_data="faq_who"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🆓 Is the Marathon Forex University really free?",
                    callback_data="faq_free",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏦 What broker do we use?", callback_data="faq_broker"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 How do I change my partner?", callback_data="faq_change_partner"
                )
            ],
            [
                InlineKeyboardButton(
                    "⏱ How long does verification take?",
                    callback_data="faq_verify_time",
                )
            ],
            [
                InlineKeyboardButton(
                    "💎 What's in the VIP Mentorship?", callback_data="faq_vip"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def faq_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Back to FAQs", callback_data="faq_menu")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]
    )


async def faq_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the FAQ question list."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "❓ *Frequently Asked Questions*\n\n" "Tap a question to get the answer 👇",
        parse_mode="Markdown",
        reply_markup=faq_main_keyboard(),
    )


async def faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the answer to a specific FAQ question."""
    query = update.callback_query
    await query.answer()

    key = query.data
    if key not in FAQ_ITEMS:
        await query.answer("Question not found.", show_alert=True)
        return

    raw_title, raw_answer = FAQ_ITEMS[key]

    # FIXED: Explicitly run .format() to inject environmental values dynamically per execution
    title = raw_title.format(MENTOR_NAME=MENTOR_NAME)
    answer = raw_answer.format(MENTOR_NAME=MENTOR_NAME, PARTNER_LINK=PARTNER_LINK)

    await query.edit_message_text(
        f"{title}\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=faq_answer_keyboard(),
    )
