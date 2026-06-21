"""
welcome.py — /start command. Greets new users warmly, welcomes back verified users.
"""

from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes

from src.handlers.keyboards import main_menu, verified_beginners, verified_advanced
from src.core.logging import logger
from src.core.settings import BEGINNERS_GROUP_LINK, ADVANCED_GROUP_LINK, MENTOR_NAME
from src.db.database import upsert_user, get_user

# Exported so menu.py can import it
WELCOME_MESSAGE = (
    "👋 Hey {name}! Welcome to *{MENTOR_NAME}* 📈\n\n"
    "Here, we help you level up your trading journey "
    "By turning you into a consistently profitable trader\n\n"
    "With our proven strategies and expert guidance.\n\n"
    "Tap a button below to get started 👇"
)

WELCOME_BACK_VERIFIED = (
    "👋 Welcome back, *{name}*! Great to see you again. 😊\n\n"
    "✅ Your Exness account is verified under *{MENTOR_NAME}*.\n"
    "📚 Program: *{mentorship}*\n\n"
    "Tap below to go to your group or explore more 👇"
)

WELCOME_BACK_UNVERIFIED = (
    "👋 Hey {name}, welcome back! 😊\n\n"
    "You haven't verified your Exness account yet. "
    "Tap a button below to get started 👇"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = user.first_name or "Trader"
    logger.info("user_start", user_id=user.id, username=user.username)

    upsert_user(user.id, user.username, user.first_name)

    db_user = get_user(user.id)

    if db_user and db_user["verified_email"]:
        mentorship = (db_user["mentorship_type"] or "beginners").capitalize()
        kb = (
            verified_beginners()
            if db_user["mentorship_type"] == "beginners"
            else verified_advanced()
        )
        await update.message.reply_text(
            WELCOME_BACK_VERIFIED.format(
                name=name,
                mentorship=mentorship,
                MENTOR_NAME=MENTOR_NAME,
            ),
            parse_mode="Markdown",
            reply_markup=kb,
        )
    elif db_user:
        await update.message.reply_text(
            WELCOME_BACK_UNVERIFIED.format(name=name),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            WELCOME_MESSAGE.format(name=name, MENTOR_NAME=MENTOR_NAME),
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
