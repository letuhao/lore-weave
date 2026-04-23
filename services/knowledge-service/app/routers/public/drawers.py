"""K19e.5 — Public drawer (passage) search endpoint.

GET /v1/knowledge/drawers/search?project_id=&query=&limit=

Semantic search over the user's project passages (":Passage" nodes).
Embeds the query server-side using the project's configured embedding
model, then runs the K18.3 vector search. Results come back as
``DrawerSearchHit`` objects — the stored vector stays on the server.

Cycle γ-a ships the minimal BE surface: project_id + query + limit.
Source-type filter (chapter / chat / glossary) is deferred as
D-K19e-γa-01; no query-embedding cache (select_l3_passages has one,
but drawer search has a different access pattern — user-driven search
rarely repeats exactly-matching queries in a 30s window).
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    find_passages_by_vector,
)
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_embedding_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["drawers"],
    dependencies=[Depends(get_current_user)],
)


# Cap chosen to match the K18.3 pool_size_fine default — a user
# scanning drawers doesn't need more than 100 at a time, and the
# vector-index oversample factor (10×) keeps server-side work bounded.
DRAWERS_MAX_LIMIT = 100
DRAWERS_QUERY_MAX_LENGTH = 1000


class DrawerSearchHit(BaseModel):
    """Public projection of a ``:Passage`` search hit.

    The stored vector is omitted (it's on ``PassageSearchHit.vector``
    but only when ``include_vectors=True``; drawer search leaves it
    off). ``user_id`` is omitted because the caller already knows
    their own id — one less leak surface.
    """

    id: str
    project_id: str | None
    source_type: str
    source_id: str
    chunk_index: int
    text: str
    is_hub: bool
    chapter_index: int | None
    created_at: datetime | None
    raw_score: float


class DrawerSearchResponse(BaseModel):
    hits: list[DrawerSearchHit]
    # Surfaced so the FE can show "searched via X" for transparency
    # and to distinguish the "not indexed" branch (null) from a
    # zero-hit live search.
    embedding_model: str | None


@router.get("/drawers/search", response_model=DrawerSearchResponse)
async def search_drawers(
    project_id: UUID = Query(
        ...,
        description=(
            "Project scope. Required — passages are project-scoped and "
            "cross-project search is a different retrieval pattern."
        ),
    ),
    query: str = Query(
        ...,
        min_length=1,
        max_length=DRAWERS_QUERY_MAX_LENGTH,
        description="Free-text semantic search query.",
    ),
    limit: int = Query(40, ge=1, le=DRAWERS_MAX_LIMIT),
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> DrawerSearchResponse:
    """K19e.5 — semantic search over project passages.

    Behaviour contract:
      - 404 when ``project_id`` doesn't exist or belongs to another
        user (KSA §6.4 anti-leak: cross-user is indistinguishable
        from "missing").
      - 200 with ``{hits: [], embedding_model: null}`` when the
        project has no embedding model configured yet. The FE should
        surface this as "not indexed yet", not an error.
      - 200 with ``{hits: [], embedding_model: "..."}`` when the
        search returns zero matches — still includes the model so
        the FE can show what was searched.
      - 502 with ``{error_code: "provider_error"}`` on
        ``EmbeddingError`` from the BYOK provider.
      - 502 with ``{error_code: "embedding_dim_mismatch"}`` when the
        live embedding's length disagrees with the project's stored
        ``embedding_dimension`` (user changed model out-of-band).
    """
    # Whitespace-only query is semantically empty. Short-circuit
    # before burning a provider-registry call.
    if not query.strip():
        return DrawerSearchResponse(hits=[], embedding_model=None)

    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    if (
        project.embedding_model is None
        or project.embedding_dimension is None
    ):
        return DrawerSearchResponse(hits=[], embedding_model=None)

    if project.embedding_dimension not in SUPPORTED_PASSAGE_DIMS:
        logger.warning(
            "K19e.5: project %s has unsupported embedding_dim=%s; "
            "returning empty",
            project_id, project.embedding_dimension,
        )
        return DrawerSearchResponse(
            hits=[], embedding_model=project.embedding_model,
        )

    try:
        embed_result = await embedding_client.embed(
            user_id=user_id,
            model_source="user_model",
            model_ref=project.embedding_model,
            texts=[query],
        )
    except EmbeddingError as exc:
        logger.warning(
            "K19e.5: embedding failed project=%s model=%s: %s",
            project_id, project.embedding_model, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "provider_error",
                "message": str(exc),
                # Review-impl L3: propagate the retryable hint so the
                # FE can decide between "show retry button" vs "tell
                # user to fix their model config". Timeout + 5xx set
                # retryable=True; a bad model ref or 4xx sets False.
                "retryable": bool(getattr(exc, "retryable", False)),
            },
        )

    if not embed_result.embeddings or not embed_result.embeddings[0]:
        # Provider returned 200 OK but either empty outer list OR an
        # empty inner vector — both are "the provider responded with
        # no useful data" and should NOT escalate to a confusing
        # dim_mismatch 502. Treat as empty search.
        return DrawerSearchResponse(
            hits=[], embedding_model=project.embedding_model,
        )
    query_vector = embed_result.embeddings[0]

    try:
        async with neo4j_session() as session:
            raw_hits = await find_passages_by_vector(
                session,
                user_id=str(user_id),
                project_id=str(project_id),
                query_vector=query_vector,
                dim=project.embedding_dimension,
                embedding_model=project.embedding_model,
                limit=limit,
                include_vectors=False,
            )
    except ValueError as exc:
        # Defensive catch for the "query_vector length does not match
        # dim" path: a user who changed their embedding model in
        # provider-registry without re-running the benchmark can land
        # here. 502 is the right code (upstream provider returned a
        # vector of unexpected shape, from our perspective).
        logger.warning(
            "K19e.5: embedding dim mismatch project=%s stored=%s live=%s",
            project_id, project.embedding_dimension, len(query_vector),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "embedding_dim_mismatch",
                "message": str(exc),
            },
        )

    hits = [
        DrawerSearchHit(
            id=h.passage.id,
            project_id=h.passage.project_id,
            source_type=h.passage.source_type,
            source_id=h.passage.source_id,
            chunk_index=h.passage.chunk_index,
            text=h.passage.text,
            is_hub=h.passage.is_hub,
            chapter_index=h.passage.chapter_index,
            created_at=h.passage.created_at,
            raw_score=h.raw_score,
        )
        for h in raw_hits
    ]
    return DrawerSearchResponse(
        hits=hits, embedding_model=project.embedding_model,
    )
