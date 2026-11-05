"""
Process Supervisor Engine for Hosted Telegram Bots.

Manages child process lifecycle, async streaming of stdout and stderr into
circular in-memory ring buffers, crash detection, auto-restart policies,
and event callbacks for alerting.
"""

from __future__ import annotations

import asyncio
import collections
from datetime import datetime, timezone
import os
import sys
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Set, Tuple

import psutil

from src.core.config import settings
from src.core.database import (
    BotStatus,
    add_bot_log,
    get_bot,
    get_session,
    update_bot_restart_count,
    update_bot_status,
)
from src.core.sandbox import BotSandbox

# Type alias for crash event callbacks: (bot_id, return_code, last_logs) -> Coroutine
CrashCallback = Callable[[int, int, str], Coroutine[Any, Any, None]]


class BotProcessSupervisor:
    """Supervises and manages child bot processes running in sandbox environments."""

    def __init__(self) -> None:
        # Active child processes: bot_id -> asyncio.subprocess.Process
        self._processes: Dict[int, asyncio.subprocess.Process] = {}

        # Background async tasks (stream readers, monitor): bot_id -> list[Task]
        self._tasks: Dict[int, List[asyncio.Task]] = {}

        # Circular in-memory ring buffers: bot_id -> Deque[str]
        self._log_buffers: Dict[int, Deque[str]] = {}

        # Set of bot IDs currently undergoing intentional shutdown
        self._intentional_stops: Set[int] = set()

        # Concurrency locks per bot to avoid race conditions during start/stop/restart
        self._bot_locks: Dict[int, asyncio.Lock] = {}

        # Registered crash callbacks
        self._crash_callbacks: List[CrashCallback] = []

        # Supervisor shutdown flag
        self._is_shutting_down: bool = False

    def _get_lock(self, bot_id: int) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock for a specific bot."""
        if bot_id not in self._bot_locks:
            self._bot_locks[bot_id] = asyncio.Lock()
        return self._bot_locks[bot_id]

    def _get_buffer(self, bot_id: int) -> Deque[str]:
        """Retrieve or initialize the circular log buffer for a bot."""
        if bot_id not in self._log_buffers:
            self._log_buffers[bot_id] = collections.deque(maxlen=settings.LOG_BUFFER_SIZE)
        return self._log_buffers[bot_id]

    def _append_log(self, bot_id: int, stream: str, message: str) -> str:
        """Format and append a log entry to the in-memory ring buffer."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] [{stream.upper()}] {message}"
        buf = self._get_buffer(bot_id)
        buf.append(entry)
        return entry

    def register_crash_callback(self, callback: CrashCallback) -> None:
        """
        Register an asynchronous callback to be notified when a bot crashes.

        Callback signature: async def on_crash(bot_id: int, return_code: int, last_logs: str) -> None
        """
        if callback not in self._crash_callbacks:
            self._crash_callbacks.append(callback)

    def is_running(self, bot_id: int) -> bool:
        """Check if a bot process is actively running."""
        process = self._processes.get(bot_id)
        if process is None:
            return False
        if process.returncode is not None:
            return False
        try:
            return psutil.pid_exists(process.pid)
        except Exception:
            return False

    async def get_status(self, bot_id: int) -> str:
        """
        Get the current operational status of a bot.

        Reflects real-time process state and synchronizes with the database if inconsistent.
        """
        if self.is_running(bot_id):
            return BotStatus.RUNNING.value

        async with get_session() as session:
            bot = await get_bot(session, bot_id)
            if bot is None:
                return "NOT_FOUND"
            # If DB marked as RUNNING but process is not alive, correct it
            if bot.status == BotStatus.RUNNING:
                await update_bot_status(session, bot_id, BotStatus.STOPPED, pid=None)
                return BotStatus.STOPPED.value
            return bot.status.value

    def get_logs(self, bot_id: int, lines: int = 50) -> List[str]:
        """
        Retrieve the latest log lines from the in-memory circular ring buffer.

        Args:
            bot_id: The ID of the bot.
            lines: Number of recent log lines to return (defaults to 50).

        Returns:
            List of log lines in chronological order.
        """
        buffer = self._log_buffers.get(bot_id)
        if not buffer:
            return []
        items = list(buffer)
        return items[-lines:] if lines < len(items) else items

    async def start_bot(self, bot_id: int) -> Tuple[bool, str]:
        """
        Start a hosted bot process.

        Validates workspace, resolves Python runtime in venv, sets up environment
        variables, spawns subprocess with redirected streams, and updates database state.

        Returns:
            Tuple of (success: bool, status_message: str).
        """
        async with self._get_lock(bot_id):
            return await self._start_bot_unlocked(bot_id, reset_retries=True)

    async def _start_bot_unlocked(
        self, bot_id: int, reset_retries: bool = True
    ) -> Tuple[bool, str]:
        """Internal unlocked start method."""
        if self.is_running(bot_id):
            return False, f"Bot {bot_id} is already running (PID: {self._processes[bot_id].pid})."

        # Fetch bot definition from database
        async with get_session() as session:
            bot = await get_bot(session, bot_id)
            if bot is None:
                return False, f"Bot {bot_id} does not exist in database."

            entry_point_name = bot.entry_point
            bot_token = bot.token
            custom_env = dict(bot.env_vars or {})

            if reset_retries:
                await update_bot_restart_count(session, bot_id, 0)
            await update_bot_status(session, bot_id, BotStatus.STARTING, pid=None)

        sandbox = BotSandbox(bot_id)
        workspace = sandbox.ensure_workspace()
        entry_file = workspace / entry_point_name

        if not entry_file.is_file():
            err_msg = f"Entry point file '{entry_point_name}' not found in workspace '{workspace}'."
            self._append_log(bot_id, "system", err_msg)
            async with get_session() as session:
                await update_bot_status(session, bot_id, BotStatus.ERROR, pid=None)
                await add_bot_log(session, bot_id, "system", err_msg)
            return False, err_msg

        # Ensure Python virtual environment exists
        if not sandbox.has_venv():
            self._append_log(bot_id, "system", "Creating virtual environment...")
            success, msg, _ = await sandbox.create_virtualenv(with_pip=False)
            if not success:
                err_msg = f"Failed to initialize virtualenv: {msg}"
                self._append_log(bot_id, "system", err_msg)
                async with get_session() as session:
                    await update_bot_status(session, bot_id, BotStatus.ERROR, pid=None)
                    await add_bot_log(session, bot_id, "system", err_msg)
                return False, err_msg

        python_executable = sandbox.get_venv_python()
        if not python_executable.is_file():
            # Fall back to sys.executable if venv python binary is missing
            python_executable = Path(sys.executable)

        # Prepare child process environment
        proc_env = os.environ.copy()
        proc_env.update({
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "HOSTED_BOT_ID": str(bot_id),
            "BOT_WORKSPACE": str(workspace),
        })

        if bot_token and "BOT_TOKEN" not in custom_env:
            proc_env["BOT_TOKEN"] = bot_token

        for k, v in custom_env.items():
            proc_env[str(k)] = str(v)

        # Discard any existing intentional stop flag
        self._intentional_stops.discard(bot_id)

        try:
            cmd = [str(python_executable), str(entry_file)]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
            )
            self._processes[bot_id] = process

            start_msg = f"Process spawned successfully (PID: {process.pid}, Executable: {python_executable.name})"
            self._append_log(bot_id, "system", start_msg)

            async with get_session() as session:
                await update_bot_status(session, bot_id, BotStatus.RUNNING, pid=process.pid)
                await add_bot_log(session, bot_id, "system", start_msg)

            # Spawn async background streaming tasks and process watcher
            task_out = asyncio.create_task(
                self._stream_reader(bot_id, process.stdout, "stdout"),
                name=f"bot-{bot_id}-stdout",
            )
            task_err = asyncio.create_task(
                self._stream_reader(bot_id, process.stderr, "stderr"),
                name=f"bot-{bot_id}-stderr",
            )
            task_mon = asyncio.create_task(
                self._process_watcher(bot_id, process),
                name=f"bot-{bot_id}-monitor",
            )
            self._tasks[bot_id] = [task_out, task_err, task_mon]

            return True, f"Bot {bot_id} started successfully (PID: {process.pid})."

        except Exception as exc:
            err_msg = f"Failed to launch process: {exc}"
            self._append_log(bot_id, "system", err_msg)
            async with get_session() as session:
                await update_bot_status(session, bot_id, BotStatus.ERROR, pid=None)
                await add_bot_log(session, bot_id, "system", err_msg)
            return False, err_msg

    async def stop_bot(self, bot_id: int, timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Gracefully terminate or forcefully kill a running bot process.

        Attempts graceful termination with timeout before escalating to SIGKILL.
        Terminates the entire process tree to prevent orphan processes.

        Args:
            bot_id: The ID of the bot to stop.
            timeout: Grace period in seconds before killing (defaults to config setting).

        Returns:
            Tuple of (success: bool, status_message: str).
        """
        async with self._get_lock(bot_id):
            return await self._stop_bot_unlocked(bot_id, timeout)

    async def _stop_bot_unlocked(
        self, bot_id: int, timeout: Optional[float] = None
    ) -> Tuple[bool, str]:
        """Internal unlocked stop method."""
        self._intentional_stops.add(bot_id)
        stop_timeout = timeout or settings.PROCESS_STOP_TIMEOUT
        process = self._processes.get(bot_id)

        if process is None or process.returncode is not None:
            # Clean up references and sync database
            self._processes.pop(bot_id, None)
            async with get_session() as session:
                await update_bot_status(session, bot_id, BotStatus.STOPPED, pid=None)
            return True, f"Bot {bot_id} is not running."

        pid = process.pid
        self._append_log(bot_id, "system", f"Stopping bot process (PID: {pid})...")

        # Terminate process tree via psutil
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            try:
                process.terminate()
            except ProcessLookupError:
                pass

        # Wait for graceful termination
        try:
            await asyncio.wait_for(process.wait(), timeout=stop_timeout)
        except asyncio.TimeoutError:
            self._append_log(bot_id, "system", f"Graceful termination timed out; killing PID {pid}...")
            # Force kill process tree
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                parent.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except Exception:
                pass

        self._processes.pop(bot_id, None)

        # Cancel remaining streaming/monitoring tasks
        tasks = self._tasks.pop(bot_id, [])
        for task in tasks:
            if not task.done():
                task.cancel()

        stop_msg = f"Bot {bot_id} stopped cleanly."
        self._append_log(bot_id, "system", stop_msg)

        async with get_session() as session:
            await update_bot_status(session, bot_id, BotStatus.STOPPED, pid=None)
            await add_bot_log(session, bot_id, "system", stop_msg)

        return True, stop_msg

    async def restart_bot(self, bot_id: int) -> Tuple[bool, str]:
        """
        Restart a hosted bot process cleanly.

        Stops the process if running, applies a brief cool-down delay,
        and starts a new child process.
        """
        async with self._get_lock(bot_id):
            await self._stop_bot_unlocked(bot_id)
            await asyncio.sleep(0.5)
            return await self._start_bot_unlocked(bot_id, reset_retries=True)

    async def _stream_reader(
        self, bot_id: int, stream: Optional[asyncio.StreamReader], stream_name: str
    ) -> None:
        """Continuously read lines from process stdout/stderr into ring buffer."""
        if stream is None:
            return

        while True:
            try:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace").rstrip("\r\n")
                self._append_log(bot_id, stream_name, line)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._append_log(bot_id, "system", f"Error reading {stream_name}: {exc}")
                break

    async def _process_watcher(
        self, bot_id: int, process: asyncio.subprocess.Process
    ) -> None:
        """Monitor process lifecycle, handle exits, crashes, and auto-restart policies."""
        return_code = await process.wait()

        # Check if the process stopped due to intentional user action
        if bot_id in self._intentional_stops:
            self._intentional_stops.discard(bot_id)
            self._processes.pop(bot_id, None)
            return

        # Unexpected process exit
        self._processes.pop(bot_id, None)
        exit_msg = f"Process terminated unexpectedly with exit code {return_code}"
        self._append_log(bot_id, "system", exit_msg)

        # Retrieve recent logs for diagnostics
        last_logs = "\n".join(self.get_logs(bot_id, lines=15))

        # Persist log event
        async with get_session() as session:
            await add_bot_log(session, bot_id, "system", f"{exit_msg}\n{last_logs}")

        # If clean exit (code 0) without intentional stop, mark STOPPED
        if return_code == 0:
            async with get_session() as session:
                await update_bot_status(session, bot_id, BotStatus.STOPPED, pid=None)
            return

        # Non-zero exit code represents a CRASH
        async with get_session() as session:
            await update_bot_status(session, bot_id, BotStatus.CRASHED, pid=None)
            bot = await get_bot(session, bot_id)
            auto_restart_enabled = bot.auto_restart if bot else False
            current_restart_count = bot.restart_count if bot else 0

        # Dispatch crash callbacks
        for callback in self._crash_callbacks:
            try:
                await callback(bot_id, return_code, last_logs)
            except Exception as cb_exc:
                self._append_log(bot_id, "system", f"Error in crash callback: {cb_exc}")

        # Evaluate auto-restart policy
        if auto_restart_enabled and not self._is_shutting_down:
            if current_restart_count < settings.DEFAULT_RESTART_RETRIES:
                next_count = current_restart_count + 1
                async with get_session() as session:
                    await update_bot_restart_count(session, bot_id, next_count)

                restart_msg = (
                    f"Auto-restart attempt {next_count}/{settings.DEFAULT_RESTART_RETRIES} "
                    f"in {settings.RESTART_DELAY_SECONDS}s..."
                )
                self._append_log(bot_id, "system", restart_msg)
                await asyncio.sleep(settings.RESTART_DELAY_SECONDS)

                if not self._is_shutting_down and bot_id not in self._intentional_stops:
                    async with self._get_lock(bot_id):
                        await self._start_bot_unlocked(bot_id, reset_retries=False)
            else:
                exhaust_msg = (
                    f"Maximum auto-restart retries ({settings.DEFAULT_RESTART_RETRIES}) "
                    f"exceeded. Bot {bot_id} remains in CRASHED state."
                )
                self._append_log(bot_id, "system", exhaust_msg)
                async with get_session() as session:
                    await update_bot_status(session, bot_id, BotStatus.CRASHED, pid=None)
                    await add_bot_log(session, bot_id, "system", exhaust_msg)

    async def shutdown(self) -> None:
        """Gracefully terminate all running bot processes on supervisor shutdown."""
        self._is_shutting_down = True
        active_bot_ids = list(self._processes.keys())
        for bot_id in active_bot_ids:
            try:
                await self.stop_bot(bot_id, timeout=2.0)
            except Exception:
                pass


# Global process supervisor singleton
supervisor = BotProcessSupervisor()
