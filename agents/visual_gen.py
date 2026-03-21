"""
Step 7: Visual Gen Agent.

Generates an image generation prompt using exact brand parameters (hex colors,
font name, design category, OG image as style reference) and a suggested
visual format. Video script is Phase 3 — always None in this version.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object


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

def run(
    strategy_brief: StrategyBrief,
    brand_profile: BrandProfile,
    content_brief: ContentBrief,
) -> dict:
    if settings.MOCK_MODE:
        return _mock(strategy_brief, brand_profile, content_brief)

    user_msg = (
        f"brand: design_category={brand_profile.design_category}, "
        f"primary_color={brand_profile.primary_color}, "
        f"secondary_color={brand_profile.secondary_color}, "
        f"font={brand_profile.font_family}, tone={brand_profile.tone}\n"
        f"product: {strategy_brief.primary_claim}\n"
        f"hook_direction: {strategy_brief.hook_direction}\n"
        f"content_type: {content_brief.content_type}"
    )

    raw = chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "You are a visual direction agent for SaaS marketing. "
                    "Return ONLY valid JSON with these keys:\n"
                    "  image_prompt: detailed image generation prompt using exact brand colors and style\n"
                    "  suggested_format: one of static, carousel, video, ugc\n"
                    "  video_script: null\n"
                    "  video_hook: null"
                ),
            },
            {"role": "user", "content": user_msg},
        ]
    )
    data = parse_json_object(raw)
    # video is Phase 3 — always null regardless of LLM output
    data["video_script"] = None
    data["video_hook"] = None
    return data
