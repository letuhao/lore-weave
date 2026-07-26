"""composition_work repository — the Work marker + work-level settings (§5/§6.2).

SCOPE RULE (book-package re-key — 00A BPS-1/2/8 + spec 25 PM-9): Work rows are
PER-BOOK, grant-gated. No method takes or filters on a user id — reads key on
`project_id` / `book_id` / the surrogate `id` alone, and access is decided
BEFORE the repo, at the E0 book-grant gate on the row's `book_id`
(`grant_deps.authorize_book` / MCP `_book_or_deny`). Write methods take
`created_by` as a plain ACTOR stamp (who did it — spend/audit attribution
under BYOK): INSERTs store it; nothing ever filters on it. Reviewers must
reject any query that re-introduces an actor predicate.

`composition_work.project_id` equals the knowledge project id (cross-DB, no
FK) and is unique per Work (`uq_composition_work_project`); the surrogate `id`
is the PK. At most one CANONICAL Work per book (`uq_composition_work_book`,
partial: `source_work_id IS NULL AND status = 'active'`); derivatives (C23)
remain N-per-book. Creating a backed Work requires an already-existing
knowledge project id — the POST /work flow (M7) creates the knowledge project
first, then the row here.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple
from uuid import UUID

import asyncpg

from app.db.models import CompositionWork
from app.db.repositories import VersionMismatchError

_SELECT_COLS = """
  project_id, created_by, book_id, id, pending_project_backfill,
  source_work_id, branch_point,
  active_template_id, status, settings,
  version, created_at, updated_at
"""

# Fields a PATCH /works/{id} may change. Defense-in-depth against a router
# passing an unexpected column into the dynamic UPDATE.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"active_template_id", "status", "settings"}
)
# Columns that accept an explicit NULL (clear). `active_template_id` clears the
# template selection; status/settings are NOT NULL so None is skipped.
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset({"active_template_id"})


class WorkScopeMeta(NamedTuple):
    """PM-8 ids-only scope row — exactly what the access gate needs, nothing
    more (no titles, no settings, no status): mirrors knowledge's
    `project_meta` anti-oracle read."""

    book_id: UUID
    work_id: UUID | None
    project_id: UUID


def _row_to_work(row: asyncpg.Record) -> CompositionWork:
    data = dict(row)
    s = data.get("settings")
    if isinstance(s, str):
        data["settings"] = json.loads(s)
    return CompositionWork.model_validate(data)


class WorksRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        created_by: UUID,
        project_id: UUID,
        book_id: UUID,
        *,
        active_template_id: UUID | None = None,
        settings: dict[str, Any] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CompositionWork:
        """Insert the Work marker row for an existing knowledge project.

        `created_by` is the acting caller — a plain actor stamp (PM-9), never a
        scope key. Accepts an optional `conn` so the POST /work flow can create
        the knowledge project + emit the outbox event + write this row in one
        transaction (txn-local outbox, §1).
        """
        query = f"""
        INSERT INTO composition_work (project_id, created_by, book_id, active_template_id, settings)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (project_id, created_by, book_id, active_template_id, json.dumps(settings or {}))
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def create_pending(
        self,
        created_by: UUID,
        book_id: UUID,
        *,
        active_template_id: UUID | None = None,
        settings: dict[str, Any] | None = None,
    ) -> CompositionWork:
        """C16 (WG-3): create a LAZY greenfield Work with a NULL project_id +
        `pending_project_backfill=true` when knowledge-service could not mint the
        project (down/5xx). The surrogate `id` PK makes the row addressable; the
        partial-unique `(book_id) WHERE pending_project_backfill` index caps it at
        one PER BOOK (PM-4) — so a concurrent retry by ANY collaborator that loses
        the race re-gets the book's existing pending row. `created_by` stamps the
        acting caller (actor, not scope); whichever later owner-path creates the
        knowledge project backfills this same row.
        GREENFIELD ONLY: the router refuses this path for a derivative Work (C23
        guard — a derivative keeps project_id NOT NULL)."""
        query = f"""
        INSERT INTO composition_work
          (project_id, created_by, book_id, pending_project_backfill, active_template_id, settings)
        VALUES (NULL, $1, $2, true, $3, $4::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (created_by, book_id, active_template_id, json.dumps(settings or {}))
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def create_derivative(
        self,
        created_by: UUID,
        project_id: UUID,
        book_id: UUID,
        source_work_id: UUID,
        *,
        branch_point: int | None = None,
        settings: dict[str, Any] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> CompositionWork:
        """C23 (dị bản M0): insert a DERIVATIVE Work linked to its source.

        `project_id` MUST be a freshly-minted knowledge project (G2 — the
        derivative's own delta partition; NEVER the source's) and is NOT NULL: the
        `chk_derivative_project_required` DB CHECK rejects a null project on a row
        with `source_work_id` set, the same guard the router enforces before this
        call. `created_by` stamps the acting caller (actor, not scope). Accepts an
        optional `conn` so the derive flow can write the Work + its
        divergence_spec + entity_override[] in one transaction.
        """
        query = f"""
        INSERT INTO composition_work
          (project_id, created_by, book_id, source_work_id, branch_point, settings)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        RETURNING {_SELECT_COLS}
        """
        args = (project_id, created_by, book_id, source_work_id, branch_point,
                json.dumps(settings or {}))
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_work(row)

    async def get_pending_for_book(self, book_id: UUID) -> CompositionWork | None:
        """The (at-most-one) lazy greenfield Work awaiting a knowledge project for
        this BOOK (C16 backfill seam; capped at one by the `(book_id) WHERE
        pending_project_backfill` partial unique — PM-4). None when there is none.

        This predicate deliberately matches the partial-unique index's exactly
        (book_id + the pending marker) so the create_pending catch-and-re-get
        paths re-find precisely the row the index collided on
        (postgres-partial-index-on-conflict-predicate-must-match)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE book_id = $1 AND pending_project_backfill
        ORDER BY created_at
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, book_id)
        return _row_to_work(row) if row else None

    async def backfill_project(
        self, work_id: UUID, project_id: UUID, *, created_by: UUID
    ) -> CompositionWork | None:
        """C16 backfill seam: stamp the now-created knowledge `project_id` onto a
        lazy Work (by surrogate `id`) and clear the pending marker. Idempotent:
        only updates a still-pending row, so a double-backfill no-ops. Returns the
        updated row, or None if the row vanished / was already backfilled.

        `created_by` is the acting caller (write-law actor arg, PM-9) — attribution
        only; the row keeps its creator and the actor is never a predicate."""
        del created_by  # actor arg — attribution parity only, never scope/stamp here
        query = f"""
        UPDATE composition_work
        SET project_id = $2, pending_project_backfill = false, updated_at = now()
        WHERE id = $1 AND pending_project_backfill
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, work_id, project_id)
        return _row_to_work(row) if row else None

    async def get(self, project_id: UUID) -> CompositionWork | None:
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE project_id = $1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id)
        return _row_to_work(row) if row else None

    async def get_by_id(self, work_id: UUID) -> CompositionWork | None:
        """Fetch a Work by its surrogate `id`. C25 — the packer resolves a
        derivative's BASE knowledge project from its `source_work_id` (the source
        Work's `id`), and the source's `id` is NOT necessarily its `project_id`
        (the two diverge for a Work whose surrogate id was minted distinct from
        its project), so the base project MUST be looked up here rather than
        reusing `source_work_id` as a project_id directly. Access is gated by the
        caller's E0 grant on the returned row's `book_id` (never here)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE id = $1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, work_id)
        return _row_to_work(row) if row else None

    async def scope_meta(self, project_id: UUID) -> WorkScopeMeta | None:
        """PM-8 access-gate bootstrap — the ids-only `(book_id, work_id,
        project_id)` for a project's Work, un-user-scoped. This read exists so
        `_book_or_deny` / `book_id_for_project` can resolve the book to gate on
        WITHOUT consulting row ownership (F2 inversion) and without leaking row
        content: it returns ids or None, so a non-grantee still gets the uniform
        H13/404 at the access layer (no oracle — mirrors knowledge's
        `project_meta`, projects.py:454-466)."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT book_id, id, project_id FROM composition_work WHERE project_id = $1",
                project_id,
            )
        if row is None:
            return None
        return WorkScopeMeta(
            book_id=row["book_id"], work_id=row["id"], project_id=row["project_id"]
        )

    async def resolve_by_book(self, book_id: UUID) -> list[CompositionWork]:
        """Return every MARKED (real-project) Work for this book (§6.2
        prefers-marked) — the canonical Work plus any C23 derivatives.

        The caller (work_resolution.resolve_work) maps the result:
          len == 1 → found · len > 1 → candidates · len == 0 → defer to the
        knowledge book-project lookup. Ordered by created_at so a candidates
        list is stable.

        C16: a LAZY null-project Work (`pending_project_backfill`) is EXCLUDED — it
        is a placeholder, not yet a grounding-backed marked Work, and would have a
        null project_id (un-anchorable). Excluding it makes resolution fall through
        to the knowledge book-project lookup so a retry once knowledge recovers hits
        the create_project → BACKFILL seam (which stamps the project onto this same
        pending row) instead of returning the placeholder as a finished `found` Work.
        """
        # P3 (book-structure §4.6, Option C): `book_lifecycle = 'active'` gates the plan-hub entry so a
        # trashed / purge_pending book's Work does not resolve as active — orthogonal to `status` (the
        # USER Work-archive flag). The deep planning/generation reads hang off the resolved Work, so gating
        # this chokepoint covers them without a column on every book-scoped table (the bounded Option C).
        query = f"""
        SELECT {_SELECT_COLS} FROM composition_work
        WHERE book_id = $1 AND status = 'active' AND book_lifecycle = 'active'
          AND NOT pending_project_backfill
        ORDER BY created_at, project_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id)
        return [_row_to_work(r) for r in rows]

    async def update(
        self,
        project_id: UUID,
        patch: dict[str, Any],
        *,
        created_by: UUID,
        expected_version: int | None = None,
    ) -> CompositionWork | None:
        """Partial update with optional If-Match (§5).

        - `created_by` is the acting caller (write-law actor arg, PM-9) —
          attribution only, never a predicate; the row keeps its creator.
        - Unknown fields → ValueError (defense-in-depth).
        - None on a NOT-NULL column is skipped; None on a nullable column clears.
        - Empty effective patch returns the current row unchanged (no version
          bump, no updated_at touch) — GET-like no-op.
        - `expected_version` set: WHERE gates on version, SET bumps it; a 0-row
          result does a follow-up GET to distinguish 404 (None) from 412
          (raises VersionMismatchError with the current row).
        """
        del created_by  # actor arg — attribution parity only, never scope/stamp here
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get(project_id)

        set_clauses: list[str] = []
        params: list[Any] = [project_id]
        for field, value in updates.items():
            if field == "settings":
                # BE-18: SHALLOW-MERGE rather than full-blob replace. Callers PATCH
                # a partial settings map (e.g. a scene-graph drag sends only
                # {scene_graph}); a `settings = $n` replace would WIPE every other
                # key — notably BE-13a's derivative_name and any concurrent write's
                # keys (the world-map lost-update window). `||` merges top-level keys,
                # last-write-wins per key; a caller replacing a nested object still
                # sends the whole sub-object (read-modify-write), so top-level merge
                # is the right grain. COALESCE guards a NULL settings (never NULL in
                # practice — NOT NULL default '{}' — but defensive).
                params.append(json.dumps(value))
                set_clauses.append(
                    f"settings = COALESCE(settings, '{{}}'::jsonb) || ${len(params)}::jsonb"
                )
            else:
                params.append(value)
                set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
            set_clauses.append("version = version + 1")

        query = f"""
        UPDATE composition_work
        SET {", ".join(set_clauses)}
        WHERE project_id = $1{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        if row is not None:
            return _row_to_work(row)
        if expected_version is None:
            return None
        current = await self.get(project_id)
        if current is None:
            return None
        raise VersionMismatchError(current)
