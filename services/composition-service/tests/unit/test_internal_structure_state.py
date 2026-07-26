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


# ── Internal part-WRITE routes (manuscript-structure MCP tool, spec 2026-07-22) ────────────────────

from types import SimpleNamespace  # noqa: E402

from app.db.repositories.structure import StructureConflictError  # noqa: E402

PART = uuid4()


def _node(node_id=PART, *, kind="part", title="Act II", rank="1", archived=False, book=BOOK):
    return SimpleNamespace(id=node_id, kind=kind, title=title, rank=rank, is_archived=archived, book_id=book)


def _client_repo(owner, repo):
    from app.deps import get_grant_client_dep, get_structure_repo
    from app.main import app

    app.dependency_overrides[get_structure_repo] = lambda: repo
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(owner)
    return TestClient(app)


def _create_url():
    return f"/internal/composition/books/{BOOK}/parts?caller_user_id={CALLER}"


def _reorder_url():
    return f"/internal/composition/books/{BOOK}/parts/reorder?caller_user_id={CALLER}"


def _rename_url(node_id=PART):
    return f"/internal/composition/parts/{node_id}?caller_user_id={CALLER}"


def test_create_part_requires_internal_token():
    c = _client_repo(OWNER, AsyncMock())
    try:
        assert c.post(_create_url(), json={"title": "x"}).status_code == 401
    finally:
        _teardown()


def test_create_part_no_grant_is_404_before_write():
    repo = AsyncMock()
    c = _client_repo(None, repo)  # resolve_owner → None
    try:
        assert c.post(_create_url(), json={"title": "Act II"}, headers=TOK).status_code == 404
        repo.create_part.assert_not_awaited()  # gate BEFORE the write
    finally:
        _teardown()


def test_create_part_happy_returns_201_and_shape():
    repo = AsyncMock()
    repo.create_part = AsyncMock(return_value=_node())
    c = _client_repo(OWNER, repo)
    try:
        r = c.post(_create_url(), json={"title": "  Act II  "}, headers=TOK)
        assert r.status_code == 201
        assert r.json() == {"part_id": str(PART), "title": "Act II", "sort_order": 1, "lifecycle_state": "active"}
        # title is stripped before the write
        assert repo.create_part.await_args.kwargs["title"] == "Act II"
        assert repo.create_part.await_args.kwargs["created_by"] == CALLER
    finally:
        _teardown()


def test_rename_part_rejects_non_part_node_404():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(kind="arc"))  # a parts route must never touch an arc
    c = _client_repo(OWNER, repo)
    try:
        assert c.patch(_rename_url(), json={"title": "x"}, headers=TOK).status_code == 404
        repo.update.assert_not_awaited()
    finally:
        _teardown()


def test_rename_part_missing_node_404():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    c = _client_repo(OWNER, repo)
    try:
        assert c.patch(_rename_url(), json={"title": "x"}, headers=TOK).status_code == 404
    finally:
        _teardown()


def test_rename_part_no_grant_on_owning_book_404():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node())
    c = _client_repo(None, repo)  # node is a part, but caller holds no grant on its book
    try:
        assert c.patch(_rename_url(), json={"title": "x"}, headers=TOK).status_code == 404
        repo.update.assert_not_awaited()
    finally:
        _teardown()


def test_rename_part_happy_200():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node())
    repo.update = AsyncMock(return_value=_node(title="Renamed"))
    c = _client_repo(OWNER, repo)
    try:
        r = c.patch(_rename_url(), json={"title": " Renamed "}, headers=TOK)
        assert r.status_code == 200
        assert r.json()["title"] == "Renamed"
        assert repo.update.await_args.args[1] == {"title": "Renamed"}  # stripped
    finally:
        _teardown()


def test_reorder_parts_conflict_is_409_fail_closed():
    repo = AsyncMock()
    repo.reorder_parts = AsyncMock(side_effect=StructureConflictError("ordered_ids must be exactly the active parts"))
    c = _client_repo(OWNER, repo)
    try:
        r = c.post(_reorder_url(), json={"ordered_ids": [str(uuid4())]}, headers=TOK)
        assert r.status_code == 409  # a subset/superset/foreign id fails the WHOLE op, no silent drop
    finally:
        _teardown()


def test_reorder_parts_happy_200():
    repo = AsyncMock()
    a, b = _node(node_id=uuid4(), rank="0"), _node(node_id=uuid4(), rank="1")
    repo.reorder_parts = AsyncMock(return_value=[a, b])
    c = _client_repo(OWNER, repo)
    try:
        r = c.post(_reorder_url(), json={"ordered_ids": [str(a.id), str(b.id)]}, headers=TOK)
        assert r.status_code == 200
        assert [i["part_id"] for i in r.json()["items"]] == [str(a.id), str(b.id)]
    finally:
        _teardown()


def test_archive_part_rejects_non_part_404():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(kind="arc"))
    c = _client_repo(OWNER, repo)
    try:
        assert c.delete(_rename_url(), headers=TOK).status_code == 404
        repo.archive.assert_not_awaited()
    finally:
        _teardown()


def test_archive_part_happy_204():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node())
    repo.archive = AsyncMock(return_value=None)
    c = _client_repo(OWNER, repo)
    try:
        assert c.delete(_rename_url(), headers=TOK).status_code == 204
        repo.archive.assert_awaited_once_with(PART)
    finally:
        _teardown()


def test_archive_part_no_grant_404():
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node())
    c = _client_repo(None, repo)
    try:
        assert c.delete(_rename_url(), headers=TOK).status_code == 404
        repo.archive.assert_not_awaited()
    finally:
        _teardown()


def test_create_part_dormant_repo_503():
    from app.deps import get_grant_client_dep, get_structure_repo
    from app.main import app
    app.dependency_overrides[get_structure_repo] = lambda: None
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(OWNER)
    try:
        assert TestClient(app).post(_create_url(), json={"title": "x"}, headers=TOK).status_code == 503
    finally:
        _teardown()
