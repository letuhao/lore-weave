"""generation_job repository — AI generation + critic tracking (§1.2/§5).

SCOPE RULE (BPS-1 package re-key, spec 25 §Repo/service layer — supersedes the
old M5 per-user isolation): READ methods take `project_id` (the Work partition
key, PM-3) and NO user_id; WRITE methods additionally take `created_by` — a
plain actor stamp, STORED for BYOK spend attribution (25 T5), never filtered
on. Access is decided BEFORE the repo, at the gate (E0 grant on the row's
`book_id`); inserts derive `book_id` from `composition_work` inside the
statement. `create` honours `idempotency_key` via the partial UNIQUE index
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
from loreweave_jobs import emit_job_event

from app.clients.model_name import resolve_model_name

from app.db.models import GenerationJob
from app.db.repositories import ChapterJobInFlightError, ReferenceViolationError
from app.worker.constants import is_worker_drivable

#: Unified Job Control Plane P1 — the service id stamped on every emitted JobEvent.
_JOB_SERVICE = "composition"


def _job_error(result: dict[str, Any] | None) -> dict[str, str] | None:
    """Map a failed job's ``result`` to the canonical JobEvent error shape, or None."""
    if not result:
        return None
    err = result.get("error")
    if err is None:
        return None
    if isinstance(err, dict):
        return {"code": str(err.get("code", "error")), "message": str(err.get("message", err))}
    return {"code": "error", "message": str(err)}

_SELECT_COLS = """
  id, created_by, project_id, book_id, outline_node_id, operation, mode, status,
  llm_job_id, input, result, critic, target_chapter_id, base_revision_id,
  target_revision_id, cost_usd, idempotency_key, created_at, updated_at
"""

# Active = not yet terminal. Used by the M6 engine to cancel an in-flight job
# before starting a new one for the same node (§13 S2).
_ACTIVE_STATUSES = ("pending", "running")

# Advisory-lock namespace for the chapter-level in-flight guard (Cycle-2). MUST
# differ from outline's _DECOMPOSE_COMMIT_LOCK_NS (0x10AF) so the two locks never
# contend on a shared hashtext slot. Paired with hashtext("{project}:{chapter}").
_CHAPTER_JOB_LOCK_NS = 0x10B0

# M3 (WS-B3 prose-persist-on-promote): the input marker that tags a SYNTHETIC
# completed generation_job carrying a promoted scene's prose (no LLM ran). The
# scene-prose persist endpoint writes one of these per promoted derivative scene so
# `prior_scene_drafts` / `chapter_scene_drafts` (and gather_recent's fallback) read
# the take prose back — with NO new table. Idempotent on (project_id,
# outline_node_id): a re-promote overwrites the prior promoted row, never duplicates.
_PROMOTED_SCENE_PROSE_KIND = "promoted_scene_prose"

#: BE-7c — ops whose jobs are genuinely NOT Work-bound. Their ONLY scope key is
#: `created_by`. Keep this list HERE (in the writer), never in the DDL CHECK: a new
#: Work-less op must not need a migration (the
#: `migration-check-constraint-must-backfill-all-historical-blocks` trap).
UNBOUND_OPERATIONS = frozenset({"mine_motifs", "analyze_reference"})


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
        project_id: UUID,
        *,
        created_by: UUID,
        operation: str,
        outline_node_id: UUID | None = None,
        mode: str = "cowrite",
        status: str = "pending",
        input: dict[str, Any] | None = None,
        base_revision_id: UUID | None = None,
        idempotency_key: str | None = None,
        conn: asyncpg.Connection | None = None,
        model_name: str | None = None,
    ) -> tuple[GenerationJob, bool]:
        """Insert a job. Returns ``(job, created)``.

        When `idempotency_key` is set and already exists for this project (the
        Work partition — the PM-10 dedup scope), the existing job is returned
        with ``created=False`` (no duplicate) — the replay-safe surface for
        POST /generate. The conflict target carries the index's partial
        predicate so it matches idx_generation_job_idem. `created_by` is the
        acting caller — a plain stamp (spend attribution rides the actor, 25
        T5), never a filter; `book_id` is derived from `composition_work`
        inside the statement so it can never be NULL.
        """
        # P4 usage emit — a whitelisted params dict (cheap, no I/O) + the resolved model
        # NAME on the create event; the projection's COALESCE keeps them across later
        # status events. cost_usd is not populated on this row yet → omitted.
        # The model-NAME resolve is HTTP, so it must NOT run inside a caller's tx (H1) —
        # create_chapter_job_guarded holds an in-flight row lock, so a 5s resolve there
        # would pin the tx/lock across the network call. D-JOBS-P4-COMPOSITION-GUARDED-MODEL:
        # the guarded caller now resolves the name OUT-OF-TX and passes `model_name`, so the
        # auto-draft path emits the real name too. Precedence: caller-provided name >
        # self-resolve (only on the self-managed-tx path, conn is None) > None.
        _in = input or {}
        _model_name = model_name
        if _model_name is None and conn is None:
            _model_name = await resolve_model_name(_in.get("model_source"), _in.get("model_ref"))
        _job_params = {
            "model": _model_name,
            "model_ref": _in.get("model_ref"),
            "operation": operation,
            "mode": mode,
            "reasoning": _in.get("reasoning"),
            "reasoning_effort": _in.get("reasoning_effort"),
            # D-JOBS-P4-RETRY-COMPOSITION — per-job retryability signal for the unified
            # control plane. A composition job is server-reconstructable iff it is
            # worker-drivable (its input carries the full bearer-resolved context the
            # worker re-runs from). The inline/streamed cowrite path packs its prompt
            # live and never persists it → retryable=False (the FE re-generate is its
            # retry surface). jobs-service `derive_control_caps` reads this off the
            # projection's params to gate the Retry button per-job (kind alone can't
            # tell the worker path from the inline path — both emit the same free-form
            # operation as `kind`).
            "retryable": is_worker_drivable(operation, _in),
        }

        async def _do(c: asyncpg.Connection) -> tuple[GenerationJob, bool]:
            if outline_node_id is not None:
                # Defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): the job's node must
                # live in THIS project (the FK only proves existence).
                owned = await c.fetchval(
                    "SELECT 1 FROM outline_node "
                    "WHERE project_id = $1 AND id = $2",
                    project_id, outline_node_id,
                )
                if owned is None:
                    raise ReferenceViolationError(
                        f"outline_node {outline_node_id} is not a node in this project"
                    )
            row = await c.fetchrow(
                f"""
                INSERT INTO generation_job
                  (created_by, project_id, book_id, outline_node_id, operation,
                   mode, status, input, base_revision_id, idempotency_key)
                SELECT $1, $2, w.book_id, $3, $4,
                       $5, $6, $7::jsonb, $8, $9
                FROM composition_work w
                WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
                RETURNING {_SELECT_COLS}
                """,
                created_by, project_id, outline_node_id, operation, mode, status,
                json.dumps(input or {}), base_revision_id, idempotency_key,
            )
            if row is not None:
                job = _row_to_job(row)
                # Unified Job Control Plane P1 — emit the lifecycle event in the SAME
                # tx/conn as the INSERT (only on a genuinely-new job, not a replay).
                # owner_user_id = the actor stamp: BYOK spend attribution (25 T5).
                await emit_job_event(
                    c, service=_JOB_SERVICE, job_id=str(job.id),
                    owner_user_id=str(job.created_by), kind=job.operation, status=job.status,
                    model=_model_name, params=_job_params,
                )
                return job, True
            # No row: either an idempotency conflict OR the INSERT … SELECT found no
            # composition_work to derive book_id from — distinguish loudly. First,
            # the replay path: return the existing job (scoped to this project so a
            # cross-project key collision can't leak a row).
            if idempotency_key is not None:
                existing = await c.fetchrow(
                    f"SELECT {_SELECT_COLS} FROM generation_job "
                    f"WHERE project_id = $1 AND idempotency_key = $2",
                    project_id, idempotency_key,
                )
                if existing is not None:
                    return _row_to_job(existing), False
            has_work = await c.fetchval(
                "SELECT 1 FROM composition_work WHERE project_id = $1", project_id,
            )
            if has_work is None:
                # Dangling project_id (PM-7 spirit): never mint a job without a
                # book_id home — and never misreport it as a key conflict.
                raise ReferenceViolationError(
                    f"project {project_id} has no composition_work row"
                )
            # Key belongs to another project → behave as not-found-for-us; the
            # router maps this to a conflict rather than silently reusing.
            raise KeyError("idempotency_key conflict across projects")

        if conn is not None:
            return await _do(conn)
        async with self._pool.acquire() as c:
            async with c.transaction():  # INSERT + emit_job_event atomic (H1)
                return await _do(c)

    async def create_unbound(
        self,
        *,
        created_by: UUID,
        operation: str,
        input: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> GenerationJob:
        """Insert an OWNER-scoped, Work-LESS job (BE-7c). project_id/book_id are NULL —
        the row's ONLY scope key is `created_by`, and every read of it MUST gate on that
        (see GET /motif-jobs/{job_id}).

        `create()` cannot express this: it DERIVES book_id from composition_work inside
        the INSERT…SELECT, and a corpus/book motif-mine or an arc-import has no Work. The
        old code papered over that with a synthetic uuid4() project_id, which matched no
        Work row ⇒ zero rows inserted ⇒ ReferenceViolationError ⇒ /actions/confirm 500'd
        AFTER burning the confirm token and reserving the billing hold. The user paid and
        got nothing. NEVER back-fill a phantom composition_work per mine.

        Raises ValueError for an operation not in UNBOUND_OPERATIONS — a Work-BOUND op
        arriving here would silently lose its tenancy keys, which is a tenancy defect,
        not a shortcut.
        """
        if operation not in UNBOUND_OPERATIONS:
            raise ValueError(
                f"operation {operation!r} is Work-bound — use create(); "
                f"unbound ops are {sorted(UNBOUND_OPERATIONS)}"
            )
        _in = input or {}
        # Resolve the model NAME out-of-tx (H1: it is HTTP; never inside the tx below).
        _model_name = await resolve_model_name(_in.get("model_source"), _in.get("model_ref"))
        _job_params = {
            "model": _model_name,
            "model_ref": _in.get("model_ref"),
            "operation": operation,
            "mode": "auto",
            "reasoning": _in.get("reasoning"),
            "reasoning_effort": _in.get("reasoning_effort"),
            "retryable": is_worker_drivable(operation, _in),
        }
        async with self._pool.acquire() as c:
            async with c.transaction():  # INSERT + emit_job_event atomic (H1)
                row = await c.fetchrow(
                    f"""
                    INSERT INTO generation_job
                      (created_by, project_id, book_id, operation, mode, status, input)
                    VALUES ($1, NULL, NULL, $2, 'auto', $3, $4::jsonb)
                    RETURNING {_SELECT_COLS}
                    """,
                    created_by, operation, status, json.dumps(_in),
                )
                job = _row_to_job(row)
                # The job-event plane is OWNER-keyed, not project-keyed — this works
                # unchanged for a Work-less job. Let it raise → the tx rolls back → the
                # sweeper redelivers (transactional-outbox-must-not-swallow).
                await emit_job_event(
                    c, service=_JOB_SERVICE, job_id=str(job.id),
                    owner_user_id=str(job.created_by), kind=job.operation, status=job.status,
                    model=_model_name, params=_job_params,
                )
                return job

    async def create_chapter_job_guarded(
        self,
        project_id: UUID,
        chapter_id: UUID,
        *,
        created_by: UUID,
        operation: str,
        mode: str = "auto",
        status: str = "running",
        input: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        stale_secs: int = 1800,
        model_name: str | None = None,
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

          1. **Replay first** — if `idempotency_key` already exists for this
             project, return that job (``created=False``). A same-key replay is NOT
             a concurrent duplicate, so it must bypass the guard (else a replay of a
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
                    WHERE project_id = $1 AND outline_node_id IS NULL
                      AND input->>'chapter_id' = $2 AND status = ANY($3::text[])
                      AND created_at <= $4
                    """,
                    project_id, str(chapter_id), list(_ACTIVE_STATUSES), cutoff,
                )
                # 1. Replay-under-lock: a same-key replay returns the existing job
                # and must short-circuit BEFORE the guard. Scoped to project_id (the
                # idempotency index is global on the key) so a cross-project key
                # collision falls through to create()'s cross-project handling.
                if idempotency_key:
                    existing = await c.fetchrow(
                        f"SELECT {_SELECT_COLS} FROM generation_job "
                        f"WHERE project_id = $1 AND idempotency_key = $2",
                        project_id, idempotency_key,
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
                    WHERE project_id = $1
                      AND outline_node_id IS NULL
                      AND input->>'chapter_id' = $2
                      AND status = ANY($3::text[])
                      AND created_at > $4
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    project_id, str(chapter_id), list(_ACTIVE_STATUSES), cutoff,
                )
                if active is not None:
                    raise ChapterJobInFlightError(str(active["id"]))
                # 3. Create under the same conn (shares the Tx + lock). `model_name` was
                # resolved OUT-OF-TX by the caller (D-JOBS-P4-COMPOSITION-GUARDED-MODEL) so
                # the create emit carries the real name without an in-lock HTTP call.
                return await self.create(
                    project_id, created_by=created_by, operation=operation,
                    outline_node_id=None, mode=mode, status=status, input=input,
                    idempotency_key=idempotency_key, conn=c, model_name=model_name,
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

    async def get(self, job_id: UUID) -> GenerationJob | None:
        query = f"SELECT {_SELECT_COLS} FROM generation_job WHERE id = $1"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, job_id)
        return _row_to_job(row) if row else None

    async def get_by_idempotency_key(
        self, project_id: UUID, key: str
    ) -> GenerationJob | None:
        query = (
            f"SELECT {_SELECT_COLS} FROM generation_job "
            f"WHERE project_id = $1 AND idempotency_key = $2"
        )
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, key)
        return _row_to_job(row) if row else None

    async def list_active_for_node(
        self, project_id: UUID, outline_node_id: UUID
    ) -> list[GenerationJob]:
        """Pending/running jobs for a node — the M6 cancel-in-flight input."""
        query = f"""
        SELECT {_SELECT_COLS} FROM generation_job
        WHERE project_id = $1 AND outline_node_id = $2
          AND status = ANY($3::text[])
        ORDER BY created_at
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, outline_node_id, list(_ACTIVE_STATUSES))
        return [_row_to_job(r) for r in rows]

    async def prior_scene_drafts(
        self, project_id: UUID, chapter_id: UUID, before_story_order: int,
    ) -> list[str]:
        """S1 state-reinjection fallback (used when no accepted chapter draft yet):
        the latest COMPLETED generation winner text for each scene in `chapter_id`
        with ``story_order < before_story_order``, returned in story_order.

        ⚠ STRICTLY POSITION-BOUNDED (spoiler-safety, /review-impl H1): only scenes
        BEFORE the current one — a scene must never see its own future. Latest job
        per node (DISTINCT ON + created_at DESC). Empty text is filtered out.
        Scope: INTRA-chapter only (`o.chapter_id`) — cross-chapter context comes
        from the canon/timeline KG lenses, not here. Package tenancy (25 PM-3):
        project_id filtered on BOTH the job AND the joined node (the kinds-bug
        double-filter rule)."""
        query = """
        SELECT story_order, text FROM (
            SELECT DISTINCT ON (o.id)
                   o.story_order AS story_order, j.result->>'text' AS text
            FROM generation_job j
            JOIN outline_node o ON o.id = j.outline_node_id
            WHERE j.project_id = $1
              AND o.project_id = $1
              AND o.chapter_id = $2 AND o.kind = 'scene'
              AND o.story_order IS NOT NULL AND o.story_order < $3
              AND j.status = 'completed'
            ORDER BY o.id, j.created_at DESC
        ) latest
        WHERE text IS NOT NULL AND text <> ''
        ORDER BY story_order
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, chapter_id, before_story_order)
        return [r["text"] for r in rows]

    async def chapter_scene_drafts(
        self, project_id: UUID, chapter_id: UUID,
    ) -> list[dict[str, str]]:
        """B3 stitch input — the latest COMPLETED generation winner text for EVERY
        scene in `chapter_id`, in story_order, as `{title, text}` rows (F4
        D-SCENEMARKER-EMIT: the stitch prepends a `### title` scene-heading line
        per draft so the persisted chapter carries scene markers). Unlike
        `prior_scene_drafts` there is NO upper position bound (we want the whole
        chapter's drafts to stitch). Latest job per node (DISTINCT ON +
        created_at DESC); empty text filtered.
        Package tenancy (25 PM-3): project_id on BOTH the job AND the joined node."""
        query = """
        SELECT title, text FROM (
            SELECT DISTINCT ON (o.id)
                   o.story_order AS story_order, o.title AS title,
                   j.result->>'text' AS text
            FROM generation_job j
            JOIN outline_node o ON o.id = j.outline_node_id
            WHERE j.project_id = $1
              AND o.project_id = $1
              AND o.chapter_id = $2 AND o.kind = 'scene'
              AND o.story_order IS NOT NULL
              AND j.status = 'completed'
            ORDER BY o.id, j.created_at DESC
        ) latest
        WHERE text IS NOT NULL AND text <> ''
        ORDER BY story_order
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, chapter_id)
        return [{"title": r["title"] or "", "text": r["text"]} for r in rows]

    async def upsert_promoted_scene_prose(
        self, project_id: UUID, outline_node_id: UUID, text: str,
        *, created_by: UUID, idempotency_key: str | None = None,
    ) -> tuple[GenerationJob, int]:
        """M3 (WS-B3) — persist a promoted scene's PROSE into the synthetic-job store,
        keyed by `outline_node_id`, IDEMPOTENTLY on (project, node). Returns
        ``(job, version)`` where ``version`` is the per-node promote count (1 on the
        first promote, +1 on each re-promote / overwrite).

        Mechanism (NO new table): write a SYNTHETIC ``completed`` generation_job in
        the DERIVATIVE project with ``result = {text}`` + an input marker
        ``{kind: 'promoted_scene_prose', version}`` so `prior_scene_drafts` /
        `chapter_scene_drafts` (and gather_recent's fallback) read it back as the
        scene's draft. SOURCE-CLOBBER SAFE: this writes ONLY composition's own DB —
        it never touches book-service's shared chapter draft (the COW/tenancy belt).

        IDEMPOTENT on the node: under a per-(project, node) advisory xact lock,
        delete any EXISTING promoted-prose rows for this node, then insert the new
        one — so a re-promote / double-submit OVERWRITES, never duplicates. The
        version carries over (prior + 1) so the response reflects the promote count.

        Defense-in-depth (mirrors `create`): the node must be a scene in THIS
        project (the FK only proves existence) → ReferenceViolationError else.
        `created_by` is a plain actor stamp; `book_id` derives from
        `composition_work` inside the INSERT. Emits the lifecycle event in the
        same tx (a synthetic but real completed job the unified control plane
        should still mirror)."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                # Serialize concurrent promotes of the SAME node so the
                # delete-then-insert can't race a second submit into a duplicate
                # (a plain DELETE+INSERT under READ COMMITTED would let two
                # concurrent submits both delete-nothing then both insert).
                await c.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                    _CHAPTER_JOB_LOCK_NS, f"{project_id}:promoted:{outline_node_id}",
                )
                owned = await c.fetchval(
                    "SELECT 1 FROM outline_node "
                    "WHERE project_id = $1 AND id = $2 AND kind = 'scene'",
                    project_id, outline_node_id,
                )
                if owned is None:
                    raise ReferenceViolationError(
                        f"outline_node {outline_node_id} is not a scene in this project"
                    )
                # Idempotent overwrite: drop prior promoted rows for this node, but
                # carry the version forward so the count reflects every promote.
                prior_version = await c.fetchval(
                    """
                    SELECT max((input->>'version')::int) FROM generation_job
                    WHERE project_id = $1 AND outline_node_id = $2
                      AND input->>'kind' = $3
                    """,
                    project_id, outline_node_id, _PROMOTED_SCENE_PROSE_KIND,
                )
                version = (prior_version or 0) + 1
                await c.execute(
                    """
                    DELETE FROM generation_job
                    WHERE project_id = $1 AND outline_node_id = $2
                      AND input->>'kind' = $3
                    """,
                    project_id, outline_node_id, _PROMOTED_SCENE_PROSE_KIND,
                )
                # The natural dedup key is (project, node) — enforced by the
                # lock+delete above — so the optional request `idempotency_key` is
                # NOT written to the unique `idempotency_key` column (that would let a
                # key reused across DIFFERENT nodes 23505-collide, and it's redundant
                # with node-scoped idempotency). It's stashed in `input` for trace only.
                _input = {"kind": _PROMOTED_SCENE_PROSE_KIND, "version": version}
                if idempotency_key:
                    _input["idempotency_key"] = idempotency_key
                row = await c.fetchrow(
                    f"""
                    INSERT INTO generation_job
                      (created_by, project_id, book_id, outline_node_id, operation,
                       mode, status, input, result)
                    SELECT $1, $2, w.book_id, $3, $4,
                           'cowrite', 'completed', $5::jsonb, $6::jsonb
                    FROM composition_work w
                    WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
                    RETURNING {_SELECT_COLS}
                    """,
                    created_by, project_id, outline_node_id,
                    _PROMOTED_SCENE_PROSE_KIND,
                    json.dumps(_input), json.dumps({"text": text}),
                )
                if row is None:
                    # The INSERT … SELECT found no composition_work → dangling
                    # project_id. Loud failure (PM-7 spirit): never mint a job
                    # without a book_id home.
                    raise ReferenceViolationError(
                        f"project {project_id} has no composition_work row"
                    )
                job = _row_to_job(row)
                await emit_job_event(
                    c, service=_JOB_SERVICE, job_id=str(job.id),
                    owner_user_id=str(job.created_by), kind=job.operation, status=job.status,
                )
                return job, version

    async def update_status(
        self,
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
        job or None (missing)."""
        query = f"""
        UPDATE generation_job
        SET status = $2,
            result = COALESCE($3::jsonb, result),
            critic = COALESCE($4::jsonb, critic),
            llm_job_id = COALESCE($5, llm_job_id),
            target_chapter_id = COALESCE($6, target_chapter_id),
            target_revision_id = COALESCE($7, target_revision_id),
            cost_usd = COALESCE($8, cost_usd),
            updated_at = now()
        WHERE id = $1
        RETURNING {_SELECT_COLS}
        """
        args = (
            job_id, status, _jsonb(result), _jsonb(critic), llm_job_id,
            target_chapter_id, target_revision_id, cost_usd,
        )
        async def _do(c: asyncpg.Connection) -> GenerationJob | None:
            row = await c.fetchrow(query, *args)
            if row is None:
                return None
            job = _row_to_job(row)
            # Unified Job Control Plane P1 — emit the status transition in the SAME
            # tx/conn as the UPDATE (H1: status change + event commit atomically).
            await emit_job_event(
                c, service=_JOB_SERVICE, job_id=str(job.id),
                owner_user_id=str(job.created_by), kind=job.operation, status=status,
                error=_job_error(result) if status == "failed" else None,
            )
            return job

        if conn is not None:
            return await _do(conn)
        async with self._pool.acquire() as c:
            async with c.transaction():  # UPDATE + emit_job_event atomic (H1)
                return await _do(c)

    async def list_since(self, since: datetime, *, limit: int = 1000) -> list[GenerationJob]:
        """Reconcile snapshot (Unified Job Control Plane H1 backstop): generation jobs
        updated at/after `since`, oldest-first, capped. ALL actors/projects (the
        jobs-service projection mirrors every row; user-scoping is at its read API).
        Used by the jobs-service reconcile sweep to heal any outbox drift."""
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLS} FROM generation_job "
            f"WHERE updated_at >= $1 ORDER BY updated_at ASC LIMIT $2",
            since, limit,
        )
        return [_row_to_job(r) for r in rows]

    async def cancel(
        self, job_id: UUID, *, conn: asyncpg.Connection | None = None
    ) -> GenerationJob | None:
        """Race-safe cancel for the unified control plane (P3): CAS the row to
        'cancelled' ONLY from an active state. Returns the cancelled job, or None
        when nothing transitioned — i.e. the job is missing OR already terminal
        (the caller distinguishes those with a prior ``get``: get→None ⇒ 404,
        get-ok+cancel→None ⇒ 409). Access is gated BEFORE the repo (E0 grant on
        the row's book_id — the new-law chokepoint).

        Unlike ``update_status`` (a plain by-id UPDATE, used by the engine
        which already knows the job is active), this guards ``status = ANY(active)``
        so a control-plane cancel can never clobber a job that completed in the
        TOCTOU window. Emits the terminal event on the SAME conn as the UPDATE (H1),
        only on the winning CAS (mirrors the video-gen CAS ``fail``)."""
        query = f"""
        UPDATE generation_job
           SET status = 'cancelled', updated_at = now()
         WHERE id = $1 AND status = ANY($2::text[])
        RETURNING {_SELECT_COLS}
        """
        async def _do(c: asyncpg.Connection) -> GenerationJob | None:
            row = await c.fetchrow(query, job_id, list(_ACTIVE_STATUSES))
            if row is None:
                return None
            job = _row_to_job(row)
            await emit_job_event(
                c, service=_JOB_SERVICE, job_id=str(job.id),
                owner_user_id=str(job.created_by), kind=job.operation, status="cancelled",
            )
            return job

        if conn is not None:
            return await _do(conn)
        async with self._pool.acquire() as c:
            async with c.transaction():  # UPDATE + emit_job_event atomic (H1)
                return await _do(c)
