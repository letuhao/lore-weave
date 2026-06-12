"""generation_job repository — AI generation + critic tracking (§1.2/§5).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. `create` honours `idempotency_key` via the partial UNIQUE index
(idx_generation_job_idem): a replay returns the existing job instead of a
duplicate (the M6 engine's idempotency surface, §13 S2). `base_revision_id` is
captured at draft time (OI-2 accept-staleness guard).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import GenerationJob
from app.db.repositories import ChapterJobInFlightError, ReferenceViolationError

_SELECT_COLS = """
  id, user_id, project_id, outline_node_id, operation, mode, status, llm_job_id,
  input, result, critic, target_chapter_id, base_revision_id, target_revision_id,
  cost_usd, idempotency_key, created_at, updated_at
"""

# Active = not yet terminal. Used by the M6 engine to cancel an in-flight job
# before starting a new one for the same node (§13 S2).
_ACTIVE_STATUSES = ("pending", "running")

# Advisory-lock namespace for the chapter-level in-flight guard (Cycle-2). MUST
# differ from outline's _DECOMPOSE_COMMIT_LOCK_NS (0x10AF) so the two locks never
# contend on a shared hashtext slot. Paired with hashtext("{project}:{chapter}").
_CHAPTER_JOB_LOCK_NS = 0x10B0


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

    async def create_chapter_job_guarded(
        self,
        user_id: UUID,
        project_id: UUID,
        chapter_id: UUID,
        *,
        operation: str,
        mode: str = "auto",
        status: str = "running",
        input: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        stale_secs: int = 1800,
    ) -> tuple[GenerationJob, bool]:
        """Create a CHAPTER-LEVEL job (``outline_node_id=None``) behind an
        in-flight guard. Returns ``(job, created)``; raises
        ``ChapterJobInFlightError`` when a concurrent active job blocks it.

        Chapter generate and stitch both persist the SAME book chapter draft, so a
        second concurrent chapter-level job for the same chapter double-spends the
        LLM and races the persist. A per-(project, chapter) advisory xact lock
        serializes the whole check+create — a plain SELECT takes no lock, so two
        no-key concurrent submits would both see "no active job" and both run
        (the Cycle-1 decompose-commit TOCTOU lesson). Under the lock, in order:

          1. **Replay first** — if `idempotency_key` already exists for this user,
             return that job (``created=False``). A same-key replay is NOT a
             concurrent duplicate, so it must bypass the guard (else a replay of a
             still-running job would 409 — AC#2).
          2. **Guard** — if ANY active (pending/running) chapter-level job exists
             for this chapter (regardless of operation: a running generate blocks a
             stitch and vice-versa, since both write the draft), raise
             ``ChapterJobInFlightError(active_job_id)`` → router 409.
          3. **Create** — INSERT the new job (reusing ``create`` on the same conn so
             it keeps the ON CONFLICT replay-safety) and return ``(job, True)``.

        The lock releases at Tx commit — BEFORE the minutes-long generation runs,
        so it never holds a connection across the LLM call. `chapter_id` is matched
        via ``input->>'chapter_id'`` (callers must put it in `input`).

        ``stale_secs`` bounds the guard: a job ``running`` longer than this is
        presumed dead (a mid-generation crash/kill orphans it as ``running`` and
        there is no reaper — /review-impl Cycle-2 #1), so it no longer blocks a
        chapter forever. Must exceed worst-case generation wall-clock.

        NOTE (/review-impl Cycle-2 #3): the replay match is on `idempotency_key`
        alone (system-wide idempotency contract — the key, not the chapter, is the
        dedup unit), so reusing one key across chapters replays the first job. That
        is existing `create()` semantics, intentionally not changed here."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0, stale_secs))
        async with self._pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                    _CHAPTER_JOB_LOCK_NS, f"{project_id}:{chapter_id}",
                )
                # 0. Opportunistic reap (D-COMP-CHAPTER-INFLIGHT-REAPER): mark THIS
                # chapter's STALE node-less jobs failed — the ones the guard's
                # `created_at > cutoff` filter (step 2) intentionally skips. Keeps a
                # crash-orphaned `running` row from lingering; the periodic sweep is
                # the global backstop. Under the lock, so it can't race the guard.
                await c.execute(
                    """
                    UPDATE generation_job SET status = 'failed', updated_at = now()
                    WHERE user_id = $1 AND project_id = $2 AND outline_node_id IS NULL
                      AND input->>'chapter_id' = $3 AND status = ANY($4::text[])
                      AND created_at <= $5
                    """,
                    user_id, project_id, str(chapter_id), list(_ACTIVE_STATUSES), cutoff,
                )
                # 1. Replay-under-lock: a same-key replay returns the existing job
                # and must short-circuit BEFORE the guard. Scoped to user_id (the
                # idempotency index is global on the key) so a cross-user key
                # collision falls through to create()'s cross-user handling.
                if idempotency_key:
                    existing = await c.fetchrow(
                        f"SELECT {_SELECT_COLS} FROM generation_job "
                        f"WHERE user_id = $1 AND idempotency_key = $2",
                        user_id, idempotency_key,
                    )
                    if existing is not None:
                        return _row_to_job(existing), False
                # 2. In-flight guard: any RECENT active chapter-level job for THIS
                # chapter. The `created_at > cutoff` bound presumes a job orphaned
                # in `running` past the staleness window is dead, so a crash can't
                # lock the chapter out forever (#1).
                active = await c.fetchrow(
                    """
                    SELECT id FROM generation_job
                    WHERE user_id = $1 AND project_id = $2
                      AND outline_node_id IS NULL
                      AND input->>'chapter_id' = $3
                      AND status = ANY($4::text[])
                      AND created_at > $5
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    user_id, project_id, str(chapter_id), list(_ACTIVE_STATUSES), cutoff,
                )
                if active is not None:
                    raise ChapterJobInFlightError(str(active["id"]))
                # 3. Create under the same conn (shares the Tx + lock).
                return await self.create(
                    user_id, project_id, operation=operation, outline_node_id=None,
                    mode=mode, status=status, input=input,
                    idempotency_key=idempotency_key, conn=c,
                )

    async def reap_stale_jobs(
        self, cutoff: datetime, *, exclude_operations: list[str] | None = None
    ) -> int:
        """Mark jobs orphaned in a non-terminal state as failed; return the count.

        A job still `pending`/`running` with `created_at <= cutoff` is presumed
        dead — its producer (a request handler / process) was killed mid-run and
        will never transition it (composition has no producer that resumes).
        Covers ALL job types (chapter-level + per-scene hygiene). Idempotent +
        multi-replica safe: a concurrent sweep just matches 0 already-reaped rows.
        The periodic backstop for D-COMP-CHAPTER-INFLIGHT-REAPER (the guard reaps
        per-chapter opportunistically; this catches never-re-requested chapters).

        ``exclude_operations`` (D-M4-REAPER-WORKER-CONFLICT): when the composition
        WORKER is enabled it IS a producer that resumes its own jobs (the
        ``updated_at``-based stuck-job sweeper in ``app/worker``). This
        ``created_at``-based reaper would otherwise spuriously fail a worker op
        whose legitimate wall-clock exceeds the window. So the loop passes the
        worker-op set (``SUPPORTED_OPERATIONS``): a job is worker-owned when its
        ``operation`` is in that set OR it carries an ``input->>'worker_op'``
        (generate/selection-edit stamp the canonical op there, not in
        ``operation``). Those are left to the worker's sweeper. ``None`` (worker
        off) → the original behavior verbatim (the inline producer never resumes,
        so reaping a stale inline job is correct)."""
        if exclude_operations:
            query = """
            UPDATE generation_job SET status = 'failed', updated_at = now()
            WHERE status = ANY($1::text[]) AND created_at <= $2
              AND NOT (operation = ANY($3::text[]) OR input->>'worker_op' IS NOT NULL)
            RETURNING id
            """
            async with self._pool.acquire() as c:
                rows = await c.fetch(query, list(_ACTIVE_STATUSES), cutoff, exclude_operations)
            return len(rows)
        query = """
        UPDATE generation_job SET status = 'failed', updated_at = now()
        WHERE status = ANY($1::text[]) AND created_at <= $2
        RETURNING id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, list(_ACTIVE_STATUSES), cutoff)
        return len(rows)

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

    async def prior_scene_drafts(
        self, user_id: UUID, project_id: UUID, chapter_id: UUID, before_story_order: int,
    ) -> list[str]:
        """S1 state-reinjection fallback (used when no accepted chapter draft yet):
        the latest COMPLETED generation winner text for each scene in `chapter_id`
        with ``story_order < before_story_order``, returned in story_order.

        ⚠ STRICTLY POSITION-BOUNDED (spoiler-safety, /review-impl H1): only scenes
        BEFORE the current one — a scene must never see its own future. Latest job
        per node (DISTINCT ON + created_at DESC). Empty text is filtered out.
        Scope: INTRA-chapter only (`o.chapter_id`) — cross-chapter context comes
        from the canon/timeline KG lenses, not here. M5 isolation: filters
        user_id/project_id on BOTH the job AND the joined node (defense-in-depth)."""
        query = """
        SELECT story_order, text FROM (
            SELECT DISTINCT ON (o.id)
                   o.story_order AS story_order, j.result->>'text' AS text
            FROM generation_job j
            JOIN outline_node o ON o.id = j.outline_node_id
            WHERE j.user_id = $1 AND j.project_id = $2
              AND o.user_id = $1 AND o.project_id = $2
              AND o.chapter_id = $3 AND o.kind = 'scene'
              AND o.story_order IS NOT NULL AND o.story_order < $4
              AND j.status = 'completed'
            ORDER BY o.id, j.created_at DESC
        ) latest
        WHERE text IS NOT NULL AND text <> ''
        ORDER BY story_order
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id, chapter_id, before_story_order)
        return [r["text"] for r in rows]

    async def chapter_scene_drafts(
        self, user_id: UUID, project_id: UUID, chapter_id: UUID,
    ) -> list[str]:
        """B3 stitch input — the latest COMPLETED generation winner text for EVERY
        scene in `chapter_id`, in story_order. Unlike `prior_scene_drafts` there is
        NO upper position bound (we want the whole chapter's drafts to stitch).
        Latest job per node (DISTINCT ON + created_at DESC); empty text filtered.
        M5 isolation: user_id/project_id on BOTH the job AND the joined node."""
        query = """
        SELECT text FROM (
            SELECT DISTINCT ON (o.id)
                   o.story_order AS story_order, j.result->>'text' AS text
            FROM generation_job j
            JOIN outline_node o ON o.id = j.outline_node_id
            WHERE j.user_id = $1 AND j.project_id = $2
              AND o.user_id = $1 AND o.project_id = $2
              AND o.chapter_id = $3 AND o.kind = 'scene'
              AND o.story_order IS NOT NULL
              AND j.status = 'completed'
            ORDER BY o.id, j.created_at DESC
        ) latest
        WHERE text IS NOT NULL AND text <> ''
        ORDER BY story_order
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id, chapter_id)
        return [r["text"] for r in rows]

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
