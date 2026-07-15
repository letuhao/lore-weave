"""The internal per-turn structure-state probe — `GET /internal/composition/books/
{book_id}/structure-state?caller_user_id=` (Phase G · G0).

Route behavior over a mocked repo (the SQL itself — the plan_run_id distinction that makes
D2/D3 real — is proven against real Postgres in
tests/integration/db/test_repositories.py::test_linked_structure_state_*). Internal-token
gated; grant-gated (no grant → 404, no oracle). A dormant repo → 503 (UNKNOWN), never a
fabricated 0.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

OWNER, BOOK, CALLER, RUN = uuid4(), uuid4(), uuid4(), uuid4()
TOK = {"X-Internal-Token": "test_token"}


class _Grant:
    def __init__(self, owner):
        self._owner = owner

    async def resolve_owner(self, book_id, user_id):
        return self._owner


def _client(owner, state):
    from app.deps import get_grant_client_dep, get_structure_repo
    from app.main import app

    repo = AsyncMock()
    repo.linked_structure_state = AsyncMock(return_value=state)
    app.dependency_overrides[get_structure_repo] = lambda: repo
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(owner)
    return TestClient(app), repo


def _client_dormant(owner):
    from app.deps import get_grant_client_dep, get_structure_repo
    from app.main import app

    app.dependency_overrides[get_structure_repo] = lambda: None
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(owner)
    return TestClient(app)


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


def _url():
    return f"/internal/composition/books/{BOOK}/structure-state?caller_user_id={CALLER}"


def test_requires_internal_token():
    c, _ = _client(OWNER, {"linked_count": 0, "latest_run_id": None, "latest_run_linked_count": 0})
    try:
        assert c.get(_url()).status_code == 401
    finally:
        _teardown()


def test_no_grant_is_404_before_read():
    c, repo = _client(None, {"linked_count": 5, "latest_run_id": RUN, "latest_run_linked_count": 5})
    try:
        assert c.get(_url(), headers=TOK).status_code == 404
        repo.linked_structure_state.assert_not_awaited()  # gate runs BEFORE the read
    finally:
        _teardown()


def test_compiled_book_reports_linked_count():
    c, repo = _client(
        OWNER, {"linked_count": 4, "latest_run_id": RUN, "latest_run_linked_count": 4}
    )
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200
        assert r.json() == {
            "book_id": str(BOOK),
            "linked_count": 4,
            "latest_run_id": str(RUN),
            "latest_run_linked_count": 4,
        }
        repo.linked_structure_state.assert_awaited_once_with(BOOK)
    finally:
        _teardown()


def test_no_structure_is_200_not_404():
    # A book with no compiled arcs: both counts 0, latest_run_id null — the expected answer.
    c, _ = _client(OWNER, {"linked_count": 0, "latest_run_id": None, "latest_run_linked_count": 0})
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200
        assert r.json()["linked_count"] == 0
        assert r.json()["latest_run_id"] is None
    finally:
        _teardown()


def test_bare_arc_insert_does_not_show_as_linked_D3():
    # D3: a book whose ONLY structure_node rows came from bare composition_arc_create
    # (plan_run_id NULL) — the repo's compile-attributed count is 0, so the response says
    # linked_count=0. A plain insert can NOT fabricate the compile effect.
    c, _ = _client(OWNER, {"linked_count": 0, "latest_run_id": None, "latest_run_linked_count": 0})
    try:
        assert c.get(_url(), headers=TOK).json()["linked_count"] == 0
    finally:
        _teardown()


def test_replan_reads_fresh_zero_D2():
    # D2: a re-plan — run #1 compiled (linked_count>0), run #2 is the latest with no compile
    # yet (latest_run_linked_count=0). A step gated on produce-NEW is NOT born-done.
    c, _ = _client(
        OWNER, {"linked_count": 6, "latest_run_id": RUN, "latest_run_linked_count": 0}
    )
    try:
        body = c.get(_url(), headers=TOK).json()
        assert body["linked_count"] == 6              # book HAS a compiled plan (ensure-EXISTS)
        assert body["latest_run_linked_count"] == 0   # but THIS attempt has not (produce-NEW)
    finally:
        _teardown()


def test_dormant_repo_is_503_unknown_not_fake_zero():
    c = _client_dormant(OWNER)
    try:
        assert c.get(_url(), headers=TOK).status_code == 503
    finally:
        _teardown()
