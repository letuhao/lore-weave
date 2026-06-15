"""T2-M2.1: per-segment translation status (record + dirty compute) + endpoints.

Mock-style (fake_pool), mirroring test_segments.py. The dirty-cycle correctness is
also covered end-to-end against a real Postgres in test_segment_status_pg.py."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import FakeRecord
from app.workers.segment_status import (
    _is_dirty,
    compute_segment_status,
    record_segment_translations,
    scan_glossary_usage,
)

TOKEN = {"X-Internal-Token": "test_internal_token"}


# ── pure dirty predicate ──────────────────────────────────────────────────────

def test_is_dirty_no_record():
    assert _is_dirty("h0", None) is True


def test_is_dirty_source_changed():
    assert _is_dirty("h-new", "h-old") is True


def test_is_dirty_unchanged():
    assert _is_dirty("h0", "h0") is False


# ── scan_glossary_usage (T2-M3.2, pure) ───────────────────────────────────────

def test_scan_glossary_usage_matches_source_terms():
    segments = [(0, "提拉米来了"), (1, "无名小卒"), (2, "")]
    entity_terms = [
        ("e-tira", ["提拉米", "提拉"]),   # appears in seg 0
        ("e-other", ["龙王"]),            # appears nowhere
        ("e-empty", []),                  # no terms → never matches
    ]
    usage = scan_glossary_usage(segments, entity_terms)
    assert usage == [(0, "e-tira")]


def test_scan_glossary_usage_multiple_entities_one_segment():
    segments = [(5, "提拉米 and 龙王 meet")]
    entity_terms = [("e-tira", ["提拉米"]), ("e-long", ["龙王"])]
    usage = scan_glossary_usage(segments, entity_terms)
    assert set(usage) == {(5, "e-tira"), (5, "e-long")}


# ── record count parse ────────────────────────────────────────────────────────

class _FakeConn:
    def __init__(self, tag):
        self._tag = tag
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return self._tag


@pytest.mark.asyncio
async def test_record_returns_segment_count():
    conn = _FakeConn("INSERT 0 3")
    n = await record_segment_translations(conn, uuid4(), "vi", uuid4())
    assert n == 3
    assert "INSERT INTO segment_translations" in conn.calls[0][0]


@pytest.mark.asyncio
async def test_record_tolerates_non_str_tag():
    # A test mock may return a MagicMock, not a command tag → 0, no crash.
    conn = _FakeConn(object())
    assert await record_segment_translations(conn, uuid4(), "vi", uuid4()) == 0


# ── compute status ────────────────────────────────────────────────────────────

class _FetchConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


@pytest.mark.asyncio
async def test_compute_marks_dirty_and_translated():
    ts = datetime(2026, 6, 15, tzinfo=timezone.utc)
    rows = [
        # seg 0: translated, source unchanged, not stale → clean
        FakeRecord({"segment_index": 0, "start_block_index": 0, "end_block_index": 2,
                    "token_estimate": 100, "current_hash": "h0", "translated_hash": "h0",
                    "translated_at": ts, "is_glossary_stale": False}),
        # seg 1: translated but source changed → dirty
        FakeRecord({"segment_index": 1, "start_block_index": 3, "end_block_index": 5,
                    "token_estimate": 120, "current_hash": "h1-new", "translated_hash": "h1-old",
                    "translated_at": ts, "is_glossary_stale": False}),
        # seg 2: never translated → dirty + not translated
        FakeRecord({"segment_index": 2, "start_block_index": 6, "end_block_index": 6,
                    "token_estimate": 80, "current_hash": "h2", "translated_hash": None,
                    "translated_at": None, "is_glossary_stale": False}),
        # seg 3: translated, source unchanged, but glossary-stale → stale (needs)
        FakeRecord({"segment_index": 3, "start_block_index": 7, "end_block_index": 7,
                    "token_estimate": 60, "current_hash": "h3", "translated_hash": "h3",
                    "translated_at": ts, "is_glossary_stale": True}),
    ]
    out = await compute_segment_status(_FetchConn(rows), uuid4(), "vi")
    assert [s["dirty"] for s in out] == [False, True, True, False]
    assert [s["stale"] for s in out] == [False, False, False, True]
    assert [s["needs"] for s in out] == [False, True, True, True]
    assert [s["translated"] for s in out] == [True, True, False, True]
    assert out[0]["translated_at"] == ts.isoformat()
    assert out[2]["translated_at"] is None
    assert out[1]["start_block_index"] == 3 and out[1]["end_block_index"] == 5


# ── internal endpoint ─────────────────────────────────────────────────────────

def _seg_row(idx, current, translated, stale=False):
    return FakeRecord({"segment_index": idx, "start_block_index": idx, "end_block_index": idx,
                       "token_estimate": 50, "current_hash": current,
                       "translated_hash": translated, "translated_at": None,
                       "is_glossary_stale": stale})


def test_internal_status_endpoint(client, fake_pool):
    fake_pool.fetch.return_value = [_seg_row(0, "h0", "h0"), _seg_row(1, "h1", None)]
    resp = client.get(
        f"/internal/translation/chapters/{uuid4()}/segments/status",
        params={"target_language": "vi"}, headers=TOKEN,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dirty_count"] == 1
    assert len(body["segments"]) == 2
    assert body["segments"][1]["dirty"] is True


def test_internal_status_requires_token(client):
    resp = client.get(
        f"/internal/translation/chapters/{uuid4()}/segments/status",
        params={"target_language": "vi"},
    )
    assert resp.status_code == 401


# ── public endpoint (book grant) ──────────────────────────────────────────────

def test_public_status_endpoint(client, fake_pool):
    fake_pool.fetchval.return_value = uuid4()  # book_for_chapter → a book exists
    fake_pool.fetch.return_value = [_seg_row(0, "h0", "h0"), _seg_row(1, "h1", "STALE")]
    resp = client.get(
        f"/v1/translation/chapters/{uuid4()}/segments/status",
        params={"target_language": "vi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dirty_count"] == 1  # seg 1 source changed
    assert body["segments"][1]["dirty"] is True


# ── finalize hook: _record_segment_status best-effort + fast path ─────────────

class _PoolCM:
    """A pool whose acquire() yields a throwaway conn (the record fn is patched)."""
    def acquire(self):
        class _CM:
            async def __aenter__(s):
                return object()
            async def __aexit__(s, *e):
                return False
        return _CM()


@pytest.mark.asyncio
async def test_record_status_hook_swallows_errors(monkeypatch):
    from app.workers import chapter_worker
    # n==0 (no segments) → ensure runs; ensure raising must NOT propagate.
    async def rec_zero(*a, **k):
        return 0
    async def boom(*a, **k):
        raise RuntimeError("book-service down")
    monkeypatch.setattr("app.workers.segment_status.record_segment_translations", rec_zero)
    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", boom)
    # Must not raise — best-effort telemetry.
    await chapter_worker._record_segment_status(_PoolCM(), uuid4(), uuid4(), "vi", uuid4())


@pytest.mark.asyncio
async def test_record_status_hook_skips_fetch_when_segments_exist(monkeypatch):
    from app.workers import chapter_worker
    # record returns >0 → segments already built → ensure_chapter_segments NOT called
    # (no book-service round-trip on the hot path).
    async def rec_two(*a, **k):
        return 2
    called = {"ensure": 0}
    async def ensure_spy(*a, **k):
        called["ensure"] += 1
        return {}
    monkeypatch.setattr("app.workers.segment_status.record_segment_translations", rec_two)
    monkeypatch.setattr("app.workers.segment_store.ensure_chapter_segments", ensure_spy)
    await chapter_worker._record_segment_status(_PoolCM(), uuid4(), uuid4(), "vi", uuid4())
    assert called["ensure"] == 0


@pytest.mark.asyncio
async def test_record_status_hook_noop_without_language(monkeypatch):
    from app.workers import chapter_worker
    called = {"record": 0}
    async def rec_spy(*a, **k):
        called["record"] += 1
        return 0
    monkeypatch.setattr("app.workers.segment_status.record_segment_translations", rec_spy)
    # empty target_language (legacy text job) → no rows to key on → early return.
    await chapter_worker._record_segment_status(_PoolCM(), uuid4(), uuid4(), "", uuid4())
    assert called["record"] == 0


def test_public_status_no_translations_empty(client, fake_pool):
    fake_pool.fetchval.return_value = None  # no translation rows → no book to gate on
    resp = client.get(
        f"/v1/translation/chapters/{uuid4()}/segments/status",
        params={"target_language": "vi"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "chapter_id": resp.json()["chapter_id"],
        "target_language": "vi",
        "segments": [],
        "dirty_count": 0,
        "needs_count": 0,
    }
