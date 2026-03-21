"""
Qdrant vector storage for the Knowledge Layer.

Handles collection lifecycle, vector upserts, and filtered semantic search.
All public functions are safe to call without prior initialization —
the collection is created lazily on first use.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from config import settings

logger = logging.getLogger(__name__)

VECTOR_DIMENSION = 384  # BAAI/bge-small-en-v1.5

_client: QdrantClient | None = None
_collection_ready = False


def _collection_name() -> str:
    return f"{settings.QDRANT_COLLECTION_PREFIX}_knowledge"


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL or None,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _client


def ensure_collection(dimension: int = VECTOR_DIMENSION) -> None:
    """Create the knowledge collection if it does not exist."""
    global _collection_ready
    if _collection_ready:
        return

    client = _get_client()
    name = _collection_name()

    try:
        collections = [c.name for c in client.get_collections().collections]
        if name not in collections:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE,
                ),
            )
            client.create_payload_index(
                collection_name=name,
                field_name="org_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("Created Qdrant collection: %s", name)
        _collection_ready = True
    except Exception:
        logger.warning("Failed to ensure Qdrant collection", exc_info=True)
        raise


def upsert_vectors(
    vectors: list[list[float]],
    payloads: list[dict[str, Any]],
) -> None:
    """Batch-upsert vectors with associated payloads."""
    if not vectors:
        return

    ensure_collection(dimension=len(vectors[0]))
    client = _get_client()

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload=payload,
        )
        for vec, payload in zip(vectors, payloads)
    ]
    client.upsert(collection_name=_collection_name(), points=points)


def search(
    query_vector: list[float],
    org_id: str,
    limit: int = 9,
) -> list[dict[str, Any]]:
    """Semantic search filtered by org_id. Returns scored results with payloads."""
    ensure_collection()
    client = _get_client()

    hits = client.query_points(
        collection_name=_collection_name(),
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))]
        ),
        limit=limit,
        with_payload=True,
    )
    return [
        {"score": hit.score, **(hit.payload or {})}
        for hit in hits.points
    ]
