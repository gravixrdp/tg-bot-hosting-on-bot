"""
Automated unit tests verifying reply buttons and inline keyboard button handlers.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey

from src.bot.handlers.admin import (
    handle_admin_broadcast_cancel,
    handle_admin_broadcast_prompt,
    handle_admin_dashboard,
    handle_admin_force_kill,
    handle_admin_quota_delta,
    handle_admin_quota_custom_prompt,
    handle_admin_running_bots,
    handle_admin_stats,
    handle_admin_users_search_prompt,
)
from src.bot.handlers.host_flow import (
    handle_cancel,
    handle_deploy_type_chosen,
    handle_host_menu_back,
    handle_host_prompt,
    handle_template_selected,
)
from src.bot.handlers.my_bots import (
    handle_bot_details,
    handle_bot_logs,
    handle_bot_restart,
    handle_bot_start,
    handle_bot_stop,
    handle_delete_confirm,
    handle_delete_prompt,
    handle_env_add_prompt,
    handle_env_delete_prompt,
    handle_env_vars_view,
    handle_my_bots,
)
from src.bot.handlers.start import handle_help, handle_start
from src.bot.handlers.status import handle_system_status
from src.bot.states import HostBotStates
from src.core.config import settings
from src.core.database import (
    BotStatus,
    create_hosted_bot,
    get_or_create_user,
    get_session,
    get_user,
    update_bot_env_vars,
)
from src.core.supervisor import supervisor


def make_mock_message(user_id: int = 12345, username: str = "testuser", text: str = "") -> types.Message:
    message = AsyncMock(spec=types.Message)
    user = types.User(id=user_id, is_bot=False, first_name="Test", username=username)
    chat = types.Chat(id=user_id, type="private")
    message.from_user = user
    message.chat = chat
    message.text = text
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    return message


def make_mock_callback(user_id: int = 12345, data: str = "") -> types.CallbackQuery:
    callback = AsyncMock(spec=types.CallbackQuery)
    user = types.User(id=user_id, is_bot=False, first_name="Test", username="testuser")
    callback.from_user = user
    callback.data = data
    callback.answer = AsyncMock()
    msg = AsyncMock(spec=types.Message)
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    callback.message = msg
    return callback


def make_mock_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


# ===========================================================================
# 1. Reply Keyboard Text Buttons Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_reply_button_host_new_bot(temp_environment):
    msg = make_mock_message(user_id=10101, text="🚀 Host New Bot")
    state = make_mock_state()
    await handle_host_prompt(msg, state)
    msg.answer.assert_called_once()
    assert "Deploy a New Telegram Bot" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_reply_button_my_bots(temp_environment):
    msg = make_mock_message(user_id=10102, text="🤖 My Bots")
    state = make_mock_state()
    await handle_my_bots(msg, state)
    msg.answer.assert_called_once()
    assert "My Hosted Bots" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_reply_button_system_status(temp_environment):
    msg = make_mock_message(user_id=10103, text="📊 System Status")
    await handle_system_status(msg)
    msg.answer.assert_called_once()
    assert "System & Platform Diagnostics" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_reply_button_help_and_guide(temp_environment):
    msg = make_mock_message(user_id=10104, text="❓ Help & Guide")
    await handle_help(msg)
    msg.answer.assert_called_once()
    assert "Platform Guide" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_reply_button_admin_panel(temp_environment):
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [10105]
    try:
        msg = make_mock_message(user_id=10105, text="👑 Admin Panel")
        state = make_mock_state()
        await handle_admin_dashboard(msg, state)
        msg.answer.assert_called_once()
        assert "Administrator Master Control Center" in msg.answer.call_args[0][0]
    finally:
        settings.ADMIN_IDS = original_admins


# ===========================================================================
# 2. Host Flow Inline Buttons Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_inline_button_cancel_flow(temp_environment):
    cb = make_mock_callback(user_id=20201, data="cancel_flow")
    state = make_mock_state()
    await state.set_state(HostBotStates.waiting_for_name)
    await handle_cancel(cb, state)
    assert await state.get_state() is None
    cb.answer.assert_called_once()
    cb.message.edit_text.assert_called_once()
    assert "Operation cancelled" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_inline_button_host_menu_back(temp_environment):
    cb = make_mock_callback(user_id=20202, data="host_menu_back")
    state = make_mock_state()
    await handle_host_menu_back(cb, state)
    cb.message.edit_text.assert_called_once()
    assert "Deploy a New Telegram Bot" in cb.message.edit_text.call_args[0][0]
    assert await state.get_state() == HostBotStates.choosing_deploy_type


@pytest.mark.asyncio
async def test_inline_button_deploy_type_zip(temp_environment):
    cb = make_mock_callback(user_id=20203, data="deploy_type:zip")
    state = make_mock_state()
    await handle_deploy_type_chosen(cb, state)
    cb.message.edit_text.assert_called_once()
    assert "Zip Archive Upload" in cb.message.edit_text.call_args[0][0]
    assert await state.get_state() == HostBotStates.waiting_for_name


@pytest.mark.asyncio
async def test_inline_button_deploy_type_template(temp_environment):
    cb = make_mock_callback(user_id=20204, data="deploy_type:template")
    state = make_mock_state()
    await handle_deploy_type_chosen(cb, state)
    cb.message.edit_text.assert_called_once()
    assert "Select a Pre-Built Bot Template" in cb.message.edit_text.call_args[0][0]
    assert await state.get_state() == HostBotStates.choosing_template


@pytest.mark.asyncio
async def test_inline_button_template_select(temp_environment):
    cb = make_mock_callback(user_id=20205, data="template_select:echo")
    state = make_mock_state()
    await handle_template_selected(cb, state)
    cb.message.edit_text.assert_called_once()
    assert "Echo Bot" in cb.message.edit_text.call_args[0][0]
    assert await state.get_state() == HostBotStates.waiting_for_template_name


# ===========================================================================
# 3. My Bots Inline Buttons & Lifecycle Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_inline_button_refresh_bots_list(temp_environment):
    cb = make_mock_callback(user_id=30301, data="refresh_bots_list")
    state = make_mock_state()
    await handle_my_bots(cb, state)
    cb.message.edit_text.assert_called_once()
    assert "My Hosted Bots" in cb.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_inline_button_bot_manage_and_controls(temp_environment):
    user_id = 30302
    async with get_session() as session:
        user = await get_or_create_user(session, user_id, "bot_tester")
        bot = await create_hosted_bot(session, user_id, "TestControlBot", auto_restart=False)
        bot_id = bot.id

    # bot_manage:<id>
    cb_manage = make_mock_callback(user_id=user_id, data=f"bot_manage:{bot_id}")
    state = make_mock_state()
    await handle_bot_details(cb_manage, state)
    cb_manage.message.edit_text.assert_called_once()
    assert "TestControlBot" in cb_manage.message.edit_text.call_args[0][0]

    # bot_start:<id>
    with patch.object(supervisor, "start_bot", new=AsyncMock(return_value=(True, "Bot started"))):
        cb_start = make_mock_callback(user_id=user_id, data=f"bot_start:{bot_id}")
        await handle_bot_start(cb_start)
        cb_start.message.edit_text.assert_called_once()

    # bot_stop:<id>
    with patch.object(supervisor, "stop_bot", new=AsyncMock(return_value=(True, "Bot stopped"))):
        cb_stop = make_mock_callback(user_id=user_id, data=f"bot_stop:{bot_id}")
        await handle_bot_stop(cb_stop)
        cb_stop.message.edit_text.assert_called_once()

    # bot_restart:<id>
    with patch.object(supervisor, "restart_bot", new=AsyncMock(return_value=(True, "Bot restarted"))):
        cb_restart = make_mock_callback(user_id=user_id, data=f"bot_restart:{bot_id}")
        await handle_bot_restart(cb_restart)
        cb_restart.message.edit_text.assert_called_once()

    # bot_logs:<id>
    cb_logs = make_mock_callback(user_id=user_id, data=f"bot_logs:{bot_id}")
    await handle_bot_logs(cb_logs)
    cb_logs.message.edit_text.assert_called_once()
    assert "Live Output Logs" in cb_logs.message.edit_text.call_args[0][0]

    # bot_delete_prompt:<id>
    cb_del_prompt = make_mock_callback(user_id=user_id, data=f"bot_delete_prompt:{bot_id}")
    await handle_delete_prompt(cb_del_prompt)
    cb_del_prompt.message.edit_text.assert_called_once()
    assert "Delete Confirmation" in cb_del_prompt.message.edit_text.call_args[0][0]

    # bot_delete_confirm:<id>
    cb_del_confirm = make_mock_callback(user_id=user_id, data=f"bot_delete_confirm:{bot_id}")
    await handle_delete_confirm(cb_del_confirm)
    cb_del_confirm.message.edit_text.assert_called_once()
    assert "deleted successfully" in cb_del_confirm.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_inline_button_env_vars_and_prompts(temp_environment):
    user_id = 30303
    async with get_session() as session:
        user = await get_or_create_user(session, user_id)
        bot = await create_hosted_bot(
            session,
            user_id,
            "EnvBot",
            env_vars={"API_KEY": "12345"},
            auto_restart=False,
        )
        bot_id = bot.id

    state = make_mock_state()

    # bot_env:<id>
    cb_env = make_mock_callback(user_id=user_id, data=f"bot_env:{bot_id}")
    await handle_env_vars_view(cb_env, state)
    cb_env.message.edit_text.assert_called_once()
    assert "Environment Variables" in cb_env.message.edit_text.call_args[0][0]

    # env_add:<id>
    cb_env_add = make_mock_callback(user_id=user_id, data=f"env_add:{bot_id}")
    await handle_env_add_prompt(cb_env_add, state)
    cb_env_add.message.edit_text.assert_called_once()
    assert "Add / Update Environment Variable" in cb_env_add.message.edit_text.call_args[0][0]

    # env_del:<id>
    cb_env_del = make_mock_callback(user_id=user_id, data=f"env_del:{bot_id}")
    await handle_env_delete_prompt(cb_env_del, state)
    cb_env_del.message.edit_text.assert_called_once()
    assert "Delete Environment Variable" in cb_env_del.message.edit_text.call_args[0][0]


# ===========================================================================
# 4. Status Inline Button Refresh Test
# ===========================================================================

@pytest.mark.asyncio
async def test_inline_button_refresh_system_status(temp_environment):
    cb = make_mock_callback(user_id=40401, data="refresh_system_status")
    await handle_system_status(cb)
    cb.message.edit_text.assert_called_once()
    assert "System & Platform Diagnostics" in cb.message.edit_text.call_args[0][0]


# ===========================================================================
# 5. Admin Panel Inline Buttons Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_inline_button_admin_stats_and_users(temp_environment):
    admin_id = 50501
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [admin_id]
    try:
        # admin_stats
        cb_stats = make_mock_callback(user_id=admin_id, data="admin_stats")
        await handle_admin_stats(cb_stats)
        cb_stats.message.edit_text.assert_called_once()
        assert "Platform Global Analytics" in cb_stats.message.edit_text.call_args[0][0]

        # admin_users
        state = make_mock_state()
        cb_users = make_mock_callback(user_id=admin_id, data="admin_users")
        await handle_admin_users_search_prompt(cb_users, state)
        cb_users.message.edit_text.assert_called_once()
        assert "User Quota Management" in cb_users.message.edit_text.call_args[0][0]

        # quota_mod:<uid>:+1
        async with get_session() as session:
            target_user = await get_or_create_user(session, 60601, "target")
            target_user.max_bots = 3
        cb_mod = make_mock_callback(user_id=admin_id, data="quota_mod:60601:+1")
        await handle_admin_quota_delta(cb_mod)
        cb_mod.message.edit_text.assert_called_once()
        assert "4" in cb_mod.message.edit_text.call_args[0][0]

        # quota_set:<uid>
        cb_set = make_mock_callback(user_id=admin_id, data="quota_set:60601")
        await handle_admin_quota_custom_prompt(cb_set, state)
        cb_set.message.edit_text.assert_called_once()
        assert "Set Custom Bot Quota" in cb_set.message.edit_text.call_args[0][0]

        # admin_running_bots
        cb_running = make_mock_callback(user_id=admin_id, data="admin_running_bots")
        await handle_admin_running_bots(cb_running)
        cb_running.message.edit_text.assert_called_once()
        assert "Running Bots Monitor" in cb_running.message.edit_text.call_args[0][0]

        # admin_kill:<id>
        async with get_session() as session:
            kill_bot = await create_hosted_bot(session, 60601, "KillMeBot", auto_restart=False)
            kill_bot_id = kill_bot.id
        cb_kill = make_mock_callback(user_id=admin_id, data=f"admin_kill:{kill_bot_id}")
        await handle_admin_force_kill(cb_kill)
        cb_kill.message.edit_text.assert_called_once()
        assert "Process Terminated" in cb_kill.message.edit_text.call_args[0][0]

        # admin_broadcast prompt & cancel
        cb_bcast = make_mock_callback(user_id=admin_id, data="admin_broadcast")
        await handle_admin_broadcast_prompt(cb_bcast, state)
        cb_bcast.message.edit_text.assert_called_once()
        assert "Global Announcement Broadcast" in cb_bcast.message.edit_text.call_args[0][0]

        cb_bcast_cancel = make_mock_callback(user_id=admin_id, data="broadcast_cancel")
        await handle_admin_broadcast_cancel(cb_bcast_cancel, state)
        cb_bcast_cancel.message.edit_text.assert_called_once()
        assert "Broadcast cancelled" in cb_bcast_cancel.message.edit_text.call_args[0][0]
    finally:
        settings.ADMIN_IDS = original_admins
