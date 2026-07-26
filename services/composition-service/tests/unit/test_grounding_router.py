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
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK)


def _node(project_id=PROJECT):
    return OutlineNode(id=NODE, created_by=USER, project_id=project_id, book_id=BOOK,
                       kind="scene", rank="a0", chapter_id=uuid.uuid4())


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
    async def get(self, project_id):
        return self.work


class StubOutline:
    def __init__(self):
        self.node = None
    async def get_node(self, node_id):
        return self.node


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (get_book_client_dep, get_canon_rules_repo, get_derivatives_repo,
                          get_embedding_client_dep, get_generation_jobs_repo,
                          get_glossary_client_dep, get_grant_client_dep,
                          get_grounding_pins_repo,
                          get_knowledge_client_dep, get_outline_repo, get_references_repo,
                          get_scene_links_repo, get_style_profile_repo,
                          get_voice_profile_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the PUT grounding-pins endpoint
    # gates EDIT on the Work's book before writing.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, outline = StubWorks(), StubOutline()
    pack_stub = AsyncMock(return_value=_packed())
    monkeypatch.setattr("app.routers.grounding.pack", pack_stub)

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    # the remaining packer deps are unused once pack() is stubbed, but must resolve
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    app.dependency_overrides[get_canon_rules_repo] = lambda: object()
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    app.dependency_overrides[get_generation_jobs_repo] = lambda: object()  # S1: new pack dep
    app.dependency_overrides[get_grounding_pins_repo] = lambda: object()  # T3.4: pack stubbed
    app.dependency_overrides[get_style_profile_repo] = lambda: object()  # T3.5: pack stubbed
    app.dependency_overrides[get_voice_profile_repo] = lambda: object()  # T3.5: pack stubbed
    app.dependency_overrides[get_references_repo] = lambda: object()  # T3.6: pack stubbed
    app.dependency_overrides[get_embedding_client_dep] = lambda: object()  # T3.6: pack stubbed
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


def test_grounding_response_carries_grounding_items(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    body = c.get(_URL).json()
    assert "grounding_items" in body  # T3.4 — addressable pin/exclude state surfaced


# ───────────────────────── PUT grounding-pins (T3.4) ─────────────────────────

_PINS_URL = f"/v1/composition/works/{PROJECT}/scenes/{NODE}/grounding-pins"


class _RecordingPins:
    def __init__(self):
        self.calls = []
    async def set_action(self, project_id, node_id, item_type, item_id, action, *, created_by=None):
        self.calls.append(("set", item_type, item_id, action))
        from types import SimpleNamespace
        return SimpleNamespace(item_type=item_type, item_id=item_id, action=action)
    async def clear(self, project_id, node_id, item_type, item_id):
        self.calls.append(("clear", item_type, item_id))
        return True


def _use_recording_pins():
    from app.main import app
    from app.deps import get_grounding_pins_repo
    rec = _RecordingPins()
    app.dependency_overrides[get_grounding_pins_repo] = lambda: rec
    return rec


def test_put_grounding_pin_sets_action(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    rec = _use_recording_pins()
    r = c.put(_PINS_URL, json={"item_type": "lore", "item_id": "src-1", "action": "pin"})
    assert r.status_code == 200
    assert r.json() == {"item_type": "lore", "item_id": "src-1", "action": "pin"}
    assert rec.calls == [("set", "lore", "src-1", "pin")]


def test_put_grounding_pin_none_clears(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    rec = _use_recording_pins()
    r = c.put(_PINS_URL, json={"item_type": "present", "item_id": "g1", "action": "none"})
    assert r.status_code == 200
    assert rec.calls == [("clear", "present", "g1")]  # 'none' routes to clear, not set


def test_put_grounding_pin_404_when_work_missing(ctx):
    c, works, outline, _ = ctx
    works.work = None  # not owned → 404, no existence oracle
    _use_recording_pins()
    r = c.put(_PINS_URL, json={"item_type": "lore", "item_id": "src-1", "action": "pin"})
    assert r.status_code == 404


def test_put_grounding_pin_404_when_node_other_project(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node(project_id=uuid.uuid4())  # scene of another project
    _use_recording_pins()
    r = c.put(_PINS_URL, json={"item_type": "canon", "item_id": "r1", "action": "exclude"})
    assert r.status_code == 404


def test_put_grounding_pin_rejects_unknown_item_type(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    _use_recording_pins()
    # 'timeline' is not an addressable type (present/canon/lore) → 422 at validation
    r = c.put(_PINS_URL, json={"item_type": "timeline", "item_id": "x", "action": "pin"})
    assert r.status_code == 422


def test_put_grounding_pin_rejects_oversize_item_id(ctx):
    c, works, outline, _ = ctx
    works.work = _work()
    outline.node = _node()
    _use_recording_pins()
    # >200 chars → 422 at the boundary (not a 500 on the RETURNING-row revalidation)
    r = c.put(_PINS_URL, json={"item_type": "lore", "item_id": "x" * 201, "action": "pin"})
    assert r.status_code == 422
