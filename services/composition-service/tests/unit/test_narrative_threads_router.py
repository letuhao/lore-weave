"""FD-1 S4a — narrative-threads read router (the promise-ledger debt surface)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

USER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()


def _thread(summary: str, kind: str = "promise", status: str = "open"):
    from app.db.models import NarrativeThread
    return NarrativeThread(
        id=uuid4(), created_by=USER, project_id=PROJECT, kind=kind, status=status, summary=summary,
    )


class _Works:
    def __init__(self, exists=True):
        self.exists = exists

    async def get(self, project_id):
        # non-None carries a book_id for the E0 gate; None → uniform 404.
        return SimpleNamespace(book_id=BOOK) if self.exists else None


class _Threads:
    def __init__(self, open_threads=None, all_threads=None, open_count=None):
        self._open = open_threads or []
        self._all = all_threads if all_threads is not None else list(self._open)
        # count_open is a SEPARATE source (a true COUNT) — defaults to len(open)
        # but a test can set it distinct to prove the route uses count_open, not len.
        self._count = open_count if open_count is not None else len(self._open)

    async def list_open(self, project_id, *, limit=100):
        return self._open

    async def list_for_project(self, project_id):
        return self._all

    async def count_open(self, project_id):
        return self._count


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_grant_client_dep, get_narrative_thread_repo, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; the route resolves the Work's book
    # then gates VIEW (deny paths in test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    state = {"works": _Works(), "threads": _Threads()}
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: state["works"]
    app.dependency_overrides[get_narrative_thread_repo] = lambda: state["threads"]
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


def _url(status="open"):
    return f"/v1/composition/works/{PROJECT}/narrative-threads?status={status}"


def test_list_open_returns_unpaid_debt(client):
    c, state = client
    state["threads"] = _Threads(open_threads=[_thread("A"), _thread("B")])
    r = c.get(_url("open"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["threads"]) == 2 and body["open_count"] == 2


def test_status_all_returns_full_ledger_but_open_count_is_open(client):
    c, state = client
    open_t = [_thread("still open")]
    allt = open_t + [_thread("done", status="paid")]
    state["threads"] = _Threads(open_threads=open_t, all_threads=allt)
    r = c.get(_url("all"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["threads"]) == 2          # full ledger
    assert body["open_count"] == 1            # debt = open only, regardless of filter


def test_empty_ledger_zero_debt(client):
    c, _ = client
    r = c.get(_url("open"))
    assert r.status_code == 200 and r.json()["open_count"] == 0


def test_404_when_work_missing(client):
    c, state = client
    state["works"] = _Works(exists=False)
    r = c.get(_url("open"))
    assert r.status_code == 404


def test_bad_status_value_422(client):
    c, _ = client
    r = c.get(_url("garbage"))
    assert r.status_code == 422


def test_open_count_uses_count_open_not_list_len(client):
    # review-impl MED#1 regression: open_count is a TRUE count (count_open), not
    # len(list_open) which caps at the query LIMIT. Stub a count distinct from the
    # returned list length to prove the route reads count_open.
    c, state = client
    state["threads"] = _Threads(open_threads=[_thread("only one returned")], open_count=150)
    r = c.get(_url("open"))
    assert r.status_code == 200
    body = r.json()
    assert len(body["threads"]) == 1 and body["open_count"] == 150


@pytest.mark.asyncio
async def test_open_promise_count_helper_gate(monkeypatch):
    """review-impl LOW#3 — the chapter-result debt flag helper: gate off → None
    (no read); gate on → count_open; repo error → None (best-effort)."""
    from app.routers import engine as engine_mod

    class _R:
        def __init__(self, n=None, boom=False):
            self.n, self.boom = n, boom
            self.called = 0

        async def count_open(self, project_id):
            self.called += 1
            if self.boom:
                raise RuntimeError("boom")
            return self.n

    off = _R(n=3)
    assert await engine_mod._open_promise_count(
        SimpleNamespace(settings={}), repo=off, project_id=PROJECT) is None
    assert off.called == 0  # gate off → no read

    on = _R(n=3)
    assert await engine_mod._open_promise_count(
        SimpleNamespace(settings={"narrative_thread_enabled": True}),
        repo=on, project_id=PROJECT) == 3

    err = _R(boom=True)
    assert await engine_mod._open_promise_count(
        SimpleNamespace(settings={"narrative_thread_enabled": True}),
        repo=err, project_id=PROJECT) is None  # swallowed
