"""Per-book enrichment PROFILE authoring API (C3 / slice 0d, T4/T5/T7).

The de-bias profile (worldview / language / era / voice + per-kind dimension
overrides) is read at runtime by C1's prompt builders, dimension resolver, and
anachronism check. C1 shipped the table + reader; this router lets an author
AUTHOR it:

  GET  /v1/lore-enrichment/books/{book_id}/profile          — read (neutral default if unset)
  PUT  /v1/lore-enrichment/books/{book_id}/profile          — upsert (profile_source='manual')
  POST /v1/lore-enrichment/books/{book_id}/profile/suggest  — AI-suggest a DRAFT (not persisted)

Scope (Q3): the profile table is keyed by book_id only (a book has one owner), so
authorization is decided against the book-service projection ``owner_user_id`` —
the TRUTH source, mirroring the promote path — NOT a client claim. A non-owner gets
403; a missing book 404; no token 401. Suggest's LLM call resolves the model by a
caller-supplied ``model_ref`` (BYOK) — NO hardcoded model name. The KG summary is
best-effort (an empty/down graph degrades to book-only). H0 is untouched — this
writes the PROFILE, never canon.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.eval import require_internal_token
from app.api.principal import Principal, require_principal
from app.clients.book import BookClient, BookProjection, BookServiceError
from app.compose.compose_task import create_compose_task, enqueue_compose_task
from app.config import settings
from app.db.book_profile import (
    BookProfile,
    get_book_profile,
    upsert_book_profile,
    validate_dimension_overrides,
)
from app.deps import get_db

router = APIRouter(prefix="/v1/lore-enrichment/books", tags=["profile"])
logger = logging.getLogger("lore_enrichment.book_profile")


class MarkerIn(BaseModel):
    term: str = Field(min_length=1)
    reason: str = ""


class ProfileBody(BaseModel):
    worldview: str = ""
    language: str = "auto"
    era_policy: str | None = None
    voice: str | None = None
    anachronism_markers: list[MarkerIn] = Field(default_factory=list)
    dimension_overrides: dict = Field(default_factory=dict)


class SuggestBody(BaseModel):
    project_id: UUID
    suggest_model_ref: UUID  # provider-registry user_model id (NO model name)
    sample_chapter_ids: list[UUID] = Field(default_factory=list, max_length=8)


def _profile_view(p: BookProfile) -> dict:
    return {
        "book_id": str(p.book_id) if p.book_id else None,
        "worldview": p.worldview,
        "language": p.language,
        "era_policy": p.era_policy,
        "voice": p.voice,
        "anachronism_markers": [{"term": t, "reason": r} for t, r in p.anachronism_markers],
        "anachronism_enabled": p.anachronism_enabled,
        "dimension_overrides": p.dimension_overrides,
        "profile_source": p.profile_source,
    }


def _require_user(principal: Principal) -> UUID:
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    return principal.user_id


async def _projection_owned(
    book_client: BookClient, *, book_id: UUID, user_id: UUID
) -> BookProjection:
    """Read the book projection and authorize the acting user as its owner.

    404 → book not found; 403 → not the owner; transient → 502/503. The owner is
    the book-service truth source (not a client claim), matching promote."""
    try:
        proj = await book_client.get_projection(book_id=book_id)
    except BookServiceError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="book not found")
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=f"book read failed: {exc}")
    if proj.owner_user_id is None or proj.owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the book owner")
    return proj


@router.get("/{book_id}/profile")
async def get_profile(
    book_id: UUID,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """The book's enrichment profile (neutral default if unset). Owner-only."""
    user_id = _require_user(principal)
    book_client = BookClient(
        base_url=settings.book_service_url, internal_token=settings.internal_service_token
    )
    try:
        await _projection_owned(book_client, book_id=book_id, user_id=user_id)
    finally:
        await book_client.aclose()
    profile = await get_book_profile(pool, book_id)
    return _profile_view(profile)


@router.put("/{book_id}/profile")
async def put_profile(
    book_id: UUID,
    body: ProfileBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Upsert the book's profile (sets profile_source='manual'). Validates the
    dimension overrides BEFORE persist → 400 on malformed. Owner-only.

    CONTRACT — this is a FULL REPLACE (REST PUT semantics): every field is written
    from the body, so an OMITTED field is reset to its default (e.g. omitting
    ``anachronism_markers`` clears them → anachronism check OFF). The client (FE
    Settings, slice 0e) MUST GET-then-PUT the whole profile to avoid silently
    wiping the seeded markers / overrides. Pinned by test_put_profile_full_replace."""
    user_id = _require_user(principal)
    # Authorize BEFORE processing the body — a non-owner gets 403 regardless of
    # what they sent (auth precedes validation).
    book_client = BookClient(
        base_url=settings.book_service_url, internal_token=settings.internal_service_token
    )
    try:
        await _projection_owned(book_client, book_id=book_id, user_id=user_id)
    finally:
        await book_client.aclose()
    try:
        clean_overrides = validate_dimension_overrides(body.dimension_overrides)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid dimension_overrides: {exc}",
        )
    markers = tuple((m.term, m.reason) for m in body.anachronism_markers)
    profile = await upsert_book_profile(
        pool, book_id,
        worldview=body.worldview, language=body.language,
        era_policy=body.era_policy, voice=body.voice,
        anachronism_markers=markers, dimension_overrides=clean_overrides,
        profile_source="manual",
    )
    return _profile_view(profile)


@router.post("/{book_id}/profile/suggest", status_code=status.HTTP_202_ACCEPTED)
async def suggest_book_profile(
    book_id: UUID,
    body: SuggestBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """AI-suggest a profile DRAFT (worldview/language/era/voice + per-kind
    dimension overrides) from the book metadata + sample chapters + KG summary.

    Phase 3 M2 — OFF the request path: the owner check stays synchronous (a
    non-owner gets 403 immediately, before any task is created), then a 'pending'
    compose task is created + a resume-stream trigger enqueued; returns 202 +
    task_id. The resume worker runs the LLM pipeline (model by BYOK model_ref);
    GET /v1/lore-enrichment/compose-tasks/{task_id} polls for the draft. Does NOT
    persist the profile (the author edits the draft + PUTs)."""
    user_id = _require_user(principal)
    # Owner check on the request path — a non-owner never creates a task.
    book_client = BookClient(
        base_url=settings.book_service_url, internal_token=settings.internal_service_token
    )
    try:
        await _projection_owned(book_client, book_id=book_id, user_id=user_id)
    finally:
        await book_client.aclose()

    task_id = await create_compose_task(
        pool,
        kind="profile_suggest",
        user_id=str(user_id),
        project_id=str(body.project_id),
        book_id=str(book_id),
        request={
            "user_id": str(user_id),
            "book_id": str(book_id),
            "project_id": str(body.project_id),
            "suggest_model_ref": str(body.suggest_model_ref),
            "sample_chapter_ids": [str(c) for c in body.sample_chapter_ids],
        },
    )
    enqueued = await enqueue_compose_task(
        task_id=task_id, kind="profile_suggest",
        user_id=str(user_id), project_id=str(body.project_id),
    )
    return {"task_id": task_id, "status": "pending",
            "enqueued": "ok" if enqueued else "retriggerable"}


# ── internal (server-to-server) read ────────────────────────────────────────────
# wiki-llm M1 / option A — the de-bias BookProfile stays AUTHORED here (it's an
# AI-domain artifact: LLM-suggested, era/anachronism-aware), and knowledge-service
# reads it over the internal token to SHAPE the wiki-generation prompt (worldview/
# voice/era/language). Additive: a NEW internal router, NOT a change to enrichment
# internals. No owner check — the internal token is the trust boundary (the caller
# is another LoreWeave service, like the eval gate-status route). Never 404s on a
# missing profile: get_book_profile returns the neutral default (a no-profile book
# shapes the prompt like a generic worldbuilder, never the hardcoded 封神 default).

internal_router = APIRouter(
    prefix="/internal/lore-enrichment/books",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


@internal_router.get("/{book_id}/profile")
async def get_profile_internal(
    book_id: UUID,
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """The book's enrichment profile for server-to-server consumers (neutral
    default if unset). Same view shape as the authored GET; X-Internal-Token."""
    profile = await get_book_profile(pool, book_id)
    return _profile_view(profile)
