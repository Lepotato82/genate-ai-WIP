"""
Knowledge Layer orchestrator.

Public API consumed by pipeline.py and api.py:
  - query_context(org_id, query_text, limit)  → KnowledgeContext
  - persist_run(org_id, brand_profile, product_knowledge, strategy_brief, approved_copy)

Delegates to:
  - knowledge.embeddings   (fastembed vectors)
  - knowledge.qdrant_store (Qdrant semantic search)
  - knowledge.supabase_store (Supabase relational storage)

Graceful degradation: external failures are logged but never raised.
The pipeline always continues — query_context returns empty context,
persist_run silently skips.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from schemas.brand_profile import BrandProfile
from schemas.knowledge_context import KnowledgeContext
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief

logger = logging.getLogger(__name__)


def query_context(
    org_id: str,
    query_text: str = "",
    limit: int = 3,
) -> KnowledgeContext:
    """
    Retrieve semantically relevant context from previous approved runs.

    If *query_text* is provided, Qdrant semantic search is used.
    Falls back to empty context on any error.
    """
    empty = KnowledgeContext(org_id=org_id)

    if not query_text:
        return empty

    try:
        from knowledge.embeddings import embed_text
        from knowledge.qdrant_store import search

        query_vector = embed_text(query_text)
        # Fetch more results than limit so we can group by content_type
        hits = search(query_vector=query_vector, org_id=org_id, limit=limit * 3)

        strategy_summaries: list[str] = []
        approved_copy_examples: list[str] = []
        proof_points: list[str] = []

        for hit in hits:
            text = hit.get("text", "")
            if not text:
                continue
            content_type = hit.get("content_type", "")
            if content_type == "strategy_summary" and len(strategy_summaries) < limit:
                strategy_summaries.append(text)
            elif content_type == "approved_copy" and len(approved_copy_examples) < limit:
                approved_copy_examples.append(text)
            elif content_type == "proof_point" and len(proof_points) < limit:
                proof_points.append(text)

        return KnowledgeContext(
            org_id=org_id,
            strategy_summaries=strategy_summaries,
            approved_copy_examples=approved_copy_examples,
            proof_points=proof_points,
        )
    except Exception:
        logger.warning("Knowledge query failed — returning empty context", exc_info=True)
        return empty


def persist_run(
    org_id: str,
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    strategy_brief: StrategyBrief,
    approved_copy: str,
) -> None:
    """
    Persist an approved run to Supabase (relational) and Qdrant (vectors).

    Each run produces multiple vectors in Qdrant:
      - strategy_summary  (primary_claim + lead_pain_point)
      - approved_copy     (the final approved text)
      - proof_point       (one per proof point used)
    """
    run_id = getattr(strategy_brief, "run_id", "") or ""
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Supabase persist ─────────────────────────────────────────────────
    try:
        from knowledge.supabase_store import insert_approved_run

        insert_approved_run(
            org_id=org_id,
            run_id=run_id,
            brand_profile=brand_profile,
            product_knowledge=product_knowledge,
            strategy_brief=strategy_brief,
            approved_copy=approved_copy,
        )
    except Exception:
        logger.warning("Supabase persist failed — skipping", exc_info=True)

    # ── Qdrant vector persist ────────────────────────────────────────────
    try:
        from knowledge.embeddings import embed_texts
        from knowledge.qdrant_store import upsert_vectors

        texts: list[str] = []
        payloads: list[dict] = []
        base_payload = {"org_id": org_id, "run_id": run_id, "created_at": now_iso}

        strategy_summary = (
            f"{strategy_brief.primary_claim}. {strategy_brief.lead_pain_point}"
        )
        texts.append(strategy_summary)
        payloads.append({**base_payload, "content_type": "strategy_summary", "text": strategy_summary})

        if approved_copy:
            # Truncate very long copy for embedding (models have token limits)
            copy_for_embedding = approved_copy[:2000]
            texts.append(copy_for_embedding)
            payloads.append({**base_payload, "content_type": "approved_copy", "text": approved_copy})

        if strategy_brief.proof_point:
            texts.append(strategy_brief.proof_point)
            payloads.append({**base_payload, "content_type": "proof_point", "text": strategy_brief.proof_point})

        vectors = embed_texts(texts)
        upsert_vectors(vectors=vectors, payloads=payloads)
    except Exception:
        logger.warning("Qdrant persist failed — skipping", exc_info=True)
