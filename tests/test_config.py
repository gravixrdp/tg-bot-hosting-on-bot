"""
Unit tests for src/core/config.py.
"""

from pathlib import Path
import pytest

from src.core.config import Settings


def test_default_settings():
    config = Settings()
    assert config.MAX_BOTS_PER_USER == 3
    assert config.LOG_BUFFER_SIZE == 1000
    assert config.DEFAULT_RESTART_RETRIES == 3
    assert config.RESTART_DELAY_SECONDS == 3.0
    assert config.PROCESS_STOP_TIMEOUT == 5.0
    assert config.PIP_TIMEOUT_SECONDS == 300
    assert "sqlite" in config.DATABASE_URL
    assert isinstance(config.ADMIN_IDS, list)


def test_admin_ids_parsing():
    # Comma-separated string
    cfg1 = Settings(ADMIN_IDS="12345, 67890, 111213")
    assert cfg1.ADMIN_IDS == [12345, 67890, 111213]

    # JSON formatted string
    cfg2 = Settings(ADMIN_IDS="[999, 888, 777]")
    assert cfg2.ADMIN_IDS == [999, 888, 777]

    # Direct list
    cfg3 = Settings(ADMIN_IDS=[42, 43])
    assert cfg3.ADMIN_IDS == [42, 43]

    # Empty string or empty list
    cfg4 = Settings(ADMIN_IDS="")
    assert cfg4.ADMIN_IDS == []

    # Whitespace only
    cfg5 = Settings(ADMIN_IDS="   ")
    assert cfg5.ADMIN_IDS == []


def test_admin_ids_advanced_parsing():
    # Tuple input
    cfg_tuple = Settings(ADMIN_IDS=(101, 102))
    assert cfg_tuple.ADMIN_IDS == [101, 102]

    # Set input
    cfg_set = Settings(ADMIN_IDS={201, 202})
    assert set(cfg_set.ADMIN_IDS) == {201, 202}

    # None input
    cfg_invalid = Settings(ADMIN_IDS=None)
    assert cfg_invalid.ADMIN_IDS == []


def test_workspace_root_resolution():
    # Relative path
    cfg_rel = Settings(WORKSPACE_ROOT=Path("custom/bots"))
    abs_path = cfg_rel.get_absolute_workspace_root()
    assert abs_path.is_absolute()
    assert str(abs_path).endswith(str(Path("custom/bots")))

    # String input converted to Path
    cfg_str = Settings(WORKSPACE_ROOT="another/custom/bots")
    assert isinstance(cfg_str.WORKSPACE_ROOT, Path)
    abs_str_path = cfg_str.get_absolute_workspace_root()
    assert abs_str_path.is_absolute()

    # Absolute path
    fixed_path = Path("C:/data/bots") if Path("C:/").exists() else Path("/data/bots")
    cfg_abs = Settings(WORKSPACE_ROOT=fixed_path)
    assert cfg_abs.get_absolute_workspace_root() == fixed_path


def test_custom_settings_overrides():
    custom = Settings(
        BOT_TOKEN="123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456",
        MAX_BOTS_PER_USER=10,
        LOG_BUFFER_SIZE=5000,
        DEFAULT_RESTART_RETRIES=5,
        RESTART_DELAY_SECONDS=1.5,
        PROCESS_STOP_TIMEOUT=10.0,
        PIP_TIMEOUT_SECONDS=600,
        DATABASE_URL="sqlite+aiosqlite:///tmp/custom.db",
    )
    assert custom.BOT_TOKEN == "123456789:ABCdef-GHIjklMNO_pqRstUVwxyZ123456"
    assert custom.MAX_BOTS_PER_USER == 10
    assert custom.LOG_BUFFER_SIZE == 5000
    assert custom.DEFAULT_RESTART_RETRIES == 5
    assert custom.RESTART_DELAY_SECONDS == 1.5
    assert custom.PROCESS_STOP_TIMEOUT == 10.0
    assert custom.PIP_TIMEOUT_SECONDS == 600
    assert custom.DATABASE_URL == "sqlite+aiosqlite:///tmp/custom.db"
