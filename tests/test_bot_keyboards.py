"""
Unit tests for src/bot/keyboards/reply.py and src/bot/keyboards/inline.py.
"""

from aiogram.types import InlineKeyboardButton, KeyboardButton

from src.bot.keyboards.inline import (
    get_admin_menu_keyboard,
    get_admin_running_bots_keyboard,
    get_admin_user_quota_keyboard,
    get_bot_control_keyboard,
    get_bots_list_keyboard,
    get_broadcast_confirm_keyboard,
    get_cancel_inline_keyboard,
    get_crash_alert_keyboard,
    get_delete_confirm_keyboard,
    get_deployment_methods_keyboard,
    get_env_vars_keyboard,
    get_logs_keyboard,
    get_templates_keyboard,
)
from src.bot.keyboards.reply import get_main_menu_keyboard
from src.core.config import settings
from src.core.database import BotStatus, HostedBot


def test_main_menu_keyboard_regular_user():
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [99999]
    try:
        kb = get_main_menu_keyboard(is_admin=False, telegram_id=11111)
        assert kb.resize_keyboard is True
        assert kb.is_persistent is True

        all_buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "🚀 Host New Bot" in all_buttons
        assert "🤖 My Bots" in all_buttons
        assert "📊 System Status" in all_buttons
        assert "❓ Help & Guide" in all_buttons
        assert "👑 Admin Panel" not in all_buttons
    finally:
        settings.ADMIN_IDS = original_admins


def test_main_menu_keyboard_admin_flag():
    kb = get_main_menu_keyboard(is_admin=True)
    all_buttons = [btn.text for row in kb.keyboard for btn in row]
    assert "👑 Admin Panel" in all_buttons


def test_main_menu_keyboard_admin_by_id():
    original_admins = list(settings.ADMIN_IDS)
    settings.ADMIN_IDS = [88888]
    try:
        kb = get_main_menu_keyboard(is_admin=False, telegram_id=88888)
        all_buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "👑 Admin Panel" in all_buttons
    finally:
        settings.ADMIN_IDS = original_admins


def test_deployment_methods_keyboard():
    kb = get_deployment_methods_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "deploy_type:zip" in callbacks
    assert "deploy_type:single_file" in callbacks
    assert "deploy_type:github" in callbacks
    assert "deploy_type:template" in callbacks
    assert "cancel_flow" in callbacks


def test_templates_keyboard():
    kb = get_templates_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "template_select:broadcast" in callbacks
    assert "template_select:auto_reply" in callbacks
    assert "template_select:filter" in callbacks
    assert "template_select:echo" in callbacks
    assert "host_menu_back" in callbacks


def test_bots_list_keyboard():
    # Empty list
    empty_kb = get_bots_list_keyboard([])
    callbacks_empty = [btn.callback_data for row in empty_kb.inline_keyboard for btn in row]
    assert "host_new_bot_action" in callbacks_empty
    assert "refresh_bots_list" in callbacks_empty

    # List with dummy bots
    dummy_bot1 = HostedBot(id=1, user_id=10, name="AlphaBot", status=BotStatus.RUNNING)
    dummy_bot2 = HostedBot(id=2, user_id=10, name="BetaBot", status=BotStatus.STOPPED)
    populated_kb = get_bots_list_keyboard([dummy_bot1, dummy_bot2])

    buttons = [btn for row in populated_kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for btn in buttons]
    texts = [btn.text for btn in buttons]

    assert "bot_manage:1" in callbacks
    assert "bot_manage:2" in callbacks
    assert any("🟢" in t and "AlphaBot" in t for t in texts)
    assert any("⏹️" in t and "BetaBot" in t for t in texts)


def test_bot_control_keyboard():
    # When running -> should show Stop button
    kb_running = get_bot_control_keyboard(bot_id=10, is_running=True)
    running_callbacks = [btn.callback_data for row in kb_running.inline_keyboard for btn in row]
    assert "bot_stop:10" in running_callbacks
    assert "bot_start:10" not in running_callbacks
    assert "bot_restart:10" in running_callbacks
    assert "bot_logs:10" in running_callbacks
    assert "bot_env:10" in running_callbacks
    assert "bot_delete_prompt:10" in running_callbacks
    assert "back_to_my_bots" in running_callbacks

    # When stopped -> should show Start button
    kb_stopped = get_bot_control_keyboard(bot_id=10, is_running=False)
    stopped_callbacks = [btn.callback_data for row in kb_stopped.inline_keyboard for btn in row]
    assert "bot_start:10" in stopped_callbacks
    assert "bot_stop:10" not in stopped_callbacks


def test_logs_and_delete_keyboards():
    logs_kb = get_logs_keyboard(bot_id=7)
    logs_callbacks = [btn.callback_data for row in logs_kb.inline_keyboard for btn in row]
    assert "bot_logs_refresh:7" in logs_callbacks
    assert "bot_manage:7" in logs_callbacks

    del_kb = get_delete_confirm_keyboard(bot_id=7)
    del_callbacks = [btn.callback_data for row in del_kb.inline_keyboard for btn in row]
    assert "bot_delete_confirm:7" in del_callbacks
    assert "bot_manage:7" in del_callbacks


def test_env_vars_keyboard():
    # Without existing vars
    kb_no_vars = get_env_vars_keyboard(bot_id=5, has_vars=False)
    no_vars_callbacks = [btn.callback_data for row in kb_no_vars.inline_keyboard for btn in row]
    assert "env_add:5" in no_vars_callbacks
    assert "env_del:5" not in no_vars_callbacks
    assert "bot_manage:5" in no_vars_callbacks

    # With existing vars
    kb_vars = get_env_vars_keyboard(bot_id=5, has_vars=True)
    vars_callbacks = [btn.callback_data for row in kb_vars.inline_keyboard for btn in row]
    assert "env_add:5" in vars_callbacks
    assert "env_del:5" in vars_callbacks
    assert "bot_manage:5" in vars_callbacks


def test_admin_keyboards():
    admin_kb = get_admin_menu_keyboard()
    admin_callbacks = [btn.callback_data for row in admin_kb.inline_keyboard for btn in row]
    assert "admin_stats" in admin_callbacks
    assert "admin_users" in admin_callbacks
    assert "admin_running_bots" in admin_callbacks
    assert "admin_broadcast" in admin_callbacks
    assert "admin_refresh" in admin_callbacks

    quota_kb = get_admin_user_quota_keyboard(target_user_id=123)
    quota_callbacks = [btn.callback_data for row in quota_kb.inline_keyboard for btn in row]
    assert "quota_mod:123:+1" in quota_callbacks
    assert "quota_mod:123:+5" in quota_callbacks
    assert "quota_mod:123:-1" in quota_callbacks
    assert "quota_set:123" in quota_callbacks
    assert "admin_refresh" in quota_callbacks

    dummy_bot = HostedBot(id=99, user_id=10, name="DeadBot", status=BotStatus.RUNNING, pid=1234)
    running_kb = get_admin_running_bots_keyboard([dummy_bot])
    running_callbacks = [btn.callback_data for row in running_kb.inline_keyboard for btn in row]
    assert "admin_kill:99" in running_callbacks
    assert "admin_running_bots" in running_callbacks


def test_broadcast_and_crash_alert_keyboards():
    b_kb = get_broadcast_confirm_keyboard()
    b_callbacks = [btn.callback_data for row in b_kb.inline_keyboard for btn in row]
    assert "broadcast_confirm" in b_callbacks
    assert "broadcast_cancel" in b_callbacks

    crash_kb = get_crash_alert_keyboard(bot_id=88)
    crash_callbacks = [btn.callback_data for row in crash_kb.inline_keyboard for btn in row]
    assert "bot_restart:88" in crash_callbacks
    assert "bot_logs:88" in crash_callbacks
    assert "bot_manage:88" in crash_callbacks

    cancel_kb = get_cancel_inline_keyboard()
    cancel_callbacks = [btn.callback_data for row in cancel_kb.inline_keyboard for btn in row]
    assert "cancel_flow" in cancel_callbacks


def test_main_menu_keyboard_font_styles():
    from src.bot.keyboards.reply import get_main_menu_buttons, get_main_menu_keyboard
    from src.bot.utils import normalize_button_text

    for style in ["bold", "monospace", "serif_bold", "italic", "plain"]:
        kb = get_main_menu_keyboard(is_admin=True, font_style=style)
        buttons = [btn.text for row in kb.keyboard for btn in row]
        assert len(buttons) == 5
        # Verify all buttons normalize back to the canonical plain texts
        normalized = [normalize_button_text(b) for b in buttons]
        assert "🚀 Host New Bot" in normalized
        assert "🤖 My Bots" in normalized
        assert "📊 System Status" in normalized
        assert "❓ Help & Guide" in normalized
        assert "👑 Admin Panel" in normalized

    # Helper function check
    btn_list = get_main_menu_buttons(is_admin=False, font_style="bold")
    assert len(btn_list) == 4
    assert any("𝗛𝗼𝘀𝘁" in b for b in btn_list)


def test_inline_keyboards_font_styles():
    from src.bot.keyboards.inline import (
        get_admin_menu_keyboard,
        get_bot_control_keyboard,
        get_deployment_methods_keyboard,
        get_templates_keyboard,
    )

    deploy_kb = get_deployment_methods_keyboard(font_style="bold")
    deploy_texts = [btn.text for row in deploy_kb.inline_keyboard for btn in row]
    assert any("𝗭𝗶𝗽" in t for t in deploy_texts)

    tpl_kb = get_templates_keyboard(font_style="monospace")
    tpl_texts = [btn.text for row in tpl_kb.inline_keyboard for btn in row]
    assert any("𝙱𝚘𝚝" in t for t in tpl_texts)

    ctrl_kb = get_bot_control_keyboard(bot_id=1, is_running=True, font_style="bold")
    ctrl_texts = [btn.text for row in ctrl_kb.inline_keyboard for btn in row]
    assert any("𝗦𝘁𝗼𝗽" in t for t in ctrl_texts)

    admin_kb = get_admin_menu_keyboard(font_style="italic")
    admin_texts = [btn.text for row in admin_kb.inline_keyboard for btn in row]
    assert any("𝘗𝘭𝘢𝘵𝘧𝘰𝘳𝘮" in t for t in admin_texts)

