"""TOOL DEEP-DIVE `translation_start_job` (T4-D1) — the cost gate estimated ZERO.

🔴 MEASURED LIVE 2026-08-13, throwaway book 019ff8f5, a chapter holding 121 words in two real
paragraph blocks. `translation_start_job` returned

    {"scope": "chapters", "priced": false, "cost_usd": null,
     "input_tokens": 0, "output_tokens": 0, "segment_count": 0, ...}

so the confirm card rendered "Translate 1 chapter(s)" with NO figure — correctly, because there was
none. The job then cost real money: translation_jobs.cost_usd = 0.004485, chapter_translations
input_tokens = 400, output_tokens = 219.

The timestamps make the mechanism exact. `_sum_chapter_tokens` sums `chapter_segments`; a chapter
that has never been translated has none, so it returns (0, 0), and `_price_tokens` early-returns
None on `input_tokens <= 0 and output_tokens <= 0` — the pricing oracle is never called. The
segments are written BY THE JOB: job created 04:23:34.797, started 04:23:34.877, the chapter's only
segment (token_estimate=166) created 04:23:40.504. The gate read a table its own downstream fills.

So the zero was STRUCTURAL: a first-time translation of any chapter always estimated zero, and only
a chapter already through the pipeline showed a number — the case where the author least needs it.
"""

import uuid

import pytest

from app.mcp import estimate as est


class _FakePool:
    """Just enough asyncpg surface for the estimate path."""

    def __init__(self, segments_by_chapter):
        self.segments = dict(segments_by_chapter)
        self.ensured = []

    async def fetch(self, sql, *args):
        assert "DISTINCT chapter_id" in sql
        return [{"chapter_id": c} for c in args[0] if self.segments.get(c)]

    async def fetchrow(self, sql, *args):
        toks = sum(t for c in args[0] for t in self.segments.get(c, []))
        segs = sum(len(self.segments.get(c, [])) for c in args[0])
        return {"toks": toks, "segs": segs}


@pytest.mark.asyncio
async def test_a_chapter_with_no_segments_is_segmented_so_it_can_be_priced(monkeypatch):
    """🔴 THE DEFECT. Before the fix this chapter summed to (0, 0) and the card showed no cost."""
    book_id, chapter_id = uuid.uuid4(), uuid.uuid4()
    pool = _FakePool({})

    async def _ensure(db, bid, cid, **kw):
        pool.ensured.append(cid)
        pool.segments[cid] = [166]           # what the real segmenter would write
        return {"segments": 1, "changed": True}

    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", _ensure)
    await est._ensure_segments_for_estimate(pool, book_id, [chapter_id])
    toks, segs = await est._sum_chapter_tokens(pool, [chapter_id])
    assert pool.ensured == [chapter_id]
    assert (toks, segs) == (166, 1), (
        "a first-time chapter still estimates zero, so a PAID action asks for consent with no price"
    )


@pytest.mark.asyncio
async def test_an_ALREADY_SEGMENTED_chapter_costs_no_book_service_call(monkeypatch):
    """THE CONTROL for cost: the repair is bounded to chapters that have nothing, so an
    already-segmented book pays one cheap query and no per-chapter HTTP."""
    book_id, chapter_id = uuid.uuid4(), uuid.uuid4()
    pool = _FakePool({chapter_id: [140]})

    async def _ensure(db, bid, cid, **kw):
        pool.ensured.append(cid)
        return {}

    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", _ensure)
    await est._ensure_segments_for_estimate(pool, book_id, [chapter_id])
    assert pool.ensured == [], "an already-segmented chapter was re-segmented on the estimate path"


@pytest.mark.asyncio
async def test_a_segmentation_failure_DEGRADES_and_never_fails_the_estimate(monkeypatch):
    """THE CONTROL for safety. An estimate that raises would break PROPOSE entirely — turning a
    missing price into a missing tool. The chapter is simply left unsummed, which reproduces the old
    zero for it, and `priced=false` still says the cost is unknown."""
    book_id, chapter_id = uuid.uuid4(), uuid.uuid4()
    pool = _FakePool({})

    async def _boom(db, bid, cid, **kw):
        raise RuntimeError("book-service unreachable")

    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", _boom)
    await est._ensure_segments_for_estimate(pool, book_id, [chapter_id])   # must not raise
    toks, segs = await est._sum_chapter_tokens(pool, [chapter_id])
    assert (toks, segs) == (0, 0)


@pytest.mark.asyncio
async def test_only_the_chapters_that_are_missing_get_built(monkeypatch):
    """A mixed selection must not re-segment the ones that are fine."""
    book_id = uuid.uuid4()
    have, missing = uuid.uuid4(), uuid.uuid4()
    pool = _FakePool({have: [100]})

    async def _ensure(db, bid, cid, **kw):
        pool.ensured.append(cid)
        pool.segments[cid] = [60]
        return {}

    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", _ensure)
    await est._ensure_segments_for_estimate(pool, book_id, [have, missing])
    assert pool.ensured == [missing]
    assert await est._sum_chapter_tokens(pool, [have, missing]) == (160, 2)


@pytest.mark.asyncio
async def test_an_empty_selection_touches_nothing():
    pool = _FakePool({})
    await est._ensure_segments_for_estimate(pool, uuid.uuid4(), [])
    assert pool.ensured == []


def test_the_estimator_actually_CALLS_it_before_summing():
    """🔴 Guard the CALL SITE, not the helper. Every assertion above passes against a repair that is
    never wired in — and it must run BEFORE the sum, or it changes nothing."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "mcp" / "estimate.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    call = "await _ensure_segments_for_estimate(db, book_id, chapter_ids)"
    assert call in body, "the estimator never segments, so a first-time chapter still prices at zero"
    assert body.index(call) < body.index("input_tokens, segment_count = await _sum_chapter_tokens"), (
        "segmentation runs after the sum, so the sum still sees an empty table"
    )


def test_the_DIRTY_scope_is_left_alone():
    """The retranslate-dirty path computes from compute_segment_status, not from a raw
    chapter_segments sum, so it never had this defect and must not grow a segmentation side effect
    on the estimate path."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "mcp" / "estimate.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    dirty = body[body.index("if scope == SCOPE_DIRTY:"):body.index("output_tokens = int(round(")]
    assert "_ensure_segments_for_estimate" not in dirty.split("else:")[0], (
        "the dirty scope now segments too, which is a behaviour change it did not need"
    )
