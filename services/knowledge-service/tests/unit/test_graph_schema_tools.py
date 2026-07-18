"""Lane LF — unit tests for the KG ontology MCP tool surface.

Covers, mirroring `test_tool_definitions.py` / `test_tool_executor.py`:
  * tool-schema validity + drift-lock against the arg models;
  * the design-D3 envelope/tool-arg separation (no scope key is a field);
  * class-C deferral — the confirm-token tools are NOT registered;
  * executor dispatch through the unified validate→dispatch path;
  * envelope-scoping (identity from ctx, never from args);
  * ownership / project-grant gating;
  * `kg_propose_edge` temporal-required rejection at mint;
  * `kg_propose_*` go to the inbox (pending-facts / triage), never Neo4j.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extraction.anchor_loader import ProjectionResult
from app.tools.definitions import ARG_MODELS, TOOL_DEFINITIONS, TOOL_NAMES
from app.tools.executor import ToolContext, ToolExecutionError, execute_tool
from app.tools.graph_schema_tools import (
    GRAPH_SCHEMA_ARG_MODELS,
    GRAPH_SCHEMA_TOOL_DEFINITIONS,
    KgGraphQueryArgs,
    KgMultiQueryArgs,
    KgProposeEdgeArgs,
    KgTriageResolveArgs,
    KgWorldQueryArgs,
    _resolve_project_owner,
    _resolve_project_owner_and_level,
)

try:
    from loreweave_grants import GrantLevel
except ModuleNotFoundError:  # pragma: no cover - SDK on path in CI
    GrantLevel = None  # type: ignore

_USER = uuid4()
_OWNER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()

# INV-K2 (H-I-amended): user_id / session_id are envelope-only FOREVER (identity).
# project_id is NO LONGER here — it is a deliberately-allowed, ownership-checked
# SCOPE arg on the kg READ **and WRITE/BUILD** tools (Wave-C Slice 3 exposed the
# writes; the public edge mints no X-Project-Id, so a public agent supplies it; the
# owner gate confines it to the caller's own projects).
_ENVELOPE_KEYS = {"user_id", "session_id"}

# The 15 tools this lane builds (R + reversible W) — incl. Track-B kg_world_query +
# kg_multi_query (B1(3): arbitrary owner-owned project set) and WS-4B
# kg_project_entities_to_nodes (deterministic glossary→node projection).
_LANE_LF_TOOLS = {
    "kg_graph_query",
    "kg_world_query",
    "kg_multi_query",
    "kg_entity_edge_timeline",
    "kg_schema_read",
    "kg_list_templates",
    "kg_sync_available",
    "kg_view_read",
    "kg_triage_list",
    "kg_propose_fact",
    "kg_propose_edge",
    "kg_project_entities_to_nodes",
    "kg_create_node",
    "kg_view_upsert",
    "kg_view_delete",
    "kg_triage_resolve",
}

# KM6 live class-C tools — registered, but each MINTS a confirm-token (no write); the
# human confirms via /v1/kg/actions/confirm. M1: schema_edit, M2: adopt, M3: sync_apply,
# E2: triage_place_edge (place a proposed_edge), E3: triage_schema_write (schema-mutating
# triage resolution) — both via the confirm spine.
_CLASS_C_LIVE_TOOLS = {
    "kg_schema_edit", "kg_adopt_template", "kg_sync_apply",
    "kg_triage_place_edge", "kg_triage_schema_write",
}

# Every KG tool registered in the catalog (R + reversible W + live class-C).
_REGISTERED_KG_TOOLS = _LANE_LF_TOOLS | _CLASS_C_LIVE_TOOLS

# The class-C tools STILL deferred to later KM6 sub-phases / KM5 — they must NOT be
# registered anywhere yet.
_CLASS_C_TOOLS = {
    "kg_triage_handoff_glossary",
    "kg_admin_template_read",
    "kg_admin_propose_template",
}


def _defn(name: str) -> dict:
    return next(d for d in TOOL_DEFINITIONS if d["function"]["name"] == name)


# ── registry consistency ──────────────────────────────────────────────


def test_total_tool_count_is_memory_plus_lane_lf():
    """5 memory + 1 story_search (#12 universal manuscript search) + 15 lane-LF
    (incl. Track-B kg_world_query + kg_multi_query and WS-4B
    kg_project_entities_to_nodes) + 5 live class-C + 3 project lifecycle
    (kg_project_create + kg_project_list, the W0 #4a discovery tool, +
    kg_project_set_embedding_model — the F6 setup step that used to exist only as a
    REST route behind the Build-KG dialog, which left kg_build_graph unreachable by an
    agent) + 2 cost-gated (kg_build_graph, kg_build_wiki) + 1 kg_run_benchmark (R4)
    + 4 W11-M2 reader tools (lore_ask/lore_browse_entities/lore_entity/lore_timeline)
    + 1 W10-M1 kg_create_node (manual single-node create)
    = 37."""
    schema_names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert len(TOOL_DEFINITIONS) == 37
    assert set(TOOL_NAMES) == set(ARG_MODELS) == schema_names
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)  # no dupes
    assert {"kg_project_create", "kg_project_list", "kg_project_set_embedding_model",
            "kg_build_graph", "kg_build_wiki", "kg_run_benchmark",
            "story_search"}.issubset(schema_names)
    assert {"lore_ask", "lore_browse_entities", "lore_entity",
            "lore_timeline"}.issubset(schema_names)


def test_agent_can_reach_kg_build_graph_without_leaving_the_tool_surface():
    """F6 (Track D liveness eval). kg_build_graph's precondition — a configured embedding
    model — must be satisfiable BY A TOOL. Before this the chain was:

        kg_project_create ✅ → [configure embedding model ❌ REST + GUI only]
                             → kg_run_benchmark ✅ → kg_build_graph ✅

    so every agent-created project dead-ended, and the precondition error told the model
    to open a dialog it cannot open. Assert every link exists on the tool surface, and
    that the prose never sends a tool-caller to the UI."""
    schema_names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    chain = ["kg_project_create", "kg_project_set_embedding_model",
             "kg_run_benchmark", "kg_build_graph"]
    missing = [n for n in chain if n not in schema_names]
    assert not missing, f"kg_build_graph is unreachable by an agent — missing: {missing}"

    build = _defn("kg_build_graph")["function"]["description"]
    assert "kg_project_set_embedding_model" in build
    assert "dialog" not in build.lower()


def test_lane_lf_tools_all_registered():
    assert _REGISTERED_KG_TOOLS == set(GRAPH_SCHEMA_ARG_MODELS)
    schema_names = {d["function"]["name"] for d in GRAPH_SCHEMA_TOOL_DEFINITIONS}
    assert schema_names == _REGISTERED_KG_TOOLS


def test_class_c_tools_are_not_registered():
    """INV-T3 — the STILL-deferred class-C tools (handoff + System-tier admin) must be
    absent from the user catalog. The 5 live class-C tools (schema_edit / adopt /
    sync_apply / triage_place_edge / triage_schema_write) ARE registered + MCP-exposed
    as of D-KG-LF-KM6 — each mints a confirm-token (no direct write); admin tools live
    behind the separate RS256-gated /mcp/admin endpoint."""
    all_names = set(TOOL_NAMES)
    leaked = _CLASS_C_TOOLS & all_names
    assert not leaked, f"deferred class-C tools leaked into the catalog: {leaked}"


# ── OpenAI schema well-formedness + drift lock ────────────────────────


@pytest.mark.parametrize("name", sorted(_REGISTERED_KG_TOOLS))
def test_tool_is_valid_openai_function_schema(name: str):
    defn = _defn(name)
    assert defn["type"] == "function"
    fn = defn["function"]
    assert isinstance(fn["name"], str) and fn["name"]
    assert isinstance(fn["description"], str) and len(fn["description"]) > 20
    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["additionalProperties"] is False
    assert set(params["required"]).issubset(params["properties"])
    for prop_name, prop in params["properties"].items():
        assert "type" in prop, prop_name
        assert prop.get("description"), prop_name


@pytest.mark.parametrize("name", sorted(_REGISTERED_KG_TOOLS))
def test_schema_properties_match_arg_model_fields(name: str):
    params = _defn(name)["function"]["parameters"]
    model = ARG_MODELS[name]
    assert set(params["properties"]) == set(model.model_fields)
    schema_required = set(params["required"])
    model_required = {
        f for f, info in model.model_fields.items() if info.is_required()
    }
    assert schema_required == model_required


def test_no_envelope_keys_leak_into_any_lane_lf_schema():
    """Design D3 / INV-K2 (H-I-amended) — user_id / session_id are envelope
    identity fields, NEVER tool parameters. (project_id IS allowed on the kg-read
    tools as an ownership-checked scope arg — see
    test_kg_read_tools_accept_project_id_arg.)"""
    for name in _REGISTERED_KG_TOOLS:
        props = set(_defn(name)["function"]["parameters"]["properties"])
        assert _ENVELOPE_KEYS.isdisjoint(props), name
        assert _ENVELOPE_KEYS.isdisjoint(GRAPH_SCHEMA_ARG_MODELS[name].model_fields)


# ── arg-model validation ──────────────────────────────────────────────


def test_graph_query_defaults_and_bounds():
    args = KgGraphQueryArgs()
    assert args.view is None and args.as_of_chapter is None
    assert args.limit == 500
    with pytest.raises(ValidationError):
        KgGraphQueryArgs(limit=2001)  # le=2000
    with pytest.raises(ValidationError):
        KgGraphQueryArgs(as_of_chapter=-1)  # ge=0


def test_kg_read_tools_accept_project_id_arg():
    """H-I — project_id is now a valid, optional, ownership-checked scope arg on
    the kg-READ tools. The owner gate (executor) confines it to the caller's own
    projects; extra='forbid' still rejects identity keys."""
    assert KgGraphQueryArgs(project_id="p1").project_id == "p1"
    assert KgGraphQueryArgs().project_id is None  # optional
    with pytest.raises(ValidationError):
        KgGraphQueryArgs(user_id="smuggled")  # identity stays forbidden


def test_arg_models_reject_smuggled_scope_override():
    """extra='forbid' — identity keys (user_id / session_id) are NEVER accepted on a
    WRITE tool. project_id IS now an accepted, OPTIONAL, ownership-checked scope arg
    on the kg WRITE tools too (Wave-C Slice 3 public exposure — the executor's owner
    gate confines it to the caller's own projects, with OD-8 owned-only for public
    keys); only identity stays envelope-only forever."""
    # H-I: project_id is now a valid optional scope arg on writes (owner-gated downstream).
    assert (
        KgProposeEdgeArgs(
            source_entity_id="a", target_entity_id="b", edge_type="loves",
            project_id="x",
        ).project_id
        == "x"
    )
    # Identity keys remain forbidden, forever (envelope-only).
    with pytest.raises(ValidationError):
        KgProposeEdgeArgs(
            source_entity_id="a", target_entity_id="b", edge_type="loves",
            user_id="smuggled",
        )
    with pytest.raises(ValidationError):
        KgProposeEdgeArgs(
            source_entity_id="a", target_entity_id="b", edge_type="loves",
            session_id="smuggled",
        )


def test_triage_resolve_rejects_class_c_actions_at_the_model():
    """The arg model's Literal excludes schema-mutating / handoff actions —
    they can't even be expressed (defense-in-depth on top of the handler check)."""
    KgTriageResolveArgs(signature="s", action="map")
    for c_action in ("add_to_vocab", "add_to_schema", "widen_target_kinds",
                     "set_multi_active", "promote_to_glossary_kind",
                     "demote_to_attribute"):
        with pytest.raises(ValidationError):
            KgTriageResolveArgs(signature="s", action=c_action)


# ── executor dispatch fixtures ────────────────────────────────────────


def _ctx(*, user_id=_OWNER, project_id=_PROJECT, projects_repo=None, **deps) -> ToolContext:
    """A KG-tool ToolContext. By default the caller IS the owner (the grant
    gate passes without consulting the grant client); pass a projects_repo
    whose project_meta returns a different owner to exercise the grantee path."""
    if projects_repo is None:
        projects_repo = AsyncMock()
        # Default project_meta → (caller, book) so caller==owner ⇒ gate passes.
        projects_repo.project_meta = AsyncMock(return_value=(user_id, _BOOK))
    base = dict(
        projects_repo=projects_repo,
        pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(),
        redis=None,
        grant_client=AsyncMock(),
        graph_views_repo=AsyncMock(),
        graph_schemas_repo=AsyncMock(),
        triage_repo=AsyncMock(),
        ontology_resolver=AsyncMock(),
        ontology_mutations_repo=AsyncMock(),
    )
    base.update(deps)
    return ToolContext(
        user_id=user_id,
        project_id=project_id,
        session_id="sess-kg",
        **base,
    )


def _resolved_schema(edge_types=None, schema_version=3):
    return SimpleNamespace(
        project_id=str(_PROJECT),
        schema_version=schema_version,
        allow_free_edges=True,
        edge_types=edge_types or [],
        fact_types=[],
        vocab_sets=[],
        vocab_values={},
        node_kinds=[],
        model_dump=lambda mode="json": {"schema_version": schema_version, "edge_types": []},
    )


# ── envelope-scoping + gating ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_read_requires_project_in_scope():
    ctx = _ctx(project_id=None)
    res = await execute_tool(ctx, "kg_schema_read", {})
    assert not res.success
    assert "project" in res.error.lower()


@pytest.mark.asyncio
async def test_project_tool_404s_for_non_grantee():
    """A caller who is neither owner nor a grantee gets a tool error (no
    existence oracle) — identity comes from ctx, the args carry no scope."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.NONE)
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant)
    res = await execute_tool(ctx, "kg_view_read", {})
    assert not res.success
    assert "not found" in res.error.lower()


@pytest.mark.asyncio
async def test_hi_kg_read_project_id_arg_hoisted_and_owner_checked():
    """H-I — a kg-read tool's project_id arg supplies scope when the envelope has
    none (the executor hoist), and the owner gate then validates it: a project the
    caller neither owns nor has a grant on yields the uniform 'project not found'."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.NONE)
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # not the caller
    ctx = _ctx(user_id=_USER, project_id=None,
               projects_repo=projects_repo, grant_client=grant)
    res = await execute_tool(ctx, "kg_schema_read", {"project_id": str(uuid4())})
    assert not res.success
    assert "not found" in res.error.lower()


@pytest.mark.asyncio
async def test_hi_kg_write_project_id_arg_hoisted_and_owner_checked():
    """H-I (Wave-C Slice 3) — a kg-WRITE tool's project_id arg now supplies scope for
    a public key (no envelope project); the owner gate then confines it. A public key
    targeting ANOTHER tenant's project is denied with the uniform 'project not found'
    (OD-8 owned-only, before grants are consulted), proving the newly-exposed write
    surface is tenant-safe."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # would pass IF consulted
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    ctx = _ctx(user_id=_USER, project_id=None, projects_repo=projects_repo,
               grant_client=grant, mcp_key_id="lw_pk_publickey")
    res = await execute_tool(
        ctx, "kg_propose_fact",
        {"fact_text": "x", "fact_type": "decision", "project_id": str(uuid4())},
    )
    assert not res.success
    assert "not found" in res.error.lower()
    grant.resolve_grant.assert_not_awaited()  # OD-8 short-circuits before grants


@pytest.mark.asyncio
async def test_public_key_call_is_owned_only_no_grants():
    """OD-8 — a public MCP-key call (mcp_key_id set) gets owned-only access: a
    project owned by someone ELSE is rejected BEFORE the grant client is consulted,
    even when the caller would otherwise hold an EDIT grant on the book. A
    third-party agent must never inherit the owner's share-grants."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # would pass IF consulted
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant,
               mcp_key_id="lw_pk_publickey")
    res = await execute_tool(ctx, "kg_view_read", {})
    assert not res.success
    assert "not found" in res.error.lower()
    grant.resolve_grant.assert_not_awaited()  # OD-8 short-circuits before grants


@pytest.mark.asyncio
async def test_resolve_project_owner_public_key_owner_still_allowed():
    """OD-8 only drops GRANT-derived access — a public key acting as the project
    OWNER resolves normally (both resolver variants)."""
    grant = AsyncMock()
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_USER, _BOOK))  # caller IS owner
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant,
               mcp_key_id="lw_pk_publickey")
    assert await _resolve_project_owner(ctx, GrantLevel.EDIT) == _USER
    owner, lvl = await _resolve_project_owner_and_level(ctx, GrantLevel.EDIT)
    assert owner == _USER and lvl == GrantLevel.OWNER
    grant.resolve_grant.assert_not_awaited()  # owner path never consults grants


@pytest.mark.asyncio
async def test_resolve_project_owner_and_level_public_key_denied_before_grants():
    """Symmetry: the _and_level variant also short-circuits a non-owner public-key
    call before the grant client (would otherwise return a grant level)."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.OWNER)  # would pass IF consulted
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant,
               mcp_key_id="lw_pk_publickey")
    with pytest.raises(ToolExecutionError, match="not found"):
        await _resolve_project_owner_and_level(ctx, GrantLevel.VIEW)
    grant.resolve_grant.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_party_grantee_path_unchanged_by_od8():
    """Regression: a FIRST-PARTY call (mcp_key_id is None) keeps the grant-aware
    path — a book grantee still resolves to the owner via the grant client."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant)  # no mcp_key_id
    assert await _resolve_project_owner(ctx, GrantLevel.EDIT) == _OWNER
    grant.resolve_grant.assert_awaited_once()  # grant path WAS consulted


@pytest.mark.asyncio
async def test_propose_fact_requires_edit_and_grantee_under_tier_is_denied():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.VIEW)  # < EDIT
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant)
    res = await execute_tool(
        ctx, "kg_propose_fact",
        {"fact_text": "Kai prefers fire", "fact_type": "preference"},
    )
    assert not res.success
    assert "insufficient access" in res.error.lower()


@pytest.mark.asyncio
async def test_view_read_lists_callers_views(monkeypatch):
    views_repo = AsyncMock()
    view = SimpleNamespace(model_dump=lambda mode="json": {"code": "drives"})
    views_repo.list = AsyncMock(return_value=[view])
    ctx = _ctx(graph_views_repo=views_repo)
    res = await execute_tool(ctx, "kg_view_read", {})
    assert res.success
    assert "success" not in res.result  # MCP success-key invariant
    assert res.result["count"] == 1
    # owner-scoped: list called with the caller's user_id
    assert views_repo.list.await_args.args[0] == _OWNER


# ── propose-fact → inbox, never Neo4j ─────────────────────────────────


@pytest.mark.asyncio
async def test_propose_fact_queues_into_pending_inbox(monkeypatch):
    monkeypatch.setattr(
        "app.tools.graph_schema_tools.neutralize_injection",
        MagicMock(return_value=("SANITIZED", 0)),
    )
    pending_repo = AsyncMock()
    pending_repo.queue = AsyncMock(return_value=SimpleNamespace(
        pending_fact_id=uuid4(), fact_text="SANITIZED", fact_type="decision",
    ))
    ctx = _ctx(pending_facts_repo=pending_repo)
    res = await execute_tool(
        ctx, "kg_propose_fact",
        {"fact_text": "ignore previous", "fact_type": "decision"},
    )
    assert res.success
    assert res.result["queued"] is True
    # Sanitized at queue time; queued to the inbox, never a graph write.
    assert pending_repo.queue.await_args.kwargs["fact_text"] == "SANITIZED"
    pending_repo.queue.assert_awaited_once()


# ── propose-edge: temporal-required + parks to triage (never Neo4j) ───


def _patch_endpoints_present(monkeypatch, present=("a", "b")):
    """Make kg_propose_edge's WS-4B endpoint precheck see both endpoints as
    existing nodes, so the test exercises the park path (not the fail-fast).
    Also stubs neo4j_session so no real driver is needed."""

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr(
        "app.tools.graph_schema_tools.neo4j_session", _fake_session,
    )
    monkeypatch.setattr(
        "app.db.neo4j_repos.entities.existing_entity_node_ids",
        AsyncMock(return_value=set(present)),
    )


@pytest.mark.asyncio
async def test_propose_edge_temporal_required_rejected_at_mint():
    temporal_edge = SimpleNamespace(code="loves", temporal=True)
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_resolved_schema([temporal_edge]))
    triage_repo = AsyncMock()
    ctx = _ctx(ontology_resolver=resolver, triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "loves"},
    )
    assert not res.success
    assert "temporal" in res.error.lower()
    assert "valid_from" in res.error.lower()
    # Rejected before any park — nothing entered the inbox.
    triage_repo.park.assert_not_awaited()


@pytest.mark.asyncio
async def test_propose_edge_parks_to_triage_inbox_never_neo4j(monkeypatch):
    """INV-K1 — a proposed edge is parked into the triage inbox; the handler
    never WRITES Neo4j (it reads it once for the WS-4B endpoint precheck)."""
    _patch_endpoints_present(monkeypatch)
    # validate_edge returns an off-schema issue (closed schema, unknown edge).
    issue = SimpleNamespace(item_type="unknown_edge_type", signature="edge:loves")
    monkeypatch.setattr(
        "app.tools.graph_schema_tools.validate_edge",
        MagicMock(return_value=issue),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_resolved_schema([], schema_version=4))
    triage_repo = AsyncMock()
    triage_repo.park = AsyncMock(return_value=SimpleNamespace(
        triage_id=uuid4(), item_type="unknown_edge_type", signature="edge:loves",
    ))
    ctx = _ctx(ontology_resolver=resolver, triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "loves",
         "valid_from": 12},
    )
    assert res.success
    assert res.result["parked"] is True
    assert res.result["on_schema"] is False
    park_kwargs = triage_repo.park.await_args.kwargs
    assert park_kwargs["item_type"] == "unknown_edge_type"
    assert park_kwargs["schema_version"] == 4
    # Owner-scoped park (caller is owner here).
    assert park_kwargs["user_id"] == _OWNER


@pytest.mark.asyncio
async def test_propose_edge_on_schema_parks_as_proposed_edge(monkeypatch):
    # D-KG-LF-PROPOSE-EDGE-INBOX: a well-formed on-schema proposal parks as its own
    # `proposed_edge` item_type — NOT edge_cardinality_conflict (a stateful
    # condition the tool can't check, INV-K1).
    _patch_endpoints_present(monkeypatch)
    monkeypatch.setattr(
        "app.tools.graph_schema_tools.validate_edge",
        MagicMock(return_value=None),  # on-schema, no issue
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_resolved_schema(
        [SimpleNamespace(code="allies", temporal=False)]
    ))
    triage_repo = AsyncMock()
    triage_repo.park = AsyncMock(return_value=SimpleNamespace(
        triage_id=uuid4(), item_type="proposed_edge",
        signature="propose_edge:allies:a->b",
    ))
    ctx = _ctx(ontology_resolver=resolver, triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "allies"},
    )
    assert res.success
    assert res.result["on_schema"] is True
    assert triage_repo.park.await_args.kwargs["item_type"] == "proposed_edge"


@pytest.mark.asyncio
async def test_propose_edge_fails_fast_when_endpoint_not_a_node(monkeypatch):
    """WS-4B / contract C5 — an edge whose endpoint isn't a graph node yet is
    rejected UP FRONT with KG_ENDPOINT_NOT_NODE + the missing ids, and is NEVER
    parked (no dead-end park→fail-at-confirm)."""

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr(
        "app.tools.graph_schema_tools.neo4j_session", _fake_session,
    )
    # only "a" exists as a node; "b" is missing.
    monkeypatch.setattr(
        "app.db.neo4j_repos.entities.existing_entity_node_ids",
        AsyncMock(return_value={"a"}),
    )
    monkeypatch.setattr(
        "app.tools.graph_schema_tools.validate_edge",
        MagicMock(return_value=None),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_resolved_schema(
        [SimpleNamespace(code="allies", temporal=False)]
    ))
    triage_repo = AsyncMock()
    ctx = _ctx(ontology_resolver=resolver, triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "allies"},
    )
    assert not res.success
    assert res.code == "KG_ENDPOINT_NOT_NODE"
    assert res.detail == {"missing": ["b"]}
    assert "kg_project_entities_to_nodes" in res.error
    # never parked — the whole point of fail-fast.
    triage_repo.park.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_entities_to_nodes_returns_counts(monkeypatch):
    """WS-4B — the projection tool returns {nodes_created, nodes_existing} from
    the orchestrator, scoped to the project's book, under the owner."""

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr(
        "app.tools.graph_schema_tools.neo4j_session", _fake_session,
    )
    monkeypatch.setattr(
        "app.clients.glossary_client.get_glossary_client",
        MagicMock(return_value=MagicMock()),
    )
    proj = AsyncMock(
        return_value=ProjectionResult(created=3, existing=1, seen=4, skipped=0),
    )
    monkeypatch.setattr(
        "app.extraction.anchor_loader.project_glossary_entities_to_nodes", proj,
    )
    ctx = _ctx()  # caller == owner, project_meta → (_OWNER, _BOOK)
    res = await execute_tool(ctx, "kg_project_entities_to_nodes", {})
    assert res.success
    assert res.result == {
        "nodes_created": 3, "nodes_existing": 1, "entities_seen": 4, "skipped": 0,
    }
    kw = proj.await_args.kwargs
    assert kw["user_id"] == str(_OWNER)
    assert kw["book_id"] == _BOOK
    assert kw["entity_ids"] is None  # whole-glossary when none given


@pytest.mark.asyncio
async def test_project_entities_to_nodes_refreshes_stat_cache(monkeypatch):
    """D-KG-STAT-CACHE-DEAD (rail HIGH): after a projection, the handler recounts the
    stat cache so `connections` becomes KNOWN — otherwise the vision-to-book rail
    (connect-people done_when "connections > 0") stalls forever at STOP_UNKNOWN because
    stat_updated_at has no other production writer."""

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr("app.tools.graph_schema_tools.neo4j_session", _fake_session)
    monkeypatch.setattr(
        "app.clients.glossary_client.get_glossary_client",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.extraction.anchor_loader.project_glossary_entities_to_nodes",
        AsyncMock(return_value=ProjectionResult(created=3, existing=1, seen=4, skipped=0)),
    )
    reconcile = AsyncMock(return_value={"stat_entity_count": 4})
    # the handler imports reconcile_project_stats locally, so patch the module attribute
    monkeypatch.setattr("app.jobs.stats_updater.reconcile_project_stats", reconcile)

    ctx = _ctx()  # caller == owner, project_meta → (_OWNER, _BOOK)
    res = await execute_tool(ctx, "kg_project_entities_to_nodes", {})
    assert res.success
    reconcile.assert_awaited_once()
    args = reconcile.await_args.args
    assert args[2] == _OWNER and args[3] == _PROJECT  # (pool, session, user_id, project_id)


@pytest.mark.asyncio
async def test_project_entities_to_nodes_survives_stat_recount_failure(monkeypatch):
    """The stat recount is advisory — a recount error must NOT fail an otherwise-successful
    projection (the nodes were placed; the counter is a best-effort cache)."""

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr("app.tools.graph_schema_tools.neo4j_session", _fake_session)
    monkeypatch.setattr(
        "app.clients.glossary_client.get_glossary_client",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.extraction.anchor_loader.project_glossary_entities_to_nodes",
        AsyncMock(return_value=ProjectionResult(created=2, existing=0, seen=2, skipped=0)),
    )
    monkeypatch.setattr(
        "app.jobs.stats_updater.reconcile_project_stats",
        AsyncMock(side_effect=RuntimeError("neo4j down")),
    )
    ctx = _ctx()
    res = await execute_tool(ctx, "kg_project_entities_to_nodes", {})
    assert res.success
    assert res.result["nodes_created"] == 2


@pytest.mark.asyncio
async def test_project_entities_to_nodes_bookless_project_errors():
    """A book-less project has no glossary to project → a clear tool error."""
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, None))
    ctx = _ctx(projects_repo=projects_repo)
    res = await execute_tool(ctx, "kg_project_entities_to_nodes", {})
    assert not res.success
    assert "isn't linked to a book" in res.error


@pytest.mark.asyncio
async def test_propose_edge_rejects_valid_to_before_valid_from():
    # D-KG-LF-PROPOSE-VALIDTO: a closing ordinal before the opening one is a
    # malformed temporal window → rejected at mint (Pydantic model_validator).
    ctx = _ctx()
    res = await execute_tool(
        ctx, "kg_propose_edge",
        {"source_entity_id": "a", "target_entity_id": "b", "edge_type": "allies",
         "valid_from": 10, "valid_to": 3},
    )
    assert not res.success
    assert "valid_to" in res.error.lower()


def test_propose_edge_args_temporal_window_boundaries():
    # D-KG-LF-PROPOSE-VALIDTO — pin the validator boundaries directly on the model.
    from app.tools.graph_schema_tools import KgProposeEdgeArgs

    base = dict(source_entity_id="a", target_entity_id="b", edge_type="allies")
    # equal is allowed (an edge that opens and closes in the same chapter)
    KgProposeEdgeArgs(**base, valid_from=5, valid_to=5)
    # one side None → no window constraint
    KgProposeEdgeArgs(**base, valid_from=10)
    KgProposeEdgeArgs(**base, valid_to=10)
    # neither → fine
    KgProposeEdgeArgs(**base)
    # closing before opening → rejected
    with pytest.raises(ValueError):
        KgProposeEdgeArgs(**base, valid_from=10, valid_to=3)


# ── triage_resolve: KG-local only, valid-action gating ────────────────


@pytest.mark.asyncio
async def test_triage_resolve_kg_local_action_resolves_signature():
    triage_repo = AsyncMock()
    triage_repo.list_pending_for_signature = AsyncMock(
        return_value=[SimpleNamespace(item_type="unknown_edge_type")]
    )
    triage_repo.resolve_signature = AsyncMock(return_value=3)
    ctx = _ctx(triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_triage_resolve", {"signature": "edge:loves", "action": "map"},
    )
    assert res.success
    assert res.result["status"] == "resolved"
    assert res.result["affected"] == 3
    assert triage_repo.resolve_signature.await_args.kwargs["new_status"] == "resolved"


@pytest.mark.asyncio
async def test_triage_resolve_action_invalid_for_item_type_is_tool_error():
    triage_repo = AsyncMock()
    # close_previous is KG-local but only valid for edge_cardinality_conflict.
    triage_repo.list_pending_for_signature = AsyncMock(
        return_value=[SimpleNamespace(item_type="unknown_edge_type")]
    )
    ctx = _ctx(triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_triage_resolve",
        {"signature": "edge:loves", "action": "close_previous"},
    )
    assert not res.success
    assert "not valid for item_type" in res.error
    triage_repo.resolve_signature.assert_not_awaited()


@pytest.mark.asyncio
async def test_triage_resolve_unknown_signature_is_tool_error():
    triage_repo = AsyncMock()
    triage_repo.list_pending_for_signature = AsyncMock(return_value=[])
    ctx = _ctx(triage_repo=triage_repo)
    res = await execute_tool(
        ctx, "kg_triage_resolve", {"signature": "ghost", "action": "map"},
    )
    assert not res.success
    assert "no pending triage items" in res.error


# ── view upsert / delete (owner == caller) ────────────────────────────


@pytest.mark.asyncio
async def test_view_upsert_is_owner_scoped_to_caller():
    views_repo = AsyncMock()
    view = SimpleNamespace(model_dump=lambda mode="json": {"code": "drives"})
    views_repo.upsert = AsyncMock(return_value=(view, True))
    ctx = _ctx(graph_views_repo=views_repo)
    res = await execute_tool(
        ctx, "kg_view_upsert", {"code": "drives", "name": "Drives"},
    )
    assert res.success
    assert res.result["created"] is True
    # upsert keyed on the CALLER's user_id, never another user's.
    assert views_repo.upsert.await_args.args[0] == _OWNER


@pytest.mark.asyncio
async def test_view_delete_reports_real_outcome():
    views_repo = AsyncMock()
    views_repo.delete = AsyncMock(return_value=False)
    ctx = _ctx(graph_views_repo=views_repo)
    res = await execute_tool(ctx, "kg_view_delete", {"code": "ghost"})
    assert res.success
    assert res.result["deleted"] is False


# ── KM6 — kg_schema_edit (class-C mint; NO write) ─────────────────────


@pytest.mark.asyncio
async def test_schema_edit_mints_confirm_token_and_does_not_write():
    """The class-C tool returns a confirm_token bound to the proposer + the live
    schema_id/version, and performs NO mutation (INV-K1/INV-T3)."""
    import time as _time

    from app.config import settings
    from app.ontology.confirm import AUTH_GRANT, DESC_SCHEMA_EDIT, verify_action_token

    sid = uuid4()
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=sid, schema_version=7)
    )
    mutations = AsyncMock()
    ctx = _ctx(graph_schemas_repo=schemas, ontology_mutations_repo=mutations)  # caller==owner
    res = await execute_tool(
        ctx, "kg_schema_edit",
        {"verb": "add", "level": "edge_type", "code": "WORSHIPS", "label": "Worships"},
    )
    assert res.success
    out = res.result
    assert out["proposed"] is True and out["descriptor"] == DESC_SCHEMA_EDIT
    assert out["confirm_token"]
    # No write — only a token minted.
    mutations.add_edge_type.assert_not_called()
    mutations.add_fact_type.assert_not_called()
    # The token verifies and carries the proposer + optimistic-concurrency anchor.
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], _time.time())
    assert claims.authority == AUTH_GRANT
    assert claims.user_id == str(ctx.user_id)
    assert claims.project_id == str(_PROJECT)
    assert claims.params["schema_id"] == str(sid)
    assert claims.params["expected_schema_version"] == 7
    assert claims.params["verb"] == "add" and claims.params["code"] == "WORSHIPS"


@pytest.mark.asyncio
async def test_schema_edit_label_defaults_to_code():
    import time as _time

    from app.config import settings
    from app.ontology.confirm import verify_action_token

    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=1)
    )
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(
        ctx, "kg_schema_edit", {"verb": "add", "level": "fact_type", "code": "prophecy"},
    )
    assert res.success
    claims = verify_action_token(settings.jwt_secret, res.result["confirm_token"], _time.time())
    assert claims.params["label"] == "prophecy"  # defaulted from code


@pytest.mark.asyncio
async def test_schema_edit_rejects_project_without_adopted_schema():
    """A project resolving to the System `general` template (no project-scoped row)
    has nothing project-local to edit — the tool refuses (never edits System tier)."""
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(return_value=None)
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(
        ctx, "kg_schema_edit", {"verb": "add", "level": "edge_type", "code": "X", "label": "X"},
    )
    assert not res.success
    assert "adopt" in res.error.lower()


@pytest.mark.asyncio
async def test_schema_edit_requires_manage_grant():
    """A grantee with EDIT (< MANAGE) is denied — class-C schema edits need MANAGE."""
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # < MANAGE
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=1)
    )
    ctx = _ctx(
        user_id=_USER, projects_repo=projects_repo, grant_client=grant,
        graph_schemas_repo=schemas,
    )
    res = await execute_tool(
        ctx, "kg_schema_edit", {"verb": "add", "level": "edge_type", "code": "X", "label": "X"},
    )
    assert not res.success
    assert "insufficient access" in res.error.lower()


# ── KM6-M2 — kg_adopt_template (class-C mint; NO write) ───────────────


@pytest.mark.asyncio
async def test_adopt_template_mints_confirm_token():
    import time as _time

    from app.config import settings
    from app.ontology.confirm import AUTH_GRANT, DESC_ADOPT, verify_action_token

    src = uuid4()
    schemas = AsyncMock()
    schemas.template_summary = AsyncMock(return_value={
        "schema_id": str(src), "code": "xianxia", "name": "Xianxia", "scope": "system",
        "edge_type_count": 7, "node_kind_count": 5, "fact_type_count": 3,
    })
    mutations = AsyncMock()
    ctx = _ctx(graph_schemas_repo=schemas, ontology_mutations_repo=mutations)  # caller==owner
    res = await execute_tool(ctx, "kg_adopt_template", {"source_schema_id": str(src)})
    assert res.success
    out = res.result
    assert out["proposed"] is True and out["descriptor"] == DESC_ADOPT
    assert "Xianxia" in out["summary"]
    mutations.adopt.assert_not_called()  # mint only — no write
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], _time.time())
    assert claims.authority == AUTH_GRANT and claims.user_id == str(ctx.user_id)
    assert claims.project_id == str(_PROJECT)
    assert claims.params["source_schema_id"] == str(src)


@pytest.mark.asyncio
async def test_adopt_template_rejects_invisible_or_missing_source():
    schemas = AsyncMock()
    schemas.template_summary = AsyncMock(return_value=None)  # not visible / missing
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(ctx, "kg_adopt_template", {"source_schema_id": str(uuid4())})
    assert not res.success
    assert "template" in res.error.lower()


@pytest.mark.asyncio
async def test_adopt_template_rejects_malformed_source_id():
    ctx = _ctx()
    res = await execute_tool(ctx, "kg_adopt_template", {"source_schema_id": "not-a-uuid"})
    assert not res.success
    assert "valid template id" in res.error.lower()


@pytest.mark.asyncio
async def test_adopt_template_requires_manage_grant():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # < MANAGE
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant)
    res = await execute_tool(ctx, "kg_adopt_template", {"source_schema_id": str(uuid4())})
    assert not res.success
    assert "insufficient access" in res.error.lower()


# ── KM6-M3 — kg_sync_apply (class-C mint; NO write) ───────────────────


@pytest.mark.asyncio
async def test_sync_apply_mints_confirm_token():
    import time as _time

    from app.config import settings
    from app.ontology.confirm import DESC_SYNC, verify_action_token

    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=4)
    )
    mutations = AsyncMock()
    ctx = _ctx(graph_schemas_repo=schemas, ontology_mutations_repo=mutations)
    res = await execute_tool(ctx, "kg_sync_apply", {
        "base_source_hash": "abc123",
        "decisions": [
            {"node_type": "edge_type", "code": "WORSHIPS", "choice": "take_theirs"},
            {"node_type": "fact_type", "code": "curse", "choice": "keep_mine"},
        ],
    })
    assert res.success
    out = res.result
    assert out["descriptor"] == DESC_SYNC and "1 take-theirs" in out["summary"]
    mutations.sync_apply.assert_not_called()  # mint only
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], _time.time())
    assert claims.params["base_source_hash"] == "abc123"
    assert len(claims.params["decisions"]) == 2
    assert claims.params["decisions"][0]["choice"] == "take_theirs"


@pytest.mark.asyncio
async def test_sync_apply_rejects_project_without_adopted_schema():
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(return_value=None)
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(ctx, "kg_sync_apply", {"base_source_hash": "h", "decisions": []})
    assert not res.success
    assert "adopt" in res.error.lower()


@pytest.mark.asyncio
async def test_sync_apply_rejects_bad_choice_at_the_model():
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=uuid4(), schema_version=1)
    )
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(ctx, "kg_sync_apply", {
        "base_source_hash": "h",
        "decisions": [{"node_type": "edge_type", "code": "X", "choice": "overwrite_all"}],
    })
    assert not res.success  # invalid choice → arg validation error


# ── E2 — kg_triage_place_edge (class-C mint; NO write) ────────────────


def _pending_proposed_edge_item(tid):
    from datetime import datetime, timezone

    from app.db.ontology_models import TriageItem

    return TriageItem(
        triage_id=tid, user_id=_OWNER, project_id=str(_PROJECT), source={},
        item_type="proposed_edge",
        payload={"source_entity_id": "a", "target_entity_id": "b", "predicate": "ALLIES"},
        signature="propose_edge:ALLIES:a->b", status="pending", resolution=None,
        schema_version=None, created_at=datetime.now(timezone.utc),
        resolved_at=None, resolved_by=None,
    )


@pytest.mark.asyncio
async def test_triage_place_edge_mints_confirm_token_and_does_not_write():
    """INV-K1 — the place_edge MCP tool MINTS a confirm-token bound to the proposer
    and the triage_id, and performs NO Neo4j write (the central path runs only at
    confirm, redeemed by the human's browser JWT)."""
    import time as _time

    from app.config import settings
    from app.ontology.confirm import (
        AUTH_GRANT,
        DESC_TRIAGE_PROPOSED_EDGE,
        verify_action_token,
    )

    tid = uuid4()
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=_pending_proposed_edge_item(tid))
    triage.resolve_item = AsyncMock()
    ctx = _ctx(triage_repo=triage)  # caller==owner
    res = await execute_tool(ctx, "kg_triage_place_edge", {"triage_id": str(tid)})
    assert res.success, res.error
    out = res.result
    assert out["proposed"] is True and out["descriptor"] == DESC_TRIAGE_PROPOSED_EDGE
    assert out["confirm_token"]
    # MINT-ONLY — the item is NOT resolved + nothing written from the MCP path.
    triage.resolve_item.assert_not_called()
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], _time.time())
    assert claims.authority == AUTH_GRANT
    assert claims.user_id == str(ctx.user_id)
    assert claims.params["triage_id"] == str(tid)


@pytest.mark.asyncio
async def test_triage_place_edge_rejects_non_pending_or_wrong_type():
    tid = uuid4()
    triage = AsyncMock()
    triage.get_item = AsyncMock(return_value=None)  # gone / not visible
    ctx = _ctx(triage_repo=triage)
    res = await execute_tool(ctx, "kg_triage_place_edge", {"triage_id": str(tid)})
    assert not res.success
    assert "no pending proposed edge" in res.error.lower()


# ── E3 — kg_triage_schema_write (class-C mint; NO write) ──────────────


@pytest.mark.asyncio
async def test_triage_schema_write_mints_confirm_token_and_does_not_write():
    """INV-T3 — the schema-write MCP tool MINTS a confirm-token bound to the proposer
    + the live schema_id/version, and performs NO mutation (Manage-gated)."""
    import time as _time

    from app.config import settings
    from app.ontology.confirm import (
        AUTH_GRANT,
        DESC_TRIAGE_SCHEMA_WRITE,
        verify_action_token,
    )

    sid = uuid4()
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(
        return_value=SimpleNamespace(schema_id=sid, schema_version=4)
    )
    mutations = AsyncMock()
    ctx = _ctx(graph_schemas_repo=schemas, ontology_mutations_repo=mutations)  # caller==owner
    res = await execute_tool(ctx, "kg_triage_schema_write", {
        "signature": "drive:curiosity", "action": "add_to_vocab",
        "code": "curiosity", "set_code": "drive",
    })
    assert res.success, res.error
    out = res.result
    assert out["proposed"] is True and out["descriptor"] == DESC_TRIAGE_SCHEMA_WRITE
    # MINT-ONLY — no schema mutation from the MCP path.
    mutations.add_vocab_value.assert_not_called()
    mutations.set_edge_cardinality.assert_not_called()
    claims = verify_action_token(settings.jwt_secret, out["confirm_token"], _time.time())
    assert claims.authority == AUTH_GRANT
    assert claims.user_id == str(ctx.user_id)
    assert claims.params["action"] == "add_to_vocab"
    assert claims.params["schema_id"] == str(sid)
    assert claims.params["expected_schema_version"] == 4


@pytest.mark.asyncio
async def test_triage_schema_write_requires_manage():
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # < MANAGE
    projects_repo = AsyncMock()
    projects_repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))
    ctx = _ctx(user_id=_USER, projects_repo=projects_repo, grant_client=grant)
    res = await execute_tool(ctx, "kg_triage_schema_write", {
        "signature": "s", "action": "set_multi_active", "code": "X",
    })
    assert not res.success
    assert "insufficient access" in res.error.lower()


@pytest.mark.asyncio
async def test_triage_schema_write_requires_adopted_schema():
    schemas = AsyncMock()
    schemas.active_project_schema = AsyncMock(return_value=None)
    ctx = _ctx(graph_schemas_repo=schemas)
    res = await execute_tool(ctx, "kg_triage_schema_write", {
        "signature": "s", "action": "add_to_schema", "code": "WORSHIPS",
    })
    assert not res.success
    assert "adopt" in res.error.lower()


# ── Track B B1(1): kg_world_query (world-rollup MCP tool) ─────────────


@pytest.mark.asyncio
async def test_kg_world_query_unions_partitions_and_reports_unreadable(monkeypatch):
    """EC-B2: union the caller's OWN world partitions (world-level + owned member
    books) AND report how many member partitions were owner-skipped, never dropping
    them silently."""
    import app.tools.graph_schema_tools as gst

    owned_book, other_book = uuid4(), uuid4()
    world_proj, owned_proj, other_proj = uuid4(), uuid4(), uuid4()
    other_owner = uuid4()

    book = AsyncMock()
    book.list_world_books = AsyncMock(
        return_value=[{"book_id": str(owned_book)}, {"book_id": str(other_book)}]
    )
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))
    repo.list = AsyncMock(return_value=[SimpleNamespace(project_id=world_proj)])

    async def _get_by_book(bid):
        if bid == owned_book:
            return SimpleNamespace(project_id=owned_proj, user_id=_OWNER)
        return SimpleNamespace(project_id=other_proj, user_id=other_owner)

    repo.get_by_book = AsyncMock(side_effect=_get_by_book)

    seen = {}

    async def _fake_subgraph(session, *, user_id, project_ids, limit):
        seen["project_ids"] = list(project_ids)
        return SimpleNamespace(
            model_dump=lambda mode="json": {"nodes": [{"id": "n1"}], "edges": []}
        )

    monkeypatch.setattr("app.db.neo4j_repos.relations.get_world_subgraph", _fake_subgraph)

    class _CM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(gst, "neo4j_session", lambda: _CM())

    ctx = _ctx(user_id=_OWNER, projects_repo=repo, book_client=book)
    res = await execute_tool(ctx, "kg_world_query", {"world_id": str(uuid4()), "limit": 50})

    assert res.success, res.error
    out = res.result
    assert out["partitions_read"] == 2          # world-level + the owned member book
    assert out["partitions_unreadable"] == 1     # the member book owned by someone else
    assert str(world_proj) in seen["project_ids"]
    assert str(owned_proj) in seen["project_ids"]
    assert str(other_proj) not in seen["project_ids"]   # never leak a partition we don't own
    assert "skipped" in out["note"].lower()


@pytest.mark.asyncio
async def test_kg_world_query_unknown_world_is_self_correcting_error():
    """EC-B5: a bad world / book-service issue maps to a tool-error STRING (not a 500),
    so a weak model can self-correct."""
    from app.clients.book_client import WorldNotFound

    book = AsyncMock()
    book.list_world_books = AsyncMock(side_effect=WorldNotFound("nope"))
    ctx = _ctx(user_id=_OWNER, book_client=book)
    res = await execute_tool(ctx, "kg_world_query", {"world_id": str(uuid4())})

    assert not res.success
    assert "world" in res.error.lower()


@pytest.mark.asyncio
async def test_kg_world_query_no_readable_partitions_returns_empty_not_error(monkeypatch):
    """A world with no partitions you own returns an empty-but-honest result (with the
    unreadable count) rather than an error — an empty world is valid."""
    other_book = uuid4()
    book = AsyncMock()
    book.list_world_books = AsyncMock(return_value=[{"book_id": str(other_book)}])
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))
    repo.list = AsyncMock(return_value=[])   # no world-level project
    repo.get_by_book = AsyncMock(
        return_value=SimpleNamespace(project_id=uuid4(), user_id=uuid4())  # owned by another
    )
    ctx = _ctx(user_id=_OWNER, projects_repo=repo, book_client=book)
    res = await execute_tool(ctx, "kg_world_query", {"world_id": str(uuid4())})

    assert res.success
    assert res.result["partitions_read"] == 0
    assert res.result["partitions_unreadable"] == 1
    assert res.result["nodes"] == []


# ── Track B B1(3): kg_multi_query (arbitrary owner-owned project set) ─────


def _multi_repo(owned: set):
    """A projects_repo whose .get returns a Project only for an id in ``owned``
    (owner-keyed), None otherwise — the ownership signal kg_multi_query reports on."""
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))

    async def _get(user_id, project_id):
        return SimpleNamespace(project_id=project_id) if project_id in owned else None

    repo.get = AsyncMock(side_effect=_get)
    return repo


def _patch_subgraph(monkeypatch, seen: dict):
    import app.tools.graph_schema_tools as gst

    async def _fake_subgraph(session, *, user_id, project_ids, limit):
        seen["project_ids"] = list(project_ids)
        seen["limit"] = limit
        return SimpleNamespace(
            model_dump=lambda mode="json": {"nodes": [{"id": "n1"}], "edges": []}
        )

    monkeypatch.setattr("app.db.neo4j_repos.relations.get_world_subgraph", _fake_subgraph)

    class _CM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(gst, "neo4j_session", lambda: _CM())


@pytest.mark.asyncio
async def test_kg_multi_query_unions_owned_and_reports_unreadable(monkeypatch):
    """B1(3)/EC-B2: union ONLY the projects the caller owns from the requested set, and
    report how many requested ids were skipped (foreign or stale) — never silently."""
    owned_a, owned_b, foreign = uuid4(), uuid4(), uuid4()
    repo = _multi_repo({owned_a, owned_b})
    seen: dict = {}
    _patch_subgraph(monkeypatch, seen)

    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_multi_query",
        {"project_ids": [str(owned_a), str(foreign), str(owned_b)], "limit": 50},
    )

    assert res.success, res.error
    out = res.result
    assert out["partitions_read"] == 2
    assert out["partitions_unreadable"] == 1
    assert set(seen["project_ids"]) == {str(owned_a), str(owned_b)}
    assert str(foreign) not in seen["project_ids"]   # never leak an unowned partition
    assert seen["limit"] == 50
    assert "skipped" in out["note"].lower()


@pytest.mark.asyncio
async def test_kg_multi_query_dedups_requested_ids(monkeypatch):
    """A duplicate id must not double-count coverage nor be queried twice."""
    owned_a, owned_b = uuid4(), uuid4()
    repo = _multi_repo({owned_a, owned_b})
    seen: dict = {}
    _patch_subgraph(monkeypatch, seen)

    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_multi_query",
        {"project_ids": [str(owned_a), str(owned_a), str(owned_b)]},
    )
    assert res.success, res.error
    assert res.result["partitions_read"] == 2
    assert res.result["partitions_unreadable"] == 0
    assert sorted(seen["project_ids"]) == sorted({str(owned_a), str(owned_b)})
    assert "note" not in res.result  # fully-readable → no partial-coverage note


@pytest.mark.asyncio
async def test_kg_multi_query_all_unreadable_returns_empty_not_error(monkeypatch):
    """Naming only ids you don't own returns an empty-but-honest result (with the
    unreadable count), not an error — a self-correctable state, not a failure."""
    foreign = uuid4()
    repo = _multi_repo(set())   # owns nothing requested
    seen: dict = {}
    _patch_subgraph(monkeypatch, seen)

    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(ctx, "kg_multi_query", {"project_ids": [str(foreign)]})

    assert res.success
    assert res.result["partitions_read"] == 0
    assert res.result["partitions_unreadable"] == 1
    assert res.result["nodes"] == []
    assert "project_ids" not in seen   # subgraph never queried when nothing readable


@pytest.mark.asyncio
async def test_kg_multi_query_invalid_id_is_self_correcting_error():
    """EC-B5-style: a non-UUID id maps to a tool-error STRING (not a 500) so a weak
    model can self-correct."""
    repo = _multi_repo(set())
    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(ctx, "kg_multi_query", {"project_ids": ["not-a-uuid"]})
    assert not res.success
    assert "valid id" in res.error.lower()


def test_kg_multi_query_args_require_at_least_one_and_cap_at_16():
    """The set must be non-empty (min_length=1) and capped at 16 (matches the B1(2)
    chat-session multi-KG grounding cap)."""
    assert KgMultiQueryArgs(project_ids=["p1"]).limit == 200
    with pytest.raises(ValidationError):
        KgMultiQueryArgs(project_ids=[])            # min_length=1
    with pytest.raises(ValidationError):
        KgMultiQueryArgs(project_ids=[f"p{i}" for i in range(17)])  # max_length=16
    with pytest.raises(ValidationError):
        KgMultiQueryArgs(project_ids=["p1"], user_id="smuggled")    # identity forbidden


def test_kg_multi_query_advertises_project_ids_bounds():
    """/review-impl #1 — the 1..16 bound must be in the MACHINE-READABLE schema (so a
    model sees it up front), not only in the prose + the model-layer ValidationError."""
    prop = _defn("kg_multi_query")["function"]["parameters"]["properties"]["project_ids"]
    assert prop["type"] == "array"
    assert prop["minItems"] == 1
    assert prop["maxItems"] == 16


# ── Track B B1(4): cross-partition unification (`unify` enum + wiring) ────


def test_unify_enum_matches_model_literal_on_both_tools():
    """B1(4)/EC-M6 — the machine-readable `unify` enum on kg_world_query AND
    kg_multi_query equals the arg-model Literal value-set (enum-locked for weak
    models; drift-locked). T0+T1: ['off','by_name','semantic']."""
    from app.tools.graph_schema_tools import _UNIFY_MODES

    for name in ("kg_world_query", "kg_multi_query"):
        prop = _defn(name)["function"]["parameters"]["properties"]["unify"]
        assert prop["type"] == "string"
        assert prop["enum"] == list(_UNIFY_MODES) == ["off", "by_name", "semantic"]
    assert KgMultiQueryArgs(project_ids=["p1"]).unify == "off"  # default
    assert KgWorldQueryArgs(world_id="w").unify == "off"
    assert KgMultiQueryArgs(project_ids=["p1"], unify="semantic").unify == "semantic"
    with pytest.raises(ValidationError):
        KgMultiQueryArgs(project_ids=["p1"], unify="fuzzy")  # not a valid mode
    with pytest.raises(ValidationError):
        KgWorldQueryArgs(world_id="w", unify="nonsense")


@pytest.mark.asyncio
async def test_kg_multi_query_default_off_omits_unify_keys_and_skips_unifier(monkeypatch):
    """EC-M5 — default unify='off' is byte-identical to the forest: no
    unification_clusters / bridge_edges keys, and the unifier is NEVER called."""
    import app.tools.kg_unify as ku

    owned_a, owned_b = uuid4(), uuid4()
    repo = _multi_repo({owned_a, owned_b})
    _patch_subgraph(monkeypatch, {})
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {}

    monkeypatch.setattr(ku, "unify_subgraph", _boom)

    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(
        ctx, "kg_multi_query", {"project_ids": [str(owned_a), str(owned_b)]}
    )
    assert res.success, res.error
    assert "unification_clusters" not in res.result
    assert "bridge_edges" not in res.result
    assert "disagreements" not in res.result
    assert called["n"] == 0  # off never touches the unifier


@pytest.mark.asyncio
async def test_kg_multi_query_unify_by_name_merges_unifier_result(monkeypatch):
    """B1(4) wiring proof — unify='by_name' calls the unifier and MERGES its additive
    keys into the result without clobbering the coverage keys."""
    import app.tools.kg_unify as ku

    owned_a, owned_b = uuid4(), uuid4()
    repo = _multi_repo({owned_a, owned_b})
    _patch_subgraph(monkeypatch, {})
    seen: dict = {}

    async def _fake_unify(session, *, user_id, subgraph, method, embedding_client=None):
        seen["method"] = method
        seen["has_embed_client"] = embedding_client is not None
        return {
            "unification_clusters": [{"cluster_id": "uc_x"}],
            "bridge_edges": [],
            "unify_method": method,
            "unify_capped": False,
        }

    monkeypatch.setattr(ku, "unify_subgraph", _fake_unify)

    ctx = _ctx(user_id=_OWNER, projects_repo=repo)
    res = await execute_tool(
        ctx,
        "kg_multi_query",
        {"project_ids": [str(owned_a), str(owned_b)], "unify": "by_name"},
    )
    assert res.success, res.error
    assert seen["method"] == "by_name"
    assert seen["has_embed_client"] is True  # embedding_client threaded for Q1=b/semantic
    assert res.result["unification_clusters"] == [{"cluster_id": "uc_x"}]
    assert res.result["unify_method"] == "by_name"
    assert res.result["partitions_read"] == 2  # coverage keys survive the merge


@pytest.mark.asyncio
async def test_kg_world_query_unify_by_name_wired(monkeypatch):
    """B1(4) — the same unification wiring is present on kg_world_query."""
    import app.tools.kg_unify as ku
    import app.world_rollup as wr

    async def _fake_resolve(*, world_id, user_id, repo, book):
        return SimpleNamespace(project_ids=[str(uuid4()), str(uuid4())], unreadable_count=0)

    monkeypatch.setattr(wr, "resolve_world_partitions", _fake_resolve)
    _patch_subgraph(monkeypatch, {})

    seen: dict = {}

    async def _fake_unify(session, *, user_id, subgraph, method, embedding_client=None):
        seen["method"] = method
        return {"unification_clusters": [], "bridge_edges": [],
                "unify_method": method, "unify_capped": False}

    monkeypatch.setattr(ku, "unify_subgraph", _fake_unify)

    ctx = _ctx(user_id=_OWNER, book_client=AsyncMock())
    res = await execute_tool(
        ctx, "kg_world_query", {"world_id": str(uuid4()), "unify": "by_name"}
    )
    assert res.success, res.error
    assert seen["method"] == "by_name"
    assert res.result["unify_method"] == "by_name"


# ── W10-M1 kg_create_node (manual single-node create) ────────────────────────
@pytest.mark.asyncio
async def test_kg_create_node_creates_and_returns_endpoint_id(monkeypatch):
    ctx = _ctx()  # caller == owner

    @asynccontextmanager
    async def _fake_session(**_):
        yield object()

    monkeypatch.setattr("app.tools.graph_schema_tools.neo4j_session", _fake_session)
    me = AsyncMock(return_value=SimpleNamespace(id="kg-sha", name="Kai", kind="character"))
    monkeypatch.setattr("app.db.neo4j_repos.entities.merge_entity", me)

    res = await execute_tool(ctx, "kg_create_node", {"name": "  Kai  ", "kind": "character"})
    assert res.success
    assert res.result["entity_id"] == "kg-sha"
    _, kwargs = me.call_args
    assert kwargs["name"] == "Kai"                 # trimmed
    assert kwargs["kind"] == "character"
    assert kwargs["source_type"] == "manual"
    assert kwargs["user_id"] == str(_OWNER)        # ran as the OWNER


@pytest.mark.asyncio
async def test_kg_create_node_non_grantee_anti_oracle():
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.NONE)
    ctx = _ctx(user_id=uuid4(), projects_repo=repo, grant_client=grant)
    res = await execute_tool(ctx, "kg_create_node", {"name": "X", "kind": "character"})
    assert not res.success
    assert "project not found" in res.error.lower()  # no existence oracle


@pytest.mark.asyncio
async def test_kg_create_node_resolves_to_owner_not_caller(monkeypatch):
    reader = uuid4()
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(_OWNER, _BOOK))  # owner != caller
    grant = AsyncMock()
    grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)  # grantee can write
    ctx = _ctx(user_id=reader, projects_repo=repo, grant_client=grant)

    @asynccontextmanager
    async def _fake_session(**_):
        yield object()

    monkeypatch.setattr("app.tools.graph_schema_tools.neo4j_session", _fake_session)
    me = AsyncMock(return_value=SimpleNamespace(id="kg-1", name="Kai", kind="character"))
    monkeypatch.setattr("app.db.neo4j_repos.entities.merge_entity", me)

    res = await execute_tool(ctx, "kg_create_node", {"name": "Kai", "kind": "character"})
    assert res.success
    _, kwargs = me.call_args
    assert kwargs["user_id"] == str(_OWNER)  # the write ran as OWNER, never the grantee


@pytest.mark.asyncio
async def test_kg_create_node_rejects_free_string_kind():
    # S7-1 (INV-parity): the agent free-string kind path is now gated to the
    # same closed set the human REST create accepts. A bogus kind must fail
    # validation BEFORE any write (no silent free-string mint).
    ctx = _ctx()  # caller == owner
    res = await execute_tool(ctx, "kg_create_node", {"name": "X", "kind": "gadget"})
    assert not res.success
    assert "kind must be one of" in res.error.lower()


@pytest.mark.asyncio
async def test_kg_create_node_rejects_legacy_faction_kind():
    # ``faction`` is the retired misnomer — the agent must not be able to mint
    # it either (create == agent). ``organization`` is the canonical group kind.
    ctx = _ctx()
    res = await execute_tool(ctx, "kg_create_node", {"name": "The Guild", "kind": "faction"})
    assert not res.success
    assert "kind must be one of" in res.error.lower()
