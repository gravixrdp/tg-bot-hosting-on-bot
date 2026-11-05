"""
Telegram Bot Handlers Package.

Registers and exports all routers for start/help, hosting workflows,
bot management, system telemetry, and administrative controls.
"""

from aiogram import Router

from src.bot.handlers.admin import router as admin_router
from src.bot.handlers.host_flow import router as host_flow_router
from src.bot.handlers.my_bots import router as my_bots_router
from src.bot.handlers.start import router as start_router
from src.bot.handlers.status import router as status_router


def get_all_routers() -> list[Router]:
    """Return all configured bot routers in logical registration order."""
    return [
        start_router,
        host_flow_router,
        my_bots_router,
        status_router,
        admin_router,
    ]


__all__ = [
    "start_router",
    "host_flow_router",
    "my_bots_router",
    "status_router",
    "admin_router",
    "get_all_routers",
]
