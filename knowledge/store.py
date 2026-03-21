from __future__ import annotations

from collections import defaultdict

from schemas.brand_profile import BrandProfile
from schemas.knowledge_context import KnowledgeContext
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief

_MEMORY: dict[str, list[dict]] = defaultdict(list)


def query_context(org_id: str, limit: int = 3) -> KnowledgeContext:
    rows = _MEMORY.get(org_id, [])[-limit:]
    return KnowledgeContext(
        org_id=org_id,
        strategy_summaries=[r.get("strategy_summary", "") for r in rows if r.get("strategy_summary")],
        approved_copy_examples=[r.get("approved_copy", "") for r in rows if r.get("approved_copy")],
        proof_points=[r.get("proof_point", "") for r in rows if r.get("proof_point")],
    )


def persist_run(
    org_id: str,
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    strategy_brief: StrategyBrief,
    approved_copy: str,
) -> None:
    _MEMORY[org_id].append(
        {
            "brand_tone": brand_profile.writing_instruction,
            "strategy_summary": strategy_brief.primary_claim,
            "approved_copy": approved_copy,
            "proof_point": strategy_brief.proof_point,
            "product_name": product_knowledge.product_name,
        }
    )
