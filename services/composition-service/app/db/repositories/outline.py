"""outline_node repository — the Arc→Chapter→Scene→Beat tree (§1.2/§5).

SCOPE RULE (BPS-1 package re-key, spec 25 §Repo/service layer — supersedes the
old M5 per-user isolation): READ methods take `project_id` (the Work partition
key, PM-3) and NO user_id; WRITE methods additionally take `created_by` — a
plain actor stamp that is STORED, never filtered on. Access is decided BEFORE
the repo, at the gate (E0 grant on the row's `book_id`). Every INSERT derives
`book_id` from `composition_work` inside the statement (INSERT … SELECT
w.book_id), so a write can never mint a NULL book_id. Sibling order is a
fractional `rank` (see rank.py) so an insert touches one row. DELETE is a
RECURSIVE soft-archive (PO decision): archiving a node also archives its
descendants, so no orphaned-visible child survives under an archived parent.
Hard FK CASCADE is reserved for scene_link edges only.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import OutlineNode
from app.db.repositories import (
    AlreadyPlannedError, ReferenceViolationError, VersionMismatchError, outbox,
)
from app.db.repositories.rank import rank_after, rank_between
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

# 24 PH18 — `rule_violations` rows are FLAT per (scene x violation) and each carries the rule's
# full text, so a long book multiplies out fast. Bounded like every other list here
# (`coverage.UNPLANNED_CAP`, `plan_overlay._REFS_CAP`); the COUNT stays exact so the truncation is
# always visible (OUT-5: never silent-truncate).
RULE_VIOLATIONS_CAP = 200

_SELECT_COLS = """
  id, created_by, project_id, book_id, parent_id, kind, rank, title, pov_entity_id,
  present_entity_ids, goal, beat_role, status, chapter_id, tension,
  story_order, synopsis, structure_node_id,
  location_entity_id, story_time, conflict, outcome, value_shift, stakes,
  target_words, exit_state, source,
  -- SC11 Phase 1/3 — the written verdict. A MAINTAINED column (reconciled from
  -- book-service's scenes.source_scene_id), never authored. Selected here so the PH10
  -- summary projection can ship `written` without a second query.
  written_scene_id, written_chapter_id, written_at,
  version, is_archived, created_at, updated_at
"""

# Namespace key (arg-1) for the per-project decompose-commit advisory xact lock.
# Distinguishes it from any other pg_advisory_xact_lock(int4, int4) in the service.
_DECOMPOSE_COMMIT_LOCK_NS = 0x10AF

_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"parent_id", "rank", "title", "pov_entity_id", "present_entity_ids", "goal",
     "beat_role", "status", "chapter_id", "tension", "story_order", "synopsis",
     # 22 SC4/B2 — authored scene intent (the eight fields). conflict/outcome/stakes
     # are NOT NULL DEFAULT '' (not clearable); the rest accept an explicit NULL.
     "location_entity_id", "story_time", "conflict", "outcome", "value_shift",
     "stakes", "target_words", "exit_state"}
)
# Columns that accept an explicit NULL (clear). The others are NOT NULL, so a
# None on them is skipped (treated as no-op for that field).
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"parent_id", "pov_entity_id", "beat_role", "chapter_id", "tension", "story_order",
     # 22 SC4/B2 — the nullable-clearable authored-intent fields
     "location_entity_id", "story_time", "value_shift", "target_words", "exit_state"}
)


def _row_to_node(row: asyncpg.Record) -> OutlineNode:
    data = dict(row)
    # 22 SC12 — exit_state is JSONB; this pool sets no jsonb codec, so asyncpg returns it
    # as a JSON string. Deserialize to a dict for the model (mirrors structure.py's pattern).
    ev = data.get("exit_state")
    if isinstance(ev, str):
        data["exit_state"] = json.loads(ev)
    return OutlineNode.model_validate(data)


def _is_scene_commit(old: OutlineNode | None, new: OutlineNode | None) -> bool:
    """M9 telemetry predicate: a SCENE transitioning into status='done' is the
    'committed for review' signal (§3.1). True only when a real transition
    happened — the node is a scene, existed before, was NOT already done, and is
    now done. A done→done no-op or a non-scene node returns False (no emit)."""
    return (
        new is not None
        and new.kind == "scene"
        and old is not None
        and old.status != "done"
        and new.status == "done"
    )


class OutlineRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _next_rank(
        self, conn: asyncpg.Connection, project_id: UUID,
        parent_id: UUID | None,
    ) -> str:
        """Append position: a rank after the current last sibling under parent.

        `parent_id IS NOT DISTINCT FROM $2` so NULL (top-level) groups together
        and compares equal — a plain `=` would never match NULL.
        """
        # max(rank COLLATE "C"): the DB default collation is en_US.UTF-8 (NOT
        # byte-order), so an unqualified max(rank) could pick a different "last"
        # sibling than fractional-rank byte ordering intends. COLLATE "C" makes
        # it exact regardless of DB locale.
        last = await conn.fetchval(
            """
            SELECT max(rank COLLATE "C") FROM outline_node
            WHERE project_id = $1
              AND parent_id IS NOT DISTINCT FROM $2 AND NOT is_archived
            """,
            project_id, parent_id,
        )
        return rank_after(last)

    async def _validate_parent(
        self, conn: asyncpg.Connection, project_id: UUID,
        parent_id: UUID,
    ) -> None:
        """Ensure `parent_id` is a node in the SAME project (Work partition).

        Defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): the in-DB FK only proves the
        parent EXISTS — not that it is in this project. Without this a node could
        be parented under another Work's node (a broken cross-scope edge)."""
        row = await conn.fetchrow(
            "SELECT project_id FROM outline_node WHERE id = $1",
            parent_id,
        )
        if row is None:
            raise ReferenceViolationError(f"parent node {parent_id} not found")
        if row["project_id"] != project_id:
            raise ReferenceViolationError(
                f"parent node {parent_id} is in a different project"
            )

    async def _descendant_ids(
        self, conn: asyncpg.Connection, project_id: UUID, node_id: UUID,
    ) -> set[UUID]:
        """The project's descendants of `node_id` (NOT including node_id). UNION
        dedups so a pre-existing malformed cycle can't loop the walk. project_id
        filters BOTH legs of the self-join (the kinds-bug double-filter rule)."""
        rows = await conn.fetch(
            """
            WITH RECURSIVE descendants AS (
              SELECT id FROM outline_node WHERE project_id = $1 AND parent_id = $2
              UNION
              SELECT n.id FROM outline_node n
              JOIN descendants d ON n.parent_id = d.id
              WHERE n.project_id = $1
            )
            SELECT id FROM descendants
            """,
            project_id, node_id,
        )
        return {r["id"] for r in rows}

    async def _validate_reparent(
        self, conn: asyncpg.Connection, node_id: UUID,
        new_parent_id: UUID,
    ) -> None:
        """Guard a reparent: not self, parent in the same project, and not a
        descendant (cycle). Prevents the malformed cycle at the source — the
        archive_node UNION is the backstop for any cycle that still slips in."""
        if new_parent_id == node_id:
            raise ReferenceViolationError("a node cannot be its own parent")
        node = await conn.fetchrow(
            "SELECT project_id FROM outline_node WHERE id = $1",
            node_id,
        )
        if node is None:
            # Node missing: let the UPDATE 0-row path report 404/412.
            return
        await self._validate_parent(conn, node["project_id"], new_parent_id)
        if new_parent_id in await self._descendant_ids(conn, node["project_id"], node_id):
            raise ReferenceViolationError(
                f"reparenting under descendant {new_parent_id} would create a cycle"
            )

    async def create_node(
        self,
        project_id: UUID,
        *,
        created_by: UUID,
        kind: str,
        parent_id: UUID | None = None,
        rank: str | None = None,
        title: str = "",
        pov_entity_id: UUID | None = None,
        present_entity_ids: list[UUID] | None = None,
        goal: str = "",
        beat_role: str | None = None,
        status: str = "empty",
        chapter_id: UUID | None = None,
        structure_node_id: UUID | None = None,
        tension: int | None = None,
        story_order: int | None = None,
        synopsis: str = "",
        # 22 SC4/SC8 (B3) — authored scene intent. conflict/outcome/stakes are
        # NOT NULL DEFAULT '' (default to ''); the rest are nullable. exit_state is
        # the SC12 {v:1,…} envelope as a plain dict (::jsonb serialized below,
        # mirroring update_node's B2 handling). Range/enum are validated upstream
        # at the MCP schema (_NodeCreateArgs) so a bad value 422s before this INSERT.
        location_entity_id: UUID | None = None,
        story_time: str | None = None,
        conflict: str = "",
        outcome: str = "",
        value_shift: int | None = None,
        stakes: str = "",
        target_words: int | None = None,
        exit_state: dict[str, Any] | None = None,
        # 26 IX-11 (D1) — provenance. Human authoring defaults 'authored'; the
        # decompiler passes source='decompiled' + decompile_key='<chapter>:<sort>'.
        source: str = "authored",
        decompile_key: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> OutlineNode:
        """Insert an outline node. When `rank` is omitted it is auto-computed to
        append after the last sibling under `parent_id` (single-row touch).
        `created_by` is a plain actor stamp (never a filter); `book_id` is derived
        from `composition_work` INSIDE the statement so it can never be NULL.

        The eight SC4 authored-intent fields (location_entity_id/story_time/
        conflict/outcome/value_shift/stakes/target_words/exit_state) are inserted
        here too; `exit_state` is serialized + cast ::jsonb (asyncpg does not
        auto-encode a dict — same shape as update_node's SC12 path).

        `structure_node_id` links a CHAPTER to its spec arc in `structure_node`
        (25 M4 lifted model — arcs live there, NOT as a `kind='arc'` outline_node).
        The DB CHECK (`structure_node_id IS NULL OR kind='chapter'`) rejects it on
        any other kind; the referenced arc must exist first (FK)."""
        async def _do(c: asyncpg.Connection) -> asyncpg.Record:
            if parent_id is not None:
                await self._validate_parent(c, project_id, parent_id)
            node_rank = rank if rank is not None else await self._next_rank(
                c, project_id, parent_id
            )
            row = await c.fetchrow(
                f"""
                INSERT INTO outline_node
                  (created_by, project_id, book_id, parent_id, kind, rank, title,
                   pov_entity_id, present_entity_ids, goal, beat_role, status,
                   chapter_id, tension, story_order, synopsis,
                   location_entity_id, story_time, conflict, outcome, value_shift,
                   stakes, target_words, exit_state, source, decompile_key,
                   structure_node_id)
                SELECT $1, $2, w.book_id, $3, $4, $5, $6,
                       $7, $8, $9, $10, $11,
                       $12, $13, $14, $15,
                       $16, $17, $18, $19, $20,
                       $21, $22, $23::jsonb, $24, $25,
                       $26
                FROM composition_work w
                WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
                RETURNING {_SELECT_COLS}
                """,
                created_by, project_id, parent_id, kind, node_rank, title,
                pov_entity_id, present_entity_ids or [], goal, beat_role, status,
                chapter_id, tension, story_order, synopsis,
                location_entity_id, story_time, conflict, outcome, value_shift,
                stakes, target_words,
                json.dumps(exit_state) if exit_state is not None else None,
                source, decompile_key, structure_node_id,
            )
            if row is None:
                # The INSERT … SELECT found no composition_work to derive book_id
                # from → the project_id is dangling. Loud failure (PM-7 spirit):
                # never mint a node without a book_id home.
                raise ReferenceViolationError(
                    f"project {project_id} has no composition_work row"
                )
            return row

        if conn is not None:
            row = await _do(conn)
        else:
            async with self._pool.acquire() as c:
                row = await _do(c)
        return _row_to_node(row)

    async def existing_scene_chapter_ids(
        self, project_id: UUID, chapter_ids: list[UUID],
    ) -> set[UUID]:
        """A3 commit replace-guard: which of `chapter_ids` already have ≥1 active
        scene outline node. The endpoint refuses to re-decompose those unless
        `replace=true` (don't silently double-plan a chapter)."""
        if not chapter_ids:
            return set()
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT DISTINCT chapter_id FROM outline_node
                WHERE project_id = $1 AND kind = 'scene'
                  AND NOT is_archived AND chapter_id = ANY($2)
                """,
                project_id, chapter_ids,
            )
        return {r["chapter_id"] for r in rows}

    async def linked_chapter_nodes(self, book_id: UUID) -> list[dict[str, Any]]:
        """Every active spec node that CLAIMS a manuscript chapter (26 IX-13's half).

        The mirror of `planned_chapter_ids`: that one returns the id SET for the coverage diff; this
        returns the NODES, because IX-13's finding is about the node — the author has to re-link or
        archive it, so they need to know which one it is.

        `chapter_id IS NOT NULL` is the whole predicate: a node with a NULL chapter_id is "planned,
        not yet written" (27's linker writes exactly that), which is a perfectly healthy state and
        emphatically not a dangling pointer.
        """
        query = """
        SELECT id, title, kind, chapter_id, story_order
          FROM outline_node
         WHERE book_id = $1 AND chapter_id IS NOT NULL AND NOT is_archived
         ORDER BY story_order NULLS LAST
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, book_id)
        return [
            {
                "id": str(r["id"]), "title": r["title"], "kind": r["kind"],
                "chapter_id": str(r["chapter_id"]),
            }
            for r in rows
        ]

    async def planned_chapter_ids(self, book_id: UUID) -> set[UUID]:
        """The manuscript chapters this book's SPEC covers — every active chapter
        node's `chapter_id` (24 H1.3's coverage diff; the planned half).

        Book-keyed, not Work-keyed (BPS-1/BA8: the package is per-book, and the
        Hub has no Work gate — PH9). The complement against book-service's active
        chapter spine is the PH21 "unplanned chapters" tray. Lives here because
        `outline_node` is this repo's table; the diff itself is
        ``app/services/coverage.py`` — the ONE computation 24 H1.3 and 28 AN-4
        share (28 OQ-4/NC-1).

        `chapter_id IS NOT NULL` is not redundant defensiveness: today the
        `outline_chapter_required` CHECK forces it non-null on chapter nodes, but
        27-V2-A3 swaps that CHECK so a chapter can be PLANNED before its prose
        exists. Such a node covers no manuscript chapter, so it must contribute
        nothing to the planned set — and it already does, by this predicate.
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT DISTINCT chapter_id FROM outline_node
                WHERE book_id = $1 AND kind = 'chapter'
                  AND NOT is_archived AND chapter_id IS NOT NULL
                """,
                book_id,
            )
        return {r["chapter_id"] for r in rows}

    async def scenes_for_chapter(
        self, project_id: UUID, chapter_id: UUID,
    ) -> list[OutlineNode]:
        """B2 chapter-assembly — the Work's active scene nodes for `chapter_id`
        in reading order (story_order, then fractional rank as tiebreak). The
        chapter single-pass path builds its combined synopsis + union cast from
        these (the A3 decompose plan). story_order NULLS LAST so a legacy scene
        without a reading-order still sorts deterministically after placed ones."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT {_SELECT_COLS} FROM outline_node
                WHERE project_id = $1 AND chapter_id = $2
                  AND kind = 'scene' AND NOT is_archived
                ORDER BY story_order NULLS LAST, rank COLLATE "C", id
                """,
                project_id, chapter_id,
            )
        return [_row_to_node(r) for r in rows]

    async def chapter_node_id(
        self, project_id: UUID, chapter_id: UUID,
    ) -> UUID | None:
        """#12 M-G — the outline CHAPTER node bound to a book chapter (scenes parent
        under it; the rail's Create needs it when the chapter has zero scenes).
        None when the chapter was never outlined."""
        async with self._pool.acquire() as c:
            return await c.fetchval(
                """
                SELECT id FROM outline_node
                WHERE project_id = $1 AND chapter_id = $2
                  AND kind = 'chapter' AND NOT is_archived
                ORDER BY rank COLLATE "C", id
                LIMIT 1
                """,
                project_id, chapter_id,
            )

    async def chapter_structure_node_id(
        self, project_id: UUID, chapter_id: UUID,
    ) -> UUID | None:
        """23 BA12 — the arc (`structure_node.id`) a book chapter is assigned to, read
        off its outline CHAPTER node. A SCENE never carries `structure_node_id` (the
        `outline_structure_kind` CHECK forbids it — only chapters may), so the packer
        resolves a scene's arc through its chapter here. None when the chapter is
        unoutlined or unassigned — the arc lens then stays dormant (no <arc> frame)."""
        async with self._pool.acquire() as c:
            return await c.fetchval(
                """
                SELECT structure_node_id FROM outline_node
                WHERE project_id = $1 AND chapter_id = $2
                  AND kind = 'chapter' AND NOT is_archived
                  AND structure_node_id IS NOT NULL
                ORDER BY rank COLLATE "C", id
                LIMIT 1
                """,
                project_id, chapter_id,
            )

    async def _insert_decomposed_tree(
        self, c: asyncpg.Connection, project_id: UUID, *,
        book_id: UUID, created_by: UUID, arc_title: str, chapters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Insert arc→chapter→scene on an open connection (NO Tx of its own — the
        caller owns the transaction). The ARC is a `structure_node` (kind='arc',
        the 25 M4 lifted model / spec 27 link step — arcs live in `structure_node`,
        NEVER as a `kind='arc'` outline_node, which the post-lift CHECK rejects);
        chapters are outline_nodes LINKED to it via `structure_node_id` (parent_id
        stays NULL — the arc is not an outline parent). `beat_role` is stamped on
        the SCENES (DB CHECK forbids it on chapter); the chapter node carries the
        beat intent in `goal`. Returns the created node ids (UUIDs); `arc_id` is a
        `structure_node` id."""
        # Lazy import avoids a package-load cycle (structure ↔ repositories __init__).
        from app.db.repositories.structure import StructureRepo

        arc = await StructureRepo(self._pool).create_node(
            book_id, created_by=created_by, kind="arc", title=arc_title,
            status="outline", conn=c,
        )
        chapter_ids: list[UUID] = []
        scene_ids: list[UUID] = []
        for ch in chapters:
            ch_node = await self.create_node(
                project_id, created_by=created_by, kind="chapter",
                structure_node_id=arc.id,
                chapter_id=ch["chapter_id"], title=ch.get("title", ""),
                goal=ch.get("intent", ""),
                # The chapter's reading position on the SAME axis its scenes use
                # (chapter_sort * STORY_ORDER_CHAPTER_STRIDE — so a chapter sits exactly at its
                # own scene 0). Omitting it left every chapter node's story_order NULL, which:
                #   • made the plan-overlay canon anchor join (chapter.story_order =
                #     canon_rule.from_order) never match, so a chapter could not carry a canon badge;
                #   • made the arc's derived span/contiguity (BA6) unresolvable (ordered < count);
                #   • degraded the Plan Hub's x-axis to the id tiebreak — i.e. the canvas never
                #     showed reading order at all.
                story_order=ch.get("story_order"),
                status="outline", conn=c,
            )
            chapter_ids.append(ch_node.id)
            for sc in ch.get("scenes", []):
                sn = await self.create_node(
                    project_id, created_by=created_by, kind="scene",
                    parent_id=ch_node.id,
                    chapter_id=ch["chapter_id"], beat_role=ch.get("beat_role"),
                    title=sc.get("title", ""), synopsis=sc.get("synopsis", ""),
                    tension=sc.get("tension"),
                    present_entity_ids=sc.get("present_entity_ids") or [],
                    story_order=sc.get("story_order"),  # reading axis (S1 needs it)
                    status="outline", conn=c,
                )
                scene_ids.append(sn.id)
        return {"arc_id": arc.id, "chapter_ids": chapter_ids, "scene_ids": scene_ids}

    async def create_decomposed_tree(
        self, project_id: UUID, *,
        book_id: UUID, created_by: UUID, arc_title: str, chapters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """A3 commit — persist an arc→chapter→scene tree ATOMICALLY (one Tx).
        Low-level inserter (no idempotency/replace guard); prefer
        `commit_decomposed_tree` from the router. Caller MUST pre-validate
        (chapter_id ∈ book, present_entity_id ∈ glossary)."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                return await self._insert_decomposed_tree(
                    c, project_id, book_id=book_id, created_by=created_by,
                    arc_title=arc_title, chapters=chapters,
                )

    async def resync_reading_order(
        self, book_id: UUID, chapter_sorts: dict[UUID, int],
    ) -> dict[str, int]:
        """24 PH20 Row-3 — rebuild this book's reading-axis MIRROR from book-service's truth.

        `chapter_sorts` is {book chapter_id -> sort_order}, the manuscript's own order. Composition
        stores a DERIVED copy of that order as `outline_node.story_order`
        (`sort_order * STORY_ORDER_CHAPTER_STRIDE` on a chapter, `+ i` on its i-th scene), because
        the packer's strictly-prior lenses and the canon-rule windows key on it. Nothing keeps the
        two in step — composition consumes no book events — so the mirror is rebuilt on demand, and
        this is the ONLY writer of a chapter's slot outside the initial commit.

        Three things move together, in ONE transaction, or the axis is left inconsistent:
          1. every live chapter node → its book slot;
          2. every one of its scenes → chapter slot + index-by-rank;
          3. **canon_rule anchors** — `from_order`/`until_order` are positions on this very axis and
             carry NO node FK (the story timeline IS their only anchor), so a renumber that ignored
             them would silently re-point a rule at whatever chapter now sits in the old slot. They
             are remapped through the old→new slot mapping, preserving any intra-chapter offset.

        Idempotent (a no-op when the mirror already agrees) and safe to re-run — the client chains it
        after a book reorder, so a retry after a partial failure must converge, not drift.

        A chapter node whose `chapter_id` is not in `chapter_sorts` (trashed/purged upstream) is left
        untouched: its position is no longer meaningful, and guessing one would be worse than stale.
        """
        stride = STORY_ORDER_CHAPTER_STRIDE
        moved = {"chapters": 0, "scenes": 0, "canon_rules": 0}
        async with self._pool.acquire() as c:
            async with c.transaction():
                rows = await c.fetch(
                    """
                    SELECT id, chapter_id, story_order FROM outline_node
                     WHERE book_id = $1 AND kind = 'chapter' AND NOT is_archived
                       AND chapter_id IS NOT NULL
                    """,
                    book_id,
                )
                # old slot -> new slot, for the canon remap. Only chapters that HAD a slot can be
                # remapped from; a previously-unpositioned chapter simply gains one.
                slot_map: dict[int, int] = {}
                for r in rows:
                    sort = chapter_sorts.get(r["chapter_id"])
                    if sort is None:
                        continue
                    new_order = sort * stride
                    old_order = r["story_order"]
                    if old_order is not None and old_order != new_order:
                        slot_map[old_order] = new_order
                    if old_order != new_order:
                        await c.execute(
                            "UPDATE outline_node SET story_order = $2, updated_at = now() "
                            "WHERE id = $1",
                            r["id"], new_order,
                        )
                        moved["chapters"] += 1
                    # Scenes always re-derive from the (possibly unchanged) chapter slot: a scene
                    # drag may have left them on the wrong axis even when the chapter didn't move.
                    scenes = await c.execute(
                        """
                        WITH ordered AS (
                          SELECT id, (row_number() OVER (ORDER BY rank COLLATE "C", id) - 1) AS idx
                            FROM outline_node
                           WHERE parent_id = $1 AND kind = 'scene' AND NOT is_archived
                        )
                        UPDATE outline_node n
                           SET story_order = $2 + o.idx, updated_at = now()
                          FROM ordered o
                         WHERE n.id = o.id AND n.story_order IS DISTINCT FROM ($2 + o.idx)
                        """,
                        r["id"], new_order,
                    )
                    moved["scenes"] += int(scenes.split()[-1]) if scenes else 0

                # Canon anchors. A rule's boundary may sit at a scene-level offset inside a chapter
                # (base + k), so remap the BASE and carry the offset across.
                if slot_map:
                    for col in ("from_order", "until_order"):
                        anchors = await c.fetch(
                            f"SELECT id, {col} AS v FROM canon_rule "
                            f"WHERE book_id = $1 AND {col} IS NOT NULL AND NOT is_archived",
                            book_id,
                        )
                        for a in anchors:
                            old = int(a["v"])
                            base, offset = (old // stride) * stride, old % stride
                            new_base = slot_map.get(base)
                            if new_base is None or new_base == base:
                                continue
                            await c.execute(
                                f"UPDATE canon_rule SET {col} = $2 WHERE id = $1",
                                a["id"], new_base + offset,
                            )
                            moved["canon_rules"] += 1
        return moved

    async def commit_decomposed_tree(
        self, project_id: UUID, *,
        book_id: UUID, created_by: UUID, arc_title: str, chapters: list[dict[str, Any]],
        replace: bool = False, idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Atomic + idempotent A3 commit (D-A3-COMMIT-IDEMPOTENCY/TRUE-REPLACE).
        In ONE transaction: (1) replay — a committed `idempotency_key` returns its
        stored result; (2) guard — a target chapter with active scenes + NOT
        `replace` raises AlreadyPlannedError (in-Tx → closes the TOCTOU race a
        pre-Tx check left open); (3) replace — `replace=true` soft-archives ONLY
        the target chapters' existing scenes (book chapters + other plans
        untouched); (4) insert the tree; (5) ledger the (key→result) for replay.
        A per-project advisory lock serializes concurrent commits so even a
        NO-KEY concurrent double-submit can't both pass the guard (the lock — not
        the plain SELECT — is what closes the TOCTOU); keyed exactly-once is also
        backed by the ledger unique index — keyed (project_id, idempotency_key),
        PM-10: the Work partition is the dedup scope, so a derivative replaying a
        client key is never handed the SOURCE Work's stored result. The ledger row
        stamps `created_by` + `book_id` (actor stamp, never a filter). Result ids
        are strings (JSON-stable)."""
        affected = [ch["chapter_id"] for ch in chapters]

        async def _replay(c: asyncpg.Connection) -> dict[str, Any] | None:
            if not idempotency_key:
                return None
            row = await c.fetchrow(
                "SELECT result FROM decompose_commit "
                "WHERE project_id = $1 AND idempotency_key = $2",
                project_id, idempotency_key,
            )
            return {**json.loads(row["result"]), "replay": True} if row else None

        async with self._pool.acquire() as c:
            try:
                async with c.transaction():
                    # Serialize commits per (project) — a plain existing-scenes
                    # SELECT takes no lock, so two concurrent no-key submits would
                    # both see "empty" and double-insert. The advisory xact lock
                    # (namespaced, released at Tx end) makes the guard real for the
                    # no-key path too. Replay is re-checked UNDER the lock so a
                    # concurrent same-key replays instead of hitting the guard.
                    await c.execute(
                        "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                        _DECOMPOSE_COMMIT_LOCK_NS, str(project_id),
                    )
                    replayed = await _replay(c)
                    if replayed is not None:
                        return replayed
                    existing = await c.fetch(
                        """
                        SELECT DISTINCT chapter_id FROM outline_node
                        WHERE project_id = $1 AND kind = 'scene'
                          AND NOT is_archived AND chapter_id = ANY($2)
                        """,
                        project_id, affected,
                    )
                    existing_ids = [r["chapter_id"] for r in existing]
                    if existing_ids and not replace:
                        raise AlreadyPlannedError(existing_ids)
                    if replace:
                        # true replace — soft-archive the target chapters' prior
                        # PLAN nodes: the scene + chapter outline_nodes AND the now-
                        # emptied `structure_node` arc (D-A3-REPLACE-ORPHAN-ARC-NODES
                        # / FD-17). Archiving only scenes left every prior `chapter`
                        # node (and its arc) childless-but-active, accumulating
                        # orphan structure on each re-plan.
                        #
                        # Capture the SPEC ARCS the chapters we're about to archive
                        # link to FIRST (via `structure_node_id`, the 25 M4 lifted
                        # model — arcs are `structure_node` rows, not outline `arc`
                        # nodes), so the arc sweep below is SCOPED to the arc(s) this
                        # replace actually orphans — NOT a book-wide "any childless
                        # arc" sweep, which would also archive an unrelated freshly-
                        # created empty arc (a bystander).
                        candidate_arcs = await c.fetch(
                            """
                            SELECT DISTINCT structure_node_id FROM outline_node
                            WHERE project_id = $1 AND kind = 'chapter'
                              AND NOT is_archived AND chapter_id = ANY($2)
                              AND structure_node_id IS NOT NULL
                            """,
                            project_id, affected,
                        )
                        candidate_arc_ids = [r["structure_node_id"] for r in candidate_arcs]
                        # Archive the prior scene + chapter nodes for the target
                        # chapters. Keyed on `affected` (all target chapters), NOT
                        # `existing_ids` (chapters with active scenes), so this also
                        # reaps chapter nodes whose scenes a prior replace already
                        # archived. chapter_id ties each row to this re-plan — no
                        # bystander risk (an unrelated chapter has a different id).
                        await c.execute(
                            """
                            UPDATE outline_node SET is_archived = true, updated_at = now()
                            WHERE project_id = $1
                              AND kind IN ('scene', 'chapter')
                              AND NOT is_archived AND chapter_id = ANY($2)
                            """,
                            project_id, affected,
                        )
                        # Archive only THOSE candidate spec arcs left with NO active
                        # `chapter` still linking to them. The NOT EXISTS guard
                        # preserves an arc that still spans active chapters OUTSIDE
                        # the target set (a partial re-plan). Scoped by id, so a
                        # bystander empty arc is untouched. Runs BEFORE the insert
                        # (the fresh tree links to a NEW arc, never matched here).
                        # book_id scopes the structure_node side (its scope key).
                        if candidate_arc_ids:
                            await c.execute(
                                """
                                UPDATE structure_node a SET is_archived = true, updated_at = now()
                                WHERE a.book_id = $1 AND a.kind = 'arc'
                                  AND NOT a.is_archived AND a.id = ANY($2)
                                  AND NOT EXISTS (
                                    SELECT 1 FROM outline_node ch
                                    WHERE ch.structure_node_id = a.id
                                      AND ch.kind = 'chapter' AND NOT ch.is_archived
                                  )
                                """,
                                book_id, candidate_arc_ids,
                            )
                    ids = await self._insert_decomposed_tree(
                        c, project_id, book_id=book_id, created_by=created_by,
                        arc_title=arc_title, chapters=chapters,
                    )
                    result = {
                        "arc_id": str(ids["arc_id"]),
                        "chapter_ids": [str(x) for x in ids["chapter_ids"]],
                        "scene_ids": [str(x) for x in ids["scene_ids"]],
                    }
                    if idempotency_key:
                        # Ledger row: created_by is a plain actor stamp; book_id is
                        # derived from composition_work INSIDE the statement (never
                        # NULL). The tree insert above already proved the work row
                        # exists (same Tx), so this SELECT always finds it.
                        await c.execute(
                            """
                            INSERT INTO decompose_commit
                              (created_by, project_id, book_id, idempotency_key, structure_node_id, result)
                            SELECT $1, $2, w.book_id, $3, $4, $5::jsonb
                            FROM composition_work w
                            WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
                            """,
                            created_by, project_id, idempotency_key, ids["arc_id"],
                            json.dumps(result),
                        )
                    return result
            except asyncpg.UniqueViolationError:
                # a concurrent same-key commit won the ledger race → our Tx rolled
                # back (no dup tree). Replay the winner's stored result.
                replayed = await _replay(c)
                if replayed is not None:
                    return replayed
                raise

    async def list_tree(
        self, project_id: UUID, *, include_archived: bool = False,
    ) -> list[OutlineNode]:
        """All nodes of a project as a flat, deterministically-ordered list
        (parent grouping then sibling rank). The router assembles the tree."""
        archived_pred = "" if include_archived else " AND NOT is_archived"
        # rank COLLATE "C": byte-order, matching the fractional-rank algorithm.
        # The DB default (en_US.UTF-8) is a locale collation that does not equal
        # byte order, so we pin it here for deterministic sibling order.
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE project_id = $1{archived_pred}
        ORDER BY parent_id NULLS FIRST, rank COLLATE "C", id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_node(r) for r in rows]

    async def list_children(
        self,
        project_id: UUID,
        parent_id: UUID | None,
        *,
        after: tuple[str, UUID] | None = None,
        limit: int = 100,
        include_archived: bool = False,
    ) -> list[OutlineNode]:
        """Direct children of `parent_id` (NULL → top-level arcs), keyset-paged by
        (rank, id). The lazy-tree primitive for the manuscript navigator: fetch one
        level a page at a time instead of the whole outline. Returns up to limit+1
        rows so the caller can detect a further page.

        `parent_id IS NOT DISTINCT FROM $2` so NULL (top level) matches. rank COLLATE
        "C" (byte order) matches the fractional-rank algorithm + list_tree's ordering,
        so the keyset is a strict total order regardless of DB locale.
        """
        archived_pred = "" if include_archived else " AND NOT is_archived"
        args: list[Any] = [project_id, parent_id]
        keyset_pred = ""
        if after is not None:
            after_rank, after_id = after
            args.extend([after_rank, after_id])
            # strictly after (rank, id): rank byte-greater, or same rank + greater id.
            keyset_pred = (
                f' AND (rank COLLATE "C" > ${len(args) - 1}'
                f' OR (rank COLLATE "C" = ${len(args) - 1} AND id > ${len(args)}))'
            )
        args.append(limit + 1)
        # child_count: non-archived DIRECT children of each row (scene-count badge for a
        # chapter, chapter-count for an arc). Correlated scalar subquery on the
        # (parent_id, …) WHERE-NOT-archived keyset index — one page = `limit` cheap
        # index counts, so it scales with the page, not the 10k tree. project_id on
        # BOTH sides of the self-join (the kinds-bug double-filter rule).
        query = f"""
        SELECT {_SELECT_COLS},
          (SELECT count(*) FROM outline_node c
             WHERE c.project_id = outline_node.project_id
               AND c.parent_id = outline_node.id
               AND NOT c.is_archived) AS child_count
        FROM outline_node
        WHERE project_id = $1
          AND parent_id IS NOT DISTINCT FROM $2{archived_pred}{keyset_pred}
        ORDER BY rank COLLATE "C", id
        LIMIT ${len(args)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *args)
        return [_row_to_node(r) for r in rows]

    async def list_children_by_structure(
        self,
        book_id: UUID,
        structure_node_id: UUID,
        *,
        after: tuple[str, UUID] | None = None,
        limit: int = 100,
    ) -> list[OutlineNode]:
        """24 PH11/H1.1 — the ARC axis of the Plan Hub children window: the CHAPTER
        nodes attached to `structure_node_id`. After the 25 M4 lift a chapter carries
        `parent_id = NULL` and attaches to its arc via `structure_node_id` (arcs are
        `structure_node` rows, not `kind='arc'` outline nodes), so the parent-axis
        `list_children` cannot serve this level. Keyset-paged by (rank, id).

        `book_id` is the TENANCY double-filter (the router already gated VIEW on it;
        the query re-scopes so a `structure_node_id` belonging to ANOTHER book can never
        leak its chapters under a book the caller happens to hold — the kinds-bug
        double-filter rule). `AND kind = 'chapter' AND NOT is_archived` is repeated
        VERBATIM so Postgres matches the partial `idx_outline_node_structure_keyset`
        (H8.1's EXPLAIN asserts it — the planner will NOT infer `kind='chapter'` from the
        `outline_structure_kind` CHECK; without the literal the 10k-chapter window
        degrades to scan+sort). `rank COLLATE "C"` (byte order) matches the fractional-
        rank algorithm so the keyset is a strict total order regardless of DB locale.
        Returns up to limit+1 rows so the caller can detect a further page."""
        args: list[Any] = [structure_node_id, book_id]
        keyset_pred = ""
        if after is not None:
            after_rank, after_id = after
            args.extend([after_rank, after_id])
            # strictly after (rank, id): rank byte-greater, or same rank + greater id.
            keyset_pred = (
                f' AND (rank COLLATE "C" > ${len(args) - 1}'
                f' OR (rank COLLATE "C" = ${len(args) - 1} AND id > ${len(args)}))'
            )
        args.append(limit + 1)
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE structure_node_id = $1 AND book_id = $2
          AND kind = 'chapter' AND NOT is_archived{keyset_pred}
        ORDER BY rank COLLATE "C", id
        LIMIT ${len(args)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *args)
        return [_row_to_node(r) for r in rows]

    async def list_unassigned_chapters(
        self,
        book_id: UUID,
        *,
        after: tuple[str, UUID] | None = None,
        limit: int = 100,
    ) -> list[OutlineNode]:
        """24 PH21 — the UNASSIGNED axis: chapter nodes bound to no arc
        (`structure_node_id IS NULL`).

        Neither existing axis can reach these rows: the ARC axis needs an arc, and the
        PARENT axis needs a `parent_id` — which the 25 M4 lift set to NULL on every
        chapter. So they were unreachable by the Hub entirely, which matters because it
        is the NORMAL post-decompile state: `materialize-scenes` mints chapter + scene
        nodes with no arc (arc grouping is the separate LLM step), and a freshly
        extracted plan would have rendered as an empty canvas.

        This is an explicit, NAMED axis — not "omitted ⇒ everything". The OQ-4 law it
        must not violate is *no silent whole-book fetch*; this returns only the arc-less
        subset, keyset-paged like its siblings. Same `book_id` tenancy scope, same
        `(rank, id)` byte-order keyset, same limit+1 has-more probe."""
        args: list[Any] = [book_id]
        keyset_pred = ""
        if after is not None:
            after_rank, after_id = after
            args.extend([after_rank, after_id])
            keyset_pred = (
                f' AND (rank COLLATE "C" > ${len(args) - 1}'
                f' OR (rank COLLATE "C" = ${len(args) - 1} AND id > ${len(args)}))'
            )
        args.append(limit + 1)
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE book_id = $1 AND structure_node_id IS NULL
          AND kind = 'chapter' AND NOT is_archived{keyset_pred}
        ORDER BY rank COLLATE "C", id
        LIMIT ${len(args)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *args)
        return [_row_to_node(r) for r in rows]

    async def list_children_by_parent_book(
        self,
        book_id: UUID,
        parent_id: UUID,
        *,
        after: tuple[str, UUID] | None = None,
        limit: int = 100,
    ) -> list[OutlineNode]:
        """24 H1.1 — the CHAPTER axis of the Plan Hub children window: the SCENE
        children of `parent_id`, book-scoped. Mirrors `list_children` but keys on
        `book_id` (BPS-8, the Hub's tenancy scope), not `project_id`. Serves the existing
        `idx_outline_node_children_keyset` (parent_id-leading, `WHERE NOT is_archived`).

        `parent_id` is a concrete CHAPTER node id here — the book-keyed route requires
        exactly one of {structure_node_id, parent_id} (OQ-4), so this axis is never called
        with NULL; a plain `parent_id = $2` is correct (no `IS NOT DISTINCT FROM`, which
        would resurrect the "omitted → every chapter" root-semantics bug). `book_id` is the
        tenancy double-filter: a `parent_id` from another book yields no rows under this
        book (its scenes carry that other book's `book_id`). Returns up to limit+1 rows."""
        args: list[Any] = [book_id, parent_id]
        keyset_pred = ""
        if after is not None:
            after_rank, after_id = after
            args.extend([after_rank, after_id])
            keyset_pred = (
                f' AND (rank COLLATE "C" > ${len(args) - 1}'
                f' OR (rank COLLATE "C" = ${len(args) - 1} AND id > ${len(args)}))'
            )
        args.append(limit + 1)
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE book_id = $1 AND parent_id = $2
          AND NOT is_archived{keyset_pred}
        ORDER BY rank COLLATE "C", id
        LIMIT ${len(args)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *args)
        return [_row_to_node(r) for r in rows]

    async def outline_stats(
        self, project_id: UUID,
    ) -> dict[str, int]:
        """Whole-book totals per kind (non-archived) for the navigator footer — arcs / chapters
        / scenes. A single GROUP BY (not derivable from the lazy-loaded tree window). Kinds with
        no rows report 0; 'beat' is excluded (structural, not navigable)."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT kind, count(*) AS n FROM outline_node
                WHERE project_id = $1 AND NOT is_archived AND kind <> 'beat'
                GROUP BY kind
                """,
                project_id,
            )
        out = {"arcs": 0, "chapters": 0, "scenes": 0}
        key = {"arc": "arcs", "chapter": "chapters", "scene": "scenes"}
        for r in rows:
            mapped = key.get(r["kind"])
            if mapped:
                out[mapped] = r["n"]
        return out

    async def search_nodes(
        self, project_id: UUID, q: str, *, limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Title substring search across the outline (arc/chapter/scene), project
        scoped (the Work partition), non-archived. The navigator jump box + Quick
        Open (#06a) share this — it's the server leg that reaches nodes NOT yet
        lazy-loaded into the tree. Each hit carries a breadcrumb `path` (ancestor
        titles, top-first) so a scene shows which chapter/arc it lives in. Bounded
        LIMIT; the ILIKE runs on a per-project table.
        """
        # Escape LIKE metacharacters so the user's query is a literal substring (default
        # backslash escape); a bare `%`/`_` would otherwise act as a wildcard.
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = """
        SELECT n.id, n.kind, n.title, n.chapter_id, n.status, n.story_order,
               p.title  AS parent_title,
               gp.title AS grandparent_title
        FROM outline_node n
        LEFT JOIN outline_node p  ON p.id  = n.parent_id AND p.project_id  = n.project_id
        LEFT JOIN outline_node gp ON gp.id = p.parent_id AND gp.project_id = p.project_id
        WHERE n.project_id = $1 AND NOT n.is_archived
          AND n.kind <> 'beat' AND n.title ILIKE $2
        ORDER BY n.kind, n.story_order NULLS LAST, n.rank COLLATE "C"
        LIMIT $3
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, like, limit)
        out: list[dict[str, Any]] = []
        for r in rows:
            # path top-first: grandparent (arc) → parent (chapter); Nones dropped so an arc
            # yields [], a chapter [arc], a scene [arc, chapter].
            path = [t for t in (r["grandparent_title"], r["parent_title"]) if t]
            out.append({
                "id": str(r["id"]),
                "kind": r["kind"],
                "title": r["title"],
                "chapter_id": str(r["chapter_id"]) if r["chapter_id"] else None,
                "status": r["status"],
                "story_order": r["story_order"],
                "path": path,
            })
        return out

    async def get_node(
        self, node_id: UUID, *, conn: asyncpg.Connection | None = None,
    ) -> OutlineNode | None:
        query = f"SELECT {_SELECT_COLS} FROM outline_node WHERE id = $1"
        if conn is not None:
            row = await conn.fetchrow(query, node_id)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, node_id)
        return _row_to_node(row) if row else None

    async def update_node(
        self,
        node_id: UUID,
        patch: dict[str, Any],
        *,
        expected_version: int | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> OutlineNode | None:
        """Partial update with optional If-Match (same discipline as WorksRepo).
        A 0-row result with `expected_version` set raises VersionMismatchError
        when the row exists (412) or returns None when it doesn't (404)."""
        updates: dict[str, Any] = {}
        for field, value in patch.items():
            if field not in _UPDATABLE_COLUMNS:
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                continue
            updates[field] = value

        if not updates:
            return await self.get_node(node_id, conn=conn)

        set_clauses: list[str] = []
        params: list[Any] = [node_id]
        for field, value in updates.items():
            # 22 SC12/B2 — exit_state is JSONB; asyncpg does not auto-encode a dict, so
            # serialize + cast (mirrors the ::jsonb inserts elsewhere in this repo). A
            # clear (None, allowed since it is nullable) passes through as SQL NULL.
            if field == "exit_state" and value is not None:
                params.append(json.dumps(value))
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
        UPDATE outline_node
        SET {", ".join(set_clauses)}
        WHERE id = $1{version_clause}
        RETURNING {_SELECT_COLS}
        """
        new_parent = updates.get("parent_id")

        async def _do(c: asyncpg.Connection) -> asyncpg.Record | None:
            # Validate a reparent BEFORE the write (cycle / cross-scope guard).
            # Clearing the parent (None → top-level) needs no check.
            if "parent_id" in updates and new_parent is not None:
                await self._validate_reparent(c, node_id, new_parent)
            return await c.fetchrow(query, *params)

        if conn is not None:
            row = await _do(conn)
        else:
            async with self._pool.acquire() as c:
                row = await _do(c)
        if row is not None:
            return _row_to_node(row)
        if expected_version is None:
            return None
        current = await self.get_node(node_id, conn=conn)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def update_node_commit_aware(
        self,
        node_id: UUID,
        patch: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> OutlineNode | None:
        """update_node + emit `composition.scene_committed` ATOMICALLY when a
        scene transitions into status='done' (M9 / §3.1 commit telemetry).

        The prior-status read, the UPDATE, and the outbox emit run in ONE
        transaction so the telemetry can never desync from the status write
        (the outbox is txn-local). On a VersionMismatch / ReferenceViolation the
        transaction rolls back and the exception propagates to the router (→ 412
        / 400) — no half-written state, no orphan event. The emit is gated by
        `_is_scene_commit`, so a non-scene node or a done→done no-op writes no
        event."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                old = await self.get_node(node_id, conn=conn)
                node = await self.update_node(
                    node_id, patch,
                    expected_version=expected_version, conn=conn,
                )
                if _is_scene_commit(old, node):
                    assert node is not None  # _is_scene_commit guarantees it
                    await outbox.emit(
                        conn,
                        aggregate_id=node.project_id,
                        event_type=outbox.SCENE_COMMITTED,
                        payload={
                            "scene_id": str(node.id),
                            "chapter_id": str(node.chapter_id) if node.chapter_id else None,
                            "project_id": str(node.project_id),
                        },
                    )
                return node

    async def chapter_scene_gate(
        self, project_id: UUID, chapter_id: UUID,
    ) -> dict[str, Any]:
        """M9 chapter-gate (OI-1 sweep): can this chapter be published?

        Counts the Work's live scene nodes for `chapter_id`. `can_publish` is
        True only when there is at least one scene AND every scene is 'done' (PO
        decision: block publish until ≥1 done scene — no unreviewed scene gets
        canonized). A chapter with zero composition scenes is NOT publishable
        through the gated affordance (total=0 → can_publish=False); the caller
        scopes the gate to books that actually have a composition Work."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE status = 'done') AS done
                FROM outline_node
                WHERE project_id = $1 AND chapter_id = $2
                  AND kind = 'scene' AND NOT is_archived
                """,
                project_id, chapter_id,
            )
            # D-A2S3B-PUBLISH-GATE — enforce the D4 hard canon block: a scene
            # whose LATEST completed auto-generation left a CONFIRMED canon
            # contradiction (`result.canon.resolved == false`, A2-S3b) must not
            # be published. Conservative-for-canon: a false-pass ships a
            # contradiction; a false-block (the author edited the prose to fix it
            # without re-generating) is recoverable by re-generating. DISTINCT ON
            # the node → only the most recent job per scene counts. project_id on
            # BOTH the job AND the joined node (the kinds-bug double-filter rule).
            canon_row = await c.fetchrow(
                """
                SELECT
                  count(*) FILTER (
                    WHERE (latest.result -> 'canon' ->> 'resolved') = 'false'
                  ) AS unresolved,
                  count(*) FILTER (
                    WHERE (latest.result -> 'canon' ->> 'status')
                          IN ('skipped_no_position', 'degraded')
                  ) AS unchecked
                FROM (
                  SELECT DISTINCT ON (j.outline_node_id) j.result AS result
                  FROM generation_job j
                  JOIN outline_node n ON n.id = j.outline_node_id
                  WHERE j.project_id = $1 AND n.project_id = $1 AND n.chapter_id = $2
                    AND n.kind = 'scene' AND NOT n.is_archived
                    AND j.status = 'completed'
                    -- D-M3-PROSEJOB-PUBLISHGATE: the M3 prose-persist writes a SYNTHETIC
                    -- completed job (operation 'promoted_scene_prose') that carries NO
                    -- canon verdict. It must NOT be the "latest" job here, or it would
                    -- SHADOW an earlier auto-gen's CONFIRMED contradiction and silently
                    -- un-block publish. Excluding it keeps the gate conservative-for-canon:
                    -- a synthetic prose write can't clear a block — only a real
                    -- re-generation (which re-runs the canon-check) can.
                    AND j.operation <> 'promoted_scene_prose'
                  ORDER BY j.outline_node_id, j.created_at DESC, j.id DESC
                ) latest
                """,
                project_id, chapter_id,
            )
        total, done = int(row["total"]), int(row["done"])
        canon_unresolved = int(canon_row["unresolved"]) if canon_row else 0
        # Scenes whose latest auto job had a CAST but could not be verified
        # (dangling chapter position / knowledge outage). Dirty data is normal in
        # a real DB, so this is SURFACED, not hard-blocked — false-blocking every
        # un-positioned scene would be worse; the FE warns + the author can act.
        canon_unchecked = int(canon_row["unchecked"]) if canon_row else 0
        canon_blocked = canon_unresolved > 0
        return {
            "chapter_id": str(chapter_id),
            "scenes_total": total,
            "scenes_done": done,
            # A2-S3b/D4 — surfaced so the FE (A2-S4) can explain WHY publish is
            # blocked (an unresolved canon contradiction vs an undone scene), and
            # warn when canon protection silently did NOT apply (dirty data).
            "canon_blocked": canon_blocked,
            "canon_unresolved_scenes": canon_unresolved,
            "canon_unchecked_scenes": canon_unchecked,
            "can_publish": total > 0 and done == total and not canon_blocked,
        }

    async def canon_issues(self, project_id: UUID) -> list[dict[str, Any]]:
        """Book-wide ITEMIZED canon issues (Studio Quality tab, `quality-canon` panel).

        Same base predicate as `chapter_scene_gate`'s canon half (DISTINCT ON the
        node's latest completed, non-synthetic job; `result.canon.resolved ==
        false`), but un-scoped from a single chapter and returning the actual
        violation rows instead of a count — `chapter_scene_gate` answers "can this
        chapter publish", this answers "show me every open contradiction in the
        book". Returns `chapter_id` only (not a title) — composition-service
        doesn't own chapter titles (book-service does); the caller resolves them
        from whatever chapter list it already has loaded (scope-separation)."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT
                  n.id AS scene_id, n.title AS scene_title, n.chapter_id,
                  latest.job_id, latest.created_at,
                  (latest.result -> 'canon' ->> 'resolved') = 'false' AS unresolved,
                  (latest.result -> 'canon' ->> 'status') AS status,
                  COALESCE(latest.result -> 'canon' -> 'violations', '[]'::jsonb) AS violations
                FROM (
                  SELECT DISTINCT ON (j.outline_node_id)
                    j.outline_node_id, j.id AS job_id, j.result, j.created_at
                  FROM generation_job j
                  JOIN outline_node n2 ON n2.id = j.outline_node_id
                  WHERE j.project_id = $1 AND n2.project_id = $1
                    AND n2.kind = 'scene' AND NOT n2.is_archived
                    AND j.status = 'completed'
                    -- D-M3-PROSEJOB-PUBLISHGATE (same exclusion as chapter_scene_gate):
                    -- a synthetic prose-persist job carries no canon verdict and must
                    -- never shadow an earlier auto-gen's real verdict.
                    AND j.operation <> 'promoted_scene_prose'
                  ORDER BY j.outline_node_id, j.created_at DESC, j.id DESC
                ) latest
                JOIN outline_node n ON n.id = latest.outline_node_id
                  AND n.project_id = $1
                WHERE (latest.result -> 'canon' ->> 'resolved') = 'false'
                ORDER BY latest.created_at DESC
                """,
                project_id,
            )
        return [
            {
                "scene_id": str(r["scene_id"]),
                "scene_title": r["scene_title"],
                "chapter_id": str(r["chapter_id"]) if r["chapter_id"] else None,
                "job_id": str(r["job_id"]),
                "created_at": r["created_at"].isoformat(),
                "status": r["status"],
                "violations": json.loads(r["violations"]) if isinstance(r["violations"], str) else r["violations"],
            }
            for r in rows
        ]

    async def rule_violations(self, project_id: UUID, *, limit: int = RULE_VIOLATIONS_CAP) -> dict[str, Any]:
        """Book-wide canon-RULE violations (Studio Quality tab, `quality-canon` panel; 24 PH18).

        The SIBLING of `canon_issues`, and the distinction is the whole point.
        A generation job carries TWO independent verdicts, written by two engines
        into two columns:

          * `result.canon.violations[]` — entity continuity ("a character marked
            gone is acting"). Keyed by `entity_id`. `canon_check` never loads the
            `canon_rule` table at all, so these rows carry NO rule id — which is
            why `canon_issues` cannot answer "show me violations of rule X".
          * `critic.violations[]` — THIS one. `judge_prose` is handed the active
            rules and its output contract requires a `rule_id` per violation
            (`critic._filter_violations` drops any item lacking one).

        So the rule→violation link the Plan Hub's canon badge needs already exists;
        it lives here. Flat — one item per (scene, violation) — because a deep-link
        targets a RULE and one scene may violate several.

        `rule_id` is LLM output. It is compared as TEXT and never cast to uuid: a
        judge that paraphrases an id must not take the query down. A violation whose
        rule does not resolve (hallucinated id, or the author archived the rule) is
        returned with `rule_text: None`, NEVER dropped — silently dropping every
        unattributable finding would render the panel clean when it is not.

        BOUNDED + partiality-flagged (OUT-5 / Performance Standard "bounded results"),
        the same shape `plan_overlay` (`_REFS_CAP`/`refs_capped`) and `coverage`
        (`UNPLANNED_CAP`/`unplanned_capped`) already use two files away. Rows are FLAT
        per (scene x violation) and each carries the rule's full text, so a long book
        multiplies out fast. The COUNT stays exact even when the list is capped — a
        truncation the reader cannot see is worse than no list at all."""
        async with self._pool.acquire() as c:
            total = await c.fetchval(
                """
                WITH latest AS (
                  SELECT DISTINCT ON (j.outline_node_id)
                    j.outline_node_id, j.critic
                  FROM generation_job j
                  JOIN outline_node n2 ON n2.id = j.outline_node_id
                  WHERE j.project_id = $1 AND n2.project_id = $1
                    AND n2.kind = 'scene' AND NOT n2.is_archived
                    AND j.status = 'completed'
                    AND j.operation <> 'promoted_scene_prose'
                  ORDER BY j.outline_node_id, j.created_at DESC, j.id DESC
                )
                SELECT count(*)
                FROM latest
                CROSS JOIN LATERAL jsonb_array_elements(
                  COALESCE(latest.critic -> 'violations', '[]'::jsonb)
                ) AS e(value)
                WHERE (e.value -> 'violated')  IS DISTINCT FROM 'false'::jsonb
                  AND (e.value -> 'dismissed') IS DISTINCT FROM 'true'::jsonb
                """,
                project_id,
            )
            rows = await c.fetch(
                """
                WITH latest AS (
                  SELECT DISTINCT ON (j.outline_node_id)
                    j.outline_node_id, j.id AS job_id, j.critic, j.created_at
                  FROM generation_job j
                  JOIN outline_node n2 ON n2.id = j.outline_node_id
                  WHERE j.project_id = $1 AND n2.project_id = $1
                    AND n2.kind = 'scene' AND NOT n2.is_archived
                    AND j.status = 'completed'
                    -- Same exclusion as canon_issues/chapter_scene_gate: a synthetic
                    -- prose-persist job runs no critic and must never shadow a real one.
                    AND j.operation <> 'promoted_scene_prose'
                  ORDER BY j.outline_node_id, j.created_at DESC, j.id DESC
                ), v AS (
                  SELECT latest.outline_node_id, latest.job_id, latest.created_at,
                         e.value AS violation
                  FROM latest
                  CROSS JOIN LATERAL jsonb_array_elements(
                    COALESCE(latest.critic -> 'violations', '[]'::jsonb)
                  ) AS e(value)
                  -- jsonb comparison, not ::boolean — a malformed judge value must
                  -- degrade to "still a violation", never throw. Default-open on
                  -- `violated` (absent ⇒ it IS one) and default-closed on `dismissed`
                  -- (only an explicit human dismiss silences a finding).
                  WHERE (e.value -> 'violated')  IS DISTINCT FROM 'false'::jsonb
                    AND (e.value -> 'dismissed') IS DISTINCT FROM 'true'::jsonb
                )
                SELECT
                  n.id AS scene_id, n.title AS scene_title, n.chapter_id,
                  v.job_id, v.created_at,
                  v.violation ->> 'rule_id' AS rule_id,
                  v.violation ->> 'span'    AS span,
                  v.violation ->> 'why'     AS why,
                  cr.text AS rule_text
                FROM v
                JOIN outline_node n
                  ON n.id = v.outline_node_id AND n.project_id = $1
                LEFT JOIN canon_rule cr
                  ON cr.id::text = v.violation ->> 'rule_id'
                 AND cr.project_id = $1 AND cr.active AND NOT cr.is_archived
                ORDER BY v.created_at DESC
                LIMIT $2
                """,
                project_id, limit,
            )
        items = [
            {
                "scene_id": str(r["scene_id"]),
                "scene_title": r["scene_title"],
                "chapter_id": str(r["chapter_id"]) if r["chapter_id"] else None,
                "job_id": str(r["job_id"]),
                "created_at": r["created_at"].isoformat(),
                "rule_id": r["rule_id"],
                "rule_text": r["rule_text"],
                "span": r["span"] or "",
                "why": r["why"] or "",
            }
            for r in rows
        ]
        return {"items": items, "count": int(total or 0), "capped": int(total or 0) > len(items)}

    async def archive_node(self, node_id: UUID) -> OutlineNode | None:
        """Soft-archive a node AND its descendants (PO decision — no orphaned-
        visible children). A recursive CTE walks parent_id down from the target,
        then one UPDATE flips is_archived on the whole subtree. Returns the
        target node (archived) or None if it doesn't exist / was already
        archived. project_id is threaded through every CTE leg, so the subtree
        can only contain nodes of the same Work (defense against a malformed
        cross-project parent edge).

        UNION (not UNION ALL): defense-in-depth against a malformed parent_id
        CYCLE — UNION ALL would recurse forever (and hang past the pool
        command_timeout), UNION dedups so the walk terminates at the cycle. Note
        that reparent-cycle PREVENTION is already enforced upstream by
        `_validate_reparent` (via `_descendant_ids`) on every `update_node`
        reparent (D-COMP-M2-XREF-OWNERSHIP CLEARED, LOOM cycle 5); a cycle is only
        reachable via raw SQL, which this UNION still tolerates as a backstop."""
        query = f"""
        WITH RECURSIVE subtree AS (
          SELECT id, project_id FROM outline_node
          WHERE id = $1 AND NOT is_archived
          UNION
          SELECT n.id, n.project_id FROM outline_node n
          JOIN subtree s ON n.parent_id = s.id AND n.project_id = s.project_id
          WHERE NOT n.is_archived
        )
        UPDATE outline_node
        SET is_archived = true, updated_at = now()
        WHERE id IN (SELECT id FROM subtree)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, node_id)
        target = next((r for r in rows if r["id"] == node_id), None)
        return _row_to_node(target) if target else None

    async def restore_node(self, node_id: UUID) -> OutlineNode | None:
        """Un-archive a node — the inverse of `archive_node` (T1.1b restore). Two
        recursive walks over ARCHIVED rows only:
          - `subtree` walks parent_id DOWN → restores the node's archived
            descendants (symmetric with the archive cascade);
          - `ancestors` walks parent_id UP → restores the archived ancestor chain
            so the restored node always reconnects to a visible root (else a node
            whose parent is still archived would orphan out of the tree).
        Sibling branches stay archived (only the direct ancestor chain is walked).
        Returns the target (restored) or None if it doesn't exist / wasn't
        archived. UNION (not UNION ALL) so a malformed parent_id cycle terminates
        instead of hanging (same backstop as archive_node). project_id is
        threaded through every CTE leg (same Work-partition defense)."""
        query = f"""
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_id, project_id FROM outline_node
          WHERE id = $1 AND is_archived
          UNION
          SELECT p.id, p.parent_id, p.project_id FROM outline_node p
          JOIN ancestors a ON p.id = a.parent_id AND p.project_id = a.project_id
          WHERE p.is_archived
        ),
        subtree AS (
          SELECT id, project_id FROM outline_node
          WHERE id = $1 AND is_archived
          UNION
          SELECT n.id, n.project_id FROM outline_node n
          JOIN subtree s ON n.parent_id = s.id AND n.project_id = s.project_id
          WHERE n.is_archived
        )
        UPDATE outline_node
        SET is_archived = false, updated_at = now()
        WHERE (id IN (SELECT id FROM ancestors) OR id IN (SELECT id FROM subtree))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, node_id)
        target = next((r for r in rows if r["id"] == node_id), None)
        return _row_to_node(target) if target else None

    async def _renumber_scene_story_order(
        self, c: asyncpg.Connection, project_id: UUID, parent_id: UUID | None,
    ) -> None:
        """Renumber `story_order` for the SCENE children of `parent_id` (T1.1c reorder),
        keeping the reading axis in lockstep with the tree's `rank` order so the FE's
        story_order-first sort reflects a drag with no client renumber.

        The scene's position is its CHAPTER's slot plus its index within the chapter
        (`chapter.story_order + i`) — the ONE global reading axis, chapter-major /
        scene-minor, shared with `plan.py`'s commit, `chapter_gen`, the packer's
        strictly-prior lenses, and the canon-rule windows.

        This previously renumbered scenes to a chapter-LOCAL `0..n-1`, which silently
        collapsed a chapter's scenes onto the same low integers as every other chapter's
        the moment anyone dragged a scene: the global order was destroyed, the packer's
        "prior scenes" filter started matching across chapters, and canon windows
        mis-fired. Two conventions on one column — this is the surviving one.

        A chapter with no position of its own yields NULL (propagated) rather than a
        fabricated 0 — an unknown slot must not claim to be the book's first.
        NOT version-bumped — story_order is a system-maintained ordinal, not a user field.
        project_id-scoped, so the renumber can never leave this Work."""
        await c.execute(
            """
            WITH base AS (
              SELECT story_order AS b FROM outline_node
               WHERE id = $2 AND project_id = $1
            ), ordered AS (
              SELECT id, (row_number() OVER (ORDER BY rank COLLATE "C", id) - 1) AS idx
              FROM outline_node
              WHERE project_id = $1 AND parent_id IS NOT DISTINCT FROM $2
                AND kind = 'scene' AND NOT is_archived
            )
            UPDATE outline_node n
            SET story_order = (SELECT b FROM base) + o.idx, updated_at = now()
            FROM ordered o
            WHERE n.id = o.id AND n.project_id = $1
              AND n.story_order IS DISTINCT FROM ((SELECT b FROM base) + o.idx)
            """,
            project_id, parent_id,
        )

    async def reorder_node(
        self,
        node_id: UUID,
        *,
        new_parent_id: UUID | None,
        after_id: UUID | None,
        expected_version: int | None = None,
    ) -> OutlineNode | None:
        """T1.1c drag-reorder + reparent. Places `node_id` under `new_parent_id`
        directly AFTER `after_id` (None = first child) by computing a fractional
        `rank` strictly between `after_id` and the next sibling — a single-row
        rank write, never a full renumber. Reparenting a SCENE across chapters
        also inherits the new chapter's `chapter_id` (the DB CHECK requires a
        scene to carry one). Finally dense-renumbers `story_order` for the scene
        siblings of the affected parent(s). All in ONE transaction so a stale
        If-Match (412) or a cycle (400) rolls the whole move back.

        Returns the moved node (re-read, reflecting rank + parent + renumbered
        story_order), None if it doesn't exist (404). Raises VersionMismatchError
        (412) / ReferenceViolationError (cycle/ownership/bad after_id → 400)."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                node = await self.get_node(node_id, conn=c)
                if node is None:
                    return None
                if new_parent_id is not None:
                    # cycle / cross-scope guard (reused from update_node's reparent)
                    await self._validate_reparent(c, node_id, new_parent_id)

                # Siblings under the destination parent, excluding the moved node,
                # in canonical fractional-rank (byte) order. project_id-scoped:
                # parent_id may be NULL (top level).
                siblings = await c.fetch(
                    """
                    SELECT id, rank FROM outline_node
                    WHERE project_id = $1 AND parent_id IS NOT DISTINCT FROM $2
                      AND id <> $3 AND NOT is_archived
                    ORDER BY rank COLLATE "C", id
                    """,
                    node.project_id, new_parent_id, node_id,
                )
                if after_id is None:
                    lo, hi = None, (siblings[0]["rank"] if siblings else None)
                else:
                    idx = next((i for i, s in enumerate(siblings) if s["id"] == after_id), None)
                    if idx is None:
                        raise ReferenceViolationError(
                            f"after_id {after_id} is not a sibling under the new parent"
                        )
                    lo = siblings[idx]["rank"]
                    hi = siblings[idx + 1]["rank"] if idx + 1 < len(siblings) else None
                new_rank = rank_between(lo, hi)

                patch: dict[str, Any] = {"rank": new_rank}
                if new_parent_id != node.parent_id:
                    patch["parent_id"] = new_parent_id
                    if node.kind == "scene" and new_parent_id is not None:
                        np = await c.fetchrow(
                            "SELECT chapter_id FROM outline_node "
                            "WHERE project_id = $1 AND id = $2",
                            node.project_id, new_parent_id,
                        )
                        if np is not None and np["chapter_id"] is not None:
                            patch["chapter_id"] = np["chapter_id"]

                # update_node owns the If-Match/version discipline + the reparent
                # revalidation; a 412 raises here → the Tx rolls back (no renumber).
                await self.update_node(
                    node_id, patch, expected_version=expected_version, conn=c,
                )

                await self._renumber_scene_story_order(c, node.project_id, new_parent_id)
                if node.parent_id != new_parent_id:
                    await self._renumber_scene_story_order(c, node.project_id, node.parent_id)

                return await self.get_node(node_id, conn=c)
