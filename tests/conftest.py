"""
Pytest configuration and shared fixtures for the test suite.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

from src.core.config import settings
from src.core.database import Base, close_db, get_engine, get_sessionmaker, init_db
from src.core.supervisor import supervisor


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create a session-wide event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def temp_environment(tmp_path: Path) -> AsyncGenerator[dict, None]:
    """
    Set up an isolated temporary database and sandbox workspace for testing.
    """
    db_file = tmp_path / "test_hosting.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    workspace_dir = tmp_path / "bots"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Save original settings
    original_db_url = settings.DATABASE_URL
    original_workspace = settings.WORKSPACE_ROOT

    # Override settings for tests
    settings.DATABASE_URL = db_url
    settings.WORKSPACE_ROOT = workspace_dir

    # Reset any active engine
    await close_db()

    # Initialize schema
    await init_db(db_url)

    yield {
        "db_url": db_url,
        "db_file": db_file,
        "workspace_dir": workspace_dir,
    }

    # Teardown
    await supervisor.shutdown()
    await close_db()

    settings.DATABASE_URL = original_db_url
    settings.WORKSPACE_ROOT = original_workspace
