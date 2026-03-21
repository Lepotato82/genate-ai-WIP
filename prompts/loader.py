"""
Prompt loader for YAML prompt files in prompts/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PromptSpec(BaseModel):
    name: str
    agent: str
    version: str
    system_prompt: str = Field(..., alias="system_prompt")
    few_shot_examples: list[dict[str, Any]] = Field(default_factory=list)


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent


def load_prompt(name: str) -> PromptSpec:
    path = _prompts_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid prompt YAML format in {path}")
    return PromptSpec.model_validate(raw)
