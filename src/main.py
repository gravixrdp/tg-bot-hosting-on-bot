"""
Main Application Entry Point for the Telegram Bot Hosting Platform.

Initializes the database schema, sets up the Aiogram Bot and Dispatcher,
registers UI routers, hooks the supervisor crash alert callback,
and runs the polling loop with graceful shutdown handling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers import get_all_routers
from src.bot.keyboards.inline import get_crash_alert_keyboard
from src.core.config import settings
from src.core.database import close_db, get_bot, get_session, init_db
from src.core.supervisor import supervisor

# Configure application-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MasterBot")


async def setup_crash_callback(bot: Bot) -> None:
    """
    Register supervisor crash notification callback.

    Dispatches an alert to the bot owner whenever a child bot crashes unexpectedly:
    "⚠️ Alert: Your bot [Bot Name] crashed! Exit code: [code]. Click below to view logs or restart."
    """

    async def on_bot_crash(bot_id: int, return_code: int, last_logs: str) -> None:
        try:
            async with get_session() as session:
                hosted_bot = await get_bot(session, bot_id)
                if not hosted_bot:
                    return

                owner_id = hosted_bot.user_id
                bot_name = hosted_bot.name

            # Truncate logs snippet for alert display
            truncated_logs = last_logs[-600:] if last_logs else "No logs available."

            alert_text = (
                f"⚠️ <b>Alert: Your bot '{bot_name}' crashed!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Bot ID:</b> <code>{bot_id}</code>\n"
                f"• <b>Exit Code:</b> <code>{return_code}</code>\n\n"
                f"<b>Recent Logs:</b>\n"
                f"<pre>{truncated_logs}</pre>\n\n"
                f"Click below to view full logs or attempt a restart."
            )

            await bot.send_message(
                chat_id=owner_id,
                text=alert_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_crash_alert_keyboard(bot_id),
            )
            logger.info("Dispatched crash alert to user %s for bot %s (code %s)", owner_id, bot_id, return_code)

        except Exception as exc:
            logger.error("Failed to send crash alert for bot %s: %s", bot_id, exc)

    supervisor.register_crash_callback(on_bot_crash)


def create_dispatcher() -> Dispatcher:
    """Create and configure the central Aiogram Dispatcher with all routers."""
    dp = Dispatcher(storage=MemoryStorage())
    for router in get_all_routers():
        dp.include_router(router)
    return dp


async def main() -> None:
    """Initialize system services and start bot polling."""
    logger.info("Initializing Telegram Bot Hosting Platform...")

    # 1. Initialize database schema
    await init_db()
    logger.info("Database initialized successfully.")

    if not settings.BOT_TOKEN:
        logger.error(
            "FATAL: BOT_TOKEN is not configured! Please set BOT_TOKEN in .env file or environment variables."
        )
        sys.exit(1)

    # 2. Initialize Bot and Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()

    # 3. Hook real-time supervisor crash alerting
    await setup_crash_callback(bot)

    logger.info("Starting Master Bot polling loop...")
    try:
        # Delete any pending webhook updates before starting polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Shutting down bot process supervisor and closing sessions...")
        await supervisor.shutdown()
        await bot.session.close()
        await close_db()
        logger.info("Platform shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
