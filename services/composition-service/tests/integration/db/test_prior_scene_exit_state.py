"""D-GENERATED-FACT-HAS-NO-HOME — `OutlineRepo.prior_scene_exit_state`, against real SQL.

The two properties this method has are BOTH in the WHERE clause, which means a unit test with
a fake repo cannot see them at all:

  · archived scenes are excluded — a soft-deleted scene is not part of the story, and feeding
    its cast into the next prompt would resurrect a deleted character exactly the way
    D-ARCHIVED-SCENE-PROSE-LEAK resurrected a discarded ending;
  · the position bound is strict and NULL-excluding — a scene must never see its own future,
    and an unplaced scene has no provable position, so "probably before" is not a guarantee.

No cleanup, hence nothing destructive: every row is created under a fresh random project_id,
so parallel runs and a dirty database cannot collide (`db-safety-gate` has nothing to catch
here, and there is no unscoped DELETE to guard).
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


def _cast(who: str, pronoun: str) -> dict:
    return {"v": 1, "source": "generator",
            "cast": [{"who": who, "pronoun": pronoun, "role": ""}]}


async def _scene(repo, project, user, chapter, order, exit_state=None):
    return await repo.create_node(
        project, created_by=user, kind="scene", title=f"S{order}",
        chapter_id=chapter, story_order=order, exit_state=exit_state,
    )


async def test_it_returns_the_immediately_preceding_scene_not_the_first_one(pool):
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    repo = OutlineRepo(pool)
    await _scene(repo, project, user, chapter, 10, _cast("Elara", "she"))
    await _scene(repo, project, user, chapter, 20, _cast("Cassius", "he"))

    got = await repo.prior_scene_exit_state(project, chapter, 30)
    assert got["cast"][0]["who"] == "Cassius", "the NEAREST predecessor, not the earliest"


async def test_an_archived_scene_does_not_hand_its_cast_forward(pool):
    """The scene was deleted. Its characters left with it."""
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    repo = OutlineRepo(pool)
    await _scene(repo, project, user, chapter, 10, _cast("Elara", "she"))
    doomed = await _scene(repo, project, user, chapter, 20, _cast("Ghost", "they"))
    await repo.archive_node(doomed.id)

    got = await repo.prior_scene_exit_state(project, chapter, 30)
    assert got["cast"][0]["who"] == "Elara", "the archived scene must be skipped, not returned"


async def test_a_scene_never_sees_its_own_future(pool):
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    repo = OutlineRepo(pool)
    await _scene(repo, project, user, chapter, 20, _cast("Cassius", "he"))
    await _scene(repo, project, user, chapter, 30, _cast("Spoiler", "she"))

    # Strictly `<`: at position 20 its OWN row is not its predecessor either.
    assert await repo.prior_scene_exit_state(project, chapter, 20) is None
    assert (await repo.prior_scene_exit_state(project, chapter, 30))["cast"][0]["who"] == "Cassius"


async def test_an_unplaced_scene_is_not_treated_as_earlier(pool):
    """`story_order IS NULL` sorts last in this repo's other queries. Here it is EXCLUDED:
    an unplaced scene has no provable position, and a spoiler guarantee cannot rest on a
    sort tiebreak."""
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    repo = OutlineRepo(pool)
    await repo.create_node(project, created_by=user, kind="scene", title="floating",
                           chapter_id=chapter, exit_state=_cast("Nowhere", "they"))

    assert await repo.prior_scene_exit_state(project, chapter, 30) is None


async def test_another_works_scene_is_not_visible(pool):
    """The scope key is `project_id`. Without it in the WHERE clause a chapter id collision
    across Works would hand one book's cast to another."""
    user, book = uuid.uuid4(), uuid.uuid4()
    mine, theirs, chapter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    works = WorksRepo(pool)
    await works.create(user, mine, book)
    await works.create(user, theirs, uuid.uuid4())
    repo = OutlineRepo(pool)
    await _scene(repo, theirs, user, chapter, 10, _cast("Foreign", "she"))

    assert await repo.prior_scene_exit_state(mine, chapter, 30) is None


async def test_a_predecessor_that_recorded_nothing_returns_None_not_an_empty_shell(pool):
    user, project, book, chapter = (uuid.uuid4() for _ in range(4))
    await WorksRepo(pool).create(user, project, book)
    repo = OutlineRepo(pool)
    await _scene(repo, project, user, chapter, 10, None)

    assert await repo.prior_scene_exit_state(project, chapter, 30) is None
