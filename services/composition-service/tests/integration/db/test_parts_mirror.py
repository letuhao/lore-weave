"""C-merge C2 — reconcile_book_parts against a real Postgres (throwaway test DB).

Proves the manuscript-parts → structure_node mirror: upsert kind='part' by id (== part.id, depth 0),
rename updates in place, and a part removed from book-service is archived (not left claiming a grouping
the author deleted). Gated on TEST_COMPOSITION_DB_URL (the fixture drops + rebuilds the schema).
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.services.parts_mirror_service import reconcile_book_parts

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "structure_node", "motif_application", "motif_link", "motif", "arc_template",
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "composition_daily_progress", "composition_progress_baseline",
    "style_profile", "voice_profile", "scene_grounding_pins", "reference_source",
    "decompose_commit", "outbox_events", "generation_correction", "generation_job",
    "narrative_thread", "canon_rule", "scene_link", "outline_node",
    "structure_template", "entity_override", "divergence_spec", "composition_work",
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


def _part(pid, title, sort_order):
    return {"id": str(pid), "title": title, "sort_order": sort_order}


async def _parts(pool, book):
    return await pool.fetch(
        "SELECT id, title, rank, depth, is_archived FROM structure_node "
        "WHERE book_id=$1 AND kind='part' ORDER BY rank",
        book,
    )


async def test_reconcile_upserts_by_part_id_at_depth0(pool):
    book = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    res = await reconcile_book_parts(pool, book, [_part(p1, "Part One", 1), _part(p2, "Part Two", 2)])
    assert res == {"upserted": 2, "archived": 0}
    rows = await _parts(pool, book)
    # structure_node.id == part.id, kind='part', depth 0, ordered by sort_order-derived rank.
    assert [r["id"] for r in rows] == [p1, p2]
    assert all(r["depth"] == 0 and not r["is_archived"] for r in rows)
    assert [r["title"] for r in rows] == ["Part One", "Part Two"]


async def test_reconcile_renames_in_place_and_reorders(pool):
    book = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    await reconcile_book_parts(pool, book, [_part(p1, "One", 1), _part(p2, "Two", 2)])
    # rename p1 + swap order (p2 now sort_order 1)
    await reconcile_book_parts(pool, book, [_part(p1, "Act One", 2), _part(p2, "Act Two", 1)])
    rows = await _parts(pool, book)
    assert [r["id"] for r in rows] == [p2, p1]  # reordered by new sort_order
    titles = {r["id"]: r["title"] for r in rows}
    assert titles[p1] == "Act One" and titles[p2] == "Act Two"
    assert len(rows) == 2  # no duplicates — upsert by id


async def test_reconcile_archives_removed_parts(pool):
    book = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    await reconcile_book_parts(pool, book, [_part(p1, "One", 1), _part(p2, "Two", 2)])
    # p2 removed from book-service (trashed) → reconcile archives its mirror, keeps p1 active.
    res = await reconcile_book_parts(pool, book, [_part(p1, "One", 1)])
    assert res == {"upserted": 1, "archived": 1}
    rows = {r["id"]: r["is_archived"] for r in await _parts(pool, book)}
    assert rows[p1] is False and rows[p2] is True


async def test_reconcile_reactivates_a_restored_part(pool):
    book = uuid.uuid4()
    p1 = uuid.uuid4()
    await reconcile_book_parts(pool, book, [_part(p1, "One", 1)])
    await reconcile_book_parts(pool, book, [])          # trashed → archived
    await reconcile_book_parts(pool, book, [_part(p1, "One", 1)])  # restored → un-archived
    rows = await _parts(pool, book)
    assert len(rows) == 1 and rows[0]["is_archived"] is False


async def test_parts_and_arcs_do_not_pollute_each_other(pool):
    """C3 pollution fix: list_tree defaults to ('saga','arc') so a mirrored 'part' never shows on the
    Plan rail, and kinds=('part',) returns ONLY parts — the read-cutover source for the Manuscript rail."""
    from app.db.repositories.structure import StructureRepo

    book = uuid.uuid4()
    p1 = uuid.uuid4()
    await reconcile_book_parts(pool, book, [_part(p1, "Part One", 1)])
    repo = StructureRepo(pool)
    saga = await repo.create_node(book, created_by=uuid.uuid4(), kind="saga", title="The Saga")

    # Plan-rail read (default kinds) sees ONLY the saga/arc — never the 'part'.
    arc_tree = await repo.list_tree(book)
    assert [n.id for n in arc_tree] == [saga.id]
    # Manuscript-rail read (kinds=('part',)) sees ONLY the part.
    part_tree = await repo.list_tree(book, kinds=("part",))
    assert [n.id for n in part_tree] == [p1]
    assert part_tree[0].title == "Part One"
