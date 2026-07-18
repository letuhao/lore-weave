"""S-09 W2 — POST /projects/{id}/entities/from-glossary (glossary→graph projection).

The projection engine + Neo4j session are stubbed; this asserts the route's gating,
argument threading (owner/book/subset), serialization of the ProjectionResult counts,
and the book-less-project 400. The engine's own behaviour is covered in anchor_loader tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.grant_deps import project_meta_dep
from app.deps import get_glossary_client, get_grant_client, get_projects_repo
from app.extraction.anchor_loader import ProjectionResult
from app.middleware.jwt_auth import get_current_user
from app.routers.public.entities import entities_router

_PROJ = "11111111-1111-1111-1111-111111111111"


class _AsyncCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def _build(monkeypatch, *, book):
    owner = uuid4()
    monkeypatch.setattr("app.routers.public.entities.neo4j_session", lambda: _AsyncCM())

    seen: dict = {}

    async def fake_project(session, glossary, *, user_id, project_id, book_id, entity_ids=None):
        seen.update(user_id=user_id, project_id=project_id, book_id=book_id, entity_ids=entity_ids)
        return ProjectionResult(created=3, existing=1, seen=5, skipped=0, truncated=False, conflicted=2)

    monkeypatch.setattr(
        "app.routers.public.entities.project_glossary_entities_to_nodes", fake_project)

    async def fake_reconcile(*a, **k):
        return None
    monkeypatch.setattr("app.jobs.stats_updater.reconcile_project_stats", fake_reconcile)

    app = FastAPI()
    app.include_router(entities_router)
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[project_meta_dep] = lambda: (owner, book)  # owner==caller → authorized
    app.dependency_overrides[get_grant_client] = lambda: object()
    app.dependency_overrides[get_glossary_client] = lambda: object()
    app.dependency_overrides[get_projects_repo] = lambda: SimpleNamespace(_pool=object())
    return TestClient(app), seen, owner


def test_from_glossary_projects_whole_glossary_and_returns_counts(monkeypatch):
    book = uuid4()
    c, seen, owner = _build(monkeypatch, book=book)
    r = c.post(f"/v1/knowledge/projects/{_PROJ}/entities/from-glossary", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"created": 3, "existing": 1, "seen": 5, "skipped": 0, "truncated": False, "conflicted": 2}
    # threaded the owner + the project's book, and entity_ids=None → whole active glossary
    assert seen["user_id"] == str(owner) and seen["book_id"] == book
    assert seen["project_id"] == _PROJ and seen["entity_ids"] is None


def test_from_glossary_targets_a_subset(monkeypatch):
    c, seen, _ = _build(monkeypatch, book=uuid4())
    r = c.post(f"/v1/knowledge/projects/{_PROJ}/entities/from-glossary",
               json={"entity_ids": ["e1", "e2"]})
    assert r.status_code == 200
    assert seen["entity_ids"] == ["e1", "e2"]


def test_from_glossary_bookless_project_is_400(monkeypatch):
    c, _seen, _ = _build(monkeypatch, book=None)  # project_meta → (owner, None)
    r = c.post(f"/v1/knowledge/projects/{_PROJ}/entities/from-glossary", json={})
    assert r.status_code == 400


def test_from_glossary_normalizes_entity_ids_like_the_mcp_tool(monkeypatch):
    # Parity with kg_project_entities_to_nodes: strip whitespace, drop empties.
    c, seen, _ = _build(monkeypatch, book=uuid4())
    r = c.post(f"/v1/knowledge/projects/{_PROJ}/entities/from-glossary",
               json={"entity_ids": ["  e1 ", "", "e2", "   "]})
    assert r.status_code == 200
    assert seen["entity_ids"] == ["e1", "e2"]


def test_from_glossary_empty_id_list_becomes_whole_glossary(monkeypatch):
    # An all-blank / empty subset → None (whole active glossary), not "project nothing".
    c, seen, _ = _build(monkeypatch, book=uuid4())
    r = c.post(f"/v1/knowledge/projects/{_PROJ}/entities/from-glossary",
               json={"entity_ids": ["", "  "]})
    assert r.status_code == 200
    assert seen["entity_ids"] is None
