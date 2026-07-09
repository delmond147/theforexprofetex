"""
keyboards.py — All InlineKeyboardMarkup definitions in one place.
"""

from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.core.settings import (
    PARTNER_LINK,
    BEGINNERS_GROUP_LINK,
    ADVANCED_GROUP_LINK,
    SWING_TRADING_LINK,
    INNER_CIRCLE_LINK,
    MENTOR_CONTACT,
    VIP_PRICE,
    SIGNAL_PRICE_1MONTH,
    SIGNAL_PRICE_2MONTH,
    SIGNAL_PRICE_6MONTH,
    SIGNAL_PRICE_1YEAR,
    DIFFERENT_BROKER_PRICE,
    VIP_ONE_ON_ONE_PRICE,
    VIP_GROUP_PRICE,
    PAYMENT_METHOD_1_NAME,
    PAYMENT_METHOD_2_NAME,
    PAYMENT_METHOD_3_NAME,
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            # [
            #     InlineKeyboardButton(
            #         "📗 Free Beginners Mentorship", callback_data="beginners_mentorship"
            #     )
            # ],
            [
                InlineKeyboardButton(
                    "📚 EXNESS VIP SIGNALS",
                    callback_data="advanced_mentorship",
                )
            ],
            # [InlineKeyboardButton("🥇 EXNESS VIP", callback_data="vip_signal")],
            [
                InlineKeyboardButton(
                    "🔄 USING A DIFFERENT BROKER?", callback_data="different_broker"
                )
            ],
            [InlineKeyboardButton("💎 VIP MENTORSHIP", callback_data="vip_mentorship")],
            # [
            #     InlineKeyboardButton(
            #         "📉 Swing Trading Private Telegram", callback_data="swing_trading"
            #     )
            # ],
            [
                InlineKeyboardButton(
                    "📢 THEFOREXPROPHETESS COMMUNITY", url=INNER_CIRCLE_LINK
                )
            ],
            [InlineKeyboardButton("🆘 Get Support", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("❓ FAQs", callback_data="faq_menu")],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    )


# ── Verification flow ─────────────────────────────────────────────────────────


def register_with_partner() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 Create Exness Account", url=PARTNER_LINK)],
            [
                InlineKeyboardButton(
                    "✅ I've registered — verify me", callback_data="already_registered"
                )
            ],
            [InlineKeyboardButton("🆘 Need help?", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def account_not_found_options() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, I have an account", callback_data="has_account_not_linked"
                )
            ],
            [
                InlineKeyboardButton(
                    "🆕 No, I don't have one", callback_data="not_registered"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Try a different email", callback_data="verify_email"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def change_partner_guide() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💬 Open Exness Live Chat", url="https://www.exness.com/support/"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ I've changed it — verify me again",
                    callback_data="reverify_email",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Try a different email", callback_data="verify_email"
                )
            ],
            [InlineKeyboardButton("🆘 Get Support", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def verified_beginners() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎉 Join Beginners Group", url=BEGINNERS_GROUP_LINK)],
            [
                InlineKeyboardButton(
                    "📘 Upgrade to Advanced", callback_data="advanced_mentorship"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def verified_advanced() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎉 Join Exness VIP Group", url=ADVANCED_GROUP_LINK)],
            [InlineKeyboardButton("💎 Upgrade to VIP", callback_data="vip_mentorship")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def verified_swing() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📉 Join Swing Trading Channel",
                    url=SWING_TRADING_LINK,
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


# ── VIP Signal Subscription Button Menu ─────────────────────────────────────────────────
def vip_signal_packages() -> InlineKeyboardMarkup:
    """Package selection menu for VIP Signal Subscription."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"1️⃣ Month - {SIGNAL_PRICE_1MONTH}", callback_data="signal_1month"
                )
            ],
            [
                InlineKeyboardButton(
                    f"2️⃣ Months - {SIGNAL_PRICE_2MONTH}",
                    callback_data="signal_2month",
                )
            ],
            [
                InlineKeyboardButton(
                    f"6️⃣ Months - {SIGNAL_PRICE_6MONTH}",
                    callback_data="signal_6month",
                )
            ],
            [
                InlineKeyboardButton(
                    f"1️⃣ Year - {SIGNAL_PRICE_1YEAR}", callback_data="signal_1year"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


# ── VIP Signal Subscription Payment Proof ─────────────────────────────────────────────────
def signal_payment_proof() -> InlineKeyboardMarkup:
    """Payment proof submission menu for VIP Signal Subscription."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📩 Send Payment Proof", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def onboarding(group_url: str) -> InlineKeyboardMarkup:
    """Follow-up keyboard sent after a user joins a group."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📌 Go to Group", url=group_url)],
            [InlineKeyboardButton("❓ FAQs", callback_data="faq_menu")],
            [InlineKeyboardButton("🆘 Get Support", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]
    )


# ── VIP ───────────────────────────────────────────────────────────────────────


def vip_after_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📩 Send Payment Proof", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def vip_mentorship_packages() -> InlineKeyboardMarkup:
    """VIP Mentorship package selection."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"👤 One-on-One Mentorship — {VIP_ONE_ON_ONE_PRICE}",
                    callback_data="vip_one_on_one",
                )
            ],
            [
                InlineKeyboardButton(
                    f"👥 Group Mentorship — {VIP_GROUP_PRICE}",
                    callback_data="vip_group",
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def vip_payment_methods() -> InlineKeyboardMarkup:
    """VIP Mentorship payment method selection."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"💳 {PAYMENT_METHOD_1_NAME}", callback_data="vip_payment_method_1"
                )
            ],
            [
                InlineKeyboardButton(
                    f"💵 {PAYMENT_METHOD_2_NAME}", callback_data="vip_payment_method_2"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🏦 {PAYMENT_METHOD_3_NAME}", callback_data="vip_payment_method_3"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )


def different_broker_payment() -> InlineKeyboardMarkup:
    """Show after user confirms payment for different broker subscription."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📩 Send Payment Proof", url=MENTOR_CONTACT)],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
        ]
    )
