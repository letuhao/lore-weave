"""C14b — sweeper_state repository for resumable background sweepers.

Wraps the ``sweeper_state`` table introduced in migrate.py. Any
background sweeper that iterates over users (per-user reconciler,
future per-tenant migrations, etc.) can persist its cursor here and
resume mid-list after a crash.

Usage pattern (see reconcile_evidence_count_scheduler):

    async def sweep(..., repo: SweeperStateRepo):
        last_user_id = await repo.read_cursor('reconcile_evidence_count')
        # `last_user_id IS None` → fresh sweep from the start
        users = await fetch_users(after=last_user_id)
        for uid in users:
            await do_work(uid)
            await repo.upsert_cursor('reconcile_evidence_count', uid)
        # natural completion — clear cursor so next sweep starts fresh
        await repo.clear_cursor('reconcile_evidence_count')

Crash semantics:
  - If ``do_work`` raises, the upsert is skipped → cursor stays at the
    prior user → next sweep resumes from the next unprocessed user.
  - If the sweep itself exits via exception AFTER the for loop but
    BEFORE the clear (e.g. metrics call raises), the cursor persists
    at the last user. Next sweep reads the cursor + seeks past it →
    fetches zero users → naturally completes with no work.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

__all__ = ["SweeperStateRepo"]


class SweeperStateRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def read_cursor(self, sweeper_name: str) -> UUID | None:
        """Return the sweeper's persisted ``last_user_id``, or ``None``
        if no cursor row exists (fresh or post-completion state).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_user_id FROM sweeper_state "
                "WHERE sweeper_name = $1",
                sweeper_name,
            )
        if row is None:
            return None
        return row["last_user_id"]

    async def read_cursor_full(
        self, sweeper_name: str,
    ) -> tuple[UUID | None, dict[str, Any]] | None:
        """Return ``(last_user_id, last_scope)`` tuple, or ``None`` if
        no row. Used when a sweeper cares about ``last_scope`` beyond
        the user_id (e.g. per-user-per-project sub-iteration).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_user_id, last_scope FROM sweeper_state "
                "WHERE sweeper_name = $1",
                sweeper_name,
            )
        if row is None:
            return None
        # asyncpg deserializes JSONB to a str; convert to dict for the
        # caller. An empty-object default (migrate.py DDL) keeps this
        # consistently a dict.
        scope_raw = row["last_scope"]
        scope: dict[str, Any]
        if isinstance(scope_raw, str):
            scope = json.loads(scope_raw)
        elif isinstance(scope_raw, dict):
            scope = scope_raw
        else:
            scope = {}
        return row["last_user_id"], scope

    async def upsert_cursor(
        self,
        sweeper_name: str,
        last_user_id: UUID,
        last_scope: dict[str, Any] | None = None,
    ) -> None:
        """Write the cursor atomically. ON CONFLICT replaces the row so
        each call is the authoritative state for that sweeper.

        ``last_scope`` is optional; ``None`` keeps the existing scope
        or defaults to ``{}`` on fresh insert.
        """
        scope_json = json.dumps(last_scope) if last_scope is not None else None
        async with self._pool.acquire() as conn:
            if scope_json is None:
                # Don't overwrite scope on update when caller didn't
                # pass one — mirrors the "partial UPDATE" semantic of
                # Pydantic's model_dump(exclude_unset=True).
                await conn.execute(
                    """
                    INSERT INTO sweeper_state
                        (sweeper_name, last_user_id, updated_at)
                    VALUES ($1, $2, now())
                    ON CONFLICT (sweeper_name) DO UPDATE SET
                        last_user_id = EXCLUDED.last_user_id,
                        updated_at   = EXCLUDED.updated_at
                    """,
                    sweeper_name, last_user_id,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO sweeper_state
                        (sweeper_name, last_user_id, last_scope, updated_at)
                    VALUES ($1, $2, $3::jsonb, now())
                    ON CONFLICT (sweeper_name) DO UPDATE SET
                        last_user_id = EXCLUDED.last_user_id,
                        last_scope   = EXCLUDED.last_scope,
                        updated_at   = EXCLUDED.updated_at
                    """,
                    sweeper_name, last_user_id, scope_json,
                )

    async def clear_cursor(self, sweeper_name: str) -> None:
        """Delete the cursor row — fires on natural sweep completion.
        Next sweep sees ``read_cursor() → None`` and iterates from the
        start. Idempotent: deleting a non-existent row is a no-op.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM sweeper_state WHERE sweeper_name = $1",
                sweeper_name,
            )
