"""Raw-search Phase 2 — hybrid search orchestrator.

GET /v1/knowledge/books/{book_id}/search?query=&mode=&limit=

Fuses the LEXICAL leg (book-service `/internal/.../lexical-search`, draft
surface) with the SEMANTIC leg (Neo4j `:Passage` vectors, canon surface) via
RRF. The caller's project for the book is the ownership gate AND the embedding
config source — no project ⇒ 404 `not_indexed` (FE falls back to the
book-service lexical endpoint). Every single-leg failure degrades to the other
leg; never a 500 on a partial outage (spec §3.4–3.5).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.reranker_client import RerankerClient
from app.config import settings
from app.context.query_embedding import embed_query_cached
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    PassageSearchHit,
    find_passages_by_vector,
)
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_book_client,
    get_embedding_client,
    get_projects_repo,
    get_reranker_client,
)
from app.middleware.jwt_auth import get_current_user
from app.search.hybrid_fusion import (
    BLOCK_CHAPTER_CAP,
    PER_CHAPTER_CAP,
    apply_relevance_floor,
    cap_per_chapter,
    rrf_fuse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["raw-search"],
    dependencies=[Depends(get_current_user)],
)

RAW_SEARCH_MAX_LIMIT = 100
RAW_SEARCH_QUERY_MAX_LENGTH = 1000
# E5 score-floor default — DISABLED (0.0), and that is an evidence-based choice.
# Calibration probe (2026-06-08, bge-m3 on the eval corpus) showed semantic
# cosine is compressed in [0.68, 0.82] with POOR separation: a negative-control
# query (封神榜 0.733) outscores a real positive (a paraphrase at 0.706). So NO
# global cosine threshold cleanly drops junk without also dropping true hits —
# a floor would be lossy. The calibrated `relevance` field still ships (real
# cosine / lexical similarity, useful for display + opt-in filtering via the
# `min_relevance` query param). Real junk-rejection needs a reranker /
# per-query score normalisation → D-RAWSEARCH-E5B-RERANK.
MIN_RELEVANCE_DEFAULT = 0.0

SearchMode = Literal["lexical", "semantic", "hybrid"]
Granularity = Literal["chapter", "block"]


class RawSearchResponse(BaseModel):
    query: str
    mode: str
    results: list[dict[str, Any]]
    # Which leg degraded, if any (e.g. {"semantic": "embed_unavailable"}).
    degraded: dict[str, str] = {}


def _passage_to_hit(h: PassageSearchHit) -> dict[str, Any]:
    """Map a `:Passage` search hit → the unified raw-search hit shape.
    Passages are published canon ⇒ surface="canon"/matchType="semantic".
    `chapterTitle` is null in P2a (semantic-title enrichment deferred,
    D-RAWSEARCH-P2-SEMANTIC-TITLES); `highlights` empty (no exact span)."""
    p = h.passage
    return {
        "chapterId": p.source_id,
        "chapterTitle": None,
        "sortOrder": p.chapter_index if p.chapter_index is not None else 0,
        "surface": "canon",
        "matchType": "semantic",
        "score": h.raw_score,
        "relevance": h.raw_score,  # E5: native cosine (0–1) for the score-floor
        "snippet": p.text,
        "highlights": [],
        "location": {
            "chunkIndex": p.chunk_index,
            # P3-C: real chapter block where this chunk starts → FE jumps to
            # source precisely (reader scrolls to ?block=N), like lexical hits.
            "blockIndex": p.block_index,
            "headingContext": None,
            "charStart": 0,
            "charEnd": 0,
        },
    }


async def _enrich_titles(hits: list[dict[str, Any]], book_client: BookClient) -> None:
    """Populate `chapterTitle` on semantic hits (D-RAWSEARCH-P2-SEMANTIC-TITLES).
    Lexical hits already carry titles from book-service; passages don't. One
    batched `get_chapter_titles` call; best-effort — it returns {} on failure,
    so titles stay null (FE falls back to #sortOrder)."""
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


async def _apply_rerank(
    q: str,
    fused: list[dict[str, Any]],
    reranker: RerankerClient,
    *,
    pool_n: int,
    min_rerank_score: float,
    degraded: dict[str, str],
) -> list[dict[str, Any]]:
    """E5B — cross-encoder rerank the top `pool_n` fused candidates.

    Re-sorts by the cross-encoder score (set as each hit's `relevance`) and
    drops hits below `min_rerank_score` — this is the junk-rejection a global
    cosine floor couldn't do (the candidates beyond `pool_n` are dropped, so a
    fully-off-topic query that scores everything low returns nothing).
    Reranker unavailable ⇒ keep the fusion order untouched (degraded marker)."""
    if not fused:
        return fused
    cand = fused[:pool_n]
    docs = [str(h.get("snippet") or "") for h in cand]
    scores = await reranker.rerank(q, docs)
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


@router.get("/books/{book_id}/search", response_model=RawSearchResponse)
async def search_book(
    book_id: UUID = Path(..., description="Book to search."),
    query: str = Query(..., min_length=1, max_length=RAW_SEARCH_QUERY_MAX_LENGTH),
    mode: SearchMode = Query("hybrid"),
    limit: int = Query(20, ge=1, le=RAW_SEARCH_MAX_LIMIT),
    granularity: Granularity = Query("chapter"),
    min_relevance: float = Query(MIN_RELEVANCE_DEFAULT, ge=0.0, le=1.0),
    rerank: bool = Query(True),
    min_rerank_score: float | None = Query(None, ge=0.0, le=1.0),
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    book_client: BookClient = Depends(get_book_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    reranker_client: RerankerClient = Depends(get_reranker_client),
) -> RawSearchResponse:
    q = query.strip()
    if not q:
        return RawSearchResponse(query=query, mode=mode, results=[])

    # Resolve the caller's project for this book — ownership gate + embedding
    # config. No project ⇒ 404 not_indexed (FE falls back to lexical, P2b).
    projects = await projects_repo.list(user_id, book_id=book_id, limit=1)
    if not projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed",
        )
    project = projects[0]
    degraded: dict[str, str] = {}

    async def _lexical() -> list[dict[str, Any]]:
        if mode == "semantic":
            return []
        hits = await book_client.lexical_search(
            book_id, q, limit=limit, granularity=granularity,
        )
        if hits is None:
            degraded["lexical"] = "book_service_unavailable"
            return []
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
                )
        except ValueError:
            degraded["semantic"] = "embedding_dim_mismatch"
            return []
        hits = [_passage_to_hit(h) for h in raw_hits]
        await _enrich_titles(hits, book_client)  # semantic hits lack titles
        return hits

    lexical_hits, semantic_hits = await asyncio.gather(_lexical(), _semantic())
    # E5: score-floor drops low-relevance junk (negative-control queries);
    # granularity sets the per-chapter cap (chapter=1 best block; block=lift cap
    # for exhaustive mining). RRF still ranks; `relevance` survives fusion.
    fused = rrf_fuse([lexical_hits, semantic_hits])
    # E5B: cross-encoder rerank for semantic/hybrid (where junk leaks). Lexical
    # mode is already clean (exact substring) so it skips rerank + stays fast.
    if (
        rerank
        and settings.rerank_enabled
        and mode != "lexical"
        and fused
    ):
        floor = settings.min_rerank_score if min_rerank_score is None else min_rerank_score
        fused = await _apply_rerank(
            q, fused, reranker_client,
            # 2*limit: two-leg fusion yields up to 2*limit hits — rerank the
            # whole returnable pool so no distinct chapter is dropped pre-cap
            # (review-impl LOW-1).
            pool_n=max(settings.rerank_top_n, 2 * limit),
            min_rerank_score=floor,
            degraded=degraded,
        )
    fused = apply_relevance_floor(fused, min_relevance)
    # `cap_per_chapter` keys on chapterId ALONE (not surface), so chapter mode
    # (cap=1) yields exactly one row per chapter even in hybrid — if a chapter
    # has both a lexical(draft) and semantic(canon) hit, the higher-RRF one wins.
    # That's the intended navigate shape (one best result per chapter); use
    # granularity=block to see every hit (all surfaces, all blocks).
    cap = 1 if granularity == "chapter" else BLOCK_CHAPTER_CAP
    fused = cap_per_chapter(fused, cap=cap)[:limit]
    return RawSearchResponse(query=q, mode=mode, results=fused, degraded=degraded)
