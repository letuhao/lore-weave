"""Unit test for the wiki-gen cost-config endpoint (D-WIKI-P2B-COST-ESTIMATE).

GET /internal/knowledge/wiki/gen-config — returns the flat per-article cost the FE
multiplies by N for its pre-flight estimate. Pure settings read; no repo/pool.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware.internal_auth import require_internal_token
from app.routers import internal_wiki


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(internal_wiki.router)
    app.dependency_overrides[require_internal_token] = lambda: None
    return TestClient(app)


def test_gen_config_returns_configured_per_article_cost():
    resp = _client().get("/internal/knowledge/wiki/gen-config")
    assert resp.status_code == 200
    got = Decimal(str(resp.json()["cost_per_article_usd"]))
    assert got == Decimal(str(settings.wiki_gen_cost_per_article_usd))


def test_gen_config_requires_internal_token():
    # Without the dependency override the real guard runs → 401/403 (no token).
    app = FastAPI()
    app.include_router(internal_wiki.router)
    resp = TestClient(app).get("/internal/knowledge/wiki/gen-config")
    assert resp.status_code in (401, 403)
