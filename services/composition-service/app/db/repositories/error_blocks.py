"""chapter_error_block repository — the author's marked defects in a chapter's prose.

Atom-edit Phase D. Design + sealed decisions:
docs/specs/2026-07-26-atom-edit/DESIGN-error-blocks.md

SCOPE RULE (same as CanonRulesRepo): reads key on `project_id` (the Work partition key); access
is decided BEFORE the repo, at the gate (E0 grant on the row's `book_id`). Writes stamp
`created_by` (a plain actor stamp — STORED, never filtered on) and derive `book_id` from
composition_work inside the INSERT, so a row can never land with a NULL book scope.

DELETE is a soft-archive. A resolved block is history: it records that the author found this
passage wrong and what was done about it, which is exactly the signal the correction-rate
eval-gate wants. Hard-deleting it would erase that.

ANCHORING lives in the engine, not here — this repo stores `quote`/offsets/`source_fingerprint`
verbatim and never re-locates. Re-anchoring needs the chapter text, which is a caller concern.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import ErrorBlock
from app.db.repositories import ReferenceViolationError, VersionMismatchError

_SELECT_COLS = """
  id, created_by, project_id, book_id, target_kind, chapter_id, draft_version, job_id,
  start_offset, end_offset, quote, source_fingerprint, source, kind, note, desired,
  status, proposal_id, resolution, version, is_archived, created_at, updated_at, resolved_at
"""

# `status` is deliberately NOT here: it moves only through the explicit lifecycle helpers
# (mark_proposed / resolve / dismiss / mark_orphaned), so an arbitrary PATCH can never park a
# block in a state nothing produced. The span itself is immutable — re-marking is a new block,
# which keeps `quote`/offsets/fingerprint a consistent triple rather than three fields that can
# drift apart under partial updates.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset({"kind", "note", "desired"})
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset({"desired"})

# The statuses that still want the author's (or the co-writer's) attention.
OPEN_STATUSES = ("open", "proposed", "orphaned")


class DuplicateErrorBlockError(Exception):
    """An identical open mark already exists (same span + same note).

    Raised instead of silently returning the existing row: a double-click and a genuine second
    mark are indistinguishable at the repo, and swallowing it would make `create` a silent no-op.
    """


def _row(row: asyncpg.Record) -> ErrorBlock:
    return ErrorBlock.model_validate(dict(row))


class ErrorBlocksRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        project_id: UUID,
        *,
        created_by: UUID,
        target_kind: str,
        start_offset: int,
        end_offset: int,
        quote: str,
        source_fingerprint: str,
        kind: str,
        note: str,
        chapter_id: UUID | None = None,
        draft_version: int | None = None,
        job_id: UUID | None = None,
        desired: str | None = None,
        source: str = "human",
    ) -> ErrorBlock:
        query = f"""
        INSERT INTO chapter_error_block
          (created_by, project_id, book_id, target_kind, chapter_id, draft_version, job_id,
           start_offset, end_offset, quote, source_fingerprint, source, kind, note, desired)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        RETURNING {_SELECT_COLS}
        """
        try:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(
                    query, created_by, project_id, target_kind, chapter_id, draft_version,
                    job_id, start_offset, end_offset, quote, source_fingerprint, source,
                    kind, note, desired,
                )
        except asyncpg.UniqueViolationError as exc:  # uq_chapter_error_block_open
            raise DuplicateErrorBlockError(
                "an identical open mark already exists on this span"
            ) from exc
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row(row)

    async def list_for_chapter(
        self,
        project_id: UUID,
        chapter_id: UUID,
        *,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> tuple[list[ErrorBlock], int]:
        """(page, open_count). `open_count` is the TRUE count of blocks still wanting attention —
        never capped by `limit` — so a caller that shows "12 of 200" cannot silently under-report
        (the listNarrativeThreads precedent)."""
        preds = ["project_id = $1", "chapter_id = $2"]
        params: list[Any] = [project_id, chapter_id]
        if not include_archived:
            preds.append("NOT is_archived")
        if status is not None:
            params.append(status)
            preds.append(f"status = ${len(params)}")
        params.append(limit)
        where = " AND ".join(preds)
        query = f"""
        SELECT {_SELECT_COLS} FROM chapter_error_block
        WHERE {where}
        ORDER BY start_offset, created_at, id
        LIMIT ${len(params)}
        """
        count_query = """
        SELECT count(*) FROM chapter_error_block
        WHERE project_id = $1 AND chapter_id = $2 AND NOT is_archived
          AND status = ANY($3::text[])
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
            open_count = await c.fetchval(
                count_query, project_id, chapter_id, list(OPEN_STATUSES)
            )
        return [_row(r) for r in rows], int(open_count or 0)

    async def list_for_job(
        self, project_id: UUID, job_id: UUID, *, include_archived: bool = False,
    ) -> list[ErrorBlock]:
        """Blocks marked on a pre-accept compose preview, which has no chapter identity yet."""
        archived_pred = "" if include_archived else " AND NOT is_archived"
        query = f"""
        SELECT {_SELECT_COLS} FROM chapter_error_block
        WHERE project_id = $1 AND job_id = $2{archived_pred}
        ORDER BY start_offset, created_at, id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, job_id)
        return [_row(r) for r in rows]

    async def get(self, project_id: UUID, block_id: UUID) -> ErrorBlock | None:
        query = f"SELECT {_SELECT_COLS} FROM chapter_error_block WHERE project_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, block_id)
        return _row(row) if row else None

    async def update(
        self,
        project_id: UUID,
        block_id: UUID,
        patch: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> ErrorBlock | None:
        """Partial update of the FINDING text only (kind/note/desired) with optional If-Match.

        Same discipline as CanonRulesRepo.update. The span and the status are not updatable here
        — see `_UPDATABLE_COLUMNS`.
        """
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get(project_id, block_id)

        set_clauses: list[str] = []
        params: list[Any] = [project_id, block_id]
        for field, value in updates.items():
            params.append(value)
            set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
            set_clauses.append("version = version + 1")

        query = f"""
        UPDATE chapter_error_block
        SET {", ".join(set_clauses)}
        WHERE project_id = $1 AND id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        if row is not None:
            return _row(row)
        if expected_version is None:
            return None
        # Distinguish "gone" from "changed under you" — a 404 and a 412 are different bugs.
        exists = await self.get(project_id, block_id)
        if exists is None:
            return None
        raise VersionMismatchError(
            f"error block {block_id} version is {exists.version}, expected {expected_version}"
        )

    async def set_status(
        self,
        project_id: UUID,
        block_id: UUID,
        status: str,
        *,
        proposal_id: str | None = None,
        resolution: str | None = None,
    ) -> ErrorBlock | None:
        """The explicit lifecycle transition. `resolved_at` is stamped only for terminal states,
        so 'when was this closed' stays answerable and a re-open would clear it."""
        query = f"""
        UPDATE chapter_error_block
        SET status = $3,
            proposal_id = COALESCE($4, proposal_id),
            resolution = COALESCE($5, resolution),
            resolved_at = CASE WHEN $3::text IN ('resolved','dismissed') THEN now() ELSE NULL END,
            version = version + 1,
            updated_at = now()
        WHERE project_id = $1 AND id = $2
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, block_id, status, proposal_id, resolution)
        return _row(row) if row else None

    async def reanchor(
        self,
        project_id: UUID,
        block_id: UUID,
        *,
        start_offset: int,
        end_offset: int,
        source_fingerprint: str,
    ) -> ErrorBlock | None:
        """Persist re-computed offsets after the engine re-located the quote.

        The span TEXT (`quote`) is never rewritten — it is the anchor, and rewriting it would
        destroy the only stable identity the block has.
        """
        query = f"""
        UPDATE chapter_error_block
        SET start_offset = $3, end_offset = $4, source_fingerprint = $5, updated_at = now()
        WHERE project_id = $1 AND id = $2
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, project_id, block_id, start_offset, end_offset, source_fingerprint,
            )
        return _row(row) if row else None

    async def migrate_job_blocks_to_chapter(
        self,
        project_id: UUID,
        job_id: UUID,
        *,
        chapter_id: UUID,
        draft_version: int | None,
        located: dict[UUID, tuple[int, int]],
        fingerprint: str,
    ) -> int:
        """Accept migration: re-target a preview's blocks onto the now-real chapter.

        `located` carries only the blocks whose quote was found in the chapter text. Everything
        else is marked 'orphaned' rather than dropped — a mark that silently vanishes is
        indistinguishable from one the author fixed.
        """
        moved = 0
        async with self._pool.acquire() as c:
            async with c.transaction():
                for block_id, (start, end) in located.items():
                    await c.execute(
                        """
                        UPDATE chapter_error_block
                        SET target_kind = 'chapter_draft', chapter_id = $3, draft_version = $4,
                            start_offset = $5, end_offset = $6, source_fingerprint = $7,
                            job_id = NULL, updated_at = now()
                        WHERE project_id = $1 AND id = $2
                        """,
                        project_id, block_id, chapter_id, draft_version, start, end, fingerprint,
                    )
                    moved += 1
                # ORDER MATTERS: the re-targeted rows above cleared their `job_id`, so this
                # sweep can key on `job_id = $2` and by construction touches only the blocks
                # that did NOT locate. Reversing the two statements would orphan everything.
                await c.execute(
                    """
                    UPDATE chapter_error_block
                    SET status = 'orphaned', updated_at = now()
                    WHERE project_id = $1 AND job_id = $2 AND NOT is_archived
                      AND status NOT IN ('resolved','dismissed')
                    """,
                    project_id, job_id,
                )
        return moved

    async def archive(self, project_id: UUID, block_id: UUID) -> ErrorBlock | None:
        query = f"""
        UPDATE chapter_error_block SET is_archived = true, version = version + 1, updated_at = now()
        WHERE project_id = $1 AND id = $2 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, block_id)
        return _row(row) if row else None

    async def restore(self, project_id: UUID, block_id: UUID) -> ErrorBlock | None:
        query = f"""
        UPDATE chapter_error_block SET is_archived = false, version = version + 1, updated_at = now()
        WHERE project_id = $1 AND id = $2 AND is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, block_id)
        return _row(row) if row else None
