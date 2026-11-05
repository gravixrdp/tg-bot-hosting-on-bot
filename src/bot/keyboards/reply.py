"""
Persistent Reply Keyboards for the Master Telegram Bot Interface.

Provides the bottom pinned keyboard menu with access to bot hosting, management,
system diagnostics, help documentation, and administrative controls.
"""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src.core.config import settings


def get_main_menu_keyboard(
    is_admin: bool = False,
    telegram_id: int | None = None,
) -> ReplyKeyboardMarkup:
    """
    Construct the persistent bottom reply keyboard.

    Row 1: [ 🚀 Host New Bot ] [ 🤖 My Bots ]
    Row 2: [ 📊 System Status ] [ ❓ Help & Guide ]
    Row 3: [ 👑 Admin Panel ] (included only for admins)
    """
    has_admin = is_admin or (telegram_id is not None and telegram_id in settings.ADMIN_IDS)

    keyboard = [
        [
            KeyboardButton(text="🚀 Host New Bot"),
            KeyboardButton(text="🤖 My Bots"),
        ],
        [
            KeyboardButton(text="📊 System Status"),
            KeyboardButton(text="❓ Help & Guide"),
        ],
    ]

    if has_admin:
        keyboard.append([KeyboardButton(text="👑 Admin Panel")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Select an option from the menu...",
    )
