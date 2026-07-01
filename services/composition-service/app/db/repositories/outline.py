"""outline_node repository — the Arc→Chapter→Scene→Beat tree (§1.2/§5).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. Sibling order is a fractional `rank` (see rank.py) so an insert
touches one row. DELETE is a RECURSIVE soft-archive (PO decision): archiving a
node also archives its descendants, so no orphaned-visible child survives under
an archived parent. Hard FK CASCADE is reserved for scene_link edges only.
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

_SELECT_COLS = """
  id, user_id, project_id, parent_id, kind, rank, title, pov_entity_id,
  present_entity_ids, goal, beat_role, status, chapter_id, tension,
  story_order, synopsis, version, is_archived, created_at, updated_at
"""

# Namespace key (arg-1) for the per-project decompose-commit advisory xact lock.
# Distinguishes it from any other pg_advisory_xact_lock(int4, int4) in the service.
_DECOMPOSE_COMMIT_LOCK_NS = 0x10AF

_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"parent_id", "rank", "title", "pov_entity_id", "present_entity_ids", "goal",
     "beat_role", "status", "chapter_id", "tension", "story_order", "synopsis"}
)
# Columns that accept an explicit NULL (clear). The others are NOT NULL, so a
# None on them is skipped (treated as no-op for that field).
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"parent_id", "pov_entity_id", "beat_role", "chapter_id", "tension", "story_order"}
)


def _row_to_node(row: asyncpg.Record) -> OutlineNode:
    return OutlineNode.model_validate(dict(row))


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
        self, conn: asyncpg.Connection, user_id: UUID, project_id: UUID,
        parent_id: UUID | None,
    ) -> str:
        """Append position: a rank after the current last sibling under parent.

        `parent_id IS NOT DISTINCT FROM $3` so NULL (top-level) groups together
        and compares equal — a plain `=` would never match NULL.
        """
        # max(rank COLLATE "C"): the DB default collation is en_US.UTF-8 (NOT
        # byte-order), so an unqualified max(rank) could pick a different "last"
        # sibling than fractional-rank byte ordering intends. COLLATE "C" makes
        # it exact regardless of DB locale.
        last = await conn.fetchval(
            """
            SELECT max(rank COLLATE "C") FROM outline_node
            WHERE user_id = $1 AND project_id = $2
              AND parent_id IS NOT DISTINCT FROM $3 AND NOT is_archived
            """,
            user_id, project_id, parent_id,
        )
        return rank_after(last)

    async def _validate_parent(
        self, conn: asyncpg.Connection, user_id: UUID, project_id: UUID,
        parent_id: UUID,
    ) -> None:
        """Ensure `parent_id` is one of the caller's nodes in the SAME project.

        Defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): the in-DB FK only proves the
        parent EXISTS — not that it is the caller's, nor in this project. Without
        this a node could be parented under another user's / another project's
        node (a broken cross-scope edge)."""
        row = await conn.fetchrow(
            "SELECT project_id FROM outline_node WHERE user_id = $1 AND id = $2",
            user_id, parent_id,
        )
        if row is None:
            raise ReferenceViolationError(f"parent node {parent_id} not found for user")
        if row["project_id"] != project_id:
            raise ReferenceViolationError(
                f"parent node {parent_id} is in a different project"
            )

    async def _descendant_ids(
        self, conn: asyncpg.Connection, user_id: UUID, node_id: UUID,
    ) -> set[UUID]:
        """The caller's descendants of `node_id` (NOT including node_id). UNION
        dedups so a pre-existing malformed cycle can't loop the walk."""
        rows = await conn.fetch(
            """
            WITH RECURSIVE descendants AS (
              SELECT id FROM outline_node WHERE user_id = $1 AND parent_id = $2
              UNION
              SELECT n.id FROM outline_node n
              JOIN descendants d ON n.parent_id = d.id
              WHERE n.user_id = $1
            )
            SELECT id FROM descendants
            """,
            user_id, node_id,
        )
        return {r["id"] for r in rows}

    async def _validate_reparent(
        self, conn: asyncpg.Connection, user_id: UUID, node_id: UUID,
        new_parent_id: UUID,
    ) -> None:
        """Guard a reparent: not self, parent owned + same project, and not a
        descendant (cycle). Prevents the malformed cycle at the source — the
        archive_node UNION is the backstop for any cycle that still slips in."""
        if new_parent_id == node_id:
            raise ReferenceViolationError("a node cannot be its own parent")
        node = await conn.fetchrow(
            "SELECT project_id FROM outline_node WHERE user_id = $1 AND id = $2",
            user_id, node_id,
        )
        if node is None:
            # Node missing / not ours: let the UPDATE 0-row path report 404/412.
            return
        await self._validate_parent(conn, user_id, node["project_id"], new_parent_id)
        if new_parent_id in await self._descendant_ids(conn, user_id, node_id):
            raise ReferenceViolationError(
                f"reparenting under descendant {new_parent_id} would create a cycle"
            )

    async def create_node(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
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
        tension: int | None = None,
        story_order: int | None = None,
        synopsis: str = "",
        conn: asyncpg.Connection | None = None,
    ) -> OutlineNode:
        """Insert an outline node. When `rank` is omitted it is auto-computed to
        append after the last sibling under `parent_id` (single-row touch)."""
        async def _do(c: asyncpg.Connection) -> asyncpg.Record:
            if parent_id is not None:
                await self._validate_parent(c, user_id, project_id, parent_id)
            node_rank = rank if rank is not None else await self._next_rank(
                c, user_id, project_id, parent_id
            )
            return await c.fetchrow(
                f"""
                INSERT INTO outline_node
                  (user_id, project_id, parent_id, kind, rank, title, pov_entity_id,
                   present_entity_ids, goal, beat_role, status, chapter_id, tension,
                   story_order, synopsis)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                RETURNING {_SELECT_COLS}
                """,
                user_id, project_id, parent_id, kind, node_rank, title, pov_entity_id,
                present_entity_ids or [], goal, beat_role, status, chapter_id,
                tension, story_order, synopsis,
            )

        if conn is not None:
            row = await _do(conn)
        else:
            async with self._pool.acquire() as c:
                row = await _do(c)
        return _row_to_node(row)

    async def existing_scene_chapter_ids(
        self, user_id: UUID, project_id: UUID, chapter_ids: list[UUID],
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
                WHERE user_id = $1 AND project_id = $2 AND kind = 'scene'
                  AND NOT is_archived AND chapter_id = ANY($3)
                """,
                user_id, project_id, chapter_ids,
            )
        return {r["chapter_id"] for r in rows}

    async def scenes_for_chapter(
        self, user_id: UUID, project_id: UUID, chapter_id: UUID,
    ) -> list[OutlineNode]:
        """B2 chapter-assembly — the caller's active scene nodes for `chapter_id`
        in reading order (story_order, then fractional rank as tiebreak). The
        chapter single-pass path builds its combined synopsis + union cast from
        these (the A3 decompose plan). story_order NULLS LAST so a legacy scene
        without a reading-order still sorts deterministically after placed ones."""
        async with self._pool.acquire() as c:
            rows = await c.fetch(
                f"""
                SELECT {_SELECT_COLS} FROM outline_node
                WHERE user_id = $1 AND project_id = $2 AND chapter_id = $3
                  AND kind = 'scene' AND NOT is_archived
                ORDER BY story_order NULLS LAST, rank COLLATE "C", id
                """,
                user_id, project_id, chapter_id,
            )
        return [_row_to_node(r) for r in rows]

    async def _insert_decomposed_tree(
        self, c: asyncpg.Connection, user_id: UUID, project_id: UUID, *,
        arc_title: str, chapters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Insert arc→chapter→scene on an open connection (NO Tx of its own — the
        caller owns the transaction). `beat_role` is stamped on the SCENES (DB
        CHECK forbids it on chapter); the chapter node carries the beat intent in
        `goal`. Returns the created node ids (UUIDs)."""
        arc = await self.create_node(
            user_id, project_id, kind="arc", title=arc_title, status="outline", conn=c,
        )
        chapter_ids: list[UUID] = []
        scene_ids: list[UUID] = []
        for ch in chapters:
            ch_node = await self.create_node(
                user_id, project_id, kind="chapter", parent_id=arc.id,
                chapter_id=ch["chapter_id"], title=ch.get("title", ""),
                goal=ch.get("intent", ""), status="outline", conn=c,
            )
            chapter_ids.append(ch_node.id)
            for sc in ch.get("scenes", []):
                sn = await self.create_node(
                    user_id, project_id, kind="scene", parent_id=ch_node.id,
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
        self, user_id: UUID, project_id: UUID, *,
        arc_title: str, chapters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """A3 commit — persist an arc→chapter→scene tree ATOMICALLY (one Tx).
        Low-level inserter (no idempotency/replace guard); prefer
        `commit_decomposed_tree` from the router. Caller MUST pre-validate
        (chapter_id ∈ book, present_entity_id ∈ glossary)."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                return await self._insert_decomposed_tree(
                    c, user_id, project_id, arc_title=arc_title, chapters=chapters,
                )

    async def commit_decomposed_tree(
        self, user_id: UUID, project_id: UUID, *,
        arc_title: str, chapters: list[dict[str, Any]],
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
        backed by the ledger unique index. Result ids are strings (JSON-stable)."""
        affected = [ch["chapter_id"] for ch in chapters]

        async def _replay(c: asyncpg.Connection) -> dict[str, Any] | None:
            if not idempotency_key:
                return None
            row = await c.fetchrow(
                "SELECT result FROM decompose_commit "
                "WHERE user_id = $1 AND project_id = $2 AND idempotency_key = $3",
                user_id, project_id, idempotency_key,
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
                        WHERE user_id = $1 AND project_id = $2 AND kind = 'scene'
                          AND NOT is_archived AND chapter_id = ANY($3)
                        """,
                        user_id, project_id, affected,
                    )
                    existing_ids = [r["chapter_id"] for r in existing]
                    if existing_ids and not replace:
                        raise AlreadyPlannedError(existing_ids)
                    if replace:
                        # true replace — soft-archive the target chapters' prior
                        # PLAN nodes: BOTH scenes AND their `chapter` nodes
                        # (D-A3-REPLACE-ORPHAN-ARC-NODES / FD-17). Archiving only
                        # scenes left every prior `chapter` node (and its `arc`)
                        # childless-but-active, accumulating orphan structure on
                        # each re-plan.
                        #
                        # Capture the parent arcs of the chapter nodes we're about
                        # to archive FIRST, so the arc sweep below is SCOPED to the
                        # arc(s) this replace actually orphans — NOT a project-wide
                        # "any childless arc" sweep, which would also archive an
                        # unrelated freshly-created empty arc (a bystander). Arcs
                        # carry no chapter_id, so they can only be tied to this
                        # operation through the chapter→arc parent link.
                        candidate_arcs = await c.fetch(
                            """
                            SELECT DISTINCT parent_id FROM outline_node
                            WHERE user_id = $1 AND project_id = $2 AND kind = 'chapter'
                              AND NOT is_archived AND chapter_id = ANY($3)
                              AND parent_id IS NOT NULL
                            """,
                            user_id, project_id, affected,
                        )
                        candidate_arc_ids = [r["parent_id"] for r in candidate_arcs]
                        # Archive the prior scene + chapter nodes for the target
                        # chapters. Keyed on `affected` (all target chapters), NOT
                        # `existing_ids` (chapters with active scenes), so this also
                        # reaps chapter nodes whose scenes a prior replace already
                        # archived. chapter_id ties each row to this re-plan — no
                        # bystander risk (an unrelated chapter has a different id).
                        await c.execute(
                            """
                            UPDATE outline_node SET is_archived = true, updated_at = now()
                            WHERE user_id = $1 AND project_id = $2
                              AND kind IN ('scene', 'chapter')
                              AND NOT is_archived AND chapter_id = ANY($3)
                            """,
                            user_id, project_id, affected,
                        )
                        # Archive only THOSE candidate arcs left with NO active
                        # `chapter` child. The NOT EXISTS guard preserves an arc
                        # that still spans active chapters OUTSIDE the target set (a
                        # partial re-plan). Scoped by id, so a bystander empty arc
                        # is untouched. Runs BEFORE the insert (the fresh tree is
                        # never matched).
                        if candidate_arc_ids:
                            await c.execute(
                                """
                                UPDATE outline_node a SET is_archived = true, updated_at = now()
                                WHERE a.user_id = $1 AND a.kind = 'arc'
                                  AND NOT a.is_archived AND a.id = ANY($2)
                                  AND NOT EXISTS (
                                    SELECT 1 FROM outline_node ch
                                    WHERE ch.user_id = $1 AND ch.parent_id = a.id
                                      AND ch.kind = 'chapter' AND NOT ch.is_archived
                                  )
                                """,
                                user_id, candidate_arc_ids,
                            )
                    ids = await self._insert_decomposed_tree(
                        c, user_id, project_id, arc_title=arc_title, chapters=chapters,
                    )
                    result = {
                        "arc_id": str(ids["arc_id"]),
                        "chapter_ids": [str(x) for x in ids["chapter_ids"]],
                        "scene_ids": [str(x) for x in ids["scene_ids"]],
                    }
                    if idempotency_key:
                        await c.execute(
                            """
                            INSERT INTO decompose_commit
                              (user_id, project_id, idempotency_key, arc_id, result)
                            VALUES ($1, $2, $3, $4, $5::jsonb)
                            """,
                            user_id, project_id, idempotency_key, ids["arc_id"], json.dumps(result),
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
        self, user_id: UUID, project_id: UUID, *, include_archived: bool = False,
    ) -> list[OutlineNode]:
        """All nodes of a project as a flat, deterministically-ordered list
        (parent grouping then sibling rank). The router assembles the tree."""
        archived_pred = "" if include_archived else " AND NOT is_archived"
        # rank COLLATE "C": byte-order, matching the fractional-rank algorithm.
        # The DB default (en_US.UTF-8) is a locale collation that does not equal
        # byte order, so we pin it here for deterministic sibling order.
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE user_id = $1 AND project_id = $2{archived_pred}
        ORDER BY parent_id NULLS FIRST, rank COLLATE "C", id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_node(r) for r in rows]

    async def list_children(
        self,
        user_id: UUID,
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

        `parent_id IS NOT DISTINCT FROM $3` so NULL (top level) matches. rank COLLATE
        "C" (byte order) matches the fractional-rank algorithm + list_tree's ordering,
        so the keyset is a strict total order regardless of DB locale.
        """
        archived_pred = "" if include_archived else " AND NOT is_archived"
        args: list[Any] = [user_id, project_id, parent_id]
        keyset_pred = ""
        if after is not None:
            after_rank, after_id = after
            args.extend([after_rank, after_id])
            # strictly after (rank, id): rank byte-greater, or same rank + greater id.
            keyset_pred = (
                f' AND (rank COLLATE "C" > ${len(args) - 1}'
                f' OR (rank = ${len(args) - 1} AND id > ${len(args)}))'
            )
        args.append(limit + 1)
        query = f"""
        SELECT {_SELECT_COLS} FROM outline_node
        WHERE user_id = $1 AND project_id = $2
          AND parent_id IS NOT DISTINCT FROM $3{archived_pred}{keyset_pred}
        ORDER BY rank COLLATE "C", id
        LIMIT ${len(args)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *args)
        return [_row_to_node(r) for r in rows]

    async def get_node(
        self, user_id: UUID, node_id: UUID, *, conn: asyncpg.Connection | None = None,
    ) -> OutlineNode | None:
        query = f"SELECT {_SELECT_COLS} FROM outline_node WHERE user_id = $1 AND id = $2"
        if conn is not None:
            row = await conn.fetchrow(query, user_id, node_id)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, user_id, node_id)
        return _row_to_node(row) if row else None

    async def update_node(
        self,
        user_id: UUID,
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
            return await self.get_node(user_id, node_id, conn=conn)

        set_clauses: list[str] = []
        params: list[Any] = [user_id, node_id]
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
        UPDATE outline_node
        SET {", ".join(set_clauses)}
        WHERE user_id = $1 AND id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        new_parent = updates.get("parent_id")

        async def _do(c: asyncpg.Connection) -> asyncpg.Record | None:
            # Validate a reparent BEFORE the write (cycle / cross-scope guard).
            # Clearing the parent (None → top-level) needs no check.
            if "parent_id" in updates and new_parent is not None:
                await self._validate_reparent(c, user_id, node_id, new_parent)
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
        current = await self.get_node(user_id, node_id, conn=conn)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def update_node_commit_aware(
        self,
        user_id: UUID,
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
                old = await self.get_node(user_id, node_id, conn=conn)
                node = await self.update_node(
                    user_id, node_id, patch,
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
        self, user_id: UUID, project_id: UUID, chapter_id: UUID,
    ) -> dict[str, Any]:
        """M9 chapter-gate (OI-1 sweep): can this chapter be published?

        Counts the caller's live scene nodes for `chapter_id`. `can_publish` is
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
                WHERE user_id = $1 AND project_id = $2 AND chapter_id = $3
                  AND kind = 'scene' AND NOT is_archived
                """,
                user_id, project_id, chapter_id,
            )
            # D-A2S3B-PUBLISH-GATE — enforce the D4 hard canon block: a scene
            # whose LATEST completed auto-generation left a CONFIRMED canon
            # contradiction (`result.canon.resolved == false`, A2-S3b) must not
            # be published. Conservative-for-canon: a false-pass ships a
            # contradiction; a false-block (the author edited the prose to fix it
            # without re-generating) is recoverable by re-generating. DISTINCT ON
            # the node → only the most recent job per scene counts.
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
                  WHERE j.user_id = $1 AND j.project_id = $2 AND n.chapter_id = $3
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
                user_id, project_id, chapter_id,
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

    async def archive_node(self, user_id: UUID, node_id: UUID) -> OutlineNode | None:
        """Soft-archive a node AND its descendants (PO decision — no orphaned-
        visible children). A recursive CTE walks parent_id down from the target,
        then one UPDATE flips is_archived on the whole subtree. Returns the
        target node (archived) or None if it doesn't exist / isn't ours / was
        already archived. Scoped by user_id at the CTE root, so the subtree can
        only contain the caller's nodes.

        UNION (not UNION ALL): defense-in-depth against a malformed parent_id
        CYCLE — UNION ALL would recurse forever (and hang past the pool
        command_timeout), UNION dedups so the walk terminates at the cycle. Note
        that reparent-cycle PREVENTION is already enforced upstream by
        `_validate_reparent` (via `_descendant_ids`) on every `update_node`
        reparent (D-COMP-M2-XREF-OWNERSHIP CLEARED, LOOM cycle 5); a cycle is only
        reachable via raw SQL, which this UNION still tolerates as a backstop."""
        query = f"""
        WITH RECURSIVE subtree AS (
          SELECT id FROM outline_node
          WHERE user_id = $1 AND id = $2 AND NOT is_archived
          UNION
          SELECT n.id FROM outline_node n
          JOIN subtree s ON n.parent_id = s.id
          WHERE n.user_id = $1 AND NOT n.is_archived
        )
        UPDATE outline_node
        SET is_archived = true, updated_at = now()
        WHERE user_id = $1 AND id IN (SELECT id FROM subtree)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, node_id)
        target = next((r for r in rows if r["id"] == node_id), None)
        return _row_to_node(target) if target else None

    async def restore_node(self, user_id: UUID, node_id: UUID) -> OutlineNode | None:
        """Un-archive a node — the inverse of `archive_node` (T1.1b restore). Two
        recursive walks over ARCHIVED rows only:
          - `subtree` walks parent_id DOWN → restores the node's archived
            descendants (symmetric with the archive cascade);
          - `ancestors` walks parent_id UP → restores the archived ancestor chain
            so the restored node always reconnects to a visible root (else a node
            whose parent is still archived would orphan out of the tree).
        Sibling branches stay archived (only the direct ancestor chain is walked).
        Returns the target (restored) or None if it doesn't exist / isn't ours /
        wasn't archived. UNION (not UNION ALL) so a malformed parent_id cycle
        terminates instead of hanging (same backstop as archive_node)."""
        query = f"""
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_id FROM outline_node
          WHERE user_id = $1 AND id = $2 AND is_archived
          UNION
          SELECT p.id, p.parent_id FROM outline_node p
          JOIN ancestors a ON p.id = a.parent_id
          WHERE p.user_id = $1 AND p.is_archived
        ),
        subtree AS (
          SELECT id FROM outline_node
          WHERE user_id = $1 AND id = $2 AND is_archived
          UNION
          SELECT n.id FROM outline_node n
          JOIN subtree s ON n.parent_id = s.id
          WHERE n.user_id = $1 AND n.is_archived
        )
        UPDATE outline_node
        SET is_archived = false, updated_at = now()
        WHERE user_id = $1
          AND (id IN (SELECT id FROM ancestors) OR id IN (SELECT id FROM subtree))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, node_id)
        target = next((r for r in rows if r["id"] == node_id), None)
        return _row_to_node(target) if target else None

    async def _renumber_scene_story_order(
        self, c: asyncpg.Connection, user_id: UUID, parent_id: UUID | None,
    ) -> None:
        """Dense-renumber `story_order` (0..n-1, by fractional rank) for the
        SCENE children of `parent_id` (T1.1c reorder). Keeps the reading axis
        (story_order) in lockstep with the tree's `rank` order, so the FE's
        story_order-first sort reflects a drag with no client renumber. No-op for
        non-scene siblings (arcs/chapters have NULL story_order). NOT version-
        bumped — story_order is a system-maintained ordinal, not a user field."""
        await c.execute(
            """
            WITH ordered AS (
              SELECT id, (row_number() OVER (ORDER BY rank COLLATE "C", id) - 1) AS so
              FROM outline_node
              WHERE user_id = $1 AND parent_id IS NOT DISTINCT FROM $2
                AND kind = 'scene' AND NOT is_archived
            )
            UPDATE outline_node n
            SET story_order = o.so, updated_at = now()
            FROM ordered o
            WHERE n.id = o.id AND n.user_id = $1 AND n.story_order IS DISTINCT FROM o.so
            """,
            user_id, parent_id,
        )

    async def reorder_node(
        self,
        user_id: UUID,
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
                node = await self.get_node(user_id, node_id, conn=c)
                if node is None:
                    return None
                if new_parent_id is not None:
                    # cycle / cross-scope guard (reused from update_node's reparent)
                    await self._validate_reparent(c, user_id, node_id, new_parent_id)

                # Siblings under the destination parent, excluding the moved node,
                # in canonical fractional-rank (byte) order.
                siblings = await c.fetch(
                    """
                    SELECT id, rank FROM outline_node
                    WHERE user_id = $1 AND parent_id IS NOT DISTINCT FROM $2
                      AND id <> $3 AND NOT is_archived
                    ORDER BY rank COLLATE "C", id
                    """,
                    user_id, new_parent_id, node_id,
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
                            "SELECT chapter_id FROM outline_node WHERE user_id = $1 AND id = $2",
                            user_id, new_parent_id,
                        )
                        if np is not None and np["chapter_id"] is not None:
                            patch["chapter_id"] = np["chapter_id"]

                # update_node owns the If-Match/version discipline + the reparent
                # revalidation; a 412 raises here → the Tx rolls back (no renumber).
                await self.update_node(
                    user_id, node_id, patch, expected_version=expected_version, conn=c,
                )

                await self._renumber_scene_story_order(c, user_id, new_parent_id)
                if node.parent_id != new_parent_id:
                    await self._renumber_scene_story_order(c, user_id, node.parent_id)

                return await self.get_node(user_id, node_id, conn=c)
