"""D-SCENE-STORY-ORDER-UNWIRED — a scene created outside PlanForge had no place in the story.

`outline_node` carries TWO order axes and they are not interchangeable: `rank` is the
fractional string the UI tree sorts by, `story_order` is the integer position in the
NARRATIVE. `rank` has always been auto-computed on create; `story_order` was not.

That silence is not cosmetic — `story_order` is the key the cross-scene state-reinjection
reads (`prior_scene_drafts`: `story_order < $3`, the D-COMP-LONGFORM-STATE-REINJECTION
fallback that shows a draft what its earlier siblings already wrote). NULL matches nothing,
so the reinjection returned empty and every scene drafted blind — which turned the system
prompt's *"do NOT reuse a distinctive image you have already used in this work"* into an
instruction with no data to check against.

Measured on the Mị Đế book: five scenes, five different beats, and **all five closed on the
same image** (the Thanh Tâm Ấn seed and a watching figure who is *counting*).

The deeper point, and why the fix is in the repository rather than a caller: this was never
a bad choice by the author. **The logic simply did not wire itself.** A writer should not
have to know this column exists.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.repositories.outline import OutlineRepo

PROJECT = uuid.uuid4()
CHAPTER_NODE = uuid.uuid4()


class _Conn:
    """Records the story_order the repo computes, without a database."""

    def __init__(self, existing_max: int | None):
        self._max = existing_max
        self.asked: list[str] = []

    async def fetchval(self, sql, *args):
        self.asked.append(sql)
        return self._max if "max(story_order)" in sql else None


@pytest.mark.asyncio
async def test_the_first_scene_in_a_chapter_is_1_not_0():
    """1-based on purpose: with a 0 first scene, `story_order < 1` would match it and the
    opening scene would be handed itself as 'prior context'."""
    repo = OutlineRepo(object())
    conn = _Conn(existing_max=None)
    assert await repo._next_story_order(conn, PROJECT, CHAPTER_NODE) == 1


@pytest.mark.asyncio
async def test_the_next_scene_appends_after_the_last_sibling():
    repo = OutlineRepo(object())
    conn = _Conn(existing_max=4)
    assert await repo._next_story_order(conn, PROJECT, CHAPTER_NODE) == 5


@pytest.mark.asyncio
async def test_siblings_are_grouped_by_parent_with_null_comparing_equal():
    """`parent_id IS NOT DISTINCT FROM $2` — a plain `=` never matches NULL, so top-level
    nodes would each restart at 1. Mirrors `_next_rank`'s grouping exactly."""
    repo = OutlineRepo(object())
    conn = _Conn(existing_max=2)
    await repo._next_story_order(conn, PROJECT, None)
    sql = conn.asked[-1]
    assert "IS NOT DISTINCT FROM" in sql
    # Archived siblings must not hold a number: deleting a scene then adding one would
    # otherwise leave a permanent gap that the strictly-prior query reads across.
    assert "NOT is_archived" in sql


@pytest.mark.asyncio
async def test_it_is_scoped_to_the_project():
    """Two books' chapters must not share a numbering sequence."""
    repo = OutlineRepo(object())
    conn = _Conn(existing_max=1)
    await repo._next_story_order(conn, PROJECT, CHAPTER_NODE)
    assert "project_id = $1" in conn.asked[-1]
