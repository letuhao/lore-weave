"""T37b — the author's role declaration, and the axis it lands on.

WHY THE STRIDE IS THE SUBJECT OF THIS FILE
------------------------------------------
composition-service defines `STORY_ORDER_CHAPTER_STRIDE = 1000` for its own outline ordering.
The KG's reading axis is `chapter × 1_000_000` — T36 measured the live graph at
1 000 000 → 20 000 000 for chapters 1..20.

**Three orders of magnitude apart, for the same word.** A role written on the wrong one is
not an error: the fact is created, the endpoint returns 201, and every as-of read at the
real position misses it. The canon check then reports a character with no ties, which reads
as "this book has no roles" rather than "that write used the wrong scale" — the exact shape
of `knowledge-reading-axis-is-sort-order-times-stride`, and of every silent-degradation
defect this plan has found.

So the endpoint takes a CHAPTER and converts once, and these rules pin the conversion rather
than the plumbing.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.routers.canon import KG_EVENT_ORDER_CHAPTER_STRIDE, RoleDeclaration, declare_role


class _Works:
    def __init__(self, book_id):
        self.book_id = book_id

    async def get(self, project_id):
        return type("W", (), {"book_id": self.book_id, "project_id": project_id})()


class _Grant:
    pass


class _Kal:
    def __init__(self):
        self.calls: list[dict] = []

    async def append_role_fact(self, book_id, **kw):
        self.calls.append({"book_id": book_id, **kw})
        return {"fact_id": str(uuid4())}


@pytest.fixture(autouse=True)
def _no_grant(monkeypatch):
    async def _ok(*a, **k):
        return None
    monkeypatch.setattr("app.routers.canon._require_work", _ok)


def _decl(**kw) -> RoleDeclaration:
    base = dict(subject_entity_id=uuid4(), predicate="betrayed", object="Lam Uyen",
                from_chapter_sort_order=12, source_episode_id=uuid4())
    base.update(kw)
    return RoleDeclaration(**base)


def test_the_KG_stride_is_not_compositions_own_stride():
    """The constant this endpoint converts with, asserted against the one it must NOT be.
    A future edit that 'unifies' the two by importing composition's would be a 1000x silent
    mis-write, so the difference is pinned as a fact rather than left as a coincidence."""
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

    assert KG_EVENT_ORDER_CHAPTER_STRIDE == 1_000_000
    assert STORY_ORDER_CHAPTER_STRIDE == 1_000
    assert KG_EVENT_ORDER_CHAPTER_STRIDE != STORY_ORDER_CHAPTER_STRIDE, (
        "the KG reading axis and composition's outline order are DIFFERENT scales; "
        "collapsing them writes every role 1000x too early, silently")


@pytest.mark.asyncio
async def test_a_declared_role_lands_on_the_KG_axis_not_the_outline_axis():
    """🔴 The rule this file exists for. Chapter 12 must reach the KAL as 12 000 000, not
    12 000. Both are plausible integers; only one is on the axis the as-of read uses."""
    book = uuid4()
    kal = _Kal()
    out = await declare_role(
        uuid4(), _decl(from_chapter_sort_order=12), user_id=uuid4(),
        works=_Works(book), grant=_Grant(), kal=kal,
    )
    assert len(kal.calls) == 1
    sent = kal.calls[0]["valid_from_ordinal"]
    assert sent == 12_000_000, (
        f"the role was written at ordinal {sent}. Chapter 12 on the KG reading axis is "
        f"12_000_000; {12_000} would be composition's outline scale, and a role written "
        f"there is invisible to every as-of read at the real position")
    assert out["valid_from_ordinal"] == 12_000_000
    assert out["from_chapter_sort_order"] == 12


@pytest.mark.asyncio
async def test_the_response_ECHOES_the_axis_so_a_scale_bug_is_visible():
    """A 201 that says nothing cannot distinguish a correct write from a 1000x-early one.
    The echo is the only thing standing between a caller and a silent mis-scale."""
    kal = _Kal()
    out = await declare_role(
        uuid4(), _decl(from_chapter_sort_order=3), user_id=uuid4(),
        works=_Works(uuid4()), grant=_Grant(), kal=kal,
    )
    assert out["valid_from_ordinal"] == 3 * KG_EVENT_ORDER_CHAPTER_STRIDE
    assert "fact" in out


def test_a_role_cannot_be_declared_at_chapter_zero_or_below():
    """`from_chapter_sort_order=0` is almost always an unresolved position rather than a
    prologue claim — and a role at ordinal 0 is in force for the ENTIRE book, which is the
    most expensive possible default to get wrong."""
    for bad in (0, -1):
        with pytest.raises(ValueError, match="from_chapter_sort_order"):
            _decl(from_chapter_sort_order=bad)


def test_an_empty_predicate_or_object_is_refused():
    """A role with a blank side is a canon claim about nothing, and the KAL would store it
    happily — `attr_or_predicate` and `value` are plain strings downstream."""
    for field in ("predicate", "object"):
        with pytest.raises(ValueError):
            _decl(**{field: "   "})
