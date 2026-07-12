"""Unit tests for the internal KG-state probe.

GET /internal/books/{book_id}/kg-state — the per-chat-turn "does this book have
a knowledge graph, and how big is it?" read. The pg layer (the single
knowledge_projects row lookup) is mocked so these run hermetically; the real
query + its index are covered by the live-smoke.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.routers import internal_kg_state as mod

_TOKEN = "default_test_token"  # conftest INTERNAL_SERVICE_TOKEN default
_BOOK = str(uuid4())


# ── fake pg pool ──────────────────────────────────────────────────────────────

class _FakePool:
    """Pool-level ``fetchrow`` (the shape internal_canon uses). Records the args
    so a test can assert the book_id was actually bound to the query."""

    def __init__(self, row):
        self._row = row
        self.calls: list[tuple] = []

    async def fetchrow(self, *args):
        self.calls.append(args)
        return self._row


def _patch_pool(monkeypatch, row):
    pool = _FakePool(row)
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: pool)
    return pool


def _client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _get(client, book_id=_BOOK, *, token=_TOKEN):
    headers = {"X-Internal-Token": token} if token is not None else {}
    return client.get(f"/internal/books/{book_id}/kg-state", headers=headers)


def _row(project_id, *, entities=0, facts=0, events=0, status="ready"):
    return {
        "project_id": project_id,
        "extraction_status": status,
        "entity_count": entities,
        "fact_count": facts,
        "event_count": events,
    }


# ── auth ──────────────────────────────────────────────────────────────────────

def test_requires_internal_token():
    resp = _get(_client(), token=None)
    assert resp.status_code == 401


def test_rejects_wrong_internal_token(monkeypatch):
    _patch_pool(monkeypatch, None)
    resp = _get(_client(), token="not-the-token")
    assert resp.status_code == 401


# ── (a) a book WITH a projection returns the cached counts ────────────────────

def test_book_with_projection_returns_counts(monkeypatch):
    project_id = uuid4()
    pool = _patch_pool(
        monkeypatch,
        _row(project_id, entities=42, facts=117, events=9, status="ready"),
    )

    resp = _get(_client())
    assert resp.status_code == 200
    assert resp.json() == {
        "book_id": _BOOK,
        "has_projection": True,
        "project_id": str(project_id),
        "entity_count": 42,
        "fact_count": 117,
        "event_count": 9,
        "extraction_status": "ready",
    }

    # The book_id must actually reach the query (UUID-typed for asyncpg).
    assert pool.calls and str(pool.calls[0][1]) == _BOOK


def test_extraction_status_is_passed_through(monkeypatch):
    """A projection still building is a real projection — the caller decides what
    to do with the status; the route does not filter on it."""
    _patch_pool(monkeypatch, _row(uuid4(), entities=3, status="building"))
    body = _get(_client()).json()
    assert body["has_projection"] is True
    assert body["extraction_status"] == "building"
    assert body["entity_count"] == 3


# ── (b) a book with NO project ⇒ has_projection=false + 200 (NOT 404) ─────────

def test_book_without_project_returns_200_not_404(monkeypatch):
    _patch_pool(monkeypatch, None)

    resp = _get(_client())
    assert resp.status_code == 200, "cold start is an expected answer, not an error"
    assert resp.json() == {
        "book_id": _BOOK,
        "has_projection": False,
        "project_id": None,
        "entity_count": None,
        "fact_count": None,
        "event_count": None,
        "extraction_status": None,
    }


# ── (c) NULL stat_* columns coalesce to 0 (never crash) ───────────────────────

def test_null_stat_columns_read_as_UNKNOWN_not_zero(monkeypatch):
    """A project whose stats job has not run. The counters read as None (UNKNOWN), NOT 0 —
    reporting an uncomputed cache as "0 connections" deadlocked the flagship rail, whose
    connect-people step is done_when connections>0. UNKNOWN lets the consumer fall back."""
    project_id = uuid4()
    _patch_pool(
        monkeypatch,
        _row(project_id, entities=None, facts=None, events=None, status=None),
    )

    resp = _get(_client())
    assert resp.status_code == 200
    assert resp.json() == {
        "book_id": _BOOK,
        "has_projection": True,  # the project exists — its counters are just uncomputed
        "project_id": str(project_id),
        "entity_count": None,
        "fact_count": None,
        "event_count": None,
        "extraction_status": None,
    }


def test_zero_counts_are_preserved_not_treated_as_missing(monkeypatch):
    """Guard against an `or 0` style zero-fill: a genuine 0 and a NULL both read
    as 0, but an empty-but-real projection must still report has_projection=True."""
    _patch_pool(monkeypatch, _row(uuid4(), entities=0, facts=0, events=0))
    body = _get(_client()).json()
    assert body["has_projection"] is True
    assert body["entity_count"] == 0


# ── input validation ──────────────────────────────────────────────────────────

def test_non_uuid_book_id_rejected(monkeypatch):
    _patch_pool(monkeypatch, None)
    resp = _get(_client(), book_id="not-a-uuid")
    assert resp.status_code == 422
