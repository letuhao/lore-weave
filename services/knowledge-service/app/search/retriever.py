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
    find_passages_by_vector,
)
from app.search.hybrid_fusion import (
    BLOCK_CHAPTER_CAP,
    apply_relevance_floor,
    cap_per_chapter,
    rrf_fuse,
)

logger = logging.getLogger(__name__)

SearchMode = Literal["lexical", "semantic", "hybrid"]
Granularity = Literal["chapter", "block"]

# E5 score-floor default — DISABLED (0.0), an evidence-based choice. Calibration
# (2026-06-08, bge-m3) showed semantic cosine is compressed in [0.68, 0.82] with
# POOR separation (a negative-control query can outscore a real positive), so NO
# global cosine threshold cleanly drops junk. Real junk-rejection is the
# cross-encoder rerank leg; the floor stays opt-in via `min_relevance`.
MIN_RELEVANCE_DEFAULT = 0.0


class RetrievalResult(BaseModel):
    """The fused hits + which legs degraded (e.g. {"semantic": "not_indexed"})."""

    hits: list[dict[str, Any]]
    degraded: dict[str, str] = {}


def passage_to_hit(h: PassageSearchHit) -> dict[str, Any]:
    """Map a `:Passage` search hit → the unified raw-search hit shape.
    Passages are published canon ⇒ surface="canon"/matchType="semantic"."""
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
) -> list[dict[str, Any]]:
    """E5B — cross-encoder rerank the top `pool_n` fused candidates.

    Re-sorts by the cross-encoder score (set as each hit's `relevance`) and drops
    hits below `min_rerank_score` — the junk-rejection a global cosine floor
    couldn't do. Reranker unavailable ⇒ keep the fusion order (degraded marker)."""
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
        hits = [passage_to_hit(h) for h in raw_hits]
        await enrich_titles(hits, book_client)  # semantic hits lack titles
        return hits

    lexical_hits, semantic_hits = await asyncio.gather(_lexical(), _semantic())
    fused = rrf_fuse([lexical_hits, semantic_hits])
    # E5B: cross-encoder rerank for semantic/hybrid (where junk leaks). Lexical
    # mode is already clean (exact substring) so it skips rerank + stays fast.
    if rerank and settings.rerank_enabled and mode != "lexical" and fused:
        floor = settings.min_rerank_score if min_rerank_score is None else min_rerank_score
        fused = await apply_rerank(
            q, fused, reranker_client,
            # 2*limit: two-leg fusion yields up to 2*limit hits — rerank the
            # whole returnable pool so no distinct chapter is dropped pre-cap.
            pool_n=max(settings.rerank_top_n, 2 * limit),
            min_rerank_score=floor,
            degraded=degraded,
        )
    fused = apply_relevance_floor(fused, min_relevance)
    # chapter mode (cap=1) = one best row per chapter (navigate); block mode
    # lifts the cap (exhaustive mine). cap_per_chapter keys on chapterId alone.
    cap = 1 if granularity == "chapter" else BLOCK_CHAPTER_CAP
    fused = cap_per_chapter(fused, cap=cap)[:limit]
    return RetrievalResult(hits=fused, degraded=degraded)
