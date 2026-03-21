"""
Step 4: Planner — ContentBrief from brand + product + platform.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from llm.client import chat_completion
from prompts.loader import load_prompt
from config import settings
from schemas.brand_profile import BrandProfile
from schemas.content_brief import ContentBrief, PostingStrategy
from schemas.product_knowledge import ProductKnowledge
from agents._utils import parse_json_object, utc_now_iso

_Platform = Literal["linkedin", "twitter", "instagram", "blog"]

_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "platform_rules.json"


def _load_platform_rules() -> dict:
    if not _RULES_PATH.exists():
        return {}
    return json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def _mock_brief(platform: _Platform, run_id: str, org_id: str | None) -> ContentBrief:
    posting = PostingStrategy(
        recommended_frequency="3x weekly",
        best_days=["Tuesday", "Thursday"],
        best_time_window="10:00–12:00 IST",
    )
    common = dict(
        run_id=run_id,
        org_id=org_id,
        created_at=utc_now_iso(),
        content_pillar="product_and_solution",
        funnel_stage="mofu",
        posting_strategy=posting,
        knowledge_context_used=False,
        knowledge_context_summary=None,
        benchmark_reference="SaaS engagement benchmark: platform-native formats outperform generic posts.",
    )
    if platform == "linkedin":
        return ContentBrief(
            **common,
            platform="linkedin",
            content_type="carousel",
            narrative_arc="pain-agitate-solve-cta",
            word_count_target=None,
            slide_count_target=6,
            thread_length_target=None,
            platform_rules_summary=[
                "LinkedIn hook ≤180 characters before see more",
                "Place 3–5 hashtags at end only",
            ],
            seo_keyword=None,
        )
    if platform == "twitter":
        return ContentBrief(
            **common,
            platform="twitter",
            content_type="thread",
            narrative_arc="pain-agitate-solve-cta",
            word_count_target=None,
            slide_count_target=None,
            thread_length_target=6,
            platform_rules_summary=[
                "Thread 4–8 tweets, ≤280 chars each",
                "Hashtags only in final tweet",
            ],
            seo_keyword=None,
        )
    if platform == "instagram":
        return ContentBrief(
            **common,
            platform="instagram",
            content_type="carousel",
            narrative_arc="pain-agitate-solve-cta",
            word_count_target=None,
            slide_count_target=6,
            thread_length_target=None,
            platform_rules_summary=[
                "Preview line ≤125 characters",
                "20–30 hashtags after five line breaks",
            ],
            seo_keyword=None,
        )
    return ContentBrief(
        **common,
        platform="blog",
        content_type="how_to",
        narrative_arc="pain-agitate-solve-cta",
        word_count_target=1800,
        slide_count_target=None,
        thread_length_target=None,
        platform_rules_summary=[
            "Blog body 1200–2500 words",
            "Keyword in first 100 words",
        ],
        seo_keyword="saas workflow automation",
    )


def _enforce_planner_rules(
    data: dict,
    platform: str,
    product_knowledge: ProductKnowledge,
) -> dict:
    d = dict(data)
    if platform == "twitter":
        d["content_type"] = "thread"
        if d.get("thread_length_target") is None:
            d["thread_length_target"] = 6
        d["word_count_target"] = None
        d["seo_keyword"] = None
        d["slide_count_target"] = None
    elif platform == "blog":
        d["content_type"] = "how_to"
        if d.get("word_count_target") is None:
            d["word_count_target"] = 1800
        if d.get("seo_keyword") is None:
            if product_knowledge.messaging_angles:
                d["seo_keyword"] = product_knowledge.messaging_angles[0][:120]
            else:
                d["seo_keyword"] = (
                    (product_knowledge.product_name or "saas")
                    .lower()
                    .replace(" ", "-")[:80]
                )
        d["thread_length_target"] = None
        d["slide_count_target"] = None
    elif platform == "linkedin":
        d.setdefault("content_type", "carousel")
        d.setdefault("narrative_arc", "pain-agitate-solve-cta")
        if d.get("content_type") == "carousel" and d.get("slide_count_target") is None:
            d["slide_count_target"] = 6
        d["word_count_target"] = None
        d["seo_keyword"] = None
        if d.get("content_type") != "thread":
            d["thread_length_target"] = None
    elif platform == "instagram":
        d.setdefault("content_type", "carousel")
        if d.get("content_type") == "carousel" and d.get("slide_count_target") is None:
            d["slide_count_target"] = 6
        d["word_count_target"] = None
        d["seo_keyword"] = None
        if d.get("content_type") != "thread":
            d["thread_length_target"] = None
    return d


def run(
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    platform: _Platform,
) -> ContentBrief:
    run_id = product_knowledge.run_id
    org_id = product_knowledge.org_id

    if settings.MOCK_MODE:
        return _mock_brief(platform, run_id, org_id)

    rules = _load_platform_rules()
    spec = load_prompt("planner_v1")
    user_msg = (
        f"platform={platform}\n\n"
        f"PLATFORM_RULES_JSON:\n{json.dumps(rules.get(platform, {}), indent=2)}\n\n"
        f"brand_profile:\n{json.dumps(brand_profile.model_dump(mode='json'), indent=2, default=str)}\n\n"
        f"product_knowledge:\n{json.dumps(product_knowledge.model_dump(mode='json'), indent=2, default=str)}\n\n"
        "Select the optimal strategy. Return only JSON as specified."
    )
    raw = chat_completion(
        [
            {"role": "system", "content": spec.system_prompt},
            {"role": "user", "content": user_msg},
        ]
    )
    data = parse_json_object(raw)
    data.pop("reasoning", None)
    data = _enforce_planner_rules(data, platform, product_knowledge)

    ps = data.get("posting_strategy") or {}
    posting = PostingStrategy(
        recommended_frequency=str(ps.get("recommended_frequency") or "2–3x weekly"),
        best_days=list(ps.get("best_days") or ["Tuesday", "Thursday"]),
        best_time_window=str(ps.get("best_time_window") or "10:00–12:00 IST"),
    )

    payload = {
        "run_id": run_id,
        "org_id": org_id,
        "created_at": utc_now_iso(),
        "platform": platform,
        "content_type": data["content_type"],
        "narrative_arc": data["narrative_arc"],
        "content_pillar": data["content_pillar"],
        "funnel_stage": data["funnel_stage"],
        "posting_strategy": posting,
        "word_count_target": data.get("word_count_target"),
        "slide_count_target": data.get("slide_count_target"),
        "thread_length_target": data.get("thread_length_target"),
        "platform_rules_summary": list(data.get("platform_rules_summary") or [])[:20],
        "seo_keyword": data.get("seo_keyword"),
        "knowledge_context_used": bool(data.get("knowledge_context_used", False)),
        "knowledge_context_summary": data.get("knowledge_context_summary"),
        "benchmark_reference": str(
            data.get("benchmark_reference") or "SaaS engagement benchmark: native format for platform."
        ),
    }
    if len(payload["platform_rules_summary"]) < 2:
        payload["platform_rules_summary"] = [
            "Follow platform-native structure",
            "Single clear CTA",
        ]
    return ContentBrief.model_validate(payload)
