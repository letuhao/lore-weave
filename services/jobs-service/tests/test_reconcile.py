"""Reconcile sweep (H1 backstop) — fetch → JobEvent → monotonic upsert, tolerant."""

from unittest.mock import AsyncMock

import pytest

from app import reconcile

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

    monkeypatch.setattr(reconcile.httpx, "AsyncClient", _Client)


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
async def test_fetch_sends_since_and_internal_token(monkeypatch):
    cap = {}
    _patch_client(monkeypatch, body={"jobs": []}, captured=cap)
    monkeypatch.setattr(reconcile.store, "upsert_job_event", AsyncMock(return_value=True))
    await reconcile.ReconcileSweeper(pool=object()).sweep_once()
    assert cap["url"].endswith("/internal/composition/jobs")
    assert "since" in cap["params"]
    assert "X-Internal-Token" in cap["headers"]


@pytest.mark.asyncio
async def test_source_error_is_tolerated(monkeypatch):
    _patch_client(monkeypatch, raise_exc=reconcile.httpx.ConnectError("down"))
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


def test_all_five_owning_services_are_reconcile_sources():
    # P3-reconcile B: every owning service exposes a GET /internal/{svc}/jobs?since= source.
    assert _REGISTERED_SOURCES == {
        "knowledge", "composition", "video_gen", "lore_enrichment", "translation"
    }


@pytest.mark.asyncio
async def test_run_noops_when_disabled(monkeypatch):
    # reconcile_enabled defaults False in the test env → run() returns immediately.
    monkeypatch.setattr(reconcile.settings, "reconcile_enabled", False)
    await reconcile.ReconcileSweeper(pool=object()).run()  # returns without looping
