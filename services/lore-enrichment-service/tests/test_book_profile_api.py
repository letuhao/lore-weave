"""Profile-authoring API tests (C3 / slice 0d, T4/T5/T7).

Auth + owner guard + override validation run via fake pool / respx-mocked
book-service (owner), knowledge-service (KG summary), provider-registry (the
suggest LLM stream). No live stack. The DB round-trip is fake-echoed (the real
upsert is integration-covered by the live smoke).
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import book_profile as bp_api
from app.config import settings
from app.deps import get_db

OWNER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")


def _bearer(sub: UUID = OWNER) -> str:
    return pyjwt.encode({"sub": str(sub)}, "x", algorithm="HS256")


# ── fake pools ────────────────────────────────────────────────────────────────

class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _NeutralConn:
    async def fetchrow(self, _sql, *_a):
        return None  # no profile row → neutral default


class _EchoConn:
    """Echoes upsert args back as the RETURNING row (jsonb as str, like asyncpg)."""

    async def fetchrow(self, _sql, *args):
        b, wv, lang, era, voice, markers_json, overrides_json, src = args
        return {
            "book_id": b, "worldview": wv, "language": lang, "era_policy": era,
            "voice": voice, "anachronism_markers": markers_json,
            "dimension_overrides": overrides_json, "profile_source": src,
        }


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


def _app(pool) -> FastAPI:
    app = FastAPI()
    app.include_router(bp_api.router)
    app.dependency_overrides[get_db] = lambda: pool
    return app


def _mock_projection(book: UUID, owner: UUID) -> None:
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(
        200,
        json={
            "book_id": str(book), "owner_user_id": str(owner),
            "title": "Neon Saigon", "original_language": "vi",
            "description": "cyberpunk", "summary_excerpt": "",
            "genre_tags": ["cyberpunk"], "chapter_count": 5,
        },
    )


# ── GET ───────────────────────────────────────────────────────────────────────

def test_get_profile_requires_auth():
    resp = TestClient(_app(_Pool(_NeutralConn()))).get(
        f"/v1/lore-enrichment/books/{uuid4()}/profile"
    )
    assert resp.status_code == 401


@respx.mock
def test_get_profile_non_owner_forbidden():
    book = uuid4()
    _mock_projection(book, owner=uuid4())  # a DIFFERENT owner
    resp = TestClient(_app(_Pool(_NeutralConn()))).get(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 403


@respx.mock
def test_get_profile_owner_unset_returns_neutral():
    book = uuid4()
    _mock_projection(book, owner=OWNER)
    resp = TestClient(_app(_Pool(_NeutralConn()))).get(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "auto"
    assert body["anachronism_enabled"] is False
    assert body["dimension_overrides"] == {}


@respx.mock
def test_get_profile_book_not_found_404():
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(404)
    resp = TestClient(_app(_Pool(_NeutralConn()))).get(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 404


# ── internal (S2S) GET — wiki-llm M1 ────────────────────────────────────────────

class _PopulatedConn:
    """Returns a populated profile row (jsonb columns as str, like asyncpg)."""

    async def fetchrow(self, _sql, *_a):
        return {
            "book_id": _a[0] if _a else None,
            "worldview": "Shang-Zhou xianxia", "language": "zh",
            "era_policy": "no firearms", "voice": "epic",
            "anachronism_markers": json.dumps([{"term": "枪", "reason": "anachronism"}]),
            "dimension_overrides": json.dumps({}),
            "profile_source": "manual",
        }


def _internal_app(pool) -> FastAPI:
    app = FastAPI()
    app.include_router(bp_api.internal_router)
    app.dependency_overrides[get_db] = lambda: pool
    return app


def _internal_url(book: UUID) -> str:
    return f"/internal/lore-enrichment/books/{book}/profile"


def test_internal_get_requires_token():
    # No X-Internal-Token → 401 (no owner/JWT path on the internal route).
    resp = TestClient(_internal_app(_Pool(_NeutralConn()))).get(_internal_url(uuid4()))
    assert resp.status_code == 401


def test_internal_get_wrong_token():
    resp = TestClient(_internal_app(_Pool(_NeutralConn()))).get(
        _internal_url(uuid4()), headers={"X-Internal-Token": "nope"}
    )
    assert resp.status_code == 401


def test_internal_get_unset_returns_neutral():
    resp = TestClient(_internal_app(_Pool(_NeutralConn()))).get(
        _internal_url(uuid4()),
        headers={"X-Internal-Token": settings.internal_service_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "auto"
    assert body["worldview"] == ""
    assert body["anachronism_enabled"] is False


def test_internal_get_populated():
    resp = TestClient(_internal_app(_Pool(_PopulatedConn()))).get(
        _internal_url(uuid4()),
        headers={"X-Internal-Token": settings.internal_service_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["worldview"] == "Shang-Zhou xianxia"
    assert body["language"] == "zh"
    assert body["era_policy"] == "no firearms"
    assert body["voice"] == "epic"
    assert body["anachronism_markers"] == [{"term": "枪", "reason": "anachronism"}]
    assert body["anachronism_enabled"] is True


# ── PUT ───────────────────────────────────────────────────────────────────────

@respx.mock
def test_put_profile_round_trips():
    book = uuid4()
    _mock_projection(book, owner=OWNER)
    resp = TestClient(_app(_Pool(_EchoConn()))).put(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={
            "worldview": "near-future Saigon", "language": "vi",
            "era_policy": "no pre-2040 tech", "voice": "noir",
            "anachronism_markers": [{"term": "马车", "reason": "pre-modern"}],
            "dimension_overrides": {"character": {"add": [{"id": "implants", "label": "Implants"}]}},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "vi" and body["worldview"] == "near-future Saigon"
    assert body["profile_source"] == "manual"
    assert body["anachronism_markers"] == [{"term": "马车", "reason": "pre-modern"}]
    assert body["anachronism_enabled"] is True
    assert body["dimension_overrides"]["character"]["add"][0]["id"] == "implants"


@respx.mock
def test_put_profile_rejects_malformed_overrides():
    book = uuid4()
    _mock_projection(book, owner=OWNER)
    resp = TestClient(_app(_Pool(_EchoConn()))).put(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"dimension_overrides": {"character": {"add": [{"label": "no id"}]}}},
    )
    assert resp.status_code == 400, resp.text


@respx.mock
def test_put_profile_non_owner_forbidden_even_with_bad_body():
    # auth precedes validation: a non-owner gets 403, NOT a 400 about the body.
    book = uuid4()
    _mock_projection(book, owner=uuid4())  # different owner
    resp = TestClient(_app(_Pool(_EchoConn()))).put(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"dimension_overrides": {"character": {"add": [{"label": "no id"}]}}},
    )
    assert resp.status_code == 403, resp.text


def test_put_profile_requires_auth():
    resp = TestClient(_app(_Pool(_EchoConn()))).put(
        f"/v1/lore-enrichment/books/{uuid4()}/profile", json={"worldview": "x"}
    )
    assert resp.status_code == 401


@respx.mock
def test_put_profile_full_replace_clears_omitted_markers():
    # CONTRACT pin (review #3): PUT is a FULL REPLACE — omitting anachronism_markers
    # resets them to [] (anachronism OFF). The FE (0e) must GET-then-PUT to avoid
    # wiping the seeded markers.
    book = uuid4()
    _mock_projection(book, owner=OWNER)
    resp = TestClient(_app(_Pool(_EchoConn()))).put(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"worldview": "only this set"},  # no markers, no overrides
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["anachronism_markers"] == []
    assert body["anachronism_enabled"] is False
    assert body["dimension_overrides"] == {}


@respx.mock
def test_get_profile_projection_missing_owner_forbidden():
    # a projection with no owner_user_id must NOT authorize (owner is None → 403),
    # never crash.
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(
        200, json={"book_id": str(book), "title": "x"}  # no owner_user_id
    )
    resp = TestClient(_app(_Pool(_NeutralConn()))).get(
        f"/v1/lore-enrichment/books/{book}/profile",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 403


# ── POST suggest (Phase 3 M2 — async) ─────────────────────────────────────────
# The endpoint now: owner-check on the request path (a non-owner never creates a
# task), then create a 'pending' compose task + enqueue a resume-stream trigger,
# return 202 + task_id. The LLM pipeline runs in the worker (compute_profile_suggest)
# — its respx-mocked coverage lives in test_compose_task.py.

def _patch_task(monkeypatch, *, task_id="11111111-1111-7111-8111-111111111111",
                enqueued=True):
    created: dict = {}

    async def _create(pool, *, kind, user_id, project_id, book_id, request):
        created.update(kind=kind, user_id=user_id, project_id=project_id,
                       book_id=book_id, request=request)
        return task_id

    async def _enqueue(*, task_id, kind, user_id, project_id):
        created["enqueued_kind"] = kind
        return enqueued

    monkeypatch.setattr(bp_api, "create_compose_task", _create)
    monkeypatch.setattr(bp_api, "enqueue_compose_task", _enqueue)
    return created


@respx.mock
def test_suggest_202_creates_task(monkeypatch):
    book, ch, proj = uuid4(), uuid4(), uuid4()
    _mock_projection(book, owner=OWNER)
    created = _patch_task(monkeypatch)
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(proj), "suggest_model_ref": str(uuid4()),
              "sample_chapter_ids": [str(ch)]},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["task_id"] == "11111111-1111-7111-8111-111111111111"
    assert body["status"] == "pending"
    assert created["kind"] == "profile_suggest"
    assert created["book_id"] == str(book)
    assert created["request"]["sample_chapter_ids"] == [str(ch)]
    assert created["request"]["user_id"] == str(OWNER)
    assert created["enqueued_kind"] == "profile_suggest"


@respx.mock
def test_suggest_non_owner_403(monkeypatch):
    book = uuid4()
    _mock_projection(book, owner=uuid4())  # a DIFFERENT owner
    created = _patch_task(monkeypatch)
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4())},
    )
    assert resp.status_code == 403
    assert created == {}  # owner-check precedes task creation → nothing created


def test_suggest_requires_auth():
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{uuid4()}/profile/suggest",
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4())},
    )
    assert resp.status_code == 401
