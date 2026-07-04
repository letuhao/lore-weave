"""D2 — corpus-register/ingest/list endpoint tests (no live stack).

Auth + kind-validation guards run before any DB access; _corpus_view is pure.
The full register→ingest→list round-trip is live-verified (real embed) — the
store methods are integration-covered there.
"""

from __future__ import annotations

from uuid import uuid4

import jwt as pyjwt
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sources as sources_api
from app.api.sources import _corpus_view
from app.config import settings
from app.deps import get_db

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


def test_corpus_view_parses_jsonb_string_and_shapes():
    # asyncpg may hand back provenance_json as a JSON string — _corpus_view must
    # parse it and expose chunk_count only when present.
    row = {
        "corpus_id": uuid4(), "name": "山海经", "kind": "shanhaijing",
        "license": "public-domain", "provenance_json": '{"src":"demo"}',
        "created_at": None, "chunk_count": 7,
    }
    v = _corpus_view(row)
    assert v["provenance_json"] == {"src": "demo"}
    assert v["kind"] == "shanhaijing" and v["license"] == "public-domain"
    assert v["chunk_count"] == 7


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sources_api.router)
    # get_db is reached only AFTER the auth/kind guards; a stub keeps wiring valid.
    app.dependency_overrides[get_db] = lambda: object()
    return app


def _bearer() -> str:
    return pyjwt.encode({"sub": OWNER, "exp": 4102444800}, "test_jwt_secret", algorithm="HS256")


def test_create_source_requires_auth():
    resp = TestClient(_app()).post(
        "/v1/lore-enrichment/sources",
        json={"project_id": str(uuid4()), "name": "x", "kind": "shanhaijing"},
    )
    assert resp.status_code == 401


# ── de-bias C2 T6: chapter-selection grounding ingest ───────────────────────

def _app_books() -> FastAPI:
    app = FastAPI()
    app.include_router(sources_api.books_router)
    app.dependency_overrides[get_db] = lambda: object()
    return app


def test_ground_from_book_requires_auth():
    resp = TestClient(_app_books()).post(
        f"/v1/lore-enrichment/books/{uuid4()}/ground",
        json={"project_id": str(uuid4()), "embedding_model_ref": str(uuid4()),
              "chapter_ids": [str(uuid4())]},
    )
    assert resp.status_code == 401


def test_ground_from_book_empty_selection_422():
    # chapter_ids min 1 — pydantic rejects an empty selection.
    resp = TestClient(_app_books()).post(
        f"/v1/lore-enrichment/books/{uuid4()}/ground",
        json={"project_id": str(uuid4()), "embedding_model_ref": str(uuid4()),
              "chapter_ids": []},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 422


@respx.mock
def test_ground_from_book_no_chapter_text_400():
    # selected chapters with no draft text → 400 BEFORE any ingest (no DB needed).
    book, ch = uuid4(), uuid4()
    respx.get(
        f"{settings.book_service_url}/internal/books/{book}/chapters/{ch}/draft-text"
    ).respond(200, json={"text": ""})
    resp = TestClient(_app_books()).post(
        f"/v1/lore-enrichment/books/{book}/ground",
        json={"project_id": str(uuid4()), "embedding_model_ref": str(uuid4()),
              "chapter_ids": [str(ch)]},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 400, resp.text


def test_create_source_rejects_bad_kind():
    resp = TestClient(_app()).post(
        "/v1/lore-enrichment/sources",
        json={"project_id": str(uuid4()), "name": "x", "kind": "not-a-kind"},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 400


def test_ingest_requires_auth():
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/sources/{uuid4()}/ingest",
        json={"project_id": str(uuid4()), "text": "蓬萊", "embedding_model_ref": str(uuid4())},
    )
    assert resp.status_code == 401
