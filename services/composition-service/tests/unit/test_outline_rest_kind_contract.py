"""#263 — the REST outline-node CREATE door must not accept retired node kinds.

`outline_node`'s base schema (`outline_node_kind_check`) admits arc/beat, but the
pkg_lift_v1 lift retired them as CREATABLE kinds: arcs live in `structure_node`
(composition_arc_create) and beat is verified-dead. The MCP door already narrows its
create Literal (`_NodeCreateArgs.kind: Literal["chapter","scene"]`, BPS-4) — the REST
door kept the stored four-kind vocabulary on `NodeCreate.kind`, so a documented kind
passed request validation, reached the INSERT, and died as a 400 carrying the raw
Postgres check message INCLUDING the entire failing row.

The split this pins:
  • NodeCreate.kind (the WRITE door) is chapter/scene only — a retired kind is a
    schema 422 naming the accepted values and never reaches the repo, so the
    constraint text + row dump cannot leak through this route;
  • OutlineNode.kind (the READ model) stays the STORED vocabulary — a not-yet-lifted
    DB is a supported boot state and its legacy rows must still validate.
The repo stub raises the exact CheckViolationError the live CHECK produces, so the
unfixed router is exercised against the real failure shape.
"""

from typing import get_args
from unittest.mock import AsyncMock
from uuid import UUID

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.db.models import OutlineNode
from app.routers.outline import NodeCreate

_USER = UUID("00000000-0000-0000-0000-0000000000aa")
_PROJECT = UUID("00000000-0000-0000-0000-0000000000bb")
_BOOK = UUID("00000000-0000-0000-0000-0000000000cc")
_NODE = UUID("00000000-0000-0000-0000-0000000000dd")

# The live CHECK (base schema). A retired kind that reaches the INSERT dies here.
_KIND_CHECK_VIOLATION = asyncpg.CheckViolationError(
    'new row for relation "outline_node" violates check constraint '
    '"outline_node_kind_check"\nDETAIL: Failing row contains '
    f'({_NODE}, {_USER}, {_PROJECT}, ..., beat, r, Beat, null, {{}}, , null, empty, ...).'
)


def test_nodecreate_kind_is_the_lifted_chapter_scene_set():
    # BPS-4 / #263 — the WRITE door's closed set. Guarded on the annotation because a
    # Literal cannot be derived: widening it back reopens the 400-constraint-leak door.
    assert get_args(NodeCreate.model_fields["kind"].annotation) == ("chapter", "scene"), (
        "NodeCreate.kind advertises kinds the lift retired as creatable — a client built "
        "from this door will send a request the database always rejects (#263). Arcs "
        "belong to structure_node (composition_arc_create); beat is gone. The READ model "
        "(OutlineNode.kind) intentionally keeps the stored vocabulary."
    )


def _node(kind: str) -> OutlineNode:
    return OutlineNode.model_validate(dict(
        id=_NODE, created_by=_USER, project_id=_PROJECT, book_id=_BOOK, parent_id=None,
        kind=kind, rank="a0", title="A node", goal="", status="outline", synopsis="",
        version=1, story_order=1,
    ))


def test_outline_read_model_still_validates_legacy_kinds():
    # The counterpart guarantee: narrowing the write door must NOT narrow the read
    # model — a not-yet-lifted DB's arc/beat rows have to keep validating (the
    # integration fixtures boot exactly that world).
    for legacy in ("arc", "beat"):
        assert _node(legacy).kind == legacy


class _StubOutline:
    def __init__(self, *, violate: bool):
        self.violate = violate
        self.create_seen: dict | None = None

    async def create_node(self, project_id, *, created_by=None, **fields):
        self.create_seen = dict(fields)
        if self.violate:
            raise _KIND_CHECK_VIOLATION
        return _node(fields["kind"])


class _StubWorks:
    async def get(self, project_id):
        from types import SimpleNamespace
        return SimpleNamespace(book_id=_BOOK)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_grant_client_dep, get_outline_repo, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    holder: dict = {"repo": None}
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_works_repo] = lambda: _StubWorks()
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_outline_repo] = lambda: holder["repo"]
    with TestClient(app) as c:
        yield c, holder
    app.dependency_overrides.clear()


def _post(client, kind: str):
    return client.post(
        f"/v1/composition/works/{_PROJECT}/outline/nodes",
        json={"kind": kind, "title": "Beat"},
    )


@pytest.mark.parametrize("kind", ["beat", "arc"])
def test_retired_kinds_are_a_schema_422_and_never_reach_the_repo(client, kind):
    c, holder = client
    holder["repo"] = _StubOutline(violate=True)  # would raise the live CHECK if reached
    r = _post(c, kind)
    assert r.status_code == 422, (
        f"kind={kind!r} must be rejected by request validation, got {r.status_code}: {r.text}"
    )
    # The 422 names the values the API actually accepts (a typed, actionable error).
    assert "'chapter'" in r.text and "'scene'" in r.text
    # The raw Postgres failure — constraint name + the caller's whole row — must not
    # surface through this route. On the unfixed code the 400 body carried both.
    assert "violates check constraint" not in r.text
    assert "Failing row" not in r.text
    assert "outline_node_kind_check" not in r.text
    assert holder["repo"].create_seen is None, "a retired kind reached OutlineRepo.create_node"


def test_live_scene_kind_still_creates(client):
    c, holder = client
    holder["repo"] = _StubOutline(violate=False)
    r = _post(c, "scene")
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "scene"
    assert holder["repo"].create_seen is not None
    assert holder["repo"].create_seen["kind"] == "scene"
