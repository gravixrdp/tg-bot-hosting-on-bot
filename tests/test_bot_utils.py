"""
Unit tests for src/bot/utils.py helper utilities and formatters.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.bot.utils import (
    detect_entry_point,
    format_bot_card,
    format_status_badge,
    get_system_metrics,
    is_valid_bot_token,
    mask_token,
    sanitize_bot_name,
)
from src.core.database import BotStatus, HostedBot


def test_format_status_badge():
    assert "🟢" in format_status_badge(BotStatus.RUNNING)
    assert "⏹️" in format_status_badge(BotStatus.STOPPED)
    assert "⚠️" in format_status_badge(BotStatus.CRASHED)
    assert "🔄" in format_status_badge(BotStatus.STARTING)
    assert "❌" in format_status_badge(BotStatus.ERROR)
    assert "CUSTOM" in format_status_badge("custom")


def test_mask_token():
    # Standard format: 123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456
    token = "123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456"
    masked = mask_token(token)
    assert "123456789:" in masked
    assert "..." in masked
    assert "ABCdef-GHI" not in masked

    # Short / None token
    assert mask_token(None) == "••••••••••••••••"
    assert mask_token("short") == "••••••••••••••••"

    # Token without colon
    masked_no_colon = mask_token("12345678901234567890")
    assert "••••" in masked_no_colon


def test_is_valid_bot_token():
    valid_token = "123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456"
    assert is_valid_bot_token(valid_token) is True

    # Invalid tokens
    assert is_valid_bot_token("") is False
    assert is_valid_bot_token("invalid_token") is False
    assert is_valid_bot_token("12345:short") is False
    assert is_valid_bot_token("123456789:ABC") is False


def test_sanitize_bot_name():
    assert sanitize_bot_name("  My_Cool_Bot-1.0!@#$  ") == "My_Cool_Bot-1.0"
    assert sanitize_bot_name("!!!@@@###$$$") == "MyBot"
    # Extremely long name truncated
    long_name = "A" * 60
    assert len(sanitize_bot_name(long_name)) <= 40


def test_detect_entry_point(tmp_path: Path):
    # bot.py preferred
    (tmp_path / "main.py").write_text("print('main')")
    (tmp_path / "bot.py").write_text("print('bot')")
    assert detect_entry_point(tmp_path) == "bot.py"

    # main.py next
    (tmp_path / "bot.py").unlink()
    assert detect_entry_point(tmp_path) == "main.py"

    # any .py file if standard names absent
    (tmp_path / "main.py").unlink()
    (tmp_path / "custom_script.py").write_text("print('custom')")
    assert detect_entry_point(tmp_path) == "custom_script.py"

    # fallback to main.py if no py files exist
    (tmp_path / "custom_script.py").unlink()
    assert detect_entry_point(tmp_path) == "main.py"


def test_format_bot_card():
    bot = HostedBot(
        id=42,
        user_id=100,
        name="TestBot",
        status=BotStatus.RUNNING,
        pid=12345,
        entry_point="main.py",
        auto_restart=True,
        restart_count=1,
        env_vars={"KEY": "VAL"},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    card = format_bot_card(bot, is_running=True, pid=12345)
    assert "TestBot" in card
    assert "42" in card
    assert "12345" in card
    assert "main.py" in card
    assert "1 configured" in card


def test_get_system_metrics():
    metrics = get_system_metrics()
    assert "cpu_percent" in metrics
    assert "cpu_cores" in metrics
    assert "ram_total_gb" in metrics
    assert "ram_used_gb" in metrics
    assert "disk_total_gb" in metrics
    assert "uptime_str" in metrics


def test_apply_font_style():
    from src.bot.utils import apply_font_style

    sample = "Host New Bot 2026"

    # Plain / invalid style returns text unchanged
    assert apply_font_style(sample, "plain") == sample
    assert apply_font_style(sample, "unknown_style") == sample
    assert apply_font_style("", "bold") == ""

    # Bold (sans-serif bold)
    bold = apply_font_style(sample, "bold")
    assert "𝗛𝗼𝘀𝘁" in bold
    assert "𝟮𝟬𝟮𝟲" in bold

    # Sans bold alias
    sans_bold = apply_font_style(sample, "sans_bold")
    assert sans_bold == bold

    # Monospace
    mono = apply_font_style(sample, "monospace")
    assert "𝙷𝚘𝚜𝚝" in mono
    assert "𝟸𝟶𝟸𝟼" in mono

    # Serif bold
    serif = apply_font_style(sample, "serif_bold")
    assert "𝐇𝐨𝐬𝐭" in serif
    assert "𝟐𝟎𝟐𝟔" in serif

    # Italic
    italic = apply_font_style(sample, "italic")
    assert "𝘏𝘰𝘴𝘵" in italic


def test_normalize_button_text():
    from src.bot.utils import apply_font_style, normalize_button_text

    original = "🚀 Host New Bot"
    assert normalize_button_text("") == ""
    assert normalize_button_text("  🚀   Host   New   Bot  ") == original

    # Various stylized versions normalize back to original
    for style in ["bold", "sans_bold", "serif_bold", "monospace", "italic"]:
        styled = apply_font_style(original, style)
        assert normalize_button_text(styled) == original


def test_strip_emojis():
    from src.bot.utils import strip_emojis

    assert strip_emojis("🚀 Host New Bot") == "Host New Bot"
    assert strip_emojis("🤖 My Bots") == "My Bots"
    assert strip_emojis("📊 System Status") == "System Status"
    assert strip_emojis("❓ Help & Guide") == "Help & Guide"
    assert strip_emojis("👑 Admin Panel") == "Admin Panel"
    assert strip_emojis("") == ""


def test_is_button_match():
    from src.bot.utils import apply_font_style, is_button_match

    target = "🚀 Host New Bot"

    # Exact match
    assert is_button_match("🚀 Host New Bot", target) is True

    # Styled matches (bold, monospace, serif bold, italic)
    for style in ["bold", "sans_bold", "serif_bold", "monospace", "italic"]:
        styled = apply_font_style(target, style)
        assert is_button_match(styled, target) is True

    # Text without emoji
    assert is_button_match("Host New Bot", target) is True
    assert is_button_match("host new bot", target) is True

    # Styled text without emoji
    assert is_button_match(apply_font_style("Host New Bot", "bold"), target) is True

    # Non-matching text
    assert is_button_match("🤖 My Bots", target) is False
    assert is_button_match("", target) is False
    assert is_button_match("Random text", target) is False


@pytest.mark.asyncio
async def test_button_match_filter():
    from unittest.mock import AsyncMock
    from aiogram import types
    from src.bot.utils import ButtonMatchFilter, apply_font_style, button_filter

    filter_obj = ButtonMatchFilter("🚀 Host New Bot", "Host New Bot")

    # None text
    msg_empty = AsyncMock(spec=types.Message)
    msg_empty.text = None
    assert await filter_obj(msg_empty) is False

    # Bold styled text
    msg_bold = AsyncMock(spec=types.Message)
    msg_bold.text = apply_font_style("🚀 Host New Bot", "bold")
    assert await filter_obj(msg_bold) is True

    # Monospace styled text
    msg_mono = AsyncMock(spec=types.Message)
    msg_mono.text = apply_font_style("🚀 Host New Bot", "monospace")
    assert await filter_obj(msg_mono) is True

    # Helper button_filter factory
    alt_filter = button_filter("🤖 My Bots")
    msg_mybots = AsyncMock(spec=types.Message)
    msg_mybots.text = apply_font_style("🤖 My Bots", "bold")
    assert await alt_filter(msg_mybots) is True
    assert await alt_filter(msg_bold) is False

