"""M7 router tests — outline/scene-links + canon-rules/templates (TestClient)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CanonRule, CompositionWork, OutlineNode, SceneLink, StructureTemplate
from app.db.repositories import ReferenceViolationError, VersionMismatchError

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
NODE = uuid.uuid4()
RULE = uuid.uuid4()


def _work():
    return CompositionWork(project_id=PROJECT, user_id=USER, book_id=uuid.uuid4())


def _node(**kw):
    return OutlineNode(id=kw.get("id", NODE), user_id=USER, project_id=PROJECT,
                       kind=kw.get("kind", "scene"), rank="a0", version=kw.get("version", 1),
                       chapter_id=uuid.uuid4(), is_archived=kw.get("is_archived", False))


def _rule(**kw):
    return CanonRule(id=kw.get("id", RULE), user_id=USER, project_id=PROJECT,
                     text=kw.get("text", "no magic"), version=kw.get("version", 1),
                     from_order=kw.get("from_order"), until_order=kw.get("until_order"))


class StubWorks:
    def __init__(self): self.work = _work()
    async def get(self, u, p): return self.work


class StubOutline:
    def __init__(self):
        self.tree = []
        self.node = _node()
        self.create_raises = None
        self.update_raises = None
        self.update_result = _node(version=2)
        self.archive_result = _node(is_archived=True)
    async def list_tree(self, u, p, **kw): return self.tree
    async def create_node(self, u, p, **kw):
        if self.create_raises: raise self.create_raises
        return self.node
    async def update_node(self, u, n, patch, **kw):
        if self.update_raises: raise self.update_raises
        return self.update_result
    async def archive_node(self, u, n): return self.archive_result


class StubSceneLinks:
    def __init__(self):
        self.links = []
        self.create_raises = None
        self.deleted = True
    async def list_by_project(self, u, p): return self.links
    async def create(self, u, p, f, t, **kw):
        if self.create_raises: raise self.create_raises
        return SceneLink(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, from_node_id=f, to_node_id=t)
    async def delete(self, u, lid): return self.deleted


class StubCanon:
    def __init__(self):
        self.rules = []
        self.rule = _rule()
        self.update_raises = None
        self.update_result = _rule(version=2)
        self.archive_result = _rule()
    async def list_all(self, u, p): return self.rules
    async def list_active(self, u, p): return self.rules
    async def create(self, u, p, text, **kw): return self.rule
    async def get(self, u, rid): return self.rule
    async def update(self, u, rid, patch, **kw):
        if self.update_raises: raise self.update_raises
        return self.update_result
    async def archive(self, u, rid): return self.archive_result


class StubTemplates:
    async def list_for_user(self, u):
        return [StructureTemplate(id=uuid.uuid4(), name="Save the Cat", kind="save_the_cat")]


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (get_canon_rules_repo, get_outline_repo, get_scene_links_repo,
                          get_structure_templates_repo, get_works_repo)
    from app.middleware.jwt_auth import get_current_user
    works, outline, links, canon, templates = StubWorks(), StubOutline(), StubSceneLinks(), StubCanon(), StubTemplates()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_scene_links_repo] = lambda: links
    app.dependency_overrides[get_canon_rules_repo] = lambda: canon
    app.dependency_overrides[get_structure_templates_repo] = lambda: templates
    with TestClient(app) as c:
        yield c, works, outline, links, canon
    app.dependency_overrides.clear()


# ── outline ──

def test_get_outline_returns_tree_and_links(ctx):
    c, _, outline, links, _ = ctx
    outline.tree = [_node()]
    links.links = [SceneLink(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, from_node_id=NODE, to_node_id=uuid.uuid4())]
    r = c.get(f"/v1/composition/works/{PROJECT}/outline")
    assert r.status_code == 200 and len(r.json()["nodes"]) == 1 and len(r.json()["scene_links"]) == 1


def test_get_outline_404_when_work_missing(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/outline").status_code == 404


def test_create_node_201_and_bad_reference_400(ctx):
    c, _, outline, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/nodes", json={"kind": "arc", "title": "Act I"})
    assert r.status_code == 201
    outline.create_raises = ReferenceViolationError("parent not owned")
    r2 = c.post(f"/v1/composition/works/{PROJECT}/outline/nodes", json={"kind": "arc", "parent_id": str(uuid.uuid4())})
    assert r2.status_code == 400 and r2.json()["detail"]["code"] == "BAD_REFERENCE"


def test_patch_node_ifmatch_412_and_cycle_400(ctx):
    c, _, outline, _, _ = ctx
    outline.update_raises = VersionMismatchError(_node(version=3))
    r = c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"title": "x"}, headers={"If-Match": "1"})
    assert r.status_code == 412 and r.json()["detail"]["current"]["version"] == 3
    outline.update_raises = ReferenceViolationError("cycle")
    r2 = c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"parent_id": str(uuid.uuid4())})
    assert r2.status_code == 400


def test_delete_node_archives(ctx):
    c, _, _, _, _ = ctx
    r = c.delete(f"/v1/composition/outline/nodes/{NODE}")
    assert r.status_code == 200 and r.json()["is_archived"] is True


def test_scene_link_create_400_on_foreign_endpoint(ctx):
    c, _, _, links, _ = ctx
    links.create_raises = ReferenceViolationError("endpoint not owned")
    r = c.post(f"/v1/composition/works/{PROJECT}/scene-links",
               json={"from_node_id": str(uuid.uuid4()), "to_node_id": str(uuid.uuid4())})
    assert r.status_code == 400


def test_scene_link_delete_204_and_404(ctx):
    c, _, _, links, _ = ctx
    assert c.delete(f"/v1/composition/scene-links/{uuid.uuid4()}").status_code == 204
    links.deleted = False
    assert c.delete(f"/v1/composition/scene-links/{uuid.uuid4()}").status_code == 404


# ── canon ──

def test_canon_create_rejects_inverted_window_cr4(ctx):
    c, _, _, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/canon-rules",
               json={"text": "secret", "from_order": 10, "until_order": 3})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "CANON_WINDOW_INVERTED"


def test_canon_create_201(ctx):
    c, _, _, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/canon-rules", json={"text": "no magic", "from_order": 1, "until_order": 10})
    assert r.status_code == 201


def test_canon_patch_ifmatch_412(ctx):
    c, _, _, _, canon = ctx
    canon.update_raises = VersionMismatchError(_rule(version=5))
    r = c.patch(f"/v1/composition/canon-rules/{RULE}", json={"text": "v2"}, headers={"If-Match": "1"})
    assert r.status_code == 412 and r.json()["detail"]["current"]["version"] == 5


def test_canon_patch_cr4_on_effective_window(ctx):
    # patch sets only from_order; effective window vs current until_order is inverted
    c, _, _, _, canon = ctx
    canon.rule = _rule(from_order=1, until_order=5)
    r = c.patch(f"/v1/composition/canon-rules/{RULE}", json={"from_order": 20})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "CANON_WINDOW_INVERTED"


def test_canon_delete_archives(ctx):
    c, _, _, _, _ = ctx
    assert c.delete(f"/v1/composition/canon-rules/{RULE}").status_code == 200


def test_templates_lists_builtins(ctx):
    c, _, _, _, _ = ctx
    r = c.get("/v1/composition/templates")
    assert r.status_code == 200 and r.json()["templates"][0]["kind"] == "save_the_cat"
