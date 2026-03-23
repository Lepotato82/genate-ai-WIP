"""
Step 4: Planner.

Selects content type, narrative arc, content pillar, and posting strategy.
Returns a ContentBrief consumed by the Strategy agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from agents._utils import parse_json_object, utc_now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_platform_rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "platform_rules.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _platform_rules_summary(platform: str) -> list[str]:
    rules = _load_platform_rules()
    pr = rules.get(platform, {})
    if platform == "linkedin":
        return [
            f"Hook must be standalone in first {pr.get('hook_max_chars', 180)} characters",
            f"{pr.get('hashtags_min', 3)}-{pr.get('hashtags_max', 5)} hashtags at end only, never inline",
            "Short paragraphs with blank line between each",
        ]
    if platform == "twitter":
        return [
            f"Thread of {pr.get('thread_min', 4)}-{pr.get('thread_max', 8)} tweets",
            f"Each tweet max {pr.get('tweet_max_chars', 280)} chars",
            f"{pr.get('hashtags_min', 1)}-{pr.get('hashtags_max', 2)} hashtags in final tweet only",
        ]
    if platform == "instagram":
        return [
            f"First {pr.get('preview_max_chars', 125)} chars must be a complete emotional statement",
            (
                f"{pr.get('hashtags_min', 20)}-{pr.get('hashtags_max', 30)} hashtags "
                f"after {pr.get('line_breaks_before_hashtags', 5)} blank line breaks"
            ),
        ]
    if platform == "blog":
        return [
            f"Word count {pr.get('word_count_min', 1200)}-{pr.get('word_count_max', 2500)}",
            f"SEO keyword in first {pr.get('keyword_first_words', 100)} words",
            f"Meta title {pr.get('meta_title_min', 50)}-{pr.get('meta_title_max', 60)} chars",
        ]
    return ["Use platform-native structure", "Keep CTA singular"]


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

def _mock(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    platform: str,
) -> ContentBrief:
    return ContentBrief(
        run_id=product_knowledge.run_id,
        org_id=product_knowledge.org_id,
        created_at=utc_now_iso(),
        platform="linkedin",  # type: ignore[arg-type]
        content_type="carousel",  # type: ignore[arg-type]
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="pain_and_problem",
        funnel_stage="tofu",
        slide_count_target=8,
        word_count_target=None,
        thread_length_target=None,
        posting_strategy={
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        },
        platform_rules_summary=_platform_rules_summary("linkedin"),
        seo_keyword=None,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference=(
            "LinkedIn carousel posts generate 3x more reach than text-only posts "
            "for B2B SaaS accounts (Socialinsider 2024 benchmark)."
        ),
    )


# ---------------------------------------------------------------------------
# System prompt (inline — Person B will replace with YAML later)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a SaaS content strategist. Given a brand profile and product knowledge, "
    "select the optimal LinkedIn content strategy.\n"
    "Return ONLY valid JSON with these fields:\n"
    "  content_type: one of carousel, text_post, single_image\n"
    "  narrative_arc: one of pain-agitate-solve-cta, before-after-bridge-cta, "
    "stat-hook-problem-solution-cta\n"
    "  content_pillar: one of pain_and_problem, education_and_insight, "
    "product_and_solution, social_proof, founder_team_voice\n"
    "  funnel_stage: one of tofu, mofu, bofu\n"
    "  slide_count_target: integer 6-10 (required for carousel, omit for others)\n"
    "  reasoning: one sentence explaining this choice\n"
    "  benchmark_reference: cite a relevant engagement benchmark"
)

# Valid LinkedIn content types — used to coerce invalid LLM output
_VALID_LINKEDIN_CONTENT_TYPES = {
    "carousel", "text_post", "multi_image", "short_video",
    "poll", "question_post", "single_image",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    platform: str = "linkedin",
) -> ContentBrief:
    run_id = product_knowledge.run_id
    org_id = product_knowledge.org_id

    if settings.MOCK_MODE:
        return _mock(brand_profile, product_knowledge, platform)

    pain_top3 = product_knowledge.pain_points[:3]
    user_msg = (
        f"product_name: {product_knowledge.product_name}\n"
        f"product_category: {product_knowledge.product_category}\n"
        f"pain_points: {pain_top3}\n"
        f"messaging_angles: {product_knowledge.messaging_angles}\n"
        f"brand_tone: {brand_profile.tone}\n"
        f"platform: {platform}"
    )

    raw = chat_completion(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    data = parse_json_object(raw)

    # Enforce platform compatibility — default to carousel if invalid
    if platform == "linkedin":
        ct = str(data.get("content_type", "carousel"))
        if ct not in _VALID_LINKEDIN_CONTENT_TYPES:
            ct = "carousel"
        data["content_type"] = ct

    # carousel requires slide_count_target (6–10)
    if data.get("content_type") == "carousel":
        sct = data.get("slide_count_target")
        try:
            sct = int(sct)
        except (TypeError, ValueError):
            sct = 8
        data["slide_count_target"] = max(6, min(10, sct))
    else:
        data.pop("slide_count_target", None)

    # thread requires thread_length_target; others must not have it
    if data.get("content_type") == "thread":
        data.setdefault("thread_length_target", 5)
    else:
        data.pop("thread_length_target", None)

    # Strip keys that don't belong in ContentBrief
    data.pop("reasoning", None)

    # Provide posting_strategy default if LLM omitted it
    if not data.get("posting_strategy"):
        data["posting_strategy"] = {
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        }

    return ContentBrief(
        run_id=product_knowledge.run_id,
        org_id=product_knowledge.org_id,
        created_at=utc_now_iso(),
        platform=platform,  # type: ignore[arg-type]
        platform_rules_summary=_platform_rules_summary(platform),
        word_count_target=None,
        seo_keyword=None,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        **data,
    )
