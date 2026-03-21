"""
Supabase (Postgres) relational storage for the Knowledge Layer.

Stores full run artifacts as JSONB for audit trail and potential re-indexing.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import Client, create_client

from config import settings
from schemas.brand_profile import BrandProfile
from schemas.product_knowledge import ProductKnowledge
from schemas.strategy_brief import StrategyBrief

logger = logging.getLogger(__name__)

TABLE = "approved_runs"

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set when "
                "KNOWLEDGE_LAYER_ENABLED=true"
            )
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    return _client


def insert_approved_run(
    org_id: str,
    run_id: str,
    brand_profile: BrandProfile,
    product_knowledge: ProductKnowledge,
    strategy_brief: StrategyBrief,
    approved_copy: str,
) -> None:
    """Insert a single approved run into the approved_runs table."""
    client = _get_client()
    client.table(TABLE).insert(
        {
            "org_id": org_id,
            "run_id": run_id,
            "brand_profile": brand_profile.model_dump(mode="json"),
            "product_knowledge": product_knowledge.model_dump(mode="json"),
            "strategy_brief": strategy_brief.model_dump(mode="json"),
            "approved_copy": approved_copy,
        }
    ).execute()


def get_recent_runs(org_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch the most recent approved runs for an organisation."""
    client = _get_client()
    response = (
        client.table(TABLE)
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []
