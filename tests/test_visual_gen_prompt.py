"""visual_gen_v1.yaml loads and enforces scene-only rules in the system prompt."""

from __future__ import annotations

from prompts.loader import load_prompt


def test_visual_gen_yaml_loads():
    spec = load_prompt("visual_gen_v1")
    assert spec.agent == "visual_gen"
    assert spec.version == "1.1"
    assert "SCENE ONLY" in spec.system_prompt
    assert "image_prompt" in spec.system_prompt
    assert "suggested_format" in spec.system_prompt


def test_visual_gen_yaml_requires_negative_space_for_overlays():
    spec = load_prompt("visual_gen_v1")
    sp = spec.system_prompt
    assert "NEGATIVE SPACE" in sp
    assert "60%" in sp
    assert "LEFT" in sp.upper() or " left " in sp.lower()
    assert "asymmetric" in sp.lower()
