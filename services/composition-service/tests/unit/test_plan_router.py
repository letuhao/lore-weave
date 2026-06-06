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
        self.work = CompositionWork(project_id=PROJECT, user_id=USER, book_id=BOOK, settings={})
    async def get(self, u, p):
        return self.work


class StubBook:
    def __init__(self):
        self.chapters = [
            {"chapter_id": CH1, "title": "Ch 1", "sort_order": 1},
            {"chapter_id": CH2, "title": "Ch 2", "sort_order": 2},
        ]
    async def list_chapters(self, book_id, bearer, *, limit=200):
        return self.chapters


class StubGlossary:
    def __init__(self):
        self.resp = {"items": [{"entity_id": str(ENT), "name": "Alice"}], "next_cursor": None}
    async def list_entities(self, book_id, *, limit=100, cursor=None):
        return self.resp


class StubOutline:
    def __init__(self):
        self.existing: set = set()
        self.created = None
    async def existing_scene_chapter_ids(self, u, p, ids):
        return self.existing
    async def create_decomposed_tree(self, u, p, *, arc_title, chapters):
        self.created = {"arc_title": arc_title, "chapters": chapters}
        return {"arc_id": uuid.uuid4(),
                "chapter_ids": [uuid.uuid4() for _ in chapters],
                "scene_ids": [uuid.uuid4() for ch in chapters for _ in ch["scenes"]]}


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
    from app.deps import (get_book_client_dep, get_glossary_client_dep, get_llm_client_dep,
                          get_outline_repo, get_structure_templates_repo, get_works_repo)
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works, book, glossary, outline, templates = (
        StubWorks(), StubBook(), StubGlossary(), StubOutline(), StubTemplates())
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_glossary_client_dep] = lambda: glossary
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_structure_templates_repo] = lambda: templates
    app.dependency_overrides[get_llm_client_dep] = lambda: object()
    with TestClient(app) as c:
        yield c, works, book, glossary, outline, templates
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


def test_decompose_commit_bad_entity_400(ctx):
    c, *_ = ctx
    body = _commit_body()
    body["chapters"][0]["scenes"][0]["present_entity_ids"] = [str(uuid.uuid4())]  # not in cast
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_ENTITY"


def test_decompose_commit_already_planned_guard_409_then_force_201(ctx):
    c, _, _, _, outline, _ = ctx
    outline.existing = {CH1}  # CH1 already has scenes
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=_commit_body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CHAPTER_ALREADY_PLANNED"
    # force=true adds anyway (does NOT replace — documented)
    r2 = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit",
                json=_commit_body(force=True))
    assert r2.status_code == 201


def test_decompose_commit_reference_violation_maps_400(ctx):
    # a repo ReferenceViolationError (e.g. parent/ownership) → 400, not 500
    c, _, _, _, outline, _ = ctx
    from app.db.repositories import ReferenceViolationError

    async def boom(*a, **kw):
        raise ReferenceViolationError("bad parent")

    outline.create_decomposed_tree = boom
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
    # glossary down (None) → empty roster → skip entity validation (don't false-reject)
    c, _, _, glossary, _, _ = ctx
    glossary.resp = None
    body = _commit_body()
    body["chapters"][0]["scenes"][0]["present_entity_ids"] = [str(uuid.uuid4())]
    r = c.post(f"/v1/composition/works/{PROJECT}/outline/decompose/commit", json=body)
    assert r.status_code == 201  # not rejected — validation skipped on outage
