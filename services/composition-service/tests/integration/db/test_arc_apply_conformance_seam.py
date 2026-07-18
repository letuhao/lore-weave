"""23-A5 → A4 seam: arc_apply's ledger rows must be visible to arc conformance.

This is the cross-agent seam two parallel builders left broken (Stage 2 integration):
  · A5 (arc_apply) originally folded `structure_node_id` into `motif_application.annotations`
    only, because `insert_many` hard-coded its column list.
  · A4 (conformance) reads the realized bindings via `WHERE a.structure_node_id = $arc`
    (the first-class column Deploy 1 added, BA4/BA5).
So apply wrote to `annotations` and conformance read the column — the ledger rows were
INVISIBLE to the very report they exist to feed. The fix made `structure_node_id` a
first-class write in `insert_many` (+ the model + `_SELECT_COLS`); arc_apply now sets it.

This test proves the seam BY EFFECT: apply a template onto an arc, then read the arc's
realized bindings through `arc_bindings_by_structure` and assert the rows come back keyed
on the column — the exact query the deep conformance job runs.

Gated on TEST_COMPOSITION_DB_URL (throwaway DB — drops tables).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.motif_application import MotifApplicationRepo
from app.routers.conformance import ConformanceTraceReader

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in ("motif_application", "outline_node", "structure_node",
                      "motif", "composition_work"):
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in ("motif_application", "outline_node", "structure_node",
                      "motif", "composition_work"):
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


async def test_insert_many_writes_structure_node_id_first_class(pool):
    """The minimal seam: a ledger row written with a `structure_node_id` field is
    readable through the column, not just annotations."""
    actor, book, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    arc_id = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, created_by, book_id) VALUES ($1,$2,$3)",
            project, actor, book,
        )
        await c.execute(
            "INSERT INTO structure_node (id, book_id, kind, rank, title) "
            "VALUES ($1,$2,'arc','a0','Betrayal')",
            arc_id, book,
        )
        motif_id = await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, name, kind) "
            "VALUES ($1,'betrayal','Betrayal','scheme') RETURNING id",
            actor,
        )
        chapter = uuid.uuid4()
        # The scene carries no structure_node_id (only chapter nodes may — the
        # outline_structure_kind CHECK). The arc link lives on the motif_application row.
        node_id = await c.fetchval(
            "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, "
            "chapter_id, tension, story_order) "
            "VALUES ($1,$2,$3,'scene','a0',$4,80,5) RETURNING id",
            actor, project, book, chapter,
        )

    rows = [{
        "motif_id": str(motif_id), "motif_version": 1,
        "outline_node_id": str(node_id),
        "structure_node_id": str(arc_id),          # ← the first-class field arc_apply now sets
        "role_bindings": {}, "annotations": {"structure_node_id": str(arc_id)},
    }]
    inserted = await MotifApplicationRepo(pool).insert_many(
        project, book, rows, created_by=actor,
    )
    assert len(inserted) == 1
    # the model surfaces the column now
    assert inserted[0].structure_node_id == arc_id

    # ...and the conformance reader finds it via the COLUMN (the exact deep-job query)
    reader = ConformanceTraceReader(pool)
    found = await reader.arc_bindings_by_structure(project, arc_id)
    assert len(found) == 1, "arc_apply's binding is invisible to conformance (A5↔A4 seam broken)"
    assert found[0]["motif_code"] == "betrayal"
    assert found[0]["chapter_id"] == chapter
    assert found[0]["tension"] == 80

    # a DIFFERENT arc must not capture it (the column is the discriminator, not annotations)
    other = await reader.arc_bindings_by_structure(project, uuid.uuid4())
    assert other == []
