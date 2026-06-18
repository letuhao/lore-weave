"""M4 grounding router test (TestClient + overrides; packer stubbed).

The packer itself is unit-tested in test_pack.py; here we isolate the router's
work/node loading, 404s, and response shape by stubbing pack().
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork, OutlineNode
from app.packer import profile as P
from app.packer.pack import OwnershipError, PackedContext

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
NODE = uuid.uuid4()


def _work():
    return CompositionWork(project_id=PROJECT, user_id=USER, book_id=BOOK)


def _node(project_id=PROJECT):
    return OutlineNode(id=NODE, user_id=USER, project_id=project_id, kind="scene",
                       rank="a0", chapter_id=uuid.uuid4())


def _packed(available=True):
    return PackedContext(
        blocks={"canon": "no spoilers"}, prompt="<canon>\nno spoilers\n</canon>",
        profile=P.NEUTRAL, token_count=3, dropped_count=0, l4_dropped_no_position=0,
        grounding_available=available, over_budget=False,
        warnings=[] if available else ["grounding_unavailable: ..."],
    )


class StubWorks:
    def __init__(self):
        self.work = None
    async def get(self, user_id, project_id):
        return self.work


class StubOutline:
    def __init__(self):
        self.node = None
    async def get_node(self, user_id, node_id):
        return self.node


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (get_book_client_dep, get_canon_rules_repo, get_derivatives_repo,
                          get_generation_jobs_repo, get_glossary_client_dep,
                          get_knowledge_client_dep, get_outline_repo,
                          get_scene_links_repo, get_works_repo)
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works, outline = StubWorks(), StubOutline()
    pack_stub = AsyncMock(return_value=_packed())
    monkeypatch.setattr("app.routers.grounding.pack", pack_stub)

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    # the remaining packer deps are unused once pack() is stubbed, but must resolve
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    app.dependency_overrides[get_canon_rules_repo] = lambda: object()
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    app.dependency_overrides[get_generation_jobs_repo] = lambda: object()  # S1: new pack dep
    # C25 — derivatives repo (StubWorks non-derivative → never read; pack stubbed).
    from types import SimpleNamespace
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=lambda *a, **k: [])
    with TestClient(app) as c:
        yield c, works, outline, pack_stub
    app.dependency_overrides.clear()


_URL = f"/v1/composition/works/{PROJECT}/scenes/{NODE}/grounding"


def test_grounding_404_when_work_missing(ctx):
    c, works, outline, _ = ctx
    works.work = None
    assert c.get(_URL).status_code == 404


def test_grounding_404_when_node_missing(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = None
    assert c.get(_URL).status_code == 404


def test_grounding_404_when_node_other_project(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node(project_id=uuid.uuid4())  # node belongs to a different project
    assert c.get(_URL).status_code == 404


def test_grounding_happy_returns_pack(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    r = c.get(_URL, params={"guide": "make it tense"})
    assert r.status_code == 200
    body = r.json()
    assert body["blocks"]["canon"] == "no spoilers"
    assert body["grounding_available"] is True
    assert body["profile"]["source_language"] == "auto"


def test_grounding_ownership_error_maps_404(ctx):
    c, works, outline, pack_stub = ctx
    works.work = _work()
    outline.node = _node()
    pack_stub.side_effect = OwnershipError("nope")
    assert c.get(_URL).status_code == 404


def test_grounding_book_down_maps_502(ctx):
    from app.clients.book_client import BookClientError
    c, works, outline, pack_stub = ctx
    works.work = _work()
    outline.node = _node()
    pack_stub.side_effect = BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")
    assert c.get(_URL).status_code == 502
