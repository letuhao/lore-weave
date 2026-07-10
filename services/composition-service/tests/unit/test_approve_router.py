"""C27 (dị bản M4) — approve-chapter → delta-flywheel ROUTER tests.

End-to-end through the FastAPI handler (TestClient + dependency_overrides), the
SAME stub pattern as test_routers.py. Proves the wiring the pure-logic tests
(test_delta_flywheel.py) can't: the extract-item dispatch targets the DERIVATIVE's
OWN project_id, the GUARD surfaces as a 409 on a null delta, a non-derivative /
pre-branch chapter is a clean no-op, and a knowledge outage doesn't 500 the
approval.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork

USER = uuid.uuid4()
BOOK = uuid.uuid4()
DELTA = uuid.uuid4()    # the derivative's OWN project (the delta partition)
SOURCE_PROJECT = uuid.uuid4()
SOURCE_WORK_ID = uuid.uuid4()
CHAPTER = uuid.uuid4()


def _derivative_work(**kw) -> CompositionWork:
    """A derivative Work: source_work_id + branch_point set, its OWN project_id."""
    return CompositionWork(
        project_id=kw.get("project_id", DELTA), created_by=USER, book_id=BOOK,
        id=kw.get("id", uuid.uuid4()), version=1, status="active",
        source_work_id=kw.get("source_work_id", SOURCE_WORK_ID),
        branch_point=kw.get("branch_point", 4),
    )


def _canon_work(**kw) -> CompositionWork:
    return CompositionWork(
        project_id=kw.get("project_id", DELTA), created_by=USER, book_id=BOOK,
        id=uuid.uuid4(), version=1, status="active",
    )


class StubWorks:
    def __init__(self, work=None, source=None):
        self.work = work
        self.source = source

    async def get(self, project_id):
        return self.work

    async def get_by_id(self, work_id):
        # build_derivative_context resolves the BASE project via source_work_id.
        return self.source


class StubDerivatives:
    def __init__(self, overrides=None):
        self._overrides = overrides or []

    async def list_overrides_for_work(self, work_id):
        return list(self._overrides)


class StubBook:
    def __init__(self, sort_order=5, body=None):
        self.sort_order = sort_order
        self.body = body if body is not None else {
            "type": "doc",
            "content": [{"type": "paragraph", "_text": "张若尘 is now a woman."}],
        }

    async def get_chapter_sort_orders(self, chapter_ids):
        return {str(c): self.sort_order for c in chapter_ids}

    async def get_draft(self, book_id, chapter_id, bearer):
        return {"chapter_id": str(chapter_id), "body": self.body, "draft_version": 3}


class StubKnowledge:
    def __init__(self, result=None):
        self.result = result
        self.extract_calls = []

    async def extract_item(self, **kw):
        self.extract_calls.append(kw)
        return self.result


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (
        get_book_client_dep,
        get_derivatives_repo,
        get_grant_client_dep,
        get_knowledge_client_dep,
        get_works_repo,
    )
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER

    works = StubWorks()
    derivs = StubDerivatives()
    bookc = StubBook()
    know = StubKnowledge()

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "tok"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_derivatives_repo] = lambda: derivs
    app.dependency_overrides[get_book_client_dep] = lambda: bookc
    app.dependency_overrides[get_knowledge_client_dep] = lambda: know
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()

    client = TestClient(app)
    yield client, works, derivs, bookc, know
    app.dependency_overrides.clear()


def _approve(client, project=DELTA, chapter=CHAPTER):
    return client.post(
        f"/v1/composition/works/{project}/chapters/{chapter}/approve",
        json={"model_source": "user_model", "model_ref": str(uuid.uuid4())},
    )


# ── happy path: extraction targets the DERIVATIVE's OWN delta project ─────


def test_approve_derivative_chapter_extracts_into_delta_project(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)
    # source Work (base project) resolved via source_work_id → its project_id.
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 5  # forward of branch 4
    know.result = {"entities_merged": 3, "events_merged": 1, "facts_merged": 2}

    r = _approve(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispatched"] is True
    # CRITICAL (G2): the extraction targeted the DERIVATIVE's OWN project, the DELTA.
    assert len(know.extract_calls) == 1
    call = know.extract_calls[0]
    assert call["project_id"] == DELTA
    assert call["project_id"] != SOURCE_PROJECT
    assert body["project_id"] == str(DELTA)
    # the chapter prose was flattened + forwarded.
    assert "张若尘" in call["chapter_text"]


# ── GUARD: null delta project on a forward derivative chapter → 409 ───────


def test_approve_null_delta_project_is_refused_409(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(project_id=None, branch_point=4)  # null DELTA
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 5  # forward of branch → would dispatch but for the guard

    r = _approve(client, project=DELTA)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "DELTA_PROJECT_UNSCOPED"
    # NEVER dispatched into a null/all-projects scope.
    assert know.extract_calls == []


# ── non-derivative: clean no-op, never touches the canon partition ───────


def test_approve_canon_work_is_clean_no_op(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()       # no source_work_id → not a derivative
    works.source = None
    bookc.sort_order = 5

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "not_a_derivative"
    assert know.extract_calls == []  # canon partition untouched


# ── out-of-order (pre-branch) chapter → thinner delta, not an error ──────


def test_approve_pre_branch_chapter_yields_thinner_delta(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 2  # BEFORE the branch → inherited base, not delta

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "pre_branch_thinner_delta"
    assert know.extract_calls == []  # graceful skip, no extraction


# ── knowledge outage: approval stands, flywheel didn't enrich ────────────


def test_approve_survives_knowledge_outage_no_500(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 5
    know.result = None  # extract_item degrades to None on a knowledge outage

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "knowledge_unavailable"


# ── empty chapter: no dispatch ───────────────────────────────────────────


def test_approve_empty_chapter_no_dispatch(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 5
    bookc.body = {"type": "doc", "content": []}  # empty prose

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "empty_chapter"
    assert know.extract_calls == []


# ── derivative whose SOURCE is unresolvable (deleted) → observable skip ───


def test_approve_derivative_with_unresolved_source_is_observable_skip(ctx):
    # the Work IS a derivative (source_work_id set) but its source Work was deleted
    # → build_derivative_context resolves source_project_id=None. Must NOT be
    # silently mislabeled `not_a_derivative`; surface `source_unresolved` instead,
    # and NEVER dispatch (can't scope the base).
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)  # source_work_id set
    works.source = None                            # source Work deleted → unresolved
    bookc.sort_order = 5

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "source_unresolved"
    assert know.extract_calls == []


# ── work not found → 404 ─────────────────────────────────────────────────


def test_approve_work_not_found_404(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = None

    r = _approve(client)
    assert r.status_code == 404
