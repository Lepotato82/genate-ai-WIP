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


def _first_color(tokens: dict[str, str], default: str) -> str:
    for key in ("--color-brand-bg", "--color-accent", "--color-primary", "--background"):
        value = tokens.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in tokens.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _normalize_tone(raw_tone: object) -> str:
    tone = str(raw_tone or "").strip().lower()
    allowed = {"technical", "playful", "corporate", "minimal", "bold"}
    if tone in allowed:
        return tone
    mapping = {
        "dark": "technical",
        "neutral": "minimal",
        "professional": "corporate",
        "clean": "minimal",
        "modern": "technical",
    }
    return mapping.get(tone, "technical")


def _normalize_font_family(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [str(x) for x in value if str(x).strip()]
        if parts:
            return ", ".join(parts)
    return "Inter, system-ui, sans-serif"


def _normalize_font_weights(value: object) -> list[float]:
    if not isinstance(value, list):
        return [400.0]
    out: list[float] = []
    for item in value:
        try:
            out.append(float(item))
        except Exception:
            continue
    return out or [400.0]


def _normalize_instruction(value: object, data: dict, pkg: InputPackage) -> str:
    text = str(value or "").strip()
    if len(text.split()) >= 15:
        return text
    primary = str(data.get("primary_color") or _first_color(pkg.css_tokens, "#5e6ad2"))
    category = str(data.get("design_category") or "developer-tool")
    return (
        f"Write in a direct SaaS tone with concrete specificity, reflect the {category} "
        f"visual identity, reference the primary color {primary}, and avoid generic claims."
    )


def _normalize_design_category(value: object) -> str:
    category = str(value or "").strip()
    allowed = {
        "developer-tool",
        "minimal-saas",
        "bold-enterprise",
        "consumer-friendly",
        "data-dense",
    }
    return category if category in allowed else "developer-tool"


def _normalized_brand_data(data: dict, pkg: InputPackage) -> dict:
    normalized = dict(data)
    normalized["design_category"] = _normalize_design_category(normalized.get("design_category"))
    normalized["primary_color"] = str(
        normalized.get("primary_color") or _first_color(pkg.css_tokens, "#5e6ad2")
    )
    normalized["secondary_color"] = str(
        normalized.get("secondary_color") or pkg.css_tokens.get("--color-accent", "#7170ff")
    )
    normalized["background_color"] = str(
        normalized.get("background_color") or pkg.css_tokens.get("--_bg-body", "#ffffff")
    )
    normalized["font_family"] = _normalize_font_family(normalized.get("font_family"))
    normalized["font_weights"] = _normalize_font_weights(normalized.get("font_weights"))
    normalized["border_radius"] = str(
        normalized.get("border_radius") or pkg.css_tokens.get("--border-radius-md", "6px")
    )
    normalized["spacing_unit"] = str(
        normalized.get("spacing_unit") or pkg.css_tokens.get("--spacing-unit", "4px")
    )
    normalized["tone"] = _normalize_tone(normalized.get("tone"))
    normalized["writing_instruction"] = _normalize_instruction(
        normalized.get("writing_instruction"), normalized, pkg
    )
    try:
        normalized["confidence"] = float(normalized.get("confidence", 0.7))
    except Exception:
        normalized["confidence"] = 0.7
    normalized["confidence"] = min(1.0, max(0.0, normalized["confidence"]))
    return normalized


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
    data = _normalized_brand_data(parse_json_object(raw), pkg)
    return BrandProfile(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        css_tokens=pkg.css_tokens,
        **data,
    )
