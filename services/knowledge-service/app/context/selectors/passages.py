"""K18.3 — L3 semantic passage selector.

Runs after K18.2a classified the user's intent. Steps:

  1. Embed the user message via `embedding_client` (K12.2 → provider-
     registry BYOK).
  2. Dimension-route to the `:Passage` vector index matching the
     project's configured embedding model.
  3. **Dynamic candidate pool sizing** (ContextHub L-CH-02). Pool
     size is intent-aware:
        - SPECIFIC_ENTITY — tight pool (pool_small)
        - GENERAL / RELATIONAL — wider pool (pool_large)
        - HISTORICAL / RECENT_EVENT — middle
  4. **Hub-file dominance penalty** (ContextHub L-CH-03). Chunks
     flagged as `is_hub=True` (L1 summaries, long bios) get their
     score multiplied by a penalty factor. Penalty is steepest for
     SPECIFIC_ENTITY queries (we want the specific detail, not the
     summary) and minimal for GENERAL.
  5. **Intent-driven recency weight**. `intent.recency_weight` is
     already signed (HISTORICAL = -1 → prefer older; RECENT_EVENT =
     +2 → prefer newer). Recency is proxied by `chapter_index`.
  6. **MMR diversification** (λ=0.7). Greedy re-rank that picks the
     next passage maximizing relevance - similarity-to-selected,
     dropping near-duplicate consecutive chunks.
  7. Return ranked `L3Passage` list, truncated to final top-N.

**What's deferred:**
  - Rerank step (LM Studio generative rerank). The plan's acceptance
    criterion allows this as optional; pool sizing is still
    observable via the log line.
  - Ingestion pipeline. This selector returns `[]` when no passages
    exist — harmless.

Reference: KSA §4.3, ContextHub lessons L-CH-02 (dynamic pool),
L-CH-03 (hub penalty), L-CH-07 (intent routing before retrieval).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable

from cachetools import TTLCache

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.context.intent.classifier import Intent, IntentResult
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    PassageSearchHit,
    SUPPORTED_PASSAGE_DIMS,
    find_passages_by_vector,
)

logger = logging.getLogger(__name__)

__all__ = ["L3Passage", "EMBEDDING_MODEL_TO_DIM", "select_l3_passages"]


# Known model → dim mapping. Keys mirror common BYOK model names;
# production projects should have `embedding_dimension` populated
# directly on knowledge_projects (K12.3). This fallback table keeps
# the selector functional when the column isn't projected into the
# in-memory Project model.
EMBEDDING_MODEL_TO_DIM: dict[str, int] = {
    "bge-small": 384,
    "bge-m3": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "nomic-embed-text": 768,  # unsupported dim — selector will skip
    "nomic-embed-code": 768,  # unsupported dim — selector will skip
}


# ── Intent-driven pool sizing (L-CH-02) ─────────────────────────────

# (small_pool, large_pool) per intent. Small pool = SPECIFIC_ENTITY
# case where we want the single best hit; large pool = GENERAL /
# RELATIONAL where we need broader coverage.
_POOL_SIZE: dict[Intent, int] = {
    Intent.SPECIFIC_ENTITY: 20,
    Intent.RECENT_EVENT: 30,
    Intent.HISTORICAL: 30,
    Intent.RELATIONAL: 40,
    Intent.GENERAL: 40,
}

# Final top-N after MMR diversification. Also intent-aware — tight
# queries want few very relevant results; broad queries want variety.
_FINAL_TOP_N: dict[Intent, int] = {
    Intent.SPECIFIC_ENTITY: 5,
    Intent.RECENT_EVENT: 8,
    Intent.HISTORICAL: 8,
    Intent.RELATIONAL: 10,
    Intent.GENERAL: 10,
}

# Hub-file penalty factor (multiplied into score). <1 depresses hub
# chunks; SPECIFIC_ENTITY wants them gone, GENERAL tolerates them.
_HUB_PENALTY: dict[Intent, float] = {
    Intent.SPECIFIC_ENTITY: 0.3,
    Intent.RECENT_EVENT: 0.5,
    Intent.HISTORICAL: 0.5,
    Intent.RELATIONAL: 0.7,
    Intent.GENERAL: 0.9,  # summary is fine
}

# MMR diversification tradeoff — λ·relevance - (1-λ)·redundancy.
# 0.7 matches ContextHub's tuned value; higher = more relevance-
# dominated, lower = more diversity-dominated.
_MMR_LAMBDA = 0.7


@dataclass
class L3Passage:
    """Final scored passage ready for the `<passages>` XML block."""

    text: str
    source_type: str
    source_id: str
    chunk_index: int
    score: float
    is_hub: bool
    chapter_index: int | None


# ── query embedding cache (P-K18.3-01) ──────────────────────────────

_QUERY_EMBEDDING_CACHE_TTL_S = 30.0
_QUERY_EMBEDDING_CACHE_MAX = 512

# Per-worker-process cache for the query embedding step. In a
# multi-turn chat the user often sends consecutive messages whose
# first-pass meaning is similar ("Tell me about Kai." → "and what
# happened next?"); repeated or near-identical queries across turns
# pay provider-registry's embedding round-trip every time without
# this cache. A 30s TTL matches the rhythm of active chat without
# leaking stale embeddings into long-idle sessions.
#
# Key: (user_id, project_id, embedding_model, message) — user_id is
# included because two users sharing a project could be using
# DIFFERENT providers configured under the same model name string;
# their embedding vectors aren't guaranteed to be interchangeable
# across providers, even for an identically-named model. Partitioning
# the cache by user sidesteps that correctness risk at trivially
# higher miss rate.
# Value: list[float] (the vector) — not the full EmbedResult,
# which carries provider metadata we don't need for re-lookup.
#
# Populated only on successful embedding; failed calls (empty vector,
# EmbeddingError) do NOT populate so a transient provider outage
# doesn't lock in an empty result for 30s.
_query_embedding_cache: TTLCache[tuple[str, str, str, str], list[float]] = TTLCache(
    maxsize=_QUERY_EMBEDDING_CACHE_MAX, ttl=_QUERY_EMBEDDING_CACHE_TTL_S,
)


# ── public selector ─────────────────────────────────────────────────


async def select_l3_passages(
    session: CypherSession,
    embedding_client: EmbeddingClient,
    *,
    user_id: str,
    project_id: str,
    message: str,
    intent: IntentResult,
    embedding_model: str | None,
    embedding_dim: int | None,
    user_uuid,   # UUID, needed by embedding_client
    model_source: str = "user_model",
    current_chapter_index: int | None = None,
) -> list[L3Passage]:
    """Run K18.3 semantic retrieval.

    Returns `[]` when the project has no embedding model configured
    (passage infra not yet ingested for this project), when the
    embedding call fails, or when the vector search returns nothing.
    In all of those paths Mode 3 degrades to facts-only — the
    caller should not surface an error.
    """
    if not embedding_model or not embedding_dim:
        logger.debug("K18.3 skipped: project has no embedding_model configured")
        return []
    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        logger.warning(
            "K18.3 skipped: embedding_dim %s not in supported set %s",
            embedding_dim, SUPPORTED_PASSAGE_DIMS,
        )
        return []
    if not message or not message.strip():
        return []

    # 1. Embed the query. P-K18.3-01: cache hit short-circuits the
    # provider-registry round-trip for repeated/near-identical queries
    # inside a 30s window (multi-turn chat case).
    cache_key = (str(user_uuid), project_id, embedding_model, message)
    cached_vector = _query_embedding_cache.get(cache_key)
    if cached_vector is not None:
        query_vector = cached_vector
    else:
        try:
            result = await embedding_client.embed(
                user_id=user_uuid,
                model_source=model_source,
                model_ref=embedding_model,
                texts=[message],
            )
        except EmbeddingError:
            logger.warning(
                "K18.3: embedding failed project=%s — degrading to empty L3",
                project_id, exc_info=True,
            )
            return []

        if not result.embeddings:
            return []
        query_vector = result.embeddings[0]
        _query_embedding_cache[cache_key] = query_vector

    # 2. Dim-routed vector search with intent-tuned pool size.
    pool_size = _POOL_SIZE.get(intent.intent, 30)
    hits = await find_passages_by_vector(
        session,
        user_id=user_id,
        project_id=project_id,
        query_vector=query_vector,
        dim=embedding_dim,
        embedding_model=embedding_model,
        limit=pool_size,
    )

    if not hits:
        return []

    # 3-5. Score each hit: hub penalty + recency weight.
    hub_penalty = _HUB_PENALTY.get(intent.intent, 0.5)
    recency_w = intent.recency_weight
    # If the caller didn't supply a current chapter, treat the newest
    # passage in the pool as "now" — otherwise every passage would see
    # age=0 and recency weighting would produce no differentiation.
    ref_chapter = current_chapter_index
    if ref_chapter is None:
        chapter_indices = [
            h.passage.chapter_index for h in hits
            if h.passage.chapter_index is not None
        ]
        ref_chapter = max(chapter_indices) if chapter_indices else None
    scored = [
        (_apply_post_filters(hit, hub_penalty, recency_w, ref_chapter), hit)
        for hit in hits
    ]

    # 6. MMR diversification (greedy).
    #    Relevance = post-filter score; redundancy proxy = Jaccard
    #    token overlap on the raw text (cheap, language-neutral
    #    enough for MVP; a real embedding-based MMR would re-use
    #    per-passage vectors but we strip those in the repo).
    ordered = _mmr_rerank(scored, _MMR_LAMBDA)

    # 7. Truncate to final top-N.
    top_n = _FINAL_TOP_N.get(intent.intent, 10)
    final = ordered[:top_n]

    logger.info(
        "K18.3: L3 selection intent=%s pool=%d hits=%d final=%d hub_penalty=%.2f "
        "recency_w=%+.1f",
        intent.intent.value, pool_size, len(hits), len(final),
        hub_penalty, recency_w,
    )
    return [
        L3Passage(
            text=hit.passage.text,
            source_type=hit.passage.source_type,
            source_id=hit.passage.source_id,
            chunk_index=hit.passage.chunk_index,
            score=score,
            is_hub=hit.passage.is_hub,
            chapter_index=hit.passage.chapter_index,
        )
        for score, hit in final
    ]


# ── ranking helpers ─────────────────────────────────────────────────


def _apply_post_filters(
    hit: PassageSearchHit,
    hub_penalty: float,
    recency_weight: float,
    current_chapter: int | None,
) -> float:
    """Combine raw cosine score with hub penalty + recency weight.

    Recency decay: `1 / (1 + age_in_chapters)`. Multiplied by the
    intent's `recency_weight`, which is signed — HISTORICAL intent
    has recency_weight = -1, so newer chapters get a NEGATIVE
    multiplier and older chapters float up. The `1 +` in the
    product prevents the score from going to zero when `recency_w`
    is exactly the magnitude of the decay.
    """
    score = hit.raw_score
    if hit.passage.is_hub:
        score *= hub_penalty

    if recency_weight != 0.0 and hit.passage.chapter_index is not None:
        ref = current_chapter if current_chapter is not None else 0
        age = max(0, ref - hit.passage.chapter_index)
        decay = 1.0 / (1.0 + age)
        # Scale by recency_weight. `1 + w * (decay - 0.5)` centers
        # decay around 0 so weight -1 inverts the preference rather
        # than just flattening it.
        score *= 1.0 + recency_weight * (decay - 0.5)
    return score


def _jaccard(a: str, b: str) -> float:
    """Cheap similarity for MMR redundancy term. Word-level Jaccard."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _mmr_rerank(
    scored: Iterable[tuple[float, PassageSearchHit]],
    lam: float,
) -> list[tuple[float, PassageSearchHit]]:
    """Greedy MMR. Picks next passage maximizing
    `lam * relevance - (1-lam) * max(similarity_to_selected)`.

    Runs in O(n²) which is fine at our pool size (≤ 40 candidates).
    """
    candidates = list(scored)
    if not candidates:
        return []
    # Sort candidates by relevance score so the first pick is the
    # unambiguous top relevance row.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[tuple[float, PassageSearchHit]] = [candidates.pop(0)]

    while candidates:
        best_idx = -1
        best_mmr = -math.inf
        for i, (rel, hit) in enumerate(candidates):
            redundancy = max(
                _jaccard(hit.passage.text, sel_hit.passage.text)
                for _, sel_hit in selected
            )
            mmr = lam * rel - (1.0 - lam) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        if best_idx == -1:
            break
        selected.append(candidates.pop(best_idx))

    return selected
