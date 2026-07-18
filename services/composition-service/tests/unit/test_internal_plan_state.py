"""The internal per-turn plan-state probe — `GET /internal/composition/books/
{book_id}/plan-state?caller_user_id=`.

Route behavior over a mocked repo (the SQL itself is proven against real Postgres in
tests/integration/db/test_repositories.py::test_plan_state_for_book_*). Internal-token
gated; grant-gated (no grant → 404, no oracle). The load-bearing distinction: runs can
EXIST without any `spec` artifact — that book has no arc plan, so has_plan=true must
still report has_spec=false.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

OWNER, BOOK, CALLER = uuid4(), uuid4(), uuid4()
TOK = {"X-Internal-Token": "test_token"}


class _Grant:
    def __init__(self, owner):
        self._owner = owner

    async def resolve_owner(self, book_id, user_id):
        return self._owner


def _client(owner, state):
    from app.deps import get_grant_client_dep, get_plan_runs_repo
    from app.main import app

    plans = AsyncMock()
    plans.plan_state_for_book = AsyncMock(return_value=state)
    app.dependency_overrides[get_plan_runs_repo] = lambda: plans
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(owner)
    return TestClient(app), plans


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


def _url():
    return f"/internal/composition/books/{BOOK}/plan-state?caller_user_id={CALLER}"


def test_requires_internal_token():
    c, _ = _client(OWNER, {"run_count": 0, "latest_status": None, "has_spec": False})
    try:
        assert c.get(_url()).status_code == 401
    finally:
        _teardown()


def test_no_grant_is_404():
    # resolve_owner → None (no grant, or the book does not exist): uniform 404.
    c, plans = _client(None, {"run_count": 3, "latest_status": "compiled", "has_spec": True})
    try:
        assert c.get(_url(), headers=TOK).status_code == 404
        plans.plan_state_for_book.assert_not_awaited()  # gate runs BEFORE the read
    finally:
        _teardown()


def test_book_with_runs_and_spec_artifact():
    # (a) runs + a spec artifact → the book HAS an arc plan.
    c, plans = _client(OWNER, {"run_count": 3, "latest_status": "compiled", "has_spec": True})
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200
        assert r.json() == {
            "book_id": str(BOOK),
            "has_plan": True,
            "run_count": 3,
            "latest_status": "compiled",
            "has_spec": True,
        }
        # single cheap read — one repo call, keyed by book_id alone (no N+1 per run)
        plans.plan_state_for_book.assert_awaited_once_with(BOOK)
    finally:
        _teardown()


def test_book_with_no_plan_is_200_not_404():
    # (b) a brand-new book: "no plan yet" is the EXPECTED answer, never an error.
    c, _ = _client(OWNER, {"run_count": 0, "latest_status": None, "has_spec": False})
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200
        assert r.json() == {
            "book_id": str(BOOK),
            "has_plan": False,
            "run_count": 0,
            "latest_status": None,
            "has_spec": False,
        }
    finally:
        _teardown()


def test_runs_without_spec_artifact_has_plan_true_has_spec_false():
    # (c) THE distinction this route exists for: a run exists (e.g. still pending, or
    # failed before emitting a spec) → has_plan=true, but there is NO arc plan yet.
    c, _ = _client(OWNER, {"run_count": 1, "latest_status": "pending", "has_spec": False})
    try:
        body = c.get(_url(), headers=TOK).json()
        assert body["has_plan"] is True and body["run_count"] == 1
        assert body["latest_status"] == "pending"
        assert body["has_spec"] is False
    finally:
        _teardown()
