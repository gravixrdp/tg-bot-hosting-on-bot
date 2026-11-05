"""
Echo Telegram Bot Template.

A clean, responsive Telegram bot that echoes incoming text messages,
stickers, and media back to the sender.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("EchoBot")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logger.error("FATAL: BOT_TOKEN environment variable is not set!")
    sys.exit(1)

dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    """Handle /start command."""
    user_name = message.from_user.first_name if message.from_user else "Friend"
    await message.answer(
        f"👋 Hello, <b>{user_name}</b>!\n\n"
        f"I am your <b>Echo Bot</b>, hosted seamlessly on Telegram.\n"
        f"Send me any text, sticker, or message and I will echo it right back to you!",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    """Handle /help command."""
    await message.answer(
        "ℹ️ <b>Echo Bot Help:</b>\n"
        "• Just send any text or message to have it echoed.\n"
        "• Use /start to reset conversation.",
        parse_mode=ParseMode.HTML,
    )


@dp.message()
async def handle_echo(message: types.Message) -> None:
    """Echo incoming messages back to the user."""
    if message.text:
        await message.reply(f"🔁 <b>Echo:</b> {message.text}", parse_mode=ParseMode.HTML)
    elif message.sticker:
        await message.reply_sticker(message.sticker.file_id)
    elif message.animation:
        await message.reply_animation(message.animation.file_id)
    elif message.photo:
        await message.reply_photo(message.photo[-1].file_id, caption=message.caption)
    else:
        await message.reply("Received your message! 🚀")


async def main() -> None:
    bot = Bot(token=TOKEN)
    logger.info("Starting Echo Bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
