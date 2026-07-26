"""Reconcile sweep (H1 backstop) — fetch → JobEvent → monotonic upsert, tolerant."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app import reconcile
from app.projection.store import _ts

# Captured at import, BEFORE the autouse fixture pins it to one source.
_REGISTERED_SOURCES = set(reconcile._RECONCILE)

PAYLOAD = {
    "service": "composition", "job_id": "22222222-2222-2222-2222-222222222222",
    "owner_user_id": "33333333-3333-3333-3333-333333333333", "kind": "generate",
    "status": "running", "parent_job_id": None, "detail_status": None, "progress": None,
    "title": None, "error": None, "occurred_at": "2026-06-15T00:00:00+00:00",
}


@pytest.fixture(autouse=True)
def _single_source(monkeypatch):
    """Pin the registry to ONE source so the sweep-mechanics assertions are
    deterministic regardless of how many real sources ship (B registers 5)."""
    monkeypatch.setattr(
        reconcile, "_RECONCILE",
        {"composition": ("http://composition-service:8093", "/internal/composition/jobs")},
    )


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _patch_client(monkeypatch, *, body=None, captured=None, raise_exc=None):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            if captured is not None:
                captured.update(url=url, params=params, headers=headers)
            if raise_exc:
                raise raise_exc
            return _Resp(body)

    # P3 SDK-first (W5): reconcile builds its client via build_internal_client
    # (token baked). Patch the factory to return the fake client + capture the
    # factory kwargs so tests can still assert the internal token was supplied.
    def _factory(*a, **k):
        if captured is not None:
            captured.update(factory_kwargs=k)
        return _Client()

    monkeypatch.setattr(reconcile, "build_internal_client", _factory)


@pytest.mark.asyncio
async def test_sweep_once_upserts_and_advances_watermark(monkeypatch):
    _patch_client(monkeypatch, body={"jobs": [PAYLOAD]})
    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(reconcile.store, "upsert_job_event", spy)
    sweeper = reconcile.ReconcileSweeper(pool=object())
    before = sweeper._watermark["composition"]

    res = await sweeper.sweep_once()

    assert res == {"composition": 1}
    spy.assert_awaited_once()
    ev = spy.await_args.args[1]
    assert ev.service == "composition" and ev.status.value == "running"
    assert sweeper._watermark["composition"] > before  # advanced to sweep_start


@pytest.mark.asyncio
async def test_fetch_sends_since_limit_and_internal_token(monkeypatch):
    cap = {}
    _patch_client(monkeypatch, body={"jobs": []}, captured=cap)
    monkeypatch.setattr(reconcile.store, "upsert_job_event", AsyncMock(return_value=True))
    await reconcile.ReconcileSweeper(pool=object()).sweep_once()
    assert cap["url"].endswith("/internal/composition/jobs")
    assert "since" in cap["params"]
    assert cap["params"]["limit"] == reconcile._PAGE_LIMIT  # shared page-cap contract
    assert cap["factory_kwargs"]["internal_token"]  # token baked into the client via the factory


@pytest.mark.asyncio
async def test_partial_page_advances_to_now(monkeypatch):
    """A partial page = caught up → watermark jumps to ~now (bounds the next window)."""
    _patch_client(monkeypatch, body={"jobs": [PAYLOAD]})  # 1 row, _PAGE_LIMIT=1000 → partial
    monkeypatch.setattr(reconcile.store, "upsert_job_event", AsyncMock(return_value=True))
    sweeper = reconcile.ReconcileSweeper(pool=object())
    await sweeper.sweep_once()
    # advanced well past the single row's old occurred_at (2026-06-15) → ~now
    assert sweeper._watermark["composition"].year >= 2026
    assert sweeper._watermark["composition"] > _ts(PAYLOAD["occurred_at"])


@pytest.mark.asyncio
async def test_full_page_advances_to_last_row_not_now(monkeypatch):
    """A FULL page (len >= _PAGE_LIMIT) means overflow may exist → the watermark must
    advance ONLY to the last row's timestamp, never jump to now (which would skip the
    unfetched overflow). Regression guard for the review-impl #1 finding."""
    monkeypatch.setattr(reconcile, "_PAGE_LIMIT", 2)
    last_ts = "2026-06-15T12:00:00+00:00"
    rows = [
        {**PAYLOAD, "job_id": "11111111-1111-1111-1111-111111111111",
         "occurred_at": "2026-06-15T11:00:00+00:00"},
        {**PAYLOAD, "job_id": "22222222-2222-2222-2222-222222222222", "occurred_at": last_ts},
    ]
    _patch_client(monkeypatch, body={"jobs": rows})
    monkeypatch.setattr(reconcile.store, "upsert_job_event", AsyncMock(return_value=True))
    sweeper = reconcile.ReconcileSweeper(pool=object())
    # Seed an older watermark so the page rows are genuinely newer than `since` (as a real
    # source only returns rows >= since); the full-page branch then advances to last_ts.
    sweeper._watermark["composition"] = _ts("2026-06-15T10:00:00+00:00")
    await sweeper.sweep_once()
    assert sweeper._watermark["composition"] == _ts(last_ts)  # last row, NOT now()


@pytest.mark.asyncio
async def test_source_error_is_tolerated(monkeypatch):
    _patch_client(monkeypatch, raise_exc=httpx.ConnectError("down"))
    monkeypatch.setattr(reconcile.store, "upsert_job_event", AsyncMock(return_value=True))
    sweeper = reconcile.ReconcileSweeper(pool=object())
    res = await sweeper.sweep_once()  # must NOT raise
    assert res == {"composition": 0}


@pytest.mark.asyncio
async def test_unparseable_row_skipped(monkeypatch):
    _patch_client(monkeypatch, body={"jobs": [{"bad": "row"}, PAYLOAD]})
    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(reconcile.store, "upsert_job_event", spy)
    res = await reconcile.ReconcileSweeper(pool=object()).sweep_once()
    assert res == {"composition": 1}  # the good row applied, the bad one skipped
    spy.assert_awaited_once()


def test_all_owning_services_are_reconcile_sources():
    # P3-reconcile B: every owning service exposes a GET /internal/{svc}/jobs?since= source.
    # `book` added by the producer-emit backfill (Slice D — D-JOBS-BOOK-IMPORT-UNWIRED).
    assert _REGISTERED_SOURCES == {
        "knowledge", "composition", "video_gen", "lore_enrichment", "translation", "book"
    }


@pytest.mark.asyncio
async def test_run_noops_when_disabled(monkeypatch):
    # reconcile_enabled defaults False in the test env → run() returns immediately.
    monkeypatch.setattr(reconcile.settings, "reconcile_enabled", False)
    await reconcile.ReconcileSweeper(pool=object()).run()  # returns without looping
