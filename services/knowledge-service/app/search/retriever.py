"""Raw-search hybrid retriever — the in-process fusion core (wiki-llm M2 / §C10).

Extracted from the `GET /v1/knowledge/books/{id}/search` HTTP handler so the wiki
generator can run the SAME hybrid retrieval IN-PROCESS (no HTTP round-trip, no
JWT, no 404). `run_hybrid_search` takes an ALREADY-RESOLVED `project` (the caller
owns the ownership gate — the HTTP handler resolves book→project + raises 404; the
wiki orchestrator passes its job's project) and NEVER raises an HTTPException: a
`not_indexed`/degraded leg becomes a marker in `RetrievalResult.degraded`, never a
status code. The fusion logic (lexical + semantic gather → RRF → cross-encoder
rerank → relevance floor → per-chapter cap) is identical to the shipped endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.reranker_client import RerankerClient
from app.config import settings
from app.context.query_embedding import embed_query_cached
from app.db.models import Project
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    PassageSearchHit,
    find_passages_by_fulltext,
    find_passages_by_vector,
)
from app.search.hybrid_fusion import (
    BLOCK_CHAPTER_CAP,
    apply_language_preference,
    apply_relevance_floor,
    cap_per_chapter,
    rrf_fuse,
)

logger = logging.getLogger(__name__)

SearchMode = Literal["lexical", "semantic", "hybrid"]
Granularity = Literal["chapter", "block"]
# D-RAWSEARCH-CANON-WIRING — which passages the semantic leg may return.
# "canon" (default) = published content only; "all" = canon + on-demand-indexed
# drafts (owner-only — the HTTP layer downgrades a non-owner "all" to "canon").
Surface = Literal["canon", "all"]

# E5 score-floor default — DISABLED (0.0), an evidence-based choice. Calibration
# (2026-06-08, bge-m3) showed semantic cosine is compressed in [0.68, 0.82] with
# POOR separation (a negative-control query can outscore a real positive), so NO
# global cosine threshold cleanly drops junk. Real junk-rejection is the
# cross-encoder rerank leg; the floor stays opt-in via `min_relevance`.
MIN_RELEVANCE_DEFAULT = 0.0

# KG-ML M6 (D12) — CJK codepoint ranges. A query containing any of these can't be
# served well by the book-service pg_trgm lexical leg (trigram is noise on CJK +
# a GIN-trigram index can't accelerate a 2-char term), so we add the Neo4j
# `cjk`-analyzed full-text leg over :Passage. Covers CJK Unified (+ Ext-A),
# Hiragana/Katakana, and Hangul — the scripts the bi-gram `cjk` analyzer targets.
_CJK_RE = re.compile(
    r"[㐀-䶿一-鿿぀-ヿ가-힯豈-﫿]"
)


def query_has_cjk(text: str) -> bool:
    """True when the query contains a CJK/Japanese/Korean character — the signal
    that the trigram lexical leg will under-recall and the cjk full-text leg
    should run. Operates on the raw query (a bare proper noun is too short for
    reliable language detection, so we test codepoints, not detected language)."""
    return bool(_CJK_RE.search(text or ""))


class RetrievalResult(BaseModel):
    """The fused hits + which legs degraded (e.g. {"semantic": "not_indexed"})."""

    hits: list[dict[str, Any]]
    degraded: dict[str, str] = {}


def passage_to_hit(h: PassageSearchHit, *, match_type: str = "semantic") -> dict[str, Any]:
    """Map a `:Passage` search hit → the unified raw-search hit shape.
    `surface` reflects the node's canon flag (D-RAWSEARCH-CANON-WIRING):
    canon passages → "canon", on-demand-indexed drafts → "draft". Legacy
    nodes (no flag) read as canon via `Passage.canon`'s default.

    KG-ML M6 — `match_type` records WHICH passage leg produced the hit: the
    vector leg → "semantic" (default), the cjk full-text leg → "lexical". Both
    read `:Passage` nodes, so without this they'd both report "semantic" (the
    cosmetic mislabel D-KG-ML-M6-MATCHTYPE)."""
    p = h.passage
    return {
        "chapterId": p.source_id,
        "chapterTitle": None,
        "sortOrder": p.chapter_index if p.chapter_index is not None else 0,
        "surface": "canon" if p.canon else "draft",
        "matchType": match_type,
        # KG-ML M4 — source language of this passage (zh original / vi dual-index),
        # for language-aware ranking. "mixed" matches any reader pref.
        "sourceLang": p.source_lang,
        "score": h.raw_score,
        "relevance": h.raw_score,  # E5: native cosine (0–1) for the score-floor
        "snippet": p.text,
        "highlights": [],
        "location": {
            "chunkIndex": p.chunk_index,
            # P3-C: real chapter block where this chunk starts → precise jump.
            "blockIndex": p.block_index,
            "headingContext": None,
            "charStart": 0,
            "charEnd": 0,
        },
    }


async def enrich_titles(hits: list[dict[str, Any]], book_client: BookClient) -> None:
    """Populate `chapterTitle` on semantic hits (D-RAWSEARCH-P2-SEMANTIC-TITLES).
    Lexical hits already carry titles; passages don't. One batched call;
    best-effort — {} on failure leaves titles null (FE falls back to #sortOrder)."""
    ids: set[UUID] = set()
    for h in hits:
        try:
            ids.add(UUID(str(h["chapterId"])))
        except (ValueError, TypeError, KeyError):
            pass
    if not ids:
        return
    titles = await book_client.get_chapter_titles(list(ids))
    if not titles:
        return
    for h in hits:
        try:
            title = titles.get(UUID(str(h["chapterId"])))
        except (ValueError, TypeError, KeyError):
            title = None
        if title:
            h["chapterTitle"] = title


async def apply_rerank(
    q: str,
    fused: list[dict[str, Any]],
    reranker: RerankerClient,
    *,
    pool_n: int,
    min_rerank_score: float,
    degraded: dict[str, str],
    user_id: str,
    model_source: str,
    model_ref: str,
) -> list[dict[str, Any]]:
    """E5B — cross-encoder rerank the top `pool_n` fused candidates.

    Re-sorts by the cross-encoder score (set as each hit's `relevance`) and drops
    hits below `min_rerank_score` — the junk-rejection a global cosine floor
    couldn't do. Reranker unavailable ⇒ keep the fusion order (degraded marker).
    Routed through the project's BYOK rerank model (D-RERANK-NOT-BYOK)."""
    if not fused:
        return fused
    cand = fused[:pool_n]
    docs = [str(h.get("snippet") or "") for h in cand]
    scores = await reranker.rerank(
        q, docs, user_id=user_id, model_source=model_source, model_ref=model_ref,
    )
    if scores is None:
        degraded["rerank"] = "unavailable"
        return fused
    by_index = {int(s["index"]): float(s["relevance_score"]) for s in scores if "index" in s}
    reranked: list[dict[str, Any]] = []
    for i, h in enumerate(cand):
        sc = by_index.get(i)
        if sc is None or sc < min_rerank_score:
            continue
        reranked.append({**h, "relevance": sc})
    reranked.sort(key=lambda h: h["relevance"], reverse=True)
    return reranked


def _visible_within_window(hit: dict[str, Any], before_sort_order: int) -> bool:
    """W11-M1 reader spoiler predicate for a book-service LEXICAL hit dict, whose
    ``sortOrder`` is None-preserving (a hit without a real chapter index has no /
    None ``sortOrder`` and is dropped). A cutoff < 0 (the fail-closed sentinel —
    reading position unresolvable) admits NOTHING.

    NOTE: do NOT use this on a ``passage_to_hit`` dict — that path coerces an
    unknown ``chapter_index`` (None) to ``sortOrder`` 0, which would FAIL OPEN
    (an un-ordered canon passage read as chapter 0). Passage legs are windowed on
    the raw ``chapter_index`` via ``_window_raw_passages`` BEFORE ``passage_to_hit``."""
    if before_sort_order < 0:
        return False
    so = hit.get("sortOrder")
    return isinstance(so, int) and so <= before_sort_order


def _window_dict_hits(
    hits: list[dict[str, Any]], before_sort_order: int | None
) -> list[dict[str, Any]]:
    """Filter book-service lexical hit dicts to the reader's window (no-op when the
    caller supplies no cutoff — the author/wiki path)."""
    if before_sort_order is None:
        return hits
    return [h for h in hits if _visible_within_window(h, before_sort_order)]


def _window_raw_passages(raw_hits: list, before_sort_order: int | None) -> list:
    """Filter raw ``PassageSearchHit``s to the reader's window on the passage's OWN
    ``chapter_index`` — the None-preserving source, BEFORE ``passage_to_hit``'s
    None→0 coercion can fail open. A passage with an unknown ``chapter_index`` is
    DROPPED (fail-closed), matching spec §4.3. No cutoff (None) → no-op; an
    unresolvable position (< 0) → nothing passes."""
    if before_sort_order is None:
        return raw_hits
    if before_sort_order < 0:
        return []
    return [
        h for h in raw_hits
        if h.passage.chapter_index is not None
        and h.passage.chapter_index <= before_sort_order
    ]


async def run_hybrid_search(
    *,
    user_id: UUID,
    book_id: UUID,
    query: str,
    project: Project,
    book_client: BookClient,
    embedding_client: EmbeddingClient,
    reranker_client: RerankerClient,
    mode: SearchMode = "hybrid",
    granularity: Granularity = "chapter",
    limit: int = 20,
    min_relevance: float = MIN_RELEVANCE_DEFAULT,
    rerank: bool = True,
    min_rerank_score: float | None = None,
    surface: Surface = "canon",
    pref_lang: str | None = None,
    before_sort_order: int | None = None,
) -> RetrievalResult:
    """Run the hybrid lexical+semantic search for one already-resolved project.

    Pure of the HTTP layer: `project` is supplied by the caller (who owns the
    ownership gate), and a degraded/empty leg returns a marker rather than
    raising. `query` must be non-empty/stripped (the caller validates). Mirrors
    the shipped `search_book` fusion exactly so the two paths can't drift."""
    q = query.strip()
    degraded: dict[str, str] = {}
    if not q:
        return RetrievalResult(hits=[], degraded=degraded)

    async def _lexical() -> list[dict[str, Any]]:
        if mode == "semantic":
            return []
        hits = await book_client.lexical_search(
            book_id, q, limit=limit, granularity=granularity, surface=surface,
        )
        if hits is None:
            degraded["lexical"] = "book_service_unavailable"
            return []
        # W11 reader spoiler cutoff — lexical hits carry a None-preserving sortOrder.
        return _window_dict_hits(hits, before_sort_order)

    async def _cjk_lexical() -> list[dict[str, Any]]:
        # KG-ML M6 (D12) — the CJK-tokenized lexical leg. Only for hybrid/lexical
        # modes AND only when the query carries CJK (else it's pure overhead —
        # the trigram leg already serves Latin scripts well). Searches the same
        # :Passage nodes as the semantic leg via the `cjk` full-text index, so it
        # needs no embedding model (works even on an un-embedded project). Any
        # failure (index missing on a not-yet-migrated Neo4j, query error) →
        # degraded marker, never a raised error.
        if mode == "semantic" or not query_has_cjk(q):
            return []
        try:
            async with neo4j_session() as session:
                raw_hits = await find_passages_by_fulltext(
                    session,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    query=q,
                    source_type="chapter",
                    limit=limit,
                    include_drafts=(surface == "all"),
                )
        except Exception:
            degraded["cjk_lexical"] = "unavailable"
            return []
        # W11 reader spoiler cutoff — window on the raw chapter_index (None-preserving)
        # BEFORE passage_to_hit coerces an unknown chapter to sortOrder 0 (fail-open).
        raw_hits = _window_raw_passages(raw_hits, before_sort_order)
        hits = [passage_to_hit(h, match_type="lexical") for h in raw_hits]
        await enrich_titles(hits, book_client)  # passage hits lack titles
        return hits

    async def _semantic() -> list[dict[str, Any]]:
        if mode == "lexical":
            return []
        if not project.embedding_model or not project.embedding_dimension:
            degraded["semantic"] = "not_indexed"
            return []
        if project.embedding_dimension not in SUPPORTED_PASSAGE_DIMS:
            degraded["semantic"] = "unsupported_dim"
            return []
        vector = await embed_query_cached(
            embedding_client,
            user_id=user_id,
            project_id=str(project.project_id),
            embedding_model=project.embedding_model,
            message=q,
        )
        if not vector:
            degraded["semantic"] = "embed_unavailable"
            return []
        try:
            async with neo4j_session() as session:
                raw_hits = await find_passages_by_vector(
                    session,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    query_vector=vector,
                    dim=project.embedding_dimension,
                    embedding_model=project.embedding_model,
                    source_type="chapter",
                    limit=limit,
                    include_vectors=False,
                    # D-RAWSEARCH-CANON-WIRING — owner-only "all" lets drafts through.
                    include_drafts=(surface == "all"),
                )
        except ValueError:
            degraded["semantic"] = "embedding_dim_mismatch"
            return []
        # W11 reader spoiler cutoff — window on the raw chapter_index (None-preserving)
        # BEFORE passage_to_hit coerces an unknown chapter to sortOrder 0 (fail-open).
        raw_hits = _window_raw_passages(raw_hits, before_sort_order)
        hits = [passage_to_hit(h) for h in raw_hits]
        await enrich_titles(hits, book_client)  # semantic hits lack titles
        return hits

    lexical_hits, cjk_hits, semantic_hits = await asyncio.gather(
        _lexical(), _cjk_lexical(), _semantic()
    )
    # KG-ML M6: the CJK leg fuses as a third RRF input — additive (empty for
    # non-CJK queries, so Latin-script retrieval is byte-identical to pre-M6).
    # W11-M1 (spec §4.3) — the reader spoiler cutoff is applied per-LEG above, on
    # each leg's None-preserving chapter source (raw chapter_index for the passage
    # legs, sortOrder for the lexical leg), so a future/unknown-chapter hit never
    # enters fusion — it can't skew RRF, consume a rerank/limit slot, or hide a
    # visible chapter. Author/wiki callers pass before_sort_order=None → no-op.
    fused = rrf_fuse([lexical_hits, cjk_hits, semantic_hits])
    # E5B: cross-encoder rerank for semantic/hybrid (where junk leaks). Lexical
    # mode is already clean (exact substring) so it skips rerank + stays fast.
    # D-RERANK-NOT-BYOK: rerank is OPTIONAL and BYOK. Resolve the effective model =
    # the project's per-project rerank model, else the user's DEFAULT rerank model
    # (provider-registry user_default_models) — the default restores the UX the
    # removed RERANK_URL/_MODEL .env config gave. No model anywhere ⇒ skip (keep
    # fusion order, mark degraded).
    want_rerank = rerank and settings.rerank_enabled and mode != "lexical" and bool(fused)
    effective_ref = project.rerank_model
    effective_source = project.rerank_model_source
    if want_rerank and not effective_ref:
        default_ref = await reranker_client.get_default_rerank(str(user_id))
        if default_ref:
            effective_ref, effective_source = default_ref, "user_model"
    if want_rerank and effective_ref:
        floor = settings.min_rerank_score if min_rerank_score is None else min_rerank_score
        fused = await apply_rerank(
            q, fused, reranker_client,
            # 2*limit: two-leg fusion yields up to 2*limit hits — rerank the
            # whole returnable pool so no distinct chapter is dropped pre-cap.
            pool_n=max(settings.rerank_top_n, 2 * limit),
            min_rerank_score=floor,
            degraded=degraded,
            user_id=str(user_id),
            model_source=effective_source,
            model_ref=effective_ref,
        )
    elif want_rerank and not effective_ref:
        degraded["rerank"] = "not_configured"
    fused = apply_relevance_floor(fused, min_relevance)
    # KG-ML M4 (D5) — language preference is the FINAL ordering pass: a stable
    # matched-first partition over whatever order rerank/RRF produced (scale-
    # independent, so it works WITH rerank — a pre-rerank additive boost was
    # discarded by the cross-encoder re-sort; /review-impl HIGH). Runs BEFORE the
    # per-chapter cap so the reader's language wins the chapter's single slot.
    # No-op when pref_lang is None (wiki in-process path unaffected).
    if pref_lang:
        fused = apply_language_preference(fused, pref_lang)
    # chapter mode (cap=1) = one best row per chapter (navigate); block mode
    # lifts the cap (exhaustive mine). cap_per_chapter keys on chapterId alone.
    cap = 1 if granularity == "chapter" else BLOCK_CHAPTER_CAP
    fused = cap_per_chapter(fused, cap=cap)[:limit]
    return RetrievalResult(hits=fused, degraded=degraded)
