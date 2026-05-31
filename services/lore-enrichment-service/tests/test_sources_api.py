"""D2 — corpus-register/ingest/list endpoint tests (no live stack).

Auth + kind-validation guards run before any DB access; _corpus_view is pure.
The full register→ingest→list round-trip is live-verified (real embed) — the
store methods are integration-covered there.
"""

from __future__ import annotations

from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sources as sources_api
from app.api.sources import _corpus_view
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
    return pyjwt.encode({"sub": OWNER}, "x", algorithm="HS256")


def test_create_source_requires_auth():
    resp = TestClient(_app()).post(
        "/v1/lore-enrichment/sources",
        json={"project_id": str(uuid4()), "name": "x", "kind": "shanhaijing"},
    )
    assert resp.status_code == 401


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
