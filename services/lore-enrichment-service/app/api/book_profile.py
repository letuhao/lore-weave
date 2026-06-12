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
from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.clients.sanitize import neutralize_injection
from app.config import settings
from app.db.book_profile import (
    BookProfile,
    get_book_profile,
    upsert_book_profile,
    validate_dimension_overrides,
)
from app.deps import get_db
from app.generation.complete import CompletionSeamError, make_complete_fn
from app.services.profile_suggest import (
    ProfileSuggestError,
    SuggestedProfile,
    suggest_profile,
)
from app.strategies.base import StrategyContext

router = APIRouter(prefix="/v1/lore-enrichment/books", tags=["profile"])
logger = logging.getLogger("lore_enrichment.book_profile")

#: how many chapters to auto-sample for AI-suggest when the author picks none.
_AUTO_SAMPLE_CHAPTERS = 3


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


def _suggested_view(s: SuggestedProfile) -> dict:
    return {
        "worldview": s.worldview,
        "language": s.language,
        "era_policy": s.era_policy,
        "voice": s.voice,
        "dimension_overrides": s.dimension_overrides,
        "profile_source": s.profile_source,
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


async def _sample_chapter_texts(
    book_client: BookClient, *, book_id: UUID, chapter_ids: list[UUID]
) -> list[str]:
    """Collect the text of the chapters to feed AI-suggest. Uses the author's
    explicit selection when given, else auto-samples the first few chapters.
    Best-effort: a chapter that errors or is empty is skipped."""
    if not chapter_ids:
        try:
            chapters, _ = await book_client.list_chapters(
                book_id=book_id, limit=_AUTO_SAMPLE_CHAPTERS
            )
            chapter_ids = [c.chapter_id for c in chapters]
        except BookServiceError:
            return []
    texts: list[str] = []
    for cid in chapter_ids:
        try:
            t = await book_client.get_chapter_text(book_id=book_id, chapter_id=cid)
        except BookServiceError:
            continue
        if t.strip():
            texts.append(t)
    return texts


async def _kg_summary(
    *, user_id: UUID, project_id: UUID, book: BookProjection
) -> str:
    """Best-effort knowledge-graph summary for AI-suggest. Reuses build_context
    (KB5: no re-ingest). A down/empty graph degrades to '' (never blocks suggest)."""
    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    message = (book.title + " " + " ".join(book.genre_tags)).strip()
    try:
        ctx = await kc.build_context(user_id=user_id, project_id=project_id, message=message)
        # M4: the KG blob is book-derived passage text — neutralize it (symmetry
        # with the chapter-text + projection paths) before it reaches the suggest
        # LLM prompt, so a book-origin injection can't survive extraction→KG→suggest.
        return neutralize_injection(ctx.context or "")
    except KnowledgeServiceError:
        return ""
    finally:
        await kc.aclose()


@router.post("/{book_id}/profile/suggest")
async def suggest_book_profile(
    book_id: UUID,
    body: SuggestBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """AI-suggest a profile DRAFT (worldview/language/era/voice + per-kind
    dimension overrides) from the book metadata + sample chapters + KG summary.
    Does NOT persist (the author edits + PUTs). Owner-only; model by BYOK
    model_ref. LLM failure → 502; KG read is best-effort."""
    user_id = _require_user(principal)
    book_client = BookClient(
        base_url=settings.book_service_url, internal_token=settings.internal_service_token
    )
    try:
        book = await _projection_owned(book_client, book_id=book_id, user_id=user_id)
        sample_texts = await _sample_chapter_texts(
            book_client, book_id=book_id, chapter_ids=body.sample_chapter_ids
        )
    finally:
        await book_client.aclose()

    kg_summary = await _kg_summary(user_id=user_id, project_id=body.project_id, book=book)

    complete_fn = make_complete_fn(
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    ctx = StrategyContext(
        user_id=str(user_id), project_id=str(body.project_id),
        model_ref=str(body.suggest_model_ref),
    )

    async def _complete(prompt: str) -> str:
        return await complete_fn(prompt, ctx)

    try:
        draft = await suggest_profile(
            book=book, sample_texts=sample_texts, kg_summary=kg_summary, complete=_complete,
        )
    except CompletionSeamError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=f"suggest LLM call failed: {exc}")
    except ProfileSuggestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"suggest produced no usable profile: {exc}",
        )
    return _suggested_view(draft)


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
