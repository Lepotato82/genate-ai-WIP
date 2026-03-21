"""
Step 7: Visual Gen.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object


def _mock(brand: BrandProfile, brief: ContentBrief, strategy: StrategyBrief) -> dict:
    return {
        "image_prompt": (
            f"SaaS marketing visual, {brand.design_category} style, primary {brand.primary_color}, "
            f"secondary {brand.secondary_color or brand.primary_color}, minimal layout, headline-led."
        ),
        "suggested_format": "carousel" if brief.content_type == "carousel" else "static",
        "video_script": (
            f"Hook: {strategy.hook_direction}. Problem: {strategy.lead_pain_point}. "
            "Solution: show product workflow. CTA: learn more."
        ),
        "video_hook": "Your team is publishing slower than your product ships.",
    }


def run(brand_profile: BrandProfile, content_brief: ContentBrief, strategy_brief: StrategyBrief) -> dict:
    if settings.MOCK_MODE:
        return _mock(brand_profile, content_brief, strategy_brief)

    raw = chat_completion(
        [
            {
                "role": "system",
                "content": "Return JSON with keys image_prompt,suggested_format,video_script,video_hook.",
            },
            {
                "role": "user",
                "content": (
                    f"brand_profile={brand_profile.model_dump()}\n"
                    f"content_brief={content_brief.model_dump()}\n"
                    f"strategy_brief={strategy_brief.model_dump()}"
                ),
            },
        ]
    )
    return parse_json_object(raw)
