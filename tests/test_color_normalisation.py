"""Tests for _to_hex() color normalisation utility and BrandIdentity enforcement."""

from __future__ import annotations

import re

import pytest

from schemas.brand_identity import BrandIdentity, _to_hex
from schemas.brand_profile import BrandProfile

HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


# ---------------------------------------------------------------------------
# _to_hex — pass-through / no-op cases
# ---------------------------------------------------------------------------


def test_hex_passthrough():
    assert _to_hex("#c15f3c") == "#c15f3c"


def test_hex_uppercase_lowercased():
    assert _to_hex("#AABBCC") == "#aabbcc"


def test_hex_3digit_expanded():
    assert _to_hex("#fff") == "#ffffff"


def test_hex_3digit_lowercase():
    assert _to_hex("#abc") == "#aabbcc"


def test_hex_8digit_strips_alpha():
    assert _to_hex("#aabbccdd") == "#aabbcc"


# ---------------------------------------------------------------------------
# _to_hex — rgb / rgba
# ---------------------------------------------------------------------------


def test_rgb_comma_syntax():
    assert _to_hex("rgb(193, 95, 60)") == "#c15f3c"


def test_rgba_strips_alpha():
    assert _to_hex("rgba(193, 95, 60, 0.9)") == "#c15f3c"


def test_rgb_space_syntax():
    assert _to_hex("rgb(193 95 60)") == "#c15f3c"


def test_rgb_zero():
    assert _to_hex("rgb(0, 0, 0)") == "#000000"


def test_rgb_white():
    assert _to_hex("rgb(255, 255, 255)") == "#ffffff"


# ---------------------------------------------------------------------------
# _to_hex — oklch / oklab
# ---------------------------------------------------------------------------


def test_oklch_returns_valid_hex():
    result = _to_hex("oklch(98.4% .006 85.5)")
    assert result is not None
    assert HEX_RE.match(result), f"Not valid hex: {result!r}"


def test_oklch_percent_lightness():
    # High lightness (near white) should give a light color
    result = _to_hex("oklch(99% 0.001 0)")
    assert result is not None
    assert HEX_RE.match(result)


def test_oklab_returns_valid_hex():
    result = _to_hex("oklab(0.999 0.00004 0.00002)")
    assert result is not None
    assert HEX_RE.match(result), f"Not valid hex: {result!r}"


def test_oklab_with_alpha_ignored():
    result = _to_hex("oklab(0.999 0.00004 0.00002 / 0.9)")
    assert result is not None
    assert HEX_RE.match(result)


# ---------------------------------------------------------------------------
# _to_hex — hsl
# ---------------------------------------------------------------------------


def test_hsl_blue():
    result = _to_hex("hsl(210, 100%, 50%)")
    assert result is not None
    assert HEX_RE.match(result)
    # Verify it's a blue-ish color (high blue component)
    b = int(result[5:7], 16)
    assert b > 200, f"Expected high blue component, got {result!r}"


def test_hsla_strips_alpha():
    result = _to_hex("hsla(0, 100%, 50%, 0.5)")
    assert result is not None
    assert HEX_RE.match(result)


# ---------------------------------------------------------------------------
# _to_hex — None / keyword / unknown
# ---------------------------------------------------------------------------


def test_none_returns_none():
    assert _to_hex(None) is None


def test_transparent_returns_none():
    assert _to_hex("transparent") is None


def test_inherit_returns_none():
    assert _to_hex("inherit") is None


def test_currentcolor_returns_none():
    assert _to_hex("currentColor") is None


def test_unknown_format_returns_none_no_raise():
    result = _to_hex("not-a-color-at-all")
    assert result is None


def test_empty_string_returns_none():
    result = _to_hex("")
    # "#" not present, none of the patterns match — should return None
    assert result is None


# ---------------------------------------------------------------------------
# BrandIdentity integration — field_validator enforces hex
# ---------------------------------------------------------------------------


def _make_bi(**overrides) -> BrandIdentity:
    defaults = dict(
        product_name="X",
        product_url="https://x.com",
        run_id="r",
        primary_color="#000",
        background_color="#fff",
        design_category="minimal-saas",
        tone="technical",
        writing_instruction="x " * 20,
    )
    defaults.update(overrides)
    return BrandIdentity(**defaults)


def test_brand_identity_rgb_primary_converted():
    bi = _make_bi(primary_color="rgb(193, 95, 60)")
    assert bi.primary_color == "#c15f3c"


def test_brand_identity_rgb_background_converted():
    bi = _make_bi(background_color="rgb(255, 255, 255)")
    assert bi.background_color == "#ffffff"


def test_brand_identity_oklch_converted():
    bi = _make_bi(primary_color="oklch(50% 0.2 240)")
    assert bi.primary_color is not None
    assert HEX_RE.match(bi.primary_color)


def test_brand_identity_hex_passthrough():
    bi = _make_bi(primary_color="#5e6ad2")
    assert bi.primary_color == "#5e6ad2"


def test_brand_identity_3digit_hex_expanded():
    bi = _make_bi(primary_color="#abc")
    assert bi.primary_color == "#aabbcc"


def test_brand_identity_unparseable_falls_back_via_build():
    """build_brand_identity applies _to_hex() then falls back to #000000."""
    from pipeline import build_brand_identity
    from schemas.input_package import InputPackage
    from schemas.product_knowledge import ProductKnowledge

    pkg = InputPackage(url="https://x.com", run_id="r", css_tokens={})

    # Build a BrandProfile-like object via the actual BrandProfile schema
    brand = BrandProfile(
        run_id="r",
        created_at="2026-01-01T00:00:00Z",
        design_category="minimal-saas",
        primary_color="not-a-color",
        secondary_color=None,
        background_color="rgb(255,255,255)",
        font_family="Inter",
        font_weights=[400.0],
        border_radius="4px",
        spacing_unit="4px",
        tone="technical",
        writing_instruction="x " * 20,
        confidence=0.9,
    )

    product = ProductKnowledge(
        run_id="r",
        created_at="2026-01-01T00:00:00Z",
        product_name="X",
        product_url="https://x.com",
        description=(
            "X is a product built for high-performance engineering teams to get "
            "things done faster, more reliably, and with greater confidence than "
            "any other competing tool available on the market today."
        ),
        product_category="project-management",
        features=[
            {"name": "Feature A", "description": "Does something useful"},
            {"name": "Feature B", "description": "Does something else"},
        ],
        benefits=["Saves time", "Reduces errors"],
        proof_points=[
            {"text": "Used by over 1000 engineering teams worldwide", "proof_type": "user_count", "source": "scraped_page"},
        ],
    )

    bi = build_brand_identity(pkg, brand, product)
    # "not-a-color" → _to_hex returns None → fallback "#000000"
    assert bi.primary_color == "#000000"
    assert bi.background_color == "#ffffff"


def test_css_color_vars_all_hex():
    bi = _make_bi(
        primary_color="rgb(94, 106, 210)",
        secondary_color="rgb(113, 112, 255)",
        background_color="rgb(255, 255, 255)",
        foreground_color="rgb(26, 26, 46)",
    )
    for val in bi.css_color_vars.values():
        assert HEX_RE.match(val), f"Not valid hex in css_color_vars: {val!r}"
