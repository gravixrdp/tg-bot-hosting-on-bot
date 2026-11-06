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
from typing import Any, Dict, List, Optional, Sequence
import unicodedata

from aiogram import types
from aiogram.filters import Filter
import psutil

from src.core.database import BotStatus, HostedBot

# Telegram Bot token validation regex: e.g. 123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456
TOKEN_REGEX = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,50}$")


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


# ---------------------------------------------------------------------------
# Font Styling, Normalization & Resilient Button Routing Utilities
# ---------------------------------------------------------------------------

SUPPORTED_FONT_STYLES = (
    "plain",
    "bold",
    "sans_bold",
    "serif_bold",
    "monospace",
    "mono",
    "italic",
    "sans_italic",
    "script",
)

FONT_STYLE_OFFSETS: dict[str, tuple[Optional[int], Optional[int], Optional[int]]] = {
    # (uppercase_start, lowercase_start, digit_start)
    "bold": (0x1D5D4, 0x1D5EE, 0x1D7EC),  # Mathematical Sans-Serif Bold (A-Z, a-z, 0-9)
    "sans_bold": (0x1D5D4, 0x1D5EE, 0x1D7EC),
    "serif_bold": (0x1D400, 0x1D41A, 0x1D7CE),  # Mathematical Bold Serif (A-Z, a-z, 0-9)
    "monospace": (0x1D670, 0x1D68A, 0x1D7F6),  # Mathematical Monospace (A-Z, a-z, 0-9)
    "mono": (0x1D670, 0x1D68A, 0x1D7F6),
    "italic": (0x1D608, 0x1D622, None),  # Mathematical Sans-Serif Italic (A-Z, a-z)
    "sans_italic": (0x1D608, 0x1D622, None),
    "script": (0x1D4D0, 0x1D4EA, None),  # Mathematical Bold Script (A-Z, a-z)
}

EMOJI_PATTERN = re.compile(
    r"[\U0001F000-\U0001FAFF]|[\u2600-\u27BF]|[\u2300-\u23FF]|[\u2B50-\u2B55]|[\uFE00-\uFE0F]"
)


def apply_font_style(text: str, style: str = "plain") -> str:
    """
    Apply stylized Unicode fonts to ASCII alphanumeric characters within text.
    Preserves emojis, symbols, whitespace, and punctuation.

    Supported styles:
    - 'plain' / 'normal': Unchanged text
    - 'bold' / 'sans_bold': 🚀 𝗛𝗼𝘀𝘁 𝗡𝗲𝘄 𝗕𝗼𝘁
    - 'serif_bold': 🚀 𝐇𝐨𝐬𝐭 𝐍𝐞𝐰 𝐁𝐨𝐭
    - 'monospace' / 'mono': 🚀 𝙷𝚘𝚜𝚝 𝙽𝚎𝚠 𝙱𝚘𝚝
    - 'italic' / 'sans_italic': 🚀 𝘏𝘰𝘴𝘵 𝘕𝘦𝘸 𝘉𝘰𝘵
    - 'script': 🚀 𝓗𝓸𝓼𝓽 𝓝𝓮𝔀 𝓑𝓸𝓽
    """
    if not text:
        return ""
    normalized_style = (style or "plain").lower().strip()
    if normalized_style in ("plain", "normal", "none", "standard"):
        return text

    offset_entry = FONT_STYLE_OFFSETS.get(normalized_style)
    if not offset_entry:
        return text

    upper_base, lower_base, digit_base = offset_entry
    result_chars: list[str] = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90 and upper_base is not None:  # 'A'-'Z'
            result_chars.append(chr(upper_base + (code - 65)))
        elif 97 <= code <= 122 and lower_base is not None:  # 'a'-'z'
            result_chars.append(chr(lower_base + (code - 97)))
        elif 48 <= code <= 57 and digit_base is not None:  # '0'-'9'
            result_chars.append(chr(digit_base + (code - 48)))
        else:
            result_chars.append(char)
    return "".join(result_chars)


def normalize_button_text(text: str) -> str:
    """
    Normalize stylized Unicode characters (bold, monospace, serif bold, italic, etc.)
    back to standard ASCII/plain text using Unicode NFKC decomposition,
    and collapse multiple whitespaces.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.split())


def strip_emojis(text: str) -> str:
    """Strip emoji pictographs and symbols from a text string."""
    if not text:
        return ""
    return " ".join(EMOJI_PATTERN.sub("", text).split())


def is_button_match(text: str, *targets: str) -> bool:
    """
    Check if a given message text matches any of the target button labels,
    accounting for Unicode font styles (bold, monospace, serif bold, italic),
    emoji differences, extra whitespace, and case-insensitivity.
    """
    if not text:
        return False
    norm_text = normalize_button_text(text)
    if not norm_text:
        return False

    norm_lower = norm_text.lower()
    clean_lower = strip_emojis(norm_text).lower()

    for target in targets:
        if not target:
            continue
        norm_target = normalize_button_text(target)
        if norm_text == norm_target or norm_lower == norm_target.lower():
            return True
        clean_target = strip_emojis(norm_target).lower()
        if clean_target and clean_lower == clean_target:
            return True
    return False


class ButtonMatchFilter(Filter):
    """
    Aiogram Filter that matches incoming message text against expected button targets,
    normalizing Unicode font styles, emoji prefixes, and case differences.
    """

    def __init__(self, *targets: str) -> None:
        self.targets = targets

    async def __call__(self, message: types.Message) -> bool:
        if not message or not getattr(message, "text", None):
            return False
        return is_button_match(message.text, *self.targets)


def button_filter(*targets: str) -> ButtonMatchFilter:
    """Convenience factory function for ButtonMatchFilter."""
    return ButtonMatchFilter(*targets)
