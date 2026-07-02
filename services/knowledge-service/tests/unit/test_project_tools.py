"""Unit tests for kg_project_create (D-KG-LF-PROJECT-CREATE-MCP).

The security-critical property: a book-bound project create is BOOK-OWNER-ONLY,
with no existence oracle (a non-owner gets the same generic refusal). Book-less
create is a personal project (no grant check). Idempotency is delegated to
create_or_get (covered by the projects-repo tests); here we prove the gate +
dispatch wiring through execute_tool with fakes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from loreweave_grants import GrantLevel

from app.tools.executor import ToolContext, execute_tool

_USER = uuid4()
_BOOK = uuid4()


def _mk_ctx(*, user_id=_USER, grant_client=None, projects_repo=None) -> ToolContext:
    return ToolContext(
        user_id=user_id,
        project_id=None,  # project-create runs with no project in scope
        session_id="sess-proj",
        projects_repo=projects_repo or AsyncMock(),
        pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(),
        redis=None,
        grant_client=grant_client or AsyncMock(),
        graph_views_repo=AsyncMock(),
        graph_schemas_repo=AsyncMock(),
        triage_repo=AsyncMock(),
        ontology_resolver=AsyncMock(),
        ontology_mutations_repo=AsyncMock(),
    )


def _fake_project(*, book_id=None):
    return SimpleNamespace(
        project_id=uuid4(), name="Dracula KG", project_type="book", book_id=book_id
    )


@pytest.mark.asyncio
async def test_book_bound_create_denied_for_non_owner():
    """A non-owner of the book gets a tool error and NO project is created
    (book-owner-only, no existence oracle)."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.VIEW)  # grantee, not owner
    repo = AsyncMock()
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Dracula KG", "book_id": str(_BOOK)}
    )
    assert not res.success
    assert "owner" in res.error.lower()
    repo.create_or_get.assert_not_called()


@pytest.mark.asyncio
async def test_book_bound_create_succeeds_for_owner():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.OWNER)
    repo = AsyncMock()
    proj = _fake_project(book_id=_BOOK)
    repo.create_or_get = AsyncMock(return_value=(proj, True))
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Dracula KG", "book_id": str(_BOOK)}
    )
    assert res.success, res.error
    assert res.result["project_id"] == str(proj.project_id)
    assert res.result["created"] is True
    assert res.result["book_id"] == str(_BOOK)


@pytest.mark.asyncio
async def test_book_less_create_skips_grant_check():
    """A book-less personal project needs no grant client call."""
    grant = AsyncMock()
    repo = AsyncMock()
    repo.create_or_get = AsyncMock(return_value=(_fake_project(), False))
    ctx = _mk_ctx(grant_client=grant, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "Scratchpad", "project_type": "general"}
    )
    assert res.success, res.error
    assert res.result["created"] is False
    grant.resolve_grant.assert_not_called()


@pytest.mark.asyncio
async def test_bad_book_id_is_tool_error():
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "X", "book_id": "not-a-uuid"}
    )
    assert not res.success
    assert "book_id" in res.error.lower()


@pytest.mark.asyncio
async def test_smuggled_scope_arg_rejected():
    """extra='forbid' — a hallucinated user_id/project_id is a tool error, not a
    silent scope override."""
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_project_create", {"name": "X", "user_id": "smuggled"}
    )
    assert not res.success


# ── kg_project_list (W0 #4a — the "no project in scope" discovery tool) ────────


def _fake_listed_project(*, name="P", archived=False):
    return SimpleNamespace(
        project_id=uuid4(),
        name=name,
        project_type="book",
        book_id=None,
        is_archived=archived,
    )


@pytest.mark.asyncio
async def test_project_list_is_owner_scoped_and_shaped():
    """kg_project_list serves the caller's OWN projects through the repo's
    user_id-filtered list, returning the compact discovery shape (id/name/
    type/book) the #4a error directive points the model at."""
    repo = AsyncMock()
    p1, p2 = _fake_listed_project(name="A"), _fake_listed_project(name="B")
    repo.list = AsyncMock(return_value=[p1, p2])
    ctx = _mk_ctx(projects_repo=repo)
    res = await execute_tool(ctx, "kg_project_list", {})
    assert res.success, res.error
    # the repo was queried for THIS caller only (identity from the envelope ctx)
    assert repo.list.await_args.args[0] == _USER
    names = [p["name"] for p in res.result["projects"]]
    assert names == ["A", "B"]
    assert res.result["projects"][0]["project_id"] == str(p1.project_id)
    assert res.result["more"] is False


@pytest.mark.asyncio
async def test_project_list_signals_overflow_and_respects_limit():
    """The repo fetches limit+1 to signal more pages — the tool must slice to
    `limit` and set more=True."""
    repo = AsyncMock()
    repo.list = AsyncMock(return_value=[_fake_listed_project() for _ in range(3)])
    ctx = _mk_ctx(projects_repo=repo)
    res = await execute_tool(ctx, "kg_project_list", {"limit": 2})
    assert res.success, res.error
    assert len(res.result["projects"]) == 2
    assert res.result["more"] is True
