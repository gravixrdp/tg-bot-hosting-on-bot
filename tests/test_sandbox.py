"""
Unit tests for src/core/sandbox.py and Zip-Slip vulnerability prevention.
"""

import asyncio
import io
from pathlib import Path
import stat
from unittest.mock import AsyncMock, patch
import zipfile

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
        info = zipfile.ZipInfo()
        info.filename = "/tmp/evil.txt"
        zf.writestr(info, b"payload")

    zip_bytes = zip_buffer.getvalue()

    with pytest.raises(SandboxSecurityError) as exc_info:
        sandbox.safe_extract_zip(zip_bytes)

    assert "absolute path" in str(exc_info.value).lower()


def test_safe_zip_symlink_rejection(temp_environment):
    bot_id = 105
    sandbox = BotSandbox(bot_id)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        info = zipfile.ZipInfo("symlink_entry")
        # Set Unix symlink mode: S_IFLNK
        info.external_attr = stat.S_IFLNK << 16
        zf.writestr(info, "target_file")

    zip_bytes = zip_buffer.getvalue()
    with pytest.raises(SandboxSecurityError) as exc_info:
        sandbox.safe_extract_zip(zip_bytes)

    assert "symbolic link" in str(exc_info.value).lower()


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


@pytest.mark.asyncio
async def test_pip_install_no_targets(temp_environment):
    bot_id = 106
    sandbox = BotSandbox(bot_id)
    sandbox.ensure_workspace()

    with patch.object(sandbox, "has_venv", return_value=True):
        success, msg = await sandbox.install_requirements()
        assert success is True
        assert "skipping" in msg.lower()


@pytest.mark.asyncio
async def test_pip_install_mocked_success(temp_environment):
    bot_id = 107
    sandbox = BotSandbox(bot_id)
    sandbox.ensure_workspace()

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Successfully installed aiogram-3.0.0\n", b"")
    mock_process.returncode = 0

    with patch.object(sandbox, "has_venv", return_value=True), \
         patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        success, msg = await sandbox.install_requirements(packages=["aiogram==3.0.0"])
        assert success is True
        assert "Successfully installed" in msg
        mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_pip_install_mocked_timeout(temp_environment):
    bot_id = 108
    sandbox = BotSandbox(bot_id)
    sandbox.ensure_workspace()

    mock_process = AsyncMock()
    mock_process.communicate.side_effect = asyncio.TimeoutError
    from unittest.mock import MagicMock
    mock_process.kill = MagicMock()
    mock_process.wait.return_value = None

    with patch.object(sandbox, "has_venv", return_value=True), \
         patch("asyncio.create_subprocess_exec", return_value=mock_process):
        success, msg = await sandbox.install_requirements(packages=["heavy-pkg"], timeout=1)
        assert success is False
        assert "timed out" in msg.lower()
