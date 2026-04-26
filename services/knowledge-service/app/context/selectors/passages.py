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
  - Rerank step (LM Studio generative rerank — D-K18.3-02). The plan's
    acceptance criterion allows this as optional; pool sizing is still
    observable via the log line.

Reference: KSA §4.3, ContextHub lessons L-CH-02 (dynamic pool),
L-CH-03 (hub penalty), L-CH-07 (intent routing before retrieval).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from cachetools import TTLCache

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.clients.llm_client import LLMClient
from app.context.intent.classifier import Intent, IntentResult
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    PassageSearchHit,
    SUPPORTED_PASSAGE_DIMS,
    find_passages_by_vector,
)

logger = logging.getLogger(__name__)

__all__ = [
    "L3Passage",
    "EMBEDDING_MODEL_TO_DIM",
    "select_l3_passages",
    "rerank_passages",
]


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
    llm_client: LLMClient | None = None,
    rerank_model: str | None = None,
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
    # P-K18.3-02: include_vectors=True so MMR's redundancy term can
    # use real embedding cosine distance between passages instead of
    # the cheap text-Jaccard fallback. The extra list[float] per hit
    # adds ~4-12 KB per response at pool_size * dim; fine at pool<=40.
    pool_size = _POOL_SIZE.get(intent.intent, 30)
    hits = await find_passages_by_vector(
        session,
        user_id=user_id,
        project_id=project_id,
        query_vector=query_vector,
        dim=embedding_dim,
        embedding_model=embedding_model,
        limit=pool_size,
        include_vectors=True,
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
    #    Relevance = post-filter score; redundancy term = embedding
    #    cosine between hits (P-K18.3-02). The repo round-trips the
    #    stored vector onto each PassageSearchHit when include_vectors
    #    is set at the query site above, so MMR gets real semantic
    #    distance. Word-Jaccard stays as the fallback if any hit
    #    somehow lacks a vector (e.g., a future caller opts out).
    #
    #    top_n is passed in so MMR can stop after the final-cut set is
    #    filled. With cosine at dim=3072 and pool=40, ranking the full
    #    pool costs ~1.2 s (benchmark) vs. ~57 ms for top_n=10 — the
    #    caller only uses `ordered[:top_n]` anyway, so early-exit is a
    #    pure win. Critical at higher embedding dims where ranking the
    #    tail would eat most of the L3 timeout budget.
    top_n = _FINAL_TOP_N.get(intent.intent, 10)
    ordered = _mmr_rerank(scored, _MMR_LAMBDA, top_n=top_n)

    # 7. Truncate to final top-N (MMR already stopped there; this is a
    # belt-and-braces for the fallback path where top_n was None).
    final = ordered[:top_n]

    logger.info(
        "K18.3: L3 selection intent=%s pool=%d hits=%d final=%d hub_penalty=%.2f "
        "recency_w=%+.1f",
        intent.intent.value, pool_size, len(hits), len(final),
        hub_penalty, recency_w,
    )
    passages = [
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

    # 8. Optional generative rerank (D-K18.3-02). Opt-in via
    #    project.extraction_config["rerank_model"]; skipped when the
    #    llm_client isn't injected OR the model is unset OR the
    #    final cut is < 2 passages (nothing to reorder). Any failure
    #    inside rerank_passages falls back to the MMR order — the
    #    caller never sees an exception.
    if (
        rerank_model
        and llm_client is not None
        and len(passages) >= 2
    ):
        passages = await rerank_passages(
            llm_client,
            query=message,
            passages=passages,
            model=rerank_model,
            user_id=user_uuid,
            model_source=model_source,
        )
    return passages


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
    """Word-level Jaccard — MMR redundancy fallback when vectors are
    unavailable (include_vectors=False path, or a hit that raced the
    vector projection)."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _cosine(a: list[float], na: float, b: list[float], nb: float) -> float:
    """Cosine similarity with pre-computed L2 norms.

    Returns 0.0 if either vector has zero magnitude — safer than
    raising, because MMR treats 0 as "not redundant" which is the
    conservative call for a degenerate vector.
    """
    if na == 0.0 or nb == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (na * nb)


def _norm(v: list[float]) -> float:
    """L2 norm for the cosine denominator. Separated from `_cosine` so
    we can precompute per-hit once and amortize across the N² loop."""
    return math.sqrt(sum(x * x for x in v))


def _mmr_rerank(
    scored: Iterable[tuple[float, PassageSearchHit]],
    lam: float,
    *,
    top_n: int | None = None,
) -> list[tuple[float, PassageSearchHit]]:
    """Greedy MMR. Picks next passage maximizing
    `lam * relevance - (1-lam) * max(similarity_to_selected)`.

    Redundancy uses embedding cosine when both the candidate and the
    selected hit carry vectors (P-K18.3-02); otherwise falls back to
    word-Jaccard on text. Norms are cached per hit so each cosine is
    one dot product + one divide.

    `top_n` caps how many passages get selected — the outer selector
    truncates to top_n anyway, and MMR ranking past that bound is pure
    waste. Without this cap, pool=40 at dim=3072 spends ~1.2 s ranking
    30 tail passages that get dropped; capping to top_n=10 cuts that to
    ~57 ms (measured). `None` means "rank everything" for callers that
    need the full ordering.
    """
    candidates = list(scored)
    if not candidates:
        return []
    # Pre-compute L2 norms so cosine in the hot loop is just a dot/div.
    # Keyed by id(hit) — pairs are rebuilt by the selector each turn so
    # the identity stays stable for the duration of this function call.
    norms: dict[int, float] = {}
    for _, hit in candidates:
        if hit.vector is not None:
            norms[id(hit)] = _norm(hit.vector)

    # Sort candidates by relevance score so the first pick is the
    # unambiguous top relevance row.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[tuple[float, PassageSearchHit]] = [candidates.pop(0)]

    while candidates:
        if top_n is not None and len(selected) >= top_n:
            break
        best_idx = -1
        best_mmr = -math.inf
        for i, (rel, hit) in enumerate(candidates):
            redundancy = 0.0
            for _, sel_hit in selected:
                if hit.vector is not None and sel_hit.vector is not None:
                    red = _cosine(
                        hit.vector, norms[id(hit)],
                        sel_hit.vector, norms[id(sel_hit)],
                    )
                else:
                    red = _jaccard(hit.passage.text, sel_hit.passage.text)
                if red > redundancy:
                    redundancy = red
            mmr = lam * rel - (1.0 - lam) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        if best_idx == -1:
            break
        selected.append(candidates.pop(best_idx))

    return selected


# ── generative rerank (D-K18.3-02) ──────────────────────────────────


# Chars of each passage surfaced to the rerank LLM. Enough to carry
# the semantic gist for a relevance judgement without blowing the
# prompt up — a 10-passage pool at 200 chars each is ~2 KB of prompt
# before boilerplate, comfortably under any reasonable context budget.
_RERANK_PASSAGE_CHAR_BUDGET = 200

# Inner timeout for the rerank LLM call. Deliberately shorter than
# context_l3_timeout_s (2.0s) so a slow rerank model falls back to
# the MMR order instead of eating the whole L3 budget and leaving
# Mode 3 with no passages at all. Opt-in doesn't excuse the
# regression — enabling rerank must never produce strictly worse
# context than disabling it. Tunable via kwarg on `rerank_passages`.
_RERANK_TIMEOUT_S = 1.0

# Per-index budget in the response: "{"order":[0,1,2,...]}" — each
# index is ≤ 3 digits + a comma, so ~5 tokens is generous. Plus object
# wrapping overhead.
def _rerank_max_tokens(n: int) -> int:
    return max(32, 8 + 5 * n)


_RERANK_SYSTEM_PROMPT = (
    "You rank passages by relevance to a user query. "
    "Reply with ONLY a JSON object of the form "
    '{"order":[int,int,...]} listing the passage indices in the '
    "order most relevant first. Do not include prose, markdown, or "
    "any index outside the input range. Do not repeat indices."
)


def _build_rerank_user_prompt(query: str, passages: list[L3Passage]) -> str:
    """Numbered list of passages truncated to the per-passage budget.

    Truncation is deliberate — we want the semantic gist, not the full
    content. The LLM's job here is relevance ranking, not reading.
    """
    lines = [f"Query: {query}", "", "Passages:"]
    for i, p in enumerate(passages):
        snippet = p.text[:_RERANK_PASSAGE_CHAR_BUDGET]
        if len(p.text) > _RERANK_PASSAGE_CHAR_BUDGET:
            snippet += "…"
        # Flatten newlines so the numbered list stays one-per-line —
        # multi-line passage bodies would confuse the visual alignment
        # the LLM uses to map `[i]` → passage.
        snippet = snippet.replace("\n", " ")
        lines.append(f"[{i}] {snippet}")
    return "\n".join(lines)


def _parse_rerank_order(raw: str, n: int) -> list[int]:
    """Parse the LLM response into a valid permutation of `range(n)`.

    Rules:
      - `{"order": [...]}` must parse as JSON and carry a list.
      - Entries must be ints in [0, n). Non-int / out-of-range / duplicate
        indices are dropped (forgiving — partial orderings are useful).
      - Any missing indices are appended at the tail in their original
        order so MMR's ranking of the tail survives a partial response.
      - Empty-after-cleanup is not fatal; fill becomes [0..n-1], which
        equals the no-op rerank (caller can't tell a rubber-stamp from
        a legitimate "original order is correct").

    Raises json.JSONDecodeError, KeyError, or TypeError for the hard
    failure modes (non-JSON body, wrong shape); the selector catches
    those into a safe MMR-order fallback.
    """
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError("rerank response is not a JSON object")
    order = parsed["order"]
    if not isinstance(order, list):
        raise TypeError("rerank 'order' field is not a list")

    seen: set[int] = set()
    clean: list[int] = []
    for idx in order:
        if isinstance(idx, bool):  # bool is a subclass of int — reject
            continue
        if isinstance(idx, int) and 0 <= idx < n and idx not in seen:
            seen.add(idx)
            clean.append(idx)
    # Append missing indices in original order.
    for i in range(n):
        if i not in seen:
            clean.append(i)
    return clean


async def rerank_passages(
    llm_client: LLMClient,
    *,
    query: str,
    passages: list[L3Passage],
    model: str,
    user_id: UUID,
    model_source: str = "user_model",
    timeout_s: float = _RERANK_TIMEOUT_S,
) -> list[L3Passage]:
    """Listwise LLM rerank after MMR via the unified LLM gateway
    (operation=chat, no chunking — rerank prompt is bounded by
    `_rerank_max_tokens(n)` < 2K).

    The MMR output is already a strong signal-diverse list; this pass
    asks a chat model to reorder it against the user's exact query.
    Used when the project opts in via
    `extraction_config["rerank_model"]`. On any failure — gateway
    error, timeout, non-JSON body, wrong shape — falls back to the
    input order so the caller never sees an exception.

    The rerank call runs under its own `timeout_s` (default 1.0s)
    which is deliberately tighter than `context_l3_timeout_s` (2.0s).
    Rationale: if the outer L3 timeout catches a slow rerank, the
    whole `_safe_l3_passages` block returns `[]` and the user gets
    NO passages — strictly worse than the MMR result they'd have
    gotten without rerank. Enabling rerank must never degrade context
    below the no-rerank baseline, so we clamp the rerank hop itself.
    """
    n = len(passages)
    system = {"role": "system", "content": _RERANK_SYSTEM_PROMPT}
    user = {
        "role": "user",
        "content": _build_rerank_user_prompt(query, passages),
    }
    try:
        job = await asyncio.wait_for(
            llm_client.submit_and_wait(
                user_id=str(user_id),
                operation="chat",
                model_source=model_source,
                model_ref=model,
                input={
                    "messages": [system, user],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                    "max_tokens": _rerank_max_tokens(n),
                },
                chunking=None,
                job_meta={"extractor": "passage_rerank"},
                transient_retry_budget=1,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "K18.3 rerank: timed out after %.2fs model=%s — keeping MMR order",
            timeout_s, model,
        )
        return passages
    except (LLMError, LLMTransientRetryNeededError) as exc:
        logger.warning(
            "K18.3 rerank: gateway call failed model=%s err=%s — keeping MMR order",
            model, exc,
        )
        return passages

    if job.status != "completed":
        logger.warning(
            "K18.3 rerank: job ended status=%s model=%s — keeping MMR order",
            job.status, model,
        )
        return passages

    result_payload = job.result or {}
    messages_out = result_payload.get("messages") or []
    content = ""
    if isinstance(messages_out, list) and messages_out:
        first = messages_out[0]
        if isinstance(first, dict):
            content = first.get("content", "") or ""

    try:
        order = _parse_rerank_order(content, n)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "K18.3 rerank: parse failed model=%s err=%s body=%r — keeping MMR order",
            model, exc, content[:200],
        )
        return passages

    # Detect the "LLM sent total garbage, filter+fill produced no-op"
    # case and log accurately — telemetry that claims a successful
    # reorder when none happened makes perf regressions hard to spot.
    reordered = order != list(range(n))
    logger.info(
        "K18.3 rerank: %s %d passages via model=%s",
        "reordered" if reordered else "no-op (filled to original)",
        n, model,
    )
    return [passages[i] for i in order]
