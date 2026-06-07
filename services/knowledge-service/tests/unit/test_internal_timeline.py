"""M4d-1 — Unit tests for the internal timeline endpoint.

POST /internal/knowledge/timeline — the translation memo's read path. The DB
layer (pg knowledge_projects lookup + neo4j list_events_filtered) is mocked so
these run hermetically; the real query is covered by the live-smoke.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.routers import internal_timeline as mod
from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE

_TOKEN = "default_test_token"  # conftest INTERNAL_SERVICE_TOKEN default
_BOOK = str(uuid4())


# ── fakes for the pg pool + neo4j session ─────────────────────────────────────

class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, row):
        self._row = row

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._row))


class _FakeNeo4jSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def _patch_db(monkeypatch, *, project_row, events=None, total=0):
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _FakePool(project_row))
    monkeypatch.setattr(mod, "neo4j_session", lambda: _FakeNeo4jSession())
    list_mock = AsyncMock(return_value=(events or [], total))
    monkeypatch.setattr(mod, "list_events_filtered", list_mock)
    return list_mock


def _client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _post(client, body, *, token=_TOKEN):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return client.post("/internal/knowledge/timeline", json=body, headers=headers)


def _event(title, summary=None, date=None, participants=None):
    return SimpleNamespace(
        title=title, summary=summary, event_date_iso=date,
        participants=participants or [],
    )


# ── auth ──────────────────────────────────────────────────────────────────────

def test_requires_internal_token():
    resp = _post(_client(), {"book_id": _BOOK, "chapter_order": 3}, token=None)
    assert resp.status_code == 401


# ── cold start ────────────────────────────────────────────────────────────────

def test_cold_start_no_project(monkeypatch):
    list_mock = _patch_db(monkeypatch, project_row=None)
    resp = _post(_client(), {"book_id": _BOOK, "chapter_order": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is False and body["events"] == []
    list_mock.assert_not_awaited()  # no neo4j query when there's no project


def test_chapter_zero_returns_empty_without_query(monkeypatch):
    row = {"project_id": uuid4(), "user_id": uuid4()}
    list_mock = _patch_db(monkeypatch, project_row=row)
    resp = _post(_client(), {"book_id": _BOOK, "chapter_order": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True and body["events"] == []
    list_mock.assert_not_awaited()  # nothing precedes chapter 0


# ── happy path + reading-position window ──────────────────────────────────────

def test_maps_events_and_applies_reading_window(monkeypatch):
    row = {"project_id": uuid4(), "user_id": uuid4()}
    events = [
        _event("The pact", "Two houses allied.", "Y1", ["Tirami", "Aldric"]),
        _event("The betrayal"),
    ]
    list_mock = _patch_db(monkeypatch, project_row=row, events=events, total=2)

    resp = _post(_client(), {"book_id": _BOOK, "chapter_order": 10, "limit": 25})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True and body["count"] == 2 and body["total"] == 2
    assert body["events"][0] == {
        "title": "The pact", "summary": "Two houses allied.",
        "event_date": "Y1", "participants": ["Tirami", "Aldric"],
    }
    assert body["events"][1]["title"] == "The betrayal"

    # before_order = chapter_index × stride (events strictly before this chapter);
    # window: after_order = (chapter_index − 8) × stride.
    kwargs = list_mock.await_args.kwargs
    assert kwargs["before_order"] == 10 * EVENT_ORDER_CHAPTER_STRIDE
    assert kwargs["after_order"] == (10 - 8) * EVENT_ORDER_CHAPTER_STRIDE


def test_no_window_floor_within_first_chapters(monkeypatch):
    """chapter_index ≤ window ⇒ after_order None (include everything from start)."""
    row = {"project_id": uuid4(), "user_id": uuid4()}
    list_mock = _patch_db(monkeypatch, project_row=row, events=[], total=0)
    _post(_client(), {"book_id": _BOOK, "chapter_order": 4})
    kwargs = list_mock.await_args.kwargs
    assert kwargs["after_order"] is None
    assert kwargs["before_order"] == 4 * EVENT_ORDER_CHAPTER_STRIDE


def test_negative_chapter_index_rejected():
    resp = _post(_client(), {"book_id": _BOOK, "chapter_order": -1})
    assert resp.status_code == 422  # pydantic ge=0
