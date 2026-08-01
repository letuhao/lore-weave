"""S2 — `OutlineRepo.plan_liveness_after`, the producer the cascade never had.

`resolve_cast_liveness(entity_ids, snapshot, plan_status=...)` has accepted a plan layer since
S2 shipped, and MEASURED 2026-08-01 nothing ever passed one: the single production call site
handed it the knowledge snapshot alone. So the middle rung of a three-rung cascade was
unreachable, and every cast member the graph had not heard of fell straight through to
`unknown`/`none` — including the one the acceptance defect turns on (scene 1's prose kills
someone scene 2's cast still lists, while the KG tracks book-level status and has no row).

Every property lives in the WHERE clause, so a unit test with a fake repo cannot see any of
them. No cleanup, nothing destructive: each test builds under a fresh random project_id, so
parallel runs and a dirty database cannot collide.
"""
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo

pytestmark = pytest.mark.xdist_group("pg")

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")


@pytest.fixture
async def pool():
    if not _DSN:
        pytest.skip("set TEST_COMPOSITION_DB_URL to a throwaway DB to run")
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=2)
    try:
        await run_migrations(p)
        yield p
    finally:
        await p.close()


async def _scene(pool, repo, project, user, chapter, order: int | None,
                 cast: list[uuid.UUID], *, archived: bool = False) -> uuid.UUID:
    node = await repo.create_node(project, created_by=user, kind="scene",
                                  chapter_id=chapter, status="done")
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE outline_node SET story_order=$2, present_entity_ids=$3, is_archived=$4 "
            "WHERE id=$1",
            node.id, order, cast, archived,
        )
    return node.id


async def test_an_entity_the_plan_needs_LATER_is_asserted_alive(pool):
    """The acceptance shape. Scene 2 still lists Tô Thanh Dao, so at scene 1 the plan says she
    is alive — an opinion the KG does not have, and the reason the cascade has a middle rung."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    dao, other = uuid.uuid4(), uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 1, [dao])
    await _scene(pool, repo, project, user, chapter, 2, [dao, other])

    plan = await repo.plan_liveness_after(project, chapter, 1)
    assert plan == {str(dao): "alive", str(other): "alive"}


async def test_CONTROL_the_LAST_scene_gets_nothing(pool):
    """The counterweight. If the query dropped its position bound it would assert every cast
    member of the chapter alive everywhere — a layer that always speaks is not evidence, and it
    would silently convert `unresolved` into `checked` for the whole book."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    dao = uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 1, [dao])
    await _scene(pool, repo, project, user, chapter, 2, [dao])

    assert await repo.plan_liveness_after(project, chapter, 2) == {}


async def test_the_bound_is_STRICT_so_a_scene_never_reads_its_own_cast(pool):
    """`> order`, not `>=`. A scene asserting its OWN cast alive would make the plan agree with
    whatever the prose just did, which is a check reading its own input — the `truth_source`
    mistake this project already made once with the drafter's own prompt."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    only = uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 5, [only])

    assert await repo.plan_liveness_after(project, chapter, 5) == {}


async def test_an_ARCHIVED_later_scene_asserts_nothing(pool):
    """A soft-deleted scene is not part of the story. Letting it vote would keep a discarded
    character alive in the guard's eyes — the same leak `prior_scene_exit_state` excludes for."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    ghost = uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 1, [])
    await _scene(pool, repo, project, user, chapter, 2, [ghost], archived=True)

    assert await repo.plan_liveness_after(project, chapter, 1) == {}


async def test_an_UNPLACED_later_scene_asserts_nothing(pool):
    """NULL story_order is excluded rather than sorted last: an unplaced scene has no provable
    position, and "probably after" is not a basis for asserting anyone is alive."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    floating = uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 1, [])
    await _scene(pool, repo, project, user, chapter, None, [floating])

    assert await repo.plan_liveness_after(project, chapter, 1) == {}


async def test_a_scene_with_NO_position_asks_nothing(pool):
    """Caller-side symmetry: with no position there is no "later", so the method returns early
    instead of running a query whose bound is meaningless."""
    repo = OutlineRepo(pool)
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    await _scene(pool, repo, project, user, chapter, 2, [uuid.uuid4()])

    assert await repo.plan_liveness_after(project, chapter, None) == {}


async def test_another_CHAPTERS_scene_does_not_vote(pool):
    """Chapter-scoped, matching `prior_scene_exit_state`. `story_order` is compared within a
    chapter everywhere else in this repo; widening the axis here would be a second convention
    for one reading order — the exact drift D-A2S3B-READING-AXIS closed."""
    repo = OutlineRepo(pool)
    user, project, book = (uuid.uuid4() for _ in range(3))
    chapter, other_chapter = uuid.uuid4(), uuid.uuid4()
    await WorksRepo(pool).create(user, project, book)
    elsewhere = uuid.uuid4()
    await _scene(pool, repo, project, user, chapter, 1, [])
    await _scene(pool, repo, project, user, other_chapter, 2, [elsewhere])

    assert await repo.plan_liveness_after(project, chapter, 1) == {}
