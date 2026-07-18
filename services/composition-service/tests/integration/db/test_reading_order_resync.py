"""24 PH20 Row-3 — the reading-axis MIRROR, against real SQL.

Composition stores a DERIVED copy of book-service's chapter order as `outline_node.story_order`
(chapter at `sort * STRIDE`, its i-th scene at `+ i`), because the packer's strictly-prior lenses
and the canon-rule windows key on it. Nothing keeps the two in step — composition consumes no book
events — so after a manuscript reorder the mirror is REBUILT from the book's truth.

These are DB tests, not mocks, because every failure mode here is a SQL one: a permutation that
half-applies, a scene that falls off the chapter-major axis, a canon anchor left pointing at a slot
that now belongs to someone else.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE as S

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    await run_migrations(p)
    yield p
    await p.close()


async def _work(pool, project, book, user):
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO composition_work (project_id, book_id, created_by) VALUES ($1,$2,$3)",
            project, book, user,
        )


def _chapter(chapter_id, title, sort, n_scenes):
    return {
        "chapter_id": chapter_id, "title": title, "intent": "", "story_order": sort * S,
        "scenes": [
            {"title": f"{title}{i}", "synopsis": "", "story_order": sort * S + i}
            for i in range(n_scenes)
        ],
    }


async def test_resync_moves_chapters_scenes_and_canon_anchors_together(pool):
    """A SWAP. All three must move, or the axis is inconsistent — and the canon rule is the one that
    silently breaks: `from_order`/`until_order` are positions on this very axis with NO node FK (the
    story timeline IS their only anchor), so a renumber that ignored them would leave the rule
    pointing at whatever chapter now occupies the old slot."""
    repo = OutlineRepo(pool)
    project, book, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch_a, ch_b = uuid.uuid4(), uuid.uuid4()
    await _work(pool, project, book, user)

    res = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc",
        chapters=[_chapter(ch_a, "a", 1, 2), _chapter(ch_b, "b", 2, 2)],
    )
    node_a, node_b = res["chapter_ids"]

    async with pool.acquire() as c:
        rule = await c.fetchval(
            "INSERT INTO canon_rule (created_by, project_id, book_id, text, from_order, until_order) "
            "VALUES ($1,$2,$3,'no magic before the gate',$4,$5) RETURNING id",
            user, project, book, 1 * S, 1 * S + 1,   # anchored to chapter A (slot 1), with an offset
        )

    # The manuscript reorder: B becomes chapter 1, A becomes chapter 2.
    moved = await repo.resync_reading_order(book, {ch_b: 1, ch_a: 2})
    assert moved["chapters"] == 2

    async with pool.acquire() as c:
        a = await c.fetchval("SELECT story_order FROM outline_node WHERE id=$1", node_a)
        b = await c.fetchval("SELECT story_order FROM outline_node WHERE id=$1", node_b)
        a_scenes = [r["story_order"] for r in await c.fetch(
            'SELECT story_order FROM outline_node WHERE parent_id=$1 ORDER BY rank COLLATE "C", id',
            node_a)]
        b_scenes = [r["story_order"] for r in await c.fetch(
            'SELECT story_order FROM outline_node WHERE parent_id=$1 ORDER BY rank COLLATE "C", id',
            node_b)]
        r = await c.fetchrow("SELECT from_order, until_order FROM canon_rule WHERE id=$1", rule)

    assert b == 1 * S, "B took slot 1"
    assert a == 2 * S, "A moved to slot 2"
    assert b_scenes == [1 * S, 1 * S + 1]
    assert a_scenes == [2 * S, 2 * S + 1], "scenes follow their chapter, on the chapter-major axis"
    assert r["from_order"] == 2 * S, "the canon anchor must follow its CHAPTER, not sit on its old slot"
    assert r["until_order"] == 2 * S + 1, "the intra-chapter offset survives the remap"
    assert moved["canon_rules"] == 2


async def test_resync_is_idempotent_and_leaves_unknown_chapters_alone(pool):
    """The route chains reorder→resync, so a client WILL re-issue after a partial failure: the
    rebuild must converge, not drift. And a chapter node whose book chapter is gone (trashed
    upstream) keeps its stale slot — guessing one would be worse than stale."""
    repo = OutlineRepo(pool)
    project, book, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch_a, ch_orphan = uuid.uuid4(), uuid.uuid4()
    await _work(pool, project, book, user)

    res = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc",
        chapters=[_chapter(ch_a, "a", 1, 1), _chapter(ch_orphan, "gone", 2, 0)],
    )
    node_a, node_orphan = res["chapter_ids"]

    first = await repo.resync_reading_order(book, {ch_a: 3})   # orphan not in the book's order
    second = await repo.resync_reading_order(book, {ch_a: 3})

    assert first["chapters"] == 1
    assert second["chapters"] == 0, "an already-correct mirror is a no-op, not a rewrite"
    async with pool.acquire() as c:
        a = await c.fetchval("SELECT story_order FROM outline_node WHERE id=$1", node_a)
        orphan = await c.fetchval("SELECT story_order FROM outline_node WHERE id=$1", node_orphan)
        scene = await c.fetchval("SELECT story_order FROM outline_node WHERE parent_id=$1", node_a)
    assert a == 3 * S
    assert scene == 3 * S, "the scene followed its chapter on the re-run too"
    assert orphan == 2 * S, "a chapter absent from the book's order keeps its slot, not a guess"


async def test_a_scene_drag_keeps_scenes_on_the_global_axis_not_a_chapter_local_one(pool):
    """The H5 Row-4 scene drag calls `_renumber_scene_story_order`, which used to renumber a
    chapter's scenes to a chapter-LOCAL 0..n-1 — collapsing them onto the same low integers as every
    OTHER chapter's scenes. That destroys the one global reading order the packer's strictly-prior
    filter and the canon windows key on, and it fired on every scene drag."""
    repo = OutlineRepo(pool)
    project, book, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    await _work(pool, project, book, user)

    res = await repo.commit_decomposed_tree(
        project, book_id=book, created_by=user, arc_title="Arc",
        chapters=[_chapter(ch, "s", 5, 3)],   # book chapter 5 ⇒ scenes at 5000, 5001, 5002
    )
    chapter_node = res["chapter_ids"][0]
    scenes = res["scene_ids"]

    # Drag the LAST scene to the front (after_id=None ⇒ first child) — the Row-4 write path.
    await repo.reorder_node(scenes[2], new_parent_id=chapter_node, after_id=None)

    async with pool.acquire() as c:
        got = [(r["title"], r["story_order"]) for r in await c.fetch(
            "SELECT title, story_order FROM outline_node WHERE parent_id=$1 "
            'ORDER BY rank COLLATE "C", id', chapter_node)]

    assert [t for t, _ in got] == ["s2", "s0", "s1"], "the drag reordered the scenes"
    assert [o for _, o in got] == [5 * S, 5 * S + 1, 5 * S + 2], (
        f"scenes fell off the global axis onto a chapter-local one: {got}")
