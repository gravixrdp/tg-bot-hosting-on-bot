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


@pytest.mark.asyncio
async def test_reply_buttons_filter_matching_all_styles():
    """Verify ButtonMatchFilter matches all reply buttons across multiple font styles."""
    from src.bot.keyboards.reply import (
        BUTTON_ADMIN_PANEL,
        BUTTON_HELP_GUIDE,
        BUTTON_HOST_BOT,
        BUTTON_MY_BOTS,
        BUTTON_SYSTEM_STATUS,
    )
    from src.bot.utils import ButtonMatchFilter, apply_font_style

    buttons_and_plain = [
        (BUTTON_HOST_BOT, "Host New Bot"),
        (BUTTON_MY_BOTS, "My Bots"),
        (BUTTON_SYSTEM_STATUS, "System Status"),
        (BUTTON_HELP_GUIDE, "Help & Guide"),
        (BUTTON_ADMIN_PANEL, "Admin Panel"),
    ]

    styles = ["plain", "bold", "sans_bold", "monospace", "serif_bold", "italic"]

    for btn_canonical, plain_title in buttons_and_plain:
        filt = ButtonMatchFilter(btn_canonical, plain_title)

        # 1. Test across all Unicode font styles with emoji
        for s in styles:
            styled_text = apply_font_style(btn_canonical, s)
            msg = make_mock_message(text=styled_text)
            assert await filt(msg) is True, f"Failed match on style '{s}' for button '{btn_canonical}'"

        # 2. Test text without emoji
        msg_plain = make_mock_message(text=plain_title)
        assert await filt(msg_plain) is True

        # 3. Test lowercase text without emoji
        msg_lower = make_mock_message(text=plain_title.lower())
        assert await filt(msg_lower) is True

        # 4. Test styled text without emoji
        msg_styled_no_emoji = make_mock_message(text=apply_font_style(plain_title, "bold"))
        assert await filt(msg_styled_no_emoji) is True


@pytest.mark.asyncio
async def test_dispatcher_routes_styled_button_messages(temp_environment):
    """Verify that the full Aiogram Dispatcher routes styled Unicode messages to the correct handler."""
    from datetime import datetime, timezone
    from src.bot.keyboards.reply import (
        BUTTON_HELP_GUIDE,
        BUTTON_HOST_BOT,
        BUTTON_MY_BOTS,
        BUTTON_SYSTEM_STATUS,
    )
    from src.bot.utils import apply_font_style

    dp = create_dispatcher()
    mock_bot = AsyncMock(spec=Bot)

    with patch.object(types.Message, "answer", new_callable=AsyncMock) as mock_answer:
        async def send_simulated_message(user_id: int, text: str):
            mock_answer.reset_mock()
            msg = types.Message(
                message_id=100,
                date=datetime.now(timezone.utc),
                chat=types.Chat(id=user_id, type="private"),
                from_user=types.User(id=user_id, is_bot=False, first_name="Tester", username="tester"),
                text=text,
            )
            update = types.Update(update_id=1, message=msg)
            await dp.feed_update(mock_bot, update)
            return mock_answer

        # 1. Bold Host New Bot -> routed to host flow
        ans_host = await send_simulated_message(
            778001,
            apply_font_style(BUTTON_HOST_BOT, "bold"),
        )
        ans_host.assert_called_once()
        assert "Deploy a New Telegram Bot" in ans_host.call_args[0][0]

        # 2. Monospace My Bots -> routed to my_bots handler
        ans_bots = await send_simulated_message(
            778002,
            apply_font_style(BUTTON_MY_BOTS, "monospace"),
        )
        ans_bots.assert_called_once()
        assert "My Hosted Bots" in ans_bots.call_args[0][0]

        # 3. Serif Bold System Status -> routed to status handler
        ans_status = await send_simulated_message(
            778003,
            apply_font_style(BUTTON_SYSTEM_STATUS, "serif_bold"),
        )
        ans_status.assert_called_once()
        assert "System & Platform Diagnostics" in ans_status.call_args[0][0]

        # 4. Italic Help & Guide -> routed to help handler
        ans_help = await send_simulated_message(
            778004,
            apply_font_style(BUTTON_HELP_GUIDE, "italic"),
        )
        ans_help.assert_called_once()
        assert "Platform Guide" in ans_help.call_args[0][0]

        # 5. Bold Admin Panel -> routed to admin handler for admin user
        original_admins = list(settings.ADMIN_IDS)
        settings.ADMIN_IDS = [778005]
        try:
            ans_admin = await send_simulated_message(
                778005,
                apply_font_style("👑 Admin Panel", "bold"),
            )
            ans_admin.assert_called_once()
            assert "Administrator Master Control Center" in ans_admin.call_args[0][0]
        finally:
            settings.ADMIN_IDS = original_admins


