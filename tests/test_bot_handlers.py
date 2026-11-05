"""
Unit and integration tests for Telegram bot UI handlers.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey

from src.bot.handlers import get_all_routers
from src.bot.handlers.admin import handle_admin_dashboard, is_admin_authorized
from src.bot.handlers.host_flow import handle_cancel, handle_host_prompt
from src.bot.handlers.my_bots import handle_my_bots
from src.bot.handlers.start import handle_help, handle_start
from src.bot.handlers.status import handle_system_status
from src.core.config import settings
from src.core.database import (
    BotStatus,
    create_hosted_bot,
    get_or_create_user,
    get_session,
    get_user,
)
from src.core.supervisor import supervisor
from src.main import create_dispatcher, setup_crash_callback


def make_mock_message(user_id: int = 12345, username: str = "testuser", text: str = "/start") -> types.Message:
    message = AsyncMock(spec=types.Message)
    user = types.User(id=user_id, is_bot=False, first_name="Test", username=username)
    chat = types.Chat(id=user_id, type="private")
    message.from_user = user
    message.chat = chat
    message.text = text
    message.answer = AsyncMock()
    return message


def make_mock_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    state = FSMContext(storage=storage, key=key)
    return state


@pytest.mark.asyncio
async def test_handle_start_registers_user(temp_environment):
    message = make_mock_message(user_id=777001, username="starter")

    await handle_start(message)

    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    welcome_text = args[0]
    assert "Welcome, Test!" in welcome_text
    assert "Telegram Bot Hosting Platform" in welcome_text

    # Verify user persisted in database
    async with get_session() as session:
        user = await get_user(session, 777001)
        assert user is not None
        assert user.username == "starter"


@pytest.mark.asyncio
async def test_handle_help_message(temp_environment):
    message = make_mock_message(user_id=777002, text="/help")

    await handle_help(message)

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    help_text = args[0]
    assert "Platform Guide" in help_text
    assert "Deployment Methods" in help_text


@pytest.mark.asyncio
async def test_handle_my_bots_empty(temp_environment):
    message = make_mock_message(user_id=777003, text="/mybots")
    state = make_mock_state()

    await handle_my_bots(message, state)

    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "You do not have any hosted bots yet" in args[0]


@pytest.mark.asyncio
async def test_handle_my_bots_populated(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 777004, "owner")
        await create_hosted_bot(session, user.id, "OwnerBot", auto_restart=False)

    message = make_mock_message(user_id=777004, text="/mybots")
    state = make_mock_state()

    await handle_my_bots(message, state)

    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "1 active" in args[0]
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_handle_system_status(temp_environment):
    message = make_mock_message(user_id=777005, text="/status")

    await handle_system_status(message)

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    status_text = args[0]
    assert "System & Platform Diagnostics" in status_text
    assert "CPU Utilization" in status_text
    assert "RAM Usage" in status_text
    assert "Host Uptime" in status_text


@pytest.mark.asyncio
async def test_admin_authorization(temp_environment):
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [999999]
    try:
        # Non-admin
        assert await is_admin_authorized(111111) is False

        # Config admin ID
        assert await is_admin_authorized(999999) is True

        # Database admin user
        async with get_session() as session:
            await get_or_create_user(session, 222222, is_admin=True)
        assert await is_admin_authorized(222222) is True
    finally:
        settings.ADMIN_IDS = original_admins


@pytest.mark.asyncio
async def test_handle_admin_dashboard_access_denied(temp_environment):
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [999999]
    try:
        message = make_mock_message(user_id=888001, text="/admin")
        state = make_mock_state()

        await handle_admin_dashboard(message, state)

        message.answer.assert_called_once()
        args, _ = message.answer.call_args
        assert "Access Denied" in args[0]
    finally:
        settings.ADMIN_IDS = original_admins


@pytest.mark.asyncio
async def test_handle_admin_dashboard_access_granted(temp_environment):
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [888002]
    try:
        message = make_mock_message(user_id=888002, text="/admin")
        state = make_mock_state()

        await handle_admin_dashboard(message, state)

        message.answer.assert_called_once()
        args, kwargs = message.answer.call_args
        assert "Administrator Master Control Center" in args[0]
        assert "reply_markup" in kwargs
    finally:
        settings.ADMIN_IDS = original_admins


@pytest.mark.asyncio
async def test_handle_cancel_flow(temp_environment):
    message = make_mock_message(user_id=888003, text="/cancel")
    state = make_mock_state()
    await state.set_state("waiting_for_zip")

    await handle_cancel(message, state)

    current_state = await state.get_state()
    assert current_state is None
    message.answer.assert_called_once()
    assert "Operation cancelled" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_host_prompt_within_quota(temp_environment):
    message = make_mock_message(user_id=888004, text="/host")
    state = make_mock_state()

    await handle_host_prompt(message, state)

    message.answer.assert_called_once()
    assert "Deploy a New Telegram Bot" in message.answer.call_args[0][0]
    assert "reply_markup" in message.answer.call_args[1]


@pytest.mark.asyncio
async def test_handle_host_prompt_quota_reached(temp_environment):
    # Set up user with max_bots=1 and already 1 bot
    async with get_session() as session:
        user = await get_or_create_user(session, 888005, "limited_user")
        user.max_bots = 1
        await create_hosted_bot(session, user.id, "ExistingBot", auto_restart=False)

    message = make_mock_message(user_id=888005, text="/host")
    state = make_mock_state()

    await handle_host_prompt(message, state)

    message.answer.assert_called_once()
    assert "Quota Reached" in message.answer.call_args[0][0]


def test_create_dispatcher_and_routers():
    dp = create_dispatcher()
    assert isinstance(dp, Dispatcher)
    routers = get_all_routers()
    assert len(routers) == 5
    router_names = [r.name for r in routers]
    assert "start" in router_names
    assert "host_flow" in router_names
    assert "my_bots" in router_names
    assert "status" in router_names
    assert "admin" in router_names


@pytest.mark.asyncio
async def test_setup_crash_callback(temp_environment):
    mock_bot = AsyncMock(spec=Bot)
    mock_bot.send_message = AsyncMock()

    async with get_session() as session:
        user = await get_or_create_user(session, 999888, "crash_owner")
        bot = await create_hosted_bot(session, user.id, "FaultyBot", auto_restart=False)
        bot_id = bot.id

    # Register callback
    await setup_crash_callback(mock_bot)

    # Trigger callback
    assert len(supervisor._crash_callbacks) > 0
    callback = supervisor._crash_callbacks[-1]
    await callback(bot_id, 137, "Fatal error: Segmentation fault")

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 999888
    assert "FaultyBot" in call_kwargs["text"]
    assert "137" in call_kwargs["text"]
    assert "Segmentation fault" in call_kwargs["text"]
