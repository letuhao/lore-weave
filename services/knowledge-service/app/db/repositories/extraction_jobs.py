"""Extraction jobs repository (K10.4).

SECURITY RULE: every method takes ``user_id`` as the first argument
and every SQL statement filters by ``user_id = $1``. The repo is the
user-isolation boundary — downstream code (extraction worker loop,
router) trusts that any row returned here really belongs to the
caller.

**Security/money critical**: `try_spend` is the atomic cost-cap
guard. It MUST be a single SQL statement per KSA §5.5 — the naive
"SELECT then UPDATE" shape has a TOCTOU window where two parallel
workers both read "budget available", both proceed with an LLM
call, and both overshoot the cap. The current shape uses
Postgres's single-statement guarantee that the CASE expression on
the UPDATE's SET clause reads the PRE-update values for
`cost_spent_usd`, so the budget check and the reservation happen
in the same row lock.

Design notes:

- `max_spend_usd IS NULL` means **unlimited budget**. The CASE
  `cost_spent_usd + $1 >= max_spend_usd` evaluates to NULL in that
  case (SQL NULL arithmetic), which is falsy in the CASE's WHEN
  clause, so the status transition is skipped and the job stays
  running regardless of how much it has spent.

- Worst-case overshoot is one item's estimated cost. The 7th worker
  in a 10-worker, $1.00-cap, $0.15-estimate race wins the budget
  even though their reservation trips the auto-pause; the 8th+
  workers see `status='paused'` on their WHERE filter, match 0
  rows, and abort. Total reserved ≤ `max_spend_usd + last_estimate`.

- Status machine is NOT enforced at the repo layer for the
  general `update_status` path — the extraction worker is
  single-purpose and trusted. Only `try_spend` enforces a status
  filter (`running`), because that's the one where a stale
  caller's wrong-status write could leak money.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ExtractionJob",
    "ExtractionJobCreate",
    "ExtractionJobsRepo",
    "JobScope",
    "JobStatus",
    "LIST_ALL_MAX_LIMIT",
    "TrySpendOutcome",
    "TrySpendResult",
]

# K19b.1 — shared upper bound for list_all_for_user / router pagination.
# Router's Query(le=LIST_ALL_MAX_LIMIT) and the repo's min(limit, ...)
# clamp MUST stay in sync; exporting a single constant makes the
# coupling explicit so a future raise in either layer can't drift.
LIST_ALL_MAX_LIMIT = 200

JobScope = Literal["chapters", "chat", "glossary_sync", "all"]
JobStatus = Literal[
    "pending", "running", "paused", "complete", "failed", "cancelled"
]

# All columns projected in a full job row. Centralised so every query
# returns the same Pydantic-shaped tuple.
_SELECT_COLS = """
  job_id, user_id, project_id, scope, scope_range, status,
  llm_model, embedding_model, max_spend_usd,
  items_total, items_processed, current_cursor, cost_spent_usd,
  started_at, paused_at, completed_at, created_at, updated_at,
  error_message
"""


# ── Pydantic models ──────────────────────────────────────────────────────


class ExtractionJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    user_id: UUID
    project_id: UUID
    scope: JobScope
    scope_range: dict[str, Any] | None = None
    status: JobStatus

    llm_model: str
    embedding_model: str
    max_spend_usd: Decimal | None = None

    items_total: int | None = None
    items_processed: int = 0
    current_cursor: dict[str, Any] | None = None
    cost_spent_usd: Decimal = Decimal("0")

    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


class ExtractionJobCreate(BaseModel):
    """Caller-facing payload for `create`. `user_id` is enforced at the
    method signature, not the payload, so callers can't inject it.

    K10.4-I4: input validation. `max_spend_usd` must be non-negative
    (a negative cap would cause the first `try_spend` to immediately
    auto-pause, which is confusing). `llm_model` / `embedding_model`
    must be non-empty strings (the extraction worker will try to
    instantiate a model by name and fail cryptically on ""). `items_total`
    is optional but must be non-negative when provided.
    """

    project_id: UUID
    scope: JobScope
    llm_model: Annotated[str, Field(min_length=1, max_length=200)]
    embedding_model: Annotated[str, Field(min_length=1, max_length=200)]
    max_spend_usd: Annotated[Decimal, Field(ge=0)] | None = None
    scope_range: dict[str, Any] | None = None
    items_total: Annotated[int, Field(ge=0)] | None = None


# ── try_spend outcome ────────────────────────────────────────────────────


TrySpendOutcome = Literal["reserved", "auto_paused", "not_running"]


@dataclass(frozen=True)
class TrySpendResult:
    """Return type for `try_spend`. Discriminated on `outcome`:

    - ``reserved``    — budget reserved, job still running, worker may
                        proceed with the LLM call. `new_cost_spent_usd`
                        is the post-update total.
    - ``auto_paused`` — worker MAY proceed (their reservation succeeded)
                        BUT the job transitioned to `paused` in the
                        same UPDATE. Subsequent `try_spend` calls will
                        return `not_running`. The worker should make
                        this ONE LLM call and then stop polling.
    - ``not_running`` — WHERE clause matched 0 rows. Either the job
                        never existed for this user, or it was already
                        paused/complete/failed/cancelled. No budget was
                        reserved. Worker MUST NOT make the LLM call.
    """

    outcome: TrySpendOutcome
    new_cost_spent_usd: Decimal | None = None
    new_status: JobStatus | None = None


# ── Repository ───────────────────────────────────────────────────────────


def _row_to_job(row: asyncpg.Record) -> ExtractionJob:
    data = dict(row)
    # asyncpg returns JSONB as str or dict depending on codec; normalise.
    for k in ("scope_range", "current_cursor"):
        v = data.get(k)
        if isinstance(v, str):
            data[k] = json.loads(v)
    return ExtractionJob.model_validate(data)


class ExtractionJobsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ─── create ──────────────────────────────────────────────────────

    async def create(
        self, user_id: UUID, data: ExtractionJobCreate
    ) -> ExtractionJob:
        """Insert a new extraction job in `pending` state. Caller
        transitions to `running` via `update_status` before dispatching
        workers."""
        query = f"""
        INSERT INTO extraction_jobs
          (user_id, project_id, scope, scope_range, llm_model,
           embedding_model, max_spend_usd, items_total)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                user_id,
                data.project_id,
                data.scope,
                json.dumps(data.scope_range) if data.scope_range else None,
                data.llm_model,
                data.embedding_model,
                data.max_spend_usd,
                data.items_total,
            )
        return _row_to_job(row)

    # ─── reads ───────────────────────────────────────────────────────

    async def get(self, user_id: UUID, job_id: UUID) -> ExtractionJob | None:
        query = f"""
        SELECT {_SELECT_COLS}
        FROM extraction_jobs
        WHERE user_id = $1 AND job_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, job_id)
        return _row_to_job(row) if row else None

    async def list_for_project(
        self, user_id: UUID, project_id: UUID, *, limit: int = 50
    ) -> list[ExtractionJob]:
        """List all jobs for a project, newest first. Caller is
        expected to paginate via subsequent calls if the list grows."""
        effective_limit = max(1, min(limit, 200))
        query = f"""
        SELECT {_SELECT_COLS}
        FROM extraction_jobs
        WHERE user_id = $1 AND project_id = $2
        ORDER BY created_at DESC
        LIMIT {effective_limit}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, project_id)
        return [_row_to_job(r) for r in rows]

    async def list_active(self, user_id: UUID) -> list[ExtractionJob]:
        """Jobs that are pending/running/paused across all the user's
        projects. Powers the "in flight" widget on the Memory page."""
        query = f"""
        SELECT {_SELECT_COLS}
        FROM extraction_jobs
        WHERE user_id = $1
          AND status IN ('pending','running','paused')
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        return [_row_to_job(r) for r in rows]

    async def list_all_for_user(
        self,
        user_id: UUID,
        *,
        status_group: Literal["active", "history"],
        limit: int = 50,
    ) -> list[ExtractionJob]:
        """K19b.1 — user-scoped cross-project list split by status group.

        active  → pending / running / paused   ORDER BY created_at DESC
        history → complete / failed / cancelled
                  ORDER BY completed_at DESC NULLS LAST, created_at DESC
                  (finished-at is more meaningful than started-at here,
                  but some legacy rows may have NULL completed_at, so we
                  fall back to created_at to keep them orderable.)
        """
        effective_limit = max(1, min(limit, LIST_ALL_MAX_LIMIT))
        # job_id DESC tiebreaker: uuidv7 is time-ordered, so on a
        # microsecond-tied created_at the larger job_id is the one
        # inserted last — gives a deterministic order under bulk seeds.
        if status_group == "active":
            query = f"""
            SELECT {_SELECT_COLS}
            FROM extraction_jobs
            WHERE user_id = $1
              AND status IN ('pending','running','paused')
            ORDER BY created_at DESC, job_id DESC
            LIMIT {effective_limit}
            """
        else:
            query = f"""
            SELECT {_SELECT_COLS}
            FROM extraction_jobs
            WHERE user_id = $1
              AND status IN ('complete','failed','cancelled')
            ORDER BY completed_at DESC NULLS LAST, created_at DESC, job_id DESC
            LIMIT {effective_limit}
            """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        return [_row_to_job(r) for r in rows]

    # ─── state transitions ───────────────────────────────────────────

    async def update_status(
        self,
        user_id: UUID,
        job_id: UUID,
        new_status: JobStatus,
        *,
        error_message: str | None = None,
    ) -> ExtractionJob | None:
        """Generic status setter. Also updates the derived timestamp
        columns (`started_at` / `paused_at` / `completed_at`) based
        on the target status.

        K10.4-I1: terminal states (`complete`, `cancelled`, `failed`)
        CANNOT be transitioned out of. Attempting to revive a
        terminal job returns `None` (same as "not found / cross-user"
        — caller can `get()` after a `None` return to disambiguate).
        The retry use case is served by creating a NEW job, not
        resurrecting the old one — cleaner audit trail AND neutralises
        any risk that a stale `try_spend` could leak money on a
        zombie-resurrected job.

        K10.4-I3: `error_message` is only kept when the target state
        is `failed`. Every other transition clears it. Given that
        once-failed is terminal (per I1 above), this means the
        error message is write-once: the single `* → failed`
        transition sets it, and nothing ever touches it again.

        Does NOT enforce a general state machine beyond the terminal
        lock — the extraction worker is trusted to pass valid
        non-terminal transitions. For the budget-critical reservation
        path, use `try_spend` instead.
        """
        query = f"""
        UPDATE extraction_jobs
        SET
          status = $3,
          started_at = CASE
            WHEN $3 = 'running' AND started_at IS NULL THEN now()
            ELSE started_at
          END,
          paused_at = CASE
            WHEN $3 = 'paused' THEN now()
            ELSE paused_at
          END,
          completed_at = CASE
            WHEN $3 IN ('complete','failed','cancelled') THEN now()
            ELSE completed_at
          END,
          error_message = CASE
            WHEN $3 = 'failed' THEN $4
            ELSE NULL
          END,
          updated_at = now()
        WHERE user_id = $1
          AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, job_id, new_status, error_message)
        return _row_to_job(row) if row else None

    async def complete(
        self, user_id: UUID, job_id: UUID
    ) -> ExtractionJob | None:
        """Convenience wrapper for the happy-path terminal state."""
        return await self.update_status(user_id, job_id, "complete")

    async def cancel(
        self, user_id: UUID, job_id: UUID
    ) -> ExtractionJob | None:
        """Convenience wrapper for user-initiated cancel."""
        return await self.update_status(user_id, job_id, "cancelled")

    # ─── cursor advance ──────────────────────────────────────────────

    async def advance_cursor(
        self,
        user_id: UUID,
        job_id: UUID,
        cursor: dict[str, Any],
        *,
        items_processed_delta: int = 1,
    ) -> ExtractionJob | None:
        """Worker calls this after a successful LLM extraction to
        persist progress so a crash/resume can continue from the
        right place. NOT the same call as `try_spend` — cost is
        reserved before the LLM call, cursor advance happens after.

        K10.4-D1 (plan deviation): the original K10.4 spec lists
        `advance_cursor(job_id, cursor_data)` as cursor-only.
        Combining cursor + items_processed advance into one method
        halves the SQL round-trips on the hot path, since they
        always co-occur in practice. The combined shape is
        defended in tests.

        K10.4-I2: only jobs in `running` or `paused` can advance
        their cursor. Pending jobs haven't started; complete /
        cancelled / failed are terminal. Any other state returns
        `None`.

        K10.4-I7: `items_processed_delta` must be >= 0. Negative
        values would corrupt the progress counter and have no
        legitimate use case. Caller passes 0 explicitly when they
        want a cursor-only update without an item advance.

        Does NOT touch `cost_spent_usd` — cost reconciliation
        (estimated vs actual) is a separate step handled by the
        caller via a direct `UPDATE ... SET cost_spent_usd = ...`
        when needed. K10.4 keeps this repo method scope-limited.
        """
        if items_processed_delta < 0:
            raise ValueError(
                f"items_processed_delta must be >= 0, got {items_processed_delta}",
            )
        query = f"""
        UPDATE extraction_jobs
        SET
          current_cursor = $3::jsonb,
          items_processed = items_processed + $4,
          updated_at = now()
        WHERE user_id = $1
          AND job_id = $2
          AND status IN ('running', 'paused')
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, user_id, job_id, json.dumps(cursor), items_processed_delta,
            )
        return _row_to_job(row) if row else None

    # ─── atomic cost reservation (KSA §5.5) ──────────────────────────

    async def try_spend(
        self,
        user_id: UUID,
        job_id: UUID,
        estimated_cost: Decimal,
    ) -> TrySpendResult:
        """Atomic cost reservation. Security/money critical.

        Semantics:
          - If the job is not `running` for this user, returns
            `not_running` and reserves nothing.
          - If there's no budget cap (`max_spend_usd IS NULL`),
            reserves unconditionally and returns `reserved`.
          - If `cost_spent_usd + estimated_cost >= max_spend_usd`,
            reserves AND trips the status to `paused` in the same
            UPDATE. The caller MAY make one more LLM call (their
            reservation succeeded) but subsequent `try_spend` calls
            will return `not_running`. This is the "win the last
            item" behaviour from KSA §5.5.
          - Otherwise reserves and returns `reserved`.

        The CASE expression on `status` uses Postgres's guarantee
        that SET reads PRE-update column values. `cost_spent_usd +
        $3` is therefore the pre-update sum + the new reservation,
        which is the value we want to test against the cap.
        """
        # Single-statement UPDATE — the whole point of the method.
        # DO NOT split into SELECT-then-UPDATE.
        query = """
        UPDATE extraction_jobs
        SET
          cost_spent_usd = cost_spent_usd + $3,
          status = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN 'paused'
            ELSE status
          END,
          paused_at = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN now()
            ELSE paused_at
          END,
          updated_at = now()
        WHERE user_id = $1 AND job_id = $2 AND status = 'running'
        RETURNING cost_spent_usd, status
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, job_id, estimated_cost)
        if row is None:
            return TrySpendResult(outcome="not_running")
        new_status = row["status"]
        new_cost = row["cost_spent_usd"]
        if new_status == "paused":
            return TrySpendResult(
                outcome="auto_paused",
                new_cost_spent_usd=new_cost,
                new_status=new_status,
            )
        return TrySpendResult(
            outcome="reserved",
            new_cost_spent_usd=new_cost,
            new_status=new_status,
        )
