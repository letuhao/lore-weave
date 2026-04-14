"""Extraction pending queue repository (K10.5).

Events that arrive while extraction is disabled for a project get
parked in `extraction_pending`. When the user enables extraction,
the K11+ backfill drains the queue oldest-first.

SECURITY MODEL: per the K10.5 spec, user isolation is enforced via
a JOIN on `knowledge_projects.user_id` rather than the denormalised
`extraction_pending.user_id` column. The denormalised column is
convenience for indexes and audit, not authority — if it ever
drifts from the parent project's owner (migration bug, direct SQL
admin write), the JOIN catches it. Every method that takes a
`user_id` parameter resolves authority through the parent project,
not through the row itself.

Idempotency: `queue_event` uses `ON CONFLICT (project_id, event_id)
DO UPDATE SET event_id = EXCLUDED.event_id RETURNING ...` so a
duplicate event_id is a no-op-with-RETURNING. The caller can't
distinguish "freshly queued" from "already in the queue" but
that's exactly what an idempotent queue should look like.

Plan: K10.5 in docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ExtractionPending",
    "ExtractionPendingQueueRequest",
    "ExtractionPendingRepo",
]


# All columns projected in a full pending row. Centralised for
# consistency across read methods.
_SELECT_COLS = """
  pending_id, user_id, project_id, event_id, event_type,
  aggregate_type, aggregate_id, created_at, processed_at
"""


# ── Pydantic models ──────────────────────────────────────────────────────


class ExtractionPending(BaseModel):
    """Mirror of the extraction_pending row."""

    model_config = ConfigDict(from_attributes=True)

    pending_id: UUID
    user_id: UUID
    project_id: UUID
    event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    created_at: datetime
    processed_at: datetime | None = None


class ExtractionPendingQueueRequest(BaseModel):
    """Caller payload for `queue_event`. `user_id` is enforced at
    the method signature, not the payload, so callers can't inject
    it.

    Field validation matches K10.4-I4 hardening: event_type and
    aggregate_type must be non-empty strings (the worker code
    won't know how to dispatch on '' and would crash cryptically
    later). Both are capped at 100 chars to bound DB row size and
    discourage callers from stuffing payload fragments into the
    type field.
    """

    project_id: UUID
    event_id: UUID
    event_type: Annotated[str, Field(min_length=1, max_length=100)]
    aggregate_type: Annotated[str, Field(min_length=1, max_length=100)]
    aggregate_id: UUID


# ── Repository ───────────────────────────────────────────────────────────


def _row_to_pending(row: asyncpg.Record) -> ExtractionPending:
    return ExtractionPending.model_validate(dict(row))


class ExtractionPendingRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # K10.5 caps `fetch_pending` at this many rows per call so the
    # backfill loop can't accidentally pull tens of thousands of
    # rows into memory in one shot. The K11/K14 worker drains in
    # batches.
    FETCH_HARD_CAP = 1000

    # ─── queue_event ─────────────────────────────────────────────────

    async def queue_event(
        self,
        user_id: UUID,
        request: ExtractionPendingQueueRequest,
    ) -> ExtractionPending | None:
        """Queue an event for later extraction. Idempotent on
        (project_id, event_id) — a duplicate call returns the
        existing row.

        Returns None if the user does not own `request.project_id`
        (cross-user OR nonexistent — the caller cannot distinguish,
        per KSA §6.4 anti-leak rules).

        The CTE pattern mirrors K-CLEAN-3's `upsert_project_scoped`:
        the inner INSERT is gated on `EXISTS (SELECT 1 FROM owned)`
        where `owned` is a one-row CTE that resolves project
        ownership through `knowledge_projects.user_id`. This is
        the JOIN-based defense-in-depth that the K10.5 spec calls
        for — even if `extraction_pending.user_id` somehow drifts
        from the parent project's owner, the gate uses the
        authoritative source.

        ON CONFLICT (project_id, event_id) DO UPDATE SET event_id
        = EXCLUDED.event_id is a no-op UPDATE that exists only to
        force RETURNING to fire on the duplicate path. Without
        this, ON CONFLICT DO NOTHING would yield zero rows for
        duplicates and we couldn't return the existing row.
        """
        query = f"""
        WITH owned AS (
          SELECT 1 FROM knowledge_projects
          WHERE user_id = $1 AND project_id = $2
        ),
        queued AS (
          INSERT INTO extraction_pending
            (user_id, project_id, event_id, event_type,
             aggregate_type, aggregate_id)
          SELECT $1, $2, $3, $4, $5, $6
          WHERE EXISTS (SELECT 1 FROM owned)
          ON CONFLICT (project_id, event_id) DO UPDATE
            SET event_id = EXCLUDED.event_id
          RETURNING {_SELECT_COLS}
        )
        SELECT * FROM queued
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                user_id,
                request.project_id,
                request.event_id,
                request.event_type,
                request.aggregate_type,
                request.aggregate_id,
            )
        return _row_to_pending(row) if row else None

    # ─── reads ───────────────────────────────────────────────────────

    async def count_pending(
        self, user_id: UUID, project_id: UUID
    ) -> int:
        """Count unprocessed rows for a project. Returns 0 if the
        user does not own the project (no information leak).

        Authority resolved via JOIN through knowledge_projects per
        the K10.5 security model.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id
         AND p.user_id = $1
        WHERE ep.project_id = $2
          AND ep.processed_at IS NULL
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, project_id)
        return int(row["n"]) if row else 0

    async def fetch_pending(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ExtractionPending]:
        """Fetch the next batch of unprocessed events for a project,
        oldest-first (FIFO). Uses the partial index
        `idx_extraction_pending_unprocessed` for cheap reads even at
        100k+ pending rows.

        Returns empty list if the user does not own the project.
        Capped at `FETCH_HARD_CAP` rows defensively.
        """
        effective_limit = max(1, min(limit, self.FETCH_HARD_CAP))
        query = f"""
        SELECT {", ".join(f"ep.{c.strip()}" for c in _SELECT_COLS.split(","))}
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id
         AND p.user_id = $1
        WHERE ep.project_id = $2
          AND ep.processed_at IS NULL
        ORDER BY ep.created_at ASC, ep.pending_id ASC
        LIMIT {effective_limit}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, project_id)
        return [_row_to_pending(r) for r in rows]

    # ─── state transitions ───────────────────────────────────────────

    async def mark_processed(
        self, user_id: UUID, pending_id: UUID
    ) -> bool:
        """Flip processed_at to now() for one queue row. Returns
        True if the row was just transitioned, False if it was
        already processed, never existed, or belongs to another
        user (defense-in-depth via the JOIN through
        knowledge_projects).

        The `processed_at IS NULL` predicate is part of the WHERE
        so a re-mark on an already-processed row is a no-op (0
        rows affected → False) rather than an audit-trail-mangling
        re-stamp.
        """
        query = """
        UPDATE extraction_pending ep
        SET processed_at = now()
        FROM knowledge_projects p
        WHERE ep.pending_id = $2
          AND ep.processed_at IS NULL
          AND p.project_id = ep.project_id
          AND p.user_id = $1
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, pending_id)
        # asyncpg returns "UPDATE <n>"; parse the count.
        try:
            return int(status.rsplit(" ", 1)[-1]) >= 1
        except ValueError:
            return False

    async def clear_pending(
        self, user_id: UUID, project_id: UUID
    ) -> int:
        """Delete UNPROCESSED rows for a project. Called when the
        user disables extraction or cancels the in-flight job —
        the queue should drop pending work but the audit trail of
        already-processed rows is preserved.

        Returns the number of rows deleted. Returns 0 if the user
        does not own the project (no information leak).
        """
        query = """
        DELETE FROM extraction_pending ep
        USING knowledge_projects p
        WHERE ep.project_id = $2
          AND ep.processed_at IS NULL
          AND p.project_id = ep.project_id
          AND p.user_id = $1
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, project_id)
        try:
            return int(status.rsplit(" ", 1)[-1])
        except ValueError:
            return 0
