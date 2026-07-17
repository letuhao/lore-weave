"""P1 — the PROPOSE-BLIND gather lens, in isolation (no DB, no HTTP; injected fakes)."""

from __future__ import annotations

import pytest

from app.engine.plan_forge.existing_state import (
    ExistingStateBudget,
    gather_existing_state,
)


class _Node:
    def __init__(self, kind, title, summary=""):
        self.kind, self.title, self.summary = kind, title, summary


class FakeStructure:
    def __init__(self, nodes): self._nodes = nodes
    async def list_tree(self, book_id, *, include_archived=False): return list(self._nodes)


class FakeOutline:
    def __init__(self, count, briefs): self._count, self._briefs = count, briefs
    async def recent_chapter_briefs(self, book_id, *, limit=12):
        return self._count, list(self._briefs)[:limit]


class FakeKal:
    def __init__(self, roster): self._roster = roster
    async def roster(self, book_id, *, user_id=None, strict=False): return list(self._roster)


class Raises:
    async def list_tree(self, *a, **k): raise RuntimeError("structure down")
    async def recent_chapter_briefs(self, *a, **k): raise RuntimeError("outline down")
    async def roster(self, *a, **k): raise RuntimeError("kal down")


# a tiny deterministic counter (1 token per whitespace word) so tests don't depend on tiktoken
def words(text: str) -> int:
    return len(text.split())


BOOK = "book-1"


async def _gather(structure, outline, kal, **kw):
    return await gather_existing_state(
        BOOK, structure_repo=structure, outline_repo=outline, kal_client=kal, counter=words, **kw,
    )


@pytest.mark.asyncio
async def test_cold_start_book_is_empty_so_grounding_is_a_no_op():
    st = await _gather(FakeStructure([]), FakeOutline(0, []), FakeKal([]))
    assert st.is_empty()
    assert st.chapter_count == 0 and not st.cast and not st.arcs
    # absent-with-a-note, never a bare silent empty
    assert "no existing arcs" in st.notes["arcs"]
    assert "no glossary characters yet" in st.notes["cast"]


@pytest.mark.asyncio
async def test_composes_arcs_cast_spine_and_reports_counts():
    structure = FakeStructure([
        _Node("saga", "Root"), _Node("arc", "The Iron Court", "Court intrigue"),
        _Node("arc", "The Long Road", "A journey"),
    ])
    outline = FakeOutline(42, [
        {"title": f"Ch{n}", "synopsis": f"syn {n}", "story_order": n * 1000}
        for n in range(42, 30, -1)
    ])
    kal = FakeKal([{"entity_id": f"e{i}", "name": f"Char{i}"} for i in range(3)])
    st = await _gather(structure, outline, kal, budget=ExistingStateBudget(total=10_000))
    assert [a.title for a in st.arcs] == ["The Iron Court", "The Long Road"]  # sagas filtered out
    assert st.chapter_count == 42               # ABSOLUTE count, not the truncated brief count
    assert len(st.recent_chapters) == 12        # last-N cap
    assert [c.name for c in st.cast] == ["Char0", "Char1", "Char2"]
    assert not st.is_empty()


@pytest.mark.asyncio
async def test_cast_is_capped_and_the_note_says_how_many_of_how_many():
    kal = FakeKal([{"entity_id": f"e{i}", "name": f"C{i}"} for i in range(500)])
    st = await _gather(FakeStructure([]), FakeOutline(0, []), kal,
                       budget=ExistingStateBudget(total=100_000, cast_cap=40))
    assert len(st.cast) == 40
    assert "showing 40 of 500" in st.notes["cast"]   # no silent truncation


@pytest.mark.asyncio
async def test_budget_trim_drops_lowest_priority_first_and_notes_it():
    # a tight budget: spine (prio 90) must survive; systems/arcs/cast trim first.
    structure = FakeStructure([_Node("arc", "ArcA", "x"), _Node("arc", "ArcB", "y")])
    outline = FakeOutline(2, [
        {"title": "ChZ", "synopsis": "the latest chapter", "story_order": 2000},
    ])
    kal = FakeKal([{"entity_id": "e1", "name": "Hero"}, {"entity_id": "e2", "name": "Villain"}])
    # budget only fits the spine line (~5 words) — cast + arcs get trimmed
    st = await _gather(structure, outline, kal, budget=ExistingStateBudget(total=6))
    assert len(st.recent_chapters) == 1                 # spine survived (highest priority)
    assert len(st.cast) < 2 or len(st.arcs) < 2          # lower-priority trimmed
    trimmed_noted = any("trimmed for budget" in v for v in st.notes.values())
    assert trimmed_noted                                 # trim is surfaced, never silent


@pytest.mark.asyncio
async def test_a_degraded_read_is_absent_with_a_note_never_a_raise():
    st = await _gather(Raises(), Raises(), Raises())
    assert st.notes["arcs"] == "arc read failed — omitted"
    assert st.notes["cast"] == "cast read failed — omitted"
    assert st.notes["spine"] == "spine read failed — omitted"
    assert st.is_empty()   # nothing read ⇒ grounding is a no-op, not a crash


@pytest.mark.asyncio
async def test_systems_extracted_from_a_caller_supplied_package():
    pkg = {"layers": {"variables": [{"code": "PA"}, {"name": "HA"}]},
           "motifs": [{"label": "打脸"}, "爽点"]}
    st = await _gather(FakeStructure([]), FakeOutline(0, []), FakeKal([]),
                       latest_package=pkg, budget=ExistingStateBudget(total=10_000))
    assert st.variables == ["PA", "HA"]
    assert st.motifs == ["打脸", "爽点"]


@pytest.mark.asyncio
async def test_fingerprint_is_deterministic_and_order_independent():
    a = FakeStructure([_Node("arc", "B"), _Node("arc", "A")])
    b = FakeStructure([_Node("arc", "A"), _Node("arc", "B")])   # reversed read order
    kal1 = FakeKal([{"entity_id": "e2", "name": "Y"}, {"entity_id": "e1", "name": "X"}])
    kal2 = FakeKal([{"entity_id": "e1", "name": "X"}, {"entity_id": "e2", "name": "Y"}])
    st1 = await _gather(a, FakeOutline(3, []), kal1, budget=ExistingStateBudget(total=10_000))
    st2 = await _gather(b, FakeOutline(3, []), kal2, budget=ExistingStateBudget(total=10_000))
    assert st1.grounded_fingerprint == st2.grounded_fingerprint   # read order can't perturb it
    # a different chapter_count ⇒ a different fingerprint
    st3 = await _gather(a, FakeOutline(4, []), kal1, budget=ExistingStateBudget(total=10_000))
    assert st3.grounded_fingerprint != st1.grounded_fingerprint
