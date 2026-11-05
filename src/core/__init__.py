"""
Core Engine, Database, Sandbox, and Supervisor Exports.
"""

from src.core.config import Settings, settings
from src.core.database import (
    Base,
    BotLogEntry,
    BotStatus,
    HostedBot,
    User,
    add_bot_log,
    close_db,
    create_hosted_bot,
    delete_bot,
    get_all_bots,
    get_bot,
    get_bot_logs_from_db,
    get_engine,
    get_or_create_user,
    get_session,
    get_sessionmaker,
    get_user,
    get_user_bots,
    init_db,
    update_bot_entry_point,
    update_bot_env_vars,
    update_bot_restart_count,
    update_bot_status,
    update_user_max_bots,
)
from src.core.sandbox import (
    BotSandbox,
    SandboxSecurityError,
    create_bot_workspace,
    create_virtualenv,
    get_bot_workspace,
    get_venv_python,
    install_requirements,
    safe_extract_zip,
)
from src.core.supervisor import (
    BotProcessSupervisor,
    supervisor,
)

__all__ = [
    # Config
    "Settings",
    "settings",
    # Database
    "Base",
    "BotStatus",
    "User",
    "HostedBot",
    "BotLogEntry",
    "init_db",
    "close_db",
    "get_engine",
    "get_sessionmaker",
    "get_session",
    "get_or_create_user",
    "get_user",
    "update_user_max_bots",
    "create_hosted_bot",
    "get_bot",
    "get_user_bots",
    "get_all_bots",
    "update_bot_status",
    "update_bot_restart_count",
    "update_bot_entry_point",
    "update_bot_env_vars",
    "delete_bot",
    "add_bot_log",
    "get_bot_logs_from_db",
    # Sandbox
    "BotSandbox",
    "SandboxSecurityError",
    "get_bot_workspace",
    "create_bot_workspace",
    "get_venv_python",
    "create_virtualenv",
    "install_requirements",
    "safe_extract_zip",
    # Supervisor
    "BotProcessSupervisor",
    "supervisor",
]
