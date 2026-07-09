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

from app.ontology.confirm import DESC_BUILD_GRAPH, DESC_BUILD_WIKI, verify_action_token
from app.config import settings
from app.tools.executor import ToolContext, execute_tool

_USER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()


def _mk_ctx(*, embedding_model="emb-model-1", project_id=_PROJECT, owner=_USER, grant=None,
           book_id=_BOOK, mcp_key_id=None):
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(owner, _BOOK))
    repo.get = AsyncMock(
        return_value=SimpleNamespace(
            project_id=_PROJECT, embedding_model=embedding_model, book_id=book_id
        )
    )
    return ToolContext(
        user_id=_USER,
        project_id=project_id,
        session_id="sess-build",
        mcp_key_id=mcp_key_id,
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
async def test_build_graph_owner_keeps_high_effort():
    # D-RE-OTHER-AGENTIC-EFFORT: the project owner (caller == owner) has the high ceiling.
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": "gpt-x", "reasoning_effort": "high"})
    assert res.success, res.error
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.params["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_build_graph_clamps_effort_to_edit_grant():
    # An EDIT grantee (not the owner) requesting high effort is CLAMPED to medium at mint.
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)
    ctx = _mk_ctx(owner=uuid4(), grant=grant)
    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": "gpt-x", "reasoning_effort": "high"})
    assert res.success, res.error
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.params["reasoning_effort"] == "medium"  # high → EDIT ceiling


@pytest.mark.asyncio
async def test_build_wiki_clamps_effort_to_edit_grant():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)
    ctx = _mk_ctx(owner=uuid4(), grant=grant)
    res = await execute_tool(
        ctx, "kg_build_wiki", {"model_ref": "gpt-x", "reasoning_effort": "high"})
    assert res.success, res.error
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.params["reasoning_effort"] == "medium"


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
async def test_build_graph_arg_project_id_ignored_when_envelope_present():
    """H-I / D3: project_id is now an ACCEPTED arg (Wave-C Slice 3 public exposure),
    but the trusted ENVELOPE project still WINS — a first-party session cannot be
    redirected to another project by a smuggled arg. The minted token binds to the
    envelope project, not the arg."""
    ctx = _mk_ctx()  # envelope project = _PROJECT
    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": "gpt-x", "project_id": str(uuid4())}
    )
    assert res.success, res.error  # accepted now (no longer rejected as an extra field)
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.project_id == str(_PROJECT)  # envelope wins, NOT the smuggled arg


@pytest.mark.asyncio
async def test_build_graph_public_key_arg_scope_is_owner_gated_cross_tenant():
    """H-I + OD-8: a public MCP key (mcp_key_id set) has NO envelope project, so it
    supplies project_id as an arg. The executor adopts it, then the owner gate confines
    it — a project owned by ANOTHER tenant is denied with the anti-oracle 'project not
    found' (the SAME error a nonexistent project gives, so no existence oracle)."""
    other_owner = uuid4()  # the project's real owner != the caller (_USER)
    ctx = _mk_ctx(project_id=None, owner=other_owner, mcp_key_id="key-1")
    res = await execute_tool(
        ctx, "kg_build_graph", {"llm_model": "gpt-x", "project_id": str(_PROJECT)}
    )
    assert not res.success
    assert "project not found" in res.error.lower()


# ── kg_build_wiki mint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_wiki_mints_confirm_token():
    ctx = _mk_ctx()
    res = await execute_tool(ctx, "kg_build_wiki", {"model_ref": "gpt-x"})
    assert res.success, res.error
    assert res.result["descriptor"] == DESC_BUILD_WIKI
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.descriptor == DESC_BUILD_WIKI
    assert claims.params["model_ref"] == "gpt-x"
    assert claims.params["entity_ids"] == []  # empty ⇒ resolved to ALL at confirm


@pytest.mark.asyncio
async def test_build_wiki_requires_linked_book():
    ctx = _mk_ctx(book_id=None)
    res = await execute_tool(ctx, "kg_build_wiki", {"model_ref": "gpt-x"})
    assert not res.success
    assert "book" in res.error.lower()


@pytest.mark.asyncio
async def test_build_wiki_explicit_entity_subset_embedded():
    ctx = _mk_ctx()
    res = await execute_tool(
        ctx, "kg_build_wiki", {"model_ref": "gpt-x", "entity_ids": ["e1", "e2"]}
    )
    assert res.success, res.error
    import time as _t
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _t.time())
    assert claims.params["entity_ids"] == ["e1", "e2"]


# ── kg_build_wiki confirm-effect entity resolution (D-WIKI-ENTITY-FREQ-GATE) ──


@pytest.mark.asyncio
async def test_resolve_entity_ids_passes_min_frequency_1():
    """The 'all entities' path must call known-entities with min_frequency=1 so a
    single-chapter book (every entity freq 1) still yields its entities — the freq
    default 2 silently dropped them all → spurious BuildWikiNoEntities → 422.

    It must also PAGE (D-ANCHOR-PRELOAD-50-CAP — the un-limited call inherited the
    handler's silent default of 50, so a bigger book only ever got 50 wiki stubs)
    and must NOT send status="active" (D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM — the
    handler used to ignore that param; now that it honors it, "active" would empty
    the wiki, since both entity-creation paths insert status='draft')."""
    from app.ontology.build_wiki_effect import BuildWikiParams, _resolve_entity_ids

    glossary = AsyncMock()
    glossary.list_all_entities = AsyncMock(
        return_value=([{"entity_id": "e1"}, {"entity_id": "e2"}], False)
    )
    params = BuildWikiParams(model_ref="gpt-x")  # entity_ids empty ⇒ resolve ALL
    book_id = uuid4()
    out = await _resolve_entity_ids(params, book_id, glossary)
    assert out == ["e1", "e2"]
    glossary.list_all_entities.assert_awaited_once_with(
        book_id, status_filter=None, min_frequency=1
    )


@pytest.mark.asyncio
async def test_resolve_entity_ids_explicit_subset_skips_glossary():
    """An explicit entity subset is used verbatim — no glossary call (no freq gate)."""
    from app.ontology.build_wiki_effect import BuildWikiParams, _resolve_entity_ids

    glossary = AsyncMock()
    params = BuildWikiParams(model_ref="gpt-x", entity_ids=["x", "y"])
    out = await _resolve_entity_ids(params, uuid4(), glossary)
    assert out == ["x", "y"]
    glossary.list_entities.assert_not_awaited()
