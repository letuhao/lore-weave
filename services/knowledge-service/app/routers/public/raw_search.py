"""Raw-search Phase 2 — hybrid search HTTP endpoint.

GET /v1/knowledge/books/{book_id}/search?query=&mode=&limit=

Thin HTTP wrapper over `app.search.retriever.run_hybrid_search`: this layer owns
the ownership gate (resolve the caller's project for the book → 404 `not_indexed`
if none) + query validation, then delegates the lexical+semantic+RRF+rerank
fusion to the shared in-process core (so the wiki generator runs the IDENTICAL
retrieval without HTTP). Every single-leg failure degrades to the other leg;
never a 500 on a partial outage (spec §3.4–3.5).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.reranker_client import RerankerClient
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_book_client,
    get_embedding_client,
    get_projects_repo,
    get_reranker_client,
)
from app.middleware.jwt_auth import get_current_user
from app.search.retriever import (
    MIN_RELEVANCE_DEFAULT,
    Granularity,
    SearchMode,
    run_hybrid_search,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["raw-search"],
    dependencies=[Depends(get_current_user)],
)

RAW_SEARCH_MAX_LIMIT = 100
RAW_SEARCH_QUERY_MAX_LENGTH = 1000


class RawSearchResponse(BaseModel):
    query: str
    mode: str
    results: list[dict[str, Any]]
    # Which leg degraded, if any (e.g. {"semantic": "embed_unavailable"}).
    degraded: dict[str, str] = {}


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
    # config source. No project ⇒ 404 not_indexed (FE falls back to lexical, P2b).
    # The gate lives HERE (HTTP layer); the in-process retriever takes the
    # already-resolved project and never raises.
    projects = await projects_repo.list(user_id, book_id=book_id, limit=1)
    if not projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed",
        )

    result = await run_hybrid_search(
        user_id=user_id,
        book_id=book_id,
        query=q,
        project=projects[0],
        book_client=book_client,
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        mode=mode,
        granularity=granularity,
        limit=limit,
        min_relevance=min_relevance,
        rerank=rerank,
        min_rerank_score=min_rerank_score,
    )
    return RawSearchResponse(
        query=q, mode=mode, results=result.hits, degraded=result.degraded,
    )
