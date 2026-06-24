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
