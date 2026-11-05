"""
System Status and Resource Telemetry Dashboard Handler.

Displays real-time server health, CPU/RAM/Disk metrics via psutil,
and platform-wide bot process statistics.
"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.utils import get_system_metrics
from src.core.database import get_all_bots, get_or_create_user, get_session, get_user_bots
from src.core.supervisor import supervisor

router = Router(name="status")


def get_status_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard to refresh system metrics."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Refresh Status",
                    callback_data="refresh_system_status",
                ),
            ]
        ]
    )


@router.message(Command("status"))
@router.message(F.text == "📊 System Status")
@router.callback_query(F.data == "refresh_system_status")
async def handle_system_status(event: types.Message | types.CallbackQuery) -> None:
    """Render comprehensive server and platform operational status."""
    user_id = event.from_user.id if event.from_user else 0
    metrics = get_system_metrics()

    # Query database metrics
    async with get_session() as session:
        all_bots = await get_all_bots(session)
        user = await get_or_create_user(session, user_id)
        user_bots = await get_user_bots(session, user_id)

    total_bots_count = len(all_bots)
    user_bots_count = len(user_bots)
    max_bots_quota = user.max_bots

    # Calculate active running processes in supervisor
    running_bots_count = sum(1 for b in all_bots if supervisor.is_running(b.id))

    status_text = (
        "📊 <b>System & Platform Diagnostics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💻 <b>Host System Resources:</b>\n"
        f"• <b>CPU Utilization:</b> <code>{metrics['cpu_percent']}%</code> ({metrics['cpu_cores']} logical cores)\n"
        f"• <b>RAM Usage:</b> <code>{metrics['ram_used_gb']} GB</code> / <code>{metrics['ram_total_gb']} GB</code> ({metrics['ram_percent']}%)\n"
        f"• <b>Disk Usage:</b> <code>{metrics['disk_used_gb']} GB</code> / <code>{metrics['disk_total_gb']} GB</code> ({metrics['disk_percent']}%)\n"
        f"• <b>Host Uptime:</b> <code>{metrics['uptime_str']}</code>\n\n"
        "🤖 <b>Bot Platform Telemetry:</b>\n"
        f"• <b>Total Hosted Bots:</b> <code>{total_bots_count}</code>\n"
        f"• <b>Active Running Bots:</b> <code>{running_bots_count}</code>\n"
        f"• <b>Platform Health:</b> 🟢 <b>Operational</b>\n\n"
        "👤 <b>Your Account Quota:</b>\n"
        f"• <b>Allocated Bots:</b> <code>{user_bots_count}</code> / <code>{max_bots_quota}</code> used\n"
        f"• <b>Remaining Capacity:</b> <code>{max(0, max_bots_quota - user_bots_count)}</code> bots\n"
    )

    reply_kb = get_status_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.answer("Status refreshed")
        if event.message:
            await event.message.edit_text(status_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
    else:
        await event.answer(status_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
