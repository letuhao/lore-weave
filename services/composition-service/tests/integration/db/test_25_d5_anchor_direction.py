"""22 · D5 — anchor DIRECTION (the index points at the spec, never the reverse).

DA-3 / IX-13: the AUTHORED anchor is `scenes.source_scene_id → outline_node.id` (the disposable
index points at the durable spec). `outline_node.written_scene_id` is a REGENERABLE CACHE of that
pointer's inverse — nullable, reconciled, never a hard FK. So deleting a scene / clearing prose
leaves the spec node INTACT (proven by test_written_verdict.py:
`test_reconcile_clears_written_link_when_prose_is_gone` — the author deletes the prose; the spec
node survives).

THIS test is the structural GUARD D5 asks for: it REDs if someone re-adds a REVERSE hard anchor
(`outline_node.scene_id` / `outline_node.source_scene_id`) — which would make the spec a slave of
the disposable index and let a scene delete cascade the spec away.
"""
from __future__ import annotations

import os

import asyncpg
import pytest

from app.db.migrate import run_migrations

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


async def test_outline_node_has_no_reverse_scene_anchor(pool):
    async with pool.acquire() as c:
        cols = {
            r["column_name"]
            for r in await c.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name='outline_node'"
            )
        }
    # The ONLY scene link on the spec side is the disposable, nullable cache.
    assert "written_scene_id" in cols
    # A REVERSE hard anchor must never exist — the index points at the spec, not the other way.
    assert "scene_id" not in cols, "outline_node.scene_id is a reverse anchor — D5 forbids it"
    assert "source_scene_id" not in cols, (
        "source_scene_id belongs on the SCENE (index) side, never on outline_node (the spec)"
    )

    # And the cache is nullable — a scene delete/reconcile nulls it; it never NOT-NULL-forces the
    # spec to depend on an index row.
    async with pool.acquire() as c:
        nn = await c.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='outline_node' AND column_name='written_scene_id'"
        )
    assert nn == "YES", "written_scene_id must stay nullable — the spec outlives its cache"
