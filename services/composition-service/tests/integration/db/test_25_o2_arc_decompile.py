"""26 · O-2 (D3/IX-17) — the arc decompiler mints kind='arc' structure_node's from an imported
book's chapters. THE only path to an arc layer for a book with prose but no plan. Idempotent.
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.engine.arc_decompile import decompile_arcs

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "plan_run",
    "outbox_events", "generation_correction", "generation_job", "narrative_thread",
    "canon_rule", "scene_link", "outline_node", "structure_node", "structure_template",
    "entity_override", "divergence_spec", "composition_work",
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


async def _seed_chapters(pool, book, user, project, n):
    async with pool.acquire() as c:
        for i in range(n):
            await c.execute(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, story_order) "
                "VALUES ($1,$2,$3,'chapter',$4,$5)",
                user, project, book, f"m{i:03d}", (i + 1) * 1000,
            )


async def _arc_state(pool, book):
    async with pool.acquire() as c:
        arcs = await c.fetch(
            "SELECT id, source FROM structure_node WHERE book_id=$1 AND kind='arc' AND NOT is_archived",
            book,
        )
        assigned = await c.fetchval(
            "SELECT count(*) FROM outline_node WHERE book_id=$1 AND kind='chapter' "
            "AND structure_node_id IS NOT NULL AND NOT is_archived",
            book,
        )
    return arcs, int(assigned)


async def test_arc_decompiler_mints_decompiled_arcs_and_assigns_chapters(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_chapters(pool, book, user, project, 7)

    # no arc layer yet
    arcs0, _ = await _arc_state(pool, book)
    assert arcs0 == []

    res = await decompile_arcs(pool, book, created_by=user, chapters_per_arc=3)
    assert res["arcs"] == 3            # 7 chapters / 3 = ceil -> 3 arcs (3+3+1)
    assert res["chapters_assigned"] == 7

    arcs, assigned = await _arc_state(pool, book)
    assert len(arcs) == 3
    assert all(a["source"] == "decompiled" for a in arcs)   # provenance, not authored/compiled
    assert assigned == 7                                     # every chapter now hangs on an arc


async def test_arc_decompiler_is_idempotent_reruns_reuse_not_duplicate(pool):
    user, project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_chapters(pool, book, user, project, 7)

    r1 = await decompile_arcs(pool, book, created_by=user, chapters_per_arc=3)
    r2 = await decompile_arcs(pool, book, created_by=user, chapters_per_arc=3)
    assert r1["arc_ids"] == r2["arc_ids"]   # SAME arcs reused by position — no fork on re-run
    arcs, assigned = await _arc_state(pool, book)
    assert len(arcs) == 3 and assigned == 7


async def test_arc_decompiler_no_chapters_is_a_noop_not_an_error(pool):
    user, _project, book = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    res = await decompile_arcs(pool, book, created_by=user)
    assert res["arcs"] == 0 and res["chapters_assigned"] == 0
