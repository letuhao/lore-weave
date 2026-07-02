"""authoring_runs repository (RAID Wave D2, DR-D).

Tenancy: every method takes owner_user_id and filters on it — a foreign/missing
run_id returns None (routers map to 404, no existence oracle). Every FSM
transition is a guarded ``UPDATE … WHERE status = ANY(from) RETURNING`` so a
raced double-transition loses cleanly (returns None), mirroring the OCC
discipline of the plan_forge/campaign drivers. The draft→gated transition may
raise ``asyncpg.UniqueViolationError`` from the active-book scope fence
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
  run_id, owner_user_id, book_id, plan_run_id, level, scope, budget_usd,
  spent_usd, tool_allowlist, params, breaker_state, status, current_unit,
  error_message, driver_id, driver_heartbeat_at, background,
  created_at, updated_at
"""

_UNIT_SELECT = """
  u.run_id, u.unit_index, u.chapter_id, u.status, u.pre_revision_id,
  u.post_revision_id, u.cost_usd, u.error_message, u.created_at, u.updated_at
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
        owner_user_id: UUID,
        book_id: UUID,
        *,
        plan_run_id: UUID,
        level: int,
        scope: list[str],
        budget_usd: Decimal,
        tool_allowlist: list[str],
        params: dict[str, Any] | None = None,
        background: bool = False,
    ) -> AuthoringRun:
        query = f"""
        INSERT INTO authoring_runs
          (owner_user_id, book_id, plan_run_id, level, scope, budget_usd,
           tool_allowlist, params, background)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8::jsonb, $9)
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                owner_user_id,
                book_id,
                plan_run_id,
                level,
                json.dumps(scope),
                budget_usd,
                json.dumps(tool_allowlist),
                json.dumps(params or {}),
                background,
            )
        return _row(row)

    async def get_for_owner(
        self, owner_user_id: UUID, run_id: UUID,
    ) -> AuthoringRun | None:
        query = f"""
        SELECT {_SELECT} FROM authoring_runs
        WHERE run_id = $1 AND owner_user_id = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, owner_user_id)
        return _row(row) if row else None

    async def get_by_id(self, run_id: UUID) -> AuthoringRun | None:
        """UNSCOPED read — Run Report path ONLY (D3): the router MUST grant-gate
        the caller on run.book_id (E0 VIEW; OwnershipError → 404, preserving the
        no-existence-oracle) before returning anything derived from this row.
        Every other read stays get_for_owner."""
        query = f"SELECT {_SELECT} FROM authoring_runs WHERE run_id = $1"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id)
        return _row(row) if row else None

    async def list_for_owner(
        self, owner_user_id: UUID, book_id: UUID, *, limit: int = 20,
    ) -> list[AuthoringRun]:
        query = f"""
        SELECT {_SELECT} FROM authoring_runs
        WHERE owner_user_id = $1 AND book_id = $2
        ORDER BY created_at DESC, run_id DESC
        LIMIT $3
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, owner_user_id, book_id, min(max(limit, 1), 50))
        return [_row(r) for r in rows]

    async def transition(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        *,
        from_statuses: tuple[AuthoringRunStatus, ...],
        to_status: AuthoringRunStatus,
        breaker_state: dict[str, Any] | None = None,
        error_message: str | None = None,
        claim_driver_id: str | None = None,
    ) -> AuthoringRun | None:
        """Guarded FSM transition. Returns the updated run, or None when the
        row is missing / not owned / not in a `from` status (lost race — the
        caller decides whether that is a 404 or a 409). May raise
        asyncpg.UniqueViolationError on →gated (active-book scope fence).
        `claim_driver_id` (D4): a →running transition additionally CLAIMS the
        run for that driver (driver_id + fresh heartbeat) in the SAME guarded
        UPDATE — no window where a run is running but unclaimed."""
        sets = ["status = $3", "updated_at = now()"]
        args: list[Any] = [run_id, owner_user_id, to_status]
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
        WHERE run_id = $1 AND owner_user_id = $2 AND status = ANY(${len(args)})
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _row(row) if row else None

    async def record_unit_progress(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        *,
        add_spent_usd: Decimal,
        current_unit: int,
    ) -> AuthoringRun | None:
        """Accumulate spend + advance the unit cursor after a unit completes.
        Deliberately status-agnostic: the unit DID run and its cost is real
        even if the run was paused mid-unit — never lose spend accounting."""
        query = f"""
        UPDATE authoring_runs
        SET spent_usd = spent_usd + $3, current_unit = $4, updated_at = now()
        WHERE run_id = $1 AND owner_user_id = $2
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, owner_user_id, add_spent_usd, current_unit,
            )
        return _row(row) if row else None

    # ── D4 durable driver — guarded claims + sweep ─────────────────────────

    async def heartbeat_claim(
        self, owner_user_id: UUID, run_id: UUID, driver_id: str,
    ) -> AuthoringRun | None:
        """Per-unit guarded claim (D4): ONE guarded UPDATE that both re-checks
        the run is still `running` AND owned by THIS driver, and bumps the
        heartbeat (the bump doubles as the claim). Returns the fresh row, or
        None → the driver must STOP (paused/failed/closed externally, or the
        sweep re-claimed the run for another driver after a stale heartbeat)."""
        query = f"""
        UPDATE authoring_runs
        SET driver_heartbeat_at = now(), updated_at = now()
        WHERE run_id = $1 AND owner_user_id = $2
          AND status = 'running' AND driver_id = $3
        RETURNING {_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, owner_user_id, driver_id)
        return _row(row) if row else None

    async def claim_stale_running(
        self, *, driver_id: str, stale_secs: int, limit: int,
    ) -> list[AuthoringRun]:
        """Sweep claim (D4, campaign claim_active_campaigns pattern): atomically
        claim up to `limit` `running` runs with NO live driver — heartbeat NULL
        or older than `stale_secs` (which must exceed the worst-case single-unit
        wall-clock, or a slow unit's run would be stolen mid-unit). Deliberately
        UNSCOPED by owner: the sweep is a system-level durability backstop — each
        resumed drive still runs AS the row's owner_user_id (tenancy preserved).
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
    return AuthoringRunUnit.model_validate(dict(row))


class AuthoringRunUnitsRepo:
    """Per-unit ledger (RAID Wave D3). Tenancy: the units table carries no owner
    column — every method takes owner_user_id and joins authoring_runs on it (the
    parent run's tenancy IS the units' tenancy; a foreign run yields None/[], no
    existence oracle). ``list_for_run`` is the one UNSCOPED read, for the Run
    Report path where the router already grant-gated VIEW on the run's book.
    Accept/reject use the same guarded-OCC discipline as the run FSM
    (``UPDATE … WHERE status = ANY(from) RETURNING``)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_pending(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        unit_index: int,
        chapter_id: UUID,
        *,
        pre_revision_id: UUID | None,
    ) -> AuthoringRunUnit | None:
        """Driver writes this BEFORE invoking the drafting seam. Upsert (not
        insert): a resume after a pause/crash re-runs the cursor unit, which
        must re-pin its pre-revision baseline and reset the row to pending."""
        query = f"""
        INSERT INTO authoring_run_units (run_id, unit_index, chapter_id, pre_revision_id)
        SELECT r.run_id, $3, $4, $5 FROM authoring_runs r
        WHERE r.run_id = $1 AND r.owner_user_id = $2
        ON CONFLICT (run_id, unit_index) DO UPDATE SET
          chapter_id = EXCLUDED.chapter_id,
          pre_revision_id = EXCLUDED.pre_revision_id,
          status = 'pending', post_revision_id = NULL, cost_usd = 0,
          error_message = NULL, updated_at = now()
        RETURNING {_UNIT_SELECT.replace("u.", "")}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, owner_user_id, unit_index, chapter_id, pre_revision_id,
            )
        return _unit_row(row) if row else None

    async def mark_drafted(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        unit_index: int,
        *,
        post_revision_id: UUID | None,
        cost_usd: Decimal,
        run_statuses: tuple[AuthoringRunStatus, ...] | None = None,
    ) -> AuthoringRunUnit | None:
        """`run_statuses` (D4 late-result guard): the driver passes
        ('running','paused') so a seam result landing AFTER the run was closed/
        failed cannot mint a drafted row — the caller then marks the unit failed
        ('run closed mid-flight') instead."""
        return await self.transition_unit(
            owner_user_id, run_id, unit_index,
            from_statuses=("pending",), to_status="drafted",
            post_revision_id=post_revision_id, cost_usd=cost_usd,
            run_statuses=run_statuses,
        )

    async def mark_failed(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        unit_index: int,
        *,
        error: str,
    ) -> AuthoringRunUnit | None:
        return await self.transition_unit(
            owner_user_id, run_id, unit_index,
            from_statuses=("pending",), to_status="failed",
            error_message=error,
        )

    async def transition_unit(
        self,
        owner_user_id: UUID,
        run_id: UUID,
        unit_index: int,
        *,
        from_statuses: tuple[AuthoringRunUnitStatus, ...],
        to_status: AuthoringRunUnitStatus,
        post_revision_id: UUID | None = None,
        cost_usd: Decimal | None = None,
        error_message: str | None = None,
        run_statuses: tuple[AuthoringRunStatus, ...] | None = None,
    ) -> AuthoringRunUnit | None:
        """Guarded unit transition (OCC, mirrors the run FSM). Returns None when
        the unit is missing / foreign / not in a `from` status (lost race).
        `run_statuses` (D4) additionally guards on the PARENT run's status in
        the same statement — the late-result-after-close fence."""
        sets = ["status = $4", "updated_at = now()"]
        args: list[Any] = [run_id, owner_user_id, unit_index, to_status]
        if post_revision_id is not None:
            args.append(post_revision_id)
            sets.append(f"post_revision_id = ${len(args)}")
        if cost_usd is not None:
            args.append(cost_usd)
            sets.append(f"cost_usd = ${len(args)}")
        if error_message is not None:
            args.append(error_message)
            sets.append(f"error_message = ${len(args)}")
        run_guard = ""
        if run_statuses is not None:
            args.append(list(run_statuses))
            run_guard = f" AND r.status = ANY(${len(args)})"
        args.append(list(from_statuses))
        query = f"""
        UPDATE authoring_run_units u SET {", ".join(sets)}
        FROM authoring_runs r
        WHERE u.run_id = $1 AND r.run_id = u.run_id AND r.owner_user_id = $2
          AND u.unit_index = $3 AND u.status = ANY(${len(args)}){run_guard}
        RETURNING {_UNIT_SELECT}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _unit_row(row) if row else None

    async def get_for_owner(
        self, owner_user_id: UUID, run_id: UUID, unit_index: int,
    ) -> AuthoringRunUnit | None:
        query = f"""
        SELECT {_UNIT_SELECT} FROM authoring_run_units u
        JOIN authoring_runs r ON r.run_id = u.run_id
        WHERE u.run_id = $1 AND r.owner_user_id = $2 AND u.unit_index = $3
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, owner_user_id, unit_index)
        return _unit_row(row) if row else None

    async def list_for_owner(
        self, owner_user_id: UUID, run_id: UUID,
    ) -> list[AuthoringRunUnit]:
        query = f"""
        SELECT {_UNIT_SELECT} FROM authoring_run_units u
        JOIN authoring_runs r ON r.run_id = u.run_id
        WHERE u.run_id = $1 AND r.owner_user_id = $2
        ORDER BY u.unit_index
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id, owner_user_id)
        return [_unit_row(r) for r in rows]

    async def list_for_run(self, run_id: UUID) -> list[AuthoringRunUnit]:
        """UNSCOPED — Run Report path only (router grant-gates VIEW first)."""
        query = f"""
        SELECT {_UNIT_SELECT} FROM authoring_run_units u
        WHERE u.run_id = $1
        ORDER BY u.unit_index
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id)
        return [_unit_row(r) for r in rows]
