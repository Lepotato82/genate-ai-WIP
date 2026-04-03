"""
Step 7: Visual Gen Agent.

Generates an image generation prompt using exact brand parameters (hex colors,
font name, design category, OG image as style reference) and a suggested
visual format. Video script is Phase 3 — always None in this version.
"""

from __future__ import annotations

import logging

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_identity import BrandIdentity
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object

logger = logging.getLogger(__name__)

_FALLBACK_SYSTEM = (
    "You are a visual direction agent for SaaS marketing. "
    "Return ONLY valid JSON with these keys:\n"
    "  image_prompt: detailed image generation prompt using exact brand colors and style\n"
    "  suggested_format: one of static, carousel, video, ugc\n"
    "  video_script: null\n"
    "  video_hook: null"
)


def _system_prompt() -> str:
    try:
        spec = load_prompt("visual_gen_v1")
        return spec.system_prompt.strip()
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("visual_gen: falling back to inline system prompt: %s", exc)
        return _FALLBACK_SYSTEM


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    content_brief: ContentBrief,
) -> dict:
    suggested = "carousel" if content_brief.content_type == "carousel" else "static"
    return {
        "image_prompt": (
            f"SaaS marketing visual for {brand_profile.design_category} brand. "
            f"Primary color {brand_profile.primary_color}, "
            f"secondary {brand_profile.secondary_color or brand_profile.primary_color}. "
            f"Minimal layout, dark background, headline-led. "
            f"Font: {brand_profile.font_family or 'Inter'}. "
            f"Mood: {brand_profile.tone}. "
            f"Visual concept: {strategy_brief.hook_direction}"
        ),
        "suggested_format": suggested,
        "video_script": None,
        "video_hook": None,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _build_image_prompt(
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    content_brief: ContentBrief,
    identity: BrandIdentity | None,
) -> str:
    """Build a grounded image prompt using exact brand values when available."""
    if identity is None:
        return (
            f"Professional SaaS marketing image. "
            f"Brand colors: {brand_profile.primary_color}. "
            f"Style: {brand_profile.design_category}. "
            f"Platform: {content_brief.platform}."
        )

    parts = [
        f"Professional SaaS marketing visual for {identity.product_name}.",
        f"Brand primary color: {identity.primary_color}.",
    ]
    if identity.secondary_color:
        parts.append(f"Secondary color: {identity.secondary_color}.")
    if identity.background_color:
        parts.append(f"Background: {identity.background_color}.")
    if identity.primary_font:
        parts.append(f"Typography: {identity.primary_font}.")
    parts.append(f"Design style: {identity.design_category}.")
    parts.append(f"Platform format: {content_brief.platform} {content_brief.content_type}.")
    if identity.has_og_image:
        parts.append("Style reference: brand OG image available.")
    if identity.logo_compositing_enabled:
        parts.append("Logo: real brand logo available for compositing.")
    parts.append(f"Narrative: {strategy_brief.lead_pain_point[:80]}.")
    return " ".join(parts)


def run(
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    content_brief: ContentBrief,
    brand_identity: BrandIdentity | None = None,
) -> dict:
    if settings.MOCK_MODE:
        return _mock(strategy_brief, brand_profile, content_brief)

    lines = [
        f"brand: design_category={brand_profile.design_category}, "
        f"primary_color={brand_profile.primary_color}, "
        f"secondary_color={brand_profile.secondary_color}, "
        f"font={brand_profile.font_family}, tone={brand_profile.tone}",
        f"platform: {content_brief.platform}, content_type: {content_brief.content_type}",
        f"product: {strategy_brief.primary_claim}",
        f"hook_direction: {strategy_brief.hook_direction}",
        f"lead_pain_point: {strategy_brief.lead_pain_point}",
    ]
    if brand_identity is not None:
        lines.append(
            f"identity: product_name={brand_identity.product_name}, "
            f"primary_hex={brand_identity.primary_color}, "
            f"secondary_hex={brand_identity.secondary_color or 'none'}, "
            f"background_hex={brand_identity.background_color or 'none'}, "
            f"primary_font={brand_identity.primary_font or 'none'}"
        )
    user_msg = "\n".join(lines)

    raw = chat_completion(
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_msg},
        ]
    )
    data = parse_json_object(raw)
    ip = data.get("image_prompt")
    data["image_prompt"] = ip if isinstance(ip, str) else str(ip or "")
    # video is Phase 3 — always null regardless of LLM output
    data["video_script"] = None
    data["video_hook"] = None
    return data
