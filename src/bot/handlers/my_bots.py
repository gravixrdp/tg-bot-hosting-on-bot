"""
My Bots Management Handlers.

Provides interactive dashboards for viewing hosted bots, real-time status badges,
process lifecycle controls (Start, Stop, Restart), live log streaming,
environment variable management, and secure bot deletion.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.bot.keyboards.inline import (
    get_bot_control_keyboard,
    get_bots_list_keyboard,
    get_cancel_inline_keyboard,
    get_delete_confirm_keyboard,
    get_env_vars_keyboard,
    get_logs_keyboard,
)
from src.bot.states import EnvVarStates
from src.bot.utils import format_bot_card, mask_token
from src.core.database import (
    delete_bot,
    get_bot,
    get_bot_logs_from_db,
    get_session,
    get_user_bots,
    update_bot_env_vars,
)
from src.core.sandbox import BotSandbox
from src.core.supervisor import supervisor

router = Router(name="my_bots")


@router.message(Command("mybots"))
@router.message(F.text == "🤖 My Bots")
@router.callback_query(F.data == "back_to_my_bots")
@router.callback_query(F.data == "refresh_bots_list")
async def handle_my_bots(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
) -> None:
    """Render the dashboard listing all bots owned by the user."""
    await state.clear()
    user_id = event.from_user.id if event.from_user else 0
    if not user_id:
        return

    async with get_session() as session:
        bots = await get_user_bots(session, user_id)

    if not bots:
        text = (
            "🤖 <b>My Hosted Bots</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You do not have any hosted bots yet.\n\n"
            "Deploy your first bot using <b>🚀 Host New Bot</b>!"
        )
        reply_kb = get_bots_list_keyboard([])
    else:
        text = (
            f"🤖 <b>My Hosted Bots ({len(bots)} active)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Select a bot below to access live controls, view logs, or adjust settings:"
        )
        reply_kb = get_bots_list_keyboard(bots)

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
    else:
        await event.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)


@router.callback_query(F.data.startswith("bot_manage:"))
async def handle_bot_details(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Display individual bot details card and operational control buttons."""
    await state.clear()
    bot_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id if callback.from_user else 0

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        await callback.answer("Bot not found!", show_alert=True)
        return

    # Check permission (owner only)
    if bot.user_id != user_id:
        await callback.answer("You are not authorized to manage this bot.", show_alert=True)
        return

    is_running = supervisor.is_running(bot_id)
    active_pid = supervisor._processes[bot_id].pid if is_running else None
    card_text = format_bot_card(bot, is_running=is_running, pid=active_pid)
    keyboard = get_bot_control_keyboard(bot_id, is_running=is_running)

    if callback.message:
        await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ---------------------------------------------------------------------------
# Bot Lifecycle Controls: Start, Stop, Restart
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bot_start:"))
async def handle_bot_start(callback: types.CallbackQuery) -> None:
    """Start an inactive bot process."""
    bot_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Starting bot process...")

    success, message = await supervisor.start_bot(bot_id)

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        return

    is_running = supervisor.is_running(bot_id)
    active_pid = supervisor._processes[bot_id].pid if is_running else None
    card_text = format_bot_card(bot, is_running=is_running, pid=active_pid)

    if not success:
        card_text += f"\n⚠️ <b>Start Notice:</b>\n<code>{html.escape(message)}</code>"

    keyboard = get_bot_control_keyboard(bot_id, is_running=is_running)
    if callback.message:
        await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data.startswith("bot_stop:"))
async def handle_bot_stop(callback: types.CallbackQuery) -> None:
    """Terminate an active bot process."""
    bot_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Stopping bot process...")

    success, message = await supervisor.stop_bot(bot_id)

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        return

    is_running = supervisor.is_running(bot_id)
    card_text = format_bot_card(bot, is_running=is_running, pid=None)
    keyboard = get_bot_control_keyboard(bot_id, is_running=is_running)

    if callback.message:
        await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data.startswith("bot_restart:"))
async def handle_bot_restart(callback: types.CallbackQuery) -> None:
    """Restart a bot process cleanly."""
    bot_id = int(callback.data.split(":", 1)[1])
    await callback.answer("Restarting bot process...")

    success, message = await supervisor.restart_bot(bot_id)

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        return

    is_running = supervisor.is_running(bot_id)
    active_pid = supervisor._processes[bot_id].pid if is_running else None
    card_text = format_bot_card(bot, is_running=is_running, pid=active_pid)

    if not success:
        card_text += f"\n⚠️ <b>Restart Notice:</b>\n<code>{html.escape(message)}</code>"

    keyboard = get_bot_control_keyboard(bot_id, is_running=is_running)
    if callback.message:
        await callback.message.edit_text(card_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Live Log Streaming & Viewer
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bot_logs:"))
@router.callback_query(F.data.startswith("bot_logs_refresh:"))
async def handle_bot_logs(callback: types.CallbackQuery) -> None:
    """Display the latest output logs from memory ring buffers and database."""
    bot_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        await callback.answer("Bot not found!", show_alert=True)
        return

    # Retrieve memory logs first
    logs = supervisor.get_logs(bot_id, lines=30)
    if not logs:
        # Fallback to database persisted logs
        async with get_session() as session:
            db_entries = await get_bot_logs_from_db(session, bot_id, limit=30)
            logs = [f"[{e.timestamp.strftime('%H:%M:%S')}] [{e.stream.upper()}] {e.message}" for e in db_entries]

    log_content = "\n".join(logs) if logs else "No log entries recorded yet. Start the bot to generate logs."
    # Truncate if exceeding Telegram message limits (4096 chars)
    if len(log_content) > 3500:
        log_content = "..." + log_content[-3500:]

    escaped_logs = html.escape(log_content)
    text = (
        f"📜 <b>Live Output Logs: {bot.name} (ID: {bot.id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<pre>{escaped_logs}</pre>"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_logs_keyboard(bot_id),
        )
    await callback.answer("Logs updated")


# ---------------------------------------------------------------------------
# Bot Deletion Handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bot_delete_prompt:"))
async def handle_delete_prompt(callback: types.CallbackQuery) -> None:
    """Ask confirmation before permanently deleting a bot."""
    bot_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        await callback.answer("Bot not found!", show_alert=True)
        return

    text = (
        f"⚠️ <b>Delete Confirmation: '{bot.name}' (ID: {bot.id})</b>\n\n"
        f"Are you sure you want to permanently delete this bot?\n\n"
        f"• The process will be terminated if running.\n"
        f"• Its workspace sandbox and virtualenv will be deleted.\n"
        f"• All execution logs will be purged.\n\n"
        f"<i>This action cannot be undone.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_delete_confirm_keyboard(bot_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bot_delete_confirm:"))
async def handle_delete_confirm(callback: types.CallbackQuery) -> None:
    """Execute permanent deletion of a bot."""
    bot_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id if callback.from_user else 0

    await callback.answer("Deleting bot...")

    # Terminate process if running
    if supervisor.is_running(bot_id):
        await supervisor.stop_bot(bot_id)

    # Clean sandbox directory
    sandbox = BotSandbox(bot_id)
    sandbox.clean_workspace()

    # Delete from database
    async with get_session() as session:
        bot = await get_bot(session, bot_id)
        bot_name = bot.name if bot else f"Bot {bot_id}"
        await delete_bot(session, bot_id)
        remaining_bots = await get_user_bots(session, user_id)

    text = (
        f"✅ <b>'{bot_name}' deleted successfully!</b>\n\n"
        f"Select another bot or host a new one below:"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_bots_list_keyboard(remaining_bots),
        )


# ---------------------------------------------------------------------------
# Environment Variables Management
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bot_env:"))
async def handle_env_vars_view(callback: types.CallbackQuery, state: FSMContext) -> None:
    """View and manage environment variables configured for a bot."""
    await state.clear()
    bot_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot:
        await callback.answer("Bot not found!", show_alert=True)
        return

    env_dict = bot.env_vars or {}
    has_vars = bool(env_dict)

    if not has_vars:
        vars_text = "<i>No custom environment variables configured.</i>"
    else:
        lines = []
        for k, v in env_dict.items():
            # Mask sensitive values
            if any(s in k.upper() for s in ("TOKEN", "SECRET", "KEY", "PASS")):
                val_str = mask_token(str(v))
            else:
                val_str = html.escape(str(v))
            lines.append(f"• <code>{html.escape(k)}</code> = <code>{val_str}</code>")
        vars_text = "\n".join(lines)

    text = (
        f"⚙️ <b>Environment Variables: {bot.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{vars_text}\n\n"
        f"💡 Variables are injected into the bot process on startup."
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_env_vars_keyboard(bot_id, has_vars=has_vars),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("env_add:"))
async def handle_env_add_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt user to supply a KEY=VALUE pair."""
    bot_id = int(callback.data.split(":", 1)[1])
    await state.update_data(env_bot_id=bot_id)

    text = (
        "⚙️ <b>Add / Update Environment Variable</b>\n\n"
        "Please send your variable in <code>KEY=VALUE</code> format:\n"
        "e.g. <code>OPENAI_API_KEY=sk-proj-12345</code> or <code>DEBUG=True</code>\n\n"
        "<i>Send /cancel to abort.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_inline_keyboard(),
        )
    await state.set_state(EnvVarStates.waiting_for_var_key_value)
    await callback.answer()


@router.message(EnvVarStates.waiting_for_var_key_value)
async def handle_env_key_value_input(message: types.Message, state: FSMContext) -> None:
    """Parse and save the KEY=VALUE environment variable."""
    text = (message.text or "").strip()
    if "=" not in text:
        await message.reply(
            "⚠️ Format error. Please provide the variable in <code>KEY=VALUE</code> format.",
            parse_mode=ParseMode.HTML,
        )
        return

    key, value = text.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        await message.reply("⚠️ Variable key name must be alphanumeric and start with a letter or underscore.")
        return

    data = await state.get_data()
    bot_id = data.get("env_bot_id")
    if not bot_id:
        await state.clear()
        return

    async with get_session() as session:
        bot = await get_bot(session, bot_id)
        if not bot:
            await message.reply("Bot not found.")
            await state.clear()
            return

        current_env = dict(bot.env_vars or {})
        current_env[key] = value
        await update_bot_env_vars(session, bot_id, current_env)

    await state.clear()
    await message.answer(
        f"✅ Saved variable <code>{html.escape(key)}</code>.\n"
        f"Restart the bot for changes to take effect.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=supervisor.is_running(bot_id)),
    )


@router.callback_query(F.data.startswith("env_del:"))
async def handle_env_delete_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt user to choose which environment variable to delete."""
    bot_id = int(callback.data.split(":", 1)[1])
    await state.update_data(env_bot_id=bot_id)

    async with get_session() as session:
        bot = await get_bot(session, bot_id)

    if not bot or not bot.env_vars:
        await callback.answer("No environment variables to delete.", show_alert=True)
        return

    keys_list = "\n".join(f"• <code>{html.escape(k)}</code>" for k in bot.env_vars.keys())
    text = (
        f"🗑️ <b>Delete Environment Variable</b>\n\n"
        f"Active keys:\n{keys_list}\n\n"
        f"Please send the exact name of the key to delete:\n"
        f"<i>Send /cancel to abort.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_inline_keyboard(),
        )
    await state.set_state(EnvVarStates.waiting_for_delete_key)
    await callback.answer()


@router.message(EnvVarStates.waiting_for_delete_key)
async def handle_env_delete_input(message: types.Message, state: FSMContext) -> None:
    """Delete the requested key from bot's environment variables."""
    key = (message.text or "").strip()
    data = await state.get_data()
    bot_id = data.get("env_bot_id")
    if not bot_id:
        await state.clear()
        return

    async with get_session() as session:
        bot = await get_bot(session, bot_id)
        if not bot:
            await state.clear()
            return

        current_env = dict(bot.env_vars or {})
        if key in current_env:
            del current_env[key]
            await update_bot_env_vars(session, bot_id, current_env)
            msg = f"✅ Deleted variable <code>{html.escape(key)}</code>."
        else:
            msg = f"⚠️ Variable <code>{html.escape(key)}</code> not found."

    await state.clear()
    await message.answer(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=supervisor.is_running(bot_id)),
    )
