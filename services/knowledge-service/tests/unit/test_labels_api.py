"""KG-ML M5 (C5) — predicate-labels endpoint tests."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: uuid4()
    return TestClient(app, raise_server_exceptions=False)


def test_predicate_labels_catalog_vi():
    resp = _client().get("/v1/knowledge/predicate-labels?language=vi")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "vi"
    assert body["labels"]["ALLY_OF"] == "đồng minh của"


def test_predicate_labels_resolve_codes_with_fallback():
    # one curated + one open-vocab predicate → curated label + humanized fallback
    resp = _client().get(
        "/v1/knowledge/predicate-labels?language=vi&codes=ALLY_OF,SECRETLY_FUNDS"
    )
    assert resp.status_code == 200
    labels = resp.json()["labels"]
    assert labels == {"ALLY_OF": "đồng minh của", "SECRETLY_FUNDS": "secretly funds"}


def test_predicate_labels_default_language_humanized():
    resp = _client().get("/v1/knowledge/predicate-labels?codes=KILLED")
    assert resp.status_code == 200
    assert resp.json()["labels"] == {"KILLED": "killed"}


def test_predicate_labels_requires_auth():
    from app.main import app
    # no get_current_user override → real dependency rejects the anonymous call
    resp = TestClient(app, raise_server_exceptions=False).get(
        "/v1/knowledge/predicate-labels?language=vi"
    )
    assert resp.status_code in (401, 403)
