"""
Unit tests for src/core/database.py.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import select, delete

from src.core.config import settings
from src.core.database import (
    Base,
    BotLogEntry,
    BotStatus,
    HostedBot,
    User,
    add_bot_log,
    create_hosted_bot,
    delete_bot,
    get_all_bots,
    get_bot,
    get_bot_logs_from_db,
    get_or_create_user,
    get_session,
    get_user,
    get_user_bots,
    update_bot_entry_point,
    update_bot_env_vars,
    update_bot_restart_count,
    update_bot_status,
    update_user_max_bots,
)


@pytest.mark.asyncio
async def test_user_lifecycle(temp_environment):
    async with get_session() as session:
        # Create user
        user = await get_or_create_user(
            session=session,
            telegram_id=123456,
            username="testuser",
            full_name="Test User",
            is_admin=False,
        )
        assert user.id == 123456
        assert user.username == "testuser"
        assert user.full_name == "Test User"
        assert not user.is_admin

        # Fetch existing user
        fetched = await get_user(session, 123456)
        assert fetched is not None
        assert fetched.id == 123456

        # Update max bots
        updated = await update_user_max_bots(session, 123456, 10)
        assert updated is not None
        assert updated.max_bots == 10

        # Update user attributes via get_or_create_user
        modified = await get_or_create_user(
            session=session,
            telegram_id=123456,
            username="newusername",
            full_name="Updated Name",
        )
        assert modified.username == "newusername"
        assert modified.full_name == "Updated Name"


@pytest.mark.asyncio
async def test_user_admin_promotion(temp_environment):
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [999001]
    try:
        async with get_session() as session:
            admin_user = await get_or_create_user(session, 999001, "admin_user", "Admin User")
            assert admin_user.is_admin is True

            # Promote existing non-admin user
            regular = await get_or_create_user(session, 999002, "reg_user", "Regular User")
            assert regular.is_admin is False

            settings.ADMIN_IDS.append(999002)
            promoted = await get_or_create_user(session, 999002)
            assert promoted.is_admin is True
    finally:
        settings.ADMIN_IDS = original_admins


@pytest.mark.asyncio
async def test_hosted_bot_crud(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 1001, "botmaster", "Bot Master")

        # Create bot
        bot = await create_hosted_bot(
            session=session,
            user_id=user.id,
            name="EchoBot",
            runtime_type="python",
            entry_point="main.py",
            token="123:ABC",
            auto_restart=True,
            env_vars={"PORT": "8080"},
        )
        assert bot.id is not None
        bot_id = bot.id
        assert bot.name == "EchoBot"
        assert bot.status == BotStatus.STOPPED
        assert bot.env_vars == {"PORT": "8080"}

        # Get bot by ID
        fetched_bot = await get_bot(session, bot_id)
        assert fetched_bot is not None
        assert fetched_bot.user_id == user.id

        # List user bots
        user_bots = await get_user_bots(session, user.id)
        assert len(user_bots) == 1
        assert user_bots[0].id == bot_id

        # Update status and PID
        updated_bot = await update_bot_status(session, bot_id, BotStatus.RUNNING, pid=9999)
        assert updated_bot.status == BotStatus.RUNNING
        assert updated_bot.pid == 9999

        # Update restart count
        restarted_bot = await update_bot_restart_count(session, bot_id, 2)
        assert restarted_bot.restart_count == 2

        # Update entry point
        ep_bot = await update_bot_entry_point(session, bot_id, "app.py")
        assert ep_bot.entry_point == "app.py"

        # Update env vars
        ev_bot = await update_bot_env_vars(session, bot_id, {"DEBUG": "1"})
        assert ev_bot.env_vars == {"DEBUG": "1"}

        # Add bot logs
        await add_bot_log(session, bot_id, "stdout", "Server started on port 8080")
        await add_bot_log(session, bot_id, "stderr", "Warning: deprecated API call")

        logs = await get_bot_logs_from_db(session, bot_id, limit=10)
        assert len(logs) == 2
        assert "Server started" in logs[0].message
        assert "Warning: deprecated" in logs[1].message

        # Delete bot
        success = await delete_bot(session, bot_id)
        assert success is True

        deleted_bot = await get_bot(session, bot_id)
        assert deleted_bot is None

        # Logs should be cascade deleted
        logs_after = await get_bot_logs_from_db(session, bot_id)
        assert len(logs_after) == 0


@pytest.mark.asyncio
async def test_get_all_bots_and_nonexistent_updates(temp_environment):
    async with get_session() as session:
        u1 = await get_or_create_user(session, 2001, "u1")
        u2 = await get_or_create_user(session, 2002, "u2")

        b1 = await create_hosted_bot(session, u1.id, "Bot1")
        b2 = await create_hosted_bot(session, u2.id, "Bot2")

        all_bots = await get_all_bots(session)
        ids = [b.id for b in all_bots]
        assert b1.id in ids
        assert b2.id in ids

        # Update non-existent bot returns None
        non_existent_id = 999999
        assert await update_bot_status(session, non_existent_id, BotStatus.RUNNING) is None
        assert await update_bot_restart_count(session, non_existent_id, 1) is None
        assert await update_bot_entry_point(session, non_existent_id, "new.py") is None
        assert await update_bot_env_vars(session, non_existent_id, {"A": "1"}) is None
        assert await delete_bot(session, non_existent_id) is False


@pytest.mark.asyncio
async def test_bot_logs_ordering_and_limit(temp_environment):
    async with get_session() as session:
        u = await get_or_create_user(session, 3001, "log_user")
        bot = await create_hosted_bot(session, u.id, "LogBot")

        for i in range(15):
            await add_bot_log(session, bot.id, "stdout", f"Log line {i}")

        # Fetch with limit=5 (should be last 5 lines, in chronological order)
        logs = await get_bot_logs_from_db(session, bot.id, limit=5)
        assert len(logs) == 5
        assert logs[0].message == "Log line 10"
        assert logs[4].message == "Log line 14"
