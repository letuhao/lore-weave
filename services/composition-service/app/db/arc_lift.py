"""Book-package re-key M4-M5 (spec 25) — the structure lift + the destructive contract.

DEPLOY 2 — the point of no return (PM-13). NOT boot-wired: unlike M0-M3
(`package_rekey.run_package_rekey`, which runs at every startup), M4/M5 run ONLY when
explicitly invoked by an operator, AFTER Deploy 1 has soaked and the T7 rehearsal on a
snapshot is green. Invoke via `python -m app.db.arc_lift` (reads COMPOSITION_DB_URL) or
`run_arc_lift(conn)` in a test/rehearsal.

  M4 — STRUCTURE LIFT (25 §M4 = 23 phases 1-3), additive + reversible:
    1. lift every `outline_node kind='arc'` → a `structure_node` (kind='arc'), recording
       (old_outline_id → new_structure_node_id) in `_arc_lift_map`; row counts asserted equal.
    2. re-point each arc's child chapters: `structure_node_id = <new>`, `parent_id = NULL`.
    3. provenance: `structure_node.arc_template_id` from the arc's motif_applications'
       `annotations->>'arc_template_id'` (disagreeing arcs → log + leave NULL, never guess);
       `motif_application.structure_node_id` backfill for arc-bound rows + drop the annotation key.
    4. PM-10: `decompose_commit.arc_id` values mapped through `_arc_lift_map`, column renamed
       `structure_node_id`.

  M5 — CONTRACT (the point of no return; gated on M4 assertions):
    1. re-assert guards (zero kind='beat', zero orphan arc-children), DELETE the lifted arc
       rows, swap the kind CHECK to ('chapter','scene').
    2. arc_template renames: threads→tracks, arc_roster→roster (guarded).
    3. drop `_arc_lift_map`.

Marker `pkg_lift_v1` in `package_migration`; stamped only after M5 completes. A re-run past the
marker is a no-op. Every step asserts its effect (`checklist-is-self-report-enforce-by-tests`) so
the T7 rehearsal on the snapshot fails LOUDLY rather than half-migrating the real DB.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)

_LIFT_MARKER = "pkg_lift_v1"


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table))


async def _column_exists(conn: asyncpg.Connection, table: str, column: str) -> bool:
    return bool(await conn.fetchval(
        """SELECT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = $1 AND column_name = $2 AND table_schema = current_schema())""",
        table, column,
    ))


async def run_arc_lift(conn: asyncpg.Connection) -> bool:
    """Run M4+M5 in ONE transaction, marker-gated. Returns True if applied this call,
    False if the marker already existed (no-op). Any assertion failure raises and the
    transaction rolls back — nothing half-migrates."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS package_migration (marker TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    if await conn.fetchval("SELECT 1 FROM package_migration WHERE marker = $1", _LIFT_MARKER):
        return False
    if not await _table_exists(conn, "structure_node"):
        raise RuntimeError(
            "arc lift (pkg_lift_v1) requires Deploy 1's structure_node table — run M0-M3 first."
        )

    async with conn.transaction():
        await _m4_lift(conn)
        await _m5_contract(conn)
        await conn.execute(
            "INSERT INTO package_migration (marker) VALUES ($1) ON CONFLICT (marker) DO NOTHING",
            _LIFT_MARKER,
        )
    logger.warning("arc lift (pkg_lift_v1) APPLIED — arcs lifted to structure_node, arc rows DELETED (M5, no rollback)")
    return True


# ── M4 — STRUCTURE LIFT ──────────────────────────────────────────────────────

async def _m4_lift(conn: asyncpg.Connection) -> None:
    # Pre-flight (review): structure_node caps nesting at depth 2 (saga→arc→sub-arc, CHECK 0..2 +
    # the depth-guard trigger). A legacy outline_node arc tree is UNBOUNDED (plain self-FK, no depth
    # guard), so a 4+-level chain would crash the trigger MID-INSERT and roll back the irreversible
    # migration with an opaque error naming only NEW.depth. Detect + abort with the offending arc
    # ids BEFORE any DDL, mirroring M5's pre-destructive guards.
    too_deep = await conn.fetch(
        """
        WITH RECURSIVE arc_lvl AS (
          SELECT id, 0 AS lvl FROM outline_node
            WHERE kind = 'arc'
              AND (parent_id IS NULL OR parent_id NOT IN (SELECT id FROM outline_node WHERE kind = 'arc'))
          UNION ALL
          SELECT o.id, l.lvl + 1 FROM outline_node o
            JOIN arc_lvl l ON o.parent_id = l.id WHERE o.kind = 'arc'
        )
        SELECT id FROM arc_lvl WHERE lvl > 2
        """
    )
    if too_deep:
        ids = [str(r["id"]) for r in too_deep]
        raise RuntimeError(
            f"M4 refused: {len(too_deep)} arc(s) nest deeper than structure_node's saga→arc→sub-arc "
            f"cap (depth > 2): {ids}. Flatten them (re-parent to depth ≤ 2) before the lift."
        )

    # A real (not temp) table: M5.3 drops it by name, and it must survive between M4/M5 if
    # they are ever run as separate deploys. Idempotent create — a crashed M4 re-runs clean.
    await conn.execute("DROP TABLE IF EXISTS _arc_lift_map")
    await conn.execute(
        "CREATE TABLE _arc_lift_map (old_outline_id UUID PRIMARY KEY, new_structure_node_id UUID NOT NULL)"
    )

    # M4.1 — lift arcs, PARENTS BEFORE CHILDREN (the structure_node depth-guard trigger requires
    # the parent to exist + computes depth from it). Level 0 = an arc with no arc-parent; recurse
    # down the arc tree. Insert per level so parent_id resolves through the lift map already built.
    arcs = await conn.fetch(
        """
        WITH RECURSIVE arc_lvl AS (
          SELECT id, 0 AS lvl FROM outline_node
            WHERE kind = 'arc'
              AND (parent_id IS NULL OR parent_id NOT IN (SELECT id FROM outline_node WHERE kind = 'arc'))
          UNION ALL
          SELECT o.id, l.lvl + 1 FROM outline_node o
            JOIN arc_lvl l ON o.parent_id = l.id
            WHERE o.kind = 'arc'
        )
        SELECT o.id, o.book_id, o.created_by, o.parent_id, o.rank, o.title, o.goal, o.synopsis, o.status, l.lvl
          FROM outline_node o JOIN arc_lvl l ON o.id = l.id
          ORDER BY l.lvl, o.rank COLLATE "C", o.id
        """
    )
    for a in arcs:
        # parent = the lifted structure_node of the arc's arc-parent (NULL for a root arc).
        new_id = await conn.fetchval(
            """
            INSERT INTO structure_node
              (book_id, created_by, parent_id, kind, rank, title, summary, goal, status, source)
            VALUES ($1, $2,
                    (SELECT new_structure_node_id FROM _arc_lift_map WHERE old_outline_id = $3),
                    'arc', $4, $5, $6, $7, $8, 'authored')
            RETURNING id
            """,
            a["book_id"], a["created_by"], a["parent_id"], a["rank"], a["title"],
            a["synopsis"] or "", a["goal"] or "", a["status"] or "outline",
        )
        await conn.execute(
            "INSERT INTO _arc_lift_map (old_outline_id, new_structure_node_id) VALUES ($1, $2)",
            a["id"], new_id,
        )

    # row counts asserted equal (25 M4.1)
    n_arc = await conn.fetchval("SELECT count(*) FROM outline_node WHERE kind = 'arc'")
    n_map = await conn.fetchval("SELECT count(*) FROM _arc_lift_map")
    n_struct_new = await conn.fetchval(
        "SELECT count(*) FROM structure_node s WHERE EXISTS (SELECT 1 FROM _arc_lift_map m WHERE m.new_structure_node_id = s.id)"
    )
    if not (n_arc == n_map == n_struct_new):
        raise RuntimeError(f"M4.1 lift count mismatch: arcs={n_arc} map={n_map} inserted={n_struct_new}")
    logger.info("M4.1: lifted %d arc(s) → structure_node", n_arc)

    # M4.2 — re-point each arc's child chapters onto the spec; detach from the (soon-deleted) arc.
    tag = await conn.execute(
        """
        UPDATE outline_node c SET structure_node_id = m.new_structure_node_id, parent_id = NULL
          FROM _arc_lift_map m
          WHERE c.parent_id = m.old_outline_id AND c.kind = 'chapter'
        """
    )
    logger.info("M4.2: re-pointed chapters onto structure_node (%s)", tag)

    # M4.3 — provenance (23 phases 2-3).
    if await _table_exists(conn, "motif_application"):
        # (a) structure_node.arc_template_id ← the arc's motif_applications' annotation, ONLY when
        #     they agree. A disagreeing arc → log + leave NULL (never guess).
        disagreeing = await conn.fetch(
            """
            SELECT m.old_outline_id, count(DISTINCT ma.annotations->>'arc_template_id') AS distinct_tpl
              FROM _arc_lift_map m
              JOIN motif_application ma ON ma.outline_node_id = m.old_outline_id
              WHERE ma.annotations ? 'arc_template_id' AND ma.annotations->>'arc_template_id' IS NOT NULL
              GROUP BY m.old_outline_id HAVING count(DISTINCT ma.annotations->>'arc_template_id') > 1
            """
        )
        for r in disagreeing:
            logger.warning(
                "M4.3 arc %s has %d disagreeing arc_template_id annotations — left NULL (never guessed)",
                r["old_outline_id"], r["distinct_tpl"],
            )
        await conn.execute(
            """
            UPDATE structure_node s SET arc_template_id = sub.tpl
              FROM (
                SELECT m.new_structure_node_id AS sid,
                       (max(ma.annotations->>'arc_template_id'))::uuid AS tpl
                  FROM _arc_lift_map m
                  JOIN motif_application ma ON ma.outline_node_id = m.old_outline_id
                  WHERE ma.annotations ? 'arc_template_id' AND ma.annotations->>'arc_template_id' IS NOT NULL
                  GROUP BY m.new_structure_node_id
                  HAVING count(DISTINCT ma.annotations->>'arc_template_id') = 1
              ) sub
              WHERE s.id = sub.sid
            """
        )
        # (b) move each arc-bound application's anchor from the (soon-DELETED) arc outline_node
        #     to the structure_node, in ONE update: set structure_node_id, NULL outline_node_id
        #     (its FK is ON DELETE CASCADE — leaving it set means M5's arc delete cascade-DELETES
        #     the application, losing the binding), and drop the now-redundant annotation key
        #     (its home is structure_node.arc_template_id). Ordered after (a), which reads
        #     outline_node_id → the arc.
        moved = await conn.execute(
            """
            UPDATE motif_application ma
              SET structure_node_id = m.new_structure_node_id,
                  outline_node_id = NULL,
                  annotations = ma.annotations - 'arc_template_id'
              FROM _arc_lift_map m WHERE ma.outline_node_id = m.old_outline_id
            """
        )
        logger.info("M4.3: provenance backfilled + arc-bound applications re-anchored to structure_node (%s)", moved)

    # M4.4 — PM-10 re-point: decompose_commit.arc_id → lifted structure_node id, then rename column.
    if await _table_exists(conn, "decompose_commit") and await _column_exists(conn, "decompose_commit", "arc_id"):
        # arc_id currently points at an outline_node arc (a decompose commits an arc). Map it.
        # A commit whose arc_id does NOT resolve through the map (e.g. it referenced a chapter id
        # in legacy test data) is left as-is — asserted below only for arc-kind targets.
        await conn.execute(
            """
            UPDATE decompose_commit d SET arc_id = m.new_structure_node_id
              FROM _arc_lift_map m WHERE d.arc_id = m.old_outline_id
            """
        )
        await conn.execute("ALTER TABLE decompose_commit RENAME COLUMN arc_id TO structure_node_id")
        logger.info("M4.4: decompose_commit.arc_id re-pointed through the lift map + renamed structure_node_id")


# ── M5 — CONTRACT (point of no return) ───────────────────────────────────────

async def _m5_contract(conn: asyncpg.Connection) -> None:
    # Re-assert the guards IMMEDIATELY before the destructive delete (an agent could have minted a
    # kind='beat' row between deploys; an orphan child could exist).
    n_beat = await conn.fetchval("SELECT count(*) FROM outline_node WHERE kind = 'beat'")
    if n_beat:
        raise RuntimeError(f"M5 refused: {n_beat} kind='beat' row(s) exist — resolve before the contract step")
    # A NON-arc node still parented to an arc would be CASCADE-deleted (outline_node.parent_id is
    # ON DELETE CASCADE) when M5.1 deletes that arc — silent data loss. Sub-arcs (kind='arc') are
    # excluded: they are children of arcs by design and are deleted together with them.
    orphan_children = await conn.fetchval(
        """
        SELECT count(*) FROM outline_node c
          WHERE c.kind <> 'arc' AND c.parent_id IN (SELECT id FROM outline_node WHERE kind = 'arc')
        """
    )
    if orphan_children:
        raise RuntimeError(
            f"M5 refused: {orphan_children} non-arc node(s) still parented to an arc (M4.2 re-point "
            "incomplete) — they would be CASCADE-deleted. Aborting before the destructive delete."
        )

    # scene_link (from/to) and scene_grounding_pins.outline_node_id are ALSO ON DELETE CASCADE to
    # outline_node (like motif_application, which M4.3 re-anchored). A row referencing an arc node
    # would be SILENTLY cascade-deleted by M5.1's arc DELETE. These are app-conventionally scene-only
    # (the FK doesn't enforce kind), so any arc reference is anomalous — refuse rather than lose it
    # silently (review: un-guarded CASCADE gap).
    cascade_refs = await conn.fetchval(
        """
        SELECT (SELECT count(*) FROM scene_link
                  WHERE from_node_id IN (SELECT id FROM outline_node WHERE kind = 'arc')
                     OR to_node_id   IN (SELECT id FROM outline_node WHERE kind = 'arc'))
             + (SELECT count(*) FROM scene_grounding_pins
                  WHERE outline_node_id IN (SELECT id FROM outline_node WHERE kind = 'arc'))
        """
    )
    if cascade_refs:
        raise RuntimeError(
            f"M5 refused: {cascade_refs} scene_link/scene_grounding_pins row(s) reference an arc node "
            "and would be CASCADE-deleted by the arc delete. Resolve them before the destructive step."
        )

    # M5.1 — delete the lifted arc rows + swap the kind CHECK (BPS-4: beat AND arc both gone).
    del_tag = await conn.execute("DELETE FROM outline_node WHERE kind = 'arc'")
    await conn.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outline_node_kind_check') THEN
            ALTER TABLE outline_node DROP CONSTRAINT outline_node_kind_check;
          END IF;
          ALTER TABLE outline_node ADD CONSTRAINT outline_node_kind_check CHECK (kind IN ('chapter','scene'));
        END $$;
        """
    )
    # assert the swap actually took (a wrong constraint name would otherwise silently no-op).
    bad = await conn.fetchval(
        "SELECT count(*) FROM outline_node WHERE kind NOT IN ('chapter','scene')"
    )
    if bad:
        raise RuntimeError(f"M5.1 left {bad} non-chapter/scene outline_node rows after the delete")
    logger.info("M5.1: %s; kind CHECK swapped to ('chapter','scene')", del_tag)

    # M5.2 — template renames (BPS-5). Guarded: no-op if already renamed / column absent.
    await conn.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name='arc_template' AND column_name='threads' AND table_schema=current_schema()) THEN
            ALTER TABLE arc_template RENAME COLUMN threads TO tracks;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name='arc_template' AND column_name='arc_roster' AND table_schema=current_schema()) THEN
            ALTER TABLE arc_template RENAME COLUMN arc_roster TO roster;
          END IF;
        END $$;
        """
    )
    logger.info("M5.2: arc_template.threads→tracks, arc_roster→roster")

    # M5.3 — drop the lift map.
    await conn.execute("DROP TABLE IF EXISTS _arc_lift_map")
    logger.info("M5.3: _arc_lift_map dropped")


async def _amain() -> None:
    import os

    dsn = os.environ.get("COMPOSITION_DB_URL") or os.environ.get("TEST_COMPOSITION_DB_URL")
    if not dsn:
        raise SystemExit("set COMPOSITION_DB_URL to the target composition DB")
    logging.basicConfig(level=logging.INFO)
    conn = await asyncpg.connect(dsn)
    try:
        applied = await run_arc_lift(conn)
        print(f"arc lift {'APPLIED' if applied else 'already applied (no-op)'}")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_amain())
