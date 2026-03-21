"""
Step 2: UI Analyzer.
"""

from __future__ import annotations

from llm.client import vision_completion
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.input_package import InputPackage
from agents._utils import parse_json_object, utc_now_iso


def _mock_profile(pkg: InputPackage) -> BrandProfile:
    return BrandProfile(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        design_category="developer-tool",
        primary_color=pkg.css_tokens.get("--color-brand-bg", "#5e6ad2"),
        secondary_color=pkg.css_tokens.get("--color-accent", "#7170ff"),
        background_color="#ffffff",
        font_family="Inter",
        font_weights=[400.0, 510.0, 590.0],
        border_radius=pkg.css_tokens.get("--border-radius-md", "6px"),
        spacing_unit=pkg.css_tokens.get("--spacing-unit", "4px"),
        tone="technical",
        writing_instruction=(
            "Write in a direct technical SaaS voice, lead with concrete daily "
            "friction, use exact product language, and avoid generic hype claims."
        ),
        css_tokens=pkg.css_tokens,
        confidence=0.8,
    )


def run(pkg: InputPackage) -> BrandProfile:
    if settings.MOCK_MODE:
        return _mock_profile(pkg)

    system = (
        "You are UI Analyzer. Return ONLY JSON for BrandProfile fields: "
        "design_category, primary_color, secondary_color, background_color, "
        "font_family, font_weights, border_radius, spacing_unit, tone, "
        "writing_instruction, confidence. Use one of categories: developer-tool, "
        "minimal-saas, bold-enterprise, consumer-friendly, data-dense."
    )
    user = (
        f"URL: {pkg.url}\n"
        f"CSS tokens: {pkg.css_tokens}\n"
        "Analyze image + css and output JSON only."
    )
    raw = vision_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        image_data=pkg.get_primary_image(),
    )
    data = parse_json_object(raw)
    return BrandProfile(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        css_tokens=pkg.css_tokens,
        **data,
    )
