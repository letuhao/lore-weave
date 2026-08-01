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

from app.clients.book_client import BookClientError
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


# ── non-derivative: extracts into ITS OWN project ────────────────────────
#
# This test used to assert `dispatched is False` and `extract_calls == []`, and it was GREEN,
# and it was pinning the defect. The delta module's docstring says a greenfield Work "uses the
# event-driven path"; MEASURED 2026-08-01 there is no such path — `extract-item` had exactly
# one caller in the repo, behind this very branch. So a book written from scratch was never
# extracted, its knowledge graph stayed empty, and the canon guard, the LLM judge and the
# publish gate all checked every scene against nothing. The dogfood book: 15 chapters, 4
# published, a knowledge project that exists, and 0 :EntityStatus nodes.
#
# "The canon partition is untouched" was true and was the bug. What the C27 guard protects is
# a DERIVATIVE writing into its SOURCE's graph; a canon book writing into its own project is
# not that leak.


def test_approve_canon_work_extracts_into_its_own_project(ctx):
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()       # no source_work_id → not a derivative
    works.source = None
    bookc.sort_order = 5
    know.result = {"entities_merged": 2, "events_merged": 1, "facts_merged": 0}

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is True
    assert len(know.extract_calls) == 1, "a canon chapter must reach extraction"
    assert str(know.extract_calls[0]["project_id"]) == str(works.work.project_id),         "canon extraction targets the book's OWN project, never null and never a source"


def test_approve_forwards_the_chapters_reading_ORDINAL_so_status_effects_survive(ctx):
    """LIVE-SMOKE finding 2026-08-01 (throwaway book 019fbd8f…), the one that mattered most.

    The flywheel dispatched, extraction ran, 6 entities and 4 events landed — and
    `:EntityStatus` was **0**, on prose whose own extracted summary read "Castor falls and
    dies at the Bridge of Ash". `pass2_writer` skips every `status_effect` whose Event has no
    `event_order` (M2 — "no place on the reading axis"), and `event_order` comes from
    `chapter_index`, which this route never sent. So the liveness store the entire canon
    gone-cast guard reads was structurally unfillable from the authoring path.

    `chapter_sort_order` was already in hand three statements earlier — it decides
    forward-of-branch. The value existed; only the wire did not."""
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()
    works.source = None
    bookc.sort_order = 7
    know.result = {"entities_merged": 1, "events_merged": 1, "facts_merged": 0}

    assert _approve(client).status_code == 200
    assert know.extract_calls[0]["chapter_index"] == 7, (
        "without the reading ordinal every Event is positionless and knowledge DISCARDS "
        "its status_effects — the guard then checks a store nothing can fill"
    )


def test_approve_with_an_unplaceable_chapter_still_dispatches(ctx):
    """The counterweight: book-service being unreachable makes the ordinal None. That must
    degrade to positionless events (what happened before this field existed), never block the
    extraction — the approval is the author's action and it stands."""
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()
    works.source = None
    know.result = {"entities_merged": 1, "events_merged": 0, "facts_merged": 0}

    async def _no_orders(chapter_ids):
        raise BookClientError("book-service down", "BOOK_SERVICE_UNAVAILABLE")
    bookc.get_chapter_sort_orders = _no_orders

    assert _approve(client).json()["dispatched"] is True
    assert know.extract_calls[0]["chapter_index"] is None


def test_approve_canon_dispatch_REPORTS_the_canon_path_not_the_delta_one(ctx):
    """LIVE-SMOKE finding 2026-08-01 (throwaway book 019fbd8f…): the dispatch was right and
    every word describing it was wrong. The success return was hardcoded to `decision.*` — the
    DELTA decision — whose fields are all None on a canon Work. A real 200 came back as

        {"dispatched": true, "reason": "not_a_derivative", "source_project_id": "None"}

    i.e. the one field that tells an operator WHICH path ran named the path that did not run,
    and a Python None was str()'d into JSON as the four-character string "None". The unit tests
    asserted `dispatched` and the extract call's project, so both passed.

    `project_id` was accidentally correct — `plan_flywheel_dispatch` echoes its input back — so
    it is asserted here against the canon decision's own value, not left to that coincidence."""
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()
    works.source = None
    bookc.sort_order = 5
    know.result = {"entities_merged": 4, "events_merged": 2, "facts_merged": 0}

    body = _approve(client).json()
    assert body["dispatched"] is True
    assert body["reason"] == "canon_dispatch", "the reason must name the path that actually ran"
    assert body["project_id"] == str(works.work.project_id)
    assert body["source_project_id"] is None, "a canon Work has no source; null, never the string 'None'"


def test_approve_derivative_still_reports_the_delta_path(ctx):
    """The counterweight: without it, "always say canon" satisfies the test above and the
    derivative path — the one this route was built for — starts lying instead."""
    client, works, derivs, bookc, know = ctx
    works.work = _derivative_work(branch_point=4)
    works.source = _canon_work(project_id=SOURCE_PROJECT)
    bookc.sort_order = 5
    know.result = {"entities_merged": 1, "events_merged": 0, "facts_merged": 0}

    body = _approve(client).json()
    assert body["reason"] == "delta_dispatch", body["reason"]
    assert body["project_id"] == str(DELTA)
    assert body["source_project_id"] == str(SOURCE_PROJECT)


def test_approve_canon_knowledge_outage_names_the_books_own_project(ctx):
    """The outage return had the same defect: `str(decision.delta_project_id)` → "None" for a
    canon Work, so the one line telling the author which project failed to enrich named none."""
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()
    works.source = None
    bookc.sort_order = 5
    know.result = None  # knowledge down

    body = _approve(client).json()
    assert body["dispatched"] is False
    assert body["reason"] == "knowledge_unavailable"
    assert body["project_id"] == str(works.work.project_id)


def test_approve_canon_work_with_a_null_project_refuses(ctx):
    """The C23 leak guard, kept for the canon path too: a null project_id widens a knowledge
    write to ALL of a user's projects. Refuse rather than dispatch unscoped."""
    client, works, derivs, bookc, know = ctx
    works.work = _canon_work()
    works.work.project_id = None
    works.source = None
    bookc.sort_order = 5

    r = _approve(client)
    assert r.status_code == 200, r.text
    assert r.json()["dispatched"] is False
    assert r.json()["reason"] == "unscoped_project"
    assert know.extract_calls == []


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
