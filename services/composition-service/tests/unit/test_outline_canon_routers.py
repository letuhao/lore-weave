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
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=uuid.uuid4())


def _node(**kw):
    return OutlineNode(id=kw.get("id", NODE), created_by=USER, project_id=PROJECT,
                       book_id=uuid.uuid4(),
                       kind=kw.get("kind", "scene"), rank="a0", version=kw.get("version", 1),
                       chapter_id=uuid.uuid4(), is_archived=kw.get("is_archived", False))


def _rule(**kw):
    return CanonRule(id=kw.get("id", RULE), created_by=USER, project_id=PROJECT,
                     text=kw.get("text", "no magic"), version=kw.get("version", 1),
                     from_order=kw.get("from_order"), until_order=kw.get("until_order"))


class StubWorks:
    def __init__(self): self.work = _work()
    async def get(self, p): return self.work


class StubOutline:
    def __init__(self):
        self.tree = []
        self.node = _node()
        self.create_raises = None
        self.update_raises = None
        self.update_result = _node(version=2)
        self.last_patch = None
        self.archive_result = _node(is_archived=True)
        self.restore_result = _node(is_archived=False)
        self.reorder_result = _node(version=2)
        self.reorder_raises = None
        self.gate = {"chapter_id": "c", "scenes_total": 2, "scenes_done": 2, "can_publish": True}
        self.commit_aware_called = False
        self.canon_issues_result = []
        self.rule_violations_result = {"items": [], "count": 0, "capped": False}
    async def get_node(self, n, **kw): return self.node
    async def list_tree(self, p, **kw): return self.tree
    async def create_node(self, p, **kw):
        if self.create_raises: raise self.create_raises
        return self.node
    async def update_node(self, n, patch, **kw):
        self.last_patch = patch
        if self.update_raises: raise self.update_raises
        return self.update_result
    async def update_node_commit_aware(self, n, patch, **kw):
        self.commit_aware_called = True
        if self.update_raises: raise self.update_raises
        return self.update_result
    async def chapter_scene_gate(self, p, ch): return self.gate
    async def canon_issues(self, p): return self.canon_issues_result
    async def rule_violations(self, p, **kw): return self.rule_violations_result
    async def archive_node(self, n): return self.archive_result
    async def restore_node(self, n): return self.restore_result
    async def reorder_node(self, n, **kw):
        if self.reorder_raises: raise self.reorder_raises
        return self.reorder_result


class StubSceneLinks:
    def __init__(self):
        self.links = []
        self.create_raises = None
        self.deleted = True
    async def list_by_project(self, p): return self.links
    async def create(self, p, f, t, **kw):
        if self.create_raises: raise self.create_raises
        return SceneLink(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, from_node_id=f, to_node_id=t)
    async def delete(self, p, lid): return self.deleted


class StubCanon:
    """Stateful on is_archived so the BE-11 delete→restore round-trip is a REAL
    round-trip through the list, not two independent stubbed returns."""
    def __init__(self):
        self.rules = []
        self.rule = _rule()
        self.update_raises = None
        self.update_result = _rule(version=2)
        self.archive_result = _rule()
        self._archived: set = set()
    async def list_all(self, p, *, include_archived=False):
        # mirrors the repo: NOT is_archived by default; include_archived returns all (BE-11b),
        # flagging the archived ones so the caller can render them under a section.
        out = []
        for r in self.rules:
            archived = r.id in self._archived
            if archived and not include_archived:
                continue
            out.append(r.model_copy(update={"is_archived": archived}))
        return out
    async def list_active(self, p):
        return [r for r in self.rules if r.id not in self._archived]
    async def create(self, p, text, **kw): return self.rule
    async def get(self, p, rid): return self.rule
    async def update(self, p, rid, patch, **kw):
        if self.update_raises: raise self.update_raises
        return self.update_result
    async def archive(self, p, rid):
        if rid in self._archived:
            return None  # already archived
        self._archived.add(rid)
        return self.archive_result
    async def restore(self, p, rid):
        if rid not in self._archived:
            return None  # not archived → the 404 the route must surface
        self._archived.discard(rid)
        return _rule(id=rid)


class StubTemplates:
    async def list_for_user(self, u, *, include_archived=False):
        return [StructureTemplate(id=uuid.uuid4(), name="Save the Cat", kind="save_the_cat")]

    # S-01 write side — echo back a template so the route serialization is exercised.
    async def create(self, u, *, name, kind="generic", beats=None):
        return StructureTemplate(id=uuid.uuid4(), owner_user_id=u, name=name, kind=kind, beats=beats or [])

    async def clone_builtin(self, u, template_id, *, name=None):
        return StructureTemplate(id=uuid.uuid4(), owner_user_id=u, name=name or "X (copy)", beats=[])

    async def update(self, u, template_id, expected_version, **patch):
        return StructureTemplate(id=template_id, owner_user_id=u, name=patch.get("name", "n"), version=2)

    async def archive(self, u, template_id):
        return StructureTemplate(id=template_id, owner_user_id=u, name="n", is_archived=True)

    async def restore(self, u, template_id):
        return StructureTemplate(id=template_id, owner_user_id=u, name="n", is_archived=False)


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    # By-id DELETE (scene-link) + canon PATCH/DELETE resolve their scope from the
    # row itself via get_pool().fetchrow (PM-8 scope-bootstrap) before gating —
    # give both routers a fake pool that returns this project's row.
    class _FakePool:
        async def fetchrow(self, query, *args):
            return {"project_id": PROJECT}
    monkeypatch.setattr("app.routers.outline.get_pool", lambda: _FakePool())
    monkeypatch.setattr("app.routers.canon.get_pool", lambda: _FakePool())

    from app.main import app
    from app.deps import (get_canon_rules_repo, get_grant_client_dep, get_outline_repo,
                          get_scene_links_repo, get_structure_templates_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; the outline/canon routers resolve
    # the Work's book then gate VIEW/EDIT (deny paths in test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, outline, links, canon, templates = StubWorks(), StubOutline(), StubSceneLinks(), StubCanon(), StubTemplates()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_scene_links_repo] = lambda: links
    app.dependency_overrides[get_canon_rules_repo] = lambda: canon
    app.dependency_overrides[get_structure_templates_repo] = lambda: templates
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, works, outline, links, canon
    app.dependency_overrides.clear()


@pytest.fixture
def ctx_view_only(monkeypatch):
    """BE-11 — the same wiring, but the caller holds only a VIEW grant. Restore MUTATES,
    so its gate is EDIT and this caller must be refused."""
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    class _FakePool:
        async def fetchrow(self, query, *args):
            return {"project_id": PROJECT}
    monkeypatch.setattr("app.routers.canon.get_pool", lambda: _FakePool())

    from app.main import app
    from app.deps import get_canon_rules_repo, get_grant_client_dep, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    class _ViewGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.VIEW
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.VIEW, "active"

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: StubWorks()
    app.dependency_overrides[get_canon_rules_repo] = lambda: StubCanon()
    app.dependency_overrides[get_grant_client_dep] = lambda: _ViewGrant()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── outline ──

def test_get_outline_returns_tree_and_links(ctx):
    c, _, outline, links, _ = ctx
    outline.tree = [_node()]
    links.links = [SceneLink(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, from_node_id=NODE, to_node_id=uuid.uuid4())]
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


def test_restore_node_200_and_404(ctx):
    c, _, outline, _, _ = ctx
    r = c.post(f"/v1/composition/outline/nodes/{NODE}/restore")
    assert r.status_code == 200 and r.json()["is_archived"] is False
    # not archived / not ours → repo returns None → 404
    outline.restore_result = None
    assert c.post(f"/v1/composition/outline/nodes/{NODE}/restore").status_code == 404


def test_reorder_node_200_412_400_404(ctx):
    c, _, outline, _, _ = ctx
    body = {"new_parent_id": str(uuid.uuid4()), "after_id": str(uuid.uuid4())}
    r = c.post(f"/v1/composition/outline/nodes/{NODE}/reorder", json=body,
               headers={"If-Match": "1"})
    assert r.status_code == 200 and r.json()["version"] == 2
    # stale If-Match → 412 with current
    outline.reorder_raises = VersionMismatchError(_node(version=9))
    r = c.post(f"/v1/composition/outline/nodes/{NODE}/reorder", json=body, headers={"If-Match": "1"})
    assert r.status_code == 412 and r.json()["detail"]["code"] == "NODE_VERSION_CONFLICT"
    # reparent cycle / bad ref → 400
    outline.reorder_raises = ReferenceViolationError("cycle")
    assert c.post(f"/v1/composition/outline/nodes/{NODE}/reorder", json=body).status_code == 400
    # node gone → 404
    outline.reorder_raises = None
    outline.reorder_result = None
    assert c.post(f"/v1/composition/outline/nodes/{NODE}/reorder", json=body).status_code == 404


# ── M9 chapter-gate + scene_committed routing ──

def test_publish_gate_returns_counts(ctx):
    c, _, outline, _, _ = ctx
    chapter = uuid.uuid4()
    outline.gate = {"chapter_id": str(chapter), "scenes_total": 3, "scenes_done": 3, "can_publish": True}
    r = c.get(f"/v1/composition/works/{PROJECT}/chapters/{chapter}/publish-gate")
    assert r.status_code == 200
    body = r.json()
    assert body["scenes_total"] == 3 and body["scenes_done"] == 3 and body["can_publish"] is True


def test_publish_gate_404_when_work_missing(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/chapters/{uuid.uuid4()}/publish-gate").status_code == 404


# ── Studio Quality tab: book-wide itemized canon issues ──

def test_canon_issues_returns_items(ctx):
    c, _, outline, _, _ = ctx
    chapter = uuid.uuid4()
    outline.canon_issues_result = [
        {"scene_id": str(NODE), "scene_title": "Scene A", "chapter_id": str(chapter),
         "job_id": str(uuid.uuid4()), "created_at": "2026-07-06T00:00:00+00:00",
         "status": "checked", "violations": [{"entity_id": "e1", "name": "Old Man Wu"}]},
    ]
    r = c.get(f"/v1/composition/works/{PROJECT}/canon-issues")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["scene_title"] == "Scene A"
    assert items[0]["violations"][0]["name"] == "Old Man Wu"


def test_canon_issues_empty_returns_empty_items(ctx):
    c, _, outline, _, _ = ctx
    outline.canon_issues_result = []
    r = c.get(f"/v1/composition/works/{PROJECT}/canon-issues")
    assert r.status_code == 200 and r.json()["items"] == []


def test_canon_issues_404_when_work_missing(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/canon-issues").status_code == 404


# ── Studio Quality tab: the RULE lane (24 PH18 / D-04 B) ──
# A SEPARATE route from /canon-issues on purpose: two engines, two verdicts, two names.

def test_rule_violations_returns_items(ctx):
    c, _, outline, _, _ = ctx
    outline.rule_violations_result = {
        "items": [
            {"scene_id": str(NODE), "scene_title": "Scene A", "chapter_id": str(uuid.uuid4()),
             "job_id": str(uuid.uuid4()), "created_at": "2026-07-12T00:00:00+00:00",
             "rule_id": str(uuid.uuid4()), "rule_text": "Magic always costs HP",
             "span": "she cast it freely", "why": "no cost paid"},
        ],
        "count": 7, "capped": True,
    }
    r = c.get(f"/v1/composition/works/{PROJECT}/rule-violations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1 and body["items"][0]["rule_text"] == "Magic always costs HP"
    # OUT-5: the route must RELAY the partiality, not flatten it away.
    assert body["count"] == 7 and body["capped"] is True


def test_rule_violations_empty_returns_empty_items(ctx):
    c, _, outline, _, _ = ctx
    outline.rule_violations_result = {"items": [], "count": 0, "capped": False}
    r = c.get(f"/v1/composition/works/{PROJECT}/rule-violations")
    assert r.status_code == 200 and r.json()["items"] == []


def test_rule_violations_404_when_work_missing(ctx):
    # The grant gate is the same as every other work-scoped read — a book you cannot
    # VIEW must not leak its canon findings.
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/rule-violations").status_code == 404


def test_patch_status_done_routes_through_commit_aware(ctx):
    # status → done must go through the commit-aware path (which emits the
    # composition.scene_committed telemetry atomically).
    c, _, outline, _, _ = ctx
    r = c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"status": "done"})
    assert r.status_code == 200 and outline.commit_aware_called is True


def test_patch_beat_role_set_and_explicit_null_clear(ctx):
    """T1.2: assigning a beat (beat_role='k') and CLEARING it (beat_role=null) both
    reach update_node. An explicit JSON null must survive model_dump(exclude_unset)
    — the clear path silently breaks if Pydantic dropped it."""
    c, _, outline, _, _ = ctx
    c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"beat_role": "catalyst"})
    assert outline.last_patch == {"beat_role": "catalyst"}
    c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"beat_role": None})
    assert outline.last_patch == {"beat_role": None}  # explicit null kept → clears


def test_patch_non_done_uses_plain_update(ctx):
    # a title-only patch must NOT take the transactional commit-aware path.
    c, _, outline, _, _ = ctx
    r = c.patch(f"/v1/composition/outline/nodes/{NODE}", json={"title": "x"})
    assert r.status_code == 200 and outline.commit_aware_called is False


def test_is_scene_commit_truth_table():
    from app.db.repositories.outline import _is_scene_commit
    scene_draft = _node(kind="scene")  # status defaults to 'empty'
    scene_done = _node(kind="scene")
    scene_done.status = "done"
    chapter_done = _node(kind="chapter")
    chapter_done.status = "done"
    # real transition: scene was-not-done → now done
    assert _is_scene_commit(scene_draft, scene_done) is True
    # no-op: already done → done
    assert _is_scene_commit(scene_done, scene_done) is False
    # non-scene node never emits
    assert _is_scene_commit(_node(kind="chapter"), chapter_done) is False
    # missing prior state (None) → no emit (can't prove a transition)
    assert _is_scene_commit(None, scene_done) is False
    # update returned None (404/412) → no emit
    assert _is_scene_commit(scene_draft, None) is False


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


# ── S-01 · structure-template authoring route contract ──

def test_create_template_ok(ctx):
    c, _, _, _, _ = ctx
    r = c.post("/v1/composition/templates", json={"name": "My Structure", "beats": []})
    assert r.status_code == 201 and r.json()["name"] == "My Structure"


def test_create_template_rejects_blank_name(ctx):
    """The empty-name bug: a blank/whitespace name must 422, not save an unfindable row."""
    c, _, _, _, _ = ctx
    for bad in ("", "   ", "\t"):
        r = c.post("/v1/composition/templates", json={"name": bad, "beats": []})
        assert r.status_code == 422, f"blank name {bad!r} should be rejected"


def test_patch_template_requires_if_match(ctx):
    c, _, _, _, _ = ctx
    r = c.patch(f"/v1/composition/templates/{uuid.uuid4()}", json={"name": "x"})
    assert r.status_code == 428  # OCC: If-Match required


def test_patch_template_rejects_blank_name(ctx):
    c, _, _, _, _ = ctx
    r = c.patch(f"/v1/composition/templates/{uuid.uuid4()}", json={"name": "  "},
                headers={"If-Match": "1"})
    assert r.status_code == 422


def test_clone_archive_restore_routes(ctx):
    c, _, _, _, _ = ctx
    tid = uuid.uuid4()
    assert c.post(f"/v1/composition/templates/{tid}/clone", json={}).status_code == 201
    assert c.delete(f"/v1/composition/templates/{tid}").status_code == 204
    assert c.post(f"/v1/composition/templates/{tid}/restore").status_code == 200


# ── BE-11 (W0-BE2) · canon_rule RESTORE — the undo the DELETE already promises ──


def test_delete_then_restore_reappears_in_list(ctx):
    """The whole point of the slice: DELETE soft-archives (so the rule vanishes from the
    management list) and RESTORE brings it back. `list_all` filters NOT is_archived, so an
    archived rule is unlistable — the undo carries the id from the DELETE response."""
    c, _, _, _, canon = ctx
    rule = _rule()
    canon.rules = [rule]
    assert len(c.get(f"/v1/composition/works/{PROJECT}/canon-rules").json()["rules"]) == 1

    assert c.delete(f"/v1/composition/canon-rules/{rule.id}").status_code == 200
    assert c.get(f"/v1/composition/works/{PROJECT}/canon-rules").json()["rules"] == []

    r = c.post(f"/v1/composition/canon-rules/{rule.id}/restore")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(rule.id)
    assert len(c.get(f"/v1/composition/works/{PROJECT}/canon-rules").json()["rules"]) == 1


def test_restore_of_a_never_archived_rule_is_404(ctx):
    c, _, _, _, _ = ctx
    r = c.post(f"/v1/composition/canon-rules/{RULE}/restore")
    assert r.status_code == 404
    assert r.json()["detail"] == "canon rule not found or not archived"


def test_list_include_archived_returns_archived_rows_flagged(ctx):
    """BE-11b — the management UI needs to LIST archived rules (to restore one), which the
    default list hides. `?include_archived=true` returns them, flagged is_archived, so the
    default list stays lean and the UI can render an archived section."""
    c, _, _, _, canon = ctx
    rule = _rule()
    canon.rules = [rule]
    assert c.delete(f"/v1/composition/canon-rules/{rule.id}").status_code == 200
    # default list hides it …
    assert c.get(f"/v1/composition/works/{PROJECT}/canon-rules").json()["rules"] == []
    # … include_archived surfaces it, flagged.
    rows = c.get(f"/v1/composition/works/{PROJECT}/canon-rules?include_archived=true").json()["rules"]
    assert len(rows) == 1
    assert rows[0]["id"] == str(rule.id)
    assert rows[0]["is_archived"] is True


def test_restore_by_a_view_only_grantee_is_403(ctx_view_only):
    """The gate is EDIT — restore MUTATES. A VIEW grantee must not un-delete someone's rule."""
    c = ctx_view_only
    r = c.post(f"/v1/composition/canon-rules/{RULE}/restore")
    assert r.status_code == 403
