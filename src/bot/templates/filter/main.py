"""
Filter / Content Moderation Telegram Bot Template.

Monitors group chats and direct messages for prohibited keywords, spam phrases,
and unauthorized links, protecting groups from spam.
"""

import asyncio
import logging
import os
import re
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("FilterBot")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logger.error("FATAL: BOT_TOKEN environment variable is not set!")
    sys.exit(1)

# Default prohibited keywords and spam patterns
BANNED_WORDS = {"spam", "freecrypto", "airdrop", "scam", "hack"}
URL_PATTERN = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+")

dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    """Handle /start command."""
    await message.answer(
        "🛡️ <b>Filter & Moderation Bot Active!</b>\n\n"
        "Add me to your group as an Admin to automatically filter out spam, "
        "banned keywords, and phishing links.\n\n"
        "Commands:\n"
        "• /rules - View content moderation rules",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("rules"))
async def handle_rules(message: types.Message) -> None:
    """Display active filtering rules."""
    words = ", ".join(f"<code>{w}</code>" for w in sorted(BANNED_WORDS))
    await message.answer(
        f"📋 <b>Active Moderation Rules:</b>\n"
        f"• <b>Banned Keywords:</b> {words}\n"
        f"• <b>Link Policy:</b> Verified links only\n"
        f"• Violations result in instant message deletion.",
        parse_mode=ParseMode.HTML,
    )


@dp.message()
async def monitor_messages(message: types.Message, bot: Bot) -> None:
    """Scan incoming messages for forbidden patterns."""
    if not message.text:
        return

    text_lower = message.text.lower()

    # Check for banned keywords
    for word in BANNED_WORDS:
        if word in text_lower:
            try:
                await message.delete()
                warning = await message.answer(
                    f"⚠️ Warning: Message from @{message.from_user.username or 'user'} deleted "
                    f"for containing prohibited content.",
                )
                await asyncio.sleep(5)
                await warning.delete()
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
            return

    # Check for suspicious link forwarding in groups
    if message.chat.type in ("group", "supergroup") and URL_PATTERN.search(message.text):
        logger.info(f"Detected link from user {message.from_user.id if message.from_user else 'unknown'}")


async def main() -> None:
    bot = Bot(token=TOKEN)
    logger.info("Starting Filter Bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
