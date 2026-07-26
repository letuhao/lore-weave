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
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.config import settings

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.reranker_client import RerankerClient
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_book_client,
    get_embedding_client,
    get_grant_client,
    get_projects_repo,
    get_reranker_client,
)
from app.clients.grant_client import GrantClient, GrantLevel
from app.extraction.patterns import detect_primary_language
from app.middleware.jwt_auth import get_current_user
from app.search.hybrid_fusion import language_coverage
from app.spoiler_window import resolve_before_sort_order
from app.search.retriever import (
    MIN_RELEVANCE_DEFAULT,
    Granularity,
    SearchMode,
    Surface,
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

# KG-ML M4 — a lenient BCP-47-ish shape for the optional ?language= hint (mirrors
# book-service M3 langTagRe). A malformed value is IGNORED (falls through to the
# stored reader-language) rather than silently disabling the boost — /review-impl
# LOW. Query-language auto-detection (the last resolver tier) is only trusted for
# queries long enough to detect reliably, so a 1–2 char query can't mis-boost.
_LANG_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
_MIN_QUERY_CHARS_FOR_DETECT = 8


class RawSearchResponse(BaseModel):
    query: str
    mode: str
    results: list[dict[str, Any]]
    # Which leg degraded, if any (e.g. {"semantic": "embed_unavailable"}).
    degraded: dict[str, str] = {}
    # KG-ML M7 (C12) — reader-language coverage when a preference was resolved:
    # {reader_lang, total, in_language, partial, note}; None otherwise. Each hit
    # already carries `sourceLang` (M4), so the FE can badge per-hit too.
    coverage: dict[str, Any] | None = None


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
    surface: Surface = Query(
        "canon",
        description="canon = published content only; all = canon + on-demand-indexed "
        "drafts (owner-only — a non-owner 'all' is silently treated as 'canon').",
    ),
    language: str | None = Query(
        None,
        max_length=35,
        description="KG-ML M4 — preferred reader language (e.g. 'vi'). Soft boost, "
        "not a filter. Omit to use the caller's stored reader-language for this book, "
        "else the detected query language.",
    ),
    before_chapter_id: UUID | None = Query(
        None,
        description="W11 reader spoiler cutoff — restrict hits to passages from "
        "chapters at or before this one (by the chapter's sort_order). Omitted → no "
        "cutoff (author behavior). Unresolvable → fail-closed (no hits). The reader "
        "facade passes the reader's furthest-read chapter here (server-enforced).",
    ),
    caller: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    grant_client: GrantClient = Depends(get_grant_client),
    book_client: BookClient = Depends(get_book_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
    reranker_client: RerankerClient = Depends(get_reranker_client),
) -> RawSearchResponse:
    q = query.strip()
    if not q:
        return RawSearchResponse(query=query, mode=mode, results=[])

    # E0-3: book-scoped grant gate (>=view). A non-grantee → 404 (uniform with
    # not_indexed; no existence oracle). A collaborator then searches the OWNER's
    # book project (resolve-to-owner): get_by_book is not user-scoped, and search
    # runs as project.user_id so the owner's embedding/rerank config is used.
    if await grant_client.resolve_grant(book_id, caller) == GrantLevel.NONE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed")
    project = await projects_repo.get_by_book(book_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed",
        )

    # D-RAWSEARCH-CANON-WIRING — draft visibility is OWNER-ONLY. Search runs as
    # project.user_id (resolve-to-owner), so a collaborator's caller != owner.
    # A non-owner asking surface=all is silently downgraded to canon — drafts are
    # private-until-published, never exposed to shared users.
    effective_surface: Surface = (
        "all" if (surface == "all" and caller == project.user_id) else "canon"
    )

    # KG-ML M4 (D5) — resolve the reader-language for the soft boost:
    # explicit ?language= (well-formed) → the CALLER's stored reader-language
    # (M3) → the detected query language (long queries only) → None (no boost).
    # It's the SEARCHER's preference (caller), not the resolved-to-owner project
    # user. A malformed explicit hint is ignored so it falls through rather than
    # silently disabling the boost (/review-impl LOW).
    pref_lang = (language or "").strip() or None
    if pref_lang and not _LANG_TAG_RE.match(pref_lang):
        pref_lang = None
    if pref_lang is None:
        pref_lang = await book_client.get_reader_language(book_id, caller)
    if pref_lang is None and len(q) >= _MIN_QUERY_CHARS_FOR_DETECT:
        detected = detect_primary_language(q)
        pref_lang = detected if detected and detected != "mixed" else None

    # W11 reader spoiler cutoff — resolve the caller-supplied chapter to its
    # sort_order (fail-closed to -1 if unresolvable → no passages pass). None when
    # no cutoff was supplied, so the author/wiki path is unchanged.
    before_sort_order: int | None = None
    if before_chapter_id is not None:
        before_sort_order, _ = await resolve_before_sort_order(book_client, before_chapter_id)

    result = await run_hybrid_search(
        user_id=project.user_id,
        book_id=book_id,
        query=q,
        project=project,
        book_client=book_client,
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        mode=mode,
        granularity=granularity,
        limit=limit,
        min_relevance=min_relevance,
        rerank=rerank,
        min_rerank_score=min_rerank_score,
        surface=effective_surface,
        pref_lang=pref_lang,
        before_sort_order=before_sort_order,
    )
    coverage = language_coverage(
        [h.get("sourceLang") for h in result.hits], pref_lang
    )
    return RawSearchResponse(
        query=q, mode=mode, results=result.hits, degraded=result.degraded,
        coverage=coverage,
    )


class IndexDraftsResponse(BaseModel):
    """Result of an on-demand draft-indexing pass (D-RAWSEARCH-CANON-WIRING)."""

    indexed: int  # draft chapters whose passages were (re)written
    skipped: int  # draft chapters that produced no passages (empty/embed fail)
    chapters: int  # total draft chapters enumerated


@router.post("/books/{book_id}/index-drafts", response_model=IndexDraftsResponse)
async def index_drafts(
    book_id: UUID = Path(..., description="Book whose draft chapters to index."),
    caller: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    grant_client: GrantClient = Depends(get_grant_client),
    book_client: BookClient = Depends(get_book_client),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> IndexDraftsResponse:
    """D-RAWSEARCH-CANON-WIRING — owner-only, on-demand semantic indexing of a
    book's DRAFT (unpublished) chapters as `canon=false` passages, so a later
    `surface=all` search can surface unpublished content. Bounded cost: one
    embed pass per invoke (no per-save embedding). Re-run to refresh.

    Only enumerates `editorial_status=draft` chapters, so it never clobbers
    canon passages (canon is written only on publish); a subsequent publish
    re-ingests at the pinned revision (`canon=true`), replacing the draft
    passages for that chapter by source_id.
    """
    # Owner-only: a non-grantee gets the uniform 404 (no existence oracle); a
    # collaborator (view/edit/manage) gets 403 — drafts are the owner's private
    # workspace, not shared search surface.
    grant = await grant_client.resolve_grant(book_id, caller)
    if grant == GrantLevel.NONE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed")
    if grant != GrantLevel.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="owner_only",
        )
    project = await projects_repo.get_by_book(book_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_indexed")
    if not project.embedding_model or not project.embedding_dimension:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="project_not_indexed",
        )
    if not settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="semantic_index_unavailable",
        )

    items = await book_client.list_chapters(book_id, editorial_status="draft")
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="book_service_unavailable",
        )

    # ── review-impl P1: honour kg_exclude ──
    #
    # This endpoint enumerates DRAFT chapters, and it was the one chapter enumerator never
    # re-keyed onto the KG gate. So clicking "Index drafts" re-embedded and re-ingested
    # :Passage nodes for a chapter the owner had explicitly EXCLUDED from their knowledge
    # graph — silently undoing the retraction, and paying embedding cost on prose the user
    # asked us to forget.
    #
    # kg_exclude ships on the chapter LIST projection (WS-0.6a), so we filter on it.
    #
    # An ABSENT field is treated as not-excluded, deliberately. That is not fail-open: a
    # book-service old enough to omit the field has no kg_exclude CONCEPT, so no chapter
    # can be excluded there and including everything is correct. Defaulting absent→True
    # instead would filter out every chapter and turn this endpoint into a silent no-op on
    # exactly that deployment.
    #
    # (This endpoint is superseded by publish-independent indexing — RUN-STATE P-2 tracks
    # retiring it — but "redundant" is not "harmless", and it must not undo a retraction
    # while it still exists.)
    before = len(items)
    items = [it for it in items if not it.get("kg_exclude")]
    if (excluded := before - len(items)) > 0:
        logger.info(
            "index-drafts: skipped %d kg-excluded chapter(s) in book %s — the user "
            "removed them from their knowledge graph",
            excluded, book_id,
        )

    # Inline imports mirror the event-handler pattern (avoid circular import at
    # module load before the Neo4j driver is wired).
    from app.db.neo4j import neo4j_session
    from app.db.pool import get_knowledge_pool
    from app.extraction.passage_ingester import ingest_chapter_passages

    indexed = 0
    skipped = 0
    # KG-ML M1 (C10) — meter the on-demand draft-index embed spend too (same
    # leak class the publish/backfill paths fixed; owner-on-demand but still real
    # embedding tokens). Best-effort: pool acquisition must never break indexing,
    # so an uninitialised pool → None → metering simply skipped.
    try:
        pool = get_knowledge_pool()
    except RuntimeError:
        pool = None
    async with neo4j_session() as session:
        for item in items:
            try:
                chapter_id = UUID(str(item["chapter_id"]))
            except (KeyError, ValueError, TypeError):
                skipped += 1
                continue
            sort_order = item.get("sort_order")
            chapter_index = sort_order if isinstance(sort_order, int) else None
            try:
                res = await ingest_chapter_passages(
                    session,
                    book_client,
                    embedding_client,
                    user_id=project.user_id,
                    project_id=project.project_id,
                    book_id=book_id,
                    chapter_id=chapter_id,
                    chapter_index=chapter_index,
                    embedding_model=project.embedding_model,
                    embedding_dim=project.embedding_dimension,
                    # Live draft (chapter_blocks), NOT a pinned revision.
                    revision_id=None,
                    canon=False,
                    source_lang=item.get("original_language"),
                    pool=pool,
                )
                if res.chunks_created > 0:
                    indexed += 1
                else:
                    skipped += 1
            except Exception:
                logger.warning(
                    "index-drafts: ingest failed for chapter=%s book=%s — non-fatal",
                    chapter_id, book_id, exc_info=True,
                )
                skipped += 1
    return IndexDraftsResponse(
        indexed=indexed, skipped=skipped, chapters=len(items),
    )
