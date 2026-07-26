"""arc_conformance_state repository — the durable, input-pinned conformance snapshot
(26 IX-8, `.runs/`). ONE row per (book_id, structure_node_id), UPSERT-latest.

SCOPE RULE (25/BPS-1): `book_id` is the tenancy scope key, set DIRECTLY (no Work
join, no project_id). Access is decided BEFORE the repo, at the E0 book-grant gate —
this repo is a thin, un-user-scoped store. The row is DERIVED build output (the
`.runs/` package area, DA-2/DA-3): it holds "the latest report + what state of the
book it was true of", never a second copy of spec/index truth.

The table has ONE writer — `persist_conformance_state`
(app/engine/arc_conformance_orchestrate.py), called by BOTH `compute_arc_report`
callers (the sync GET + the Tier-W worker) so the manifest format can't fork.
Reads: `get` (one arc) + `list_for_book` (the status route's per-arc rollup).

JSONB (`report`, `input_manifest`) is written serialized + cast ::jsonb (asyncpg does
not auto-encode a dict) and read back with json.loads (this pool registers no JSONB
codec, so asyncpg returns a json string — the structure.py/outline.py pattern).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

_SELECT_COLS = (
    "book_id, structure_node_id, report, input_manifest, deep, "
    "generation_job_id, computed_at"
)


@dataclass(frozen=True)
class ConformanceSnapshot:
    """One arc_conformance_state row, JSONB fields already decoded to dicts."""

    book_id: UUID
    structure_node_id: UUID
    report: dict[str, Any]
    input_manifest: dict[str, Any]
    deep: bool
    generation_job_id: UUID | None
    computed_at: datetime


def _jsonb(value: Any) -> dict[str, Any]:
    """asyncpg returns JSONB as a json string (no codec registered) → decode."""
    return json.loads(value) if isinstance(value, str) else (value or {})


def _row(row: asyncpg.Record) -> ConformanceSnapshot:
    return ConformanceSnapshot(
        book_id=row["book_id"],
        structure_node_id=row["structure_node_id"],
        report=_jsonb(row["report"]),
        input_manifest=_jsonb(row["input_manifest"]),
        deep=bool(row["deep"]),
        generation_job_id=row["generation_job_id"],
        computed_at=row["computed_at"],
    )


class ConformanceStateRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self,
        *,
        book_id: UUID,
        structure_node_id: UUID,
        report: dict[str, Any],
        input_manifest: dict[str, Any],
        deep: bool = False,
        generation_job_id: str | UUID | None = None,
    ) -> ConformanceSnapshot:
        """UPSERT-latest the snapshot for one arc (26 IX-8). ON CONFLICT on the PK
        replaces report/manifest/deep/provenance and re-stamps `computed_at=now()`
        (a server clock — never a client string, the asyncpg-timestamptz lesson).
        `generation_job_id` is coerced to a UUID (the worker passes a str)."""
        gj: UUID | None = None
        if generation_job_id is not None:
            gj = generation_job_id if isinstance(generation_job_id, UUID) else UUID(str(generation_job_id))
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"""
                INSERT INTO arc_conformance_state
                  (book_id, structure_node_id, report, input_manifest, deep, generation_job_id)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)
                ON CONFLICT (book_id, structure_node_id) DO UPDATE SET
                  report            = EXCLUDED.report,
                  input_manifest    = EXCLUDED.input_manifest,
                  deep              = EXCLUDED.deep,
                  generation_job_id = EXCLUDED.generation_job_id,
                  computed_at       = now()
                RETURNING {_SELECT_COLS}
                """,
                book_id, structure_node_id, json.dumps(report),
                json.dumps(input_manifest), bool(deep), gj,
            )
        return _row(row)

    async def get(
        self, book_id: UUID, structure_node_id: UUID,
    ) -> ConformanceSnapshot | None:
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"SELECT {_SELECT_COLS} FROM arc_conformance_state "
                "WHERE book_id = $1 AND structure_node_id = $2",
                book_id, structure_node_id,
            )
        return _row(row) if row else None

    async def list_for_book(self, book_id: UUID) -> list[ConformanceSnapshot]:
        """Every arc's latest snapshot for a book (the status route reads all in one
        query, then computes dirtiness per-arc in memory against ONE canon-markers
        batch — IX-9). Ordered by structure_node_id for a stable response."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"SELECT {_SELECT_COLS} FROM arc_conformance_state "
                "WHERE book_id = $1 ORDER BY structure_node_id",
                book_id,
            )
        return [_row(r) for r in rows]
