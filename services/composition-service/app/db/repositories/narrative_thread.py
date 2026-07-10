"""narrative_thread repository — the promise/foreshadow/MICE ledger (cycle 14,
reasoning-engine spec §5.2/§10.2).

ADVISORY ledger (spec D4): the open/progressing rows are the re-injectable
"open-promise" set the reasoning loop carries (F2); arc-end unpaid rows feed the
foreshadow-drop check (§7). Lifecycle: open → progressing → paid | dropped.

SCOPE RULE (package re-key, spec 25 §Repo/service layer): all queries key on
`project_id` (= the Work id, the codebase convention for the spec's `work_id`) —
access is decided BEFORE the repo, at the gate (E0 grant on the row's
`book_id`). Writes stamp `created_by` (a plain actor stamp — STORED, never
filtered on) and derive `book_id` from composition_work inside the INSERT.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import NarrativeThread
from app.db.repositories import ReferenceViolationError

_SELECT_COLS = (
    "id, created_by, project_id, kind, status, opened_at_node, payoff_node, "
    "trigger, nesting_depth, priority, summary, version, is_archived, "
    "created_at, updated_at"
)
_OPEN_STATUSES = ["open", "progressing"]


def _row(r: asyncpg.Record) -> NarrativeThread:
    return NarrativeThread.model_validate(dict(r))


class NarrativeThreadRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def open_thread(
        self,
        project_id: UUID,
        *,
        created_by: UUID,
        kind: str,
        summary: str,
        opened_at_node: UUID | None = None,
        trigger: str = "",
        nesting_depth: int = 0,
        priority: int = 50,
    ) -> NarrativeThread:
        """Insert a new `open` thread (a detected setup/promise/MICE-open)."""
        query = f"""
        INSERT INTO narrative_thread
          (created_by, project_id, book_id, kind, summary, opened_at_node, trigger, nesting_depth, priority)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6, $7, $8
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            r = await c.fetchrow(
                query, created_by, project_id, kind, summary, opened_at_node,
                trigger, nesting_depth, priority,
            )
        if r is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row(r)

    async def update_status(
        self,
        project_id: UUID,
        thread_id: UUID,
        *,
        status: str,
        payoff_node: UUID | None = None,
    ) -> NarrativeThread | None:
        """Transition a thread (progressing/paid/dropped). `payoff_node` is
        written ONLY when paying (the table CHECK enforces payoff_node-only-when-
        paid; clearing it on non-paid statuses keeps the row legal even if a
        caller passes a stale value). Returns None when no active row matched
        (wrong project / archived / missing)."""
        query = f"""
        UPDATE narrative_thread
        SET status = $3,
            payoff_node = CASE WHEN $3 = 'paid' THEN $4::uuid ELSE NULL END,
            version = version + 1,
            updated_at = now()
        WHERE id = $2 AND project_id = $1 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            r = await c.fetchrow(query, project_id, thread_id, status, payoff_node)
        return _row(r) if r is not None else None

    async def list_open(
        self, project_id: UUID, *, limit: int = 100,
    ) -> list[NarrativeThread]:
        """The open/progressing set — the re-injectable open promises (F2).
        Highest priority first, then oldest-first so a long-standing high-priority
        debt surfaces before fresh low-priority ones."""
        query = f"""
        SELECT {_SELECT_COLS} FROM narrative_thread
        WHERE project_id = $1 AND NOT is_archived
          AND status = ANY($2)
        ORDER BY priority DESC, created_at ASC
        LIMIT $3
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, _OPEN_STATUSES, limit)
        return [_row(r) for r in rows]

    async def count_open(self, project_id: UUID) -> int:
        """TRUE count of the open/progressing set — the unpaid-promise debt
        (FD-1 S4a §7). A real COUNT, not len(list_open) which caps at its LIMIT
        and would silently under-report the debt for a large ledger."""
        query = """
        SELECT count(*) FROM narrative_thread
        WHERE project_id = $1 AND NOT is_archived
          AND status = ANY($2)
        """
        async with self._pool.acquire() as c:
            return await c.fetchval(query, project_id, _OPEN_STATUSES) or 0

    async def list_for_project(
        self, project_id: UUID,
    ) -> list[NarrativeThread]:
        """All active threads for the work (any status) — debt review / FE."""
        query = f"""
        SELECT {_SELECT_COLS} FROM narrative_thread
        WHERE project_id = $1 AND NOT is_archived
        ORDER BY created_at ASC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row(r) for r in rows]
