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
        if router._parent_router is not None:
            router._parent_router = None
        dp.include_router(router)
    return dp



from aiohttp import web

async def start_health_server(port: int = 7860) -> web.AppRunner:
    """Start lightweight HTTP server for Hugging Face Spaces and UptimeRobot keep-alive."""
    app = web.Application()

    async def handle_root(request: web.Request) -> web.Response:
        html = (
            "<!DOCTYPE html>"
            "<html>"
            "<head><title>Telegram Bot Hosting Platform</title>"
            "<meta charset='utf-8'>"
            "<style>"
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
            "background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }"
            ".card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; text-align: center; max-width: 500px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }"
            ".badge { background: #10b981; color: #fff; padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; display: inline-block; margin-bottom: 1rem; }"
            "h1 { margin: 0 0 0.5rem; font-size: 1.75rem; }"
            "p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; margin-bottom: 1.5rem; }"
            ".btn { background: #2563eb; color: #fff; text-decoration: none; padding: 0.75rem 1.5rem; border-radius: 0.5rem; font-weight: 600; display: inline-block; transition: background 0.2s; }"
            ".btn:hover { background: #1d4ed8; }"
            ".footer { margin-top: 1.5rem; font-size: 0.8rem; color: #64748b; }"
            "</style>"
            "</head>"
            "<body>"
            "<div class='card'>"
            "<div class='badge'>🟢 Active & Polling</div>"
            "<h1>Telegram Bot Hosting</h1>"
            "<p>Production-grade nested Telegram Bot Hosting Platform running on Hugging Face Spaces (16 GB RAM • 2 vCPU).</p>"
            "<a class='btn' href='https://t.me/hermes_esyiczoumzicemfa_bot' target='_blank'>Open Master Bot in Telegram 🚀</a>"
            "<div class='footer'>Health Check Active • Keep-Alive Pings Enabled</div>"
            "</div>"
            "</body>"
            "</html>"
        )
        return web.Response(text=html, content_type="text/html")

    async def handle_health(request: web.Request) -> web.Response:
        return web.json_response({
            "status": "healthy",
            "service": "telegram-bot-hosting-platform",
            "uptime_robot": "ok",
        })

    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


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

    # 4. Start HTTP Health & Dashboard server for Hugging Face Spaces and UptimeRobot
    server_port = int(os.getenv("PORT", "7860"))
    http_runner = None
    try:
        http_runner = await start_health_server(server_port)
        logger.info("HTTP Health Check server started on 0.0.0.0:%s", server_port)
    except Exception as exc:
        logger.warning("Could not start HTTP health server on port %s: %s", server_port, exc)

    logger.info("Starting Master Bot polling loop...")
    try:
        # Delete any pending webhook updates before starting polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Shutting down bot process supervisor and closing sessions...")
        if http_runner:
            await http_runner.cleanup()
        await supervisor.shutdown()
        await bot.session.close()
        await close_db()
        logger.info("Platform shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
