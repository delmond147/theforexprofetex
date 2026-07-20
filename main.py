"""
main.py — Application entry point.
"""

from __future__ import annotations
from multiprocessing import context
import os
import asyncio
from datetime import time as dtime
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from src.core.settings import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT
from src.core.logging import configure_logging, logger
from src.handlers.welcome import start
from src.handlers.menu import handle_main_menu, handle_support
from src.handlers.faq import faq_menu, faq_answer, FAQ_ITEMS
from src.handlers.admin import (
    broadcast,
    set_credentials_start,
    set_credentials_email,
    set_credentials_password,
    clear_credentials,
    check_api,
    set_token,
    clear_token,
    AWAITING_API_EMAIL,
    AWAITING_API_PASSWORD,
)
from src.handlers.signals import (
    send_signal,
    send_announcement,
    check_inactive_now,
    list_verified,
)
from src.handlers.verification import (
    beginners_entry,
    advanced_entry,
    swing_entry,
    not_registered,
    already_registered,
    receive_email,
    restart_verify,
    reverify_entry,
    receive_reverify_email,
    has_account_not_linked,
    vip_entry,
    # vip_payment,
    vip_signal_entry,
    signal_package_selected,
    receive_signal_name,
    receive_signal_phone,
    receive_vip_payment_method,
    AWAITING_VIP_PAYMENT_METHOD,
    cancel,
    AWAITING_EMAIL,
    AWAITING_REVERIFY_EMAIL,
    AWAITING_SIGNAL_NAME,
    AWAITING_SIGNAL_PHONE,
    different_broker_entry,
    broker_subscribe,
    receive_broker_name,
    receive_broker_phone,
    vip_package_selected,
    receive_vip_name,
    receive_vip_phone,
    AWAITING_VIP_NAME,
    AWAITING_VIP_PHONE,
    AWAITING_BROKER_NAME,
    AWAITING_BROKER_PHONE,
)
from src.db.database import init_db
from src.services.activity_checker import (
    run_activity_check,
    run_reminder_check,
    run_mt5_check,
)


async def help_command(update, context) -> None:
    await update.message.reply_text(
        "🤖 *Bot Help*\n\n"
        "/start — Show the main menu\n"
        "/help — Show this message\n"
        "/cancel — Cancel current action\n\n"
        "Tap any button in the menu to get started! 👇",
        parse_mode="Markdown",
    )


def build_app() -> Application:
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(HTTPXRequest(connect_timeout=30, read_timeout=30))
        .build()
    )

    # ── Commands ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("checkapi", check_api))
    app.add_handler(CommandHandler("clearcredentials", clear_credentials))
    app.add_handler(CommandHandler("settoken", set_token))
    app.add_handler(CommandHandler("cleartoken", clear_token))
    app.add_handler(CommandHandler("signal", send_signal))
    app.add_handler(CommandHandler("announce", send_announcement))
    app.add_handler(CommandHandler("checkinactive", check_inactive_now))
    app.add_handler(CommandHandler("listusers", list_verified))

    # ── Admin credential setup conversation ───────────────────────────────────
    admin_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setcredentials", set_credentials_start),
        ],
        states={
            AWAITING_API_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_credentials_email)
            ],
            AWAITING_API_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, set_credentials_password
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── Verification conversation ─────────────────────────────────────────────
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(already_registered, pattern="^already_registered$"),
            CallbackQueryHandler(restart_verify, pattern="^verify_email$"),
            CallbackQueryHandler(reverify_entry, pattern="^reverify_email$"),
        ],
        states={
            AWAITING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)
            ],
            AWAITING_REVERIFY_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reverify_email)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(conv)

    # ── VIP Signal subscription conversation ──────────────────────────────────
    signal_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                signal_package_selected, pattern="^signal_(1month|2month|6month|1year)$"
            ),
        ],
        states={
            AWAITING_SIGNAL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_signal_name)
            ],
            AWAITING_SIGNAL_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_signal_phone)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(signal_conv)

    # ── Different broker subscription conversation ─────────────────────────────────
    broker_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broker_subscribe, pattern="^broker_subscribe$"),
        ],
        states={
            AWAITING_BROKER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broker_name)
            ],
            AWAITING_BROKER_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broker_phone)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(broker_conv)

    # ── VIP Mentorship conversation ───────────────────────────────────────────────
    vip_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                vip_package_selected, pattern="^vip_(one_on_one|group)$"
            ),
        ],
        states={
            AWAITING_VIP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vip_name)
            ],
            AWAITING_VIP_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vip_phone)
            ],
            AWAITING_VIP_PAYMENT_METHOD: [
                CallbackQueryHandler(
                    receive_vip_payment_method,
                    pattern="^vip_payment_method_(1|2|3)$",
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(vip_conv)

    # ── Menu callbacks ────────────────────────────────────────────────────────
    app.add_handler(
        CallbackQueryHandler(beginners_entry, pattern="^beginners_mentorship$")
    )
    app.add_handler(
        CallbackQueryHandler(advanced_entry, pattern="^advanced_mentorship$")
    )
    app.add_handler(CallbackQueryHandler(swing_entry, pattern="^swing_trading$"))
    app.add_handler(CallbackQueryHandler(vip_entry, pattern="^vip_mentorship$"))
    # app.add_handler(CallbackQueryHandler(vip_payment, pattern="^vip_payment$"))
    app.add_handler(
        CallbackQueryHandler(different_broker_entry, pattern="^different_broker$")
    )
    app.add_handler(CallbackQueryHandler(vip_signal_entry, pattern="^vip_signal$"))
    app.add_handler(CallbackQueryHandler(not_registered, pattern="^not_registered$"))
    app.add_handler(
        CallbackQueryHandler(has_account_not_linked, pattern="^has_account_not_linked$")
    )
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"))

    # ── FAQ callbacks ─────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(faq_menu, pattern="^faq_menu$"))
    faq_pattern = "^(" + "|".join(FAQ_ITEMS.keys()) + ")$"
    app.add_handler(CallbackQueryHandler(faq_answer, pattern=faq_pattern))

    async def _reminder_job(context) -> None:
        """Wrapper for the 4-hour incomplete flow reminder."""
        logger.info("reminder_job_triggered")
        await run_reminder_check(context.bot)

    async def _mt5_check_job(context) -> None:
        """Wrapper for the 6-hour MT5 verification check."""
        logger.info("mt5_check_job_triggered")
        await run_mt5_check(context.bot)

    # ── Daily activity check — runs at 3AM UTC ────────────────────────────────
    if app.job_queue:
        app.job_queue.run_daily(
            _daily_activity_job,
            time=dtime(hour=3, minute=0),
            name="daily_activity_check",
        )
        logger.info("daily_job_scheduled")
    else:
        logger.warning("job_queue_not_available_skipping_scheduler")

    # ---- Reminder job - runs every 4 hours
    if app.job_queue:
        app.job_queue.run_daily(
            _daily_activity_job,
            time=dtime(hour=3, minute=0),
            name="daily_activity_check",
        )
        app.job_queue.run_repeating(
            _reminder_job,
            interval=14400,  # 4 hours in seconds
            first=300,  # first run 5 minutes after bot starts
            name="incomplete_flow_reminder",
        )
        logger.info("jobs_scheduled")

    else:
        logger.warning("job_queue_not_available")

    app.job_queue.run_repeating(
        _mt5_check_job,
        interval=21600,  # 6 hours in seconds
        first=600,  # first run 10 minutes after bot starts
        name="mt5_verification_check",
    )
    logger.info("jobs_scheduled")

    # ── Global error handler ──────────────────────────────────────────────────
    async def error_handler(update, context) -> None:
        logger.error("unhandled_error", error=str(context.error))
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⏳ Something went wrong. Please try again in a moment!"
            )

    app.add_error_handler(error_handler)
    return app


async def _daily_activity_job(context) -> None:
    """Wrapper for the scheduled daily activity check."""
    logger.info("scheduled_activity_check_triggered")
    await run_activity_check(context.bot)


def main() -> None:
    configure_logging(debug=os.environ.get("DEBUG", "").lower() == "true")
    logger.info("bot_starting")
    app = build_app()

    if WEBHOOK_URL:
        logger.info("mode_webhook", url=WEBHOOK_URL, port=WEBHOOK_PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "8080")),
            webhook_url=WEBHOOK_URL,
        )
    else:
        logger.info("mode_polling")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
