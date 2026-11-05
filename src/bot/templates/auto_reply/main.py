"""
Auto-Reply Telegram Bot Template.

Automatically matches keywords in incoming messages and responds
with predefined answers. Ideal for customer support, FAQ, and business bots.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AutoReplyBot")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logger.error("FATAL: BOT_TOKEN environment variable is not set!")
    sys.exit(1)

# Default keyword triggers and their corresponding responses
DEFAULT_RESPONSES = {
    "price": "💰 <b>Our Pricing Plans:</b>\n• Free Tier: $0/month\n• Pro Tier: $9.99/month\n• Enterprise: Contact us!",
    "support": "🛠️ <b>Customer Support:</b>\nPlease email support@example.com or reach out to our team @SupportAdmin.",
    "hours": "⏰ <b>Operating Hours:</b>\nWe are available 24/7 across all timezones.",
    "contact": "📫 <b>Contact Us:</b>\nWebsite: https://example.com\nTelegram: @OfficialChannel",
    "features": "✨ <b>Key Features:</b>\n1. Instant auto-replies\n2. 24/7 uptime\n3. Scalable architecture",
}

dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    """Handle /start command."""
    await message.answer(
        "👋 <b>Welcome to Auto-Reply Bot!</b>\n\n"
        "Ask me anything or mention keywords like:\n"
        "• <code>price</code>\n"
        "• <code>support</code>\n"
        "• <code>hours</code>\n"
        "• <code>contact</code>\n"
        "• <code>features</code>\n\n"
        "Use /triggers to see all active keyword responses.",
        parse_mode=ParseMode.HTML,
    )


@dp.message(Command("triggers"))
async def handle_triggers(message: types.Message) -> None:
    """List all supported trigger keywords."""
    keys = "\n".join(f"• <code>{k}</code>" for k in DEFAULT_RESPONSES.keys())
    await message.answer(
        f"📋 <b>Configured Triggers:</b>\n{keys}",
        parse_mode=ParseMode.HTML,
    )


@dp.message()
async def handle_keywords(message: types.Message) -> None:
    """Check text for keywords and reply with the matching answer."""
    if not message.text:
        return

    text_lower = message.text.lower()
    for keyword, response in DEFAULT_RESPONSES.items():
        if keyword in text_lower:
            await message.reply(response, parse_mode=ParseMode.HTML)
            return

    # Fallback response
    await message.reply(
        "🤖 I didn't recognize that inquiry. Try typing <b>support</b>, <b>price</b>, or send /triggers.",
        parse_mode=ParseMode.HTML,
    )


async def main() -> None:
    bot = Bot(token=TOKEN)
    logger.info("Starting Auto-Reply Bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
