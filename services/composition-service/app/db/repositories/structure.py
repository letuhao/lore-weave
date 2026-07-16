"""structure_node repository — the durable spec layer (23 A3, the keystone of
Stage 2). The saga→arc→sub-arc tree that steers generation: `tracks` (parallel
plotlines), `roster` (cast slots) + `roster_bindings` (slot→glossary entity), and
provenance back to an `arc_template`.

SCOPE RULE (Deploy 1 per-book re-key, spec 25/BPS-1): `structure_node` is
PER-BOOK — `book_id` is the scope key, set DIRECTLY (NO `composition_work` join,
NO `project_id`, NO `user_id`). Access is decided BEFORE the repo, at the E0
book-grant gate on `book_id`. WRITE methods take `created_by` (keyword-only) as a
plain actor stamp for write-law parity with the sibling package repos; the
shipped `structure_node` table has NO `created_by` column, so it is accepted but
not persisted (see StructureNode's model note).

NESTING is guarded by the DB trigger `structure_node_depth_guard` (BA9), NOT by
Python: it computes `depth` from the parent and REJECTS depth>2, cycles, and a
cross-book parent with `ERRCODE = check_violation`. This repo relies on it and
surfaces its `check_violation` as `StructureConflictError` (the router maps that
to a 4xx — never a 500). `move()` reparents + recomputes the WHOLE subtree's
depth (recursive CTE) in ONE transaction; the trigger validates every touched row
(so a subtree-depth-3 move is caught during the recompute, not left half-applied).

RESOLUTION (BA7): `ancestor_chain` walks parent_id root→self; `resolve_tracks`/
`resolve_roster` merge root→leaf shadowing by `key` (leaf wins), `resolve_roster_
bindings` by `role_key`. This is the ONE implementation — `pack.py` and the MCP
tools call these, they never re-derive the cascade. `span`/`member_chapter_ids`/
`open_promises` are DERIVED (BA6/BA15) — never stored.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import NarrativeThread, StructureNode
from app.db.repositories import VersionMismatchError, rows_changed
from app.db.repositories.rank import rank_after, rank_between

_SELECT_COLS = """
  id, book_id, created_by, parent_id, kind, depth, rank, title, summary, goal, status,
  tracks, roster, roster_bindings, arc_template_id, template_version,
  version, is_archived, created_at, updated_at
"""

# JSONB columns asyncpg returns as a json string → json.loads on read.
_JSONB_FIELDS = ("tracks", "roster", "roster_bindings")

# Content fields update() may change (identity/position — kind/book_id/parent_id/
# rank/depth — are NOT patchable here: reparent+reorder go through move()).
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"title", "summary", "goal", "status", "tracks", "roster",
     "roster_bindings", "arc_template_id", "template_version"}
)
_JSONB_UPDATE_COLUMNS: frozenset[str] = frozenset({"tracks", "roster", "roster_bindings"})
# Columns that accept an explicit NULL (clear). tracks/roster/roster_bindings +
# the text fields are NOT NULL, so a None on them is skipped (no-op for the field).
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset({"arc_template_id", "template_version"})

# narrative_thread projection (open_promises) — mirrors
# app/db/repositories/narrative_thread.py:_SELECT_COLS so the row validates into
# the NarrativeThread model. (book_id is stored but not in the model, so omitted.)
_THREAD_COLS = (
    "id, created_by, project_id, kind, status, opened_at_node, payoff_node, "
    "trigger, nesting_depth, priority, summary, version, is_archived, "
    "created_at, updated_at"
)


class StructureConflictError(Exception):
    """Raised when a structure_node write violates the depth/cycle/cross-book DB
    trigger (`structure_node_depth_guard`, ERRCODE `check_violation`) — depth>2,
    a cycle, a cross-book parent — or another structural invariant (a bad
    `after_id`). The router maps it to 409/400; it must NEVER surface as a 500.
    The DB trigger is the single source of truth for the nesting invariants; this
    wrapper only surfaces its `check_violation` cleanly."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _jsonb(value: Any) -> str:
    """Dump a JSONB write value (list/dict/pydantic) to a json string for ::jsonb."""
    return json.dumps(value)


def _dump_items(items: Any) -> list[dict[str, Any]]:
    """[dict|pydantic] → [dict] for JSONB serialization (tracks/roster entries)."""
    out: list[dict[str, Any]] = []
    for it in items or []:
        out.append(it.model_dump(mode="json") if hasattr(it, "model_dump") else it)
    return out


def _row_to_node(row: asyncpg.Record) -> StructureNode:
    data = dict(row)
    for f in _JSONB_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = json.loads(v)
    return StructureNode.model_validate(data)


def _thread_row(row: asyncpg.Record) -> NarrativeThread:
    return NarrativeThread.model_validate(dict(row))


class StructureRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ───────────────────────── helpers ─────────────────────────

    async def _next_rank(
        self, conn: asyncpg.Connection, book_id: UUID, parent_id: UUID | None,
    ) -> str:
        """Append position: a rank after the current last sibling under `parent_id`
        within `book_id` (single-row touch). `parent_id IS NOT DISTINCT FROM $2`
        groups the NULL (root) siblings; `max(rank COLLATE "C")` is byte-order to
        match the fractional-rank algorithm regardless of DB locale."""
        last = await conn.fetchval(
            """
            SELECT max(rank COLLATE "C") FROM structure_node
            WHERE book_id = $1 AND parent_id IS NOT DISTINCT FROM $2 AND NOT is_archived
            """,
            book_id, parent_id,
        )
        return rank_after(last)

    # ───────────────────────── CRUD ─────────────────────────

    async def create_node(
        self,
        book_id: UUID,
        *,
        created_by: UUID,
        kind: str,
        title: str = "",
        summary: str = "",
        goal: str = "",
        status: str = "outline",
        parent_id: UUID | None = None,
        tracks: list[Any] | None = None,
        roster: list[Any] | None = None,
        roster_bindings: dict[str, Any] | None = None,
        arc_template_id: UUID | None = None,
        template_version: int | None = None,
        rank: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> StructureNode:
        """Insert a spec node. `book_id` is the scope, set DIRECTLY (the gate
        resolved it — no Work join). `created_by` is accepted for write-law parity
        but the shipped table has no column for it (not persisted). `depth` is
        trigger-maintained (omitted from the INSERT). When `rank` is omitted it
        appends after the last sibling under `parent_id`.

        The depth/cycle/cross-book guard is the DB trigger: creating a saga with a
        parent, an arc under a depth-2 parent (→depth 3), or under a parent in
        another book raises `check_violation` → StructureConflictError (a clean
        4xx, never a 500)."""

        async def _do(c: asyncpg.Connection) -> asyncpg.Record:
            node_rank = rank if rank is not None else await self._next_rank(
                c, book_id, parent_id
            )
            return await c.fetchrow(
                f"""
                INSERT INTO structure_node
                  (book_id, created_by, parent_id, kind, rank, title, summary, goal, status,
                   tracks, roster, roster_bindings, arc_template_id, template_version)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10::jsonb, $11::jsonb, $12::jsonb, $13, $14)
                RETURNING {_SELECT_COLS}
                """,
                book_id, created_by, parent_id, kind, node_rank, title, summary, goal, status,
                _jsonb(_dump_items(tracks)), _jsonb(_dump_items(roster)),
                _jsonb(roster_bindings or {}), arc_template_id, template_version,
            )

        try:
            if conn is not None:
                row = await _do(conn)
            else:
                async with self._pool.acquire() as c:
                    row = await _do(c)
        except asyncpg.exceptions.CheckViolationError as exc:
            raise StructureConflictError(str(exc)) from exc
        return _row_to_node(row)

    async def find_by_plan_run(
        self, book_id: UUID, run_id: UUID, *, arc_id: str | None = None,
    ) -> StructureNode | None:
        """The arc the skeleton linker minted for this plan run (27 PF-13's write target).

        Book-scoped, and it EXCLUDES archived rows — the partial unique index that arbitrates the
        linker's upsert carries `NOT is_archived`, so an archived arc is a tombstone the linker has
        already re-created past. Binding a roster onto a tombstone would write the symbol table into
        a node nothing reads.
        """
        query = f"""
        SELECT {_SELECT_COLS} FROM structure_node
        WHERE book_id = $1 AND plan_run_id = $2 AND NOT is_archived
          AND ($3::text IS NULL OR plan_arc_id = $3)
        ORDER BY rank
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, book_id, run_id, arc_id)
        return _row_to_node(row) if row else None

    async def linked_structure_state(self, book_id: UUID) -> dict[str, Any]:
        """"Did a COMPILE actually write linked structure for this book?" — the governance
        effect-probe's durable truth (Phase G · G0, spec 2026-07-15 D2/D3), in ONE round-trip.

        Two counts, and the distinction is the whole point:

        * ``linked_count`` — structure_node rows with ``plan_run_id`` SET (compile-attributed),
          book-global. This is *ensure-EXISTS*: "the book has a compiled plan". It deliberately
          EXCLUDES ``plan_run_id IS NULL`` rows — a bare ``composition_arc_create`` INSERT (the
          agent-native manual arc) has no run stamp, so it can NOT fabricate this effect. That is
          D3: probe the durable, run-attributed truth, not a count a plain insert flips.

        * ``latest_run_linked_count`` — rows stamped by the LATEST plan_run only. This is
          *produce-NEW*: "THIS planning attempt compiled fresh structure". On a re-plan (a new
          latest run whose compile has not landed) it reads 0 even though ``linked_count`` is
          already >0 — so a step gated on it is NOT born-done. That is D2 (freshness), and it
          needs no migration: ``structure_node.plan_run_id`` already carries the provenance.

        Cheap: the counts ride ``uq_structure_node_plan_prov (book_id, plan_run_id, …)``; the
        latest-run lookup rides ``idx_plan_run_book_created (book_id, created_at DESC)``.
        A book with no runs → ``latest_run_id=None`` and both counts 0 (never an error).
        """
        query = """
        WITH latest AS (
          SELECT id FROM plan_run WHERE book_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1
        )
        SELECT
          (SELECT COUNT(*) FROM structure_node
             WHERE book_id = $1 AND plan_run_id IS NOT NULL AND NOT is_archived)::int
            AS linked_count,
          (SELECT id FROM latest) AS latest_run_id,
          (SELECT COUNT(*) FROM structure_node
             WHERE book_id = $1 AND NOT is_archived
               AND plan_run_id = (SELECT id FROM latest))::int
            AS latest_run_linked_count
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, book_id)
        return {
            "linked_count": int(row["linked_count"] or 0),
            "latest_run_id": row["latest_run_id"],
            "latest_run_linked_count": int(row["latest_run_linked_count"] or 0),
        }

    async def get(
        self, node_id: UUID, *, conn: asyncpg.Connection | None = None,
    ) -> StructureNode | None:
        """BARE-ID fetch (the E0 gate resolved the book first)."""
        query = f"SELECT {_SELECT_COLS} FROM structure_node WHERE id = $1"
        if conn is not None:
            row = await conn.fetchrow(query, node_id)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, node_id)
        return _row_to_node(row) if row else None

    async def list_tree(
        self, book_id: UUID, *, include_archived: bool = False,
    ) -> list[StructureNode]:
        """The book's spec tree as a flat, deterministically-ordered list — depth
        first (root sagas, then arcs, then sub-arcs), then fractional rank. The
        caller assembles the tree. rank COLLATE "C" is byte order (matches the
        fractional-rank algorithm) regardless of DB locale."""
        archived_pred = "" if include_archived else " AND NOT is_archived"
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT {_SELECT_COLS} FROM structure_node
                WHERE book_id = $1{archived_pred}
                ORDER BY depth, rank COLLATE "C", id
                """,
                book_id,
            )
        return [_row_to_node(r) for r in rows]

    async def derived_blocks(self, book_id: UUID) -> dict[UUID, dict[str, Any]]:
        """24 PH9/OQ-2/BA6 — the DERIVED block (span, chapter_count, is_contiguous) for
        EVERY structure node of a book in ONE query (no N+1 — the Hub's arc shell is a
        single call). Each node's block rolls up its whole SUBTREE's member chapters (a
        saga spans its arcs' chapters), matching the per-node `span()` semantics. Chapters
        bind to a leaf arc via `structure_node_id`; a parent's block aggregates descendants.

        Returned per node id: {span: {from_order, to_order} | None, is_contiguous, chapter_count}.
        `is_contiguous` is warn-only (BA6): the members' story_orders are a gap-free run — every
        chapter ordered, all distinct, no gaps. The rollup does NOT assume `story_order` uniqueness —
        it MEASURES `count(DISTINCT story_order)` over the subtree directly, so a duplicated order
        still reads non-contiguous. Returns a row ONLY for keys of LIVE (non-archived) nodes, and
        counts only live chapters — deliberately live-only (the Hub's default view). Callers that
        render archived nodes (list_arcs?include_archived=true) get the empty block for them; that is
        intended (an archived arc's warn-only metrics are not surfaced), never a computed value."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                WITH RECURSIVE tree AS (
                  SELECT id AS root, id AS node FROM structure_node
                   WHERE book_id = $1 AND NOT is_archived
                  UNION
                  SELECT t.root, s.id FROM structure_node s
                    JOIN tree t ON s.parent_id = t.node
                   WHERE s.book_id = $1 AND NOT s.is_archived
                ),
                -- The chapter's POSITION in the book's reading order (1..N), not its raw
                -- `story_order`. story_order is the STRIDED packer axis (chapter_sort * 1000,
                -- shared with the scenes + the canon-rule windows), so raw min/max would report a
                -- 3-chapter arc as span 1000..3000 and `max-min+1 == count` would never hold —
                -- every arc would read non-contiguous. dense_rank collapses it to the ordinal a
                -- reader means ("chapters 1–3"), and stays correct for ANY monotonic axis, so a
                -- future change of stride cannot silently break BA6. Duplicate story_orders share
                -- a rank ⇒ distinct < count ⇒ still non-contiguous (the check we want to keep).
                ord AS (
                  SELECT id, dense_rank() OVER (ORDER BY story_order) AS pos
                    FROM outline_node
                   WHERE book_id = $1 AND kind = 'chapter' AND NOT is_archived
                     AND story_order IS NOT NULL
                )
                SELECT t.root,
                  count(o.id)             AS chapter_count,
                  min(p.pos)              AS min_so,
                  max(p.pos)              AS max_so,
                  count(p.pos)            AS ordered_count,
                  count(DISTINCT p.pos)   AS distinct_count,
                  min(o.story_order)      AS first_story_order
                FROM tree t
                LEFT JOIN outline_node o
                  ON o.structure_node_id = t.node
                 AND o.book_id = $1 AND o.kind = 'chapter' AND NOT o.is_archived
                LEFT JOIN ord p ON p.id = o.id
                GROUP BY t.root
                """,
                book_id,
            )
        out: dict[UUID, dict[str, Any]] = {}
        for r in rows:
            cc = int(r["chapter_count"] or 0)
            min_so, max_so = r["min_so"], r["max_so"]
            ordered = int(r["ordered_count"] or 0)
            distinct = int(r["distinct_count"] or 0)
            if cc == 0:
                is_contig = True                       # empty arc: no gaps to speak of
            elif ordered < cc:
                is_contig = False                      # some member chapter has no story_order
            else:
                is_contig = distinct == cc and (max_so - min_so + 1) == cc
            span = (
                {"from_order": min_so, "to_order": max_so}
                if cc > 0 and min_so is not None
                else None
            )
            out[r["root"]] = {
                "span": span,
                "is_contiguous": is_contig,
                "chapter_count": cc,
                # The arc's first chapter on the RAW axis. `span` is the human ORDINAL ("chapters
                # 1–3"); this is the SORT key, and it must be in the same units as the chapter rows
                # the client interleaves it with (outline_node.story_order). Keeping one field for
                # both jobs put a collapsed arc's rollup card at the wrong x — an ordinal 4 sorted
                # ahead of a chapter at 1000. One field, one job.
                "first_story_order": r["first_story_order"],
            }
        return out

    async def get_children(
        self, parent_id: UUID, *, include_archived: bool = False,
    ) -> list[StructureNode]:
        """Direct children of `parent_id`, in fractional-rank order."""
        archived_pred = "" if include_archived else " AND NOT is_archived"
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT {_SELECT_COLS} FROM structure_node
                WHERE parent_id = $1{archived_pred}
                ORDER BY rank COLLATE "C", id
                """,
                parent_id,
            )
        return [_row_to_node(r) for r in rows]

    async def update(
        self, node_id: UUID, patch: dict[str, Any], *, expected_version: int | None,
    ) -> StructureNode | None:
        """Partial content update with optional If-Match OCC. Only content fields
        are patchable (title/summary/goal/status/tracks/roster/roster_bindings/
        arc_template_id/template_version); reparent+reorder go through move().
        Raises VersionMismatchError(current) on a stale `expected_version` when the
        row exists (412), returns None when it doesn't (404). A bad enum value
        (e.g. an unknown status) hits the DB CHECK → StructureConflictError."""
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get(node_id)

        set_clauses: list[str] = []
        params: list[Any] = [node_id]
        for field, value in updates.items():
            if field in _JSONB_UPDATE_COLUMNS:
                dumped = _dump_items(value) if field != "roster_bindings" else (value or {})
                params.append(_jsonb(dumped))
                set_clauses.append(f"{field} = ${len(params)}::jsonb")
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
        UPDATE structure_node
        SET {", ".join(set_clauses)}
        WHERE id = $1{version_clause}
        RETURNING {_SELECT_COLS}
        """
        try:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *params)
        except asyncpg.exceptions.CheckViolationError as exc:
            raise StructureConflictError(str(exc)) from exc
        if row is not None:
            return _row_to_node(row)
        if expected_version is None:
            return None
        current = await self.get(node_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def archive(self, node_id: UUID) -> None:
        """Soft-archive a node AND its descendants (no orphaned-visible child under
        an archived parent). A recursive CTE walks parent_id DOWN, then one UPDATE
        flips is_archived on the whole subtree. UNION (not UNION ALL) dedups so a
        malformed parent cycle terminates instead of hanging (the trigger prevents
        cycles; this is a backstop). book_id is threaded through every CTE leg.

        D-ARC-ARCHIVE-CHAPTER-STRANDING (spec 32a §B): archiving an arc no longer STRANDS
        its member chapters (visible in neither the archived lane nor the unassigned tray).
        Before flipping is_archived, we RETURN the members to the pool — null their
        structure_node_id while remembering it in archived_from_structure_node_id — so
        restore() can re-attach exactly those. Both steps run in ONE transaction."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                # 1) Return member chapters of the (still-live) subtree to the unplanned pool,
                #    recording which arc each came from. Runs BEFORE the is_archived flip so the
                #    `NOT is_archived` subtree is the full live set.
                await c.execute(
                    """
                    WITH RECURSIVE subtree AS (
                      SELECT id, book_id FROM structure_node WHERE id = $1 AND NOT is_archived
                      UNION
                      SELECT n.id, n.book_id FROM structure_node n
                      JOIN subtree s ON n.parent_id = s.id AND n.book_id = s.book_id
                      WHERE NOT n.is_archived
                    )
                    UPDATE outline_node o
                    SET archived_from_structure_node_id = o.structure_node_id,
                        structure_node_id = NULL, updated_at = now()
                    WHERE o.structure_node_id IN (SELECT id FROM subtree)
                      AND o.kind = 'chapter' AND NOT o.is_archived
                    """,
                    node_id,
                )
                # 2) Flip is_archived on the structure_node subtree.
                await c.execute(
                    """
                    WITH RECURSIVE subtree AS (
                      SELECT id, book_id FROM structure_node WHERE id = $1 AND NOT is_archived
                      UNION
                      SELECT n.id, n.book_id FROM structure_node n
                      JOIN subtree s ON n.parent_id = s.id AND n.book_id = s.book_id
                      WHERE NOT n.is_archived
                    )
                    UPDATE structure_node SET is_archived = true, updated_at = now()
                    WHERE id IN (SELECT id FROM subtree)
                    """,
                    node_id,
                )

    async def restore(self, node_id: UUID) -> None:
        """Un-archive a node — the inverse of archive(). Walks parent_id UP to
        restore the archived ancestor chain (so the node reconnects to a visible
        root) and DOWN to restore its archived descendants. Sibling branches stay
        archived. UNION terminates on a malformed cycle; book_id threads every leg.

        D-ARC-ARCHIVE-CHAPTER-STRANDING (spec 32a §B): after un-archiving, RE-ATTACH the
        chapters this subtree returned to the pool on archive — but ONLY those still
        unassigned. A chapter the user re-homed to another arc while this was archived keeps
        its new home (the `structure_node_id IS NULL` guard). One transaction."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    """
                    WITH RECURSIVE ancestors AS (
                      SELECT id, parent_id, book_id FROM structure_node
                      WHERE id = $1 AND is_archived
                      UNION
                      SELECT p.id, p.parent_id, p.book_id FROM structure_node p
                      JOIN ancestors a ON p.id = a.parent_id AND p.book_id = a.book_id
                      WHERE p.is_archived
                    ),
                    subtree AS (
                      SELECT id, book_id FROM structure_node WHERE id = $1 AND is_archived
                      UNION
                      SELECT n.id, n.book_id FROM structure_node n
                      JOIN subtree s ON n.parent_id = s.id AND n.book_id = s.book_id
                      WHERE n.is_archived
                    )
                    UPDATE structure_node SET is_archived = false, updated_at = now()
                    WHERE id IN (SELECT id FROM ancestors) OR id IN (SELECT id FROM subtree)
                    """,
                    node_id,
                )
                # Re-attach the returned chapters (only the still-unassigned ones — the race guard).
                await c.execute(
                    """
                    WITH RECURSIVE subtree AS (
                      SELECT id, book_id FROM structure_node WHERE id = $1
                      UNION
                      SELECT n.id, n.book_id FROM structure_node n
                      JOIN subtree s ON n.parent_id = s.id AND n.book_id = s.book_id
                    )
                    UPDATE outline_node o
                    SET structure_node_id = o.archived_from_structure_node_id,
                        archived_from_structure_node_id = NULL, updated_at = now()
                    WHERE o.archived_from_structure_node_id IN (SELECT id FROM subtree)
                      AND o.structure_node_id IS NULL
                    """,
                    node_id,
                )

    async def move(
        self, node_id: UUID, *, new_parent_id: UUID | None, after_id: UUID | None = None,
    ) -> StructureNode | None:
        """Reparent + reorder in ONE transaction. Places `node_id` under
        `new_parent_id` (None = a root) directly AFTER `after_id` (None = first)
        by a fractional rank strictly between `after_id` and the next sibling — a
        single-row rank write. Then recomputes the WHOLE moved subtree's `depth`
        with a recursive CTE in the SAME transaction; the DB trigger validates
        every touched row.

        A depth>2 (the moved node OR any descendant), a cycle (new_parent is a
        descendant of node), a cross-book parent, or a saga given a parent all
        raise `check_violation` at the DB → StructureConflictError (a clean 4xx,
        never a 500), and the whole move rolls back. Returns the moved node (re-read
        with the new parent + recomputed depth), or None if it doesn't exist."""
        try:
            async with self._pool.acquire() as c:
                async with c.transaction():
                    node = await self.get(node_id, conn=c)
                    if node is None:
                        return None

                    # Siblings under the destination parent (excluding the moved
                    # node), in canonical byte-rank order, scoped to the moved
                    # node's book (a cross-book parent yields none here, then the
                    # reparent's trigger rejects it).
                    siblings = await c.fetch(
                        """
                        SELECT id, rank FROM structure_node
                        WHERE book_id = $1 AND parent_id IS NOT DISTINCT FROM $2
                          AND id <> $3 AND NOT is_archived
                        ORDER BY rank COLLATE "C", id
                        """,
                        node.book_id, new_parent_id, node_id,
                    )
                    if after_id is None:
                        lo, hi = None, (siblings[0]["rank"] if siblings else None)
                    else:
                        idx = next(
                            (i for i, s in enumerate(siblings) if s["id"] == after_id),
                            None,
                        )
                        if idx is None:
                            raise StructureConflictError(
                                f"after_id {after_id} is not a sibling under the new parent"
                            )
                        lo = siblings[idx]["rank"]
                        hi = siblings[idx + 1]["rank"] if idx + 1 < len(siblings) else None
                    new_rank = rank_between(lo, hi)

                    # Reparent + reorder. The BEFORE trigger recomputes this row's
                    # depth from the new parent and validates (depth<=2 · no cycle ·
                    # same book). version bumps so a stale OCC baseline refreshes.
                    await c.execute(
                        """
                        UPDATE structure_node
                        SET parent_id = $2, rank = $3, version = version + 1, updated_at = now()
                        WHERE id = $1
                        """,
                        node_id, new_parent_id, new_rank,
                    )

                    # Recompute the WHOLE moved subtree's depth in the same tx: one
                    # UPDATE touches every descendant; the trigger recomputes each
                    # row's depth from its (now-correct) parent and REJECTS a
                    # resulting depth>2 (a subtree that no longer fits) with
                    # check_violation, rolling the move back. UNION terminates on a
                    # malformed cycle.
                    await c.execute(
                        """
                        WITH RECURSIVE sub AS (
                          SELECT id FROM structure_node WHERE parent_id = $1
                          UNION
                          SELECT n.id FROM structure_node n JOIN sub s ON n.parent_id = s.id
                        )
                        UPDATE structure_node SET updated_at = now()
                        WHERE id IN (SELECT id FROM sub)
                        """,
                        node_id,
                    )

                    return await self.get(node_id, conn=c)
        except asyncpg.exceptions.CheckViolationError as exc:
            raise StructureConflictError(str(exc)) from exc

    async def assign_chapters(
        self, book_id: UUID, structure_node_id: UUID | None, chapter_node_ids: list[UUID],
    ) -> int:
        """Attach CHAPTER-kind outline nodes to a spec node (sets
        `outline_node.structure_node_id`), OR — BE-A3 — UNASSIGN them when
        `structure_node_id is None` (return to the `?unassigned=true` pool). Book-scoped
        both sides: only chapters in `book_id` are touched, and an ASSIGN is a no-op unless
        the target node is itself in `book_id` (the EXISTS guard — a spec node never adopts
        chapters from another book). Either way the archive-recovery slot
        (`archived_from_structure_node_id`) is CLEARED, so a later restore of some old arc
        cannot yank a chapter the user has since deliberately re-homed. Returns the count."""
        if not chapter_node_ids:
            return 0
        async with self._pool.acquire() as c:
            if structure_node_id is None:
                status = await c.execute(
                    """
                    UPDATE outline_node o
                    SET structure_node_id = NULL, archived_from_structure_node_id = NULL,
                        updated_at = now()
                    WHERE o.book_id = $1 AND o.id = ANY($2)
                      AND o.kind = 'chapter' AND NOT o.is_archived
                    """,
                    book_id, chapter_node_ids,
                )
            else:
                status = await c.execute(
                    """
                    UPDATE outline_node o
                    SET structure_node_id = $1, archived_from_structure_node_id = NULL,
                        updated_at = now()
                    WHERE o.book_id = $2 AND o.id = ANY($3)
                      AND o.kind = 'chapter' AND NOT o.is_archived
                      AND EXISTS (
                        SELECT 1 FROM structure_node s
                        WHERE s.id = $1 AND s.book_id = $2
                      )
                    """,
                    structure_node_id, book_id, chapter_node_ids,
                )
        return rows_changed(status)

    # ─────────────────────── resolution (BA7) ───────────────────────

    async def ancestor_chain(self, node_id: UUID) -> list[StructureNode]:
        """The chain root(saga)→…→self, in order (root first, self last). Walks
        parent_id UP; empty if `node_id` doesn't exist."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                WITH RECURSIVE chain AS (
                  SELECT n.*, 0 AS _lvl FROM structure_node n WHERE n.id = $1
                  UNION ALL
                  SELECT p.*, c._lvl + 1 FROM structure_node p
                  JOIN chain c ON p.id = c.parent_id
                )
                SELECT {_SELECT_COLS} FROM chain ORDER BY _lvl DESC
                """,
                node_id,
            )
        return [_row_to_node(r) for r in rows]

    @staticmethod
    def _merge_by(levels: list[list[dict[str, Any]]], key_field: str) -> list[dict[str, Any]]:
        """Merge a root→leaf sequence of entry lists, shadowing by `key_field`
        (a later/leaf entry replaces an earlier/root entry with the same key).
        Insertion order of first appearance is preserved. Entries missing the key
        are kept individually (they can't shadow)."""
        merged: dict[Any, dict[str, Any]] = {}
        for level in levels:
            for it in level:
                k = it.get(key_field, id(it))
                merged[k] = it
        return list(merged.values())

    async def resolve_tracks(self, node_id: UUID) -> list[dict[str, Any]]:
        """Merge `tracks` root→leaf, shadow by `key` (leaf wins). BA7 — the ONE
        implementation; pack.py + the MCP tools call this, never re-derive it."""
        chain = await self.ancestor_chain(node_id)
        return self._merge_by([n.tracks for n in chain], "key")

    async def resolve_roster(self, node_id: UUID) -> list[dict[str, Any]]:
        """Merge `roster` root→leaf, shadow by `key` (leaf wins)."""
        chain = await self.ancestor_chain(node_id)
        return self._merge_by([n.roster for n in chain], "key")

    async def resolve_roster_bindings(self, node_id: UUID) -> dict[str, Any]:
        """Merge `roster_bindings` root→leaf, shadow by `role_key` (leaf wins)."""
        chain = await self.ancestor_chain(node_id)
        merged: dict[str, Any] = {}
        for n in chain:
            merged.update(n.roster_bindings or {})
        return merged

    # ─────────────────────── derived (BA6/BA15) ───────────────────────

    async def member_chapter_ids(self, node_id: UUID) -> list[UUID]:
        """The member chapters: outline_node (kind='chapter', active) whose
        `structure_node_id` is in the subtree(node) — a sub-arc's chapters count
        for its arc. Reading order (story_order, then id). DERIVED (BA6)."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                WITH RECURSIVE subtree AS (
                  SELECT id FROM structure_node WHERE id = $1
                  UNION
                  SELECT s.id FROM structure_node s JOIN subtree t ON s.parent_id = t.id
                )
                SELECT id FROM outline_node
                WHERE structure_node_id IN (SELECT id FROM subtree)
                  AND kind = 'chapter' AND NOT is_archived
                ORDER BY story_order NULLS LAST, id
                """,
                node_id,
            )
        return [r["id"] for r in rows]

    async def span(self, node_id: UUID) -> dict[str, Any]:
        """The DERIVED span over member chapters (BA6): min/max `story_order`,
        `chapter_count`, and warn-only `is_contiguous` (are the member chapters'
        story_orders a gap-free run — every chapter ordered, all distinct, no
        gaps). NEVER stored — a stored range goes stale on the next insert/reorder.
        A romance plotline may legitimately be non-contiguous, so contiguity is a
        warning signal, not an error."""
        async with self._pool.acquire() as c:
            r = await c.fetchrow(
                """
                WITH RECURSIVE subtree AS (
                  SELECT id FROM structure_node WHERE id = $1
                  UNION
                  SELECT s.id FROM structure_node s JOIN subtree t ON s.parent_id = t.id
                ),
                members AS (
                  SELECT story_order FROM outline_node
                  WHERE structure_node_id IN (SELECT id FROM subtree)
                    AND kind = 'chapter' AND NOT is_archived
                )
                SELECT
                  min(story_order)          AS min_so,
                  max(story_order)          AS max_so,
                  count(*)                  AS chapter_count,
                  count(story_order)        AS ordered_count,
                  count(DISTINCT story_order) AS distinct_count
                FROM members
                """,
                node_id,
            )
        chapter_count = int(r["chapter_count"] or 0)
        min_so, max_so = r["min_so"], r["max_so"]
        ordered = int(r["ordered_count"] or 0)
        distinct = int(r["distinct_count"] or 0)
        if chapter_count == 0:
            is_contiguous = True                       # empty arc: no gaps to speak of
        elif ordered < chapter_count:
            is_contiguous = False                      # some member chapter has no story_order
        else:
            is_contiguous = distinct == chapter_count and (max_so - min_so + 1) == chapter_count
        return {
            "min_story_order": min_so,
            "max_story_order": max_so,
            "chapter_count": chapter_count,
            "is_contiguous": is_contiguous,
        }

    async def open_promises(
        self, node_id: UUID, *, narrative_threads_repo: Any,
    ) -> list[NarrativeThread]:
        """The open-promise rollup (BA15): narrative_thread rows whose
        `opened_at_node` lies in this node's chapter subtree (a member chapter OR
        one of its descendant scenes) and whose status is still unresolved (NOT
        paid/dropped, not archived). DERIVED — no new column.

        `narrative_threads_repo` is passed in (rather than importing the repo
        class, per the A3 interface's circular-import note); the promise ledger is
        its domain, so the query borrows its pool. Highest priority first, then
        oldest-first (matches the repo's own open-set ordering)."""
        pool = narrative_threads_repo._pool
        async with pool.acquire() as c:
            rows = await c.fetch(
                f"""
                WITH RECURSIVE subtree AS (
                  SELECT id FROM structure_node WHERE id = $1
                  UNION
                  SELECT s.id FROM structure_node s JOIN subtree t ON s.parent_id = t.id
                ),
                member_chapters AS (
                  SELECT id FROM outline_node
                  WHERE structure_node_id IN (SELECT id FROM subtree)
                    AND kind = 'chapter' AND NOT is_archived
                ),
                member_nodes AS (
                  SELECT id FROM member_chapters
                  UNION
                  SELECT n.id FROM outline_node n
                  JOIN member_nodes m ON n.parent_id = m.id
                  WHERE NOT n.is_archived
                )
                SELECT {_THREAD_COLS} FROM narrative_thread
                WHERE opened_at_node IN (SELECT id FROM member_nodes)
                  AND status NOT IN ('paid', 'dropped') AND NOT is_archived
                ORDER BY priority DESC, created_at ASC
                """,
                node_id,
            )
        return [_thread_row(r) for r in rows]
