"""K21-C (design D5) — pending-facts repository.

A pending fact is a transient queue item awaiting explicit user
confirmation before a `memory_remember` tool call lands a `:Fact` in
the graph. Pending facts live in Postgres (`knowledge_pending_facts`),
not Neo4j — they are queue rows, not graph nodes.

Write path: the memory-tool executor inserts a row (via `queue`) when a
project has `memory_remember_confirm` on, carrying the
already-injection-neutralized `fact_text` (design D6 — neutralizing at
queue time means the confirm endpoint can't bypass the defense).

Read / drain path: the public pending-facts endpoints (design D7) list
the caller's queue, then `confirm` (merge_fact + delete) or `reject`
(delete) individual rows.

SECURITY RULE: every method takes `user_id` as the first argument and
every SQL statement filters by `user_id = $1`. Reviewers must reject
any query that does not. Cross-user access naturally returns
None / 0 rows, which the router maps to 404 (no existence oracle).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import FactType, PendingFact

__all__ = ["PendingFactsRepo"]

# All columns of a full pending-fact row. Centralised so the INSERT
# RETURNING and the read queries can't drift.
_SELECT_COLS = """
  pending_fact_id, user_id, project_id, session_id,
  fact_type, fact_text, created_at
"""


def _row_to_pending_fact(row: asyncpg.Record) -> PendingFact:
    return PendingFact.model_validate(dict(row))


def _rows_changed(status: str) -> int:
    """Parse an asyncpg command tag like 'DELETE 1' / 'DELETE 0' into
    the affected-row count, safely. Mirrors the helper of the same
    name in `projects.py` / `extraction_pending.py` — kept local to
    avoid importing private symbols across modules."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


class PendingFactsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def queue(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None,
        session_id: str | None,
        fact_type: FactType,
        fact_text: str,
    ) -> PendingFact:
        """Insert a pending fact and return the created row.

        `fact_text` is expected to already be injection-neutralized by
        the caller (the executor neutralizes before the queue-vs-write
        branch — design D6). `project_id` may be None for a no-project
        chat.
        """
        query = f"""
        INSERT INTO knowledge_pending_facts
          (user_id, project_id, session_id, fact_type, fact_text)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, user_id, project_id, session_id, fact_type, fact_text,
            )
        return _row_to_pending_fact(row)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        session_id: str | None = None,
    ) -> list[PendingFact]:
        """List the caller's pending facts, oldest-first.

        When `session_id` is given the list is narrowed to that one
        chat session; otherwise every pending fact the user owns is
        returned. Always filtered by `user_id` — a cross-user caller
        sees an empty list.
        """
        params: list[object] = [user_id]
        session_pred = ""
        if session_id is not None:
            params.append(session_id)
            session_pred = " AND session_id = $2"
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_pending_facts
        WHERE user_id = $1{session_pred}
        ORDER BY created_at ASC, pending_fact_id ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_pending_fact(r) for r in rows]

    async def get(
        self, user_id: UUID, pending_fact_id: UUID
    ) -> PendingFact | None:
        """Fetch one pending fact by id. Returns None if it does not
        exist or belongs to another user (cross-user → 404 at the
        router, no existence oracle)."""
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_pending_facts
        WHERE user_id = $1 AND pending_fact_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, pending_fact_id)
        return _row_to_pending_fact(row) if row else None

    async def delete(
        self, user_id: UUID, pending_fact_id: UUID
    ) -> bool:
        """Delete one pending fact. Returns True if a row was removed,
        False if it did not exist or belongs to another user.

        Used by both confirm (after merge_fact) and reject."""
        query = """
        DELETE FROM knowledge_pending_facts
        WHERE user_id = $1 AND pending_fact_id = $2
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, pending_fact_id)
        return _rows_changed(status) >= 1
