"""D-SCENE-STORY-ORDER-UNWIRED — a scene created outside PlanForge had no place in the story.

`outline_node` carries TWO order axes and they are not interchangeable: `rank` is the
fractional string the UI tree sorts by, `story_order` is the integer position in the
NARRATIVE. `rank` has always been auto-computed on create; `story_order` was not.

That silence is not cosmetic — `story_order` is the key the cross-scene state-reinjection
reads (`prior_scene_drafts`: `story_order < $3`, the D-COMP-LONGFORM-STATE-REINJECTION
fallback that shows a draft what its earlier siblings already wrote). NULL matches nothing,
so the reinjection returned empty and every scene drafted blind — which turned the system
prompt's *"do NOT reuse a distinctive image you have already used in this work"* into an
instruction with no data to check against. Measured on the Mị Đế book: five scenes, five
different beats, and **all five closed on the same image**.

**Why this file mostly tests which CODE PATH runs, not arithmetic.** The first cut computed
a local `max(story_order) + 1` per parent. That was wrong in a way unit tests on its own
numbers would have happily confirmed: this column is chapter-major / scene-minor on ONE
strided global axis (`chapter.story_order + i`, zero-based, chapters at `n * 1000`), shared
with plan.py's commit, `chapter_gen`, the packer's strictly-prior lenses and the canon-rule
windows. A per-parent 1..N sequence is a THIRD convention on a column whose own docstring
records that two conventions already shipped once and destroyed the global reading order the
first time anyone dragged a scene.

So the thing worth pinning is that create DELEGATES to `_renumber_scene_story_order` — the
one surviving implementation, the same one the move path calls — instead of growing a
private notion of "next".
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.db.repositories.outline import OutlineRepo

PROJECT = uuid.uuid4()
CHAPTER_NODE = uuid.uuid4()
NEW_NODE = uuid.uuid4()


class _Conn:
    """Enough asyncpg surface for create_node, recording what it delegated to."""

    def __init__(self):
        self.executed: list[str] = []
        self.renumbered = False

    async def fetchrow(self, sql, *args):
        if sql.strip().startswith("INSERT INTO outline_node"):
            return {"id": NEW_NODE}
        return {"id": NEW_NODE}

    async def fetchval(self, sql, *args):
        return None

    async def execute(self, sql, *args):
        self.executed.append(sql)
        # The canonical renumber is recognisable by its shape, not its name.
        if "row_number() OVER (ORDER BY rank" in sql and "story_order" in sql:
            self.renumbered = True


def _repo_with(conn) -> OutlineRepo:
    repo = OutlineRepo(object())
    # _row_to_node is not under test; the delegation is.
    return repo


async def _create(kind: str, story_order=None):
    conn = _Conn()
    repo = _repo_with(conn)
    repo._validate_parent = AsyncMock(return_value=None)
    repo._next_rank = AsyncMock(return_value="a0")
    import app.db.repositories.outline as mod
    real_row_to_node = mod._row_to_node
    mod._row_to_node = lambda row: row
    try:
        await repo.create_node(
            PROJECT, kind=kind, parent_id=CHAPTER_NODE, created_by=uuid.uuid4(),
            story_order=story_order, conn=conn,
        )
    finally:
        mod._row_to_node = real_row_to_node
    return conn


@pytest.mark.asyncio
async def test_a_new_scene_is_placed_on_the_reading_axis():
    """THE FIX. Before it, a scene created outside PlanForge kept story_order NULL and the
    cross-scene reinjection silently matched nothing."""
    conn = await _create("scene")
    assert conn.renumbered, "create must place the scene on the reading axis"


@pytest.mark.asyncio
async def test_it_delegates_to_the_ONE_renumber_rather_than_inventing_a_next():
    """The delegation IS the point. `chapter.story_order + i` (zero-based, chapters
    strided at n*1000) is shared with plan.py, chapter_gen, the packer's strictly-prior
    lenses and the canon windows; a private `max + 1` here would be a third convention on
    a column that has already shipped a two-convention bug."""
    conn = await _create("scene")
    renumbers = [s for s in conn.executed if "row_number() OVER (ORDER BY rank" in s]
    assert len(renumbers) == 1
    sql = renumbers[0]
    # chapter-major: the scene's slot is its CHAPTER's slot plus its index…
    assert "SELECT story_order AS b FROM outline_node" in sql
    # …zero-based, so the first scene sits exactly on its chapter's own slot.
    assert "- 1) AS idx" in sql


@pytest.mark.asyncio
async def test_an_explicit_story_order_is_left_alone():
    """PlanForge passes its own numbering (and the decompiler passes imported positions).
    Create must not renumber over an authored axis."""
    conn = await _create("scene", story_order=4000)
    assert not conn.renumbered


@pytest.mark.asyncio
async def test_a_chapter_is_never_renumbered_by_this_path():
    """A chapter's slot comes from the book spine (`n * 1000`), not from its siblings —
    renumbering chapters here would fight the axis it is trying to join."""
    conn = await _create("chapter")
    assert not conn.renumbered
