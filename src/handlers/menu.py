"""
menu.py — Handles all InlineKeyboard callbacks except the verification flow.
"""

from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes

from src.handlers.keyboards import back_to_menu, main_menu
from src.handlers.welcome import WELCOME_MESSAGE

# FIXED: Imported MENTOR_NAME alongside ADMIN_USERNAME to handle structural formatting requirements
from src.core.settings import ADMIN_USERNAME, MENTOR_NAME
from src.core.logging import logger


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redisplay the main welcome menu."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    name = user.first_name or "Trader"

    await query.edit_message_text(
        # FIXED: Added MENTOR_NAME argument to matching payload schema rules to fix the KeyError crash
        WELCOME_MESSAGE.format(name=name, MENTOR_NAME=MENTOR_NAME),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("support_requested", user_id=query.from_user.id)

    # FIXED: Added clean string formatting fallback to safely handle handles that include or exclude '@'
    clean_admin_username = ADMIN_USERNAME.lstrip("@") if ADMIN_USERNAME else "admin"

    await query.edit_message_text(
        "🆘 *Contact Admin / Support*\n\n"
        "Our support team is ready to help you.\n\n"
        f"👤 Reach our admin directly: @{clean_admin_username}\n\n"
        "_We typically respond within a few hours._",
        parse_mode="Markdown",
        reply_markup=back_to_menu(),
    )
