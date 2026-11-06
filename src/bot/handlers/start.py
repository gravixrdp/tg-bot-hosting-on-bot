"""
Start and Help Handlers.

Handles /start initialization, user registration, welcome messaging,
and documentation/help guides.
"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart

from src.bot.keyboards.reply import BUTTON_HELP_GUIDE, get_main_menu_keyboard
from src.bot.utils import ButtonMatchFilter
from src.core.config import settings
from src.core.database import get_or_create_user, get_session

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: types.Message) -> None:
    """Register user in database and display the persistent main menu."""
    from_user = message.from_user
    if not from_user:
        return

    telegram_id = from_user.id
    username = from_user.username
    full_name = from_user.full_name or from_user.first_name
    is_admin_flag = telegram_id in settings.ADMIN_IDS

    async with get_session() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            is_admin=is_admin_flag,
        )
        is_admin = user.is_admin or is_admin_flag

    reply_kb = get_main_menu_keyboard(
        is_admin=is_admin,
        telegram_id=telegram_id,
        font_style=settings.DEFAULT_BUTTON_FONT_STYLE,
    )

    welcome_text = (
        f"👋 <b>Welcome, {full_name}!</b>\n\n"
        f"🚀 <b>Telegram Bot Hosting Platform</b> allows you to host, monitor, and supervise "
        f"your Telegram bots 24/7 with zero server configuration.\n\n"
        f"✨ <b>Core Features:</b>\n"
        f"• 📦 <b>Flexible Deployment:</b> Zip archives, single <code>.py</code> scripts, GitHub repos, or pre-built templates.\n"
        f"• 🛡️ <b>Sandboxed Execution:</b> Private virtual environments with automated dependency installation.\n"
        f"• ⚡ <b>Process Supervisor:</b> Crash detection, auto-restart policies, and live log streaming.\n"
        f"• ⚙️ <b>Environment Variables:</b> Secure per-bot configuration.\n\n"
        f"Choose an option from the persistent menu below to get started!"
    )

    await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)


@router.message(Command("help"))
@router.message(ButtonMatchFilter(BUTTON_HELP_GUIDE, "Help & Guide"))
async def handle_help(message: types.Message) -> None:
    """Display comprehensive usage guide and deployment instructions."""
    help_text = (
        "📖 <b>Telegram Bot Hosting - Platform Guide</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Deployment Methods:</b>\n\n"
        "1️⃣ <b>Zip Archive Upload:</b>\n"
        "• Package your bot project into a <code>.zip</code> file.\n"
        "• Ensure an entry point exists (e.g., <code>bot.py</code> or <code>main.py</code>).\n"
        "• Include <code>requirements.txt</code> if your code uses external packages.\n"
        "• Upload the zip when prompted; we will safely extract and configure it.\n\n"
        "2️⃣ <b>Single Python Script:</b>\n"
        "• Upload a standalone <code>.py</code> file.\n"
        "• Perfect for lightweight bots and rapid prototyping.\n\n"
        "3️⃣ <b>GitHub Repository:</b>\n"
        "• Provide a public repository URL (e.g., <code>https://github.com/user/mybot.git</code>).\n"
        "• The platform will clone and set up the workspace automatically.\n\n"
        "4️⃣ <b>Pre-Built Templates:</b>\n"
        "• Choose from Echo, Broadcast, Auto-Reply, or Filter bots.\n"
        "• Just paste your @BotFather token to launch instantly!\n\n"
        "📊 <b>Bot Controls:</b>\n"
        "• Click <b>🤖 My Bots</b> to view statuses (🟢 RUNNING, ⏹️ STOPPED, ⚠️ CRASHED).\n"
        "• Start, Stop, or Restart your processes at any time.\n"
        "• Inspect live output logs in real time via in-memory buffers.\n\n"
        "💡 <i>Tip: Use /cancel at any time during deployment to abort the workflow.</i>"
    )

    await message.answer(help_text, parse_mode=ParseMode.HTML)
