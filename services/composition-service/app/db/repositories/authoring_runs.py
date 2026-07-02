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

from app.db.models import AuthoringRun, AuthoringRunStatus

_SELECT = """
  run_id, owner_user_id, book_id, plan_run_id, level, scope, budget_usd,
  spent_usd, tool_allowlist, params, breaker_state, status, current_unit,
  error_message, created_at, updated_at
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
    ) -> AuthoringRun:
        query = f"""
        INSERT INTO authoring_runs
          (owner_user_id, book_id, plan_run_id, level, scope, budget_usd,
           tool_allowlist, params)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8::jsonb)
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
    ) -> AuthoringRun | None:
        """Guarded FSM transition. Returns the updated run, or None when the
        row is missing / not owned / not in a `from` status (lost race — the
        caller decides whether that is a 404 or a 409). May raise
        asyncpg.UniqueViolationError on →gated (active-book scope fence)."""
        sets = ["status = $3", "updated_at = now()"]
        args: list[Any] = [run_id, owner_user_id, to_status]
        if breaker_state is not None:
            args.append(json.dumps(breaker_state))
            sets.append(f"breaker_state = ${len(args)}::jsonb")
        if error_message is not None:
            args.append(error_message)
            sets.append(f"error_message = ${len(args)}")
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
