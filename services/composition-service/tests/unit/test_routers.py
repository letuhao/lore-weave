"""M3 router tests — works resolve/CRUD + prose proxy (TestClient + overrides).

Lifespan DB wiring is stubbed (M0 pattern); auth + repos + clients are injected
via dependency_overrides so the tests exercise router logic, status mapping, and
the OI-2 mandatory-version guard without a live stack.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.clients.book_client import BookClientError
from app.db.models import CompositionWork
from app.db.repositories import VersionMismatchError

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
CHAPTER = uuid.uuid4()


def _work(**kw) -> CompositionWork:
    return CompositionWork(project_id=kw.get("project_id", PROJECT), user_id=USER,
                           book_id=BOOK, version=kw.get("version", 1),
                           status=kw.get("status", "active"))


class StubWorks:
    def __init__(self):
        self.work = None
        self.marked = []
        self.update_result = None
        self.update_raises = None

    async def get(self, user_id, project_id):
        return self.work

    async def resolve_by_book(self, user_id, book_id):
        return self.marked

    async def update(self, user_id, project_id, patch, *, expected_version=None):
        if self.update_raises:
            raise self.update_raises
        return self.update_result


class StubKnowledge:
    def __init__(self, projects=None):
        self.projects = projects

    async def list_projects_for_book(self, book_id, bearer):
        return self.projects


class StubBook:
    def __init__(self):
        self.draft = {"chapter_id": str(CHAPTER), "body": {"x": 1}, "draft_version": 5}
        self.revisions = {"items": [{"revision_id": "rev-1"}], "total": 1}
        self.patch_result = {"chapter_id": str(CHAPTER), "draft_version": 6}
        self.get_raises = None
        self.patch_raises = None
        self.patched_with = None

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
    from app.deps import get_book_client_dep, get_knowledge_client_dep, get_works_repo
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works, knowledge, book = StubWorks(), StubKnowledge(), StubBook()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_knowledge_client_dep] = lambda: knowledge
    app.dependency_overrides[get_book_client_dep] = lambda: book
    with TestClient(app) as c:
        yield c, works, knowledge, book
    app.dependency_overrides.clear()


# ── works resolve ──

def test_resolve_found(ctx):
    c, works, _, _ = ctx
    works.marked = [_work()]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "found" and body["work"]["project_id"] == str(PROJECT)


def test_resolve_unmarked_single_from_knowledge(ctx):
    c, works, knowledge, _ = ctx
    works.marked = []
    pid = uuid.uuid4()
    knowledge.projects = [{"project_id": str(pid), "project_type": "general", "book_id": str(BOOK), "is_archived": False}]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    assert r.json()["status"] == "unmarked_single"
    assert r.json()["book_project_id"] == str(pid)


def test_resolve_candidates_serializes_marked_works(ctx):
    c, works, _, _ = ctx
    w1, w2 = _work(project_id=uuid.uuid4()), _work(project_id=uuid.uuid4())
    works.marked = [w1, w2]
    r = c.get(f"/v1/composition/books/{BOOK}/work")
    body = r.json()
    assert body["status"] == "candidates"
    assert {w["project_id"] for w in body["candidates"]} == {str(w1.project_id), str(w2.project_id)}


# ── works CRUD ──

def test_get_work_404(ctx):
    c, works, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}").status_code == 404


def test_patch_work_ifmatch_412(ctx):
    c, works, _, _ = ctx
    works.update_raises = VersionMismatchError(_work(version=3))
    r = c.patch(f"/v1/composition/works/{PROJECT}", json={"status": "archived"}, headers={"If-Match": "1"})
    assert r.status_code == 412
    assert r.json()["detail"]["current"]["version"] == 3


def test_patch_work_success(ctx):
    c, works, _, _ = ctx
    works.update_result = _work(version=2)
    r = c.patch(f"/v1/composition/works/{PROJECT}", json={"settings": {"voice": "wry"}})
    assert r.status_code == 200 and r.json()["version"] == 2


# ── prose ──

def test_get_prose_combines_draft_and_base_revision(ctx):
    c, works, _, book = ctx
    works.work = _work()
    r = c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose")
    assert r.status_code == 200
    body = r.json()
    assert body["draft_version"] == 5 and body["base_revision_id"] == "rev-1"


def test_get_prose_404_when_work_missing(ctx):
    c, works, _, _ = ctx
    works.work = None
    assert c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose").status_code == 404


def test_put_prose_requires_expected_draft_version(ctx):
    c, works, _, _ = ctx
    works.work = _work()
    # omit expected_draft_version → 422 (mandatory field — the OI-2/PS2 guard)
    r = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose", json={"body": {"d": 1}})
    assert r.status_code == 422


def test_put_prose_rejects_null_body(ctx):
    # /review-impl M3 MED#1: an explicit null body must NOT reach book-service
    # (would risk clobbering the draft to null). dict-typed field → 422.
    c, works, _, _ = ctx
    works.work = _work()
    r = c.put(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose",
              json={"body": None, "expected_draft_version": 5})
    assert r.status_code == 422


def test_put_prose_forwards_version_and_maps_409(ctx):
    c, works, _, book = ctx
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
    c, works, _, book = ctx
    works.work = _work()
    book.get_raises = BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")
    assert c.get(f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/prose").status_code == 502
