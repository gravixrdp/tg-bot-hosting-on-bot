"""
Bot Workspace Sandbox and Process Isolation Manager.

Handles per-bot isolated directory management, virtual environment (venv)
creation, asynchronous pip dependency installation, and secure zip extraction
with Zip-Slip traversal protection.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple, Union
import zipfile

from src.core.config import settings


class SandboxSecurityError(Exception):
    """Raised when an operation violates sandbox filesystem or security boundaries."""
    pass


class BotSandbox:
    """Manages workspace lifecycle, environments, and file operations for a hosted bot."""

    def __init__(self, bot_id: int) -> None:
        self.bot_id = bot_id
        self.workspace_dir: Path = self.get_bot_workspace(bot_id)

    @classmethod
    def get_bot_workspace(cls, bot_id: int) -> Path:
        """Calculate the absolute workspace directory path for a bot."""
        root = settings.get_absolute_workspace_root()
        return (root / str(bot_id)).resolve()

    def ensure_workspace(self) -> Path:
        """Ensure the bot workspace directory exists and return its path."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.workspace_dir

    def get_venv_dir(self) -> Path:
        """Return the path to the bot's private virtualenv directory."""
        return self.workspace_dir / ".venv"

    def get_venv_python(self) -> Path:
        """Return platform-specific path to Python executable inside the bot's venv."""
        venv_dir = self.get_venv_dir()
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def get_venv_pip(self) -> Path:
        """Return platform-specific path to pip executable inside the bot's venv."""
        venv_dir = self.get_venv_dir()
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "pip.exe"
        return venv_dir / "bin" / "pip"

    def has_venv(self) -> bool:
        """Check if a valid virtualenv with Python executable exists."""
        return self.get_venv_python().is_file()

    async def create_virtualenv(
        self, with_pip: bool = False, overwrite: bool = False
    ) -> Tuple[bool, str, Path]:
        """
        Asynchronously create a Python virtual environment in the bot workspace.

        Args:
            with_pip: If True, install pip during venv creation. Defaults to False for
                      near-instant (~0.3s) lightweight environment creation.
            overwrite: If True, recreate the virtual environment if it already exists.

        Returns:
            Tuple of (success: bool, message: str, python_path: Path).
        """
        self.ensure_workspace()
        venv_dir = self.get_venv_dir()
        python_exe = self.get_venv_python()

        if self.has_venv() and not overwrite:
            return True, "Virtual environment already exists", python_exe

        if overwrite and venv_dir.exists():
            try:
                shutil.rmtree(venv_dir)
            except Exception as e:
                return False, f"Failed to remove existing venv: {e}", python_exe

        # Execute python -m venv <venv_dir>
        cmd = [sys.executable, "-m", "venv"]
        if not with_pip:
            cmd.append("--without-pip")
        cmd.append(str(venv_dir))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return True, "Virtual environment created successfully", python_exe
            err_msg = stderr.decode(errors="replace").strip()
            return False, f"Virtualenv creation failed (code {process.returncode}): {err_msg}", python_exe
        except Exception as exc:
            return False, f"Error creating virtualenv: {exc}", python_exe

    async def install_requirements(
        self,
        requirements_file: Optional[Path] = None,
        packages: Optional[List[str]] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Asynchronously install dependencies into the bot's virtual environment.

        Args:
            requirements_file: Path to requirements.txt (defaults to workspace requirements.txt).
            packages: Optional list of package names to install directly.
            timeout: Maximum execution timeout in seconds.

        Returns:
            Tuple of (success: bool, output_logs: str).
        """
        if not self.has_venv():
            success, msg, _ = await self.create_virtualenv()
            if not success:
                return False, f"Cannot install dependencies: {msg}"

        python_exe = self.get_venv_python()
        cmd = [str(python_exe), "-m", "pip", "install", "--no-cache-dir"]

        target_req = requirements_file
        if target_req is None:
            default_req = self.workspace_dir / "requirements.txt"
            if default_req.is_file():
                target_req = default_req

        has_target = False
        if target_req and target_req.is_file():
            cmd.extend(["-r", str(target_req)])
            has_target = True

        if packages:
            cmd.extend(packages)
            has_target = True

        if not has_target:
            return True, "No requirements.txt or packages specified; skipping installation."

        timeout_sec = timeout or settings.PIP_TIMEOUT_SECONDS
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.workspace_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, f"pip installation timed out after {timeout_sec} seconds"

            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            combined_log = f"{out}\n{err}".strip()

            if process.returncode == 0:
                return True, combined_log or "Dependencies installed successfully."
            return False, f"pip install exited with code {process.returncode}:\n{combined_log}"

        except Exception as exc:
            return False, f"Error running pip install: {exc}"

    def safe_extract_zip(
        self,
        zip_source: Union[str, Path, bytes, BinaryIO],
    ) -> List[Path]:
        """
        Safely extract a zip archive into the bot's workspace, preventing Zip-Slip
        and path traversal vulnerabilities.

        Args:
            zip_source: File path, raw bytes, or file-like object containing zip data.

        Returns:
            List of Path objects representing extracted files and directories.

        Raises:
            SandboxSecurityError: If an archive member attempts directory traversal
                                  or contains forbidden filesystem constructs.
        """
        target_dir = self.ensure_workspace().resolve()

        if isinstance(zip_source, bytes):
            zip_file = zipfile.ZipFile(io.BytesIO(zip_source))
        elif isinstance(zip_source, (str, Path)):
            zip_file = zipfile.ZipFile(str(zip_source))
        else:
            zip_file = zipfile.ZipFile(zip_source)

        extracted_paths: List[Path] = []

        with zip_file:
            # First pass: Validate every member for security violations
            for member in zip_file.infolist():
                filename = member.filename

                # Reject absolute paths (POSIX '/' or Windows drive letters 'C:\')
                if (
                    filename.startswith(("/", "\\"))
                    or os.path.isabs(filename)
                    or (len(filename) > 1 and filename[1] == ":")
                ):
                    raise SandboxSecurityError(
                        f"Zip entry has an absolute path which is disallowed: '{filename}'"
                    )

                # Check for path traversal segments ('..' in path)
                parts = Path(filename).parts
                if ".." in parts:
                    raise SandboxSecurityError(
                        f"Zip-Slip path traversal attempt detected in entry: '{filename}'"
                    )

                # Resolve candidate target path
                candidate_path = (target_dir / filename).resolve()

                # Verify candidate is strictly within target directory
                try:
                    candidate_path.relative_to(target_dir)
                except ValueError:
                    raise SandboxSecurityError(
                        f"Target path '{candidate_path}' escapes sandbox boundary '{target_dir}'"
                    )

                # Disallow symbolic links or suspicious Unix permission modes
                # Upper 16 bits of external_attr contain Unix file attributes
                unix_mode = member.external_attr >> 16
                if unix_mode != 0 and stat.S_ISLNK(unix_mode):
                    raise SandboxSecurityError(
                        f"Symbolic link detected in zip entry '{filename}', which is forbidden for security."
                    )

            # Second pass: Extract files safely
            for member in zip_file.infolist():
                destination = (target_dir / member.filename).resolve()
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    extracted_paths.append(destination)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zip_file.open(member) as source_f, open(destination, "wb") as target_f:
                        shutil.copyfileobj(source_f, target_f)
                    extracted_paths.append(destination)

        return extracted_paths

    def clean_workspace(self) -> bool:
        """
        Delete the entire bot workspace and all its contents.

        Returns:
            True if cleaned successfully, False otherwise.
        """
        if self.workspace_dir.exists():
            try:
                shutil.rmtree(self.workspace_dir)
                return True
            except Exception:
                return False
        return True

    def list_files(self, include_venv: bool = False) -> List[dict]:
        """
        List files in the bot workspace with relative path, size, and type.

        Args:
            include_venv: Whether to include files inside .venv (defaults to False).

        Returns:
            List of file metadata dicts.
        """
        if not self.workspace_dir.exists():
            return []

        results = []
        for root, dirs, files in os.walk(self.workspace_dir):
            root_path = Path(root)
            rel_root = root_path.relative_to(self.workspace_dir)

            if not include_venv:
                if ".venv" in rel_root.parts:
                    continue
                # Skip walking into .venv
                if ".venv" in dirs:
                    dirs.remove(".venv")

            for file_name in files:
                file_path = root_path / file_name
                try:
                    stat_res = file_path.stat()
                    results.append({
                        "name": file_name,
                        "rel_path": str(file_path.relative_to(self.workspace_dir).as_posix()),
                        "size": stat_res.st_size,
                        "is_dir": False,
                    })
                except OSError:
                    continue

        return results


# Functional module-level shortcuts
def get_bot_workspace(bot_id: int) -> Path:
    """Module-level shortcut for getting bot workspace path."""
    return BotSandbox.get_bot_workspace(bot_id)


def create_bot_workspace(bot_id: int) -> Path:
    """Module-level shortcut for ensuring bot workspace directory."""
    return BotSandbox(bot_id).ensure_workspace()


def get_venv_python(bot_id: int) -> Path:
    """Module-level shortcut for getting venv Python executable."""
    return BotSandbox(bot_id).get_venv_python()


async def create_virtualenv(
    bot_id: int, with_pip: bool = False, overwrite: bool = False
) -> Tuple[bool, str, Path]:
    """Module-level shortcut for creating a bot virtual environment."""
    return await BotSandbox(bot_id).create_virtualenv(with_pip=with_pip, overwrite=overwrite)


async def install_requirements(
    bot_id: int,
    requirements_file: Optional[Path] = None,
    packages: Optional[List[str]] = None,
    timeout: Optional[int] = None,
) -> Tuple[bool, str]:
    """Module-level shortcut for installing bot requirements."""
    return await BotSandbox(bot_id).install_requirements(
        requirements_file=requirements_file,
        packages=packages,
        timeout=timeout,
    )


def safe_extract_zip(
    zip_source: Union[str, Path, bytes, BinaryIO],
    target_dir: Path,
) -> List[Path]:
    """
    Module-level function for safely extracting a zip file into a target directory
    with full Zip-Slip protection.
    """
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(zip_source, bytes):
        zip_file = zipfile.ZipFile(io.BytesIO(zip_source))
    elif isinstance(zip_source, (str, Path)):
        zip_file = zipfile.ZipFile(str(zip_source))
    else:
        zip_file = zipfile.ZipFile(zip_source)

    extracted_paths: List[Path] = []

    with zip_file:
        for member in zip_file.infolist():
            filename = member.filename
            if (
                filename.startswith(("/", "\\"))
                or os.path.isabs(filename)
                or (len(filename) > 1 and filename[1] == ":")
            ):
                raise SandboxSecurityError(f"Absolute path disallowed in zip: {filename}")
            if ".." in Path(filename).parts:
                raise SandboxSecurityError(f"Path traversal detected in zip: {filename}")

            destination = (target_dir / filename).resolve()
            try:
                destination.relative_to(target_dir)
            except ValueError:
                raise SandboxSecurityError(f"Zip extraction escape attempt: {destination}")

            unix_mode = member.external_attr >> 16
            if unix_mode != 0 and stat.S_ISLNK(unix_mode):
                raise SandboxSecurityError(f"Symbolic link forbidden: {filename}")

        for member in zip_file.infolist():
            destination = (target_dir / member.filename).resolve()
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                extracted_paths.append(destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(member) as source_f, open(destination, "wb") as target_f:
                    shutil.copyfileobj(source_f, target_f)
                extracted_paths.append(destination)

    return extracted_paths
