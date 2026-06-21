"""Unit tests for kg_build_graph mint (D-KG-LF-BUILDKG-MCP).

The mint resolves the project's embedding model + grant-gates (EDIT) and returns a
confirm-token — it starts NO job (the confirm route does, after a human approves). These
fakes cover the mint gating; the job-start path is the existing _start_extraction_job_core
(covered by the extraction tests) reached via the confirm effect.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from loreweave_grants import GrantLevel

from app.ontology.confirm import DESC_BUILD_GRAPH, verify_action_token
from app.config import settings
from app.tools.executor import ToolContext, execute_tool

_USER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()


def _mk_ctx(*, embedding_model="emb-model-1", project_id=_PROJECT, owner=_USER, grant=None):
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(owner, _BOOK))
    repo.get = AsyncMock(
        return_value=SimpleNamespace(project_id=_PROJECT, embedding_model=embedding_model)
    )
    return ToolContext(
        user_id=_USER,
        project_id=project_id,
        session_id="sess-build",
        projects_repo=repo,
        pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(),
        redis=None,
        grant_client=grant or AsyncMock(),
        graph_views_repo=AsyncMock(),
        graph_schemas_repo=AsyncMock(),
        triage_repo=AsyncMock(),
        ontology_resolver=AsyncMock(),
        ontology_mutations_repo=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_build_graph_mints_confirm_token_when_configured():
    ctx = _mk_ctx()
    res = await execute_tool(ctx, "kg_build_graph", {"llm_model": "gpt-x", "scope": "all"})
    assert res.success, res.error
    assert res.result["descriptor"] == DESC_BUILD_GRAPH
    tok = res.result["confirm_token"]
    assert tok
    import time as _t
    claims = verify_action_token(settings.jwt_secret, tok, _t.time())
    assert claims.descriptor == DESC_BUILD_GRAPH
    assert claims.user_id == str(_USER)  # bound to the proposer
    assert claims.params["embedding_model"] == "emb-model-1"  # resolved from the project
    assert claims.params["llm_model"] == "gpt-x"


@pytest.mark.asyncio
async def test_build_graph_requires_embedding_model():
    ctx = _mk_ctx(embedding_model=None)
    res = await execute_tool(ctx, "kg_build_graph", {"llm_model": "gpt-x"})
    assert not res.success
    assert "embedding model" in res.error.lower()


@pytest.mark.asyncio
async def test_build_graph_requires_project_in_scope():
    ctx = _mk_ctx(project_id=None)
    res = await execute_tool(ctx, "kg_build_graph", {"llm_model": "gpt-x"})
    assert not res.success
    assert "project" in res.error.lower()


@pytest.mark.asyncio
async def test_build_graph_denied_for_non_grantee():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.NONE)
    # owner != caller and no grant → resolve-to-owner refuses (no oracle).
    ctx = _mk_ctx(owner=uuid4(), grant=grant)
    res = await execute_tool(ctx, "kg_build_graph", {"llm_model": "gpt-x"})
    assert not res.success


@pytest.mark.asyncio
async def test_build_graph_invalid_scope_rejected():
    ctx = _mk_ctx()
    res = await execute_tool(ctx, "kg_build_graph", {"llm_model": "gpt-x", "scope": "bogus"})
    assert not res.success


@pytest.mark.asyncio
async def test_build_graph_smuggled_scope_arg_rejected():
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": "gpt-x", "project_id": "smuggled"}
    )
    assert not res.success
