"""
FSM (Finite State Machine) State Definitions for Telegram Bot UI.

Defines conversational states for bot hosting wizards, environment variable
management, and administrative operations.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class HostBotStates(StatesGroup):
    """States for the bot deployment workflow."""

    choosing_deploy_type = State()
    waiting_for_name = State()
    waiting_for_zip = State()
    waiting_for_file = State()
    waiting_for_git_url = State()
    choosing_template = State()
    waiting_for_template_name = State()
    waiting_for_template_token = State()


class EnvVarStates(StatesGroup):
    """States for editing bot environment variables."""

    waiting_for_var_key_value = State()
    waiting_for_delete_key = State()


class AdminStates(StatesGroup):
    """States for administrative panel workflows."""

    waiting_for_user_search = State()
    waiting_for_quota_value = State()
    waiting_for_broadcast_content = State()
