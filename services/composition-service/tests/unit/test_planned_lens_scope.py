"""The planned-synopsis lens must not span chapters.

MEASURED on the dogfood book 2026-08-01. One project holds TWO `story_order` conventions at
once — five chapters numbered 1,2,3,4 and the rest chapter*1000+i (2000-2002, 3000-3001,
4000-4002) — so the old filter `n.story_order <= my_order` compared numbers from incompatible
schemes. A scene at 10002 pulled in **40 planned synopses from 14 chapters**; chapter-scoped
the honest answer is **2**.

That is a SPOILER LEAK and not merely prompt bloat: a chapter using the small convention sorts
below every 4-digit order, so a scene early in the book was shown unwritten synopses from
chapters ten ahead of it.

The fixture that matters is the two-convention one. A single-convention fixture passes with or
without the fix, which is why the first test here is the mixed-numbering case and not a tidy
one.
"""
from __future__ import annotations

import uuid

import pytest

from app.packer.lenses import gather_structural

CH_A, CH_B = str(uuid.uuid4()), str(uuid.uuid4())


class _Node:
    def __init__(self, chapter, order, title, *, kind="scene", status="planned", synopsis="s"):
        self.id = str(uuid.uuid4())
        self.chapter_id, self.story_order = chapter, order
        self.kind, self.status, self.title, self.synopsis = kind, status, title, synopsis


class _Outline:
    def __init__(self, nodes):
        self._nodes = nodes

    async def list_tree(self, project_id):
        return self._nodes


class _Links:
    async def list_by_project(self, project_id):
        return []


def _me(chapter=CH_A, order=2002):
    return {"id": str(uuid.uuid4()), "chapter_id": chapter, "story_order": order}


async def _planned(nodes, node):
    _beat, _threads, planned = await gather_structural(
        _Outline(nodes), _Links(), project_id=uuid.uuid4(), node=node)
    return [p["title"] for p in planned]


@pytest.mark.asyncio
async def test_a_FOREIGN_chapter_using_the_other_numbering_does_not_leak_in():
    """The measured shape: chapter B numbers its scenes 1,2,3 while chapter A uses 2000+. Every
    B scene sorts below every A scene, so the position filter alone lets the whole of B through
    — including scenes that come LATER in the book."""
    nodes = [
        _Node(CH_A, 2000, "A-first"),
        _Node(CH_A, 2001, "A-second"),
        _Node(CH_B, 1, "B-one-CHAPTER-TEN"),
        _Node(CH_B, 2, "B-two-CHAPTER-TEN"),
        _Node(CH_B, 3, "B-three-CHAPTER-TEN"),
    ]
    got = await _planned(nodes, _me(order=2002))
    assert got == ["A-first", "A-second"], f"foreign chapter leaked: {got}"


@pytest.mark.asyncio
async def test_CONTROL_the_scenes_planned_earlier_in_MY_chapter_still_arrive():
    """Without this, "return nothing" satisfies the test above and the lens stops doing its
    job — the drafter loses every planned beat it is supposed to avoid contradicting."""
    nodes = [_Node(CH_A, 2000, "A-first"), _Node(CH_A, 2001, "A-second")]
    assert await _planned(nodes, _me(order=2002)) == ["A-first", "A-second"]


@pytest.mark.asyncio
async def test_a_LATER_scene_in_my_own_chapter_is_still_excluded():
    """The position bound survives the chapter bound; they are different guarantees and adding
    one must not quietly drop the other."""
    nodes = [_Node(CH_A, 2000, "before"), _Node(CH_A, 2500, "AFTER-ME")]
    assert await _planned(nodes, _me(order=2002)) == ["before"]


@pytest.mark.asyncio
async def test_a_DONE_scene_is_still_excluded():
    """Its prose is already in `<recent>`; the synopsis would be a second, staler copy."""
    nodes = [_Node(CH_A, 2000, "written", status="done"), _Node(CH_A, 2001, "planned")]
    assert await _planned(nodes, _me(order=2002)) == ["planned"]


@pytest.mark.asyncio
async def test_a_node_with_NO_chapter_falls_back_rather_than_returning_nothing():
    """A planned node not yet attached to a chapter has no chapter to be scoped to. Dropping
    the scope for it is deliberate: the alternative is a silent empty lens on exactly the
    scenes an author is still organising."""
    nodes = [_Node(CH_A, 2000, "A-first"), _Node(CH_B, 1, "B-one")]
    got = await _planned(nodes, {"id": str(uuid.uuid4()), "chapter_id": None, "story_order": 2002})
    assert set(got) == {"A-first", "B-one"}
