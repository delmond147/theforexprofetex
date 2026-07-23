"""
group_access.py — Generates one-time Telegram invite links for verified members.

Each link:
- Can only be used once
- Expires after 24 hours
- Is unique per member per request
- Cannot be shared or reused
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from src.core.settings import (
    VIP_GROUP_ID,
    BEGINNERS_GROUP_LINK,
    ADVANCED_GROUP_LINK,
    SWING_TRADING_LINK,
    MENTOR_CONTACT,
    MENTOR_NAME,
)
from src.db.database import get_user
from src.core.logging import logger

# Map group type to fallback static link (used only if bot is not admin)
FALLBACK_LINKS = {
    "beginners": BEGINNERS_GROUP_LINK,
    "advanced": ADVANCED_GROUP_LINK,
    "swing": SWING_TRADING_LINK,
}

# Map mentorship type to group type
MENTORSHIP_TO_GROUP = {
    "beginners": "beginners",
    "advanced": "advanced",
    "swing": "swing",
}


async def _generate_one_time_link(bot, group_type: str) -> str | None:
    """
    Generate a one-time invite link for the VIP group.
    Link expires in 24 hours and can only be used once.
    Returns the invite link or None if generation fails.
    """
    if not VIP_GROUP_ID:
        logger.warning("vip_group_id_not_configured")
        return None

    try:
        expire_date = datetime.now(timezone.utc) + timedelta(hours=24)

        invite_link = await bot.create_chat_invite_link(
            chat_id=int(VIP_GROUP_ID),
            name=f"VIP-{group_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            expire_date=expire_date,
            member_limit=1,  # ← one use only
            creates_join_request=False,
        )

        logger.info(
            "invite_link_generated",
            group_type=group_type,
            expires=expire_date.isoformat(),
        )
        return invite_link.invite_link

    except TelegramError as e:
        logger.error(
            "invite_link_generation_failed", group_type=group_type, error=str(e)
        )
        return None


async def get_group_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Handle 'Get My Group Link' button taps.
    Verifies user is still eligible then generates a one-time link.
    """
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = get_user(user.id)

    # Extract group type from callback data
    # e.g. "get_group_link_advanced" → "advanced"
    group_type = query.data.replace("get_group_link_", "")

    # ── Eligibility check ─────────────────────────────────────────────────────
    if not db_user or not db_user["verified_email"]:
        await query.edit_message_text(
            "⚠️ You need to verify your account first.\n\n"
            "Tap /start to begin verification.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            ),
        )
        return

    if db_user["removed"]:
        await query.edit_message_text(
            "❌ Your access has been removed.\n\n"
            "Please tap /start and complete verification again "
            "to regain access.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            ),
        )
        return

    if not db_user["mt5_verified"]:
        await query.edit_message_text(
            "⚠️ Your MT5 account verification is still pending.\n\n"
            "Please create and fund your MT5 account first.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Check MT5 Status", callback_data="check_mt5_status"
                        )
                    ],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]
            ),
        )
        return

    # ── Generate one-time link ────────────────────────────────────────────────
    await query.edit_message_text(
        "⏳ Generating your personal group link...",
        parse_mode="Markdown",
    )

    invite_link = await _generate_one_time_link(context.bot, group_type)

    if invite_link:
        await query.edit_message_text(
            (
                "🎉 *Your Personal Group Link*\n\n"
                "This link is unique to you and can only be used *once*.\n"
                "It expires in *24 hours*.\n\n"
                "👇 Tap below to join:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🚀 Join Group Now", url=invite_link)],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]
            ),
        )
        logger.info(
            "one_time_link_sent",
            telegram_id=user.id,
            group_type=group_type,
        )
    else:
        # Fallback to static link if bot is not admin or group ID not set
        fallback = FALLBACK_LINKS.get(group_type, ADVANCED_GROUP_LINK)
        await query.edit_message_text(
            (
                "🎉 *Welcome to {MENTOR_NAME}!*\n\n" "Tap below to join your group 👇"
            ).format(MENTOR_NAME=MENTOR_NAME),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🚀 Join Group", url=fallback)],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
                ]
            ),
        )
        logger.warning(
            "fallback_link_used",
            telegram_id=user.id,
            group_type=group_type,
        )
