"""C-merge — manuscript 'part' structure_node write/read, against a real Postgres (throwaway test DB).

After the C4 retire, parts live ONLY in composition as structure_node kind='part' (the book-service
parts table + the C2 mirror bridge are gone). This covers the surviving SSOT path: create_part (integer
rank), reorder_parts, archive/restore, and the kind separation that keeps parts off the Plan rail.
Gated on TEST_COMPOSITION_DB_URL (the fixture drops + rebuilds the schema).
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.structure import StructureConflictError, StructureRepo

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


async def test_create_part_integer_rank_reorder_archive_restore(pool):
    """create_part appends at integer rank max+1 (C3-decodable); reorder_parts rewrites by position;
    archive excludes from the active read; restore brings it back."""
    repo = StructureRepo(pool)
    book, actor = uuid.uuid4(), uuid.uuid4()

    a = await repo.create_part(book, created_by=actor, title="One")
    b = await repo.create_part(book, created_by=actor, title="Two")
    assert (int(a.rank), int(b.rank)) == (1, 2) and a.kind == "part" and a.depth == 0

    reordered = await repo.reorder_parts(book, [b.id, a.id])
    assert [n.id for n in reordered] == [b.id, a.id]
    assert [int(n.rank) for n in reordered] == [1, 2]

    with pytest.raises(StructureConflictError):
        await repo.reorder_parts(book, [a.id])  # not the exact active set

    await repo.archive(a.id)
    assert [n.id for n in await repo.list_tree(book, kinds=("part",))] == [b.id]
    await repo.restore(a.id)
    assert {n.id for n in await repo.list_tree(book, kinds=("part",))} == {a.id, b.id}


async def test_parts_and_arcs_do_not_pollute_each_other(pool):
    """list_tree defaults to ('saga','arc') so a 'part' never shows on the Plan rail, and
    kinds=('part',) returns ONLY parts — the Manuscript-rail read surface."""
    repo = StructureRepo(pool)
    book, actor = uuid.uuid4(), uuid.uuid4()
    part = await repo.create_part(book, created_by=actor, title="Part One")
    saga = await repo.create_node(book, created_by=actor, kind="saga", title="The Saga")

    assert [n.id for n in await repo.list_tree(book)] == [saga.id]                 # Plan rail: arcs only
    part_tree = await repo.list_tree(book, kinds=("part",))                        # Manuscript rail: parts only
    assert [n.id for n in part_tree] == [part.id]
    assert part_tree[0].title == "Part One"
