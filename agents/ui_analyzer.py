"""
Step 2: UI Analyzer — LLM returns flat JSON; Python builds BrandProfile.
"""

from __future__ import annotations

import json

from llm.client import chat_completion
from prompts.loader import load_prompt
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
    def is_color(v: str) -> bool:
        t = v.strip()
        return t.startswith("#") or t.startswith("rgb") or t.startswith("hsl")

    named = (
        "yellow",
        "blue",
        "green",
        "purple",
        "teal",
        "orange",
        "pink",
    )
    for k, v in tokens.items():
        if "brand" in k.lower() and isinstance(v, str) and is_color(v):
            return v.strip()
    for k, v in tokens.items():
        if "accent" in k.lower() and isinstance(v, str) and is_color(v):
            return v.strip()
    for k, v in tokens.items():
        if "primary" in k.lower() and isinstance(v, str) and is_color(v):
            return v.strip()
    for k, v in tokens.items():
        if (
            k.startswith("--")
            and len(k) > 2
            and k[2:].split("-")[0] in named
            and isinstance(v, str)
            and is_color(v)
        ):
            return v.strip()
    for v in tokens.values():
        if isinstance(v, str) and is_color(v):
            return v.strip()
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
        "warm": "playful",
        "friendly": "playful",
        "energetic": "bold",
        "playful": "playful",
    }
    return mapping.get(tone, "minimal")


def _normalize_font_family(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        part = value.split(",")[0].strip().strip('"').strip("'")
        return part or None
    if isinstance(value, list):
        parts = [str(x) for x in value if str(x).strip()]
        if parts:
            return _normalize_font_family(parts[0])
    return None


def _normalize_font_weights(value: object) -> list[float]:
    if not isinstance(value, list):
        return [400.0]
    out: list[float] = []
    for item in value:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out or [400.0]


def _pick_brand_signals(data: dict, tokens: dict[str, str]) -> list[str]:
    """Return up to 4 specific brand signal strings derived from real token values."""
    signals: list[str] = []

    font = (
        data.get("font_family")
        or tokens.get("--_font-family-h1")
        or tokens.get("--font-family-sans")
        or ""
    )
    weight = tokens.get("--_font-weight-h1") or tokens.get("--font-weight-medium") or ""
    if font and weight:
        signals.append(f"{font} at weight {weight}")
    elif font:
        signals.append(font)

    bg = data.get("background_color") or tokens.get("--_bg-body") or ""
    if bg:
        signals.append(f"background {bg}")

    primary = str(data.get("primary_color") or _first_color(tokens, "#5e6ad2"))
    signals.append(f"primary accent {primary}")

    secondary = data.get("secondary_color") or tokens.get("--color-accent") or ""
    if secondary and secondary != primary and len(signals) < 4:
        signals.append(f"secondary {secondary}")

    border = data.get("border_radius") or tokens.get("--border-radius-md") or ""
    if border and len(signals) < 4:
        signals.append(f"border-radius {border}")

    return signals


def _normalize_instruction(value: object, data: dict, pkg: InputPackage) -> str:
    text = str(value or "").strip()
    if len(text.split()) >= 15:
        return text
    signals = _pick_brand_signals(data, pkg.css_tokens)
    signals_str = ", ".join(signals[:4]) if signals else _first_color(pkg.css_tokens, "#5e6ad2")
    category = str(data.get("design_category") or "developer-tool")
    return (
        f"Write in a direct SaaS tone that reflects the {category} visual identity: "
        f"{signals_str}. Lead with concrete specificity and avoid generic claims."
    )
def _pick_brand_signals(data: dict, tokens: dict[str, str]) -> list[str]:
    """Return up to 4 specific brand signal strings derived from real token values."""
    signals: list[str] = []

    font = (
        data.get("font_family")
        or tokens.get("--_font-family-h1")
        or tokens.get("--font-family-sans")
        or ""
    )
    weight = tokens.get("--_font-weight-h1") or tokens.get("--font-weight-medium") or ""
    if font and weight:
        signals.append(f"{font} at weight {weight}")
    elif font:
        signals.append(font)

    bg = data.get("background_color") or tokens.get("--_bg-body") or ""
    if bg:
        signals.append(f"background {bg}")

    primary = str(data.get("primary_color") or _first_color(tokens, "#5e6ad2"))
    signals.append(f"primary accent {primary}")

    secondary = data.get("secondary_color") or tokens.get("--color-accent") or ""
    if secondary and secondary != primary and len(signals) < 4:
        signals.append(f"secondary {secondary}")

    border = data.get("border_radius") or tokens.get("--border-radius-md") or ""
    if border and len(signals) < 4:
        signals.append(f"border-radius {border}")

    return signals


def _build_writing_instruction(pkg: InputPackage, design_category: str) -> str:
    tokens = pkg.css_tokens
    font: str | None = None
    for k, v in tokens.items():
        if "font-family" in k or "font_family" in k:
            if isinstance(v, str) and v.strip():
                font = v.split(",")[0].strip().strip('"').strip("'")
                break

    weights: list[float] = []
    for k, v in tokens.items():
        if "weight" in k.lower() and isinstance(v, str):
            try:
                weights.append(float(v.strip()))
            except (ValueError, TypeError):
                pass

    bg = tokens.get("--_bg-body", tokens.get("--background", ""))
    is_dark = bool(
        bg and not str(bg).startswith(("#fff", "#f9", "#fa", "#fb", "rgb(25"))
    )

    parts: list[str] = []
    if design_category == "developer-tool":
        parts.append("Short declarative sentences.")
        parts.append("Lead with workflow impact.")
        parts.append("Assume technical reader. No superlatives.")
    elif design_category == "consumer-friendly":
        parts.append("Warm, encouraging tone.")
        parts.append("Lead with how the user feels, not features.")
        parts.append("Short sentences. Approachable language.")
    elif design_category == "minimal-saas":
        parts.append("One idea per sentence.")
        parts.append("Lead with the outcome. Confident not pushy.")
    elif design_category == "bold-enterprise":
        parts.append("Direct and authoritative.")
        parts.append("Lead with business impact and ROI.")
    else:
        parts.append("Clear and direct.")
        parts.append("Lead with user benefit.")

    if font:
        parts.append(f"{font} typeface.")
    if weights:
        w_str = "/".join(str(int(w)) for w in sorted(set(weights)))
        parts.append(f"Weight scale: {w_str}.")
    if is_dark:
        parts.append("Dark background — avoid light/airy language.")

    result = " ".join(parts)
    if len(result.split()) >= 15:
        return result
    return result + " Extract brand signals from tokens and echo them in copy."


def _normalize_design_category(value: object, pkg: InputPackage) -> str:
    category = str(value or "").strip()
    allowed = {
        "developer-tool",
        "minimal-saas",
        "bold-enterprise",
        "consumer-friendly",
        "data-dense",
    }
    if category in allowed:
        return category

    bg = pkg.css_tokens.get("--_bg-body", "") or pkg.css_tokens.get("--background", "")
    bg_lower = str(bg).lower()
    light_signals = (
        "#fff",
        "#f",
        "rgb(2",
        "rgb(24",
        "rgb(25",
        "hsl(0, 0%, 9",
    )
    is_dark = (not any(bg_lower.startswith(s) for s in light_signals)) and bool(bg_lower)
    warm_signals = any(
        k in pkg.css_tokens
        for k in ("--yellow", "--orange", "--warm", "--brand-yellow")
    )
    if warm_signals:
        return "consumer-friendly"
    if is_dark:
        return "developer-tool"
    return "minimal-saas"


def _tokens_summary(css_tokens: dict[str, str]) -> dict[str, str]:
    sigs = ("color", "font", "bg", "radius", "spacing", "weight", "background", "foreground")
    return {k: v for k, v in css_tokens.items() if any(s in k.lower() for s in sigs)}


def _build_user_message(tokens_summary: dict[str, str]) -> str:
    return (
        "---\n"
        f"CSS tokens extracted from this site:\n{json.dumps(tokens_summary, indent=2)}\n\n"
        "Classify this brand and return a BrandProfile JSON.\n"
        "---"
    )


def _normalize_brand_dict(data: dict, pkg: InputPackage) -> dict:
    normalized = dict(data)
    for _k in ("run_id", "org_id", "created_at", "css_tokens"):
        normalized.pop(_k, None)

    normalized["design_category"] = _normalize_design_category(
        normalized.get("design_category"), pkg
    )
    normalized["primary_color"] = str(
        normalized.get("primary_color") or _first_color(pkg.css_tokens, "#5e6ad2")
    )
    sec = normalized.get("secondary_color")
    normalized["secondary_color"] = (
        None
        if sec is None or str(sec).strip().lower() in ("null", "none", "")
        else str(sec).strip()
    )
    if not normalized["secondary_color"]:
        normalized["secondary_color"] = pkg.css_tokens.get("--color-accent")

    bg = normalized.get("background_color")
    normalized["background_color"] = (
        None
        if bg is None or str(bg).strip().lower() in ("null", "none", "")
        else str(bg).strip()
    )
    if not normalized["background_color"]:
        normalized["background_color"] = pkg.css_tokens.get("--_bg-body", "#ffffff")

    normalized["font_family"] = _normalize_font_family(normalized.get("font_family"))
    normalized["font_weights"] = _normalize_font_weights(normalized.get("font_weights"))
    normalized["border_radius"] = str(
        normalized.get("border_radius") or pkg.css_tokens.get("--border-radius-md", "6px")
    )
    normalized["spacing_unit"] = str(
        normalized.get("spacing_unit") or pkg.css_tokens.get("--spacing-unit", "4px")
    )
    normalized["tone"] = _normalize_tone(normalized.get("tone"))

    wi = str(normalized.get("writing_instruction") or "").strip()
    if len(wi.split()) < 15:
        wi = _build_writing_instruction(pkg, str(normalized["design_category"]))
    normalized["writing_instruction"] = wi

    try:
        normalized["confidence"] = float(normalized.get("confidence", 0.7))
    except (TypeError, ValueError):
        normalized["confidence"] = 0.7
    normalized["confidence"] = min(1.0, max(0.0, normalized["confidence"]))

    fields = (
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
    )
    return {k: normalized[k] for k in fields}


def run(input_package: InputPackage) -> BrandProfile:
    pkg = input_package
    if settings.MOCK_MODE:
        return _mock_profile(pkg)

    spec = load_prompt("ui_analyzer_v1")
    system_prompt = spec.system_prompt
    summary = _tokens_summary(pkg.css_tokens)
    user_content = _build_user_message(summary)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw = chat_completion(messages)

    data = _normalize_brand_dict(parse_json_object(raw), pkg)
    return BrandProfile(
        run_id=pkg.run_id,
        org_id=pkg.org_id,
        created_at=utc_now_iso(),
        css_tokens=pkg.css_tokens,
        **data,
    )
