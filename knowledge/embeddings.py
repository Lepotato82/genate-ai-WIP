"""
Fastembed wrapper for the Knowledge Layer.

Lazy-loads the embedding model on first use so that importing this module
has zero cost when KNOWLEDGE_LAYER_ENABLED=false or MOCK_MODE=true.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import settings

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        model_name = settings.EMBEDDING_MODEL
        logger.info("Loading fastembed model: %s", model_name)
        _model = TextEmbedding(model_name=model_name)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_text(text: str) -> list[float]:
    """Generate an embedding for a single text string."""
    return embed_texts([text])[0]
