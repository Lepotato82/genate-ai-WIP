"""Tests for agents/image_gen.py — Bannerbear carousel image generation."""

from __future__ import annotations

import pytest

from agents.image_gen import (
    _build_modifications,
    _contrast_ratio,
    _is_dark,
    _luminance,
    _pick_accent_color,
    _split_into_slides,
    _truncate,
)
from schemas.brand_identity import BrandIdentity
from schemas.formatted_content import FormattedContent, LinkedInContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_linkedin_formatted(
    hook: str = "Your daily friction starts here.",
    body: str = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
    cta: str = "Try it free today.",
) -> FormattedContent:
    hashtags = ["#saas", "#productivity", "#b2b"]
    full_post = f"{hook}\n\n{body}\n\n{cta}\n\n" + " ".join(hashtags)
    return FormattedContent(
        run_id="r",
        created_at="2026-01-01T00:00:00Z",
        platform="linkedin",
        linkedin_content=LinkedInContent(
            hook=hook,
            body=body,
            cta=cta,
            hashtags=hashtags,
            full_post=full_post,
        ),
    )


def _make_identity(**overrides) -> BrandIdentity:
    defaults = dict(
        product_name="Linear",
        product_url="https://linear.app",
        run_id="r",
        primary_color="#5e6ad2",
        background_color="#ffffff",
        design_category="developer-tool",
        tone="technical",
        writing_instruction="Be direct and specific " * 5,
    )
    defaults.update(overrides)
    return BrandIdentity(**defaults)


# ---------------------------------------------------------------------------
# MOCK_MODE / disabled
# ---------------------------------------------------------------------------

def test_mock_mode_returns_3_urls(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", True)

    from agents import image_gen
    result = image_gen.run(_make_linkedin_formatted(), _make_identity())

    assert len(result["image_urls"]) == 3
    assert result["slide_count"] == 3
    assert result["template_uid"] == "mock"
    assert result["generation_enabled"] is False
    assert result["error"] is None
    assert result["background_hero_url"] == "https://mock.example.com/hero_bg.png"
    assert result["hero_generation_enabled"] is True
    assert result["hero_error"] is None


def test_disabled_returns_empty(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", False)

    from agents import image_gen
    result = image_gen.run(_make_linkedin_formatted(), _make_identity())

    assert result["image_urls"] == []
    assert result["generation_enabled"] is False
    assert result.get("background_hero_url") is None
    assert result.get("hero_generation_enabled") is False


def test_disabled_generation_enabled_false(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", False)

    from agents import image_gen
    result = image_gen.run(_make_linkedin_formatted(), _make_identity())

    assert result["generation_enabled"] is False


def test_missing_api_key_returns_error(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "BANNERBEAR_API_KEY", "")

    from agents import image_gen
    result = image_gen.run(_make_linkedin_formatted(), _make_identity())

    assert result["error"] is not None
    assert "BANNERBEAR_API_KEY" in result["error"]
    assert result["generation_enabled"] is False


# ---------------------------------------------------------------------------
# _split_into_slides
# ---------------------------------------------------------------------------

def test_split_slide1_headline_is_hook():
    formatted = _make_linkedin_formatted(hook="This is the hook.")
    slides = _split_into_slides(formatted)

    assert slides[0]["headline"] == "This is the hook."


def test_split_slide_label_format():
    # body has 3 paragraphs:
    # slide 1 = hook + para1 → slide 2 = para2 + para3 → 2 slides total
    body = "Para 1.\n\nPara 2.\n\nPara 3."
    formatted = _make_linkedin_formatted(body=body)
    slides = _split_into_slides(formatted)

    assert slides[0]["slide_label"] == "01 / 02"


def test_split_max_8_slides():
    # Build a body with many paragraphs to exceed 8
    paras = "\n\n".join(f"Paragraph {i}" for i in range(20))
    formatted = _make_linkedin_formatted(body=paras)
    slides = _split_into_slides(formatted)

    assert len(slides) <= 8


def test_split_empty_body_produces_single_slide():
    formatted = _make_linkedin_formatted(body="")
    slides = _split_into_slides(formatted)

    assert len(slides) == 1
    assert slides[0]["slide_label"] == "01 / 01"


def test_split_labels_correct_count():
    body = "Para 1.\n\nPara 2."
    formatted = _make_linkedin_formatted(body=body)
    slides = _split_into_slides(formatted)

    total = len(slides)
    for i, slide in enumerate(slides):
        expected_label = f"{i + 1:02d} / {total:02d}"
        assert slide["slide_label"] == expected_label


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------

def test_truncate_under_limit_unchanged():
    text = "Short text."
    assert _truncate(text, 100) == text


def test_truncate_over_limit_word_boundary():
    text = "word " * 50  # 250 chars
    result = _truncate(text, 30)
    assert len(result) <= 31  # 30 + ellipsis char
    assert not result[:-1].endswith(" ")  # no trailing space before ellipsis


def test_truncate_ends_with_ellipsis():
    text = "a " * 100
    result = _truncate(text, 50)
    assert result.endswith("\u2026")


def test_truncate_never_cuts_mid_word():
    text = "Hello world this is a longer sentence than allowed."
    result = _truncate(text, 20)
    # The truncated portion (excluding ellipsis) should not end mid-word
    body = result[:-1]  # strip ellipsis
    assert not body.endswith(" ")
    # Verify no partial word — all chars before ellipsis are complete words
    for word in body.split():
        assert word in text


# ---------------------------------------------------------------------------
# _is_dark
# ---------------------------------------------------------------------------

def test_is_dark_black():
    assert _is_dark("#000000") is True


def test_is_dark_near_black():
    assert _is_dark("#08090a") is True


def test_is_dark_white():
    assert _is_dark("#ffffff") is False


def test_is_dark_light_grey():
    assert _is_dark("#f0f0f0") is False


def test_is_dark_mid_blue():
    # #5e6ad2 luminance ≈ 0.40 — dark
    assert _is_dark("#5e6ad2") is True


# ---------------------------------------------------------------------------
# _luminance
# ---------------------------------------------------------------------------

def test_luminance_black():
    assert _luminance("#000000") == pytest.approx(0.0)


def test_luminance_white():
    assert _luminance("#ffffff") == pytest.approx(1.0)


def test_luminance_mid_grey():
    # #808080 → relative luminance ≈ 0.216
    assert _luminance("#808080") == pytest.approx(0.216, abs=0.01)


# ---------------------------------------------------------------------------
# _contrast_ratio
# ---------------------------------------------------------------------------

def test_contrast_ratio_max():
    assert _contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_contrast_ratio_min():
    assert _contrast_ratio("#000000", "#000000") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _pick_accent_color
# ---------------------------------------------------------------------------

class _MockIdentity:
    def __init__(self, bg, primary=None, secondary=None, accent=None):
        self.background_color = bg
        self.primary_color = primary
        self.secondary_color = secondary
        self.accent_color = accent


def test_pick_accent_returns_primary_when_contrast_ok():
    # #5e6ad2 on #ffffff → clearly visible
    identity = _MockIdentity(bg="#ffffff", primary="#5e6ad2")
    assert _pick_accent_color(identity) == "#5e6ad2"


def test_pick_accent_skips_primary_when_same_as_bg():
    # Linear run 2 scenario: primary == background
    identity = _MockIdentity(
        bg="#08090a",
        primary="#08090a",   # same as bg → contrast 1.0 → skipped
        secondary="#5e6ad2", # Linear purple → visible → picked
    )
    result = _pick_accent_color(identity)
    assert result == "#5e6ad2"
    assert _contrast_ratio(result, "#08090a") > 1.5


def test_pick_accent_fallback_white_on_dark():
    # All candidates same as dark background
    identity = _MockIdentity(bg="#000000", primary="#000000")
    assert _pick_accent_color(identity) == "#ffffff"


def test_pick_accent_fallback_black_on_light():
    # All candidates same as light background
    identity = _MockIdentity(bg="#ffffff", primary="#ffffff")
    assert _pick_accent_color(identity) == "#000000"


# ---------------------------------------------------------------------------
# _build_modifications
# ---------------------------------------------------------------------------

def _slide() -> dict[str, str]:
    return {
        "headline": "Main headline text.",
        "body_text": "Supporting body copy here.",
        "slide_label": "01 / 03",
    }


def test_build_mods_text_white_on_dark_background():
    identity = _make_identity(background_color="#08090a")  # Linear dark
    mods = _build_modifications(_slide(), identity)
    headline = next(m for m in mods if m["name"] == "headline")
    body = next(m for m in mods if m["name"] == "body_text")
    assert headline["color"] == "#ffffff"
    assert body["color"] == "#cccccc"


def test_build_mods_text_dark_on_light_background():
    identity = _make_identity(background_color="#ffffff")
    mods = _build_modifications(_slide(), identity)
    headline = next(m for m in mods if m["name"] == "headline")
    body = next(m for m in mods if m["name"] == "body_text")
    assert headline["color"] == "#111111"
    assert body["color"] == "#444444"


def test_build_mods_includes_background_color():
    identity = _make_identity(background_color="#f0f0f0")
    mods = _build_modifications(_slide(), identity)
    bg = next(m for m in mods if m["name"] == "background_color")
    assert bg["color"] == "#f0f0f0"


def test_build_mods_accent_bar_uses_pick_accent_color():
    # primary_color has good contrast against white background → picked
    identity = _make_identity(primary_color="#5e6ad2", background_color="#ffffff")
    mods = _build_modifications(_slide(), identity)
    accent = next(m for m in mods if m["name"] == "accent_bar")
    assert accent["color"] == "#5e6ad2"


def test_build_mods_accent_bar_falls_back_when_primary_matches_bg():
    # primary == background → _pick_accent_color should fall back
    identity = _make_identity(primary_color="#08090a", background_color="#08090a")
    mods = _build_modifications(_slide(), identity)
    accent = next(m for m in mods if m["name"] == "accent_bar")
    # Fallback should be #ffffff (dark background)
    assert accent["color"] == "#ffffff"


def test_build_mods_includes_logo_when_compositing_enabled():
    identity = _make_identity(
        logo_bytes=b"\x89PNG" + b"\x00" * 1200,
        logo_url="https://linear.app/logo.png",
        logo_confidence="high",
    )
    mods = _build_modifications(_slide(), identity)
    logo_mods = [m for m in mods if m["name"] == "logo"]
    assert len(logo_mods) == 1
    assert logo_mods[0]["image_url"] == "https://linear.app/logo.png"


def test_build_mods_omits_logo_when_url_is_none():
    identity = _make_identity()  # no logo fields
    mods = _build_modifications(_slide(), identity)
    logo_mods = [m for m in mods if m["name"] == "logo"]
    assert len(logo_mods) == 0


def test_build_mods_headline_truncated():
    long_headline = "H " * 100  # 200 chars
    slide = {"headline": long_headline, "body_text": "", "slide_label": "01 / 01"}
    identity = _make_identity()
    mods = _build_modifications(slide, identity)
    h = next(m for m in mods if m["name"] == "headline")
    # text field (excluding trailing ellipsis) must be <= 120
    assert len(h["text"]) <= 121  # 120 + ellipsis


def test_build_mods_body_text_truncated():
    long_body = "B " * 200  # 400 chars
    slide = {"headline": "Hook", "body_text": long_body, "slide_label": "01 / 01"}
    identity = _make_identity()
    mods = _build_modifications(slide, identity)
    b = next(m for m in mods if m["name"] == "body_text")
    assert len(b["text"]) <= 281  # 280 + ellipsis


# ---------------------------------------------------------------------------
# Pipeline integration — images key present in output
# ---------------------------------------------------------------------------

def test_images_key_in_pipeline_output(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", True)

    from pipeline import run
    result = run("https://linear.app", platform="linkedin")

    assert "visual" in result
    assert "image_prompt" in result["visual"]
    assert "images" in result
    imgs = result["images"]
    assert "image_urls" in imgs
    assert "slide_count" in imgs
    assert "generation_enabled" in imgs
    assert "error" in imgs
    assert "background_hero_url" in imgs
    assert "hero_generation_enabled" in imgs
    assert "hero_error" in imgs


def test_hero_image_invokes_provider(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "HERO_IMAGE_ENABLED", True)
    monkeypatch.setattr(settings, "HERO_IMAGE_PROVIDER", "pollinations")

    def fake_fetch(prompt: str):
        assert "abstract" in prompt
        return ("https://hero.test/out.png", None)

    monkeypatch.setattr("agents.image_gen.fetch_hero_image", fake_fetch)
    from agents import image_gen
    result = image_gen.run(
        _make_linkedin_formatted(),
        _make_identity(),
        visual={"image_prompt": "abstract gradient sky, no text"},
    )
    assert result["background_hero_url"] == "https://hero.test/out.png"
    assert result["hero_generation_enabled"] is True
    assert result["hero_error"] is None


def test_hero_missing_prompt_no_fetch(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "HERO_IMAGE_ENABLED", True)
    monkeypatch.setattr(settings, "HERO_IMAGE_PROVIDER", "pollinations")

    def boom(_):
        raise AssertionError("fetch_hero_image should not run without prompt")

    monkeypatch.setattr("agents.image_gen.fetch_hero_image", boom)
    from agents import image_gen
    result = image_gen.run(_make_linkedin_formatted(), _make_identity(), visual={})
    assert result["background_hero_url"] is None
    assert result["hero_generation_enabled"] is False
    assert result["hero_error"] and "image_prompt" in result["hero_error"]
