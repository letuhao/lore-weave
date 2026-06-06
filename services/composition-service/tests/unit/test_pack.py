"""Unit tests for the packer orchestrator (stubbed clients/repos)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models import CanonRule
from app.packer.pack import OwnershipError, PackRequest, pack

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
CHAPTER = uuid.uuid4()
NODE = uuid.uuid4()


def _wc(text: str) -> int:
    return max(1, len(text.split()))


class StubBook:
    def __init__(self, owns=True, sort_map=None):
        self._owns = owns
        self._sort = sort_map or {str(CHAPTER): 5}
    async def owns_book(self, book_id, bearer):
        return self._owns
    async def get_draft(self, book_id, chapter_id, bearer):
        return {"text_content": "first para\nsecond para\nthird para"}
    async def get_chapter_sort_orders(self, chapter_ids):
        return {k: v for k, v in self._sort.items() if k in {str(c) for c in chapter_ids}}


class StubGlossary:
    def __init__(self, bios=None):
        self._bios = bios if bios is not None else [{"entity_id": "g1", "cached_name": "Kael", "short_description": "a knight"}]
    async def select_for_context(self, book_id, user_id, query, **kw):
        return self._bios


class StubKnowledge:
    def __init__(self, events=None, hits=None, entity=None, semantic_bios=None):
        self._events = events if events is not None else []
        self._hits = hits if hits is not None else []
        self._entity = entity
        # mui #4 C-1 — default [] so present falls back to glossary FTS (the
        # pre-mui#4 behaviour these tests assert).
        self._semantic_bios = semantic_bios if semantic_bios is not None else []
    async def glossary_semantic(self, user_id, *, project_id, query, **kw):
        return self._semantic_bios
    async def timeline(self, bearer, *, project_id, before_chronological=None, **kw):
        return self._events
    async def search_drawers(self, bearer, *, project_id, query, **kw):
        return self._hits
    async def get_entity(self, bearer, entity_id):
        return self._entity


class StubCanon:
    def __init__(self, rules=None):
        self._rules = rules or []
    async def list_active(self, user_id, project_id):
        return self._rules


class StubOutline:
    async def list_tree(self, user_id, project_id, **kw):
        return []


class StubSceneLinks:
    async def list_by_project(self, user_id, project_id):
        return []


def _req(project_id=PROJECT, story_order=5, guide=""):
    return PackRequest(
        user_id=USER, project_id=project_id, book_id=BOOK,
        node={"id": str(NODE), "chapter_id": str(CHAPTER), "story_order": story_order,
              "present_entity_ids": [], "pov_entity_id": None, "beat_role": "hook",
              "goal": "rescue", "synopsis": "the escape", "title": "Ch1"},
        bearer="jwt", guide=guide,
    )


async def _pack(req, *, book=None, glossary=None, knowledge=None, canon=None):
    return await pack(
        req, book=book or StubBook(), glossary=glossary or StubGlossary(),
        knowledge=knowledge or StubKnowledge(), canon_repo=canon or StubCanon(),
        outline_repo=StubOutline(), scene_links_repo=StubSceneLinks(),
        budget_tokens=10_000, counter=_wc,
    )


async def test_a1_chokepoint_rejects_missing_project():
    req = _req(project_id=None)
    with pytest.raises(ValueError, match="A1"):
        await _pack(req)


async def test_sec2_chokepoint_blocks_non_owner():
    with pytest.raises(OwnershipError):
        await _pack(_req(), book=StubBook(owns=False))


async def test_c3a_grounding_unavailable_when_no_knowledge():
    pc = await _pack(_req(), knowledge=StubKnowledge(events=[], hits=[]))
    assert pc.grounding_available is False
    assert any("grounding_unavailable" in w for w in pc.warnings)


async def _pack_with_compress(req, compress_fn, **kw):
    return await pack(
        req, book=kw.get("book") or StubBook(), glossary=StubGlossary(),
        knowledge=kw.get("knowledge") or StubKnowledge(), canon_repo=StubCanon(),
        outline_repo=StubOutline(), scene_links_repo=StubSceneLinks(),
        budget_tokens=10_000, counter=_wc, compress_fn=compress_fn,
    )


async def test_s2_compress_fires_over_threshold(monkeypatch):
    # tiny threshold → the 3 draft paras exceed it → compress the older 2, keep 1.
    monkeypatch.setattr("app.packer.pack.settings.pack_compress_recent_threshold_chars", 5)
    monkeypatch.setattr("app.packer.pack.settings.pack_compress_keep_immediate", 1)
    seen: dict = {}

    async def fake_compress(older, timeline, plan):
        seen["older"], seen["plan"] = older, plan
        return "STATE SUMMARY"

    pc = await _pack_with_compress(_req(), fake_compress)
    recent = pc.blocks.get("recent", "")
    assert "STATE SUMMARY" in recent           # summary injected (older folded in)
    assert "third para" in recent              # immediate prose kept verbatim
    assert "first para" not in recent          # older compressed out of raw
    assert seen["older"] == ["first para", "second para"]
    assert seen["plan"] == "the escape"        # node synopsis used as the plan
    # summary renders BEFORE the immediate prose (older→immediate order)
    assert recent.index("STATE SUMMARY") < recent.index("third para")


async def test_s2_compress_not_called_under_threshold():
    called = {"n": 0}

    async def fake_compress(older, timeline, plan):
        called["n"] += 1
        return "X"

    pc = await _pack_with_compress(_req(), fake_compress)  # default threshold 6000 >> ~30 chars
    assert called["n"] == 0
    assert "first para" in pc.blocks.get("recent", "")  # raw retained


async def test_s2_compress_degrade_keeps_raw(monkeypatch):
    monkeypatch.setattr("app.packer.pack.settings.pack_compress_recent_threshold_chars", 5)

    async def boom(older, timeline, plan):
        raise RuntimeError("compress down")

    pc = await _pack_with_compress(_req(), boom)  # raises → degrade
    recent = pc.blocks.get("recent", "")
    assert "STATE SUMMARY" not in recent
    assert "first para" in recent and "third para" in recent  # raw kept, no crash


async def test_l4_spoiler_drops_future_hits():
    kn = StubKnowledge(
        events=[{"chronological_order": 2, "title": "past", "summary": "x"}],
        hits=[
            {"source_id": "a", "chapter_index": 1, "text": "early lore"},   # before cutoff 5 → keep
            {"source_id": "b", "chapter_index": 9, "text": "future lore"},  # after → drop
        ],
    )
    pc = await _pack(_req(), knowledge=kn)
    assert pc.grounding_available is True
    assert "early lore" in pc.blocks.get("lore", "")
    assert "future lore" not in pc.blocks.get("lore", "")
    # in-world timeline event present in memory block
    assert "past" in pc.blocks.get("memory", "")


async def test_l4_conservative_drop_counts_no_position():
    kn = StubKnowledge(hits=[{"source_id": "not-a-uuid", "chapter_index": None, "text": "orphan"}])
    pc = await _pack(_req(), knowledge=kn)
    assert pc.l4_dropped_no_position == 1
    assert "orphan" not in pc.blocks.get("lore", "")


async def test_di3_soft_absent_glossary_entity_skipped():
    # a bio with no entity_id (soft-absent/renamed) must be skipped, not crash
    gl = StubGlossary(bios=[{"cached_name": "Ghost", "short_description": "?"}, {"entity_id": "g2", "cached_name": "Real"}])
    pc = await _pack(_req(), glossary=gl)
    assert "Real" in pc.blocks.get("present", "")
    assert "Ghost" not in pc.blocks.get("present", "")


async def test_canon_filtered_by_story_order():
    rules = [
        CanonRule(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, text="applies now", from_order=1, until_order=10),
        CanonRule(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, text="future reveal", from_order=8, until_order=None),
    ]
    pc = await _pack(_req(story_order=5), canon=StubCanon(rules))
    assert "applies now" in pc.blocks.get("canon", "")
    assert "future reveal" not in pc.blocks.get("canon", "")  # from_order 8 > story_order 5


async def test_canon_none_story_order_fails_closed_on_reveal_gates():
    # /review-impl M4 MED#1: a scene with no story_order must NOT see gated
    # reveal rules (their text is a future spoiler) — only ungated world rules.
    rules = [
        CanonRule(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, text="world rule always"),
        CanonRule(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, text="king is the villain", from_order=20, scope="reveal_gate"),
    ]
    pc = await _pack(_req(story_order=None), canon=StubCanon(rules))
    assert "world rule always" in pc.blocks.get("canon", "")
    assert "king is the villain" not in pc.blocks.get("canon", "")  # gated → excluded


async def test_l4_resolver_fallback_when_chapter_index_none():
    # chapter_index None but source_id resolves via the sort-orders batch:
    # one hit before the cutoff (kept), one at/after (dropped).
    early, late = uuid.uuid4(), uuid.uuid4()
    book = StubBook(sort_map={str(CHAPTER): 5, str(early): 2, str(late): 8})
    kn = StubKnowledge(hits=[
        {"source_id": str(early), "chapter_index": None, "text": "resolved early"},
        {"source_id": str(late), "chapter_index": None, "text": "resolved late"},
    ])
    pc = await _pack(_req(), book=book, knowledge=kn)
    assert "resolved early" in pc.blocks.get("lore", "")
    assert "resolved late" not in pc.blocks.get("lore", "")
    assert pc.l4_dropped_no_position == 0  # both resolved, none conservative-dropped
