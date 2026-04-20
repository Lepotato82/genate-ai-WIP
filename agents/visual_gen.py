"""
Step 7: Visual Gen Agent.

Generates an image generation prompt using exact brand parameters (hex colors,
font name, design category, OG image as style reference) and a suggested
visual format. Video script is Phase 3 — always None in this version.
"""

from __future__ import annotations

import logging
import sys
import time

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_identity import BrandIdentity
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object

logger = logging.getLogger(__name__)


def _progress(msg: str) -> None:
    """Write a progress line straight to stdout so it appears during long LLM calls."""
    try:
        sys.stdout.buffer.write(f"[visual_gen] {msg}\n".encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        logger.info("[visual_gen] %s", msg)


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

    # Prefer accent_color for visual interest — it's the interactive brand color
    # (extracted from --primary/--ring css tokens). primary_color is often a text color.
    accent_hex = (
        (brand_identity.accent_color if brand_identity else None)
        or brand_profile.primary_color
    )
    lines = [
        f"brand: design_category={brand_profile.design_category}, "
        f"accent_color={accent_hex}, "
        f"secondary_color={brand_profile.secondary_color}, "
        f"background_color={brand_profile.background_color}, "
        f"font={brand_profile.font_family}, tone={brand_profile.tone}",
        f"platform: {content_brief.platform}, content_type: {content_brief.content_type}",
        f"product: {strategy_brief.primary_claim}",
        f"hook_direction: {strategy_brief.hook_direction}",
        f"lead_pain_point: {strategy_brief.lead_pain_point}",
    ]
    if brand_identity is not None:
        lines.append(
            f"identity: product_name={brand_identity.product_name}, "
            f"accent_hex={brand_identity.accent_color or accent_hex}, "
            f"background_hex={brand_identity.background_color or 'none'}, "
            f"primary_font={brand_identity.primary_font or 'none'}"
        )
    user_msg = "\n".join(lines)

    _progress(f"calling LLM (user_msg={len(user_msg)} chars)")
    _t0 = time.time()
    raw = chat_completion(
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_msg},
        ]
    )
    _progress(f"LLM responded in {time.time() - _t0:.1f}s ({len(raw)} chars)")
    data = parse_json_object(raw)
    ip = data.get("image_prompt")
    data["image_prompt"] = ip if isinstance(ip, str) else str(ip or "")
    # video is Phase 3 — always null regardless of LLM output
    data["video_script"] = None
    data["video_hook"] = None
    return data
