"""
Interactive Inline Keyboards for the Telegram Bot UI.

Contains inline menus for deployment workflows, bot lifecycle controls,
template selectors, log viewers, and administrative panels.
"""

from __future__ import annotations

from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.database import BotStatus, HostedBot


def get_deployment_methods_keyboard() -> InlineKeyboardMarkup:
    """Return inline buttons for selecting a bot deployment source."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Upload Zip Archive",
                    callback_data="deploy_type:zip",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📄 Upload Single Script (.py)",
                    callback_data="deploy_type:single_file",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Deploy from GitHub",
                    callback_data="deploy_type:github",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Pre-built Templates",
                    callback_data="deploy_type:template",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="cancel_flow",
                ),
            ],
        ]
    )


def get_templates_keyboard() -> InlineKeyboardMarkup:
    """Return inline buttons for selecting a pre-built bot template."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Broadcast Bot",
                    callback_data="template_select:broadcast",
                ),
                InlineKeyboardButton(
                    text="💬 Auto-Reply Bot",
                    callback_data="template_select:auto_reply",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Filter Bot",
                    callback_data="template_select:filter",
                ),
                InlineKeyboardButton(
                    text="🔁 Echo Bot",
                    callback_data="template_select:echo",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to Deployment Menu",
                    callback_data="host_menu_back",
                ),
            ],
        ]
    )


def get_bots_list_keyboard(bots: List[HostedBot]) -> InlineKeyboardMarkup:
    """Return inline keyboard listing the user's hosted bots with status badges."""
    rows = []
    status_icons = {
        BotStatus.RUNNING: "🟢",
        BotStatus.STOPPED: "⏹️",
        BotStatus.CRASHED: "⚠️",
        BotStatus.STARTING: "🔄",
        BotStatus.ERROR: "❌",
    }

    for b in bots:
        icon = status_icons.get(b.status, "⚪")
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {b.name} (ID: {b.id})",
                callback_data=f"bot_manage:{b.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🚀 Host New Bot",
            callback_data="host_new_bot_action",
        ),
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data="refresh_bots_list",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_bot_control_keyboard(bot_id: int, is_running: bool) -> InlineKeyboardMarkup:
    """
    Construct the full bot control inline keyboard.

    Row 1: [ ▶️ Start ] or [ ⏹️ Stop ]
    Row 2: [ 🔄 Restart ] [ 📜 Live Logs ]
    Row 3: [ ⚙️ Env Vars ] [ 🗑️ Delete ]
    Row 4: [ 🔙 Back to My Bots ]
    """
    start_stop_button = (
        InlineKeyboardButton(
            text="⏹️ Stop",
            callback_data=f"bot_stop:{bot_id}",
        )
        if is_running
        else InlineKeyboardButton(
            text="▶️ Start",
            callback_data=f"bot_start:{bot_id}",
        )
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [start_stop_button],
            [
                InlineKeyboardButton(
                    text="🔄 Restart",
                    callback_data=f"bot_restart:{bot_id}",
                ),
                InlineKeyboardButton(
                    text="📜 Live Logs",
                    callback_data=f"bot_logs:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Env Vars",
                    callback_data=f"bot_env:{bot_id}",
                ),
                InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"bot_delete_prompt:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to My Bots",
                    callback_data="back_to_my_bots",
                ),
            ],
        ]
    )


def get_logs_keyboard(bot_id: int) -> InlineKeyboardMarkup:
    """Return inline keyboard for live logs view."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Refresh Logs",
                    callback_data=f"bot_logs_refresh:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to Bot",
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_delete_confirm_keyboard(bot_id: int) -> InlineKeyboardMarkup:
    """Return inline keyboard confirming permanent bot deletion."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Yes, Permanently Delete",
                    callback_data=f"bot_delete_confirm:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_env_vars_keyboard(bot_id: int, has_vars: bool = False) -> InlineKeyboardMarkup:
    """Return inline keyboard for environment variable management."""
    rows = [
        [
            InlineKeyboardButton(
                text="➕ Add / Edit Variable",
                callback_data=f"env_add:{bot_id}",
            ),
        ]
    ]
    if has_vars:
        rows.append([
            InlineKeyboardButton(
                text="🗑️ Delete Variable",
                callback_data=f"env_del:{bot_id}",
            ),
        ])

    rows.append([
        InlineKeyboardButton(
            text="🔙 Back to Bot",
            callback_data=f"bot_manage:{bot_id}",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard for the administrative master control panel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Platform Overview",
                    callback_data="admin_stats",
                ),
                InlineKeyboardButton(
                    text="👥 User Quota Manager",
                    callback_data="admin_users",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Running Bots Monitor",
                    callback_data="admin_running_bots",
                ),
                InlineKeyboardButton(
                    text="📢 Global Announcement",
                    callback_data="admin_broadcast",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Refresh Panel",
                    callback_data="admin_refresh",
                ),
            ],
        ]
    )


def get_admin_user_quota_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    """Return inline keyboard to adjust an individual user's bot hosting quota."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Quota +1",
                    callback_data=f"quota_mod:{target_user_id}:+1",
                ),
                InlineKeyboardButton(
                    text="➕ Quota +5",
                    callback_data=f"quota_mod:{target_user_id}:+5",
                ),
                InlineKeyboardButton(
                    text="➖ Quota -1",
                    callback_data=f"quota_mod:{target_user_id}:-1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Set Custom Value",
                    callback_data=f"quota_set:{target_user_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to Admin",
                    callback_data="admin_refresh",
                ),
            ],
        ]
    )


def get_admin_running_bots_keyboard(running_bots: List[HostedBot]) -> InlineKeyboardMarkup:
    """Return list of running bots with options for force termination."""
    rows = []
    for bot in running_bots:
        rows.append([
            InlineKeyboardButton(
                text=f"🛑 Stop: {bot.name} (PID: {bot.pid or '?'})",
                callback_data=f"admin_kill:{bot.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🔄 Refresh Running Bots",
            callback_data="admin_running_bots",
        ),
        InlineKeyboardButton(
            text="🔙 Back to Admin",
            callback_data="admin_refresh",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard for confirming a global broadcast dispatch."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Confirm & Send Broadcast",
                    callback_data="broadcast_confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel Broadcast",
                    callback_data="broadcast_cancel",
                ),
            ],
        ]
    )


def get_crash_alert_keyboard(bot_id: int) -> InlineKeyboardMarkup:
    """Return inline keyboard sent to bot owner on unexpected crash alert."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Restart Bot",
                    callback_data=f"bot_restart:{bot_id}",
                ),
                InlineKeyboardButton(
                    text="📜 View Logs",
                    callback_data=f"bot_logs:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Open Bot Controls",
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    """Return simple inline cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancel Operation",
                    callback_data="cancel_flow",
                ),
            ]
        ]
    )
