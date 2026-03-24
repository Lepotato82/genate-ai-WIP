"""Unit tests for agents/ui_analyzer.py (25+ cases)."""

from __future__ import annotations

import json

import pytest

from agents import ui_analyzer
from config import settings
from schemas.input_package import InputPackage


@pytest.fixture(autouse=True)
def _restore_mock_mode():
    old = settings.MOCK_MODE
    yield
    settings.MOCK_MODE = old


def _pkg(
    *,
    run_id: str = "u1",
    css_tokens: dict[str, str] | None = None,
    user_image: bytes | None = None,
) -> InputPackage:
    return InputPackage(
        url="https://brand.example",
        run_id=run_id,
        css_tokens=css_tokens or {"--color-brand-bg": "#5e6ad2", "--foreground": "#111"},
        user_image=user_image,
    )


def test_normalize_font_weights_integers_become_floats() -> None:
    assert ui_analyzer._normalize_font_weights([400, 510, 590]) == [400.0, 510.0, 590.0]


def test_normalize_font_weights_string_numeric() -> None:
    assert ui_analyzer._normalize_font_weights(["510", "590"]) == [510.0, 590.0]


def test_normalize_font_weights_non_list_defaults() -> None:
    assert ui_analyzer._normalize_font_weights(None) == [400.0]
    assert ui_analyzer._normalize_font_weights("nope") == [400.0]


def test_normalize_font_weights_skips_bad_entries() -> None:
    assert ui_analyzer._normalize_font_weights([400, "bad", 600]) == [400.0, 600.0]


def test_normalize_font_weights_empty_list_defaults() -> None:
    assert ui_analyzer._normalize_font_weights([]) == [400.0]


def test_tokens_summary_keeps_color_font_background_keys() -> None:
    tokens = {
        "--foreground": "#000",
        "--_font-body": "Inter",
        "--unrelated-token": "x",
        "--border-radius-lg": "8px",
    }
    s = ui_analyzer._tokens_summary(tokens)
    assert "--foreground" in s
    assert "--_font-body" in s
    assert "--border-radius-lg" in s
    assert "--unrelated-token" not in s


def test_tokens_summary_case_insensitive_substrings() -> None:
    tokens = {"--MyBackground": "#fff"}
    assert "--MyBackground" in ui_analyzer._tokens_summary(tokens)


def test_build_user_message_includes_json_block() -> None:
    msg = ui_analyzer._build_user_message({"--x": "y"})
    assert "CSS tokens" in msg
    assert '"--x": "y"' in msg


def test_normalize_tone_maps_dark_to_technical() -> None:
    assert ui_analyzer._normalize_tone("dark") == "technical"


def test_normalize_tone_passes_through_allowed() -> None:
    for t in ("technical", "playful", "corporate", "minimal", "bold"):
        assert ui_analyzer._normalize_tone(t) == t


def test_normalize_tone_unknown_defaults_minimal() -> None:
    assert ui_analyzer._normalize_tone("alien") == "minimal"


def test_normalize_design_category_invalid_uses_tokens_warm() -> None:
    pkg = _pkg(
        css_tokens={"--yellow": "#ffdc42", "--white": "#ffffff"},
    )
    assert ui_analyzer._normalize_design_category("fancy", pkg) == "consumer-friendly"


def test_normalize_design_category_invalid_light_bg_minimal_saas() -> None:
    pkg = _pkg(css_tokens={"--background": "#ffffff"})
    assert ui_analyzer._normalize_design_category("nope", pkg) == "minimal-saas"


def test_normalize_design_category_valid_preserved() -> None:
    pkg = _pkg()
    assert ui_analyzer._normalize_design_category("minimal-saas", pkg) == "minimal-saas"


def test_first_color_prefers_known_keys() -> None:
    tokens = {"--color-brand-bg": "#abc", "--foreground": "#000"}
    assert ui_analyzer._first_color(tokens, "#def") == "#abc"


def test_first_color_scans_values_when_missing_known() -> None:
    tokens = {"--z": "rgb(1,2,3)"}
    assert ui_analyzer._first_color(tokens, "#def") == "rgb(1,2,3)"


def test_first_color_default() -> None:
    assert ui_analyzer._first_color({}, "#def") == "#def"


def test_normalize_font_family_string_first_face_only() -> None:
    assert ui_analyzer._normalize_font_family('Inter, system-ui, "Helvetica"') == "Inter"


def test_normalize_font_family_list() -> None:
    assert ui_analyzer._normalize_font_family(["DM Sans", "Arial"]) == "DM Sans"


def test_normalize_font_family_none() -> None:
    assert ui_analyzer._normalize_font_family(None) is None


def test_build_writing_instruction_min_words_consumer() -> None:
    pkg = _pkg(css_tokens={"--background": "#fff", "--font-family": "Inter, sans"})
    out = ui_analyzer._build_writing_instruction(pkg, "consumer-friendly")
    assert len(out.split()) >= 15
    assert "Warm" in out or "encouraging" in out


def test_build_writing_instruction_developer_dark_bg() -> None:
    pkg = _pkg(css_tokens={"--background": "#0a0a0a", "--font-family": "Mono, monospace"})
    out = ui_analyzer._build_writing_instruction(pkg, "developer-tool")
    assert "Dark background" in out


def test_normalize_brand_dict_output_has_only_expected_keys() -> None:
    raw = {
        "design_category": "nope",
        "primary_color": None,
        "extra_field": "drop me",
        "font_weights": [400, "510"],
        "tone": "bold",
        "writing_instruction": "x",
        "confidence": "0.5",
        "secondary_color": "null",
        "background_color": None,
        "font_family": "Inter",
        "border_radius": None,
        "spacing_unit": None,
    }
    pkg = _pkg()
    out = ui_analyzer._normalize_brand_dict(raw, pkg)
    assert set(out.keys()) == {
        "design_category",
        "primary_color",
        "secondary_color",
        "background_color",
        "font_family",
        "font_weights",
        "border_radius",
        "spacing_unit",
        "tone",
        "writing_instruction",
        "confidence",
    }
    assert "extra_field" not in out
    assert all(isinstance(w, float) for w in out["font_weights"])
    assert len(out["writing_instruction"].split()) >= 15


def test_confidence_clamped() -> None:
    raw = {
        "design_category": "developer-tool",
        "primary_color": "#000",
        "secondary_color": None,
        "background_color": None,
        "font_family": "Inter",
        "font_weights": [400],
        "border_radius": "4px",
        "spacing_unit": "4px",
        "tone": "technical",
        "writing_instruction": "word " * 20,
        "confidence": 99,
    }
    out = ui_analyzer._normalize_brand_dict(raw, _pkg())
    assert out["confidence"] == 1.0


def test_mock_run_preserves_run_id() -> None:
    settings.MOCK_MODE = True
    profile = ui_analyzer.run(_pkg(run_id="rid-zz"))
    assert profile.run_id == "rid-zz"


def test_real_mode_text_only_uses_chat_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False
    called: dict[str, bool] = {"chat": False}

    def _chat(*_a, **_k):
        called["chat"] = True
        return json.dumps(
            {
                "design_category": "developer-tool",
                "primary_color": "#5e6ad2",
                "secondary_color": None,
                "background_color": "#fff",
                "font_family": "Inter",
                "font_weights": [400, 510],
                "border_radius": "6px",
                "spacing_unit": "8px",
                "tone": "technical",
                "writing_instruction": "word " * 20,
                "confidence": 0.9,
            }
        )

    monkeypatch.setattr(ui_analyzer, "chat_completion", _chat)
    profile = ui_analyzer.run(_pkg(run_id="text-only", user_image=None))
    assert called["chat"]
    assert profile.run_id == "text-only"


def test_real_mode_with_image_still_uses_chat_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False

    def _chat(*_a, **_k):
        return json.dumps(
            {
                "design_category": "data-dense",
                "primary_color": "#00f",
                "secondary_color": None,
                "background_color": None,
                "font_family": "Roboto Mono",
                "font_weights": [400],
                "border_radius": "2px",
                "spacing_unit": "4px",
                "tone": "technical",
                "writing_instruction": "word " * 20,
                "confidence": 0.7,
            }
        )

    monkeypatch.setattr(ui_analyzer, "chat_completion", _chat)
    profile = ui_analyzer.run(_pkg(run_id="img", user_image=b"\x89PNG\r\n"))
    assert profile.design_category == "data-dense"
    assert profile.run_id == "img"


def test_secondary_color_none_string_sanitized() -> None:
    raw = {
        "design_category": "developer-tool",
        "primary_color": "#000",
        "secondary_color": "None",
        "background_color": "none",
        "font_family": "Inter",
        "font_weights": [400],
        "border_radius": "1px",
        "spacing_unit": "1px",
        "tone": "minimal",
        "writing_instruction": "word " * 20,
        "confidence": 0.5,
    }
    out = ui_analyzer._normalize_brand_dict(raw, _pkg(css_tokens={"--color-accent": "#f00"}))
    assert out["secondary_color"] == "#f00"


def test_css_tokens_attached_on_brand_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.MOCK_MODE = False
    tokens = {"--foreground": "#123"}

    def _chat(*_a, **_k):
        return json.dumps(
            {
                "design_category": "consumer-friendly",
                "primary_color": "#123",
                "secondary_color": None,
                "background_color": None,
                "font_family": "Inter",
                "font_weights": [400],
                "border_radius": "12px",
                "spacing_unit": "8px",
                "tone": "playful",
                "writing_instruction": "word " * 20,
                "confidence": 0.6,
            }
        )

    monkeypatch.setattr(ui_analyzer, "chat_completion", _chat)
    pkg = _pkg(css_tokens=tokens)
    profile = ui_analyzer.run(pkg)
    assert profile.css_tokens == tokens


def test_normalize_brand_dict_invalid_confidence_becomes_default() -> None:
    raw = {
        "design_category": "bold-enterprise",
        "primary_color": "#000",
        "secondary_color": None,
        "background_color": None,
        "font_family": "Inter",
        "font_weights": [400],
        "border_radius": "1px",
        "spacing_unit": "1px",
        "tone": "bold",
        "writing_instruction": "word " * 20,
        "confidence": "bad",
    }
    out = ui_analyzer._normalize_brand_dict(raw, _pkg())
    assert out["confidence"] == 0.7


def test_border_radius_fallback_from_package_tokens() -> None:
    raw = {
        "design_category": "developer-tool",
        "primary_color": "#000",
        "secondary_color": None,
        "background_color": None,
        "font_family": "Inter",
        "font_weights": [400],
        "border_radius": None,
        "spacing_unit": None,
        "tone": "technical",
        "writing_instruction": "word " * 20,
        "confidence": 0.5,
    }
    pkg = _pkg(css_tokens={"--border-radius-md": "99px", "--spacing-unit": "7px"})
    out = ui_analyzer._normalize_brand_dict(raw, pkg)
    assert out["border_radius"] == "99px"
    assert out["spacing_unit"] == "7px"


def test_module_imports_chat_from_llm_client_only() -> None:
    import agents.ui_analyzer as mod

    assert mod.chat_completion.__module__.startswith("llm")
