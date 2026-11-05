"""
UI Helpers, Text Formatters, and Diagnostic Utilities.

Provides status badge formatting, bot card renderers, system resource
telemetry, token validation, and entry point detection.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional

import psutil

from src.core.database import BotStatus, HostedBot

# Telegram Bot token validation regex: e.g. 123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456
TOKEN_REGEX = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{35}$")


def format_status_badge(status: str | BotStatus) -> str:
    """Return an emoji status badge for a bot status string or enum."""
    val = status.value if isinstance(status, BotStatus) else str(status).upper()
    badges = {
        "RUNNING": "🟢 RUNNING",
        "STOPPED": "⏹️ STOPPED",
        "CRASHED": "⚠️ CRASHED",
        "STARTING": "🔄 STARTING",
        "ERROR": "❌ ERROR",
    }
    return badges.get(val, f"⚪ {val}")


def mask_token(token: Optional[str]) -> str:
    """Mask a Telegram bot token for secure display."""
    if not token or len(token) < 15:
        return "••••••••••••••••"
    colon_idx = token.find(":")
    if colon_idx != -1:
        bot_id_part = token[:colon_idx]
        secret = token[colon_idx + 1 :]
        if len(secret) > 8:
            masked_secret = f"{secret[:4]}...{secret[-4:]}"
        else:
            masked_secret = "••••••••"
        return f"{bot_id_part}:{masked_secret}"
    return f"{token[:4]}••••{token[-4:]}"


def format_bot_card(bot: HostedBot, is_running: bool = False, pid: Optional[int] = None) -> str:
    """Format an informative, professional HTML card for a hosted bot."""
    badge = format_status_badge("RUNNING" if is_running else bot.status)
    display_pid = str(pid or bot.pid or "N/A") if is_running else "Inactive"
    created_str = bot.created_at.strftime("%Y-%m-%d %H:%M UTC") if bot.created_at else "Unknown"
    env_count = len(bot.env_vars) if bot.env_vars else 0

    return (
        f"🤖 <b>Bot Details: {bot.name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Status:</b> {badge}\n"
        f"• <b>Bot ID:</b> <code>{bot.id}</code>\n"
        f"• <b>Process ID (PID):</b> <code>{display_pid}</code>\n"
        f"• <b>Entry Point:</b> <code>{bot.entry_point}</code>\n"
        f"• <b>Runtime:</b> Python 3.x\n"
        f"• <b>Auto-Restart:</b> {'✅ Enabled' if bot.auto_restart else '❌ Disabled'}\n"
        f"• <b>Restart Count:</b> {bot.restart_count}\n"
        f"• <b>Environment Variables:</b> {env_count} configured\n"
        f"• <b>Created:</b> {created_str}\n"
    )


def is_valid_bot_token(token: str) -> bool:
    """Check if a string matches the Telegram Bot API token pattern."""
    return bool(TOKEN_REGEX.match(token.strip()))


def sanitize_bot_name(name: str) -> str:
    """Clean and sanitize user-provided bot name."""
    cleaned = re.sub(r"[^\w\s\-\.]", "", name.strip())
    # Limit to reasonable length
    return cleaned[:40].strip() or "MyBot"


def detect_entry_point(directory: Path) -> str:
    """
    Inspect a workspace directory to find the most suitable entry point script.
    Checks common naming conventions: bot.py, main.py, app.py, run.py.
    """
    candidates = ["bot.py", "main.py", "app.py", "run.py"]
    for c in candidates:
        if (directory / c).is_file():
            return c

    # Search for any .py file in the root directory
    for item in directory.glob("*.py"):
        if item.is_file():
            return item.name

    return "main.py"


def get_system_metrics() -> Dict[str, Any]:
    """Retrieve current host system resource utilization metrics."""
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True) or 1
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getcwd())
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)

    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60

    return {
        "cpu_percent": cpu_percent,
        "cpu_cores": cpu_cores,
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_available_gb": round(mem.available / (1024**3), 2),
        "ram_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "disk_percent": disk.percent,
        "uptime_str": f"{hours}h {minutes}m",
    }
