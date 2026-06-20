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

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.tools.definitions import ARG_MODELS, TOOL_DEFINITIONS, TOOL_NAMES
from app.tools.executor import ToolContext, execute_tool
from app.tools.graph_schema_tools import (
    GRAPH_SCHEMA_ARG_MODELS,
    GRAPH_SCHEMA_TOOL_DEFINITIONS,
    KgGraphQueryArgs,
    KgProposeEdgeArgs,
    KgTriageResolveArgs,
)

try:
    from loreweave_grants import GrantLevel
except ModuleNotFoundError:  # pragma: no cover - SDK on path in CI
    GrantLevel = None  # type: ignore

_USER = uuid4()
_OWNER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()

_ENVELOPE_KEYS = {"user_id", "project_id", "session_id"}

# The 12 tools this lane builds (R + reversible W).
_LANE_LF_TOOLS = {
    "kg_graph_query",
    "kg_entity_edge_timeline",
    "kg_schema_read",
    "kg_list_templates",
    "kg_sync_available",
    "kg_view_read",
    "kg_triage_list",
    "kg_propose_fact",
    "kg_propose_edge",
    "kg_view_upsert",
    "kg_view_delete",
    "kg_triage_resolve",
}

# The class-C tools deferred to KM6 — they must NOT be registered anywhere.
_CLASS_C_TOOLS = {
    "kg_adopt_template",
    "kg_schema_edit",
    "kg_sync_apply",
    "kg_triage_handoff_glossary",
    "kg_admin_template_read",
    "kg_admin_propose_template",
}


def _defn(name: str) -> dict:
    return next(d for d in TOOL_DEFINITIONS if d["function"]["name"] == name)


# ── registry consistency ──────────────────────────────────────────────


def test_total_tool_count_is_memory_plus_lane_lf():
    """5 memory tools + 12 lane-LF tools = 17, with all three artifacts agreeing."""
    schema_names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert len(TOOL_DEFINITIONS) == 17
    assert set(TOOL_NAMES) == set(ARG_MODELS) == schema_names
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)  # no dupes


def test_lane_lf_tools_all_registered():
    assert _LANE_LF_TOOLS.issubset(set(GRAPH_SCHEMA_ARG_MODELS))
    assert _LANE_LF_TOOLS == set(GRAPH_SCHEMA_ARG_MODELS)
    schema_names = {d["function"]["name"] for d in GRAPH_SCHEMA_TOOL_DEFINITIONS}
    assert schema_names == _LANE_LF_TOOLS


def test_class_c_tools_are_not_registered():
    """INV-T3 / D-KG-LF-KM6 — the confirm-token tools must be absent from the
    catalog until the KM6 confirm machinery lands. An LLM must not be able to
    name (let alone call) them."""
    all_names = set(TOOL_NAMES)
    leaked = _CLASS_C_TOOLS & all_names
    assert not leaked, f"class-C tools leaked into the catalog: {leaked}"


# ── OpenAI schema well-formedness + drift lock ────────────────────────


@pytest.mark.parametrize("name", sorted(_LANE_LF_TOOLS))
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


@pytest.mark.parametrize("name", sorted(_LANE_LF_TOOLS))
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
    """Design D3 / INV-K2 — user_id / project_id / session_id are envelope
    fields, never tool parameters."""
    for name in _LANE_LF_TOOLS:
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


def test_arg_models_reject_smuggled_scope_override():
    """extra='forbid' — a hallucinated project_id is a tool error, not a
    silent scope override."""
    with pytest.raises(ValidationError):
        KgGraphQueryArgs(project_id="x")
    with pytest.raises(ValidationError):
        KgProposeEdgeArgs(
            source_entity_id="a", target_entity_id="b", edge_type="loves",
            user_id="smuggled",
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
    never opens a Neo4j session / write."""
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
