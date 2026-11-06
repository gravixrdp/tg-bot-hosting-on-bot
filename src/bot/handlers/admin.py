"""
Administrator Master Control Panel Handler.

Provides privileged operations:
1. Global platform statistics and resource monitoring
2. User quota management (search, increment, decrement, custom value)
3. Running bots monitor with force-kill / termination capability
4. Global announcement broadcasting to all registered users
"""

from __future__ import annotations

import asyncio
import html
from typing import Optional

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from src.bot.keyboards.inline import (
    get_admin_menu_keyboard,
    get_admin_running_bots_keyboard,
    get_admin_user_quota_keyboard,
    get_broadcast_confirm_keyboard,
    get_cancel_inline_keyboard,
)
from src.bot.keyboards.reply import BUTTON_ADMIN_PANEL
from src.bot.states import AdminStates
from src.bot.utils import ButtonMatchFilter, format_status_badge, get_system_metrics
from src.core.config import settings
from src.core.database import (
    HostedBot,
    User,
    get_all_bots,
    get_bot,
    get_session,
    get_user,
    get_user_bots,
    update_user_max_bots,
)
from src.core.supervisor import supervisor

router = Router(name="admin")


async def is_admin_authorized(user_id: int) -> bool:
    """Verify whether a Telegram user holds administrative rights."""
    if user_id in settings.ADMIN_IDS:
        return True
    async with get_session() as session:
        user = await get_user(session, user_id)
        return bool(user and user.is_admin)


# ---------------------------------------------------------------------------
# Admin Panel Main Entry
# ---------------------------------------------------------------------------

@router.message(Command("admin"))
@router.message(ButtonMatchFilter(BUTTON_ADMIN_PANEL, "Admin Panel"))
@router.callback_query(F.data == "admin_refresh")
async def handle_admin_dashboard(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
) -> None:
    """Render the master administrative control center."""
    await state.clear()
    user_id = event.from_user.id if event.from_user else 0

    if not await is_admin_authorized(user_id):
        access_denied_text = "⛔ <b>Access Denied.</b> You do not have administrator permissions."
        if isinstance(event, types.CallbackQuery):
            await event.answer("Access Denied", show_alert=True)
            if event.message:
                await event.message.edit_text(access_denied_text, parse_mode=ParseMode.HTML)
        else:
            await event.answer(access_denied_text, parse_mode=ParseMode.HTML)
        return

    metrics = get_system_metrics()

    async with get_session() as session:
        all_bots = await get_all_bots(session)
        user_stmt = select(User)
        user_res = await session.execute(user_stmt)
        all_users = list(user_res.scalars().all())

    total_users_count = len(all_users)
    total_bots_count = len(all_bots)
    running_bots_count = sum(1 for b in all_bots if supervisor.is_running(b.id))

    panel_text = (
        "👑 <b>Administrator Master Control Center</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>Quick Platform Telemetry:</b>\n"
        f"• <b>Total Registered Users:</b> <code>{total_users_count}</code>\n"
        f"• <b>Total Hosted Bots:</b> <code>{total_bots_count}</code>\n"
        f"• <b>Active Running Processes:</b> <code>{running_bots_count}</code>\n\n"
        "💻 <b>Server Health:</b>\n"
        f"• <b>CPU:</b> <code>{metrics['cpu_percent']}%</code> | <b>RAM:</b> <code>{metrics['ram_percent']}%</code>\n"
        f"• <b>Disk:</b> <code>{metrics['disk_used_gb']}/{metrics['disk_total_gb']} GB</code>\n\n"
        "Select an administrative module below to proceed:"
    )

    reply_kb = get_admin_menu_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.edit_text(panel_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
    else:
        await event.answer(panel_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)


# ---------------------------------------------------------------------------
# Module 1: Detailed Platform Overview
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: types.CallbackQuery) -> None:
    """Display comprehensive system, database, and process metrics."""
    metrics = get_system_metrics()

    async with get_session() as session:
        all_bots = await get_all_bots(session)
        user_res = await session.execute(select(User))
        all_users = list(user_res.scalars().all())

    running_bots = [b for b in all_bots if supervisor.is_running(b.id)]

    stats_text = (
        "📊 <b>Platform Global Analytics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👥 <b>User Base:</b>\n"
        f"• Total registered accounts: <b>{len(all_users)}</b>\n"
        f"• Admin accounts: <b>{sum(1 for u in all_users if u.is_admin)}</b>\n\n"
        "🤖 <b>Bot Fleets:</b>\n"
        f"• Total bots provisioned: <b>{len(all_bots)}</b>\n"
        f"• Active running: <b>{len(running_bots)}</b>\n"
        f"• Inactive / Stopped: <b>{len(all_bots) - len(running_bots)}</b>\n\n"
        "💻 <b>Host Machine Diagnostics:</b>\n"
        f"• CPU Load: <code>{metrics['cpu_percent']}%</code> ({metrics['cpu_cores']} cores)\n"
        f"• RAM Usage: <code>{metrics['ram_used_gb']} GB</code> / <code>{metrics['ram_total_gb']} GB</code> ({metrics['ram_percent']}%)\n"
        f"• Disk Space: <code>{metrics['disk_used_gb']} GB</code> / <code>{metrics['disk_total_gb']} GB</code>\n"
        f"• System Uptime: <code>{metrics['uptime_str']}</code>"
    )

    if callback.message:
        await callback.message.edit_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_menu_keyboard(),
        )
    await callback.answer()


# ---------------------------------------------------------------------------
# Module 2: User Quota Management
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_users")
async def handle_admin_users_search_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt the administrator to enter a user's Telegram ID."""
    text = (
        "👥 <b>User Quota Management</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Please send the numerical <b>Telegram User ID</b> of the account you wish to inspect and manage:\n\n"
        "<i>Send /cancel to return to dashboard.</i>"
    )
    if callback.message:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
    await state.set_state(AdminStates.waiting_for_user_search)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_search)
async def handle_admin_user_lookup(message: types.Message, state: FSMContext) -> None:
    """Look up user by Telegram ID and present quota management controls."""
    raw_id = (message.text or "").strip()
    if not raw_id.isdigit():
        await message.reply("⚠️ Please provide a valid numerical Telegram ID (e.g. <code>123456789</code>).")
        return

    target_id = int(raw_id)
    async with get_session() as session:
        user = await get_user(session, target_id)
        if not user:
            await message.reply(
                f"❌ User with Telegram ID <code>{target_id}</code> was not found in the database.",
                parse_mode=ParseMode.HTML,
            )
            return
        user_bots = await get_user_bots(session, target_id)

    await state.clear()

    info_text = (
        f"👤 <b>User Profile: {html.escape(user.full_name or 'N/A')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"• <b>Username:</b> @{user.username or 'none'}\n"
        f"• <b>Administrator:</b> {'✅ Yes' if user.is_admin else 'No'}\n"
        f"• <b>Current Allowed Quota:</b> <b>{user.max_bots}</b> bots\n"
        f"• <b>Currently Hosted:</b> <b>{len(user_bots)}</b> bots\n\n"
        f"Use the buttons below to modify this user's hosting allowance:"
    )

    await message.answer(
        info_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_user_quota_keyboard(user.id),
    )


@router.callback_query(F.data.startswith("quota_mod:"))
async def handle_admin_quota_delta(callback: types.CallbackQuery) -> None:
    """Modify user quota incrementally (+1, +5, -1)."""
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    delta = int(parts[2])

    async with get_session() as session:
        user = await get_user(session, target_user_id)
        if not user:
            await callback.answer("User not found!", show_alert=True)
            return

        new_quota = max(0, user.max_bots + delta)
        await update_user_max_bots(session, target_user_id, new_quota)
        user_bots = await get_user_bots(session, target_user_id)

    await callback.answer(f"Quota adjusted to {new_quota}")

    updated_text = (
        f"👤 <b>User Profile: {html.escape(user.full_name or 'N/A')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"• <b>Username:</b> @{user.username or 'none'}\n"
        f"• <b>Current Allowed Quota:</b> <b>{new_quota}</b> bots\n"
        f"• <b>Currently Hosted:</b> <b>{len(user_bots)}</b> bots\n\n"
        f"Use the buttons below to modify this user's hosting allowance:"
    )

    if callback.message:
        await callback.message.edit_text(
            updated_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_user_quota_keyboard(target_user_id),
        )


@router.callback_query(F.data.startswith("quota_set:"))
async def handle_admin_quota_custom_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt for a custom numerical quota value."""
    target_user_id = int(callback.data.split(":", 1)[1])
    await state.update_data(target_user_id=target_user_id)

    text = (
        f"✏️ <b>Set Custom Bot Quota</b>\n\n"
        f"Please enter the new integer bot quota for user <code>{target_user_id}</code>:"
    )

    if callback.message:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
    await state.set_state(AdminStates.waiting_for_quota_value)
    await callback.answer()


@router.message(AdminStates.waiting_for_quota_value)
async def handle_admin_quota_custom_value(message: types.Message, state: FSMContext) -> None:
    """Set custom quota value."""
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 0:
        await message.reply("⚠️ Please enter a valid non-negative integer.")
        return

    new_quota = int(text)
    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    async with get_session() as session:
        await update_user_max_bots(session, target_user_id, new_quota)
        user = await get_user(session, target_user_id)
        user_bots = await get_user_bots(session, target_user_id)

    await state.clear()
    await message.answer(
        f"✅ Quota for user <code>{target_user_id}</code> updated to <b>{new_quota}</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_user_quota_keyboard(target_user_id),
    )


# ---------------------------------------------------------------------------
# Module 3: Running Bots Monitor & Force Kill
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_running_bots")
async def handle_admin_running_bots(callback: types.CallbackQuery) -> None:
    """List all currently active running bots with force-kill options."""
    async with get_session() as session:
        all_bots = await get_all_bots(session)

    running_bots = [b for b in all_bots if supervisor.is_running(b.id)]

    if not running_bots:
        text = (
            "🛑 <b>Running Bots Monitor</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "There are currently no active bot processes running on the host."
        )
        keyboard = get_admin_running_bots_keyboard([])
    else:
        text = (
            f"🛑 <b>Running Bots Monitor ({len(running_bots)} active)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Click any bot below to immediately force terminate its process tree:"
        )
        keyboard = get_admin_running_bots_keyboard(running_bots)

    if callback.message:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_kill:"))
async def handle_admin_force_kill(callback: types.CallbackQuery) -> None:
    """Force terminate any running bot process platform-wide."""
    bot_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Force terminating process...")

    success, msg = await supervisor.stop_bot(bot_id, timeout=1.0)

    async with get_session() as session:
        bot = await get_bot(session, bot_id)
        bot_name = bot.name if bot else f"Bot {bot_id}"
        all_bots = await get_all_bots(session)

    running_bots = [b for b in all_bots if supervisor.is_running(b.id)]

    text = (
        f"🛑 <b>Process Terminated:</b> '{bot_name}' (ID: {bot_id})\n"
        f"• Status: <code>{msg}</code>\n\n"
        f"Remaining active processes: <b>{len(running_bots)}</b>"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_running_bots_keyboard(running_bots),
        )


# ---------------------------------------------------------------------------
# Module 4: Global Broadcast Dispatcher
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt the administrator to compose a broadcast message."""
    text = (
        "📢 <b>Global Announcement Broadcast</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the announcement text you wish to broadcast to all registered bot owners.\n\n"
        "<i>Formatting supported: HTML (bold, italic, links). Send /cancel to abort.</i>"
    )
    if callback.message:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
    await state.set_state(AdminStates.waiting_for_broadcast_content)
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast_content)
async def handle_admin_broadcast_preview(message: types.Message, state: FSMContext) -> None:
    """Display a preview of the broadcast message and request confirmation."""
    content = message.text or message.caption or ""
    if not content:
        await message.reply("⚠️ Broadcast message cannot be empty.")
        return

    await state.update_data(broadcast_content=content)

    preview_text = (
        "📢 <b>Broadcast Preview</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{content}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Are you sure you want to dispatch this message to all registered users?"
    )

    await message.answer(
        preview_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "broadcast_confirm")
async def handle_admin_broadcast_dispatch(callback: types.CallbackQuery, bot: Bot, state: FSMContext) -> None:
    """Dispatch broadcast messages asynchronously to all users."""
    data = await state.get_data()
    content = data.get("broadcast_content", "")
    await state.clear()

    if not content:
        await callback.answer("Broadcast expired or empty.", show_alert=True)
        return

    await callback.answer("Starting global broadcast dispatch...")

    async with get_session() as session:
        user_res = await session.execute(select(User))
        all_users = list(user_res.scalars().all())

    total = len(all_users)
    success, failed = 0, 0

    progress_msg = None
    if callback.message:
        progress_msg = await callback.message.edit_text(
            f"🚀 <b>Broadcasting...</b> (0/{total})",
            parse_mode=ParseMode.HTML,
        )

    for idx, u in enumerate(all_users):
        try:
            await bot.send_message(
                chat_id=u.id,
                text=f"📢 <b>Platform Announcement:</b>\n\n{content}",
                parse_mode=ParseMode.HTML,
            )
            success += 1
        except Exception:
            failed += 1

        # Throttle to avoid hitting Telegram flood limits
        if idx % 20 == 0:
            await asyncio.sleep(0.05)

    summary_text = (
        "✅ <b>Broadcast Completed!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Total recipients: <b>{total}</b>\n"
        f"• Successfully delivered: <b>{success}</b>\n"
        f"• Failed / Blocked: <b>{failed}</b>"
    )

    if progress_msg:
        await progress_msg.edit_text(
            summary_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_menu_keyboard(),
        )


@router.callback_query(F.data == "broadcast_cancel")
async def handle_admin_broadcast_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel pending broadcast."""
    await state.clear()
    await callback.answer("Broadcast cancelled")
    if callback.message:
        await callback.message.edit_text(
            "❌ <b>Broadcast cancelled.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_menu_keyboard(),
        )
