"""outline_node repository — the Arc→Chapter→Scene→Beat tree (§1.2/§5).

SECURITY RULE (M5 isolation): every method takes `user_id` first and filters
`user_id = $1`. Sibling order is a fractional `rank` (see rank.py) so an insert
touches one row. DELETE is a RECURSIVE soft-archive (PO decision): archiving a
node also archives its descendants, so no orphaned-visible child survives under
an archived parent. Hard FK CASCADE is reserved for scene_link edges only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import OutlineNode
from app.db.repositories import ReferenceViolationError, VersionMismatchError, outbox
from app.db.repositories.rank import rank_after

_SELECT_COLS = """
  id, user_id, project_id, parent_id, kind, rank, title, pov_entity_id,
  present_entity_ids, goal, beat_role, status, chapter_id, tension,
  story_order, synopsis, version, is_archived, created_at, updated_at
"""

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
        total, done = int(row["total"]), int(row["done"])
        return {
            "chapter_id": str(chapter_id),
            "scenes_total": total,
            "scenes_done": done,
            "can_publish": total > 0 and done == total,
        }

    async def archive_node(self, user_id: UUID, node_id: UUID) -> OutlineNode | None:
        """Soft-archive a node AND its descendants (PO decision — no orphaned-
        visible children). A recursive CTE walks parent_id down from the target,
        then one UPDATE flips is_archived on the whole subtree. Returns the
        target node (archived) or None if it doesn't exist / isn't ours / was
        already archived. Scoped by user_id at the CTE root, so the subtree can
        only contain the caller's nodes.

        UNION (not UNION ALL): a malformed parent_id CYCLE (reachable today —
        update_node permits reparenting with no cycle guard) would make UNION ALL
        recurse forever (and hang past the pool command_timeout). UNION dedups,
        so the walk terminates at the cycle. (Reparent cycle PREVENTION is a
        router-layer validation, tracked as D-COMP-M2-XREF-OWNERSHIP.)"""
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
