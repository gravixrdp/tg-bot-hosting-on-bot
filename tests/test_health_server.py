"""
Tests for the HTTP Health Check and Keep-Alive Server.
Verifies the Hugging Face Spaces and UptimeRobot monitoring endpoints.
"""

from __future__ import annotations

import aiohttp
import pytest
import pytest_asyncio

from src.main import start_health_server


@pytest_asyncio.fixture
async def health_server():
    """Start and tear down health server on a dedicated test port."""
    test_port = 7872
    runner = await start_health_server(port=test_port)
    base_url = f"http://127.0.0.1:{test_port}"
    try:
        yield base_url
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_health_check_endpoint(health_server: str) -> None:
    """Ensure GET /health returns 200 OK with expected JSON payload."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{health_server}/health") as response:
            assert response.status == 200
            assert "application/json" in response.headers.get("Content-Type", "")
            data = await response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "telegram-bot-hosting-platform"
            assert data["uptime_robot"] == "ok"


@pytest.mark.asyncio
async def test_root_landing_page(health_server: str) -> None:
    """Ensure GET / returns 200 OK with valid HTML landing page."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{health_server}/") as response:
            assert response.status == 200
            assert "text/html" in response.headers.get("Content-Type", "")
            content = await response.text()
            assert "<!DOCTYPE html>" in content
            assert "Telegram Bot Hosting" in content
            assert "Hugging Face Spaces" in content


@pytest.mark.asyncio
async def test_invalid_route_returns_404(health_server: str) -> None:
    """Ensure undefined paths return 404 Not Found."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{health_server}/nonexistent") as response:
            assert response.status == 404
