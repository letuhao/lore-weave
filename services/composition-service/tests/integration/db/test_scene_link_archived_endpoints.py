"""F3 — a scene link is only LIVE while both its endpoints are (real SQL, throwaway DB).

`archive_node` cascades over the outline subtree and deliberately does not touch `scene_link`, so
archiving a scene left its causal edges behind: still returned by both reads, pointing at a node the
tree no longer shows. The FE resolves a missing title to a short id, so the author saw an edge to
`deadbeef…` — a dangling edge with no way to reason about it.

Two ways to fix that, and the choice matters:

  · CASCADE the archive onto the edges — then restoring the scene has to know WHICH edges it
    archived, or it resurrects ones the author had deleted on purpose. That needs an
    `archived_by_cascade` marker and gets it wrong the first time somebody forgets it.
  · FILTER on the endpoints at read time — symmetry is then free: archive hides the edges, restore
    brings back exactly the ones that were still live, and an edge the author deleted stays
    deleted because its own `is_archived` is independent.

The second is what shipped, and the fourth test below is the one that proves the difference. These
need real SQL: every unit test in this service stubs the repo, so the queries themselves were
covered by nothing.
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories import ReferenceViolationError
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo

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


@pytest.fixture
async def world(pool):
    """A Work with two live scenes — the minimum an edge needs."""
    user, book = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        project = await c.fetchval(
            "INSERT INTO composition_work (created_by, book_id) VALUES ($1,$2) RETURNING id",
            user, book,
        )
        scenes = [
            await c.fetchval(
                "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, story_order)"
                " VALUES ($1,$2,$3,'scene',$4,$5) RETURNING id",
                user, project, book, f"m{i:03d}", i * 1000,
            )
            for i in range(3)
        ]
    return {"user": user, "book": book, "project": project, "scenes": scenes}


async def test_an_edge_hides_with_its_endpoint_and_comes_BACK_with_it(pool, world):
    links, outline = SceneLinksRepo(pool), OutlineRepo(pool)
    a, b, _ = world["scenes"]
    await links.create(world["project"], a, b, created_by=world["user"], label="setup → payoff")

    assert len(await links.list_by_project(world["project"])) == 1
    assert len(await links.list_by_book(world["book"])) == 1

    await outline.archive_node(b)
    assert await links.list_by_project(world["project"]) == [], (
        "the edge points at a scene the tree no longer shows — it must not still be returned"
    )
    assert await links.list_by_book(world["book"]) == [], "the book-wide read has the same hole"

    await outline.restore_node(b)
    assert len(await links.list_by_project(world["project"])) == 1, (
        "restoring the scene must bring its edges back — with no cascade bookkeeping to get wrong"
    )
    assert len(await links.list_by_book(world["book"])) == 1


async def test_the_FROM_endpoint_counts_too(pool, world):
    """Both directions, because it would be easy to guard only the one the bug was noticed on."""
    links, outline = SceneLinksRepo(pool), OutlineRepo(pool)
    a, b, _ = world["scenes"]
    await links.create(world["project"], a, b, created_by=world["user"])
    await outline.archive_node(a)
    assert await links.list_by_project(world["project"]) == []


async def test_an_edge_the_AUTHOR_deleted_stays_deleted_across_archive_restore(pool, world):
    """The property that makes read-filtering better than cascading the archive.

    A cascade has to remember which edges IT archived; if it doesn't, restoring the scene
    resurrects an edge the author had deliberately removed. Filtering keeps the two facts
    independent — the edge's own `is_archived` still says the author deleted it.
    """
    links, outline = SceneLinksRepo(pool), OutlineRepo(pool)
    a, b, c = world["scenes"]
    kept = await links.create(world["project"], a, b, created_by=world["user"], label="kept")
    dropped = await links.create(world["project"], a, c, created_by=world["user"], label="dropped")
    await links.delete(world["project"], dropped.id)          # the author removes this one

    await outline.archive_node(b)
    await outline.archive_node(c)
    await outline.restore_node(b)
    await outline.restore_node(c)

    surviving = [link.id for link in await links.list_by_project(world["project"])]
    assert surviving == [kept.id], (
        "restoring the scenes resurrected an edge the author had deleted — the archive and the "
        "author's own delete must stay independent facts"
    )


async def test_you_cannot_draw_a_NEW_edge_onto_an_archived_scene(pool, world):
    """The FE picker already filters archived targets, but a rule that lives only in one client is
    not a rule — MCP and REST reach this same repo through different front doors."""
    links, outline = SceneLinksRepo(pool), OutlineRepo(pool)
    a, b, _ = world["scenes"]
    await outline.archive_node(b)
    with pytest.raises(ReferenceViolationError):
        await links.create(world["project"], a, b, created_by=world["user"])


async def test_a_live_target_is_still_creatable(pool, world):
    """The guard must not read as 'creates are broken' — pin the happy path beside the refusal."""
    links = SceneLinksRepo(pool)
    a, b, _ = world["scenes"]
    link = await links.create(world["project"], a, b, created_by=world["user"])
    assert link.id is not None
