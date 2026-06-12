"""Compose one-shot task store + executors (LLM re-arch Phase 3 M2).

The two interactive compose LLM calls — AI-suggest a book profile, and resolve a
free-text intent — used to run their single ``/internal/llm/stream`` call INLINE in
the request handler and return the result. M2 moves them OFF the request path: the
endpoint creates a ``pending`` :data:`enrichment_compose_task` row, enqueues a
trigger on the resume stream, and returns ``202 + task_id``; the resume worker runs
the compute here and writes ``result_json``; ``GET /compose-tasks/{id}`` polls.

This module owns:
  * the task store (create / load / mark running|completed|failed),
  * :func:`run_compose_task` — the idempotent worker entrypoint (completed → skip;
    a crash mid-compute leaves 'running' → redelivery recomputes + overwrites, a
    duplicate LLM call that converges — acceptable for a draft),
  * the two compute functions, holding the LLM orchestration moved out of the
    endpoints (incl. ``_sample_chapter_texts`` / ``_kg_summary``, moved here so the
    worker can run them without an api↔api import cycle).

NO model NAMES — the model resolves by ``model_ref`` (a user_model UUID) via
provider-registry, exactly as the inline path did. Unmetered (matches today's
suggest/intent — no cost cap).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.clients.book import BookClient, BookProjection, BookServiceError
from app.clients.glossary import GlossaryClient, GlossaryServiceError
from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.clients.sanitize import neutralize_injection
from app.compose.intent import IntentResolutionError, resolve_intent
from app.config import settings
from app.db.book_profile import get_book_profile
from app.generation.complete import CompletionSeamError, make_complete_fn
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.services.profile_suggest import (
    ProfileSuggestError,
    SuggestedProfile,
    suggest_profile,
)
from app.strategies.base import StrategyContext

__all__ = [
    "VALID_KINDS",
    "create_compose_task",
    "enqueue_compose_task",
    "load_compose_task",
    "run_compose_task",
    "compute_profile_suggest",
    "compute_intent_resolve",
]

logger = logging.getLogger("lore_enrichment.compose_task")

#: The closed task-kind vocabulary (matches the DB CHECK).
VALID_KINDS = ("profile_suggest", "intent_resolve")

#: how many chapters to auto-sample for AI-suggest when the author picks none.
_AUTO_SAMPLE_CHAPTERS = 3


# ── store ────────────────────────────────────────────────────────────────────


async def create_compose_task(
    pool: asyncpg.Pool,
    *,
    kind: str,
    user_id: str,
    project_id: str,
    book_id: str | None,
    request: dict[str, Any],
) -> str:
    """Insert a 'pending' task and return its id. ``request`` is the request shape
    the worker needs to compute (model_ref UUIDs + params + acting user) — NEVER a
    secret."""
    async with pool.acquire() as conn:
        task_id = await conn.fetchval(
            """INSERT INTO enrichment_compose_task
                   (kind, status, user_id, project_id, book_id, request_json)
               VALUES ($1, 'pending', $2, $3, $4, $5::jsonb)
               RETURNING task_id""",
            kind, UUID(user_id), UUID(project_id),
            UUID(book_id) if book_id else None,
            json.dumps(request, ensure_ascii=False),
        )
    return str(task_id)


async def enqueue_compose_task(
    *, task_id: str, kind: str, user_id: str, project_id: str
) -> bool:
    """Best-effort XADD of a compose-task trigger on the resume stream (the worker
    branches on the ``task_id`` field). Returns True on enqueue, False on a
    transient Redis failure — a failed enqueue does NOT fail the create (a repeat
    submit / the stuck-task sweeper re-triggers it)."""
    producer = make_redis_producer(settings.redis_url)
    try:
        await producer.xadd(
            LORE_ENRICHMENT_RESUME_STREAM,
            {"task_id": task_id, "kind": kind,
             "user_id": user_id, "project_id": project_id},
            maxlen=10000,
        )
        return True
    except Exception:  # noqa: BLE001 — enqueue failure must not fail the create
        logger.warning("compose task %s enqueue failed (re-triggerable)",
                       task_id, exc_info=True)
        return False
    finally:
        await producer.aclose()


async def load_compose_task(
    pool: asyncpg.Pool, *, task_id: str, user_id: str | None = None
) -> dict[str, Any] | None:
    """Load a task row (optionally scoped to ``user_id`` for the poll route). The
    JSONB columns are returned as parsed dicts. Returns None when absent (or not
    the caller's, when ``user_id`` is given)."""
    preds = ["task_id=$1"]
    params: list[Any] = [UUID(task_id)]
    if user_id is not None:
        params.append(UUID(user_id))
        preds.append(f"user_id=${len(params)}")
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            f"""SELECT task_id, kind, status, user_id, project_id, book_id,
                       request_json, result_json, error_message
                FROM enrichment_compose_task WHERE {' AND '.join(preds)}""",
            *params,
        )
    if r is None:
        return None
    return {
        "task_id": str(r["task_id"]),
        "kind": r["kind"],
        "status": r["status"],
        "user_id": str(r["user_id"]),
        "project_id": str(r["project_id"]),
        "book_id": str(r["book_id"]) if r["book_id"] is not None else None,
        "request": _jsonb(r["request_json"]) or {},
        "result": _jsonb(r["result_json"]),
        "error": r["error_message"],
    }


def _jsonb(raw: Any) -> Any:
    """Decode a JSONB column. asyncpg returns jsonb as ``str`` unless a codec is
    registered — handle BOTH (mirrors app/jobs/job_request.py). None → None."""
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def _mark(
    pool: asyncpg.Pool,
    *,
    task_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE enrichment_compose_task
               SET status=$2,
                   result_json = COALESCE($3::jsonb, result_json),
                   error_message = $4,
                   updated_at = now()
               WHERE task_id=$1""",
            UUID(task_id), status,
            json.dumps(result, ensure_ascii=False) if result is not None else None,
            error,
        )


# ── worker entrypoint ─────────────────────────────────────────────────────────

#: business-level failures the compute raises — a bad LLM output / upstream 5xx is
#: a TERMINAL task outcome (mark failed + ACK), NOT an infra error to redeliver.
_BUSINESS_ERRORS = (
    CompletionSeamError,
    ProfileSuggestError,
    IntentResolutionError,
)


async def run_compose_task(pool: asyncpg.Pool, *, task_id: str) -> str:
    """Run ONE compose task to terminal. Idempotent for at-least-once redelivery:
    a 'completed' task returns immediately (no recompute); a crash mid-compute left
    the row 'running' → a redelivery recomputes + overwrites (a duplicate LLM call
    that converges). Returns a short status string for the log.

    A business failure (bad LLM output / upstream error) marks the task 'failed'
    and returns normally → the consumer ACKs (terminal). An INFRA error (DB/Redis)
    propagates → the consumer leaves the message un-ACKed → redelivery."""
    row = await load_compose_task(pool, task_id=task_id)
    if row is None:
        logger.warning("compose task %s not found — dropping", task_id)
        return "not_found"
    if row["status"] == "completed":
        return "already_completed"

    await _mark(pool, task_id=task_id, status="running")
    kind, req = row["kind"], row["request"]
    try:
        if kind == "profile_suggest":
            result = await compute_profile_suggest(
                pool,
                user_id=req["user_id"],
                book_id=req["book_id"],
                project_id=req["project_id"],
                suggest_model_ref=req["suggest_model_ref"],
                sample_chapter_ids=req.get("sample_chapter_ids") or [],
            )
        elif kind == "intent_resolve":
            result = await compute_intent_resolve(
                pool,
                user_id=req["user_id"],
                project_id=req["project_id"],
                book_id=req["book_id"],
                intent_text=req["intent_text"],
                generation_model_ref=req["generation_model_ref"],
            )
        else:  # defensive — the DB CHECK already bounds kind
            await _mark(pool, task_id=task_id, status="failed",
                        error=f"unknown task kind {kind!r}")
            return "unknown_kind"
    except _BUSINESS_ERRORS as exc:
        logger.info("compose task %s (%s) failed: %s", task_id, kind, exc)
        await _mark(pool, task_id=task_id, status="failed", error=str(exc))
        return "failed"

    await _mark(pool, task_id=task_id, status="completed", result=result)
    return "completed"


# ── compute: profile suggest ──────────────────────────────────────────────────


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


async def _kg_summary(*, user_id: UUID, project_id: UUID, book: BookProjection) -> str:
    """Best-effort knowledge-graph summary for AI-suggest. A down/empty graph
    degrades to '' (never blocks suggest). The KG blob is book-derived passage
    text → neutralize it (symmetry with the chapter-text + projection paths) so a
    book-origin injection can't survive extraction→KG→suggest."""
    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    message = (book.title + " " + " ".join(book.genre_tags)).strip()
    try:
        ctx = await kc.build_context(user_id=user_id, project_id=project_id, message=message)
        return neutralize_injection(ctx.context or "")
    except KnowledgeServiceError:
        return ""
    finally:
        await kc.aclose()


def _suggested_view(s: SuggestedProfile) -> dict[str, Any]:
    return {
        "worldview": s.worldview,
        "language": s.language,
        "era_policy": s.era_policy,
        "voice": s.voice,
        "dimension_overrides": s.dimension_overrides,
        "profile_source": s.profile_source,
    }


async def compute_profile_suggest(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    book_id: str,
    project_id: str,
    suggest_model_ref: str,
    sample_chapter_ids: list[str],
) -> dict[str, Any]:
    """Run the profile-suggest LLM pipeline (book metadata + sample chapters + KG
    summary → a suggested de-bias profile draft). The submit-time owner check has
    already authorized this user; the worker re-fetches the projection for the
    metadata. Raises a business error (CompletionSeamError / ProfileSuggestError)
    on a bad LLM result — :func:`run_compose_task` maps it to a 'failed' task."""
    book_uuid = UUID(book_id)
    book_client = BookClient(
        base_url=settings.book_service_url, internal_token=settings.internal_service_token
    )
    try:
        book = await book_client.get_projection(book_id=book_uuid)
        sample_texts = await _sample_chapter_texts(
            book_client, book_id=book_uuid,
            chapter_ids=[UUID(c) for c in sample_chapter_ids],
        )
    finally:
        await book_client.aclose()

    kg_summary = await _kg_summary(
        user_id=UUID(user_id), project_id=UUID(project_id), book=book
    )
    complete_fn = make_complete_fn(
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    ctx = StrategyContext(
        user_id=user_id, project_id=project_id, model_ref=suggest_model_ref,
    )

    async def _complete(prompt: str) -> str:
        return await complete_fn(prompt, ctx)

    draft = await suggest_profile(
        book=book, sample_texts=sample_texts, kg_summary=kg_summary, complete=_complete,
    )
    return _suggested_view(draft)


# ── compute: intent resolve ───────────────────────────────────────────────────


async def compute_intent_resolve(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    project_id: str,
    book_id: str,
    intent_text: str,
    generation_model_ref: str,
) -> dict[str, Any]:
    """Resolve a free-text intent → a proposed target + dimensions + technique via
    ONE LLM call. Best-effort glossary entities hint the resolver. Raises a business
    error on a bad result (mapped to a 'failed' task)."""
    profile = await get_book_profile(pool, UUID(book_id))
    client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
    )
    try:
        ents = await client.list_entities(book_id=UUID(book_id), limit=200)
    except (GlossaryServiceError, Exception):  # noqa: BLE001 — best-effort hint
        ents = []
    finally:
        await client.aclose()
    entities = [{"name": e.name, "kind": e.kind} for e in ents]

    complete = make_complete_fn(
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    resolved = await resolve_intent(
        complete=complete,
        intent_text=intent_text,
        entities=entities,
        profile=profile,
        user_id=user_id,
        project_id=project_id,
        model_ref=generation_model_ref,
    )
    return resolved.as_dict()
