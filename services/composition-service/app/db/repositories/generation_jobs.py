"""generation_job repository — AI generation + critic tracking (§1.2/§5).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. `create` honours `idempotency_key` via the partial UNIQUE index
(idx_generation_job_idem): a replay returns the existing job instead of a
duplicate (the M6 engine's idempotency surface, §13 S2). `base_revision_id` is
captured at draft time (OI-2 accept-staleness guard).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import GenerationJob
from app.db.repositories import ReferenceViolationError

_SELECT_COLS = """
  id, user_id, project_id, outline_node_id, operation, mode, status, llm_job_id,
  input, result, critic, target_chapter_id, base_revision_id, target_revision_id,
  cost_usd, idempotency_key, created_at, updated_at
"""

# Active = not yet terminal. Used by the M6 engine to cancel an in-flight job
# before starting a new one for the same node (§13 S2).
_ACTIVE_STATUSES = ("pending", "running")


def _jsonb(value: dict[str, Any] | None) -> str | None:
    return None if value is None else json.dumps(value)


def _row_to_job(row: asyncpg.Record) -> GenerationJob:
    data = dict(row)
    for col in ("input", "result", "critic"):
        v = data.get(col)
        if isinstance(v, str):
            data[col] = json.loads(v)
    return GenerationJob.model_validate(data)


class GenerationJobsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
        operation: str,
        outline_node_id: UUID | None = None,
        mode: str = "cowrite",
        status: str = "pending",
        input: dict[str, Any] | None = None,
        base_revision_id: UUID | None = None,
        idempotency_key: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[GenerationJob, bool]:
        """Insert a job. Returns ``(job, created)``.

        When `idempotency_key` is set and already exists for this user, the
        existing job is returned with ``created=False`` (no duplicate) — the
        replay-safe surface for POST /generate. The conflict target carries the
        index's partial predicate so it matches idx_generation_job_idem.
        """
        async def _do(c: asyncpg.Connection) -> tuple[GenerationJob, bool]:
            if outline_node_id is not None:
                # Defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): the job's node must
                # be the caller's in THIS project (the FK only proves existence).
                owned = await c.fetchval(
                    "SELECT 1 FROM outline_node "
                    "WHERE user_id = $1 AND project_id = $2 AND id = $3",
                    user_id, project_id, outline_node_id,
                )
                if owned is None:
                    raise ReferenceViolationError(
                        f"outline_node {outline_node_id} is not the caller's node in this project"
                    )
            row = await c.fetchrow(
                f"""
                INSERT INTO generation_job
                  (user_id, project_id, outline_node_id, operation, mode, status,
                   input, base_revision_id, idempotency_key)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
                RETURNING {_SELECT_COLS}
                """,
                user_id, project_id, outline_node_id, operation, mode, status,
                json.dumps(input or {}), base_revision_id, idempotency_key,
            )
            if row is not None:
                return _row_to_job(row), True
            # Conflict: the key already exists. Return the existing job (scoped
            # to this user so a cross-user key collision can't leak a row).
            existing = await c.fetchrow(
                f"SELECT {_SELECT_COLS} FROM generation_job "
                f"WHERE user_id = $1 AND idempotency_key = $2",
                user_id, idempotency_key,
            )
            if existing is None:
                # Key belongs to another user → behave as not-found-for-us; the
                # router maps this to a conflict rather than silently reusing.
                raise KeyError("idempotency_key conflict across users")
            return _row_to_job(existing), False

        if conn is not None:
            return await _do(conn)
        async with self._pool.acquire() as c:
            return await _do(c)

    async def get(self, user_id: UUID, job_id: UUID) -> GenerationJob | None:
        query = f"SELECT {_SELECT_COLS} FROM generation_job WHERE user_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, job_id)
        return _row_to_job(row) if row else None

    async def get_by_idempotency_key(
        self, user_id: UUID, key: str
    ) -> GenerationJob | None:
        query = (
            f"SELECT {_SELECT_COLS} FROM generation_job "
            f"WHERE user_id = $1 AND idempotency_key = $2"
        )
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, key)
        return _row_to_job(row) if row else None

    async def list_active_for_node(
        self, user_id: UUID, project_id: UUID, outline_node_id: UUID
    ) -> list[GenerationJob]:
        """Pending/running jobs for a node — the M6 cancel-in-flight input."""
        query = f"""
        SELECT {_SELECT_COLS} FROM generation_job
        WHERE user_id = $1 AND project_id = $2 AND outline_node_id = $3
          AND status = ANY($4::text[])
        ORDER BY created_at
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id, outline_node_id, list(_ACTIVE_STATUSES))
        return [_row_to_job(r) for r in rows]

    async def update_status(
        self,
        user_id: UUID,
        job_id: UUID,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        critic: dict[str, Any] | None = None,
        llm_job_id: UUID | None = None,
        target_chapter_id: UUID | None = None,
        target_revision_id: UUID | None = None,
        cost_usd: Decimal | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> GenerationJob | None:
        """Transition a job's status and optionally stamp result/critic/refs.

        Only the explicitly-passed optional fields are written (COALESCE keeps
        the existing value when None) — a critique call can set `critic` +
        `target_revision_id` without clobbering `result`. Returns the updated
        job or None (missing / cross-user)."""
        query = f"""
        UPDATE generation_job
        SET status = $3,
            result = COALESCE($4::jsonb, result),
            critic = COALESCE($5::jsonb, critic),
            llm_job_id = COALESCE($6, llm_job_id),
            target_chapter_id = COALESCE($7, target_chapter_id),
            target_revision_id = COALESCE($8, target_revision_id),
            cost_usd = COALESCE($9, cost_usd),
            updated_at = now()
        WHERE user_id = $1 AND id = $2
        RETURNING {_SELECT_COLS}
        """
        args = (
            user_id, job_id, status, _jsonb(result), _jsonb(critic), llm_job_id,
            target_chapter_id, target_revision_id, cost_usd,
        )
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_job(row) if row else None
