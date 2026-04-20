"""
tests/test_compositor.py
Unit tests for agents/compositor.py — Pillow-based brand image compositor.

All tests are offline and require no API keys.
"""

from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from agents import compositor
from agents.compositor import (
    VISUAL_CONTENT_TYPES,
    _compose_slide,
    _load_font,
    _LAYOUT_FNS,
    _select_layout,
    _stamp_logo,
)
from schemas.brand_identity import BrandIdentity
from schemas.content_brief import ContentBrief, PostingStrategy
from schemas.formatted_content import (
    FormattedContent,
    InstagramContent,
    InstagramStoryContent,
    LinkedInContent,
    TwitterContent,
)
from agents._utils import utc_now_iso


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_run_id() -> str:
    return str(uuid.uuid4())


def _make_identity(
    design_category: str = "minimal-saas",
    logo_confidence: str | None = None,
    logo_bytes: bytes | None = None,
) -> BrandIdentity:
    # BrandIdentity validator requires logo_bytes, logo_url, and logo_confidence
    # to all be None or all be non-None simultaneously.
    logo_url = "https://example.com/logo.png" if logo_confidence is not None else None
    logo_bytes_val = logo_bytes if logo_confidence is not None else None
    return BrandIdentity(
        product_name="Genate",
        product_url="https://genate.ai",
        run_id=_make_run_id(),
        primary_color="#5e6ad2",
        background_color="#ffffff",
        secondary_color="#333333",
        accent_color="#ffde21",
        design_category=design_category,
        tone="technical",
        writing_instruction="Lead with outcome; avoid jargon; reference the brand's minimal visual language.",
        logo_confidence=logo_confidence,
        logo_bytes=logo_bytes_val,
        logo_url=logo_url,
    )


def _make_brief(
    content_type: str = "single_image",
    platform: str = "linkedin",
    narrative_arc: str = "pain-agitate-solve-cta",
    content_pillar: str = "pain_and_problem",
    run_id: str | None = None,
    slide_count_target: int | None = None,
    thread_length_target: int | None = None,
) -> ContentBrief:
    rid = run_id or _make_run_id()
    return ContentBrief(
        run_id=rid,
        org_id=None,
        created_at=utc_now_iso(),
        platform=platform,
        content_type=content_type,
        narrative_arc=narrative_arc,
        content_pillar=content_pillar,
        funnel_stage="tofu",
        content_depth="concise",
        posting_strategy=PostingStrategy(
            recommended_frequency="2-3x per week",
            best_days=["Tuesday", "Thursday"],
            best_time_window="9-11 AM IST",
        ),
        platform_rules_summary=["hook first", "hashtags at end"],
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="Razorpay LinkedIn post",
        reasoning="Pain-first approach matches the target ICP for this platform and funnel stage.",
        slide_count_target=slide_count_target,
        thread_length_target=thread_length_target,
    )


def _make_formatted_linkedin(
    hook: str = "Your ops team is drowning in manual reconciliation.",
    body: str = "Every week your team spends 12+ hours on spreadsheets.\n\nThis kills velocity.\n\nGenate automates the entire reconciliation flow.",
) -> FormattedContent:
    hashtags = ["#fintech", "#saas", "#automation"]
    full_post = f"{hook}\n\n{body}\n\n{' '.join(hashtags)}"
    return FormattedContent(
        run_id=_make_run_id(),
        org_id=None,
        created_at=utc_now_iso(),
        platform="linkedin",
        linkedin_content=LinkedInContent(
            hook=hook,
            body=body,
            hashtags=hashtags,
            full_post=full_post,
        ),
        retry_count=0,
    )


def _make_formatted_instagram_story() -> FormattedContent:
    return FormattedContent(
        run_id=_make_run_id(),
        org_id=None,
        created_at=utc_now_iso(),
        platform="instagram",
        instagram_story_content=InstagramStoryContent(
            hook="Stop losing clients to slow onboarding.",
            cta_text="Link in bio",
        ),
        retry_count=0,
    )


def _make_logo_png(size: tuple[int, int] = (60, 30), color: tuple = (255, 0, 0, 255)) -> bytes:
    """Create a minimal RGBA PNG in memory."""
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _decode_b64_png(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


# ---------------------------------------------------------------------------
# Test 1 — Mock mode renders real Pillow images for frontend preview
# ---------------------------------------------------------------------------

def test_mock_mode_returns_rendered_images(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", True)
    identity = _make_identity()
    brief = _make_brief(content_type="single_image")
    formatted = _make_formatted_linkedin()

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is True
    assert result["slide_count"] >= 1
    assert isinstance(result["composed_images"], list)
    # Should have a real base64 PNG, not empty string
    slide = result["composed_images"][0]
    assert slide["png_b64"] != ""
    img = _decode_b64_png(slide["png_b64"])
    assert img.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Test 2 — Non-visual content type skips compositor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ct,platform,extra", [
    ("text_post", "linkedin", {}),
    ("poll", "linkedin", {}),
    ("question_post", "linkedin", {}),
    ("thread", "twitter", {"thread_length_target": 4}),
    ("single_tweet", "twitter", {}),
])
def test_non_visual_content_type_skipped(ct, platform, extra, monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)
    identity = _make_identity()
    brief = _make_brief(content_type=ct, platform=platform, **extra)
    formatted = _make_formatted_linkedin()

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is False
    assert result["composed_images"] == []
    assert result["error"] is None


# ---------------------------------------------------------------------------
# Test 3 — COMPOSITOR_ENABLED=False disables compositor
# ---------------------------------------------------------------------------

def test_compositor_flag_disabled(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", False)
    identity = _make_identity()
    brief = _make_brief(content_type="single_image")
    formatted = _make_formatted_linkedin()

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is False
    assert result["composed_images"] == []


# ---------------------------------------------------------------------------
# Test 4 — Layout selection is deterministic
# ---------------------------------------------------------------------------

def test_layout_selection_deterministic():
    identity = _make_identity(design_category="minimal-saas")
    brief = _make_brief(
        run_id="aaaabbbb-cccc-dddd-eeee-ffffgggghhhh",
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="pain_and_problem",
    )
    layout1 = _select_layout(identity, brief)
    layout2 = _select_layout(identity, brief)
    assert layout1 == layout2
    assert layout1 in _LAYOUT_FNS


# ---------------------------------------------------------------------------
# Test 5 — Different run_ids yield varied layouts
# ---------------------------------------------------------------------------

def test_layout_selection_varied_across_runs():
    identity = _make_identity(design_category="minimal-saas")
    layouts_seen: set[str] = set()
    for _ in range(12):
        brief = _make_brief(run_id=str(uuid.uuid4()))
        layouts_seen.add(_select_layout(identity, brief))
    # Family has 3 layouts; 12 random runs should hit at least 2 distinct ones
    assert len(layouts_seen) >= 2


# ---------------------------------------------------------------------------
# Test 6 — Single image produces valid PNG with correct dimensions (LinkedIn)
# ---------------------------------------------------------------------------

def test_single_image_valid_png_linkedin(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)
    identity = _make_identity()
    brief = _make_brief(content_type="single_image", platform="linkedin")
    formatted = _make_formatted_linkedin()

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is True
    assert result["slide_count"] == 1
    assert len(result["composed_images"]) == 1

    img_dict = result["composed_images"][0]
    assert img_dict["width"] == 1200
    assert img_dict["height"] == 627

    img = _decode_b64_png(img_dict["png_b64"])
    assert img.mode == "RGB"
    assert img.size == (1200, 627)


# ---------------------------------------------------------------------------
# Test 7 — All 7 layout archetypes render without exception
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", list(_LAYOUT_FNS.keys()))
def test_all_layout_archetypes_render(layout, monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)
    identity = _make_identity()

    png_bytes = _compose_slide(
        headline="Stop losing clients to slow onboarding.",
        subtext="Automate reconciliation and close deals 3× faster.",
        slide_label="01 / 03",
        identity=identity,
        layout=layout,
        canvas_size=(1080, 1080),
    )

    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 1000  # non-trivial PNG
    img = Image.open(io.BytesIO(png_bytes))
    assert img.mode == "RGB"
    assert img.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Test 8 — Logo is composited when logo_compositing_enabled=True (high confidence)
# ---------------------------------------------------------------------------

def test_logo_composited_when_high_confidence(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    logo_bytes = _make_logo_png(size=(80, 40), color=(255, 0, 0, 255))
    identity_no_logo = _make_identity(logo_confidence=None, logo_bytes=None)
    identity_with_logo = _make_identity(logo_confidence="high", logo_bytes=logo_bytes)
    brief = _make_brief(content_type="single_image", platform="linkedin")
    formatted = _make_formatted_linkedin()

    result_no = compositor.run(formatted, identity_no_logo, brief)
    result_with = compositor.run(formatted, identity_with_logo, brief)

    img_no = _decode_b64_png(result_no["composed_images"][0]["png_b64"])
    img_with = _decode_b64_png(result_with["composed_images"][0]["png_b64"])

    # Compare bottom-right region where logo is stamped — should differ
    w, h = img_no.size
    region = (w - 200, h - 120, w, h)
    pixels_no = list(img_no.crop(region).getdata())
    pixels_with = list(img_with.crop(region).getdata())
    assert pixels_no != pixels_with, "Logo stamp should change bottom-right pixels"


# ---------------------------------------------------------------------------
# Test 9 — Logo omitted when logo_compositing_enabled=False (low/None confidence)
# ---------------------------------------------------------------------------

def test_logo_omitted_when_medium_confidence(monkeypatch):
    """og:image (medium) is never stamped — may be a wide marketing banner."""
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    stamped: list[bool] = []

    def _spy_stamp(canvas, logo_bytes, **kwargs):
        stamped.append(True)

    identity = _make_identity(
        logo_confidence="medium",
        logo_bytes=_make_logo_png(),
    )
    brief = _make_brief(content_type="single_image")
    formatted = _make_formatted_linkedin()

    with patch("agents.compositor._stamp_logo", side_effect=_spy_stamp):
        compositor.run(formatted, identity, brief)

    assert len(stamped) == 0, "_stamp_logo should not be called for medium confidence"


# ---------------------------------------------------------------------------
# Test 10 — Carousel generates multiple slides
# ---------------------------------------------------------------------------

def test_carousel_generates_multiple_slides(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    identity = _make_identity()
    brief = _make_brief(
        content_type="carousel",
        platform="linkedin",
        slide_count_target=6,
    )
    # Body with 3 clear paragraphs → should produce ≥2 slides
    formatted = _make_formatted_linkedin(
        body="Slide 2 content: manual work is killing your ops team.\n\n"
             "Slide 3 content: our clients reduced reconciliation time by 80%.\n\n"
             "Slide 4 content: book a demo today and see it live.",
    )

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is True
    assert result["slide_count"] >= 2
    assert len(result["composed_images"]) >= 2
    for slide_dict in result["composed_images"]:
        assert slide_dict["png_b64"] != ""
        img = _decode_b64_png(slide_dict["png_b64"])
        assert img.mode == "RGB"
        assert img.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Test 11 — Instagram story uses portrait dimensions (1080×1920)
# ---------------------------------------------------------------------------

def test_story_portrait_dimensions(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    identity = _make_identity()
    brief = _make_brief(content_type="story", platform="instagram")
    formatted = _make_formatted_instagram_story()

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is True
    assert result["slide_count"] == 1
    img_dict = result["composed_images"][0]
    assert img_dict["width"] == 1080
    assert img_dict["height"] == 1920
    img = _decode_b64_png(img_dict["png_b64"])
    assert img.size == (1080, 1920)
    assert img.height > img.width  # portrait


# ---------------------------------------------------------------------------
# Test 12 — Compositor failure is silent (no exception escapes run())
# ---------------------------------------------------------------------------

def test_compositor_failure_silent(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    def _blow_up(*args, **kwargs):
        raise RuntimeError("deliberate test failure — compositor exploded")

    identity = _make_identity()
    brief = _make_brief(content_type="single_image")
    formatted = _make_formatted_linkedin()

    with patch("agents.compositor._compose_slide", side_effect=_blow_up):
        result = compositor.run(formatted, identity, brief)

    # Must not raise; must return a clean disabled dict
    assert result["compositor_enabled"] is False
    assert result["error"] is not None
    assert "deliberate test failure" in result["error"]
    assert result["composed_images"] == []


# ---------------------------------------------------------------------------
# Test 13 — Missing font TTF falls back to PIL default (no crash)
# ---------------------------------------------------------------------------

def test_missing_ttf_falls_back_to_pil_default(monkeypatch, tmp_path):
    # Point font dir at an empty temp dir
    monkeypatch.setattr("agents.compositor._ASSETS_DIR", tmp_path)

    font = _load_font("heading_bold", 48)
    assert font is not None
    # PIL default or fallback — must not raise


# ---------------------------------------------------------------------------
# Test 14 — Instagram single_image uses correct 1080×1080 canvas
# ---------------------------------------------------------------------------

def test_instagram_single_image_dimensions(monkeypatch):
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)

    identity = _make_identity(design_category="consumer-friendly")
    brief = _make_brief(content_type="single_image", platform="instagram")

    hashtags = ["#saas"] * 20  # Instagram requires 20–30 hashtags
    caption_body = "This is a test caption body."
    preview = "Stop losing clients to slow onboarding."
    full_caption = f"{preview}\n\n{caption_body}\n\n\n\n\n{' '.join(hashtags)}"
    formatted = FormattedContent(
        run_id=_make_run_id(),
        org_id=None,
        created_at=utc_now_iso(),
        platform="instagram",
        instagram_content=InstagramContent(
            preview_text=preview,
            body=caption_body,
            hashtags=hashtags,
            full_caption=full_caption,
        ),
        retry_count=0,
    )

    result = compositor.run(formatted, identity, brief)

    assert result["compositor_enabled"] is True
    assert result["slide_count"] == 1
    img = _decode_b64_png(result["composed_images"][0]["png_b64"])
    assert img.size == (1080, 1080)


# ---------------------------------------------------------------------------
# Test — editorial_with_assets layout renders (no bundled decorations needed)
# ---------------------------------------------------------------------------

def test_editorial_with_assets_renders_without_decoration(monkeypatch):
    """Layout must render cleanly even when no decoration bytes are supplied."""
    monkeypatch.setattr("config.settings.MOCK_MODE", False)
    monkeypatch.setattr("config.settings.COMPOSITOR_ENABLED", True)
    identity = _make_identity(design_category="consumer-friendly")

    png_bytes = _compose_slide(
        headline="Your health data deserves more than a spreadsheet.",
        subtext="We turn wearable streams into insights you can act on every morning.",
        slide_label="01 / 03",
        identity=identity,
        layout="editorial_with_assets",
        canvas_size=(1080, 1080),
        hero_bytes=None,
        decoration_bytes=None,
    )

    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (1080, 1080)
    assert img.mode == "RGB"


def test_compose_slide_accepts_decoration_bytes(monkeypatch):
    """_compose_slide must accept decoration_bytes and render without error."""
    monkeypatch.setattr("config.settings.COMPOSITOR_DECORATIONS_ENABLED", True)
    identity = _make_identity(design_category="consumer-friendly")

    # Minimal valid PNG with alpha — simulates a bundled decoration
    deco = Image.new("RGBA", (200, 200), (255, 200, 0, 255))
    buf = io.BytesIO()
    deco.save(buf, format="PNG")
    decoration_bytes = buf.getvalue()

    png_bytes = _compose_slide(
        headline="Lead with the outcome.",
        subtext="Everything else is decoration.",
        slide_label=None,
        identity=identity,
        layout="editorial_with_assets",
        canvas_size=(1080, 1080),
        decoration_bytes=decoration_bytes,
    )

    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (1080, 1080)
