"""A3 B4 — decompose/commit router tests (TestClient; planner + clients stubbed).

Covers the guards the endpoints add on top of the (separately-tested) planner:
template-404, no-chapters, plan_max_chapters, IDOR chapter, present_entity
validation, replace-guard, and the commit persist spec.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork, StructureTemplate
from app.engine.plan import ChapterScenes, ChapterPlan, DecomposeResult, ScenePlan

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
CH1 = uuid.uuid4()
CH2 = uuid.uuid4()
ENT = uuid.uuid4()
TMPL = uuid.uuid4()


class StubWorks:
    def __init__(self):
        self.work = CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, settings={})
    async def get(self, p):
        return self.work


class StubBook:
    def __init__(self):
        self.chapters = [
            {"chapter_id": CH1, "title": "Ch 1", "sort_order": 1},
            {"chapter_id": CH2, "title": "Ch 2", "sort_order": 2},
        ]
    async def list_chapters(self, book_id, bearer, *, limit=200):
        return self.chapters


class StubKal:
    """Stub for the KAL client's `roster` drain (X1: the planner reads the cast
    through the KAL, not glossary directly). `roster` returns the fully-drained cast
    list (`[{entity_id, name}]`); `resp=None` simulates a KAL outage → empty cast."""
    def __init__(self):
        self.resp: dict | None = {"items": [{"entity_id": str(ENT), "name": "Alice"}], "next_cursor": None}
    async def roster(self, book_id, *, user_id=None, strict=False):
        if not self.resp:
            # Outage: a strict caller (the commit path) gets RosterIncomplete so it SKIPS
            # validation rather than treating a truncated/empty cast as authoritative; a
            # non-strict caller (the packer) gets the empty partial. Mirrors the real client.
            if strict:
                from app.clients.kal_client import RosterIncomplete
                raise RosterIncomplete("stub outage")
            return []
        return [{"entity_id": str(i["entity_id"]), "name": i["name"]}
                for i in self.resp.get("items", []) if i.get("name") and i.get("entity_id")]


class StubOutline:
    def __init__(self):
        self.existing: set = set()   # chapter_ids that already have active scenes
        self.created = None
        self.ledger: dict = {}       # idempotency_key → result (replay)
        # the swap route now dispatches on node.kind — default to a chapter node so
        # the chapter-swap test keeps routing to apply_motif_swap.
        self.node_kind = "chapter"
    async def get_node(self, node_id, *, conn=None):
        from types import SimpleNamespace
        return SimpleNamespace(project_id=PROJECT, kind=self.node_kind)
    async def commit_decomposed_tree(self, p, *, book_id=None, created_by=None, arc_title, chapters, replace=False, idempotency_key=None):
        if idempotency_key and idempotency_key in self.ledger:
            return {**self.ledger[idempotency_key], "replay": True}
        clash = [ch["chapter_id"] for ch in chapters if ch["chapter_id"] in self.existing]
        if clash and not replace:
            from app.db.repositories import AlreadyPlannedError
            raise AlreadyPlannedError(clash)
        self.created = {"arc_title": arc_title, "chapters": chapters, "replace": replace, "book_id": book_id}
        result = {"arc_id": str(uuid.uuid4()),
                  "chapter_ids": [str(uuid.uuid4()) for _ in chapters],
                  "scene_ids": [str(uuid.uuid4()) for ch in chapters for _ in ch["scenes"]]}
        if idempotency_key:
            self.ledger[idempotency_key] = result
        return result


class StubTemplates:
    def __init__(self):
        self.template = StructureTemplate(
            id=TMPL, owner_user_id=None, name="Three-Act", kind="generic",
            beats=[{"key": "setup", "label": "Setup", "purpose": "establish", "order": 1}],
        )
    async def get(self, u, tid):
        return self.template


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    from app.main import app
    from app.deps import (get_book_client_dep, get_grant_client_dep, get_kal_client_dep,
                          get_llm_client_dep, get_outline_repo,
                          get_structure_templates_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the plan endpoints resolve the
    # Work's book then gate EDIT before decompose/commit/swap (deny paths in
    # test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, book, kal, outline, templates = (
        StubWorks(), StubBook(), StubKal(), StubOutline(), StubTemplates())
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_kal_client_dep] = lambda: kal
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_structure_templates_repo] = lambda: templates
    app.dependency_overrides[get_llm_client_dep] = lambda: object()
    with TestClient(app) as c:
        yield c, works, book, kal, outline, templates
    app.dependency_overrides.clear()


def _decompose_body():
    return {"structure_template_id": str(TMPL), "premise": "a quest",
            "model_source": "user_model", "model_ref": str(uuid.uuid4())}


# ── preview ──

def test_decompose_preview_returns_tree(ctx, monkeypatch):
    c, *_ = ctx
    result = DecomposeResult(
        arc_title="Three-Act", unmapped_beats=["climax"],
        chapters=[ChapterScenes(
            chapter=ChapterPlan(chapter_id=str(CH1), title="Ch 1", sort_order=1,
                                beat_role="setup", intent="open"),
            scenes=[ScenePlan(title="s", synopsis="do", tension=20,
                              present_entity_ids=[str(ENT)],
                              present_entity_names_unresolved=[], suggested_k=1)],
        )],
    )

    async def fake_decompose(*a, **kw):
        return result

    monkeypatch.setattr("app.routers.plan.decompose", fake_decompose)
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose", json=_decompose_body())
    assert r.status_code == 200
    body = r.json()
    assert body["arc_title"] == "Three-Act" and body["unmapped_beats"] == ["climax"]
    assert body["chapters"][0]["chapter"]["beat_role"] == "setup"
    assert body["chapters"][0]["scenes"][0]["suggested_k"] == 1


def test_decompose_preview_worker_enabled_enqueues_202(ctx, monkeypatch):
    # D-M4-DECOMPOSE-ENDPOINT-TEST: with the composition worker ON, the endpoint
    # persists the FULLY-RESOLVED decompose args (the worker has no bearer to
    # re-fetch book/cast) + enqueues + returns 202 — and must NOT run the inline
    # planner. Mirrors the worker-202 tests the other M4 ops already have.
    c, *_ = ctx
    monkeypatch.setattr("app.routers.plan.settings.composition_worker_enabled", True)

    job_id = uuid.uuid4()
    created: dict = {}

    class FakeJob:
        id = job_id

    class FakeJobsRepo:
        async def create(self, project_id, *, created_by=None, operation, mode, status, input):
            created.update(operation=operation, mode=mode, status=status, input=input)
            return FakeJob(), True

    enqueued: dict = {}

    async def fake_enqueue(redis_url, *, job_id, user_id, project_id):
        enqueued.update(job_id=job_id, user_id=user_id, project_id=project_id)
        return True

    async def fail_decompose(*a, **kw):
        raise AssertionError("inline decompose must NOT run when the worker is enabled")

    # get_generation_jobs_repo is ASYNC (deps.py) — the endpoint MUST await it.
    # Mock it async so a missing `await` regresses to a 'coroutine has no attribute
    # create' 500 (the exact bug the live-smoke caught; a sync mock would hide it).
    async def fake_repo():
        return FakeJobsRepo()

    monkeypatch.setattr("app.routers.plan.get_generation_jobs_repo", fake_repo)
    monkeypatch.setattr("app.routers.plan.enqueue_job", fake_enqueue)
    monkeypatch.setattr("app.routers.plan.decompose", fail_decompose)

    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose", json=_decompose_body())
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "pending"
    assert body["enqueued"] == "ok"
    # persisted under the right op + carries the resolved args the bearer-less worker needs
    assert created["operation"] == "decompose_preview" and created["status"] == "pending"
    assert "chapters" in created["input"] and "cast" in created["input"]
    # the enqueued job is the persisted one (so GET /jobs/{id} can poll it)
    assert enqueued["job_id"] == str(job_id) and enqueued["project_id"] == str(PROJECT)


def test_decompose_preview_template_not_found_404(ctx, monkeypatch):
    c, _, _, _, _, templates = ctx
    templates.template = None
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose", json=_decompose_body())
    assert r.status_code == 404


def test_decompose_preview_no_chapters_400(ctx, monkeypatch):
    c, _, book, *_ = ctx
    book.chapters = []
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose", json=_decompose_body())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NO_CHAPTERS"


def test_decompose_preview_too_many_chapters_400(ctx, monkeypatch):
    c, *_ = ctx
    monkeypatch.setattr("app.routers.plan.settings.plan_max_chapters", 1)
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose", json=_decompose_body())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "TOO_MANY_CHAPTERS"


# ── commit ──

def _commit_body(**over):
    base = {"arc_title": "Arc", "chapters": [{
        "chapter_id": str(CH1), "title": "Ch 1", "intent": "open", "beat_role": "setup",
        "scenes": [{"title": "s1", "synopsis": "do", "tension": 80,
                    "present_entity_ids": [str(ENT)]}],
    }]}
    base.update(over)
    return base


def test_decompose_commit_persists_tree(ctx):
    c, _, _, _, outline, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=_commit_body())
    assert r.status_code == 201
    body = r.json()
    assert body["arc_id"] and len(body["chapter_ids"]) == 1 and len(body["scene_ids"]) == 1
    # the persist spec carried beat_role at the chapter level (repo stamps it on scenes)
    assert outline.created["chapters"][0]["beat_role"] == "setup"
    assert outline.created["chapters"][0]["scenes"][0]["tension"] == 80
    # story_order assigned = chapter.sort_order(1)*1000 + idx(0) — S1 state-reinjection
    # needs it (NULL would no-op the position-bound fallback). Regression-lock.
    assert outline.created["chapters"][0]["scenes"][0]["story_order"] == 1000


def test_decompose_commit_bad_chapter_idor_400(ctx):
    c, *_ = ctx
    other = str(uuid.uuid4())  # not one of the book's chapters
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
               json=_commit_body(chapters=[{"chapter_id": other, "scenes": []}]))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_CHAPTER"


def test_decompose_commit_empty_plan_400(ctx):
    # LOOM-73: a VALID chapter with NO scenes (the planner degraded — e.g. the
    # pre-LOOM-71 reasoning_effort 400 left every chapter empty) must be rejected
    # at commit with EMPTY_DECOMPOSE_PLAN, not silently committed (which would
    # surface only later as a mysterious NO_CHAPTER_PLAN at generate-time).
    c, _, _, _, outline, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
               json=_commit_body(chapters=[{"chapter_id": str(CH1), "title": "Ch 1",
                                            "intent": "open", "beat_role": "setup", "scenes": []}]))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "EMPTY_DECOMPOSE_PLAN"


# ── W2 motif persistence + swap endpoint ──

def test_decompose_commit_persists_motif_applications(ctx, monkeypatch):
    """A commit body carrying motif_application_rows persists them (one per bound
    scene), positionally mapped to the created scene nodes."""
    c, _, _, _, outline, _ = ctx
    captured = {}

    class _Apps:
        def __init__(self, pool): pass
        async def insert_many(self, p, b, rows, *, created_by=None, conn=None):
            captured["rows"] = rows
            return rows

    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", _Apps)
    monkeypatch.setattr("app.routers.plan.get_pool", lambda: object())

    motif_id = str(uuid.uuid4())
    body = _commit_body()
    body["chapters"][0]["motif_application_rows"] = [
        {"motif_id": motif_id, "motif_version": 2,
         "role_bindings": {"hero": str(ENT)}, "annotations": {"beat_key": "bait"}},
    ]
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 201
    assert r.json()["motif_applications"] == 1
    assert captured["rows"][0]["motif_id"] == motif_id
    assert captured["rows"][0]["annotations"]["beat_key"] == "bait"
    assert "outline_node_id" in captured["rows"][0]


def test_swap_endpoint_apply(ctx, monkeypatch):
    c, *_ = ctx
    from app.engine.motif_select import SwapResult

    class _FakeConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def transaction(self): return self

    class _FakePool:
        def acquire(self): return _FakeConn()

    monkeypatch.setattr("app.routers.plan.get_pool", lambda: _FakePool())
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: object())

    async def fake_apply(*a, **kw):
        return SwapResult(chapter_node_id="n", archived_scene_ids=["a"],
                          new_scene_ids=["b"], orphaned_thread_ids=["t"],
                          new_motif_id="m", undo_token={"chapter_node_id": "n"})

    # resolve the motif via a stubbed MotifRepo.get_visible
    from app.db.models import Motif

    async def fake_get_visible(self, u, mid):
        return Motif.model_validate({"id": mid, "owner_user_id": None, "code": "m",
                                     "name": "M", "kind": "scheme", "visibility": "unlisted",
                                     "status": "active", "version": 1, "roles": [], "beats": []})

    monkeypatch.setattr("app.routers.plan.apply_motif_swap", fake_apply)
    monkeypatch.setattr("app.db.repositories.motif_repo.MotifRepo.get_visible", fake_get_visible)

    node = str(uuid.uuid4())
    r = c.patch(f"/v1/composition/works/{PROJECT}/outline/{node}/motif",
                json={"motif_id": str(uuid.uuid4())})
    assert r.status_code == 200
    body = r.json()
    assert body["new_motif_id"] == "m"
    assert body["orphaned_thread_ids"] == ["t"]
    assert body["undo_token"] == {"chapter_node_id": "n"}


def test_swap_endpoint_undo(ctx, monkeypatch):
    c, _, _, _, outline, _ = ctx

    class _FakeConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def transaction(self): return self

    class _FakePool:
        def acquire(self): return _FakeConn()

    monkeypatch.setattr("app.routers.plan.get_pool", lambda: _FakePool())
    monkeypatch.setattr("app.routers.plan.MotifApplicationRepo", lambda pool: object())

    async def fake_undo(*a, **kw):
        return {"chapter_node_id": "n", "restored_scene_ids": ["a"], "removed_scene_ids": ["b"]}

    monkeypatch.setattr("app.routers.plan.undo_motif_swap", fake_undo)
    node = str(uuid.uuid4())
    r = c.patch(f"/v1/composition/works/{PROJECT}/outline/{node}/motif",
                json={"undo_token": {"chapter_node_id": "n", "archived_scene_ids": ["a"],
                                     "new_scene_ids": ["b"]}})
    assert r.status_code == 200
    assert r.json()["undone"] is True
    assert outline.created is None  # nothing committed


def test_decompose_commit_bad_entity_400(ctx):
    c, *_ = ctx
    body = _commit_body()
    body["chapters"][0]["scenes"][0]["present_entity_ids"] = [str(uuid.uuid4())]  # not in cast
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_ENTITY"


def test_decompose_commit_already_planned_guard_409_then_replace_201(ctx):
    c, _, _, _, outline, _ = ctx
    outline.existing = {CH1}  # CH1 already has scenes
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=_commit_body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CHAPTER_ALREADY_PLANNED"
    # replace=true archives the existing scenes + persists (true replace, not add)
    r2 = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
                json=_commit_body(replace=True))
    assert r2.status_code == 201 and outline.created["replace"] is True


def test_decompose_commit_force_alias_maps_to_replace(ctx):
    # `force` is the deprecated alias for `replace` (back-compat) → still archives.
    c, _, _, _, outline, _ = ctx
    outline.existing = {CH1}
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
               json=_commit_body(force=True))
    assert r.status_code == 201 and outline.created["replace"] is True


def test_decompose_commit_idempotency_key_replays(ctx):
    # D-A3-COMMIT-IDEMPOTENCY: a second commit with the same key replays the
    # original result instead of persisting a second tree.
    c, _, _, _, outline, _ = ctx
    r1 = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
                json=_commit_body(idempotency_key="k1"))
    assert r1.status_code == 201 and r1.json()["replay"] is False
    first_arc = r1.json()["arc_id"]
    outline.created = None  # prove the 2nd does NOT re-persist
    r2 = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
                json=_commit_body(idempotency_key="k1"))
    assert r2.status_code == 201 and r2.json()["replay"] is True
    assert r2.json()["arc_id"] == first_arc
    assert outline.created is None  # no second persist


def test_decompose_commit_reference_violation_maps_400(ctx):
    # a repo ReferenceViolationError (e.g. parent/ownership) → 400, not 500
    c, _, _, _, outline, _ = ctx
    from app.db.repositories import ReferenceViolationError

    async def boom(*a, **kw):
        raise ReferenceViolationError("bad parent")

    outline.commit_decomposed_tree = boom
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=_commit_body())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_REFERENCE"


def test_decompose_commit_rejects_out_of_range_tension_422(ctx):
    # author-edited tension beyond 0..100 → 422 (not a SMALLINT-overflow 500)
    c, *_ = ctx
    body = _commit_body()
    body["chapters"][0]["scenes"][0]["tension"] = 99999
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 422


def test_decompose_commit_entity_validation_skipped_on_glossary_outage(ctx):
    # KAL down (None) → empty roster → skip entity validation (don't false-reject)
    c, _, _, kal, _, _ = ctx
    kal.resp = None
    body = _commit_body()
    body["chapters"][0]["scenes"][0]["present_entity_ids"] = [str(uuid.uuid4())]
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 201  # not rejected — validation skipped on outage


def test_render_outline_plan_walks_tree_in_reading_order():
    """_render_outline_plan must WALK the tree, not iterate list_tree's flat (parent_id,
    rank) order. list_tree groups scene clusters by their parent chapter's UUID — NOT
    reading order — so a naive iteration detaches scenes from their chapters and orders
    the clusters arbitrarily. Here the flat list deliberately puts Ch2's scene BEFORE
    Ch1's scene (simulating the UUID sort); the render must still be Ch1→its scene→Ch2→its
    scene."""
    from types import SimpleNamespace

    from app.routers.plan import _render_outline_plan

    def node(nid, parent, kind, *, title="", goal="", beat_role=None, synopsis=""):
        return SimpleNamespace(id=nid, parent_id=parent, kind=kind, title=title,
                               goal=goal, beat_role=beat_role, synopsis=synopsis)

    arc, c1, c2 = "arc", "c1", "c2"
    # FLAT list as list_tree returns it: roots first, then children grouped by parent —
    # with Ch2's scene group BEFORE Ch1's (the UUID-ordering the bug depends on).
    nodes = [
        node(arc, None, "arc", title="Arc"),
        node(c1, arc, "chapter", title="Ch1", beat_role="hook", goal="a debt is owed"),
        node(c2, arc, "chapter", title="Ch2", goal="the reckoning"),
        node("s2", c2, "scene", synopsis="scene two body"),
        node("s1", c1, "scene", synopsis="scene one body"),
    ]
    out = _render_outline_plan(nodes)
    assert out == (
        "## Ch1 [hook]: a debt is owed\n"
        "- scene one body\n"
        "## Ch2: the reckoning\n"
        "- scene two body"
    )
    # each scene sits under ITS chapter, and Ch1 precedes Ch2 despite the flat mis-order.
    assert out.index("scene one body") < out.index("## Ch2")
