"""
Interactive Inline Keyboards for the Telegram Bot UI.

Contains inline menus for deployment workflows, bot lifecycle controls,
template selectors, log viewers, and administrative panels.
"""

from __future__ import annotations

from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.utils import apply_font_style
from src.core.database import BotStatus, HostedBot


def get_deployment_methods_keyboard(font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline buttons for selecting a bot deployment source."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("📦 Upload Zip Archive", font_style),
                    callback_data="deploy_type:zip",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("📄 Upload Single Script (.py)", font_style),
                    callback_data="deploy_type:single_file",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🌐 Deploy from GitHub", font_style),
                    callback_data="deploy_type:github",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("⚡ Pre-built Templates", font_style),
                    callback_data="deploy_type:template",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("❌ Cancel", font_style),
                    callback_data="cancel_flow",
                ),
            ],
        ]
    )


def get_templates_keyboard(font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline buttons for selecting a pre-built bot template."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("📢 Broadcast Bot", font_style),
                    callback_data="template_select:broadcast",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("💬 Auto-Reply Bot", font_style),
                    callback_data="template_select:auto_reply",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔍 Filter Bot", font_style),
                    callback_data="template_select:filter",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("🔁 Echo Bot", font_style),
                    callback_data="template_select:echo",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔙 Back to Deployment Menu", font_style),
                    callback_data="host_menu_back",
                ),
            ],
        ]
    )


def get_bots_list_keyboard(bots: List[HostedBot], font_style: str = "plain") -> InlineKeyboardMarkup:
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
                text=f"{icon} {apply_font_style(b.name, font_style)} (ID: {b.id})",
                callback_data=f"bot_manage:{b.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text=apply_font_style("🚀 Host New Bot", font_style),
            callback_data="host_new_bot_action",
        ),
        InlineKeyboardButton(
            text=apply_font_style("🔄 Refresh", font_style),
            callback_data="refresh_bots_list",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_bot_control_keyboard(bot_id: int, is_running: bool, font_style: str = "plain") -> InlineKeyboardMarkup:
    """
    Construct the full bot control inline keyboard.

    Row 1: [ ▶️ Start ] or [ ⏹️ Stop ]
    Row 2: [ 🔄 Restart ] [ 📜 Live Logs ]
    Row 3: [ ⚙️ Env Vars ] [ 🗑️ Delete ]
    Row 4: [ 🔙 Back to My Bots ]
    """
    start_stop_button = (
        InlineKeyboardButton(
            text=apply_font_style("⏹️ Stop", font_style),
            callback_data=f"bot_stop:{bot_id}",
        )
        if is_running
        else InlineKeyboardButton(
            text=apply_font_style("▶️ Start", font_style),
            callback_data=f"bot_start:{bot_id}",
        )
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [start_stop_button],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔄 Restart", font_style),
                    callback_data=f"bot_restart:{bot_id}",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("📜 Live Logs", font_style),
                    callback_data=f"bot_logs:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("⚙️ Env Vars", font_style),
                    callback_data=f"bot_env:{bot_id}",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("🗑️ Delete", font_style),
                    callback_data=f"bot_delete_prompt:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔙 Back to My Bots", font_style),
                    callback_data="back_to_my_bots",
                ),
            ],
        ]
    )


def get_logs_keyboard(bot_id: int, font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard for live logs view."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔄 Refresh Logs", font_style),
                    callback_data=f"bot_logs_refresh:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔙 Back to Bot", font_style),
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_delete_confirm_keyboard(bot_id: int, font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard confirming permanent bot deletion."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("⚠️ Yes, Permanently Delete", font_style),
                    callback_data=f"bot_delete_confirm:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("❌ Cancel", font_style),
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_env_vars_keyboard(bot_id: int, has_vars: bool = False, font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard for environment variable management."""
    rows = [
        [
            InlineKeyboardButton(
                text=apply_font_style("➕ Add / Edit Variable", font_style),
                callback_data=f"env_add:{bot_id}",
            ),
        ]
    ]
    if has_vars:
        rows.append([
            InlineKeyboardButton(
                text=apply_font_style("🗑️ Delete Variable", font_style),
                callback_data=f"env_del:{bot_id}",
            ),
        ])

    rows.append([
        InlineKeyboardButton(
            text=apply_font_style("🔙 Back to Bot", font_style),
            callback_data=f"bot_manage:{bot_id}",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_admin_menu_keyboard(font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard for the administrative master control panel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("📊 Platform Overview", font_style),
                    callback_data="admin_stats",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("👥 User Quota Manager", font_style),
                    callback_data="admin_users",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🛑 Running Bots Monitor", font_style),
                    callback_data="admin_running_bots",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("📢 Global Announcement", font_style),
                    callback_data="admin_broadcast",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔄 Refresh Panel", font_style),
                    callback_data="admin_refresh",
                ),
            ],
        ]
    )


def get_admin_user_quota_keyboard(target_user_id: int, font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard to adjust an individual user's bot hosting quota."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("➕ Quota +1", font_style),
                    callback_data=f"quota_mod:{target_user_id}:+1",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("➕ Quota +5", font_style),
                    callback_data=f"quota_mod:{target_user_id}:+5",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("➖ Quota -1", font_style),
                    callback_data=f"quota_mod:{target_user_id}:-1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("✏️ Set Custom Value", font_style),
                    callback_data=f"quota_set:{target_user_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔙 Back to Admin", font_style),
                    callback_data="admin_refresh",
                ),
            ],
        ]
    )


def get_admin_running_bots_keyboard(running_bots: List[HostedBot], font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return list of running bots with options for force termination."""
    rows = []
    for bot in running_bots:
        rows.append([
            InlineKeyboardButton(
                text=f"🛑 Stop: {apply_font_style(bot.name, font_style)} (PID: {bot.pid or '?'})",
                callback_data=f"admin_kill:{bot.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text=apply_font_style("🔄 Refresh Running Bots", font_style),
            callback_data="admin_running_bots",
        ),
        InlineKeyboardButton(
            text=apply_font_style("🔙 Back to Admin", font_style),
            callback_data="admin_refresh",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_broadcast_confirm_keyboard(font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard for confirming a global broadcast dispatch."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("📢 Confirm & Send Broadcast", font_style),
                    callback_data="broadcast_confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("❌ Cancel Broadcast", font_style),
                    callback_data="broadcast_cancel",
                ),
            ],
        ]
    )


def get_crash_alert_keyboard(bot_id: int, font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return inline keyboard sent to bot owner on unexpected crash alert."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("🔄 Restart Bot", font_style),
                    callback_data=f"bot_restart:{bot_id}",
                ),
                InlineKeyboardButton(
                    text=apply_font_style("📜 View Logs", font_style),
                    callback_data=f"bot_logs:{bot_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=apply_font_style("⚙️ Open Bot Controls", font_style),
                    callback_data=f"bot_manage:{bot_id}",
                ),
            ],
        ]
    )


def get_cancel_inline_keyboard(font_style: str = "plain") -> InlineKeyboardMarkup:
    """Return simple inline cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=apply_font_style("❌ Cancel Operation", font_style),
                    callback_data="cancel_flow",
                ),
            ]
        ]
    )

