"""25-T7 — the M4/M5 arc lift + contract (Deploy 2), rehearsed on a throwaway migrated DB.

Spec: docs/specs/2026-07-01-writing-studio/25_package_migration_master.md §M4/M5/T7.

The rehearsal gate (PM-13): "On the T1 snapshot: run M4, assert lift-map completeness … then M5,
assert zero orphans + CHECK swap + renames. Only after this rehearsal is M5 allowed on the real DB."
This builds a migrated (post-M3) throwaway DB — the shape M4 lifts FROM — seeds an arc tree with the
cascade-prone neighbours (a motif_application bound to the arc via an ON DELETE CASCADE FK; chapters
that MUST be detached before the arc delete), runs the lift, and asserts the whole effect.

Gated on TEST_COMPOSITION_DB_URL (a throwaway DB — the fixture drops every table; hard-guarded to
refuse any DSN whose name lacks "test", per kg-integration-tests-truncate-shared-dev-db).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.arc_lift import _LIFT_MARKER, run_arc_lift
from app.db.migrate import run_migrations

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_DROP_ALL_TABLES = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
END $$;
"""


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db.lower():
        raise RuntimeError(f"REFUSING: TEST_COMPOSITION_DB_URL={db!r} is not a throwaway DB (drops every table)")


@pytest.fixture
async def migrated_pool():
    """A throwaway DB in the FINAL post-M3 shape (structure_node empty, kind='arc' still allowed) —
    exactly what M4 lifts from. A fresh run_migrations bootstraps straight into that shape."""
    _guard_throwaway(_DSN)
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            await c.execute(_DROP_ALL_TABLES)
        await run_migrations(p)  # fresh → final post-M3 shape, marker stamped
        yield p
    finally:
        async with p.acquire() as c:
            await c.execute(_DROP_ALL_TABLES)
        await p.close()


async def _to_legacy_shape(c: asyncpg.Connection) -> None:
    """Put the fresh (final-shape) DB back into the PRE-Deploy-2 shape, so the seed + lift exercise
    the REAL legacy→lifted transition (the column renames + the arc_id re-point). Mirrors
    test_package_rekey's revert trick — the base CREATE carries the FINAL column names now, so a
    fresh DB has tracks/roster/structure_node_id; rename them back to threads/arc_roster/arc_id."""
    await c.execute("ALTER TABLE arc_template RENAME COLUMN tracks TO threads")
    await c.execute("ALTER TABLE arc_template RENAME COLUMN roster TO arc_roster")
    await c.execute("ALTER TABLE decompose_commit RENAME COLUMN structure_node_id TO arc_id")


async def _seed_arc_tree(c: asyncpg.Connection) -> dict:
    """A book with a Work; a top arc holding a sub-arc; a chapter under EACH arc; a scene under the
    top chapter; a motif_application bound to the top arc (annotation = arc_template_id, the CASCADE
    neighbour); a decompose_commit on the top arc; an arc_template with threads/arc_roster."""
    await _to_legacy_shape(c)
    actor, book, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await c.execute(
        "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
        project, actor, book,
    )
    tpl = await c.fetchval(
        "INSERT INTO arc_template (owner_user_id, code, name, threads, arc_roster) "
        "VALUES ($1,'tpl-1','Rise', '[{\"key\":\"a\"}]'::jsonb, '[{\"key\":\"hero\"}]'::jsonb) RETURNING id",
        actor,
    )
    top = await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, title, goal, synopsis, status) "
        "VALUES ($1,$2,$3,'arc','a0','Ascension','win','the climb','drafting') RETURNING id",
        actor, project, book,
    )
    sub = await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, title) "
        "VALUES ($1,$2,$3,$4,'arc','a0','Betrayal') RETURNING id",
        actor, project, book, top,
    )
    ch_top = await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, chapter_id) "
        "VALUES ($1,$2,$3,$4,'chapter','a0',$5) RETURNING id",
        actor, project, book, top, uuid.uuid4(),
    )
    ch_sub = await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, chapter_id) "
        "VALUES ($1,$2,$3,$4,'chapter','a1',$5) RETURNING id",
        actor, project, book, sub, uuid.uuid4(),
    )
    scene = await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, chapter_id, story_order) "
        "VALUES ($1,$2,$3,$4,'scene','a0',$5,1) RETURNING id",
        actor, project, book, ch_top, await c.fetchval("SELECT chapter_id FROM outline_node WHERE id=$1", ch_top),
    )
    # motif_application bound to the TOP arc — the ON DELETE CASCADE neighbour that must survive M5.
    ma = await c.fetchval(
        "INSERT INTO motif_application (created_by, project_id, book_id, outline_node_id, annotations) "
        "VALUES ($1,$2,$3,$4, jsonb_build_object('arc_template_id', $5::text)) RETURNING id",
        actor, project, book, top, str(tpl),
    )
    await c.execute(
        "INSERT INTO decompose_commit (created_by, project_id, book_id, idempotency_key, arc_id, result) "
        "VALUES ($1,$2,$3,'k1',$4,'{}'::jsonb)",
        actor, project, book, top,
    )
    return {"actor": actor, "book": book, "project": project, "tpl": tpl, "top": top, "sub": sub,
            "ch_top": ch_top, "ch_sub": ch_sub, "scene": scene, "ma": ma}


async def test_t7_lift_and_contract(migrated_pool):
    async with migrated_pool.acquire() as c:
        s = await _seed_arc_tree(c)
        applied = await run_arc_lift(c)
        assert applied is True

        # (1) both arcs lifted to structure_node; arc outline_node rows are GONE (M5.1).
        assert await c.fetchval("SELECT count(*) FROM structure_node WHERE book_id=$1", s["book"]) == 2
        assert await c.fetchval("SELECT count(*) FROM outline_node WHERE kind='arc'") == 0

        # (2) nesting preserved: the sub-arc's structure_node parents the top's, depth 0 → 1.
        top_sn = await c.fetchrow(
            "SELECT id, parent_id, depth, kind, title, goal, summary, status, arc_template_id "
            "FROM structure_node WHERE title='Ascension'"
        )
        sub_sn = await c.fetchrow("SELECT parent_id, depth FROM structure_node WHERE title='Betrayal'")
        assert top_sn["parent_id"] is None and top_sn["depth"] == 0 and top_sn["kind"] == "arc"
        assert sub_sn["parent_id"] == top_sn["id"] and sub_sn["depth"] == 1
        # field mapping: goal/summary(from synopsis)/status carried across.
        assert top_sn["goal"] == "win" and top_sn["summary"] == "the climb" and top_sn["status"] == "drafting"
        # provenance: the consistent annotation became structure_node.arc_template_id.
        assert top_sn["arc_template_id"] == s["tpl"]

        # (3) chapters re-pointed onto the spec, detached from the (deleted) arc; scene untouched.
        for ch, sn in ((s["ch_top"], top_sn["id"]), (s["ch_sub"], sub_sn["parent_id"])):
            row = await c.fetchrow("SELECT parent_id, structure_node_id FROM outline_node WHERE id=$1", ch)
            assert row["parent_id"] is None, "chapter must be detached from the arc before the delete"
            assert row["structure_node_id"] is not None, "chapter must attach to structure_node"
        assert await c.fetchval("SELECT parent_id FROM outline_node WHERE id=$1", s["scene"]) == s["ch_top"]
        assert await c.fetchval("SELECT count(*) FROM outline_node WHERE id=$1", s["scene"]) == 1  # scene survived

        # (4) the CASCADE neighbour SURVIVED: the arc-bound motif_application was re-anchored to the
        #     structure_node (outline_node_id NULL'd) and its annotation key dropped — not deleted.
        ma = await c.fetchrow(
            "SELECT outline_node_id, structure_node_id, annotations FROM motif_application WHERE id=$1", s["ma"]
        )
        assert ma is not None, "the arc-bound motif_application was CASCADE-deleted (binding lost)"
        assert ma["outline_node_id"] is None and ma["structure_node_id"] == top_sn["id"]
        assert "arc_template_id" not in ma["annotations"]

        # (5) PM-10: decompose_commit.arc_id renamed → structure_node_id, value mapped through the lift.
        assert not await c.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='decompose_commit' AND column_name='arc_id')"
        )
        assert await c.fetchval("SELECT structure_node_id FROM decompose_commit WHERE idempotency_key='k1'") == top_sn["id"]

        # (6) the kind CHECK was swapped — a fresh kind='arc' insert is now rejected.
        with pytest.raises(asyncpg.CheckViolationError):
            await c.execute(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank) VALUES ($1,$2,$3,'arc','z0')",
                s["actor"], s["project"], s["book"],
            )

        # (7) BPS-5 template renames landed; the lift map was dropped.
        cols = {r["column_name"] for r in await c.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='arc_template'"
        )}
        assert "tracks" in cols and "roster" in cols and "threads" not in cols and "arc_roster" not in cols
        assert await c.fetchval("SELECT to_regclass('_arc_lift_map')") is None


async def test_t7_deep_arc_nesting_is_refused_before_any_ddl(migrated_pool):
    # review: structure_node caps depth at 2; a 4-level legacy arc chain would crash the depth-guard
    # trigger MID-INSERT and roll back the irreversible migration with an opaque error. The M4
    # pre-flight must refuse it up front, listing the offending arcs, before any DDL.
    async with migrated_pool.acquire() as c:
        await _to_legacy_shape(c)
        actor, book, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await c.execute("INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)", project, actor, book)
        parent = None
        for i in range(4):  # depths 0,1,2,3 — one deeper than the cap
            parent = await c.fetchval(
                "INSERT INTO outline_node (created_by, project_id, book_id, parent_id, kind, rank, title) "
                "VALUES ($1,$2,$3,$4,'arc',$5,$6) RETURNING id",
                actor, project, book, parent, f"a{i}", f"L{i}",
            )
        with pytest.raises(RuntimeError, match=r"nest deeper"):
            await run_arc_lift(c)
        # refused BEFORE any DDL: no lift map, no structure_node rows, marker unset, arcs intact.
        assert await c.fetchval("SELECT to_regclass('_arc_lift_map')") is None
        assert await c.fetchval("SELECT count(*) FROM structure_node") == 0
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker=$1", _LIFT_MARKER) == 0
        assert await c.fetchval("SELECT count(*) FROM outline_node WHERE kind='arc'") == 4


async def test_t7_arc_referencing_scene_link_is_refused(migrated_pool):
    # review: scene_link.from/to_node_id is ON DELETE CASCADE — a link referencing an arc would be
    # silently deleted by M5's arc DELETE. The M5 guard must refuse it (rolling back the whole lift).
    async with migrated_pool.acquire() as c:
        s = await _seed_arc_tree(c)
        await c.execute(
            "INSERT INTO scene_link (created_by, project_id, book_id, from_node_id, to_node_id) "
            "VALUES ($1,$2,$3,$4,$5)",
            s["actor"], s["project"], s["book"], s["top"], s["scene"],  # from the ARC (anomalous)
        )
        with pytest.raises(RuntimeError, match=r"scene_link/scene_grounding_pins"):
            await run_arc_lift(c)
        # the whole transaction rolled back — arcs NOT lifted, marker unset.
        assert await c.fetchval("SELECT count(*) FROM structure_node") == 0
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker=$1", _LIFT_MARKER) == 0


async def test_t7_second_run_is_a_noop(migrated_pool):
    async with migrated_pool.acquire() as c:
        await _seed_arc_tree(c)
        assert await run_arc_lift(c) is True
        struct = await c.fetchval("SELECT count(*) FROM structure_node")
        assert await run_arc_lift(c) is False  # marker present → no-op
        assert await c.fetchval("SELECT count(*) FROM structure_node") == struct
        assert await c.fetchval("SELECT count(*) FROM package_migration WHERE marker=$1", _LIFT_MARKER) == 1
