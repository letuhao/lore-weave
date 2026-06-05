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


@respx.mock
def test_suggest_auto_samples_when_no_chapter_ids():
    # no sample_chapter_ids → endpoint lists chapters then fetches their text.
    book, c1 = uuid4(), uuid4()
    _mock_projection(book, owner=OWNER)
    respx.get(f"{settings.book_service_url}/internal/books/{book}/chapters").respond(
        200, json={"items": [{"chapter_id": str(c1), "title": "第一回", "sort_order": 1,
                              "original_language": "zh", "word_count_estimate": 50}],
                   "total": 1, "limit": 3, "offset": 0},
    )
    _mock_chapter_text(book, c1, "第一回 正文…")
    respx.post(f"{settings.knowledge_service_url}/internal/context/build").respond(
        200, json={"mode": "empty", "context": "", "token_count": 0}
    )
    _mock_llm_stream('{"worldview": "auto-sampled", "language": "zh"}')
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4())},  # no ids
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["worldview"] == "auto-sampled"


# ── POST suggest ────────────────────────────────────────────────────────────

def _mock_chapter_text(book: UUID, chapter: UUID, text: str) -> None:
    respx.get(
        f"{settings.book_service_url}/internal/books/{book}/chapters/{chapter}/draft-text"
    ).respond(200, json={"text": text})


def _mock_llm_stream(profile_json: str) -> None:
    sse = (
        "event: token\n"
        f"data: {json.dumps({'delta': profile_json})}\n\n"
        "event: done\ndata: {}\n\n"
    )
    respx.post(f"{settings.provider_registry_internal_url}/internal/llm/stream").respond(
        200, text=sse
    )


@respx.mock
def test_suggest_returns_draft():
    book, ch = uuid4(), uuid4()
    _mock_projection(book, owner=OWNER)
    _mock_chapter_text(book, ch, "Chương 1: thành phố neon…")
    # KG summary best-effort
    respx.post(f"{settings.knowledge_service_url}/internal/context/build").respond(
        200, json={"mode": "full", "context": "<passages>…</passages>", "token_count": 3}
    )
    _mock_llm_stream(
        '{"worldview": "near-future cyberpunk Saigon", "language": "vi", '
        '"dimension_overrides": {"character": {"add": [{"id": "implants", "label": "Cyberware"}]}}}'
    )
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4()),
              "sample_chapter_ids": [str(ch)]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["worldview"] == "near-future cyberpunk Saigon"
    assert body["language"] == "vi"
    assert body["profile_source"] == "ai_suggested"
    assert body["dimension_overrides"]["character"]["add"][0]["id"] == "implants"


@respx.mock
def test_suggest_degrades_when_kg_down():
    book, ch = uuid4(), uuid4()
    _mock_projection(book, owner=OWNER)
    _mock_chapter_text(book, ch, "Chương 1…")
    respx.post(f"{settings.knowledge_service_url}/internal/context/build").respond(503)
    _mock_llm_stream('{"worldview": "w", "language": "vi"}')
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4()),
              "sample_chapter_ids": [str(ch)]},
    )
    assert resp.status_code == 200, resp.text  # KG down → book-only, still works
    assert resp.json()["worldview"] == "w"


@respx.mock
def test_suggest_llm_failure_502():
    book, ch = uuid4(), uuid4()
    _mock_projection(book, owner=OWNER)
    _mock_chapter_text(book, ch, "Chương 1…")
    respx.post(f"{settings.knowledge_service_url}/internal/context/build").respond(
        200, json={"mode": "empty", "context": "", "token_count": 0}
    )
    respx.post(f"{settings.provider_registry_internal_url}/internal/llm/stream").respond(500)
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{book}/profile/suggest",
        headers={"Authorization": f"Bearer {_bearer()}"},
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4()),
              "sample_chapter_ids": [str(ch)]},
    )
    assert resp.status_code == 502, resp.text


def test_suggest_requires_auth():
    resp = TestClient(_app(object())).post(
        f"/v1/lore-enrichment/books/{uuid4()}/profile/suggest",
        json={"project_id": str(uuid4()), "suggest_model_ref": str(uuid4())},
    )
    assert resp.status_code == 401
