"""
Step 5: Strategy.
"""

from __future__ import annotations

from llm.client import chat_completion
from config import settings
from schemas.content_brief import ContentBrief
from schemas.knowledge_context import KnowledgeContext
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief
from agents._utils import parse_json_object, utc_now_iso


def _mock(brief: ContentBrief, knowledge: ProductKnowledge, ctx: KnowledgeContext | None) -> StrategyBrief:
    proof = knowledge.proof_points[0]
    out = StrategyBrief(
        run_id=brief.run_id,
        org_id=brief.org_id,
        created_at=utc_now_iso(),
        lead_pain_point=(
            "Teams lose hours each week rewriting posts that do not match product "
            "positioning, causing delays and inconsistent go-to-market execution."
        ),
        primary_claim="Genate helps SaaS teams generate grounded, brand-aligned content quickly.",
        proof_point=proof.text,
        proof_point_type=proof.proof_type,
        cta_intent="learn_more",
        appeal_type="rational",
        narrative_arc=brief.narrative_arc,
        target_icp_role="Growth marketing manager",
        differentiator=(
            "Unlike generic tools, this workflow ties copy decisions to extracted brand "
            "signals and validated proof points from product context."
        ),
        hook_direction="Open by naming a repeated daily friction and its time cost before product mention.",
        positioning_mode="category_creation",
        messaging_angle_used=knowledge.messaging_angles[0],
        knowledge_context_applied=bool(ctx and ctx.has_context),
    )
    out.validate_against_product_knowledge(knowledge)
    out.validate_against_content_brief(brief)
    return out


def run(
    content_brief: ContentBrief,
    product_knowledge: ProductKnowledge,
    knowledge_context: KnowledgeContext | None = None,
) -> StrategyBrief:
    if settings.MOCK_MODE:
        return _mock(content_brief, product_knowledge, knowledge_context)

    raw = chat_completion(
        [
            {
                "role": "system",
                "content": "Return JSON for StrategyBrief fields excluding run_id/org_id/created_at.",
            },
            {
                "role": "user",
                "content": (
                    f"content_brief={content_brief.model_dump()}\n"
                    f"product_knowledge={product_knowledge.model_dump()}\n"
                    f"knowledge_context={knowledge_context.model_dump() if knowledge_context else None}"
                ),
            },
        ]
    )
    data = parse_json_object(raw)
    strategy = StrategyBrief(
        run_id=content_brief.run_id,
        org_id=content_brief.org_id,
        created_at=utc_now_iso(),
        **data,
    )
    strategy.validate_against_product_knowledge(product_knowledge)
    strategy.validate_against_content_brief(content_brief)
    return strategy
