"""M3 (WS-B3) — POST /works/{project_id}/scenes/{node_id}/prose router tests.

The endpoint persists a promoted derivative scene's take prose into the DERIVATIVE
project's synthetic-job store (never the shared book draft). These TestClient tests
stub the works repo + grant + jobs repo to assert the contract surface:

  • EDIT-grant gating (none → 404, view → 403);
  • derivative-only (a non-derivative project → 409);
  • wrong-owner / missing work → 404;
  • empty/whitespace text → 422 EMPTY_SCENE_PROSE;
  • happy path → 200 {node_id, persisted:true, version};
  • SOURCE-CLOBBER GUARD: the endpoint has NO book-client dependency, so it
    structurally cannot write book-service's shared chapter draft — it can only
    reach composition's own synthetic-job store.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import CompositionWork
from app.db.repositories import ReferenceViolationError
from app.grant_client import GrantLevel

USER, PROJECT, BOOK, NODE, SOURCE_WORK = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()


class _Grant:
    def __init__(self, level):
        self._level = level
    async def resolve_grant(self, book_id, user_id):
        return self._level
    async def resolve_access(self, book_id, user_id):
        return self._level, "active"


def _derivative_work():
    # A derivative carries source_work_id (+ a non-null project_id, the DB CHECK).
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK,
                           source_work_id=SOURCE_WORK, branch_point=3, version=1)


def _canon_work():
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, version=1)


def _client(level, *, work=None, upsert=None):
    from app.main import app
    from app.deps import get_generation_jobs_repo, get_grant_client_dep, get_works_repo
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works = AsyncMock()
    works.get = AsyncMock(return_value=work)
    jobs = AsyncMock()
    # default upsert returns (job, version=1); a test can override
    jobs.upsert_promoted_scene_prose = upsert or AsyncMock(return_value=(object(), 1))
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(level)
    return TestClient(app), works, jobs


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


def _url():
    return f"/v1/composition/works/{PROJECT}/scenes/{NODE}/prose"


def test_happy_path_persists_and_returns_version():
    c, works, jobs = _client(GrantLevel.EDIT, work=_derivative_work())
    try:
        r = c.post(_url(), json={"text": "the chosen take's prose"})
        assert r.status_code == 200
        body = r.json()
        assert body == {"node_id": str(NODE), "persisted": True, "version": 1}
        # wrote to the synthetic-job store with the right scope/text. Post 25 re-key
        # the write signature is (project_id, node_id, text, *, created_by=<actor>).
        jobs.upsert_promoted_scene_prose.assert_awaited_once()
        args, kwargs = jobs.upsert_promoted_scene_prose.call_args
        assert args[0] == PROJECT and args[1] == NODE
        assert args[2] == "the chosen take's prose"
        assert kwargs["created_by"] == USER
    finally:
        _teardown()


def test_version_reflects_repo_promote_count():
    upsert = AsyncMock(return_value=(object(), 4))
    c, _, _ = _client(GrantLevel.EDIT, work=_derivative_work(), upsert=upsert)
    try:
        r = c.post(_url(), json={"text": "re-promoted"})
        assert r.status_code == 200 and r.json()["version"] == 4
    finally:
        _teardown()


def test_empty_text_422():
    c, _, jobs = _client(GrantLevel.EDIT, work=_derivative_work())
    try:
        r = c.post(_url(), json={"text": "   \n\t  "})
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "EMPTY_SCENE_PROSE"
        # never reached the store
        jobs.upsert_promoted_scene_prose.assert_not_called()
    finally:
        _teardown()


def test_non_derivative_409():
    # a canon (non-derivative) project has no promote surface → 409 NOT_A_DERIVATIVE
    c, _, jobs = _client(GrantLevel.EDIT, work=_canon_work())
    try:
        r = c.post(_url(), json={"text": "x"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "NOT_A_DERIVATIVE"
        jobs.upsert_promoted_scene_prose.assert_not_called()
    finally:
        _teardown()


def test_missing_or_wrong_owner_work_404():
    # works.get is user-scoped → None for a missing / cross-owner work → 404
    c, _, _ = _client(GrantLevel.EDIT, work=None)
    try:
        r = c.post(_url(), json={"text": "x"})
        assert r.status_code == 404
    finally:
        _teardown()


def test_view_grantee_403():
    c, _, jobs = _client(GrantLevel.VIEW, work=_derivative_work())
    try:
        r = c.post(_url(), json={"text": "x"})
        assert r.status_code == 403
        jobs.upsert_promoted_scene_prose.assert_not_called()
    finally:
        _teardown()


def test_non_grantee_404():
    c, _, _ = _client(GrantLevel.NONE, work=_derivative_work())
    try:
        r = c.post(_url(), json={"text": "x"})
        assert r.status_code == 404
    finally:
        _teardown()


def test_foreign_or_non_scene_node_maps_to_404():
    # the repo raises ReferenceViolationError for a node that isn't the caller's
    # scene in this project → 404 (no existence oracle).
    upsert = AsyncMock(side_effect=ReferenceViolationError("not a scene"))
    c, _, _ = _client(GrantLevel.EDIT, work=_derivative_work(), upsert=upsert)
    try:
        r = c.post(_url(), json={"text": "x"})
        assert r.status_code == 404
    finally:
        _teardown()


def test_endpoint_has_no_book_client_dependency_source_clobber_guard():
    # SOURCE-CLOBBER GUARD (structural): the persist_scene_prose handler must NOT
    # depend on the book client — it can ONLY write composition's own synthetic-job
    # store, never book-service's shared chapter draft. Assert the dependency is
    # absent so a future refactor can't quietly reintroduce a shared-draft write.
    import ast
    import inspect
    from app.routers.engine import persist_scene_prose
    # no book client in the signature → cannot reach book-service at all
    assert "book" not in inspect.signature(persist_scene_prose).parameters
    # and the handler CODE (docstring stripped) never names a shared-draft write/read
    tree = ast.parse(inspect.getsource(persist_scene_prose).strip())
    fn = tree.body[0]
    fn.body = [n for n in fn.body
               if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    code_no_doc = ast.unparse(fn)
    assert "patch_draft" not in code_no_doc and "get_draft" not in code_no_doc
