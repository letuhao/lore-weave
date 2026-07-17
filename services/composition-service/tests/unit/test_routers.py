"""M3 router tests — works resolve/CRUD + prose proxy (TestClient + overrides).

Lifespan DB wiring is stubbed (M0 pattern); auth + repos + clients are injected
via dependency_overrides so the tests exercise router logic, status mapping, and
the OI-2 mandatory-version guard without a live stack.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.clients.book_client import BookClientError
from app.db.models import CompositionWork, DivergenceSpec, EntityOverride
from app.db.repositories import ReferenceViolationError, VersionMismatchError

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
CHAPTER = uuid.uuid4()


def _work(**kw) -> CompositionWork:
    return CompositionWork(project_id=kw.get("project_id", PROJECT), created_by=USER,
                           book_id=BOOK, id=kw.get("id", uuid.uuid4()),
                           version=kw.get("version", 1),
                           status=kw.get("status", "active"))


def _pending_work(**kw) -> CompositionWork:
    """C16: a lazy greenfield Work — null project_id, backfill marker set."""
    return CompositionWork(project_id=None, created_by=USER,
                           book_id=kw.get("book_id", BOOK),
                           id=kw.get("id", uuid.uuid4()),
                           pending_project_backfill=True)


class StubWorks:
    def __init__(self):
        self.work = None
        self.marked = []
        self.update_result = None
        self.update_raises = None
        self.create_raises = None
        self.get_results = None  # if a list, pop per call (for the conflict test)
        # C16 backfill seam
        self.pending = None            # get_pending_for_book result
        self.create_pending_raises = None
        self.created_pending = False
        self.backfilled_with = None    # (work_id, project_id) on backfill
        self.backfill_result = None
        self.backfill_raises = None    # set to an exc to simulate a unique race
        # D-C16: id-addressable resolve
        self.by_id_result = None
        self.by_id_results = None      # if a list, pop per get_by_id call

    async def get_by_id(self, work_id):
        if self.by_id_results is not None:
            return self.by_id_results.pop(0) if self.by_id_results else None
        return self.by_id_result

    async def get(self, project_id):
        if self.get_results is not None:
            return self.get_results.pop(0) if self.get_results else None
        return self.work

    async def resolve_by_book(self, book_id):
        return self.marked

    async def scope_meta(self, project_id):
        # PM-8 ids-only scope row for the E0 book gate (book_id_for_project).
        # Derived from the stubbed work: None → uniform 404 at the gate.
        from app.db.repositories.works import WorkScopeMeta
        if self.work is None:
            return None
        return WorkScopeMeta(
            book_id=self.work.book_id, work_id=self.work.id, project_id=project_id,
        )

    async def update(self, project_id, patch, *, created_by=None, expected_version=None):
        if self.update_raises:
            raise self.update_raises
        return self.update_result

    async def create(self, created_by, project_id, book_id, **kw):
        if self.create_raises:
            raise self.create_raises
        self.created_with = (project_id, book_id)
        return _work(project_id=project_id)

    # C23 (dị bản) derivative create
    async def create_derivative(self, created_by, project_id, book_id, source_work_id,
                                *, branch_point=None, settings=None, conn=None):
        self.derived_with = {"project_id": project_id, "book_id": book_id,
                             "source_work_id": source_work_id, "branch_point": branch_point}
        w = _work(project_id=project_id)
        w.source_work_id = source_work_id
        w.branch_point = branch_point
        return w

    # C16 (WG-3) lazy null-project + backfill
    async def create_pending(self, created_by, book_id, **kw):
        if self.create_pending_raises:
            raise self.create_pending_raises
        self.created_pending = True
        return _pending_work(book_id=book_id)

    async def get_pending_for_book(self, book_id):
        return self.pending

    async def backfill_project(self, work_id, project_id, *, created_by=None):
        self.backfilled_with = (work_id, project_id)
        if self.backfill_raises:
            raise self.backfill_raises
        return self.backfill_result


class StubDerivatives:
    def __init__(self):
        self.specs = []
        self.overrides = []
        # WS-B2 read seams — what the derivative-context endpoint reads back.
        self.spec_for_work = None
        self.overrides_for_work = []

    async def create_spec(self, spec, *, conn=None):
        self.specs.append(spec)
        return spec

    async def create_override(self, override, *, conn=None):
        self.overrides.append(override)
        return override

    async def get_spec_for_work(self, work_id):
        return self.spec_for_work

    async def list_overrides_for_work(self, work_id):
        return self.overrides_for_work

    # S-04 post-derive editing seams
    async def update_spec(self, work_id, book_id, **kwargs):
        self.update_spec_call = (work_id, book_id, kwargs)
        if getattr(self, "update_spec_raises", None):
            raise self.update_spec_raises
        return getattr(self, "update_spec_result", None)

    async def add_override(self, work_id, book_id, created_by, target_entity_id,
                           overridden_fields, *, conn=None):
        self.add_override_call = (work_id, book_id, created_by, target_entity_id,
                                  overridden_fields)
        if getattr(self, "add_override_raises", None):
            raise self.add_override_raises
        return getattr(self, "add_override_result", None)

    async def update_override(self, work_id, book_id, override_id, overridden_fields, *, conn=None):
        self.update_override_call = (work_id, book_id, override_id, overridden_fields)
        return getattr(self, "update_override_result", None)

    async def delete_override(self, work_id, book_id, override_id, *, conn=None):
        self.delete_override_call = (work_id, book_id, override_id)
        return getattr(self, "delete_override_result", False)


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def transaction(self):
        return _FakeTxn()


class _FakeAcquire:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *a):
        return False


class _FakePool:
    """A no-op pool so the derive endpoint's txn-local writes run against stub repos
    (the repos ignore `conn` here — they just record what they were asked to write)."""

    def acquire(self):
        return _FakeAcquire()


class StubKnowledge:
    def __init__(self, projects=None):
        self.projects = projects
        self.created_project = None  # set to a dict to simulate create_project
        self.create_project_raises = None  # set to an exc to simulate a 4xx contract error

    async def list_projects_for_book(self, book_id, bearer):
        return self.projects

    async def create_project(self, book_id, name, bearer, *, force_new=False):
        self.create_project_name = name
        self.create_project_force_new = force_new
        if self.create_project_raises is not None:
            raise self.create_project_raises
        return self.created_project


class StubBook:
    def __init__(self):
        self.draft = {"chapter_id": str(CHAPTER), "body": {"x": 1}, "draft_version": 5}
        self.revisions = {"items": [{"revision_id": "rev-1"}], "total": 1}
        self.patch_result = {"chapter_id": str(CHAPTER), "draft_version": 6}
        self.get_raises = None
        self.patch_raises = None
        self.patched_with = None
        self.book = {"title": "Demo Book"}  # get_book result (None → 404)
        self.get_book_raises = None

    async def get_book(self, book_id, bearer):
        if self.get_book_raises:
            raise self.get_book_raises
        return self.book

    async def get_draft(self, book_id, chapter_id, bearer):
        if self.get_raises:
            raise self.get_raises
        return dict(self.draft)

    async def list_revisions(self, book_id, chapter_id, bearer, *, limit=1):
        return self.revisions

    async def patch_draft(self, book_id, chapter_id, bearer, *, body, expected_draft_version, body_format=None, commit_message=None):
        self.patched_with = {"body": body, "expected_draft_version": expected_draft_version,
                             "body_format": body_format, "commit_message": commit_message}
        if self.patch_raises:
            raise self.patch_raises
        return dict(self.patch_result)


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

    # C23: the derive endpoint opens a txn via app.routers.works.get_pool — point it
    # at a no-op fake pool so the stubbed repos record the writes without a real DB.
    monkeypatch.setattr("app.routers.works.get_pool", lambda: _FakePool())

    # E0-4c: stub the book-grant authority at OWNER so the collaboration gate
    # passes; the gate's deny paths (404/403) are covered in test_grant_gate.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, knowledge, book = StubWorks(), StubKnowledge(), StubBook()
    derivatives = StubDerivatives()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_derivatives_repo] = lambda: derivatives
    app.dependency_overrides[get_knowledge_client_dep] = lambda: knowledge
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, works, knowledge, book, derivatives
    app.dependency_overrides.clear()


# ── works resolve ──

def test_resolve_found(ctx):
    c, works, _, _, _ = ctx
    works.marked = [_work()]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "found" and body["work"]["project_id"] == str(PROJECT)


def test_post_work_book_not_found_404(ctx):
    c, _, _, book, _ = ctx
    book.book = None
    assert c.post(f"/v1/composition/books/{BOOK}/work").status_code == 404


def test_post_work_idempotent_when_already_marked(ctx):
    c, works, _, _, _ = ctx
    works.marked = [_work()]  # resolve → found
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201 and r.json()["project_id"] == str(PROJECT)


def test_post_work_creates_project_when_none(ctx):
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []  # resolve → none
    new_pid = uuid.uuid4()
    knowledge.created_project = {"project_id": str(new_pid)}
    works.work = None  # no existing composition_work for the new project
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201
    assert knowledge.create_project_name == "Demo Book"  # named from the book title
    assert works.created_with == (new_pid, BOOK)  # work created on the new project


# ── C16 (WG-3) Work-setup resilience ──

def test_post_work_2xx_when_create_project_down(ctx):
    # WG-3: knowledge OUTAGE (create_project None) for a GREENFIELD work → NOT 502;
    # a lazy null-project Work is persisted so the writer keeps drafting.
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []           # resolve → none (greenfield)
    knowledge.created_project = None  # outage
    works.pending = None              # no prior pending row
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201
    assert works.created_pending is True
    body = r.json()
    assert body["project_id"] is None                 # null project_id (greenfield)
    assert body["pending_project_backfill"] is True   # backfill marker set


def test_post_work_null_project_is_greenfield_only_marker(ctx):
    # The resulting Work carries the null project_id + pending marker (the exact
    # acceptance shape) and an addressable surrogate id.
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []
    knowledge.created_project = None
    works.pending = None
    body = c.post(f"/v1/composition/books/{BOOK}/work").json()
    assert body["project_id"] is None and body["pending_project_backfill"] is True
    assert body["id"] is not None


def test_post_work_derivative_rejected_on_null_project(ctx):
    # C23 GUARD: a DERIVATIVE work (source_work_id) must NOT take the null path —
    # a knowledge outage surfaces as 502, never a grounding-blind derivative.
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []
    knowledge.created_project = None  # outage
    r = c.post(f"/v1/composition/books/{BOOK}/work",
               json={"source_work_id": str(uuid.uuid4())})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "PROJECT_CREATE_FAILED"
    assert works.created_pending is False  # never minted a null derivative


def test_post_work_2xx_when_knowledge_down_resolve_unavailable(ctx):
    # WG-3 live-smoke shape: knowledge-service fully DOWN → resolve returns
    # `unavailable` (list_projects None). A GREENFIELD POST /work must still 2xx with
    # a lazy null-project Work (was a 502 KNOWLEDGE_UNAVAILABLE before C16).
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = None  # list_projects_for_book None → resolve 'unavailable'
    works.pending = None
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201
    assert works.created_pending is True
    body = r.json()
    assert body["project_id"] is None and body["pending_project_backfill"] is True


def test_post_work_derivative_502_when_knowledge_down(ctx):
    # C23 guard on the unavailable path too: a derivative still 502s (never a null Work).
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = None  # resolve 'unavailable'
    r = c.post(f"/v1/composition/books/{BOOK}/work",
               json={"source_work_id": str(uuid.uuid4())})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "KNOWLEDGE_UNAVAILABLE"
    assert works.created_pending is False


def test_post_work_4xx_contract_error_surfaces(ctx):
    # No silent swallow: a 4xx CONTRACT error from create_project still 502s
    # (only down/timeout/5xx degrade).
    from app.clients.knowledge_client import KnowledgeContractError
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []
    knowledge.create_project_raises = KnowledgeContractError(422)
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "PROJECT_CREATE_FAILED"
    assert works.created_pending is False  # 4xx is NOT degraded into a lazy Work


def test_post_work_reuses_existing_pending_on_repeat_outage(ctx):
    # A second setup during a continuing outage re-gets the SAME lazy Work (idempotent,
    # no duplicate) rather than spawning another.
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []
    knowledge.created_project = None
    works.pending = _pending_work()
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201
    assert works.created_pending is False  # reused, not re-created
    assert r.json()["project_id"] is None


def test_post_work_backfills_pending_when_knowledge_recovers(ctx):
    # Backfill seam: knowledge recovered → the freshly-created project is stamped onto
    # the prior lazy Work (marker cleared), not a second Work.
    c, works, knowledge, _, _ = ctx
    works.marked = []
    knowledge.projects = []           # resolve → none
    new_pid = uuid.uuid4()
    knowledge.created_project = {"project_id": str(new_pid)}
    pend = _pending_work()
    works.pending = pend
    works.backfill_result = _work(project_id=new_pid, id=pend.id)
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201
    assert works.backfilled_with == (pend.id, new_pid)
    body = r.json()
    assert body["project_id"] == str(new_pid)
    assert body["pending_project_backfill"] is False


# ── D-C16: id-addressable resolve + self-healing backfill ──


def test_get_work_by_id_returns_pending_work(ctx):
    c, works, _, _, _ = ctx
    pend = _pending_work()
    works.by_id_result = pend
    r = c.get(f"/v1/composition/works/by-id/{pend.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] is None
    assert body["pending_project_backfill"] is True


def test_get_work_by_id_404_when_missing(ctx):
    c, works, _, _, _ = ctx
    works.by_id_result = None
    r = c.get(f"/v1/composition/works/by-id/{uuid.uuid4()}")
    assert r.status_code == 404


def test_resolve_project_backfills_when_knowledge_recovers(ctx):
    c, works, knowledge, book, _ = ctx
    pend = _pending_work()
    works.by_id_result = pend
    new_pid = uuid.uuid4()
    knowledge.created_project = {"project_id": str(new_pid)}
    works.backfill_result = _work(project_id=new_pid, id=pend.id)
    r = c.post(f"/v1/composition/works/by-id/{pend.id}/resolve-project")
    assert r.status_code == 200
    assert works.backfilled_with == (pend.id, new_pid)
    body = r.json()
    assert body["project_id"] == str(new_pid)
    assert body["pending_project_backfill"] is False


def test_resolve_project_still_pending_when_knowledge_down(ctx):
    c, works, knowledge, _, _ = ctx
    pend = _pending_work()
    works.by_id_result = pend
    knowledge.created_project = None  # still down
    r = c.post(f"/v1/composition/works/by-id/{pend.id}/resolve-project")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "STILL_PENDING"
    assert works.backfilled_with is None  # never stamped a project


def test_resolve_project_idempotent_when_already_backed(ctx):
    c, works, knowledge, _, _ = ctx
    backed = _work(project_id=uuid.uuid4(), id=uuid.uuid4())  # has project_id
    works.by_id_result = backed
    r = c.post(f"/v1/composition/works/by-id/{backed.id}/resolve-project")
    assert r.status_code == 200
    assert works.backfilled_with is None  # short-circuits before create/backfill


def test_resolve_project_contract_error_surfaces_502(ctx):
    c, works, knowledge, _, _ = ctx
    from app.clients.knowledge_client import KnowledgeContractError
    pend = _pending_work()
    works.by_id_result = pend
    knowledge.create_project_raises = KnowledgeContractError(422)
    r = c.post(f"/v1/composition/works/by-id/{pend.id}/resolve-project")
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "PROJECT_CREATE_FAILED"
    assert works.backfilled_with is None


def test_resolve_project_404_when_work_missing(ctx):
    c, works, _, _, _ = ctx
    works.by_id_result = None
    r = c.post(f"/v1/composition/works/by-id/{uuid.uuid4()}/resolve-project")
    assert r.status_code == 404


def test_resolve_project_unique_violation_returns_resolved_not_500(ctx):
    # Review #2: if backfill hits a unique race (a concurrent backed row already
    # holds the canonical project), don't 500 — re-read and return the resolved
    # state. (The one-Work-per-book invariant makes this unreachable in practice.)
    c, works, knowledge, _, _ = ctx
    pend = _pending_work()
    new_pid = uuid.uuid4()
    backed = _work(project_id=new_pid, id=pend.id)
    works.by_id_results = [pend, backed]  # first get → pending; re-read → backed
    knowledge.created_project = {"project_id": str(new_pid)}
    works.backfill_raises = asyncpg.UniqueViolationError("dup project")
    r = c.post(f"/v1/composition/works/by-id/{pend.id}/resolve-project")
    assert r.status_code == 200
    assert r.json()["project_id"] == str(new_pid)


def test_post_work_unique_violation_reresolves(ctx):
    # /review-impl M8 #2: a concurrent same-project POST loses the PK race →
    # catch UniqueViolation, re-get, return the racey Work (not a 500).
    c, works, knowledge, _, _ = ctx
    works.marked = []
    pid = uuid.uuid4()
    knowledge.projects = [{"project_id": str(pid), "project_type": "book", "book_id": str(BOOK), "is_archived": False}]
    works.get_results = [None, _work(project_id=pid)]  # first get None → create; re-get → the winner's row
    works.create_raises = asyncpg.UniqueViolationError("dup")
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201 and r.json()["project_id"] == str(pid)


def test_post_work_binds_existing_unmarked_book_project(ctx):
    c, works, knowledge, _, _ = ctx
    works.marked = []
    pid = uuid.uuid4()
    knowledge.projects = [{"project_id": str(pid), "project_type": "general", "book_id": str(BOOK), "is_archived": False}]
    works.work = None
    r = c.post(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 201 and works.created_with[0] == pid  # bound to the existing project, no create_project


def test_resolve_unmarked_single_from_knowledge(ctx):
    c, works, knowledge, _, _ = ctx
    works.marked = []
    pid = uuid.uuid4()
    knowledge.projects = [{"project_id": str(pid), "project_type": "general", "book_id": str(BOOK), "is_archived": False}]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    assert r.json()["status"] == "unmarked_single"
    assert r.json()["book_project_id"] == str(pid)


def test_resolve_candidates_serializes_marked_works(ctx):
    c, works, _, _, _ = ctx
    w1, w2 = _work(project_id=uuid.uuid4()), _work(project_id=uuid.uuid4())
    works.marked = [w1, w2]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    body = r.json()
    assert body["status"] == "candidates"
    assert {w["project_id"] for w in body["candidates"]} == {str(w1.project_id), str(w2.project_id)}


# ── C23 (dị bản) derive ──

def _derive_body(**kw):
    body = {
        "branch_point": kw.get("branch_point", 7),
        "divergence": kw.get("divergence", {"taxonomy": "pov_shift",
                                            "pov_anchor": str(uuid.uuid4()),
                                            "canon_rule": ["The hero dies"]}),
        "entity_overrides": kw.get("entity_overrides",
                                   [{"target_entity_id": str(uuid.uuid4()),
                                     "overridden_fields": {"role": "villain"}}]),
    }
    return body


def test_derive_creates_linked_work_with_fresh_project(ctx):
    """The derivative links to the source (source_work_id) at the branch_point and
    gets its OWN fresh project_id (G2) — NEVER the source's."""
    c, works, knowledge, book, _ = ctx
    source = _work(project_id=PROJECT)
    works.work = source  # works.get(...) returns the source
    fresh = uuid.uuid4()
    knowledge.created_project = {"project_id": str(fresh)}
    r = c.post(f"/v1/composition/works/{PROJECT}/derive", json=_derive_body(branch_point=4))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_work_id"] == str(source.id)
    assert body["branch_point"] == 4
    assert body["project_id"] == str(fresh)        # fresh project provisioned
    assert body["project_id"] != str(PROJECT)      # NOT the source's project (G2)
    # C23-fix: derive MUST request force_new=True so knowledge skips its
    # per-(user,book) dedup and mints a DISTINCT is_derivative project — without
    # it a source book that already had a project returned the SOURCE's
    # project_id → uq_composition_work_project 500 (the bug this unblocks).
    assert knowledge.create_project_force_new is True
    # the repo was asked to write a derivative bound to the source + fresh project
    assert works.derived_with["source_work_id"] == source.id
    assert works.derived_with["project_id"] == fresh
    # NO chapter clone (COW): the source reference spine is untouched — only get_book
    # was read; no draft write/clone fired (StubBook records patched_with on a clone).
    assert book.patched_with is None


def test_derive_persists_spec_and_overrides(ctx):
    c, works, knowledge, _, derivatives = ctx
    works.work = _work(project_id=PROJECT)
    knowledge.created_project = {"project_id": str(uuid.uuid4())}
    target = uuid.uuid4()
    body = _derive_body(
        divergence={"taxonomy": "character_transform", "pov_anchor": None,
                    "canon_rule": ["No magic", "Set in space"]},
        entity_overrides=[{"target_entity_id": str(target),
                           "overridden_fields": {"alive": False, "role": "antagonist"}}],
    )
    r = c.post(f"/v1/composition/works/{PROJECT}/derive", json=body)
    assert r.status_code == 201, r.text
    assert len(derivatives.specs) == 1
    spec = derivatives.specs[0]
    assert spec.taxonomy == "character_transform"
    assert spec.canon_rule == ["No magic", "Set in space"]
    assert len(derivatives.overrides) == 1
    ov = derivatives.overrides[0]
    assert ov.target_entity_id == target
    assert ov.overridden_fields == {"alive": False, "role": "antagonist"}


def test_derive_rejects_when_project_cannot_be_provisioned(ctx):
    """GUARD: a derivative MUST get a NOT-NULL project_id. If knowledge can't mint one
    (outage → None), REJECT (4xx/5xx) — NEVER degrade to a null-project derivative."""
    c, works, knowledge, _, derivatives = ctx
    works.work = _work(project_id=PROJECT)
    knowledge.created_project = None  # outage
    r = c.post(f"/v1/composition/works/{PROJECT}/derive", json=_derive_body())
    assert r.status_code == 503
    # NOTHING persisted on the reject path
    assert works.__dict__.get("derived_with") is None
    assert derivatives.specs == [] and derivatives.overrides == []


def test_derive_rejects_on_contract_error(ctx):
    """A 4xx contract error from knowledge → 502 PROJECT_CREATE_FAILED (no null path)."""
    from app.clients.knowledge_client import KnowledgeContractError
    c, works, knowledge, _, _ = ctx
    works.work = _work(project_id=PROJECT)
    knowledge.create_project_raises = KnowledgeContractError(422)
    r = c.post(f"/v1/composition/works/{PROJECT}/derive", json=_derive_body())
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "PROJECT_CREATE_FAILED"


# ── S-04: derivative delta EDITING (spec PATCH + entity_override CRUD) ──

def _deriv_work(**kw):
    """A DERIVATIVE Work (source_work_id set) — the only kind with a spec/overrides."""
    w = _work(**kw)
    w.source_work_id = kw.get("source_work_id", uuid.uuid4())
    return w


def _spec(**kw):
    return DivergenceSpec(
        id=kw.get("id", uuid.uuid4()), created_by=USER, project_id=PROJECT,
        work_id=kw.get("work_id", uuid.uuid4()),
        taxonomy=kw.get("taxonomy", "au"), pov_anchor=kw.get("pov_anchor"),
        canon_rule=kw.get("canon_rule", []),
    )


def _override(**kw):
    return EntityOverride(
        id=kw.get("id", uuid.uuid4()), created_by=USER, project_id=PROJECT,
        work_id=kw.get("work_id", uuid.uuid4()),
        target_entity_id=kw.get("target_entity_id", uuid.uuid4()),
        overridden_fields=kw.get("overridden_fields", {}),
    )


def test_update_divergence_spec_persists_provided_fields(ctx):
    """PATCH divergence-spec passes only the provided fields to the repo; pov_anchor:null
    reaches the repo as an explicit clear (in model_fields_set), taxonomy round-trips."""
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.update_spec_result = _spec(taxonomy="pov_shift", canon_rule=["X"])
    r = c.patch(f"/v1/composition/works/{PROJECT}/divergence-spec",
                json={"taxonomy": "pov_shift", "pov_anchor": None, "canon_rule": ["X"]})
    assert r.status_code == 200, r.text
    assert r.json()["taxonomy"] == "pov_shift"
    _, _, kwargs = derivatives.update_spec_call
    assert kwargs["taxonomy"] == "pov_shift"
    assert "pov_anchor" in kwargs and kwargs["pov_anchor"] is None  # explicit clear
    assert kwargs["canon_rule"] == ["X"]


def test_update_divergence_spec_omitted_field_not_sent(ctx):
    """An OMITTED field is not forwarded (left unchanged) — only taxonomy here."""
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.update_spec_result = _spec(taxonomy="au")
    r = c.patch(f"/v1/composition/works/{PROJECT}/divergence-spec", json={"taxonomy": "au"})
    assert r.status_code == 200
    _, _, kwargs = derivatives.update_spec_call
    assert set(kwargs) == {"taxonomy"}  # pov_anchor / canon_rule NOT forwarded


def test_update_divergence_spec_off_enum_taxonomy_422(ctx):
    """An off-enum taxonomy is a 422 at the request boundary — never a DB CHECK 500."""
    c, works, _, _, _ = ctx
    works.work = _deriv_work()
    r = c.patch(f"/v1/composition/works/{PROJECT}/divergence-spec",
                json={"taxonomy": "not_a_taxonomy"})
    assert r.status_code == 422


def test_update_divergence_spec_non_derivative_400(ctx):
    """A base (non-derivative) Work has no spec → 400 NOT_A_DERIVATIVE (post-gate)."""
    c, works, _, _, _ = ctx
    works.work = _work()  # source_work_id is None
    r = c.patch(f"/v1/composition/works/{PROJECT}/divergence-spec", json={"taxonomy": "au"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NOT_A_DERIVATIVE"


def test_update_divergence_spec_missing_row_404(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.update_spec_result = None  # repo found no row
    r = c.patch(f"/v1/composition/works/{PROJECT}/divergence-spec", json={"taxonomy": "au"})
    assert r.status_code == 404


def test_add_entity_override_created_201(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    target = uuid.uuid4()
    derivatives.add_override_result = _override(target_entity_id=target,
                                                overridden_fields={"role": "hero"})
    r = c.post(f"/v1/composition/works/{PROJECT}/entity-overrides",
               json={"target_entity_id": str(target), "overridden_fields": {"role": "hero"}})
    assert r.status_code == 201, r.text
    assert r.json()["overridden_fields"] == {"role": "hero"}
    assert derivatives.add_override_call[3] == target


def test_add_entity_override_duplicate_409(ctx):
    """A second override for the same target → 409 OVERRIDE_EXISTS (PATCH instead)."""
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.add_override_raises = asyncpg.UniqueViolationError("dup")
    r = c.post(f"/v1/composition/works/{PROJECT}/entity-overrides",
               json={"target_entity_id": str(uuid.uuid4()), "overridden_fields": {}})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "OVERRIDE_EXISTS"


def test_add_entity_override_unresolvable_scope_404(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.add_override_raises = ReferenceViolationError("scope unresolvable")
    r = c.post(f"/v1/composition/works/{PROJECT}/entity-overrides",
               json={"target_entity_id": str(uuid.uuid4()), "overridden_fields": {}})
    assert r.status_code == 404


def test_update_entity_override_200_and_404(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    oid = uuid.uuid4()
    derivatives.update_override_result = _override(id=oid, overridden_fields={"a": 1})
    r = c.patch(f"/v1/composition/works/{PROJECT}/entity-overrides/{oid}",
                json={"overridden_fields": {"a": 1}})
    assert r.status_code == 200 and r.json()["overridden_fields"] == {"a": 1}
    # not found → 404
    derivatives.update_override_result = None
    r = c.patch(f"/v1/composition/works/{PROJECT}/entity-overrides/{uuid.uuid4()}",
                json={"overridden_fields": {}})
    assert r.status_code == 404


def test_delete_entity_override_204_and_404(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.delete_override_result = True
    r = c.delete(f"/v1/composition/works/{PROJECT}/entity-overrides/{uuid.uuid4()}")
    assert r.status_code == 204
    # idempotent second delete → 404, never a 500
    derivatives.delete_override_result = False
    r = c.delete(f"/v1/composition/works/{PROJECT}/entity-overrides/{uuid.uuid4()}")
    assert r.status_code == 404


def test_list_entity_overrides_200(ctx):
    c, works, _, _, derivatives = ctx
    works.work = _deriv_work()
    derivatives.overrides_for_work = [_override(overridden_fields={"role": "x"})]
    r = c.get(f"/v1/composition/works/{PROJECT}/entity-overrides")
    assert r.status_code == 200
    assert len(r.json()["overrides"]) == 1


# ── WS-B2: GET /works/{project_id}/derivative-context (durable read-back) ──

def test_get_derivative_context_returns_persisted_spec(ctx):
    """A derivative Work surfaces its DURABLE divergence spec + overrides — the FE
    no longer relies on the ephemeral derive-time react-query cache. source_project_id
    is resolved by looking the SOURCE up (build_derivative_context), not the raw
    source_work_id (the two id-spaces diverge)."""
    from app.db.models import DivergenceSpec, EntityOverride
    c, works, _, _, derivatives = ctx
    source_id = uuid.uuid4()
    source_project = uuid.uuid4()
    deriv_work = _work(project_id=PROJECT)
    deriv_work.source_work_id = source_id
    deriv_work.branch_point = 3
    works.work = deriv_work                                   # works.get → the derivative
    works.by_id_result = _work(project_id=source_project, id=source_id)  # source lookup
    target = uuid.uuid4()
    pov = uuid.uuid4()
    derivatives.spec_for_work = DivergenceSpec(
        created_by=USER, project_id=PROJECT, work_id=deriv_work.id,
        taxonomy="pov_shift", pov_anchor=pov, canon_rule=["The hero dies"],
    )
    derivatives.overrides_for_work = [
        EntityOverride(created_by=USER, project_id=PROJECT, work_id=deriv_work.id,
                       target_entity_id=target, overridden_fields={"description": "now a woman"}),
    ]
    r = c.get(f"/v1/composition/works/{PROJECT}/derivative-context")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_derivative"] is True
    assert body["source_work_id"] == str(source_id)
    assert body["source_project_id"] == str(source_project)   # resolved, not source_work_id
    assert body["branch_point"] == 3
    assert body["taxonomy"] == "pov_shift"
    assert body["pov_anchor"] == str(pov)
    assert body["canon_rules"] == ["The hero dies"]
    assert body["overrides"] == [
        {"target_entity_id": str(target), "overridden_fields": {"description": "now a woman"}},
    ]


def test_get_derivative_context_empty_for_greenfield(ctx):
    """A non-derivative (greenfield) Work → is_derivative False, no spec read."""
    c, works, _, _, derivatives = ctx
    works.work = _work(project_id=PROJECT)  # no source_work_id
    r = c.get(f"/v1/composition/works/{PROJECT}/derivative-context")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_derivative"] is False
    assert body["overrides"] == [] and body["canon_rules"] == []
    assert body["source_project_id"] is None


def test_get_derivative_context_404_when_work_absent(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    r = c.get(f"/v1/composition/works/{PROJECT}/derivative-context")
    assert r.status_code == 404


def test_derive_source_not_found_404(ctx):
    c, works, _, _, _ = ctx
    works.work = None  # source missing / cross-user
    r = c.post(f"/v1/composition/works/{PROJECT}/derive", json=_derive_body())
    assert r.status_code == 404


def test_derive_works_with_empty_body(ctx):
    """An absent body defaults: no overrides, taxonomy 'au', null branch_point. Still
    provisions a fresh project (GUARD holds) and writes the spec."""
    c, works, knowledge, _, derivatives = ctx
    works.work = _work(project_id=PROJECT)
    fresh = uuid.uuid4()
    knowledge.created_project = {"project_id": str(fresh)}
    r = c.post(f"/v1/composition/works/{PROJECT}/derive")
    assert r.status_code == 201, r.text
    assert r.json()["project_id"] == str(fresh)
    assert len(derivatives.specs) == 1 and derivatives.specs[0].taxonomy == "au"
    assert derivatives.overrides == []


# ── works CRUD ──

def test_get_work_404(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}").status_code == 404


def test_patch_work_ifmatch_412(ctx):
    c, works, _, _, _ = ctx
    works.work = _work()  # E0-4c: patch_work fetches the work first to gate on its book
    works.update_raises = VersionMismatchError(_work(version=3))
    r = c.patch(f"/v1/composition/works/{PROJECT}", json={"status": "archived"}, headers={"If-Match": "1"})
    assert r.status_code == 412
    assert r.json()["detail"]["current"]["version"] == 3


def test_patch_work_success(ctx):
    c, works, _, _, _ = ctx
    works.work = _work()  # E0-4c: must exist for the EDIT-gate fetch
    works.update_result = _work(version=2)
    r = c.patch(f"/v1/composition/works/{PROJECT}", json={"settings": {"voice": "wry"}})
    assert r.status_code == 200 and r.json()["version"] == 2


# ── prose ──

def test_get_prose_combines_draft_and_base_revision(ctx):
    c, works, _, book, _ = ctx
    works.work = _work()
    r = c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose")
    assert r.status_code == 200
    body = r.json()
    assert body["draft_version"] == 5 and body["base_revision_id"] == "rev-1"


def test_get_prose_404_when_work_missing(ctx):
    c, works, _, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose").status_code == 404


def test_put_prose_requires_expected_draft_version(ctx):
    c, works, _, _, _ = ctx
    works.work = _work()
    # omit expected_draft_version → 422 (mandatory field — the OI-2/PS2 guard)
    r = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose", json={"body": {"d": 1}})
    assert r.status_code == 422


def test_put_prose_rejects_null_body(ctx):
    # /review-impl M3 MED#1: an explicit null body must NOT reach book-service
    # (would risk clobbering the draft to null). dict-typed field → 422.
    c, works, _, _, _ = ctx
    works.work = _work()
    r = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose",
              json={"body": None, "expected_draft_version": 5})
    assert r.status_code == 422


def test_put_prose_forwards_version_and_maps_409(ctx):
    c, works, _, book, _ = ctx
    works.work = _work()
    r = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose",
              json={"body": {"d": 1}, "expected_draft_version": 5, "body_format": "json", "commit_message": "edit"})
    assert r.status_code == 200
    assert book.patched_with["expected_draft_version"] == 5
    assert book.patched_with["body_format"] == "json"  # forwarded
    assert book.patched_with["commit_message"] == "edit"  # forwarded
    # 409 conflict from book-service surfaces as 409
    book.patch_raises = BookClientError(409, "CHAPTER_DRAFT_CONFLICT", "stale draft version")
    r2 = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose",
               json={"body": {}, "expected_draft_version": 1})
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "CHAPTER_DRAFT_CONFLICT"


def test_get_prose_502_on_book_down(ctx):
    c, works, _, book, _ = ctx
    works.work = _work()
    book.get_raises = BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")
    assert c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose").status_code == 502


# ── D-S5-DERIVATIVE-MANUSCRIPT-FORK — work-scoped chapter drafts (the fork) ───────────


class StubWorkChapterDrafts:
    def __init__(self):
        self.row = None            # get() result (None = not forked yet → inherit canon)
        self.insert_result = None  # insert_fork() result (None = ON CONFLICT = already forked)
        self.update_result = None
        self.update_raises = None  # set to VersionMismatchError to simulate a stale OCC token
        self.forked_with = None
        self.updated_with = None
        self.merged_called = False

    async def get(self, project_id, chapter_id):
        return self.row

    async def insert_fork(self, project_id, chapter_id, book_id, created_by, body, draft_format="json"):
        self.forked_with = {"body": body, "book_id": book_id}
        return self.insert_result

    async def update_occ(self, project_id, chapter_id, body, expected_version, draft_format="json"):
        self.updated_with = {"body": body, "expected_version": expected_version}
        if self.update_raises:
            raise self.update_raises
        return self.update_result

    async def mark_merged(self, project_id, chapter_id):
        self.merged_called = True
        return self.row


def _deriv_work(**kw) -> CompositionWork:
    w = _work(**kw)
    w.source_work_id = kw.get("source_work_id", uuid.uuid4())
    w.branch_point = kw.get("branch_point", 0)
    return w


def _wcd(**kw):
    from app.db.models import WorkChapterDraft
    return WorkChapterDraft(
        project_id=kw.get("project_id", PROJECT), chapter_id=kw.get("chapter_id", CHAPTER),
        book_id=BOOK, created_by=USER, body=kw.get("body", {"v": 1}),
        draft_version=kw.get("draft_version", 1), merged_at=kw.get("merged_at"),
    )


@pytest.fixture
def wcd_ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (
        get_book_client_dep, get_grant_client_dep, get_work_chapter_drafts_repo, get_works_repo,
    )
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, book, wcd = StubWorks(), StubBook(), StubWorkChapterDrafts()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_work_chapter_drafts_repo] = lambda: wcd
    with TestClient(app) as c:
        yield c, works, book, wcd
    app.dependency_overrides.clear()


_WD_URL = f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/work-draft"


def test_work_draft_get_inherits_canon_when_not_forked(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = None  # not forked → read-through to canon
    r = c.get(_WD_URL)
    assert r.status_code == 200
    j = r.json()
    assert j["forked"] is False and j["inherited"] is True
    assert j["draft_version"] == 0            # the "fork token" the FE sends to fork
    assert j["body"] == {"x": 1}              # StubBook.draft body — inherited from canon
    assert j["canon_version"] == 5


def test_work_draft_get_returns_the_fork_when_forked(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = _wcd(body={"y": 2}, draft_version=3)
    j = c.get(_WD_URL).json()
    assert j["forked"] is True and j["draft_version"] == 3 and j["body"] == {"y": 2}


def test_work_draft_get_rejects_the_canonical_work(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _work()  # source_work_id None — canonical has no fork layer
    r = c.get(_WD_URL)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NOT_A_DERIVATIVE"


def test_work_draft_patch_forks_on_first_edit_and_never_touches_canon(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.insert_result = _wcd(body={"edited": True}, draft_version=1)
    r = c.patch(_WD_URL, json={"body": {"edited": True}, "expected_version": 0})
    assert r.status_code == 200
    assert r.json()["forked"] is True and r.json()["draft_version"] == 1
    assert wcd.forked_with["body"] == {"edited": True}
    # THE ISOLATION GUARANTEE: canon (book-service) was never patched.
    assert book.patched_with is None


def test_work_draft_patch_fork_conflict_when_already_forked(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.insert_result = None  # ON CONFLICT DO NOTHING — a concurrent fork won
    r = c.patch(_WD_URL, json={"body": {"x": 1}, "expected_version": 0})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_FORKED"


def test_work_draft_patch_occ_updates_an_existing_fork(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.update_result = _wcd(body={"v": 9}, draft_version=4)
    r = c.patch(_WD_URL, json={"body": {"v": 9}, "expected_version": 3})
    assert r.status_code == 200 and r.json()["draft_version"] == 4
    assert wcd.updated_with["expected_version"] == 3
    assert book.patched_with is None  # still never touches canon


def test_work_draft_patch_stale_version_is_412(wcd_ctx):
    from app.db.repositories import VersionMismatchError
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.update_raises = VersionMismatchError(_wcd(draft_version=7))
    r = c.patch(_WD_URL, json={"body": {"v": 1}, "expected_version": 3})
    assert r.status_code == 412
    assert r.json()["detail"]["code"] == "STALE_VERSION"
    assert r.json()["detail"]["current_version"] == 7


def test_work_draft_patch_rejects_the_canonical_work(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _work()  # canonical
    r = c.patch(_WD_URL, json={"body": {"x": 1}, "expected_version": 0})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NOT_A_DERIVATIVE"


# ── M2 — merge a forked chapter back into canon ──────────────────────────────────────

_MERGE_URL = f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/merge-to-canon"


def test_merge_to_canon_writes_canon_and_marks_merged(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = _wcd(body={"m": 1}, draft_version=2)
    r = c.post(_MERGE_URL, json={})
    assert r.status_code == 200
    assert r.json()["merged"] is True and r.json()["canon_draft_version"] == 6
    assert book.patched_with["body"] == {"m": 1}
    assert book.patched_with["expected_draft_version"] == 5
    assert wcd.merged_called is True


def test_merge_to_canon_rejects_when_not_forked(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = None
    r = c.post(_MERGE_URL, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_FORKED"
    assert book.patched_with is None


def test_merge_to_canon_canon_conflict_is_409(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = _wcd(body={"m": 1})
    book.patch_raises = BookClientError(409, "CHAPTER_DRAFT_CONFLICT")
    r = c.post(_MERGE_URL, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CANON_CONFLICT"
    assert wcd.merged_called is False


def test_merge_to_canon_rejects_the_canonical_work(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _work()
    r = c.post(_MERGE_URL, json={})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NOT_A_DERIVATIVE"


def test_merge_to_canon_honors_client_expected_canon_version(wcd_ctx):
    c, works, book, wcd = wcd_ctx
    works.work = _deriv_work()
    wcd.row = _wcd(body={"m": 1})
    r = c.post(_MERGE_URL, json={"expected_canon_version": 3})
    assert r.status_code == 200
    assert book.patched_with["expected_draft_version"] == 3
