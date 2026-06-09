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
        # default so a test can assert these even when timeline() is never called
        # (e.g. a node with no chapter_id → gather_timeline short-circuits).
        self.seen_before_order: int | None = None
        self.seen_after_order: int | None = None
    async def glossary_semantic(self, user_id, *, project_id, query, **kw):
        return self._semantic_bios
    async def timeline(self, bearer, *, project_id, before_order=None, after_order=None, **kw):
        # LOOM-32: the lens now queries the DENSE event_order axis (before_order),
        # not the sparse before_chronological. Record both bounds so a test can
        # assert the cutoff (= scene chapter sort × stride) AND the recent-window
        # lower bound (/review-impl MED#1).
        self.seen_before_order = before_order
        self.seen_after_order = after_order
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


def _req(project_id=PROJECT, story_order=5, guide="", settings=None):
    return PackRequest(
        user_id=USER, project_id=project_id, book_id=BOOK,
        node={"id": str(NODE), "chapter_id": str(CHAPTER), "story_order": story_order,
              "present_entity_ids": [], "pov_entity_id": None, "beat_role": "hook",
              "goal": "rescue", "synopsis": "the escape", "title": "Ch1"},
        bearer="jwt", guide=guide, settings=settings or {},
    )


class StubNarrativeThreads:
    """FD-1 S3 — list_open returns open promise threads for the re-injection lens."""
    def __init__(self, threads=None):
        self._t = threads or []

    async def list_open(self, user_id, project_id, *, limit=100):
        from types import SimpleNamespace
        return [SimpleNamespace(kind=k, summary=s) for k, s in self._t][:limit]


async def _pack(req, *, book=None, glossary=None, knowledge=None, canon=None, narrative_threads=None):
    return await pack(
        req, book=book or StubBook(), glossary=glossary or StubGlossary(),
        knowledge=knowledge or StubKnowledge(), canon_repo=canon or StubCanon(),
        outline_repo=StubOutline(), scene_links_repo=StubSceneLinks(),
        budget_tokens=10_000, counter=_wc,
        narrative_threads_repo=narrative_threads,
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


# ── FD-1 S3: open-promise re-injection gate (review-impl LOW#4) ──


async def test_open_promises_reinjected_when_enabled():
    pc = await _pack(
        _req(settings={"narrative_thread_enabled": True}),
        narrative_threads=StubNarrativeThreads([("foreshadow", "a black spear on the wall")]),
    )
    assert "<open_promises>" in pc.prompt
    assert "foreshadow: a black spear on the wall" in pc.prompt
    assert pc.reinjected_promise_count == 1  # FD-1 S4b — deterministic S3 fired-signal


async def test_open_promises_absent_when_flag_off():
    # Flag off (default) → the lens isn't gathered even if a repo is wired.
    pc = await _pack(
        _req(settings={}),
        narrative_threads=StubNarrativeThreads([("foreshadow", "X")]),
    )
    assert "<open_promises>" not in pc.prompt
    assert pc.reinjected_promise_count == 0


async def test_open_promises_absent_when_no_repo():
    # Flag on but no repo wired → no gather, no block (no crash).
    pc = await _pack(_req(settings={"narrative_thread_enabled": True}), narrative_threads=None)
    assert "<open_promises>" not in pc.prompt
    assert pc.reinjected_promise_count == 0


async def test_reinjected_promise_count_matches_gathered_set():
    # FD-1 S4b non-default lock — the count is the re-injected set size (3), not a
    # hardcoded 0/1; proves the live-smoke's deterministic signal tracks the ledger.
    pc = await _pack(
        _req(settings={"narrative_thread_enabled": True}),
        narrative_threads=StubNarrativeThreads(
            [("foreshadow", "the spear"), ("promise", "Kael's vow"), ("question", "the heir")]),
    )
    assert pc.reinjected_promise_count == 3


async def test_chapter_sort_hint_skips_redundant_book_fetch():
    # Cycle-4 (chapter_sort double-fetch): when the caller already fetched the
    # chapter sort (B2/B3 build the synthetic node's story_order from it) and
    # passes chapter_sort_hint, pack() drives scene_sort_order from the hint and
    # does NOT re-call book.get_chapter_sort_orders for the scene's own chapter.
    class CountingBook(StubBook):
        def __init__(self):
            super().__init__()
            self.sort_calls = 0
        async def get_chapter_sort_orders(self, chapter_ids):
            self.sort_calls += 1
            return await super().get_chapter_sort_orders(chapter_ids)

    book = CountingBook()
    req = _req()
    req.chapter_sort_hint = 7
    pc = await _pack(req, book=book)
    assert pc.scene_sort_order == 7 and book.sort_calls == 0


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
    # scene chapter sort = 5 → at_order cutoff = 5_000_000. A ch2 event (2e6) is
    # in-world-past → kept; lore hits are filtered on the chapter-sort axis.
    kn = StubKnowledge(
        events=[{"event_order": 2_000_000, "title": "past", "summary": "x"}],
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
    assert kn.seen_before_order == 5_000_000  # cutoff = scene chapter sort × stride


async def test_timeline_dense_axis_carries_dateless_and_excludes_future():
    # LOOM-32 cross-chapter carry regression: the timeline lens reads event_order
    # (dense, always set on publish), NOT chronological_order (sparse/dateless).
    # A prior-chapter event with NO date (chronological_order absent) MUST carry;
    # a same/future-chapter event MUST be excluded. Scene chapter sort=5 → cutoff 5e6.
    kn = StubKnowledge(events=[
        {"event_order": 1_000_000, "title": "ch1 dateless plot", "summary": "the keep fell"},
        {"event_order": 5_000_000, "title": "ch5 future", "summary": "spoiler"},
        {"event_order": 5_500_000, "title": "ch6 future", "summary": "spoiler2"},
    ])
    pc = await _pack(_req(story_order=5005), knowledge=kn)
    memory = pc.blocks.get("memory", "")
    assert "ch1 dateless plot" in memory          # dateless prior-chapter event carries
    assert "ch5 future" not in memory and "ch6 future" not in memory  # spoiler-bounded
    assert kn.seen_after_order is None  # sort 5 ≤ window 5 → no lower bound (carry all prior)


async def test_timeline_recent_window_bounds_lookback_on_deep_chapter():
    # /review-impl MED#1: deep in a long book the endpoint's ASC+LIMIT would return
    # the OLDEST prior events. The packer bounds lookback to the last W chapters via
    # after_order. Scene chapter sort=10, W=5 → carry chapters [5,9): after_order =
    # (10-5)×stride - 1 = 4_999_999, before_order = 10_000_000.
    kn = StubKnowledge(events=[{"event_order": 6_000_000, "title": "recent ch6", "summary": "x"}])
    pc = await _pack(_req(), knowledge=kn, book=StubBook(sort_map={str(CHAPTER): 10}))
    assert kn.seen_before_order == 10_000_000
    assert kn.seen_after_order == 4_999_999  # (10 - 5) × stride - 1 → includes chapter 5 onward
    assert "recent ch6" in pc.blocks.get("memory", "")


async def test_timeline_empty_when_chapter_unplaceable():
    # /review-impl LOW#2: a node with no chapter_id → scene_sort_order None →
    # at_order None → gather_timeline returns [] (fail closed, no leak).
    kn = StubKnowledge(events=[{"event_order": 1_000_000, "title": "should not appear"}])
    req = PackRequest(
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        node={"id": str(NODE), "chapter_id": None, "story_order": 5,
              "present_entity_ids": [], "pov_entity_id": None, "beat_role": "hook",
              "goal": "g", "synopsis": "s", "title": "t"},
        bearer="jwt",
    )
    pc = await _pack(req, knowledge=kn)
    assert kn.seen_before_order is None  # no chapter → at_order None → not queried
    assert "should not appear" not in pc.blocks.get("memory", "")


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
