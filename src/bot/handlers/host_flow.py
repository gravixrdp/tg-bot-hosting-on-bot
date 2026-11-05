"""
Host Bot FSM Flow and Multi-Source Ingestion Handler.

Supports deploying Telegram bots via:
1. Zip archive upload (with Zip-Slip security checks and auto entry point detection)
2. Single Python script (.py upload or code snippet)
3. GitHub repository URL (automated shallow git clone)
4. Pre-built templates (Echo, Broadcast, Auto-Reply, Filter) with @BotFather token setup
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
import shutil
import sys
from typing import Optional

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from src.bot.keyboards.inline import (
    get_bot_control_keyboard,
    get_cancel_inline_keyboard,
    get_deployment_methods_keyboard,
    get_templates_keyboard,
)
from src.bot.keyboards.reply import get_main_menu_keyboard
from src.bot.states import HostBotStates
from src.bot.utils import (
    detect_entry_point,
    format_bot_card,
    is_valid_bot_token,
    sanitize_bot_name,
)
from src.core.config import settings
from src.core.database import (
    create_hosted_bot,
    delete_bot,
    get_or_create_user,
    get_session,
    get_user_bots,
    update_bot_entry_point,
    update_bot_env_vars,
)
from src.core.sandbox import (
    BotSandbox,
    SandboxSecurityError,
    install_requirements,
    safe_extract_zip,
)

router = Router(name="host_flow")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@router.message(Command("cancel"))
@router.callback_query(F.data == "cancel_flow")
async def handle_cancel(event: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    """Abort any active deployment flow and reset FSM state."""
    current_state = await state.get_state()
    await state.clear()

    cancel_text = "❌ <b>Operation cancelled.</b> You can start a new deployment at any time."
    if isinstance(event, types.CallbackQuery):
        await event.answer("Operation cancelled")
        if event.message:
            await event.message.edit_text(cancel_text, parse_mode=ParseMode.HTML)
    else:
        await event.answer(cancel_text, parse_mode=ParseMode.HTML)


@router.message(Command("host"))
@router.message(F.text == "🚀 Host New Bot")
@router.callback_query(F.data == "host_new_bot_action")
async def handle_host_prompt(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
) -> None:
    """Check user quota and initiate the bot deployment wizard."""
    user_id = event.from_user.id if event.from_user else 0
    if not user_id:
        return

    await state.clear()

    # Verify user quota against limits
    async with get_session() as session:
        user = await get_or_create_user(session, user_id)
        user_bots = await get_user_bots(session, user_id)

        if len(user_bots) >= user.max_bots:
            quota_text = (
                f"⚠️ <b>Bot Hosting Quota Reached!</b>\n\n"
                f"You currently have <b>{len(user_bots)}</b> of <b>{user.max_bots}</b> allowed bots.\n\n"
                f"To host a new bot, please delete an existing one in <b>🤖 My Bots</b> "
                f"or contact a platform administrator to request an increased quota."
            )
            if isinstance(event, types.CallbackQuery):
                await event.answer("Quota reached!", show_alert=True)
                if event.message:
                    await event.message.answer(quota_text, parse_mode=ParseMode.HTML)
            else:
                await event.answer(quota_text, parse_mode=ParseMode.HTML)
            return

    intro_text = (
        "🚀 <b>Deploy a New Telegram Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose how you would like to supply your bot's source code:"
    )
    reply_kb = get_deployment_methods_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.edit_text(intro_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
    else:
        await event.answer(intro_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)

    await state.set_state(HostBotStates.choosing_deploy_type)


@router.callback_query(F.data == "host_menu_back")
async def handle_host_menu_back(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return back to the main deployment method selection."""
    intro_text = (
        "🚀 <b>Deploy a New Telegram Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose how you would like to supply your bot's source code:"
    )
    if callback.message:
        await callback.message.edit_text(
            intro_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_deployment_methods_keyboard(),
        )
    await state.set_state(HostBotStates.choosing_deploy_type)
    await callback.answer()


@router.callback_query(HostBotStates.choosing_deploy_type, F.data.startswith("deploy_type:"))
async def handle_deploy_type_chosen(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle deployment source selection."""
    deploy_type = callback.data.split(":", 1)[1]
    await state.update_data(deploy_type=deploy_type)

    if deploy_type == "template":
        text = (
            "⚡ <b>Select a Pre-Built Bot Template:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Choose a ready-to-run template below. You will only need to supply your @BotFather token!"
        )
        if callback.message:
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_templates_keyboard(),
            )
        await state.set_state(HostBotStates.choosing_template)
        await callback.answer()
        return

    type_titles = {
        "zip": "📦 Zip Archive Upload",
        "single_file": "📄 Single Python Script",
        "github": "🌐 Deploy from GitHub",
    }
    title = type_titles.get(deploy_type, "Bot Deployment")

    text = (
        f"<b>{title}</b>\n\n"
        f"📝 <b>Step 1 of 2: Bot Name</b>\n"
        f"Please enter a clean, descriptive name for your bot (e.g. <code>SupportBot</code>):"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_inline_keyboard(),
        )
    await state.set_state(HostBotStates.waiting_for_name)
    await callback.answer()


@router.message(HostBotStates.waiting_for_name)
async def handle_bot_name_input(message: types.Message, state: FSMContext) -> None:
    """Capture bot name and transition to source ingestion step."""
    if not message.text:
        await message.reply("⚠️ Please provide a valid text name for your bot.")
        return

    bot_name = sanitize_bot_name(message.text)
    await state.update_data(bot_name=bot_name)

    data = await state.get_data()
    deploy_type = data.get("deploy_type")

    if deploy_type == "zip":
        text = (
            f"📦 <b>Step 2 of 2: Upload Zip File for '{bot_name}'</b>\n\n"
            f"Please upload your bot project packaged as a <code>.zip</code> file.\n\n"
            f"📋 <b>Requirements:</b>\n"
            f"• Must contain an entry point file (e.g. <code>bot.py</code> or <code>main.py</code>).\n"
            f"• Optional: Include <code>requirements.txt</code> for auto-installing pip dependencies."
        )
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
        await state.set_state(HostBotStates.waiting_for_zip)

    elif deploy_type == "single_file":
        text = (
            f"📄 <b>Step 2 of 2: Upload Script for '{bot_name}'</b>\n\n"
            f"Please upload your Python file (<code>.py</code>) as a document, or paste the code directly."
        )
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
        await state.set_state(HostBotStates.waiting_for_file)

    elif deploy_type == "github":
        text = (
            f"🌐 <b>Step 2 of 2: GitHub Repository URL for '{bot_name}'</b>\n\n"
            f"Please send the public HTTPS clone URL for your repository:\n"
            f"e.g. <code>https://github.com/username/telegram-bot.git</code>"
        )
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
        await state.set_state(HostBotStates.waiting_for_git_url)


# ---------------------------------------------------------------------------
# 1. Zip Upload Ingestion
# ---------------------------------------------------------------------------

@router.message(HostBotStates.waiting_for_zip, F.document)
async def handle_zip_document(message: types.Message, bot: Bot, state: FSMContext) -> None:
    """Handle uploaded zip archive document."""
    doc = message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    if not filename.endswith(".zip"):
        await message.reply(
            "⚠️ The uploaded file is not a <code>.zip</code> archive. Please upload a valid zip file.",
            parse_mode=ParseMode.HTML,
        )
        return

    data = await state.get_data()
    bot_name = data.get("bot_name", "MyBot")
    user_id = message.from_user.id if message.from_user else 0

    progress_msg = await message.reply("⏳ Downloading and verifying archive security...")

    # Download file in memory
    file_bytes_io = io.BytesIO()
    try:
        await bot.download(doc, destination=file_bytes_io)
        file_bytes_io.seek(0)
    except Exception as exc:
        await progress_msg.edit_text(f"❌ Failed to download file from Telegram: {exc}")
        return

    # Create DB record and sandbox
    async with get_session() as session:
        hosted_bot = await create_hosted_bot(
            session=session,
            user_id=user_id,
            name=bot_name,
            runtime_type="python",
            entry_point="main.py",
        )
        bot_id = hosted_bot.id

    sandbox = BotSandbox(bot_id)
    workspace = sandbox.ensure_workspace()

    # Extract with Zip-Slip traversal protection
    try:
        safe_extract_zip(file_bytes_io.getvalue(), workspace)
    except SandboxSecurityError as sec_err:
        async with get_session() as session:
            await delete_bot(session, bot_id)
        sandbox.clean_workspace()
        await progress_msg.edit_text(
            f"🚫 <b>Security Violation:</b> Archive rejected.\n<code>{sec_err}</code>",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return
    except Exception as zip_err:
        async with get_session() as session:
            await delete_bot(session, bot_id)
        sandbox.clean_workspace()
        await progress_msg.edit_text(
            f"❌ <b>Archive Error:</b> Could not extract archive.\n<code>{zip_err}</code>",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return

    # Entry point detection
    detected_entry = detect_entry_point(workspace)
    async with get_session() as session:
        await update_bot_entry_point(session, bot_id, detected_entry)
        refreshed_bot = await session.get(hosted_bot.__class__, bot_id)

    # Check for requirements.txt and install if found
    req_file = workspace / "requirements.txt"
    if req_file.is_file():
        await progress_msg.edit_text(
            "📦 Found <code>requirements.txt</code>! Initializing virtual environment and installing dependencies...",
            parse_mode=ParseMode.HTML,
        )
        success, pip_logs = await install_requirements(bot_id, requirements_file=req_file)
        if not success:
            await message.answer(
                f"⚠️ <b>Notice:</b> Dependency installation had warnings/errors:\n"
                f"<pre>{pip_logs[-500:]}</pre>\n"
                f"You can still start the bot or adjust dependencies.",
                parse_mode=ParseMode.HTML,
            )

    await state.clear()
    await progress_msg.delete()

    card_text = (
        f"🎉 <b>Bot Successfully Deployed!</b>\n\n"
        f"{format_bot_card(refreshed_bot or hosted_bot, is_running=False)}\n"
        f"💡 Click <b>▶️ Start</b> below to launch your bot process."
    )
    await message.answer(
        card_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=False),
    )


# ---------------------------------------------------------------------------
# 2. Single Script (.py) Ingestion
# ---------------------------------------------------------------------------

@router.message(HostBotStates.waiting_for_file)
async def handle_single_file_upload(message: types.Message, bot: Bot, state: FSMContext) -> None:
    """Handle uploaded single python script or code text."""
    data = await state.get_data()
    bot_name = data.get("bot_name", "MyBot")
    user_id = message.from_user.id if message.from_user else 0

    progress_msg = await message.reply("⏳ Saving script to workspace...")

    # Create DB record and sandbox
    async with get_session() as session:
        hosted_bot = await create_hosted_bot(
            session=session,
            user_id=user_id,
            name=bot_name,
            runtime_type="python",
            entry_point="main.py",
        )
        bot_id = hosted_bot.id

    sandbox = BotSandbox(bot_id)
    workspace = sandbox.ensure_workspace()
    target_script = workspace / "main.py"

    if message.document:
        try:
            await bot.download(message.document, destination=target_script)
        except Exception as exc:
            async with get_session() as session:
                await delete_bot(session, bot_id)
            sandbox.clean_workspace()
            await progress_msg.edit_text(f"❌ Failed to download script file: {exc}")
            return
    elif message.text:
        # Save raw code message
        target_script.write_text(message.text, encoding="utf-8")
    else:
        async with get_session() as session:
            await delete_bot(session, bot_id)
        sandbox.clean_workspace()
        await progress_msg.edit_text("⚠️ Please send a Python <code>.py</code> file or code snippet.")
        return

    await state.clear()
    await progress_msg.delete()

    async with get_session() as session:
        refreshed_bot = await session.get(hosted_bot.__class__, bot_id)

    card_text = (
        f"🎉 <b>Bot Successfully Deployed!</b>\n\n"
        f"{format_bot_card(refreshed_bot or hosted_bot, is_running=False)}\n"
        f"💡 Click <b>▶️ Start</b> below to launch your bot process."
    )
    await message.answer(
        card_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=False),
    )


# ---------------------------------------------------------------------------
# 3. GitHub Ingestion
# ---------------------------------------------------------------------------

@router.message(HostBotStates.waiting_for_git_url)
async def handle_github_clone(message: types.Message, state: FSMContext) -> None:
    """Clone a public GitHub repository into the bot's sandbox workspace."""
    git_url = (message.text or "").strip()
    if not (git_url.startswith("https://") or git_url.startswith("http://")):
        await message.reply("⚠️ Please provide a valid HTTP/HTTPS Git repository URL.")
        return

    data = await state.get_data()
    bot_name = data.get("bot_name", "MyBot")
    user_id = message.from_user.id if message.from_user else 0

    progress_msg = await message.reply(f"⏳ Cloning repository from <code>{git_url}</code>...", parse_mode=ParseMode.HTML)

    async with get_session() as session:
        hosted_bot = await create_hosted_bot(
            session=session,
            user_id=user_id,
            name=bot_name,
            runtime_type="python",
            entry_point="main.py",
        )
        bot_id = hosted_bot.id

    sandbox = BotSandbox(bot_id)
    workspace = sandbox.ensure_workspace()

    # Execute git clone --depth 1
    cmd = ["git", "clone", "--depth", "1", git_url, "."]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_log = stderr.decode(errors="replace").strip()
            async with get_session() as session:
                await delete_bot(session, bot_id)
            sandbox.clean_workspace()
            await progress_msg.edit_text(
                f"❌ <b>Git Clone Failed (Code {proc.returncode}):</b>\n<pre>{err_log}</pre>",
                parse_mode=ParseMode.HTML,
            )
            await state.clear()
            return
    except Exception as exc:
        async with get_session() as session:
            await delete_bot(session, bot_id)
        sandbox.clean_workspace()
        await progress_msg.edit_text(f"❌ Failed to run git clone: {exc}")
        await state.clear()
        return

    detected_entry = detect_entry_point(workspace)
    async with get_session() as session:
        await update_bot_entry_point(session, bot_id, detected_entry)
        refreshed_bot = await session.get(hosted_bot.__class__, bot_id)

    req_file = workspace / "requirements.txt"
    if req_file.is_file():
        await progress_msg.edit_text("📦 Installing dependencies from cloned <code>requirements.txt</code>...")
        await install_requirements(bot_id, requirements_file=req_file)

    await state.clear()
    await progress_msg.delete()

    card_text = (
        f"🎉 <b>Bot Successfully Deployed from GitHub!</b>\n\n"
        f"{format_bot_card(refreshed_bot or hosted_bot, is_running=False)}\n"
        f"💡 Click <b>▶️ Start</b> below to launch your bot process."
    )
    await message.answer(
        card_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=False),
    )


# ---------------------------------------------------------------------------
# 4. Pre-Built Template Deployment
# ---------------------------------------------------------------------------

@router.callback_query(HostBotStates.choosing_template, F.data.startswith("template_select:"))
async def handle_template_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt for bot name when a template is selected."""
    template_name = callback.data.split(":", 1)[1]
    await state.update_data(template_name=template_name)

    titles = {
        "echo": "🔁 Echo Bot",
        "broadcast": "📢 Broadcast Bot",
        "auto_reply": "💬 Auto-Reply Bot",
        "filter": "🔍 Filter Bot",
    }
    title = titles.get(template_name, template_name.title())

    text = (
        f"<b>Selected: {title}</b>\n\n"
        f"📝 <b>Step 1 of 2: Bot Name</b>\n"
        f"Please enter a display name for this bot instance:"
    )

    if callback.message:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
    await state.set_state(HostBotStates.waiting_for_template_name)
    await callback.answer()


@router.message(HostBotStates.waiting_for_template_name)
async def handle_template_name_input(message: types.Message, state: FSMContext) -> None:
    """Save template bot name and prompt for @BotFather API token."""
    if not message.text:
        await message.reply("⚠️ Please provide a valid text name.")
        return

    bot_name = sanitize_bot_name(message.text)
    await state.update_data(bot_name=bot_name)

    text = (
        f"🔑 <b>Step 2 of 2: Telegram Bot API Token</b>\n\n"
        f"Please paste the API token obtained from @BotFather for <b>{bot_name}</b>:\n\n"
        f"<i>Format: <code>123456789:ABCdef-GHIjkl...</code></i>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_cancel_inline_keyboard())
    await state.set_state(HostBotStates.waiting_for_template_token)


@router.message(HostBotStates.waiting_for_template_token)
async def handle_template_token_input(message: types.Message, state: FSMContext) -> None:
    """Validate token, copy template files, and deploy template bot."""
    token = (message.text or "").strip()
    if not is_valid_bot_token(token):
        await message.reply(
            "⚠️ Invalid Telegram bot token format. Tokens usually look like:\n"
            "<code>123456789:ABCdefGhIjkLmNoPqRsTuVwXyZ012345678</code>\n\n"
            "Please check @BotFather and try again:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_cancel_inline_keyboard(),
        )
        return

    data = await state.get_data()
    bot_name = data.get("bot_name", "TemplateBot")
    template_type = data.get("template_name", "echo")
    user_id = message.from_user.id if message.from_user else 0

    progress_msg = await message.reply("⏳ Deploying template files and initializing environment...")

    # Create DB record
    async with get_session() as session:
        hosted_bot = await create_hosted_bot(
            session=session,
            user_id=user_id,
            name=bot_name,
            runtime_type="python",
            entry_point="main.py",
            token=token,
            env_vars={"BOT_TOKEN": token},
        )
        bot_id = hosted_bot.id

    sandbox = BotSandbox(bot_id)
    workspace = sandbox.ensure_workspace()

    # Copy template directory
    src_template_dir = TEMPLATES_DIR / template_type
    if src_template_dir.is_dir():
        for item in src_template_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, workspace / item.name)
    else:
        # Fallback basic echo script
        (workspace / "main.py").write_text(
            f"import os\nprint('Bot initialized with token:', os.getenv('BOT_TOKEN')[:10])\n",
            encoding="utf-8",
        )

    # Install requirements
    req_file = workspace / "requirements.txt"
    if req_file.is_file():
        await progress_msg.edit_text("📦 Preparing private virtual environment and packages...")
        await install_requirements(bot_id, requirements_file=req_file)

    await state.clear()
    await progress_msg.delete()

    async with get_session() as session:
        refreshed_bot = await session.get(hosted_bot.__class__, bot_id)

    card_text = (
        f"🎉 <b>{template_type.title()} Template Deployed!</b>\n\n"
        f"{format_bot_card(refreshed_bot or hosted_bot, is_running=False)}\n"
        f"💡 Click <b>▶️ Start</b> below to launch your bot process."
    )
    await message.answer(
        card_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_bot_control_keyboard(bot_id, is_running=False),
    )
