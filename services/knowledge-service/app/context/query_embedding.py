"""Shared per-worker query-embedding cache (mui #4 MED-2).

A single chat/scene message is embedded ONCE per (user, project, model) within
a short TTL window, deduping the embed across the selectors that all embed the
same message in one Mode-3 build: L3 passages, summary-blend, and (mui #4)
glossary-semantic. Extracted from passages.py's P-K18.3-01 cache so the three
share one cache object — previously each embedded the message independently
(2-3 provider-registry round trips for identical text per build).

Best-effort: returns None on an empty or failed embed (callers degrade to []).
Failures are NOT cached, so a transient provider outage doesn't lock in an
empty result for the TTL window. Keyed by user_id because embedding vectors are
model-specific and per-tenant; cross-tenant reuse would be a correctness risk.
"""
from __future__ import annotations

import logging
from uuid import UUID

from cachetools import TTLCache

from app.clients.embedding_client import EmbeddingClient, EmbeddingError

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 30
_CACHE_MAX = 512

# Key: (user_id, project_id, embedding_model, message).
_query_embedding_cache: TTLCache[tuple[str, str, str, str], list[float]] = TTLCache(
    maxsize=_CACHE_MAX, ttl=_CACHE_TTL_S,
)


async def embed_query_cached(
    embedding_client: EmbeddingClient,
    *,
    user_id: UUID,
    project_id: str,
    embedding_model: str,
    message: str,
    model_source: str = "user_model",
) -> list[float] | None:
    """Return the query embedding, hitting a shared TTL cache first.

    None on empty/failed embed (not cached). Matches the prior passages.py
    cache semantics (EmbeddingError → degrade; populate only on success).
    """
    key = (str(user_id), project_id, embedding_model, message)
    cached = _query_embedding_cache.get(key)
    if cached is not None:
        return cached
    try:
        result = await embedding_client.embed(
            user_id=user_id,
            model_source=model_source,
            model_ref=embedding_model,
            texts=[message],
        )
    except EmbeddingError:
        logger.warning(
            "query embed failed project=%s — degrading", project_id, exc_info=True
        )
        return None
    if not result.embeddings or not result.embeddings[0]:
        return None
    vec = result.embeddings[0]
    _query_embedding_cache[key] = vec
    return vec
