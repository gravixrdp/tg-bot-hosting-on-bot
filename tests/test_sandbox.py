"""
Unit tests for src/core/sandbox.py and Zip-Slip vulnerability prevention.
"""

import io
import zipfile
from pathlib import Path

import pytest

from src.core.sandbox import (
    BotSandbox,
    SandboxSecurityError,
    create_bot_workspace,
    get_bot_workspace,
    get_venv_python,
    safe_extract_zip,
)


def test_workspace_paths(temp_environment):
    bot_id = 42
    ws = get_bot_workspace(bot_id)
    assert str(bot_id) in str(ws)

    sandbox = BotSandbox(bot_id)
    ensured = sandbox.ensure_workspace()
    assert ensured.exists()
    assert ensured.is_dir()

    python_exe = get_venv_python(bot_id)
    assert ".venv" in str(python_exe)


def test_safe_zip_extraction_valid(temp_environment):
    bot_id = 101
    sandbox = BotSandbox(bot_id)
    target_dir = sandbox.ensure_workspace()

    # Create a valid zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("main.py", "print('hello from bot')\n")
        zf.writestr("utils/helpers.py", "def add(a, b): return a + b\n")

    zip_bytes = zip_buffer.getvalue()
    extracted = sandbox.safe_extract_zip(zip_bytes)

    assert len(extracted) >= 2
    assert (target_dir / "main.py").is_file()
    assert (target_dir / "utils" / "helpers.py").is_file()
    assert "hello from bot" in (target_dir / "main.py").read_text()


def test_safe_zip_slip_relative_escape(temp_environment):
    bot_id = 102
    sandbox = BotSandbox(bot_id)

    # Malicious zip attempting directory traversal ../
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../evil.txt", "malicious payload\n")

    zip_bytes = zip_buffer.getvalue()

    with pytest.raises(SandboxSecurityError) as exc_info:
        sandbox.safe_extract_zip(zip_bytes)

    assert "Zip-Slip" in str(exc_info.value) or "traversal" in str(exc_info.value).lower()


def test_safe_zip_slip_absolute_path_escape(temp_environment):
    bot_id = 103
    sandbox = BotSandbox(bot_id)

    # Malicious zip with absolute path
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        # Create an entry with absolute Unix path using ZipInfo to preserve leading slash
        info = zipfile.ZipInfo()
        info.filename = "/tmp/evil.txt"
        zf.writestr(info, b"payload")

    zip_bytes = zip_buffer.getvalue()

    with pytest.raises(SandboxSecurityError) as exc_info:
        sandbox.safe_extract_zip(zip_bytes)

    assert "absolute path" in str(exc_info.value).lower()


def test_list_files_and_clean_workspace(temp_environment):
    bot_id = 104
    sandbox = BotSandbox(bot_id)
    ws = sandbox.ensure_workspace()

    # Create dummy files
    (ws / "main.py").write_text("print('test')")
    (ws / "config.json").write_text("{}")
    dummy_venv = ws / ".venv" / "Lib"
    dummy_venv.mkdir(parents=True)
    (dummy_venv / "internal.py").write_text("# internal")

    files = sandbox.list_files(include_venv=False)
    file_names = [f["name"] for f in files]
    assert "main.py" in file_names
    assert "config.json" in file_names
    assert "internal.py" not in file_names  # .venv excluded

    # Test clean workspace
    cleaned = sandbox.clean_workspace()
    assert cleaned is True
    assert not ws.exists()
