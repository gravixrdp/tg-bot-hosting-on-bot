"""
Integration tests for src/core/supervisor.py process supervision engine.
"""

import asyncio
from pathlib import Path
import sys

import pytest

from src.core.database import (
    BotStatus,
    create_hosted_bot,
    get_bot,
    get_or_create_user,
    get_session,
)
from src.core.sandbox import BotSandbox
from src.core.supervisor import supervisor


@pytest.mark.asyncio
async def test_supervisor_start_and_stop_bot(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 5001, "sup_user", "Supervisor User")
        bot = await create_hosted_bot(
            session=session,
            user_id=user.id,
            name="RunnerBot",
            entry_point="main.py",
            auto_restart=False,
        )
        bot_id = bot.id

    sandbox = BotSandbox(bot_id)
    ws = sandbox.ensure_workspace()

    # Create dummy long-running bot script
    script_content = (
        "import sys, time\n"
        "print('HELLO_STDOUT_LINE', flush=True)\n"
        "print('HELLO_STDERR_LINE', file=sys.stderr, flush=True)\n"
        "time.sleep(10)\n"
    )
    (ws / "main.py").write_text(script_content)

    # Start bot
    success, msg = await supervisor.start_bot(bot_id)
    assert success is True
    assert "started successfully" in msg

    # Wait briefly for process output to be captured
    await asyncio.sleep(1.0)

    # Verify status
    assert supervisor.is_running(bot_id) is True
    status = await supervisor.get_status(bot_id)
    assert status == BotStatus.RUNNING.value

    # Verify logs captured in ring buffer
    logs = supervisor.get_logs(bot_id, lines=20)
    log_text = " ".join(logs)
    assert "HELLO_STDOUT_LINE" in log_text
    assert "HELLO_STDERR_LINE" in log_text

    # Stop bot
    stop_ok, stop_msg = await supervisor.stop_bot(bot_id)
    assert stop_ok is True
    assert supervisor.is_running(bot_id) is False

    status_after = await supervisor.get_status(bot_id)
    assert status_after == BotStatus.STOPPED.value


@pytest.mark.asyncio
async def test_supervisor_crash_detection_and_callback(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 5002, "crash_user", "Crash User")
        bot = await create_hosted_bot(
            session=session,
            user_id=user.id,
            name="CrasherBot",
            entry_point="main.py",
            auto_restart=False,
        )
        bot_id = bot.id

    sandbox = BotSandbox(bot_id)
    ws = sandbox.ensure_workspace()

    # Script that intentionally fails with exit code 42
    script_content = (
        "import sys\n"
        "print('CRITICAL_FAILURE_DETECTED', flush=True)\n"
        "sys.exit(42)\n"
    )
    (ws / "main.py").write_text(script_content)

    # Setup callback tracking
    crash_events = []

    async def on_crash_hook(b_id: int, return_code: int, last_logs: str) -> None:
        crash_events.append({"bot_id": b_id, "code": return_code, "logs": last_logs})

    supervisor.register_crash_callback(on_crash_hook)

    # Start bot
    success, _ = await supervisor.start_bot(bot_id)
    assert success is True

    # Wait for process to exit and monitor task to execute
    for _ in range(30):
        if len(crash_events) > 0:
            break
        await asyncio.sleep(0.1)

    assert len(crash_events) == 1
    assert crash_events[0]["bot_id"] == bot_id
    assert crash_events[0]["code"] == 42
    assert "CRITICAL_FAILURE_DETECTED" in crash_events[0]["logs"]

    # Check status updated to CRASHED
    async with get_session() as session:
        db_bot = await get_bot(session, bot_id)
        assert db_bot.status == BotStatus.CRASHED


@pytest.mark.asyncio
async def test_supervisor_missing_entry_point(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 5003, "missing_user", "Missing User")
        bot = await create_hosted_bot(
            session=session,
            user_id=user.id,
            name="GhostBot",
            entry_point="non_existent_file.py",
            auto_restart=False,
        )
        bot_id = bot.id

    success, msg = await supervisor.start_bot(bot_id)
    assert success is False
    assert "not found" in msg.lower()

    async with get_session() as session:
        db_bot = await get_bot(session, bot_id)
        assert db_bot.status == BotStatus.ERROR


@pytest.mark.asyncio
async def test_supervisor_restart_bot(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 5004, "restart_user", "Restart User")
        bot = await create_hosted_bot(
            session=session,
            user_id=user.id,
            name="RestartableBot",
            entry_point="main.py",
            auto_restart=False,
        )
        bot_id = bot.id

    sandbox = BotSandbox(bot_id)
    ws = sandbox.ensure_workspace()
    (ws / "main.py").write_text("import time\ntime.sleep(10)\n")

    # Start bot
    ok, _ = await supervisor.start_bot(bot_id)
    assert ok is True
    pid1 = supervisor._processes[bot_id].pid

    # Restart bot
    restart_ok, _ = await supervisor.restart_bot(bot_id)
    assert restart_ok is True
    assert supervisor.is_running(bot_id) is True
    pid2 = supervisor._processes[bot_id].pid
    assert pid1 != pid2

    # Clean up
    await supervisor.stop_bot(bot_id)


@pytest.mark.asyncio
async def test_supervisor_shutdown_and_cleanup(temp_environment):
    async with get_session() as session:
        user = await get_or_create_user(session, 5005, "multi_user", "Multi User")
        b1 = await create_hosted_bot(session, user.id, "MultiBot1", "main.py", auto_restart=False)
        b2 = await create_hosted_bot(session, user.id, "MultiBot2", "main.py", auto_restart=False)

    for b in [b1, b2]:
        sandbox = BotSandbox(b.id)
        ws = sandbox.ensure_workspace()
        (ws / "main.py").write_text("import time\ntime.sleep(15)\n")
        await supervisor.start_bot(b.id)
        assert supervisor.is_running(b.id) is True

    # Perform supervisor shutdown
    await supervisor.shutdown()

    assert supervisor.is_running(b1.id) is False
    assert supervisor.is_running(b2.id) is False


def test_supervisor_get_logs_empty():
    # Non-existent bot should return empty list
    assert supervisor.get_logs(999999) == []


