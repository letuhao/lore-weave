"""C13 — unit tests for GET /v1/knowledge/projects/{id}/glossary-entity-stats.

A THIN pass-through to glossary-service's /internal/books/{id}/entities/stats
(the FE cannot reach glossary /internal directly). Powers the build-wizard
Step-2 auto-pin suggestion banner. The route:
  - 404 when the project doesn't exist for the user,
  - 422 no_book when the project has no linked book,
  - returns the glossary stats payload on success,
  - degrades to an empty list on a glossary outage (never blocks the wizard).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()
_BOOK_ID = uuid4()


def _project_meta(book_id):
    proj = MagicMock()
    proj.book_id = book_id
    proj.project_id = _PROJECT_ID
    return proj


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()


_NO_PROJECT = object()


def _make_client(*, project=None, stats_return=None):
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import get_glossary_client, get_projects_repo

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    # project=None ⇒ default stub; project=_NO_PROJECT ⇒ repo returns None (404).
    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_meta(_BOOK_ID)
    repo = MagicMock()
    repo.get = AsyncMock(return_value=repo_return)
    app.dependency_overrides[get_projects_repo] = lambda: repo

    gclient = MagicMock()
    gclient.get_entity_stats = AsyncMock(return_value=stats_return)
    app.dependency_overrides[get_glossary_client] = lambda: gclient

    return TestClient(app, raise_server_exceptions=False), gclient


def _url() -> str:
    return f"/v1/knowledge/projects/{_PROJECT_ID}/glossary-entity-stats"


def test_stats_proxies_glossary_payload():
    payload = {
        "items": [
            {
                "entity_id": "g-1", "name": "PanGu", "kind": "deity",
                "mention_count": 2, "first_chapter_index": 1,
                "last_chapter_index": 50, "coverage_pct": 0.02,
            },
            {
                "entity_id": "g-2", "name": "Kai", "kind": "character",
                "mention_count": 30, "first_chapter_index": 1,
                "last_chapter_index": 20, "coverage_pct": 0.20,
            },
        ],
        "chapter_count": 100,
    }
    client, gclient = _make_client(stats_return=payload)
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["chapter_count"] == 100
    assert len(data["items"]) == 2
    pg = data["items"][0]
    assert pg["name"] == "PanGu"
    assert pg["coverage_pct"] == 0.02
    assert pg["first_chapter_index"] == 1 and pg["last_chapter_index"] == 50
    gclient.get_entity_stats.assert_awaited_once_with(_BOOK_ID)


def test_stats_no_book_returns_422():
    client, _ = _make_client(project=_project_meta(None))
    resp = client.get(_url())
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "no_book"


def test_stats_project_not_found_returns_404():
    client, _ = _make_client(project=_NO_PROJECT)
    resp = client.get(_url())
    assert resp.status_code == 404


def test_stats_glossary_outage_degrades_to_empty():
    """A glossary outage (get_entity_stats → None) must NOT 5xx — the wizard
    falls back to manual pinning."""
    client, _ = _make_client(stats_return=None)
    resp = client.get(_url())
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["chapter_count"] == 0
