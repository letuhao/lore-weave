"""wiki-llm M6 — wiki_gen_jobs repository.

Thin asyncpg repo for the batch wiki-generation job (mirrors the extraction_jobs
shape). The per-book lock lives in the schema (a partial unique index on
``book_id`` WHERE the status is active); `create` surfaces a conflict as
:class:`ActiveJobExists` so the trigger can return 409 + the existing job_id
rather than a raw IntegrityError. ``items_done`` drives skip-on-resume — the
orchestrator appends each completed entity so a paused/restarted job never
re-generates one it already wrote.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel

__all__ = ["WikiGenJob", "ActiveJobExists", "WikiGenJobsRepo"]


def _affected(tag: str) -> int:
    """Rows touched, from an asyncpg command tag ('UPDATE 1'). Robust to the
    multi-digit case ('UPDATE 21'.endswith('1') would lie)."""
    try:
        return int(tag.rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0


class ActiveJobExists(Exception):
    """Raised by `create` when an active job already exists for the book (the
    per-book lock). Carries the existing job_id for the 409 response."""

    def __init__(self, existing_job_id: UUID | None) -> None:
        super().__init__("an active wiki-gen job already exists for this book")
        self.existing_job_id = existing_job_id


class WikiGenJob(BaseModel):
    job_id: UUID
    user_id: UUID
    project_id: UUID
    book_id: UUID
    status: str
    model_source: str
    model_ref: str
    entity_ids: list[str]
    items_done: list[str]
    max_spend_usd: Decimal | None = None
    items_total: int | None = None
    items_processed: int = 0
    cost_spent_usd: Decimal = Decimal("0")
    error_message: str | None = None
    # W4a — per-entity result detail (entity_id → {outcome, citations, flags, name})
    # + the live sub-step pointer (the one in-flight entity + its pipeline pass).
    results: dict[str, Any] = {}
    current_entity_id: str | None = None
    current_pass: str | None = None
    # W5 — optional second model for the corrective revise re-gen (null = prose model).
    revise_model_ref: str | None = None
    revise_model_source: str | None = None


_COLS = (
    "job_id, user_id, project_id, book_id, status, model_source, model_ref, "
    "entity_ids, items_done, max_spend_usd, items_total, items_processed, "
    "cost_spent_usd, error_message, results, current_entity_id, current_pass, "
    "revise_model_ref, revise_model_source"
)


def _parse_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    return [str(x) for x in raw] if isinstance(raw, list) else []


def _parse_obj(raw: Any) -> dict[str, Any]:
    """JSONB object → dict (asyncpg may hand back a JSON string or a dict)."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else {}
    return dict(raw) if isinstance(raw, dict) else {}


def _row_to_job(row: asyncpg.Record) -> WikiGenJob:
    return WikiGenJob(
        job_id=row["job_id"], user_id=row["user_id"], project_id=row["project_id"],
        book_id=row["book_id"], status=row["status"],
        model_source=row["model_source"], model_ref=row["model_ref"],
        entity_ids=_parse_list(row["entity_ids"]), items_done=_parse_list(row["items_done"]),
        max_spend_usd=row["max_spend_usd"], items_total=row["items_total"],
        items_processed=row["items_processed"], cost_spent_usd=row["cost_spent_usd"],
        error_message=row["error_message"],
        results=_parse_obj(row["results"]),
        current_entity_id=row["current_entity_id"], current_pass=row["current_pass"],
        revise_model_ref=row["revise_model_ref"],
        revise_model_source=row["revise_model_source"],
    )


class WikiGenJobsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self, *, user_id: UUID, project_id: UUID, book_id: UUID,
        model_source: str, model_ref: str, entity_ids: list[str],
        max_spend_usd: Decimal | None, items_total: int | None,
        revise_model_ref: str | None = None, revise_model_source: str | None = None,
    ) -> WikiGenJob:
        """Insert a pending job. The per-book partial-unique index makes a 2nd
        active job for the book raise UniqueViolation → :class:`ActiveJobExists`.
        ``revise_model_*`` (W5) is the optional corrective-revise override (null =
        the revise reuses the prose model)."""
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO wiki_gen_jobs
                      (user_id, project_id, book_id, model_source, model_ref,
                       entity_ids, max_spend_usd, items_total,
                       revise_model_ref, revise_model_source)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10)
                    RETURNING {_COLS}
                    """,
                    user_id, project_id, book_id, model_source, model_ref,
                    json.dumps([str(e) for e in entity_ids]), max_spend_usd, items_total,
                    revise_model_ref or None, revise_model_source or None,
                )
            return _row_to_job(row)
        except asyncpg.UniqueViolationError:
            existing = await self.get_active_for_book(book_id)
            raise ActiveJobExists(existing.job_id if existing else None) from None

    async def get(self, job_id: UUID) -> WikiGenJob | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLS} FROM wiki_gen_jobs WHERE job_id=$1", job_id)
        return _row_to_job(row) if row else None

    async def list_resumable(self, *, limit: int = 100) -> list[WikiGenJob]:
        """Jobs that should be (re)driven on a consumer startup — pending (the
        trigger XADD may have been missed while the consumer was down) or running
        (a process crashed mid-run; skip-done makes re-running safe). Paused jobs
        are NOT resumed automatically (a budget pause is a deliberate stop)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT {_COLS} FROM wiki_gen_jobs
                    WHERE status IN ('pending','running')
                    ORDER BY created_at LIMIT $1""",
                limit)
        return [_row_to_job(r) for r in rows]

    async def get_active_for_book(self, book_id: UUID) -> WikiGenJob | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT {_COLS} FROM wiki_gen_jobs
                    WHERE book_id=$1 AND status IN ('pending','running','paused')
                    ORDER BY created_at DESC LIMIT 1""",
                book_id)
        return _row_to_job(row) if row else None

    async def get_latest_for_book(self, book_id: UUID, user_id: UUID) -> WikiGenJob | None:
        """The most-recent job for (book, user) regardless of status — drives the
        FE poll, which must keep seeing the row after it reaches a terminal state
        (complete/paused/failed/cancelled), unlike ``get_active_for_book``. Scoped
        to ``user_id`` as defense-in-depth (glossary already gated the owner)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT {_COLS} FROM wiki_gen_jobs
                    WHERE book_id=$1 AND user_id=$2
                    ORDER BY created_at DESC LIMIT 1""",
                book_id, user_id)
        return _row_to_job(row) if row else None

    async def mark_running(self, job_id: UUID, *, items_total: int) -> bool:
        """Claim a job for a run: pending|running → running. The status guard makes
        this a CLAIM, not a blind write — if a concurrent cancel flipped the job to
        'cancelled' (or it already completed/failed) between the consumer pulling it
        and here, this affects 0 rows and the orchestrator aborts rather than
        resurrecting a cancelled job (M7b /review-impl F1). Returns True iff claimed."""
        async with self._pool.acquire() as conn:
            tag = await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET status='running', started_at=COALESCE(started_at, now()),
                       items_total=$2, current_entity_id=NULL, current_pass=NULL,
                       updated_at=now()
                   WHERE job_id=$1 AND status IN ('pending','running')""",
                job_id, items_total)
        return _affected(tag) == 1

    async def set_progress(self, job_id: UUID, entity_id: str, pass_name: str) -> None:
        """W4a — point the live sub-step pointer at the entity currently in flight
        and its pipeline pass (context|generate|verify|revise|writeback). A cheap
        UPDATE called before each pass; the FE poll renders the live indicator off
        it. Best-effort at the call site (a progress write must not crash the run)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET current_entity_id=$2, current_pass=$3, updated_at=now()
                   WHERE job_id=$1""",
                job_id, entity_id, pass_name)

    async def record_result(self, job_id: UUID, entity_id: str, detail: dict[str, Any]) -> None:
        """W4a — upsert one entity's result detail into the ``results`` object
        ({outcome, citations, flags, name}). Idempotent: a preliminary 'processing'
        row is overwritten by the final outcome, and a resume/retry overwrites a
        prior attempt. Best-effort at the call site."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET results = results || jsonb_build_object($2::text, $3::jsonb),
                       updated_at=now()
                   WHERE job_id=$1""",
                job_id, entity_id, json.dumps(detail))

    async def mark_entity_done(self, job_id: UUID, entity_id: str, *, cost: Decimal) -> None:
        """Append the entity to items_done (skip-on-resume) + bump processed/cost,
        atomically. JSONB array append dedups defensively."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET items_done = CASE WHEN items_done @> to_jsonb($2::text)
                                         THEN items_done
                                         ELSE items_done || to_jsonb($2::text) END,
                       items_processed = items_processed + 1,
                       cost_spent_usd = cost_spent_usd + $3,
                       updated_at = now()
                   WHERE job_id=$1""",
                job_id, entity_id, cost)

    async def pause(self, job_id: UUID, *, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs SET status='paused', paused_at=now(),
                   error_message=$2, current_entity_id=NULL, current_pass=NULL,
                   updated_at=now() WHERE job_id=$1""",
                job_id, reason)

    async def complete(self, job_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs SET status='complete', completed_at=now(),
                   current_entity_id=NULL, current_pass=NULL,
                   updated_at=now() WHERE job_id=$1""",
                job_id)

    async def resume(self, job_id: UUID) -> bool:
        """paused → pending so a startup-drain / fresh XADD re-drives it (skip-done
        handles partial progress). Guarded on ``status='paused'`` so a concurrent
        cancel/complete can't be clobbered; returns True iff it actually flipped a
        paused job. Clears the budget pause marker."""
        async with self._pool.acquire() as conn:
            tag = await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET status='pending', paused_at=NULL, error_message=NULL, updated_at=now()
                   WHERE job_id=$1 AND status='paused'""",
                job_id)
        return _affected(tag) == 1

    async def cancel(self, job_id: UUID) -> bool:
        """Cancel a not-yet-running job (pending|paused → cancelled), releasing the
        per-book lock (the partial-unique index excludes 'cancelled'). A *running*
        job is intentionally NOT cancellable here — the orchestrator doesn't poll
        status mid-loop, so a cancelled-while-running row would be clobbered by its
        terminal complete()/pause() write (D-WIKI-M7B-RUNNING-CANCEL). Returns True
        iff a pending|paused job was cancelled."""
        async with self._pool.acquire() as conn:
            tag = await conn.execute(
                """UPDATE wiki_gen_jobs
                   SET status='cancelled', completed_at=now(), updated_at=now()
                   WHERE job_id=$1 AND status IN ('pending','paused')""",
                job_id)
        return _affected(tag) == 1

    async def fail(self, job_id: UUID, *, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE wiki_gen_jobs SET status='failed', error_message=$2,
                   current_entity_id=NULL, current_pass=NULL,
                   updated_at=now() WHERE job_id=$1""",
                job_id, error[:2000])
