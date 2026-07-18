"""work_chapter_draft repository (D-S5-DERIVATIVE-MANUSCRIPT-FORK).

A DERIVATIVE Work's OWN manuscript, per chapter — the fork. Chapter-level
copy-on-write: no row = the chapter INHERITS canon (the router reads through to
book-service); the FIRST write FORKS it (INSERT at version 1); later writes bump
`draft_version` under OCC. Canon (book-service `chapter_drafts`) is byte-unchanged
by any write here — the isolation the fork model promises.

SCOPE (package re-key, spec 25): the partition/tenancy keys are `project_id` (the
derivative Work's own project) + `book_id`; access is decided BEFORE the repo at
the E0 book-grant gate. `created_by` is a plain actor stamp — stored, never
filtered on. `body` is JSONB (the full chapter doc, same shape book-service stores).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import WorkChapterDraft
from app.db.repositories import VersionMismatchError

_COLS = (
    "project_id, chapter_id, book_id, created_by, body, draft_format, "
    "draft_version, merged_at, created_at, updated_at"
)


def _row(row: asyncpg.Record) -> WorkChapterDraft:
    data = dict(row)
    b = data.get("body")
    if isinstance(b, str):
        data["body"] = json.loads(b)
    return WorkChapterDraft.model_validate(data)


def _dump(body: Any) -> str:
    # asyncpg has no default codec for a Python dict → JSONB; serialize ourselves
    # (the same reason DerivativesRepo json.dumps its override deltas).
    return json.dumps(body)


class WorkChapterDraftsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, project_id: UUID, chapter_id: UUID) -> WorkChapterDraft | None:
        """The fork for (project_id, chapter_id), or None if the chapter still inherits canon."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"SELECT {_COLS} FROM work_chapter_draft WHERE project_id = $1 AND chapter_id = $2",
                project_id, chapter_id,
            )
        return _row(row) if row else None

    async def insert_fork(
        self, project_id: UUID, chapter_id: UUID, book_id: UUID, created_by: UUID, body: Any,
        draft_format: str = "json",
    ) -> WorkChapterDraft | None:
        """FORK this chapter — INSERT the first work-scoped draft (version 1). Returns None if a
        fork already exists (a concurrent fork raced us) — the router maps that to a conflict."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"""
                INSERT INTO work_chapter_draft
                  (project_id, chapter_id, book_id, created_by, body, draft_format, draft_version)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, 1)
                ON CONFLICT (project_id, chapter_id) DO NOTHING
                RETURNING {_COLS}
                """,
                project_id, chapter_id, book_id, created_by, _dump(body), draft_format,
            )
        return _row(row) if row else None

    async def update_occ(
        self, project_id: UUID, chapter_id: UUID, body: Any, expected_version: int,
        draft_format: str = "json",
    ) -> WorkChapterDraft:
        """Overwrite an existing fork under OCC: WHERE draft_version = expected_version, bump it.
        A 0-row update raises VersionMismatchError with the CURRENT row (stale token → conflict)."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"""
                UPDATE work_chapter_draft
                   SET body = $3::jsonb, draft_format = $4, draft_version = draft_version + 1,
                       updated_at = now()
                 WHERE project_id = $1 AND chapter_id = $2 AND draft_version = $5
                RETURNING {_COLS}
                """,
                project_id, chapter_id, _dump(body), draft_format, expected_version,
            )
            if row is None:
                current = await c.fetchrow(
                    f"SELECT {_COLS} FROM work_chapter_draft WHERE project_id = $1 AND chapter_id = $2",
                    project_id, chapter_id,
                )
                raise VersionMismatchError(_row(current) if current else None)
        return _row(row)

    async def mark_merged(self, project_id: UUID, chapter_id: UUID) -> WorkChapterDraft | None:
        """Record that this fork was promoted to canon (M2). The fork ROW STAYS — the branch is a
        persistent parallel manuscript; merge is a one-way content promote, not an un-fork."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                f"""
                UPDATE work_chapter_draft SET merged_at = now(), updated_at = now()
                 WHERE project_id = $1 AND chapter_id = $2
                RETURNING {_COLS}
                """,
                project_id, chapter_id,
            )
        return _row(row) if row else None
