"""
Step 4: Planner.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from schemas.content_brief import ContentBrief
from schemas.product_knowledge import ProductKnowledge
from schemas.knowledge_context import KnowledgeContext
from agents._utils import parse_json_object, utc_now_iso


def _mock(platform: str, run_id: str, org_id: str | None, knowledge_used: bool) -> ContentBrief:
    return ContentBrief(
        run_id=run_id,
        org_id=org_id,
        created_at=utc_now_iso(),
        platform=platform,  # type: ignore[arg-type]
        content_type="thread" if platform == "twitter" else "text_post",  # type: ignore[arg-type]
        narrative_arc="pain-agitate-solve-cta",
        content_pillar="product_and_solution",
        funnel_stage="mofu",
        posting_strategy={
            "recommended_frequency": "3x weekly",
            "best_days": ["Tuesday", "Thursday"],
            "best_time_window": "10:00-12:00 IST",
        },
        word_count_target=1400 if platform == "blog" else None,
        slide_count_target=None,
        thread_length_target=5 if platform == "twitter" else None,
        platform_rules_summary=["Use platform-native structure", "Keep CTA singular"],
        seo_keyword="saas marketing automation" if platform == "blog" else None,
        knowledge_context_used=knowledge_used,
        knowledge_context_summary="Used prior approved positioning." if knowledge_used else None,
        benchmark_reference="Internal SaaS benchmark: thread format performs best for product education.",
    )


def run(
    platform: str,
    product_knowledge: ProductKnowledge,
    knowledge_context: KnowledgeContext | None = None,
) -> ContentBrief:
    if settings.MOCK_MODE:
        return _mock(platform, product_knowledge.run_id, product_knowledge.org_id, bool(knowledge_context and knowledge_context.has_context))

    raw = chat_completion(
        [
            {
                "role": "system",
                "content": "Return JSON for ContentBrief fields excluding run_id/org_id/created_at.",
            },
            {
                "role": "user",
                "content": (
                    f"platform={platform}\n"
                    f"product_knowledge={product_knowledge.model_dump()}\n"
                    f"knowledge_context={knowledge_context.model_dump() if knowledge_context else None}"
                ),
            },
        ]
    )
    data = parse_json_object(raw)
    return ContentBrief(
        run_id=product_knowledge.run_id,
        org_id=product_knowledge.org_id,
        created_at=utc_now_iso(),
        **data,
    )
