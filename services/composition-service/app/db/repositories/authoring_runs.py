"""authoring_runs repository (RAID Wave D2, DR-D).

Tenancy (BPS re-key, spec 25 OQ-3): rows are BOOK-scoped — book-wide reads
filter by book_id, by-run-id reads return the row for the ROUTE to gate on its
book_id (the load-then-gate shape the Run Report path pioneered — access is
decided BEFORE the repo, at the E0 book-grant gate). `created_by` is a plain
actor stamp (stored at create, never filtered on); a missing id returns None
(routers map to 404, no existence oracle). Every FSM transition is a guarded
``UPDATE … WHERE status = ANY(from) RETURNING`` so a raced double-transition
loses cleanly (returns None), mirroring the OCC discipline of the
plan_forge/campaign drivers. The draft→gated transition may raise
``asyncpg.UniqueViolationError`` from the active-book scope fence
(uq_authoring_runs_active_book) — the service maps it to a 409 overlap.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import (
    AuthoringRun,
    AuthoringRunStatus,
    AuthoringRunUnit,
    AuthoringRunUnitStatus,
)

_SELECT = """
  run_id, created_by, book_id, plan_run_id, level, scope, budget_usd,
  spent_usd, tool_allowlist, params, breaker_state, status, current_unit,
  error_message, driver_id, driver_heartbeat_at, background,
  pause_after_each_unit, created_at, updated_at
"""

_UNIT_SELECT = """
  u.run_id, u.unit_index, u.chapter_id, u.status, u.pre_revision_id,
  u.post_revision_id, u.cost_usd, u.error_message, u.critic_verdict,
  u.job_id, u.created_at, u.updated_at
"""


def _row(row: asyncpg.Record) -> AuthoringRun:
    data = dict(row)
    for key in ("scope", "tool_allowlist", "params", "breaker_state"):
        v = data.get(key)
        if isinstance(v, str):
            data[key] = json.loads(v)
    return AuthoringRun.model_validate(data)


class AuthoringRunsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        created_by: UUID,
        book_id: UUID,
        *,
        plan_run_id: UUID,
        level: int,
        scope: list[str],
        budget_usd: Decimal,
        tool_allowlist: list[str],
        params: dict[str, Any] | None = None,
        background: bool = False,
        pause_after_each_unit: bool = True,
    ) -> AuthoringRun:
        query = f"""
        INSERT INTO authoring_runs
          (created_by, book_id, plan_run_id, level, scope, budget_usd,
           tool_allowlist, params, background, pause_after_each_unit)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8::jsonb, $9, $10)
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                created_by,
                book_id,
                plan_run_id,
                level,
                json.dumps(scope),
                budget_usd,
                json.dumps(tool_allowlist),
                json.dumps(params or {}),
                background,
                pause_after_each_unit,
            )
        return _row(row)

    async def get_by_id(self, run_id: UUID) -> AuthoringRun | None:
        """By-run-id read (OQ-3 load-then-gate): every caller MUST grant-gate
        on the returned row's book_id (E0; OwnershipError → 404, preserving the
        no-existence-oracle) before acting on anything derived from it — the
        parent scope of a client-supplied run_id IS the book gate."""
        query = f"SELECT {_SELECT} FROM authoring_runs WHERE run_id = $1"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id)
        return _row(row) if row else None

    async def list_for_book(
        self, book_id: UUID, *, limit: int = 20,
    ) -> list[AuthoringRun]:
        query = f"""
        SELECT {_SELECT} FROM authoring_runs
        WHERE book_id = $1
        ORDER BY created_at DESC, run_id DESC
        LIMIT $2
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id, min(max(limit, 1), 50))
        return [_row(r) for r in rows]

    async def transition(
        self,
        run_id: UUID,
        *,
        from_statuses: tuple[AuthoringRunStatus, ...],
        to_status: AuthoringRunStatus,
        breaker_state: dict[str, Any] | None = None,
        error_message: str | None = None,
        claim_driver_id: str | None = None,
    ) -> AuthoringRun | None:
        """Guarded FSM transition. Returns the updated run, or None when the
        row is missing / not in a `from` status (lost race — the caller decides
        whether that is a 404 or a 409). May raise
        asyncpg.UniqueViolationError on →gated (active-book scope fence).
        `claim_driver_id` (D4): a →running transition additionally CLAIMS the
        run for that driver (driver_id + fresh heartbeat) in the SAME guarded
        UPDATE — no window where a run is running but unclaimed."""
        sets = ["status = $2", "updated_at = now()"]
        args: list[Any] = [run_id, to_status]
        if breaker_state is not None:
            args.append(json.dumps(breaker_state))
            sets.append(f"breaker_state = ${len(args)}::jsonb")
        if error_message is not None:
            args.append(error_message)
            sets.append(f"error_message = ${len(args)}")
        if claim_driver_id is not None:
            args.append(claim_driver_id)
            sets.append(f"driver_id = ${len(args)}")
            sets.append("driver_heartbeat_at = now()")
        args.append(list(from_statuses))
        query = f"""
        UPDATE authoring_runs SET {", ".join(sets)}
        WHERE run_id = $1 AND status = ANY(${len(args)})
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _row(row) if row else None

    async def record_unit_progress(
        self,
        run_id: UUID,
        *,
        add_spent_usd: Decimal,
        current_unit: int,
        driver_id: str | None = None,
    ) -> AuthoringRun | None:
        """Accumulate spend + advance the unit cursor after a unit completes.
        The SPEND add is deliberately status/driver-agnostic: the unit DID run
        and its cost is real even if the run was paused or sweep-stolen
        mid-unit — never lose spend accounting. The CURSOR write is
        driver-fenced when `driver_id` is given (D4 late-write fence): a
        superseded driver landing after a sweep steal must not rewind the new
        driver's cursor and trigger a duplicate generation."""
        query = f"""
        UPDATE authoring_runs
        SET spent_usd = spent_usd + $2,
            current_unit = CASE
              WHEN $4::text IS NULL OR driver_id = $4 THEN $3
              ELSE current_unit
            END,
            updated_at = now()
        WHERE run_id = $1
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, add_spent_usd, current_unit, driver_id,
            )
        return _row(row) if row else None

    async def set_pause_policy(
        self, run_id: UUID, pause_after_each_unit: bool,
    ) -> AuthoringRun | None:
        """D-AGENT-MODE §20 D4a: flip the auto-pause-after-each-unit policy at
        create time OR mid-run (a run-header toggle). Allowed at any status
        EXCEPT 'closed' (nothing left to pause on a terminal run) — the guarded
        UPDATE excludes it directly rather than requiring the caller to pass an
        explicit from-status allowlist (unlike the FSM `transition()`, this is
        not itself an FSM transition)."""
        query = f"""
        UPDATE authoring_runs
        SET pause_after_each_unit = $2, updated_at = now()
        WHERE run_id = $1 AND status != 'closed'
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, pause_after_each_unit)
        return _row(row) if row else None

    # ── D4 durable driver — guarded claims + sweep ─────────────────────────

    async def heartbeat_claim(
        self, run_id: UUID, driver_id: str,
    ) -> AuthoringRun | None:
        """Per-unit guarded claim (D4): ONE guarded UPDATE that both re-checks
        the run is still `running` AND owned by THIS driver, and bumps the
        heartbeat (the bump doubles as the claim). Returns the fresh row, or
        None → the driver must STOP (paused/failed/closed externally, or the
        sweep re-claimed the run for another driver after a stale heartbeat)."""
        query = f"""
        UPDATE authoring_runs
        SET driver_heartbeat_at = now(), updated_at = now()
        WHERE run_id = $1 AND status = 'running' AND driver_id = $2
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, driver_id)
        return _row(row) if row else None

    async def release_claim(self, run_id: UUID, driver_id: str) -> bool:
        """D4: give a claimed-but-undriven run straight back to the sweep by
        NULLing its heartbeat (a start/resume/sweep claim whose driver-task
        spawn was deferred at DRIVER_MAX_INFLIGHT would otherwise sit
        claimed-with-a-fresh-heartbeat for the whole stale window before any
        sweeper could touch it). Guarded on driver_id=mine so a release can
        never yank a run another driver claimed in between."""
        query = """
        UPDATE authoring_runs
        SET driver_heartbeat_at = NULL, updated_at = now()
        WHERE run_id = $1 AND status = 'running' AND driver_id = $2
        RETURNING run_id
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, driver_id)
        return row is not None

    async def claim_stale_running(
        self, *, driver_id: str, stale_secs: int, limit: int,
    ) -> list[AuthoringRun]:
        """Sweep claim (D4, campaign claim_active_campaigns pattern): atomically
        claim up to `limit` `running` runs with NO live driver — heartbeat NULL
        or older than `stale_secs` (which must exceed the worst-case single-unit
        wall-clock, or a slow unit's run would be stolen mid-unit). Deliberately
        UNSCOPED: the sweep is a system-level durability backstop — each resumed
        drive still runs AS the row's `created_by` actor stamp (spend
        attribution + bearer identity preserved, the F7 sweeper rule).
        FOR UPDATE SKIP LOCKED gives disjoint claims across concurrent sweepers;
        a run whose driver died in THIS process is also re-claimable (same
        driver_id, stale heartbeat) — the in-process task registry dedupes."""
        query = f"""
        UPDATE authoring_runs
        SET driver_id = $1, driver_heartbeat_at = now(), updated_at = now()
        WHERE run_id IN (
            SELECT run_id FROM authoring_runs
            WHERE status = 'running'
              AND (driver_heartbeat_at IS NULL
                   OR driver_heartbeat_at < now() - make_interval(secs => $2::int))
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT $3::int
        )
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, driver_id, stale_secs, limit)
        return [_row(r) for r in rows]


def _unit_row(row: asyncpg.Record) -> AuthoringRunUnit:
    data = dict(row)
    v = data.get("critic_verdict")
    if isinstance(v, str):  # jsonb comes back as text without a codec
        data["critic_verdict"] = json.loads(v)
    return AuthoringRunUnit.model_validate(data)


class AuthoringRunUnitsRepo:
    """Per-unit ledger (RAID Wave D3). The units table carries no scope column
    of its own — its scope IS the parent run's book (OQ-3): the route gates the
    run's book_id (E0) before any unit read/write, and repo predicates key on
    run_id (plus the parent-run join where a write must also guard the run's
    status/driver — the D4 late-result fence). A foreign/missing key yields
    None/[] (no existence oracle). Accept/reject use the same guarded-OCC
    discipline as the run FSM (``UPDATE … WHERE status = ANY(from)
    RETURNING``)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_pending(
        self,
        run_id: UUID,
        unit_index: int,
        chapter_id: UUID,
        *,
        pre_revision_id: UUID | None,
    ) -> AuthoringRunUnit | None:
        """Driver writes this BEFORE invoking the drafting seam. Upsert (not
        insert): a resume after a pause/crash re-runs the cursor unit, which
        must re-pin its pre-revision baseline and reset the row to pending.
        The INSERT … SELECT keeps the parent-run existence guard (a vanished
        run yields None, never an orphan row)."""
        query = f"""
        INSERT INTO authoring_run_units (run_id, unit_index, chapter_id, pre_revision_id)
        SELECT r.run_id, $2, $3, $4 FROM authoring_runs r
        WHERE r.run_id = $1
        ON CONFLICT (run_id, unit_index) DO UPDATE SET
          chapter_id = EXCLUDED.chapter_id,
          pre_revision_id = EXCLUDED.pre_revision_id,
          status = 'pending', post_revision_id = NULL, cost_usd = 0,
          error_message = NULL, critic_verdict = NULL, updated_at = now()
        RETURNING {_UNIT_SELECT.replace("u.", "")}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, unit_index, chapter_id, pre_revision_id,
            )
        return _unit_row(row) if row else None

    async def mark_drafted(
        self,
        run_id: UUID,
        unit_index: int,
        *,
        post_revision_id: UUID | None,
        cost_usd: Decimal,
        job_id: UUID | None = None,
        run_statuses: tuple[AuthoringRunStatus, ...] | None = None,
        run_driver_id: str | None = None,
    ) -> AuthoringRunUnit | None:
        """`run_statuses` (D4 late-result guard): the driver passes
        ('running','paused') so a seam result landing AFTER the run was closed/
        failed cannot mint a drafted row — the caller then marks the unit failed
        ('run closed mid-flight') instead. `run_driver_id` extends the fence to
        sweep steals: a superseded driver's late result cannot mint a drafted
        row over the new driver's in-progress re-run of the same unit."""
        return await self.transition_unit(
            run_id, unit_index,
            from_statuses=("pending",), to_status="drafted",
            post_revision_id=post_revision_id, cost_usd=cost_usd, job_id=job_id,
            run_statuses=run_statuses, run_driver_id=run_driver_id,
        )

    async def set_critic_verdict(
        self,
        run_id: UUID,
        unit_index: int,
        *,
        verdict: dict[str, Any],
    ) -> AuthoringRunUnit | None:
        """D5: land the continuity-critic verdict on a DRAFTED unit row (the
        critic runs post-draft; the status guard is the same OCC fence as the
        review transitions — a row raced away from `drafted` loses cleanly and
        returns None)."""
        query = f"""
        UPDATE authoring_run_units u
        SET critic_verdict = $3::jsonb, updated_at = now()
        WHERE u.run_id = $1 AND u.unit_index = $2 AND u.status = 'drafted'
        RETURNING {_UNIT_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, unit_index, json.dumps(verdict),
            )
        return _unit_row(row) if row else None

    async def mark_failed(
        self,
        run_id: UUID,
        unit_index: int,
        *,
        error: str,
    ) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            run_id, unit_index,
            from_statuses=("pending",), to_status="failed",
            error_message=error,
        )

    async def transition_unit(
        self,
        run_id: UUID,
        unit_index: int,
        *,
        from_statuses: tuple[AuthoringRunUnitStatus, ...],
        to_status: AuthoringRunUnitStatus,
        post_revision_id: UUID | None = None,
        cost_usd: Decimal | None = None,
        error_message: str | None = None,
        job_id: UUID | None = None,
        run_statuses: tuple[AuthoringRunStatus, ...] | None = None,
        run_driver_id: str | None = None,
    ) -> AuthoringRunUnit | None:
        """Guarded unit transition (OCC, mirrors the run FSM). Returns None when
        the unit is missing / not in a `from` status (lost race).
        `run_statuses` (D4) additionally guards on the PARENT run's status, and
        `run_driver_id` on the parent's current driver, in the same statement —
        the late-result fence (close/fail AND sweep-steal variants)."""
        sets = ["status = $3", "updated_at = now()"]
        args: list[Any] = [run_id, unit_index, to_status]
        if post_revision_id is not None:
            args.append(post_revision_id)
            sets.append(f"post_revision_id = ${len(args)}")
        if cost_usd is not None:
            args.append(cost_usd)
            sets.append(f"cost_usd = ${len(args)}")
        if job_id is not None:
            # BE-9a: the generation_job that drafted this unit — so accept/reject can attach a
            # correction to it. Nullable (never backfilled): a pre-BE-9a unit records nothing.
            args.append(job_id)
            sets.append(f"job_id = ${len(args)}")
        if error_message is not None:
            args.append(error_message)
            sets.append(f"error_message = ${len(args)}")
        run_guard = ""
        if run_statuses is not None:
            args.append(list(run_statuses))
            run_guard = f" AND r.status = ANY(${len(args)})"
        if run_driver_id is not None:
            args.append(run_driver_id)
            run_guard += f" AND r.driver_id = ${len(args)}"
        args.append(list(from_statuses))
        query = f"""
        UPDATE authoring_run_units u SET {", ".join(sets)}
        FROM authoring_runs r
        WHERE u.run_id = $1 AND r.run_id = u.run_id
          AND u.unit_index = $2 AND u.status = ANY(${len(args)}){run_guard}
        RETURNING {_UNIT_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _unit_row(row) if row else None

    async def get_for_run(
        self, run_id: UUID, unit_index: int,
    ) -> AuthoringRunUnit | None:
        query = f"""
        SELECT {_UNIT_SELECT} FROM authoring_run_units u
        WHERE u.run_id = $1 AND u.unit_index = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, unit_index)
        return _unit_row(row) if row else None

    async def list_for_run(self, run_id: UUID) -> list[AuthoringRunUnit]:
        """All unit rows for a run — the caller has already gated the parent
        run's book (OQ-3 load-then-gate)."""
        query = f"""
        SELECT {_UNIT_SELECT} FROM authoring_run_units u
        WHERE u.run_id = $1
        ORDER BY u.unit_index
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id)
        return [_unit_row(r) for r in rows]
