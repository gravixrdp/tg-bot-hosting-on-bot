"""
Persistent Reply Keyboards for the Master Telegram Bot Interface.

Provides the bottom pinned keyboard menu with access to bot hosting, management,
system diagnostics, help documentation, and administrative controls.
"""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src.bot.utils import apply_font_style
from src.core.config import settings

# Canonical base button labels
BUTTON_HOST_BOT = "🚀 Host New Bot"
BUTTON_MY_BOTS = "🤖 My Bots"
BUTTON_SYSTEM_STATUS = "📊 System Status"
BUTTON_HELP_GUIDE = "❓ Help & Guide"
BUTTON_ADMIN_PANEL = "👑 Admin Panel"


def get_main_menu_buttons(
    is_admin: bool = False,
    telegram_id: int | None = None,
    font_style: str | None = None,
) -> list[str]:
    """
    Return the flat list of formatted main menu button texts.
    """
    has_admin = is_admin or (telegram_id is not None and telegram_id in settings.ADMIN_IDS)
    style = font_style if font_style is not None else getattr(settings, "DEFAULT_BUTTON_FONT_STYLE", "plain")

    buttons = [
        apply_font_style(BUTTON_HOST_BOT, style),
        apply_font_style(BUTTON_MY_BOTS, style),
        apply_font_style(BUTTON_SYSTEM_STATUS, style),
        apply_font_style(BUTTON_HELP_GUIDE, style),
    ]
    if has_admin:
        buttons.append(apply_font_style(BUTTON_ADMIN_PANEL, style))
    return buttons


def get_main_menu_keyboard(
    is_admin: bool = False,
    telegram_id: int | None = None,
    font_style: str | None = None,
) -> ReplyKeyboardMarkup:
    """
    Construct the persistent bottom reply keyboard with customizable Unicode font styles.

    Row 1: [ 🚀 Host New Bot ] [ 🤖 My Bots ]
    Row 2: [ 📊 System Status ] [ ❓ Help & Guide ]
    Row 3: [ 👑 Admin Panel ] (included only for admins)

    Args:
        is_admin: Flag indicating admin status.
        telegram_id: Telegram ID to check against configured admin IDs.
        font_style: Target font style ('plain', 'bold', 'monospace', 'serif_bold', 'italic').
                    Defaults to settings.DEFAULT_BUTTON_FONT_STYLE.
    """
    has_admin = is_admin or (telegram_id is not None and telegram_id in settings.ADMIN_IDS)
    style = font_style if font_style is not None else getattr(settings, "DEFAULT_BUTTON_FONT_STYLE", "plain")

    keyboard = [
        [
            KeyboardButton(text=apply_font_style(BUTTON_HOST_BOT, style)),
            KeyboardButton(text=apply_font_style(BUTTON_MY_BOTS, style)),
        ],
        [
            KeyboardButton(text=apply_font_style(BUTTON_SYSTEM_STATUS, style)),
            KeyboardButton(text=apply_font_style(BUTTON_HELP_GUIDE, style)),
        ],
    ]

    if has_admin:
        keyboard.append([KeyboardButton(text=apply_font_style(BUTTON_ADMIN_PANEL, style))])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Select an option from the menu...",
    )

