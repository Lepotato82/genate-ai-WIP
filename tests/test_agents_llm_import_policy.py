"""
Agents must call LLMs only through llm/client.py — no direct provider SDK imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"
_FORBIDDEN_ROOT_MODULES = frozenset({"groq", "anthropic", "ollama"})


def _py_files():
    for path in sorted(_AGENTS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


@pytest.mark.parametrize("path", list(_py_files()), ids=lambda p: p.name)
def test_agent_file_has_no_direct_groq_anthropic_ollama_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _FORBIDDEN_ROOT_MODULES, f"{path.name}: import {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in _FORBIDDEN_ROOT_MODULES, f"{path.name}: from {node.module}"


def test_at_least_one_agent_module_exists_for_policy() -> None:
    files = list(_py_files())
    assert len(files) >= 3
    names = {p.name for p in files}
    assert "input_processor.py" in names
    assert "product_analysis.py" in names
    assert "ui_analyzer.py" in names
