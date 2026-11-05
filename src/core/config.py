"""
Application Configuration Module.

Loads and validates environment variables and application runtime settings
using Pydantic BaseSettings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Configuration settings for the Telegram Bot Hosting Platform."""

    model_config = SettingsConfigDict(
        env_file=(_BASE_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base application directory
    BASE_DIR: Path = _BASE_DIR

    # Telegram Hosting Bot credentials
    BOT_TOKEN: str = Field(
        default="",
        description="Telegram Bot API Token for the main hosting manager bot",
    )

    # Administrative user Telegram IDs
    ADMIN_IDS: List[int] = Field(
        default_factory=list,
        description="List of Telegram user IDs with global administrative privileges",
    )

    # Sandbox & Storage settings
    WORKSPACE_ROOT: Path = Field(
        default=Path("data/bots"),
        description="Root directory where per-bot isolated workspaces reside",
    )
    MAX_BOTS_PER_USER: int = Field(
        default=3,
        description="Default maximum number of hosted bots allowed per user",
    )

    # Process supervision & logging settings
    LOG_BUFFER_SIZE: int = Field(
        default=1000,
        description="Maximum number of log lines kept in circular in-memory buffer per bot",
    )
    DEFAULT_RESTART_RETRIES: int = Field(
        default=3,
        description="Maximum automatic restart attempts before marking a bot as CRASHED",
    )
    RESTART_DELAY_SECONDS: float = Field(
        default=3.0,
        description="Cool-down duration in seconds before attempting an automatic restart",
    )
    PROCESS_STOP_TIMEOUT: float = Field(
        default=5.0,
        description="Timeout in seconds to wait for graceful process termination before SIGKILL",
    )
    PIP_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Maximum execution time in seconds allowed for dependency installation (pip)",
    )

    # Database settings
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///data/hosting.db",
        description="SQLAlchemy asynchronous database connection string",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        """Parse ADMIN_IDS from various formats (comma-separated, JSON list, or sequence)."""
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    return [int(x) for x in parsed]
                except Exception:
                    pass
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, (list, tuple, set)):
            return [int(x) for x in v]
        return []

    @field_validator("WORKSPACE_ROOT", mode="before")
    @classmethod
    def resolve_workspace_root(cls, v: Any) -> Path:
        """Ensure WORKSPACE_ROOT is resolved as a Path object."""
        if isinstance(v, str):
            return Path(v)
        return v

    def get_absolute_workspace_root(self) -> Path:
        """Return the absolute path for WORKSPACE_ROOT."""
        if self.WORKSPACE_ROOT.is_absolute():
            return self.WORKSPACE_ROOT
        return (self.BASE_DIR / self.WORKSPACE_ROOT).resolve()


# Global settings singleton
settings = Settings()
