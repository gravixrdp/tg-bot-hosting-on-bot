"""
Unit tests for pre-built bot templates in src/bot/templates/.
"""

import ast
from pathlib import Path
import pytest


TEMPLATE_NAMES = ["auto_reply", "broadcast", "echo", "filter"]
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "bot" / "templates"


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_template_files_exist(template_name: str):
    tpl_dir = TEMPLATES_DIR / template_name
    assert tpl_dir.is_dir(), f"Template directory missing: {template_name}"

    main_file = tpl_dir / "main.py"
    req_file = tpl_dir / "requirements.txt"

    assert main_file.is_file(), f"main.py missing for template: {template_name}"
    assert req_file.is_file(), f"requirements.txt missing for template: {template_name}"


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_template_python_syntax(template_name: str):
    main_file = TEMPLATES_DIR / template_name / "main.py"
    content = main_file.read_text(encoding="utf-8")

    # Validate Python AST syntax
    parsed = ast.parse(content, filename=str(main_file))
    assert parsed is not None

    # Check for basic bot requirements
    assert "BOT_TOKEN" in content or "token" in content.lower()
