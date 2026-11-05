"""
Broadcast Telegram Bot Template.

Allows an administrator to broadcast announcements to all registered bot users.
Subscribers are stored persistently in a local SQLite database.
"""

import asyncio
import logging
import os
import sqlite3
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("BroadcastBot")

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else None

if not TOKEN:
    logger.error("FATAL: BOT_TOKEN environment variable is not set!")
    sys.exit(1)

# Persistent subscriber storage
DB_PATH = "subscribers.db"


def init_subscribers_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def add_subscriber(user_id: int, username: str | None) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        conn.commit()


def get_all_subscribers() -> list[int]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM subscribers")
        return [row[0] for row in cursor.fetchall()]


init_subscribers_db()
dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    """Register user as subscriber."""
    if message.from_user:
        add_subscriber(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 <b>Welcome to the Announcement Channel!</b>\n\n"
        "You are now subscribed to receive broadcast messages from the admin.",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("stats"))
async def handle_stats(message: types.Message) -> None:
    """View subscriber stats."""
    subscribers = get_all_subscribers()
    await message.answer(
        f"📊 <b>Subscriber Statistics:</b>\n"
        f"• Total registered subscribers: <b>{len(subscribers)}</b>",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("broadcast"))
async def handle_broadcast(message: types.Message, bot: Bot) -> None:
    """Admin broadcast command: /broadcast <text>."""
    if ADMIN_ID and message.from_user and message.from_user.id != ADMIN_ID:
        await message.reply("⛔ You are not authorized to send broadcasts.")
        return

    text_parts = message.text.split(maxsplit=1) if message.text else []
    if len(text_parts) < 2:
        await message.reply("⚠️ Usage: <code>/broadcast Your message here</code>", parse_mode=ParseMode.HTML)
        return

    broadcast_content = text_parts[1]
    subscribers = get_all_subscribers()
    success, failed = 0, 0

    progress_msg = await message.reply(f"🚀 Dispatching broadcast to {len(subscribers)} users...")

    for uid in subscribers:
        try:
            await bot.send_message(uid, f"📢 <b>Announcement:</b>\n\n{broadcast_content}", parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await progress_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"• Sent successfully: <b>{success}</b>\n"
        f"• Failed/Blocked: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
    )


async def main() -> None:
    bot = Bot(token=TOKEN)
    logger.info("Starting Broadcast Bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
