"""
schemas/brand_identity.py
Genate — BrandIdentity

Consolidated brand visual data for Visual Gen and Phase 2
image pipeline. Assembled from InputPackage + BrandProfile.
No LLM — deterministic construction only.

Constructed by: pipeline.build_brand_identity()
Consumed by: Visual Gen (Step 7), Phase 2 image pipeline
"""

from __future__ import annotations

import logging
import math
import re
import colorsys
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)


def _to_hex(color: str | None) -> str | None:
    """
    Convert any CSS color string to #rrggbb hex.
    Returns None for None input, transparent, inherit, currentColor.
    Falls back gracefully on unknown formats — never raises.
    """
    if color is None:
        return None

    color = color.strip()

    # Already hex — pass through, normalise case and expand 3-digit
    if color.startswith("#"):
        h = color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return f"#{h.lower()}"
        if len(h) == 8:
            # 8-digit hex has alpha — strip it
            return f"#{h[:6].lower()}"
        logger.warning("[brand_identity] unrecognised hex format: %s", color)
        return None

    # Transparent / keyword values — treat as absent
    if color.lower() in ("transparent", "inherit", "currentcolor", "none"):
        return None

    # rgb() / rgba() — comma-separated
    rgb_match = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", color)
    if rgb_match:
        r, g, b = [int(float(x)) for x in rgb_match.groups()]
        return f"#{r:02x}{g:02x}{b:02x}"

    # rgb() with space-separated modern syntax: rgb(193 95 60)
    rgb_space = re.match(r"rgba?\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)", color)
    if rgb_space:
        r, g, b = [int(float(x)) for x in rgb_space.groups()]
        return f"#{r:02x}{g:02x}{b:02x}"

    # oklch(L% C H) — perceptual color space
    oklch_match = re.match(r"oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)", color)
    if oklch_match:
        L_raw, C, H = [float(x) for x in oklch_match.groups()]
        L = L_raw / 100 if L_raw > 1 else L_raw
        h_rad = H * math.pi / 180
        a = C * math.cos(h_rad)
        b_val = C * math.sin(h_rad)
        r_ = L + 0.3963377774 * a + 0.2158037573 * b_val
        g_ = L - 0.1055613458 * a - 0.0638541728 * b_val
        b_ = L - 0.0894841775 * a - 1.2914855480 * b_val

        def _f(x: float) -> float:
            return max(0.0, min(1.0, x ** 3))

        def _gamma(x: float) -> float:
            if x <= 0.0031308:
                return 12.92 * x
            return 1.055 * (x ** (1 / 2.4)) - 0.055

        r8 = max(0, min(255, int(_gamma(_f(r_)) * 255)))
        g8 = max(0, min(255, int(_gamma(_f(g_)) * 255)))
        b8 = max(0, min(255, int(_gamma(_f(b_)) * 255)))
        return f"#{r8:02x}{g8:02x}{b8:02x}"

    # oklab(L a b) or oklab(L a b / alpha)
    oklab_match = re.match(r"oklab\(\s*([\d.]+)\s+([-\d.]+)\s+([-\d.]+)", color)
    if oklab_match:
        L, a, b_val = [float(x) for x in oklab_match.groups()]
        r_ = L + 0.3963377774 * a + 0.2158037573 * b_val
        g_ = L - 0.1055613458 * a - 0.0638541728 * b_val
        b_ = L - 0.0894841775 * a - 1.2914855480 * b_val

        def _f2(x: float) -> float:
            return max(0.0, min(1.0, x ** 3))

        def _gamma2(x: float) -> float:
            if x <= 0.0031308:
                return 12.92 * x
            return 1.055 * (x ** (1 / 2.4)) - 0.055

        r8 = max(0, min(255, int(_gamma2(_f2(r_)) * 255)))
        g8 = max(0, min(255, int(_gamma2(_f2(g_)) * 255)))
        b8 = max(0, min(255, int(_gamma2(_f2(b_)) * 255)))
        return f"#{r8:02x}{g8:02x}{b8:02x}"

    # hsl() / hsla()
    hsl_match = re.match(r"hsla?\(\s*([\d.]+)\s*,?\s*([\d.]+)%\s*,?\s*([\d.]+)%", color)
    if hsl_match:
        h, s, l = [float(x) for x in hsl_match.groups()]
        r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    logger.warning("[brand_identity] unknown color format, returning None: %r", color)
    return None


class BrandIdentity(BaseModel):
    """
    Consolidated brand visual data for Visual Gen and Phase 2
    image pipeline. Assembled from InputPackage + BrandProfile.
    No LLM — deterministic construction only.
    """

    # -- Identity ----------------------------------------------------------
    product_name: str
    product_url: str
    run_id: str

    # -- Logo (from InputPackage) ------------------------------------------
    logo_bytes: bytes | None = None
    logo_url: str | None = None
    logo_confidence: Literal["high", "medium", "low"] | None = None

    # -- OG image (from InputPackage) --------------------------------------
    # Used as IP-Adapter style reference in Fal.ai (Phase 2)
    og_image_url: str | None = None
    og_image_bytes: bytes | None = None

    # -- Colors (from BrandProfile CSS tokens) -----------------------------
    primary_color: str                    # e.g. "#5e6ad2"
    secondary_color: str | None = None
    accent_color: str | None = None
    background_color: str
    foreground_color: str | None = None   # text color

    # -- Typography (from BrandProfile CSS tokens) -------------------------
    font_family_heading: str | None = None
    font_family_body: str | None = None
    font_family_mono: str | None = None
    font_weights: list[float] = []

    # -- Geometry (from BrandProfile CSS tokens) ---------------------------
    border_radius: str | None = None
    spacing_unit: str | None = None

    # -- Brand character (from BrandProfile) -------------------------------
    design_category: Literal[
        "developer-tool",
        "minimal-saas",
        "bold-enterprise",
        "consumer-friendly",
        "data-dense",
    ]
    tone: str
    writing_instruction: str

    # -- Phase 2 compositing guidance --------------------------------------
    # Computed from logo_confidence — Phase 2 checks this before
    # attempting logo compositing. Never composite low confidence.
    logo_compositing_enabled: bool = False

    model_config = {"arbitrary_types_allowed": True}

    @field_validator(
        "primary_color", "secondary_color", "accent_color",
        "background_color", "foreground_color",
        mode="before",
    )
    @classmethod
    def ensure_hex(cls, v: object) -> object:
        if v is None:
            return v
        result = _to_hex(str(v))
        if result is None and v is not None:
            logger.warning("[BrandIdentity] could not convert color to hex: %r", v)
        return result

    @model_validator(mode="after")
    def set_compositing_flag(self) -> "BrandIdentity":
        """
        Enable logo compositing only when confidence is high.
        medium = og:image used (may be marketing graphic not logo)
        low    = favicon only (too small to composite)
        None   = no logo found
        """
        self.logo_compositing_enabled = self.logo_confidence == "high"
        return self

    @model_validator(mode="after")
    def logo_fields_consistent(self) -> "BrandIdentity":
        """Mirror the all-or-nothing contract from InputPackage."""
        logo_fields = [self.logo_bytes, self.logo_url, self.logo_confidence]
        none_count = sum(1 for f in logo_fields if f is None)
        if none_count not in (0, 3):
            raise ValueError(
                "logo_bytes, logo_url, and logo_confidence must all be "
                "None or all be non-None."
            )
        return self

    # -- Convenience properties for Phase 2 --------------------------------

    @property
    def has_logo(self) -> bool:
        return self.logo_bytes is not None

    @property
    def has_og_image(self) -> bool:
        return self.og_image_bytes is not None or self.og_image_url is not None

    @property
    def css_color_vars(self) -> dict[str, str]:
        """
        Returns a dict of CSS variable name -> color value for
        Bannerbear/Placid template injection in Phase 2.
        Only includes non-None color values.
        """
        vars_: dict[str, str] = {}
        if self.primary_color:
            vars_["--color-primary"] = self.primary_color
        if self.secondary_color:
            vars_["--color-secondary"] = self.secondary_color
        if self.accent_color:
            vars_["--color-accent"] = self.accent_color
        if self.background_color:
            vars_["--color-background"] = self.background_color
        if self.foreground_color:
            vars_["--color-foreground"] = self.foreground_color
        return vars_

    @property
    def primary_font(self) -> str | None:
        """Returns the heading font, falling back to body font."""
        return self.font_family_heading or self.font_family_body

    @property
    def heading_font_weight(self) -> float | None:
        """
        Returns the heaviest font weight available.
        Used for headline text in Bannerbear templates.
        """
        return max(self.font_weights) if self.font_weights else None

    @property
    def body_font_weight(self) -> float | None:
        """
        Returns the lightest font weight available.
        Used for body text in Bannerbear templates.
        """
        return min(self.font_weights) if self.font_weights else None
