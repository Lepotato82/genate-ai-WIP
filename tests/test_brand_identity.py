"""Tests for BrandIdentity schema and build_brand_identity()."""

from __future__ import annotations

import pytest

from config import settings
from schemas.brand_identity import BrandIdentity
from schemas.brand_profile import BrandProfile
from schemas.input_package import InputPackage
from schemas.product_knowledge import ProductKnowledge


# ---------------------------------------------------------------------------
# Fixtures — minimal valid objects for testing
# ---------------------------------------------------------------------------


def _make_brand(**overrides) -> BrandProfile:
    defaults = {
        "run_id": "r1",
        "created_at": "2026-01-01T00:00:00Z",
        "design_category": "minimal-saas",
        "primary_color": "#5e6ad2",
        "secondary_color": "#7170ff",
        "background_color": "#ffffff",
        "font_family": "Inter",
        "font_weights": [400.0, 510.0, 590.0],
        "border_radius": "6px",
        "spacing_unit": "4px",
        "tone": "technical",
        "writing_instruction": (
            "One idea per sentence. Use simple language and avoid jargon. "
            "Focus on the benefit, not the feature. Lead with the outcome."
        ),
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return BrandProfile(**defaults)


def _make_pkg(**overrides) -> InputPackage:
    defaults = {
        "url": "https://linear.app",
        "run_id": "r1",
        "css_tokens": {"--font-family-mono": "JetBrains Mono, monospace"},
    }
    defaults.update(overrides)
    return InputPackage(**defaults)


def _make_product(**overrides) -> ProductKnowledge:
    defaults = {
        "run_id": "r1",
        "created_at": "2026-01-01T00:00:00Z",
        "product_name": "Linear",
        "product_url": "https://linear.app",
        "description": (
            "Linear is the issue tracking tool built for high-performance engineering teams. "
            "It streamlines software projects, sprints, tasks, and bug tracking. "
            "Used by thousands of engineering teams worldwide for product development."
        ),
        "product_category": "project-management",
        "features": [
            {"name": "Issue Tracking", "description": "Track bugs and tasks across sprints"},
            {"name": "Git Integration", "description": "Connect to GitHub and GitLab repos"},
        ],
        "benefits": ["Ship faster", "Stay aligned"],
        "proof_points": [
            {"text": "Used by over 10,000 engineering teams", "proof_type": "user_count", "source": "scraped_page"},
        ],
    }
    defaults.update(overrides)
    return ProductKnowledge(**defaults)


# ---------------------------------------------------------------------------
# build_brand_identity
# ---------------------------------------------------------------------------


def test_build_brand_identity_basic() -> None:
    from pipeline import build_brand_identity

    pkg = _make_pkg()
    brand = _make_brand()
    product = _make_product()
    bi = build_brand_identity(pkg, brand, product)

    assert bi.product_name == "Linear"
    assert bi.product_url == "https://linear.app"
    assert bi.run_id == "r1"
    assert bi.primary_color == "#5e6ad2"
    assert bi.secondary_color == "#7170ff"
    assert bi.background_color == "#ffffff"
    assert bi.font_family_heading == "Inter"
    assert bi.font_family_body == "Inter"
    assert bi.font_family_mono == "JetBrains Mono"
    assert bi.font_weights == [400.0, 510.0, 590.0]
    assert bi.border_radius == "6px"
    assert bi.design_category == "minimal-saas"
    assert bi.tone == "technical"


def test_build_brand_identity_with_logo() -> None:
    from pipeline import build_brand_identity

    logo_data = b"\x89PNG" + b"\x00" * 1200
    pkg = _make_pkg(
        logo_bytes=logo_data,
        logo_url="https://linear.app/logo.png",
        logo_confidence="high",
    )
    brand = _make_brand()
    product = _make_product()
    bi = build_brand_identity(pkg, brand, product)

    assert bi.logo_bytes == logo_data
    assert bi.logo_url == "https://linear.app/logo.png"
    assert bi.logo_confidence == "high"
    assert bi.logo_compositing_enabled is True


def test_build_brand_identity_no_logo() -> None:
    from pipeline import build_brand_identity

    pkg = _make_pkg()
    brand = _make_brand()
    product = _make_product()
    bi = build_brand_identity(pkg, brand, product)

    assert bi.logo_bytes is None
    assert bi.logo_compositing_enabled is False


# ---------------------------------------------------------------------------
# logo_compositing_enabled
# ---------------------------------------------------------------------------


def test_compositing_enabled_high() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        logo_bytes=b"\x89PNG" + b"\x00" * 100,
        logo_url="https://x.com/logo.png",
        logo_confidence="high",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.logo_compositing_enabled is True


def test_compositing_disabled_medium() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        logo_bytes=b"\x89PNG" + b"\x00" * 100,
        logo_url="https://x.com/logo.png",
        logo_confidence="medium",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.logo_compositing_enabled is False


def test_compositing_disabled_low() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        logo_bytes=b"\x89PNG" + b"\x00" * 100,
        logo_url="https://x.com/logo.png",
        logo_confidence="low",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.logo_compositing_enabled is False


def test_compositing_disabled_none() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.logo_compositing_enabled is False


# ---------------------------------------------------------------------------
# has_logo / has_og_image
# ---------------------------------------------------------------------------


def test_has_logo_true() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        logo_bytes=b"\x89PNG", logo_url="u", logo_confidence="high",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.has_logo is True


def test_has_logo_false() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.has_logo is False


def test_has_og_image_with_url() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        og_image_url="https://x.com/og.png",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.has_og_image is True


# ---------------------------------------------------------------------------
# css_color_vars
# ---------------------------------------------------------------------------


def test_css_color_vars() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        primary_color="#5e6ad2", secondary_color="#7170ff",
        background_color="#ffffff", foreground_color="#1a1a2e",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    v = bi.css_color_vars
    assert v["--color-primary"] == "#5e6ad2"
    assert v["--color-secondary"] == "#7170ff"
    assert v["--color-background"] == "#ffffff"
    assert v["--color-foreground"] == "#1a1a2e"
    assert "--color-accent" not in v  # accent_color is None


# ---------------------------------------------------------------------------
# primary_font / font weights
# ---------------------------------------------------------------------------


def test_primary_font_heading() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        font_family_heading="Inter", font_family_body="System",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.primary_font == "Inter"


def test_primary_font_fallback_to_body() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        font_family_heading=None, font_family_body="System",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.primary_font == "System"


def test_heading_font_weight_max() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        font_weights=[400.0, 510.0, 590.0],
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.heading_font_weight == 590.0


def test_body_font_weight_min() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        font_weights=[400.0, 510.0, 590.0],
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.body_font_weight == 400.0


def test_font_weight_none_when_empty() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    assert bi.heading_font_weight is None
    assert bi.body_font_weight is None


# ---------------------------------------------------------------------------
# Serialisation — exclude binary fields
# ---------------------------------------------------------------------------


def test_model_dump_excludes_binary_fields() -> None:
    bi = BrandIdentity(
        product_name="X", product_url="https://x.com", run_id="r",
        logo_bytes=b"\x89PNG", logo_url="u", logo_confidence="high",
        og_image_bytes=b"\xff\xd8",
        primary_color="#000", background_color="#fff",
        design_category="minimal-saas", tone="technical",
        writing_instruction="x " * 20,
    )
    d = bi.model_dump(exclude={"logo_bytes", "og_image_bytes"})
    assert "logo_bytes" not in d
    assert "og_image_bytes" not in d
    assert d["logo_url"] == "u"
    assert d["logo_confidence"] == "high"


# ---------------------------------------------------------------------------
# All-or-nothing logo contract
# ---------------------------------------------------------------------------


def test_partial_logo_raises() -> None:
    with pytest.raises(ValueError, match="all be None or all be non-None"):
        BrandIdentity(
            product_name="X", product_url="https://x.com", run_id="r",
            logo_bytes=b"\x89PNG", logo_url=None, logo_confidence=None,
            primary_color="#000", background_color="#fff",
            design_category="minimal-saas", tone="technical",
            writing_instruction="x " * 20,
        )


# ---------------------------------------------------------------------------
# Pipeline integration (mock mode)
# ---------------------------------------------------------------------------


def test_pipeline_run_includes_brand_identity() -> None:
    old = settings.MOCK_MODE
    try:
        settings.MOCK_MODE = True
        from pipeline import run
        r = run("https://example.com", platform="linkedin")
        assert "brand_identity" in r
        bi = r["brand_identity"]
        assert "logo_bytes" not in bi
        assert "og_image_bytes" not in bi
        assert bi["product_name"]
        assert bi["primary_color"]
        assert bi["design_category"]
    finally:
        settings.MOCK_MODE = old
