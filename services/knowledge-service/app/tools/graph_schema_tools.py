"""Lane LF (KM1/KM2 + R-class of KM3/KM4) — KG ontology MCP tool surface.

This module adds the **knowledge-graph ontology** agentic tools to the
existing memory-tool surface (`app/tools/definitions.py` + `executor.py`),
exposed via the same `/mcp` server (`app/mcp/server.py`) and federated
through ai-gateway. It is registered the same way the 5 memory tools are:
an `ARG_MODELS` entry + a `TOOL_DEFINITIONS` schema + an executor handler.

Scope (spec `docs/specs/2026-06-20-knowledge-assistant-mcp-tools.md` §3, §8):
this lane builds the **safe tiers only** —

  * **R (read)** — `kg_graph_query`, `kg_entity_edge_timeline`,
    `kg_schema_read`, `kg_list_templates`, `kg_sync_available`,
    `kg_view_read`, `kg_triage_list`.
  * **W (low-impact, reversible, owner/grant-gated)** — `kg_propose_fact`
    (pending-facts inbox), `kg_propose_edge` (schema-validated, temporal-
    required, parked to the triage inbox — NEVER a direct Neo4j write,
    INV-K1), `kg_view_upsert` / `kg_view_delete` (owner==caller),
    `kg_triage_resolve` for **KG-LOCAL actions only**
    (map / re_target / drop_edge / close_previous / dismiss).

The **class-C** tools (kg_adopt_template, kg_schema_edit, kg_sync_apply,
schema-mutating / handoff triage actions, any System/admin) are
**deferred to KM6** (the confirm-token machinery) — shipping them here
would let an LLM mutate graph shape / adopt without the human-confirm
backstop (violates INV-T3). They are listed as one-line deferral comments
in the registry below.

ENVELOPE / IDENTITY (INV-K2, design D3): `user_id` / `project_id` /
`session_id` come from the MCP context headers (`X-User-Id` etc.), NEVER
from the LLM-supplied tool args — exactly like the memory tools. Every arg
model is `extra="forbid"`, so a hallucinated `project_id` is surfaced as a
tool error, never a scope override.

TENANCY (INV-T5): project tools grant-gate the project through the SAME
resolve-to-owner path the HTTP routers use (`GrantClient.resolve_grant`,
resolve-to-owner → the repo runs as the project OWNER); user-tier tools
(views) enforce `owner == caller`. Read tools reuse the K11.4-guarded read
paths (no raw Cypher minted here — the graph-read Cypher + pure builders are
imported verbatim from `app.routers.public.graph_views`).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from loreweave_mcp import apply_response_contract
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.tools.argbase import ProjectScopedArgs

from app.config import settings
from app.ontology.confirm import (
    ACTION_TOKEN_TTL_S,
    AUTH_GRANT,
    DESC_ADOPT,
    DESC_SCHEMA_EDIT,
    DESC_SYNC,
    DESC_TRIAGE_PROPOSED_EDGE,
    DESC_TRIAGE_SCHEMA_WRITE,
    ActionClaims,
    mint_action_token,
)
from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import run_read
from app.db.ontology_models import GraphView
from app.extraction.injection_defense import neutralize_injection
from app.ontology.validation import validate_edge
from app.routers.public.graph_views import (
    _GRAPH_READ_CYPHER,
    _TIMELINE_CYPHER,
    _deprecated_edge_codes,
    _records,
    _resolve_entity_project_grant,
    build_graph_slice,
    build_timeline,
)

if TYPE_CHECKING:  # avoid an import cycle (executor imports this module)
    from app.tools.executor import ToolContext

from loreweave_grants import GrantLevel

logger = logging.getLogger(__name__)

__all__ = [
    "GRAPH_SCHEMA_ARG_MODELS",
    "GRAPH_SCHEMA_TOOL_DEFINITIONS",
    "GRAPH_SCHEMA_HANDLERS",
    "KgGraphQueryArgs",
    "KgEntityEdgeTimelineArgs",
    "KgSchemaReadArgs",
    "KgListTemplatesArgs",
    "KgSyncAvailableArgs",
    "KgViewReadArgs",
    "KgTriageListArgs",
    "KgProposeFactArgs",
    "KgProposeEdgeArgs",
    "KgViewUpsertArgs",
    "KgViewDeleteArgs",
    "KgTriageResolveArgs",
    "KgSchemaEditArgs",
    "KgAdoptTemplateArgs",
    "KgSyncApplyArgs",
    "KgTriagePlaceEdgeArgs",
    "KgTriageSchemaWriteArgs",
]

# Result-size + addressing caps (mirror the HTTP routers' query bounds so the
# MCP surface is byte-for-byte as bounded as the bespoke routes — design D7).
GRAPH_LIMIT_MAX = 2000
GRAPH_LIMIT_DEFAULT = 500
TIMELINE_LIMIT_MAX = 2000
TIMELINE_LIMIT_DEFAULT = 500
TRIAGE_LIMIT_MAX = 500
TRIAGE_LIMIT_DEFAULT = 100
_CODE_MAX = 120  # SchemaCode/view code slug cap (ontology_models.SchemaCode)
_NAME_MAX = 200

# Fact-types accepted by the pending-facts inbox (mirrors db.models.FactType).
_PROPOSE_FACT_TYPES = ("decision", "preference", "milestone", "negation")

# B1(4) — cross-partition unification mode for the multi-KG read tools
# (kg_world_query / kg_multi_query). "off" (default) = today's forest,
# byte-identical (EC-M5). "by_name" = lexical unification (T0). "semantic" = the
# lexical⊕cosine blend with on-demand embedding of discovered entities (T1, Q1=b).
# Enum-locked (LLM-client-first).
_UNIFY_MODES = ("off", "by_name", "semantic")

# KG-LOCAL triage actions this lane resolves directly (Edit-gated, reversible).
# The schema-mutating + glossary-handoff actions are class-C (KM6) and rejected
# here with a clear tool error pointing the agent at the human-confirm surface.
_KG_LOCAL_TRIAGE_ACTIONS = ("map", "re_target", "drop_edge", "close_previous", "dismiss")

# Schema-mutating triage actions the kg_triage_schema_write tool mints for (E3).
_ACTIONS_SCHEMA_WRITE = (
    "add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active",
)

# ── L1/L2 reference-first ref-field sets (Context Budget Law §6b) ──────
# At detail="summary" `apply_response_contract` keeps ONLY these keys per node/edge
# and drops the heavier per-item fields (localized labels, glossary anchors, scores,
# schema_version, sample payloads). Full detail is unchanged. `detail` defaults to
# "full" (versioned migration). Exported for the per-tool contract-guard tests.
#
# kg_graph_query nodes/edges (GraphNode/GraphEdge — public.graph_views): keep the
# identity + relation triple; DROP the kind_label/name_label/edge_type_label +
# glossary_entity_id + schema_version.
GRAPH_NODE_REF_FIELDS = ("id", "kind", "name")
GRAPH_EDGE_REF_FIELDS = ("edge_type", "source_id", "target_id", "valid_from", "valid_to")
# kg_world_query / kg_multi_query nodes/edges (SubgraphNode/SubgraphEdge): keep
# identity + the source-book tag + the relation triple; DROP anchor_score/
# mention_count/glossary_entity_id (nodes) + confidence (edges).
SUBGRAPH_NODE_REF_FIELDS = ("id", "name", "kind", "source_project_id")
SUBGRAPH_EDGE_REF_FIELDS = ("id", "source", "target", "predicate")
# kg_entity_edge_timeline instances (TimelineInstance): keep the target + the
# temporal window; DROP evidence_chapter_id/schema_version/target_glossary_entity_id/
# target_label_localized.
TIMELINE_INSTANCE_REF_FIELDS = ("target_id", "target_label", "valid_from", "valid_to")
# kg_triage_list groups: keep the signature + type/count/status; DROP the heavy
# `sample_payload` blob + the `suggested_actions` list.
TRIAGE_GROUP_REF_FIELDS = ("signature", "item_type", "count", "status")


def _project_graph(out: dict, detail: str, *, node_ref, edge_ref) -> dict:
    """Apply the L1/L2 field projection to a graph result's `nodes` + `edges` lists
    in place and stamp coverage `meta`. The tool's own `limit` already bounds ROW
    counts (in the Cypher); `detail` is the per-item FIELD lever, so summary
    projects fields but never silently drops rows — meta reports both totals."""
    nodes_p, nmeta = apply_response_contract(
        out.get("nodes", []), ref_fields=node_ref, detail=detail,
    )
    edges_p, emeta = apply_response_contract(
        out.get("edges", []), ref_fields=edge_ref, detail=detail,
    )
    out["nodes"] = nodes_p
    out["edges"] = edges_p
    out["meta"] = {
        "detail": detail,
        "nodes_total": nmeta["total"],
        "nodes_returned": nmeta["returned"],
        "edges_total": emeta["total"],
        "edges_returned": emeta["returned"],
    }
    return out


# ── arg models (extra="forbid"; envelope keys are NEVER fields) ───────


class KgGraphQueryArgs(ProjectScopedArgs):
    """`kg_graph_query` — nodes+edges for a view, as-of a chapter."""

    view: str | None = Field(default=None, max_length=_CODE_MAX)
    as_of_chapter: int | None = Field(default=None, ge=0)
    limit: int = Field(default=GRAPH_LIMIT_DEFAULT, ge=1, le=GRAPH_LIMIT_MAX)
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class KgWorldQueryArgs(BaseModel):
    """`kg_world_query` — the rolled-up graph across ALL member-book KGs of a world.

    NOT ProjectScopedArgs: a world spans many projects, so it takes an EXPLICIT
    ``world_id`` (the ai-gateway MCP federation drops envelope scope — EC-B1). The
    rollup is owner-only (EC-B2)."""

    model_config = ConfigDict(extra="forbid")

    world_id: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=200, ge=1, le=GRAPH_LIMIT_MAX)
    unify: Literal["off", "by_name", "semantic"] = "off"
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class KgMultiQueryArgs(BaseModel):
    """`kg_multi_query` (Track B B1(3)) — the union graph across an ARBITRARY SET of the
    caller's own knowledge projects (NOT a world grouping): e.g. a canon KG + a fan-theory
    KG for ad-hoc comparison, or two unrelated books at once.

    NOT ProjectScopedArgs: the caller names the exact set via ``project_ids`` (the
    ai-gateway MCP federation drops envelope scope — same EC-B1 reason kg_world_query
    takes world_id explicitly). Owner-only (EC-B2): ids the caller doesn't own are skipped
    and reported, never dropped silently. Capped at 16 to match the chat-session multi-KG
    grounding cap (B1(2))."""

    model_config = ConfigDict(extra="forbid")

    project_ids: list[str] = Field(min_length=1, max_length=16)
    limit: int = Field(default=200, ge=1, le=GRAPH_LIMIT_MAX)
    unify: Literal["off", "by_name", "semantic"] = "off"
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class KgEntityEdgeTimelineArgs(BaseModel):
    """`kg_entity_edge_timeline` — the temporal instance chain for one
    entity + edge type (e.g. a drive arc).

    NOT ProjectScopedArgs: this tool scopes by the ENTITY (resolved to its own
    project + owner via _resolve_entity_project_grant), so a project_id arg would
    be a no-op. OD-8 is enforced by passing owner_only to that gate, not via the
    central project hoist."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1, max_length=200)
    edge_type: str = Field(min_length=1, max_length=_CODE_MAX)
    limit: int = Field(default=TIMELINE_LIMIT_DEFAULT, ge=1, le=TIMELINE_LIMIT_MAX)
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class KgSchemaReadArgs(ProjectScopedArgs):
    """`kg_schema_read` — the resolved (effective) project graph schema."""


class KgListTemplatesArgs(BaseModel):
    """`kg_list_templates` — system + the caller's user templates."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["system", "user"] | None = None


class KgSyncAvailableArgs(ProjectScopedArgs):
    """`kg_sync_available` — does the project schema have upstream updates?"""


class KgViewReadArgs(ProjectScopedArgs):
    """`kg_view_read` — list the caller's views in the project."""


class KgTriageListArgs(ProjectScopedArgs):
    """`kg_triage_list` — the triage queue grouped by signature."""

    status: Literal["pending", "pending_glossary", "resolved", "dismissed"] = "pending"
    limit: int = Field(default=TRIAGE_LIMIT_DEFAULT, ge=1, le=TRIAGE_LIMIT_MAX)
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class KgProposeFactArgs(ProjectScopedArgs):
    """`kg_propose_fact` — draft a narrative fact into the inbox (reviewed)."""

    model_config = ConfigDict(extra="forbid")

    fact_text: str = Field(min_length=1, max_length=2000)
    fact_type: Literal["decision", "preference", "milestone", "negation", "statement"]


class KgProposeEdgeArgs(ProjectScopedArgs):
    """`kg_propose_edge` — draft a relationship edge into the inbox.

    Schema-validated against `kg_edge_types`; a temporal edge type REQUIRES
    `valid_from` (a chapter ordinal) — rejected at mint if missing (spec
    §10.9). NEVER writes Neo4j: the proposal is parked to the triage inbox
    for human review (INV-K1)."""

    model_config = ConfigDict(extra="forbid")

    source_entity_id: str = Field(min_length=1, max_length=200)
    target_entity_id: str = Field(min_length=1, max_length=200)
    edge_type: str = Field(min_length=1, max_length=_CODE_MAX)
    source_kind: str | None = Field(default=None, max_length=_CODE_MAX)
    target_kind: str | None = Field(default=None, max_length=_CODE_MAX)
    valid_from: int | None = Field(default=None, ge=0)
    valid_to: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_temporal_window(self) -> "KgProposeEdgeArgs":
        # D-KG-LF-PROPOSE-VALIDTO — a closing ordinal before the opening ordinal
        # is a malformed temporal window; reject at mint (both are chapter
        # ordinals on the same axis). valid_to == valid_from is allowed (an edge
        # that opens and closes in the same chapter).
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError(
                f"valid_to ({self.valid_to}) must be >= valid_from "
                f"({self.valid_from}) — a closing ordinal cannot precede the opening one"
            )
        return self


class KgViewUpsertArgs(ProjectScopedArgs):
    """`kg_view_upsert` — create/replace one of the caller's views."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=_CODE_MAX)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str = Field(default="", max_length=2000)
    edge_type_codes: list[str] = Field(default_factory=list, max_length=200)
    node_kind_codes: list[str] = Field(default_factory=list, max_length=200)


class KgViewDeleteArgs(ProjectScopedArgs):
    """`kg_view_delete` — delete one of the caller's views by code."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=_CODE_MAX)


class KgTriageResolveArgs(ProjectScopedArgs):
    """`kg_triage_resolve` — resolve a triage signature with a KG-LOCAL action.

    Only the reversible KG-local actions are accepted here (Edit-gated). The
    schema-mutating (add_to_vocab/add_to_schema/widen/set_multi_active) and
    glossary-handoff (promote/demote) actions are class-C and require the KM6
    confirm machinery — this tool rejects them with a clear tool error."""

    model_config = ConfigDict(extra="forbid")

    signature: str = Field(min_length=1, max_length=500)
    action: Literal["map", "re_target", "drop_edge", "close_previous", "dismiss"]
    params: dict = Field(default_factory=dict)


class KgSchemaEditArgs(ProjectScopedArgs):
    """`kg_schema_edit` — class-C. Adds or deprecates a project edge_type/fact_type
    and bumps the schema_version. Mints a confirm-token (no write); a human confirms
    via the review surface (INV-K1: graph-shape changes are human-gated)."""

    model_config = ConfigDict(extra="forbid")

    verb: Literal["add", "deprecate"]
    level: Literal["edge_type", "fact_type"]
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    label: str = Field(default="", max_length=_NAME_MAX)


class KgAdoptTemplateArgs(ProjectScopedArgs):
    """`kg_adopt_template` — class-C. Copies a system/user ontology template down into
    the current project (scaffold). Mints a confirm-token (no write); a human confirms
    via the review surface. `source_schema_id` is a template id from `kg_list_templates`."""

    model_config = ConfigDict(extra="forbid")

    source_schema_id: str = Field(min_length=1, max_length=64)


class KgSyncDecision(BaseModel):
    """One per-child sync decision (from a `kg_sync_available` change)."""

    model_config = ConfigDict(extra="forbid")

    node_type: str = Field(min_length=1, max_length=40)
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    parent_code: str | None = Field(default=None, max_length=_CODE_MAX)
    choice: Literal["keep_mine", "take_theirs"]


class KgSyncApplyArgs(ProjectScopedArgs):
    """`kg_sync_apply` — class-C. Applies per-child keep_mine/take_theirs decisions to
    bring the project ontology in line with its upstream template. Mints a confirm-token
    (no write). `base_source_hash` is the upstream hash from `kg_sync_available`."""

    model_config = ConfigDict(extra="forbid")

    base_source_hash: str = Field(min_length=1, max_length=128)
    decisions: list[KgSyncDecision] = Field(default_factory=list)


class KgTriagePlaceEdgeArgs(ProjectScopedArgs):
    """`kg_triage_place_edge` — class-C. Places a drafted `proposed_edge` triage item
    into the graph. Mints a `kg_triage_proposed_edge` confirm-token (NO write — INV-K1);
    a human redeems it on the review surface. `triage_id` is from `kg_triage_list`."""

    model_config = ConfigDict(extra="forbid")

    triage_id: str = Field(min_length=1, max_length=64)


class KgTriageSchemaWriteArgs(ProjectScopedArgs):
    """`kg_triage_schema_write` — class-C. Resolves a schema-mutating triage signature
    (add a vocab value / edge type, widen an edge's target kinds, or make an edge type
    multi_active) by MINTING a `kg_triage_schema_write` confirm-token (NO write — INV-T3
    / Manage-gated). A human confirms on the review surface; the schema_version bumps."""

    model_config = ConfigDict(extra="forbid")

    signature: str = Field(min_length=1, max_length=500)
    action: Literal["add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active"]
    code: str = Field(default="", max_length=_CODE_MAX)
    label: str = Field(default="", max_length=_NAME_MAX)
    set_code: str = Field(default="", max_length=_CODE_MAX)
    add_kinds: list[str] = Field(default_factory=list, max_length=50)


class KgProjectEntitiesToNodesArgs(ProjectScopedArgs):
    """`kg_project_entities_to_nodes` — deterministically project a book's
    glossary entities into the graph as canonical `:Entity` nodes (WS-4B /
    scenario S04). Tier-A: idempotent (re-projection is a no-op) + reversible.
    Optional `entity_ids` limits it to a subset; omit to project the whole
    active glossary. This is the structured, prose-less path to seed the graph
    (no chapter extraction needed)."""

    model_config = ConfigDict(extra="forbid")

    entity_ids: list[str] | None = Field(default=None, max_length=1000)


class KgCreateNodeArgs(ProjectScopedArgs):
    """`kg_create_node` — manually create ONE knowledge-graph entity node (a
    character, place, faction, item, …). Tier-A: idempotent (the same name+kind
    upserts the existing node) + reversible. Use this BEFORE `kg_propose_edge` when a
    relationship's endpoint isn't in the graph yet — an edge whose endpoints aren't
    nodes is parked and later fails at confirm. Returns the node's entity_id to use
    as an edge endpoint."""

    name: str = Field(min_length=1, max_length=200, description="the entity's name")
    kind: str = Field(
        min_length=1, max_length=100,
        description="the entity kind, e.g. 'character', 'location', 'faction', 'item'",
    )


GRAPH_SCHEMA_ARG_MODELS: dict[str, type[BaseModel]] = {
    # ── R (read) ──────────────────────────────────────────────────────
    "kg_graph_query": KgGraphQueryArgs,
    "kg_world_query": KgWorldQueryArgs,
    "kg_multi_query": KgMultiQueryArgs,
    "kg_entity_edge_timeline": KgEntityEdgeTimelineArgs,
    "kg_schema_read": KgSchemaReadArgs,
    "kg_list_templates": KgListTemplatesArgs,
    "kg_sync_available": KgSyncAvailableArgs,
    "kg_view_read": KgViewReadArgs,
    "kg_triage_list": KgTriageListArgs,
    # ── W (low-impact, reversible, owner/grant-gated) ─────────────────
    "kg_propose_fact": KgProposeFactArgs,
    "kg_propose_edge": KgProposeEdgeArgs,
    "kg_project_entities_to_nodes": KgProjectEntitiesToNodesArgs,  # WS-4B: A, deterministic projection
    "kg_create_node": KgCreateNodeArgs,  # W10-M1: A, manual single-node create (unblocks kg_propose_edge)
    "kg_view_upsert": KgViewUpsertArgs,
    "kg_view_delete": KgViewDeleteArgs,
    "kg_triage_resolve": KgTriageResolveArgs,
    # ── C (confirm-token) — KM6 confirm machinery ─────────────────────
    "kg_schema_edit": KgSchemaEditArgs,    # KM6-M1: mints a confirm-token (no write)
    "kg_adopt_template": KgAdoptTemplateArgs,  # KM6-M2: mints a confirm-token (no write)
    "kg_sync_apply": KgSyncApplyArgs,      # KM6-M3: mints a confirm-token (no write)
    "kg_triage_place_edge": KgTriagePlaceEdgeArgs,  # E2: mints a confirm-token (no write)
    "kg_triage_schema_write": KgTriageSchemaWriteArgs,  # E3: mints a confirm-token (no write)
    # kg_triage_resolve (schema-mutating actions) # KM3/KM4 class-C — deferred to KM6 confirm machinery (D-KG-LF-KM6)
    # kg_triage_handoff_glossary # KM3/KM4 class-C — deferred to KM6 confirm machinery (D-KG-LF-KM6)
}


# ── OpenAI function-calling schemas ───────────────────────────────────


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Assemble one OpenAI `type=function` tool entry (mirrors
    `app.tools.definitions._tool`)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


# H-I: the optional project_id schema property shared by the project-scoped
# kg-READ tools (mirrors ProjectScopedArgs.project_id; drift-locked by
# test_no_envelope_keys_leak / test_mcp_inputschema_mirrors). Write/build kg tools
# stay envelope-only until their public exposure (P3/P4).
_PROJECT_ID_PROP = {
    "type": "string",
    "description": (
        "Optional knowledge project id to scope this call to. Omit to use the "
        "project linked to the current session. On the public API set it to one "
        "of YOUR projects — you can only address projects you own."
    ),
}

# L1/L2 reference-first `detail` enum (§6b) shared by the SET-returning kg-read
# tools. Enum-locked + versioned-default "full" (see definitions._DETAIL_PROP).
_DETAIL_PROP = {
    "type": "string",
    "enum": ["summary", "full"],
    "description": (
        "Response granularity. 'full' (default) = every field of each node/edge/"
        "item. 'summary' = a compact reference projection (ids + names + the "
        "relation triple; localized labels, glossary anchors, scores and heavy "
        "payloads dropped) — scan a large graph cheaply, then re-read specifics "
        "with a get-by-id sibling (e.g. memory_recall_entity / "
        "kg_entity_edge_timeline). `meta` reports the node/edge totals."
    ),
}

# B1(4) — the `unify` enum shared by kg_world_query + kg_multi_query. Enum-locked
# so a weak model picks a valid mode; the 1..16-style bound discipline of #1.
_UNIFY_PROP = {
    "type": "string",
    "enum": list(_UNIFY_MODES),
    "description": (
        "Cross-book entity unification. 'off' (default) returns the raw per-book "
        "forest unchanged. 'by_name' recognizes the SAME entity appearing across the "
        "different books by matching names/aliases; 'semantic' also matches by meaning "
        "(embedding similarity, catching renamed/aliased recurrences). Both add "
        "unification_clusters + SAME_AS bridge_edges so you get one connected "
        "cross-book graph. Bridges are inferred (confidence-scored), never asserted — "
        "cite the band."
    ),
}

GRAPH_SCHEMA_TOOL_DEFINITIONS: list[dict] = [
    _tool(
        "kg_graph_query",
        "Read the current project's knowledge graph as nodes + edges, "
        "optionally narrowed to a named view (lens) and to a point in the "
        "story via a chapter ordinal. Use this to see who relates to whom "
        "as of a given chapter. Returns nodes, edges, and any warnings.",
        {
            "view": {
                "type": "string",
                "description": (
                    "Optional view code (a saved lens of edge/node kinds). "
                    "Omit to read the whole graph."
                ),
            },
            "as_of_chapter": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Optional chapter ordinal — show the graph as it stood at "
                    "that chapter. Omit for the latest state."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": GRAPH_LIMIT_MAX,
                "description": f"Max edges to scan (default {GRAPH_LIMIT_DEFAULT}).",
            },
            "detail": _DETAIL_PROP,
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
    _tool(
        "kg_world_query",
        "Read the ROLLED-UP knowledge graph of an entire WORLD — the UNION of every "
        "member book's canon KG plus the world-level lore — as nodes + edges. Use this "
        "to synthesize ACROSS all books in a world (recurring entities, cross-book "
        "relationships) instead of one project at a time. Pass world_id explicitly. "
        "Owner-only: partitions owned by other users are skipped and counted in "
        "partitions_unreadable (the result also carries partitions_read).",
        {
            "world_id": {
                "type": "string",
                "description": "The id of the world to roll up (you must own it).",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": GRAPH_LIMIT_MAX,
                "description": "Max nodes in the union (default 200).",
            },
            "unify": _UNIFY_PROP,
            "detail": _DETAIL_PROP,
        },
        ["world_id"],
    ),
    _tool(
        "kg_multi_query",
        "Read the UNION knowledge graph across an ARBITRARY SET of YOUR knowledge "
        "projects (as nodes + edges) — e.g. compare a canon KG against a fan-theory KG, "
        "or load two unrelated books at once. Unlike kg_world_query (which rolls up one "
        "whole world), you name the exact project_ids. Owner-only: ids you don't own are "
        "skipped and counted in partitions_unreadable (the result also carries "
        "partitions_read). Nodes are tagged with their source_project_id.",
        {
            "project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 16,
                "description": "The project ids to union (1–16; you must own each).",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": GRAPH_LIMIT_MAX,
                "description": "Max nodes in the union (default 200).",
            },
            "unify": _UNIFY_PROP,
            "detail": _DETAIL_PROP,
        },
        ["project_ids"],
    ),
    _tool(
        "kg_entity_edge_timeline",
        "Retrieve the ordered temporal chain of one relationship type for a "
        "single entity (e.g. a character's drive arc: revenge → seek_dao → "
        "transcendence). Use an entity id and an edge-type code you have seen "
        "in an earlier graph result. Returns the full arc, including closed "
        "(superseded) instances.",
        {
            "entity_id": {
                "type": "string",
                "description": "The entity id (as seen in a graph result).",
            },
            "edge_type": {
                "type": "string",
                "description": "The relationship edge-type code to trace.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": TIMELINE_LIMIT_MAX,
                "description": f"Max instances (default {TIMELINE_LIMIT_DEFAULT}).",
            },
            "detail": _DETAIL_PROP,
        },
        ["entity_id", "edge_type"],
    ),
    _tool(
        "kg_schema_read",
        "Read the resolved (effective) graph schema for the current project — "
        "the edge types, fact types, controlled vocab, and expected node "
        "kinds. Use this to learn what relationship and fact codes are valid "
        "before proposing an edge or fact.",
        {"project_id": _PROJECT_ID_PROP},
        [],
    ),
    _tool(
        "kg_list_templates",
        "List the graph-schema templates available to adopt — the system "
        "(built-in) templates and the caller's own user templates. Use this "
        "to discover what ontologies a project could be based on.",
        {
            "scope": {
                "type": "string",
                "enum": ["system", "user"],
                "description": (
                    "Optional — restrict to 'system' or 'user' templates. Omit "
                    "for both."
                ),
            },
        },
        [],
    ),
    _tool(
        "kg_sync_available",
        "Check whether the current project's graph schema has upstream "
        "template updates available to pull (a tree-granular diff). Read-only: "
        "reports what changed; it does NOT apply anything.",
        {"project_id": _PROJECT_ID_PROP},
        [],
    ),
    _tool(
        "kg_view_read",
        "List the caller's saved views (named lenses of edge/node kinds) for "
        "the current project. Views are per-user — you only ever see your own.",
        {"project_id": _PROJECT_ID_PROP},
        [],
    ),
    _tool(
        "kg_triage_list",
        "List the project's triage queue — extracted graph elements that did "
        "not match the schema and are parked for human review — grouped by "
        "signature with a count and a suggested-action list. Use this to see "
        "what needs resolving.",
        {
            "status": {
                "type": "string",
                "enum": ["pending", "pending_glossary", "resolved", "dismissed"],
                "description": "Which queue to list (default 'pending').",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": TRIAGE_LIMIT_MAX,
                "description": f"Max signature groups (default {TRIAGE_LIMIT_DEFAULT}).",
            },
            "detail": _DETAIL_PROP,
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
    _tool(
        "kg_propose_fact",
        "Propose a narrative fact for the current project into the review "
        "inbox (a draft awaiting the user's confirmation — it does NOT enter "
        "the graph immediately). Use for durable, important facts the user "
        "stated or confirmed.",
        {
            "fact_text": {
                "type": "string",
                "description": "The fact to propose, as a clear statement.",
            },
            "fact_type": {
                "type": "string",
                "enum": list(_PROPOSE_FACT_TYPES),
                "description": (
                    "decision = a choice made; preference = a standing "
                    "like/dislike; milestone = a notable achievement; "
                    "negation = something explicitly NOT true."
                ),
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["fact_text", "fact_type"],
    ),
    _tool(
        "kg_propose_edge",
        "Propose a relationship edge between two entities for human review. "
        "The edge is validated against the project schema and parked in the "
        "triage inbox — it is NEVER written to the graph directly. If the "
        "edge type is temporal you MUST supply valid_from (the chapter "
        "ordinal it began); otherwise the proposal is rejected.",
        {
            "source_entity_id": {
                "type": "string",
                "description": "The id of the relationship's source entity.",
            },
            "target_entity_id": {
                "type": "string",
                "description": "The id of the relationship's target entity.",
            },
            "edge_type": {
                "type": "string",
                "description": "The relationship edge-type code (see kg_schema_read).",
            },
            "source_kind": {
                "type": "string",
                "description": "Optional — the source entity's node kind, for validation.",
            },
            "target_kind": {
                "type": "string",
                "description": "Optional — the target entity's node kind, for validation.",
            },
            "valid_from": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "The chapter ordinal the relationship began. REQUIRED for a "
                    "temporal edge type."
                ),
            },
            "valid_to": {
                "type": "integer",
                "minimum": 0,
                "description": "Optional — the chapter ordinal the relationship ended.",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["source_entity_id", "target_entity_id", "edge_type"],
    ),
    _tool(
        "kg_project_entities_to_nodes",
        "Project this book's recorded glossary entities into the knowledge "
        "graph as nodes — the structured way to seed the graph from lore you "
        "already entered, WITHOUT needing any chapter prose written. "
        "Deterministic and idempotent: re-running adds no duplicates. Returns "
        "how many nodes were newly created vs. already existed. Do this before "
        "proposing edges between entities (an edge needs both endpoints to be "
        "nodes first).",
        {
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional — the specific glossary entity ids to project. "
                    "Omit to project the book's whole active glossary."
                ),
            },
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
    _tool(
        "kg_create_node",
        "Manually create ONE knowledge-graph entity node (a character, place, "
        "faction, item, …). Use this BEFORE kg_propose_edge when a relationship's "
        "endpoint isn't in the graph yet — an edge whose endpoints aren't nodes is "
        "parked and later fails. Idempotent: the same name+kind returns the existing "
        "node. Returns the entity_id to use as an edge endpoint.",
        {
            "name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "description": "the entity's name",
            },
            "kind": {
                "type": "string",
                "minLength": 1,
                "maxLength": 100,
                "description": "the entity kind, e.g. 'character', 'location', 'faction', 'item'",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["name", "kind"],
    ),
    _tool(
        "kg_view_upsert",
        "Create or replace one of the caller's saved views (a named lens of "
        "edge-type + node-kind codes) for the current project. Owner-scoped: "
        "only ever touches your own view.",
        {
            "code": {
                "type": "string",
                "description": "The view's stable code (slug).",
            },
            "name": {
                "type": "string",
                "description": "A human-readable view name.",
            },
            "description": {
                "type": "string",
                "description": "Optional description.",
            },
            "edge_type_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Edge-type codes the view includes (empty = all).",
            },
            "node_kind_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Node-kind codes the view includes (empty = all).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["code", "name"],
    ),
    _tool(
        "kg_view_delete",
        "Delete one of the caller's saved views by code for the current "
        "project. Owner-scoped and reversible (recreate with kg_view_upsert).",
        {
            "code": {
                "type": "string",
                "description": "The code of the view to delete.",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["code"],
    ),
    _tool(
        "kg_triage_resolve",
        "Resolve a triage signature group with a low-impact, reversible "
        "action: map (alias to a known code), re_target (fix an endpoint), "
        "drop_edge (discard), close_previous (close an open instance), or "
        "dismiss. Schema-changing actions (add to vocab/schema, widen, "
        "promote to glossary) are NOT available here — those need explicit "
        "human confirmation via the review surface.",
        {
            "signature": {
                "type": "string",
                "description": "The triage signature to resolve (from kg_triage_list).",
            },
            "action": {
                "type": "string",
                "enum": list(_KG_LOCAL_TRIAGE_ACTIONS),
                "description": "The KG-local resolution action to apply.",
            },
            "params": {
                "type": "object",
                "description": "Optional action parameters (e.g. the map target code).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["signature", "action"],
    ),
    _tool(
        "kg_schema_edit",
        "Propose a change to THIS project's ontology: add or deprecate an edge "
        "type or fact type. This is high-impact (it changes the graph's shape and "
        "bumps the schema version), so it does NOT apply immediately — it returns a "
        "confirm_token and a summary; a human must confirm it on the review surface. "
        "Requires the project to have adopted its own ontology first.",
        {
            "verb": {
                "type": "string",
                "enum": ["add", "deprecate"],
                "description": "add a new type, or deprecate (soft-remove) an existing one.",
            },
            "level": {
                "type": "string",
                "enum": ["edge_type", "fact_type"],
                "description": "Which kind of ontology element to change.",
            },
            "code": {
                "type": "string",
                "maxLength": _CODE_MAX,
                "description": "The type's code (e.g. WORSHIPS, prophecy).",
            },
            "label": {
                "type": "string",
                "maxLength": _NAME_MAX,
                "description": "Human-readable label (for add; defaults to the code).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["verb", "level", "code"],
    ),
    _tool(
        "kg_adopt_template",
        "Propose adopting (copying down) a system or user ontology template into THIS "
        "project, scaffolding its edge types / node kinds / fact types. High-impact — it "
        "does NOT apply immediately; it returns a confirm_token and a summary, and a human "
        "confirms on the review surface. Pick a `source_schema_id` from kg_list_templates.",
        {
            "source_schema_id": {
                "type": "string",
                "description": "The template id to adopt (from kg_list_templates).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["source_schema_id"],
    ),
    _tool(
        "kg_sync_apply",
        "Propose syncing THIS project's ontology with its upstream template — applying "
        "per-change keep_mine / take_theirs decisions (read the diff with "
        "kg_sync_available first). High-impact (overwrites/deprecates rows + bumps the "
        "schema version), so it returns a confirm_token and summary; a human confirms on "
        "the review surface. Requires the project to have adopted a template.",
        {
            "base_source_hash": {
                "type": "string",
                "description": "The upstream hash returned by kg_sync_available (drift guard).",
            },
            "decisions": {
                "type": "array",
                "description": "Per-change decisions to apply.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "node_type": {"type": "string", "description": "edge_type | fact_type | node_kind | vocab_value."},
                        "code": {"type": "string", "description": "The child's code."},
                        "parent_code": {"type": "string", "description": "Parent code (vocab_value only)."},
                        "choice": {"type": "string", "enum": ["keep_mine", "take_theirs"]},
                    },
                    "required": ["node_type", "code", "choice"],
                },
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["base_source_hash"],
    ),
    _tool(
        "kg_triage_place_edge",
        "Place an agent-drafted proposed edge (from kg_triage_list, item_type "
        "'proposed_edge') into the knowledge graph. High-impact (it writes a real "
        "edge), so it does NOT apply immediately — it returns a confirm_token and a "
        "summary; a human confirms on the review surface. Pick a `triage_id` of a "
        "pending proposed_edge from kg_triage_list.",
        {
            "triage_id": {
                "type": "string",
                "description": "The proposed_edge triage item id to place (from kg_triage_list).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["triage_id"],
    ),
    _tool(
        "kg_triage_schema_write",
        "Resolve a schema-mutating triage signature group: add_to_vocab (add a "
        "controlled-vocab value), add_to_schema (add an edge type), "
        "widen_target_kinds (allow more target node kinds on an edge type), or "
        "set_multi_active (let an edge type hold multiple open instances). This "
        "changes the project ontology and bumps the schema version, so it does NOT "
        "apply immediately — it returns a confirm_token and a summary; a human "
        "confirms on the review surface.",
        {
            "signature": {
                "type": "string",
                "description": "The triage signature to resolve (from kg_triage_list).",
            },
            "action": {
                "type": "string",
                "enum": list(_ACTIONS_SCHEMA_WRITE),
                "description": "The schema-mutating resolution action to apply.",
            },
            "code": {
                "type": "string",
                "description": "The edge-type / vocab-value code being added or modified.",
            },
            "label": {
                "type": "string",
                "description": "Human-readable label (for add actions; defaults to the code).",
            },
            "set_code": {
                "type": "string",
                "description": "The vocab set code (add_to_vocab only).",
            },
            "add_kinds": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Target node kinds to add (widen_target_kinds only).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["signature", "action"],
    ),
]


# ── grant gate (mirror app.auth.grant_deps._resolve_owner, no FastAPI) ─


async def _resolve_project_owner(ctx: "ToolContext", need: GrantLevel) -> UUID:
    """Resolve the project OWNER the repo runs as, after grant-gating the
    caller — the executor-side equivalent of `require_project_grant`.

    Mirrors `app.auth.grant_deps._resolve_owner` exactly, but raises a
    ToolExecutionError (surfaced as a tool error) instead of an HTTPException:
      * no project in scope            → tool error
      * project not found / non-grantee → tool error (no existence oracle)
      * book-less project, not owner    → tool error (owner-only)
      * grantee under the required tier → tool error
    """
    from app.tools.executor import ToolExecutionError

    if ctx.project_id is None:
        raise ToolExecutionError(
            "no project in scope — pass the optional `project_id` argument "
            "(list your projects with kg_project_list), or open this chat from "
            "a project"
        )
    meta = await ctx.projects_repo.project_meta(ctx.project_id)
    if meta is None:
        raise ToolExecutionError("project not found")
    owner, book_id = meta
    if ctx.user_id == owner:
        return owner
    # OD-8: a public MCP-key call resolves to OWNED projects only — it must NOT
    # inherit the owner's E0 share-grants to other people's books (the agent's
    # principal never consented to a third-party agent reaching shared content).
    # Reject before consulting grants. First-party calls (mcp_key_id is None) keep
    # the grant-aware path below unchanged.
    if ctx.mcp_key_id is not None:
        raise ToolExecutionError("project not found")  # owned-only, no oracle
    if book_id is None:
        raise ToolExecutionError("project not found")  # book-less → owner-only
    lvl = await ctx.grant_client.resolve_grant(book_id, ctx.user_id)
    if lvl == GrantLevel.NONE:
        raise ToolExecutionError("project not found")  # non-grantee → no oracle
    if not lvl.at_least(need):
        raise ToolExecutionError("insufficient access for this action")
    return owner


async def _resolve_project_owner_and_level(
    ctx: "ToolContext", need: GrantLevel,
) -> tuple[UUID, GrantLevel]:
    """Like `_resolve_project_owner`, but ALSO returns the caller's effective grant level —
    needed to clamp paid reasoning effort (D-RE-OTHER-AGENTIC-EFFORT). The project OWNER (the
    caller IS the owner) gets `GrantLevel.OWNER`; a book collaborator gets their resolved grant.
    Same gating/anti-oracle as `_resolve_project_owner`."""
    from app.tools.executor import ToolExecutionError

    if ctx.project_id is None:
        raise ToolExecutionError(
            "no project in scope — pass the optional `project_id` argument "
            "(list your projects with kg_project_list), or open this chat from "
            "a project"
        )
    meta = await ctx.projects_repo.project_meta(ctx.project_id)
    if meta is None:
        raise ToolExecutionError("project not found")
    owner, book_id = meta
    if ctx.user_id == owner:
        return owner, GrantLevel.OWNER
    # OD-8: a public MCP-key call gets owned-only access — never grant-derived
    # (see _resolve_project_owner). First-party calls keep the grant path below.
    if ctx.mcp_key_id is not None:
        raise ToolExecutionError("project not found")  # owned-only, no oracle
    if book_id is None:
        raise ToolExecutionError("project not found")  # book-less → owner-only
    lvl = await ctx.grant_client.resolve_grant(book_id, ctx.user_id)
    if lvl == GrantLevel.NONE:
        raise ToolExecutionError("project not found")
    if not lvl.at_least(need):
        raise ToolExecutionError("insufficient access for this action")
    return owner, lvl


async def _active_project_schema_id(ctx: "ToolContext", project_id: str):
    """The project's active project-scoped schema_id (or None if it never
    adopted — then there is no upstream to sync against). Read-only.

    Mirrors the project-schema selection in
    `app.routers.public.graph_views._deprecated_edge_codes` (one active project
    schema, newest-wins tiebreak) — read straight off the schemas repo's pool
    so this lane adds no method to LC's mutations repo."""
    async with ctx.graph_schemas_repo._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT schema_id FROM kg_graph_schemas
            WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
            ORDER BY updated_at DESC, schema_id DESC LIMIT 1
            """,
            project_id,
        )
    return row["schema_id"] if row is not None else None


# ── handlers ──────────────────────────────────────────────────────────


async def _handle_kg_graph_query(ctx: "ToolContext", args: KgGraphQueryArgs) -> dict:
    owner = await _resolve_project_owner(ctx, GrantLevel.VIEW)
    project_str = str(ctx.project_id)

    selected_view: GraphView | None = None
    if args.view is not None:
        # Views are per-user — resolve the CALLER's lens over the owner's graph.
        selected_view = await ctx.graph_views_repo.get(ctx.user_id, project_str, args.view)
        if selected_view is None:
            from app.tools.executor import ToolExecutionError

            raise ToolExecutionError(f"view not found: {args.view!r}")

    async with neo4j_session() as session:
        result = await run_read(
            session,
            _GRAPH_READ_CYPHER,
            user_id=str(owner),
            project_id=project_str,
            limit=args.limit,
        )
        records = await _records(result)

    deprecated = await _deprecated_edge_codes(ctx.graph_schemas_repo, project_str)
    slice_ = build_graph_slice(
        records,
        view=selected_view,
        as_of_chapter=args.as_of_chapter,
        deprecated_edge_codes=deprecated,
        view_code=args.view,
    )
    out = slice_.model_dump(mode="json")
    # L1/L2 reference-first (§6b): project node/edge fields per `detail` (summary =
    # id/kind/name refs + relation triple; drop labels/glossary/schema_version).
    return _project_graph(
        out, args.detail,
        node_ref=GRAPH_NODE_REF_FIELDS, edge_ref=GRAPH_EDGE_REF_FIELDS,
    )


async def _handle_kg_world_query(ctx: "ToolContext", args: KgWorldQueryArgs) -> dict:
    """`kg_world_query` (Track B B1(1)) — UNION the canon KGs of every member book in a
    world (plus the world-level bible project) into one nodes+edges result the agent can
    synthesize over. Owner-only (EC-B2): partitions owned by other users are SKIPPED but
    REPORTED via ``partitions_unreadable`` — never dropped silently. EC-B5: a bad world /
    a book-service outage return a self-correcting error string, not a 500."""
    from app.clients.book_client import BookServiceUnavailable, WorldNotFound
    from app.db.neo4j_repos.relations import get_world_subgraph
    from app.tools.executor import ToolExecutionError
    from app.world_rollup import resolve_world_partitions

    if ctx.book_client is None:
        raise ToolExecutionError(
            "world rollup is unavailable here (book-service client not configured)"
        )
    try:
        world_uuid = UUID(args.world_id)
    except (ValueError, TypeError):
        raise ToolExecutionError(f"world_id is not a valid id: {args.world_id!r}")

    try:
        partitions = await resolve_world_partitions(
            world_id=world_uuid,
            user_id=ctx.user_id,
            repo=ctx.projects_repo,
            book=ctx.book_client,
        )
    except WorldNotFound:
        raise ToolExecutionError(f"no world with id {args.world_id} (or you don't own it)")
    except BookServiceUnavailable:
        raise ToolExecutionError(
            "world membership is temporarily unavailable — retry shortly"
        )

    read = len(partitions.project_ids)
    unreadable = partitions.unreadable_count
    if read == 0:
        # No readable partitions — return an empty-but-honest result (EC-B2 report),
        # not an error: an empty world (or one entirely of others' books) is valid.
        note = "this world has no KG partitions you can read"
        if unreadable:
            note += f" ({unreadable} are owned by another user)"
        return {
            "nodes": [],
            "edges": [],
            "partitions_read": 0,
            "partitions_unreadable": unreadable,
            "note": note + ".",
        }

    async with neo4j_session() as session:
        subgraph = await get_world_subgraph(
            session,
            user_id=str(ctx.user_id),
            project_ids=partitions.project_ids,
            limit=args.limit,
        )
        # B1(4) — cross-partition unification (opt-in; default-off byte-identical, EC-M5).
        unify_extra = None
        if args.unify != "off":
            from app.tools.kg_unify import unify_subgraph

            unify_extra = await unify_subgraph(
                session,
                user_id=str(ctx.user_id),
                subgraph=subgraph,
                method=args.unify,
                embedding_client=ctx.embedding_client,
            )
    out = subgraph.model_dump(mode="json")
    # EC-B2 — surface coverage so the agent knows the rollup is partial, not complete.
    out["partitions_read"] = read
    out["partitions_unreadable"] = unreadable
    if unreadable:
        out["note"] = (
            f"{unreadable} member partition(s) are owned by another user and were "
            "skipped (owner-only world rollup); this graph covers only your partitions."
        )
    if unify_extra is not None:
        out.update(unify_extra)
    # L1/L2 reference-first (§6b): project the union node/edge fields per `detail`
    # (summary = id/name/kind + source_project_id + relation triple). The inferred
    # SAME_AS `bridge_edges` (if unify ran) are a separate small set, left as-is.
    return _project_graph(
        out, args.detail,
        node_ref=SUBGRAPH_NODE_REF_FIELDS, edge_ref=SUBGRAPH_EDGE_REF_FIELDS,
    )


async def _handle_kg_multi_query(ctx: "ToolContext", args: KgMultiQueryArgs) -> dict:
    """`kg_multi_query` (Track B B1(3)) — UNION the canon KGs of an ARBITRARY SET of the
    caller's own projects (canon KG + fan-theory KG, two unrelated books, …) into one
    nodes+edges result. Owner-only (EC-B2): requested ids the caller doesn't own (or that
    don't exist) are SKIPPED but REPORTED via ``partitions_unreadable`` — never dropped
    silently. Reuses the same per-partition union as kg_world_query
    (``get_world_subgraph`` binds user_id + project_id per read, so an unowned id would
    contribute nothing anyway — the ownership resolve here makes the report accurate)."""
    from app.db.neo4j_repos.relations import get_world_subgraph
    from app.tools.executor import ToolExecutionError

    # Validate + order-preserving dedup (a duplicate id must not double-count coverage).
    seen: set[UUID] = set()
    requested: list[UUID] = []
    for raw in args.project_ids:
        try:
            u = UUID(raw)
        except (ValueError, TypeError):
            raise ToolExecutionError(f"project_id is not a valid id: {raw!r}")
        if u not in seen:
            seen.add(u)
            requested.append(u)

    # Owner-scope: keep only the projects this caller owns; the rest (foreign OR stale)
    # are the unreadable count. projects_repo.get is owner-keyed (user_id + project_id).
    readable: list[str] = []
    for u in requested:
        project = await ctx.projects_repo.get(ctx.user_id, u)
        if project is not None:
            readable.append(str(u))

    read = len(readable)
    unreadable = len(requested) - read
    if read == 0:
        # Nothing readable — empty-but-honest (EC-B2 report), not an error: naming ids
        # you no longer own is a routine self-correctable state, not a failure.
        note = "none of the requested projects are readable by you (not owned or don't exist)"
        return {
            "nodes": [],
            "edges": [],
            "partitions_read": 0,
            "partitions_unreadable": unreadable,
            "note": note + ".",
        }

    async with neo4j_session() as session:
        subgraph = await get_world_subgraph(
            session,
            user_id=str(ctx.user_id),
            project_ids=readable,
            limit=args.limit,
        )
        # B1(4) — cross-partition unification (opt-in; default-off byte-identical, EC-M5).
        unify_extra = None
        if args.unify != "off":
            from app.tools.kg_unify import unify_subgraph

            unify_extra = await unify_subgraph(
                session,
                user_id=str(ctx.user_id),
                subgraph=subgraph,
                method=args.unify,
                embedding_client=ctx.embedding_client,
            )
    out = subgraph.model_dump(mode="json")
    # EC-B2 — surface coverage so the agent knows the union is partial, not complete.
    out["partitions_read"] = read
    out["partitions_unreadable"] = unreadable
    if unreadable:
        out["note"] = (
            f"{unreadable} requested project(s) are not yours (or don't exist) and were "
            "skipped; this graph covers only your projects."
        )
    if unify_extra is not None:
        out.update(unify_extra)
    # L1/L2 reference-first (§6b): same union node/edge projection as kg_world_query.
    return _project_graph(
        out, args.detail,
        node_ref=SUBGRAPH_NODE_REF_FIELDS, edge_ref=SUBGRAPH_EDGE_REF_FIELDS,
    )


async def _handle_kg_entity_edge_timeline(
    ctx: "ToolContext", args: KgEntityEdgeTimelineArgs
) -> dict:
    # Grant-gate via the entity's project (caller-scoped entity read → the
    # universal K11.4 pattern; re-confirm a VIEW grant). Reuses the router
    # helper verbatim so the MCP path is byte-for-byte as scoped as the route.
    from fastapi import HTTPException

    from app.tools.executor import ToolExecutionError

    try:
        await _resolve_entity_project_grant(
            args.entity_id, ctx.user_id, ctx.grant_client, ctx.projects_repo,
            # OD-8: a public MCP-key call is owned-only (no grant-derived access).
            owner_only=ctx.mcp_key_id is not None,
        )
    except HTTPException as exc:
        # 404 (not found / no grant) + 403 (under tier) collapse to a tool
        # error — no existence oracle, uniform with the HTTP route.
        raise ToolExecutionError(str(exc.detail))

    async with neo4j_session() as session:
        result = await run_read(
            session,
            _TIMELINE_CYPHER,
            user_id=str(ctx.user_id),
            entity_id=args.entity_id,
            edge_type=args.edge_type,
            limit=args.limit,
        )
        records = await _records(result)
    out = build_timeline(args.entity_id, args.edge_type, records).model_dump(mode="json")
    # L1/L2 reference-first (§6b): at detail="summary" project each temporal
    # instance to target + window, dropping evidence_chapter_id/schema_version/
    # localized/glossary fields. `meta` reports the instance total/returned.
    instances, meta = apply_response_contract(
        out.get("instances", []),
        ref_fields=TIMELINE_INSTANCE_REF_FIELDS, detail=args.detail,
    )
    out["instances"] = instances
    out["meta"] = meta
    return out


async def _handle_kg_schema_read(ctx: "ToolContext", args: KgSchemaReadArgs) -> dict:
    # @small_return: ONE resolved schema document (the project's effective edge/fact
    # types + vocab) — a single object the agent reads whole before proposing an
    # edge/fact; there is no per-item body to project (spec §6b single-object exempt).
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    resolved = await ctx.ontology_resolver.resolve(str(ctx.project_id))
    return resolved.model_dump(mode="json")


async def _handle_kg_list_templates(ctx: "ToolContext", args: KgListTemplatesArgs) -> dict:
    # @small_return: each template is already a compact metadata ref (schema_id/scope/
    # code/name/description/version) — no heavy body — and the set is bounded by the
    # small count of system + the caller's own templates (spec §6b: not SET-bloat).
    # No project grant needed — system templates are visible to everyone and
    # user templates are scope-filtered to the caller by the repo (it filters
    # `scope='user' AND scope_id=$user`). Never lists another user's templates.
    schemas = await ctx.graph_schemas_repo.list_visible(ctx.user_id, scope=args.scope)
    items = [
        {
            "schema_id": str(s.schema_id),
            "scope": s.scope,
            "code": s.code,
            "name": s.name,
            "description": s.description,
            "schema_version": s.schema_version,
        }
        for s in schemas
    ]
    return {"templates": items, "count": len(items)}


async def _handle_kg_sync_available(ctx: "ToolContext", args: KgSyncAvailableArgs) -> dict:
    # @small_return: a single diff summary (adopted flag + a bounded per-child
    # changes list of code refs) — no heavy per-item body (spec §6b single-object).
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    schema_id = await _active_project_schema_id(ctx, str(ctx.project_id))
    if schema_id is None:
        # Project never adopted a template → nothing to sync against.
        return {"has_updates": False, "adopted": False, "changes": []}
    diff = await ctx.ontology_mutations_repo.sync_diff(schema_id)
    return {
        "adopted": True,
        "has_updates": bool(diff.get("has_updates")),
        "source_ref": diff.get("source_ref"),
        "changes": diff.get("changes", []),
    }


async def _handle_kg_view_read(ctx: "ToolContext", args: KgViewReadArgs) -> dict:
    # @small_return: the caller's own saved views (code/name/description + two short
    # code lists) — a small per-user set of compact refs, no heavy body (spec §6b).
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    views = await ctx.graph_views_repo.list(ctx.user_id, str(ctx.project_id))
    return {
        "views": [v.model_dump(mode="json") for v in views],
        "count": len(views),
    }


async def _handle_kg_triage_list(ctx: "ToolContext", args: KgTriageListArgs) -> dict:
    owner = await _resolve_project_owner(ctx, GrantLevel.VIEW)
    groups, has_more = await ctx.triage_repo.list_grouped(
        user_id=owner,
        project_id=str(ctx.project_id),
        status=args.status,
        limit=args.limit,
    )
    items = [
        {
            "signature": g.signature,
            "item_type": g.item_type,
            "count": g.count,
            "status": g.status,
            "sample_payload": g.sample_payload,
            "suggested_actions": g.suggested_actions,
        }
        for g in groups
    ]
    # L1/L2 reference-first (§6b): at detail="summary" drop the heavy
    # `sample_payload` blob + `suggested_actions`, keeping the signature +
    # type/count/status so the agent can scan the queue and re-read one group
    # (kg_triage_list at full detail) before resolving it.
    projected, meta = apply_response_contract(
        items, ref_fields=TRIAGE_GROUP_REF_FIELDS, detail=args.detail,
    )
    return {"groups": projected, "has_more": has_more, **meta}


async def _handle_kg_propose_fact(ctx: "ToolContext", args: KgProposeFactArgs) -> dict:
    # W (reversible) — queue a draft into the pending-facts inbox; the user
    # confirms before it lands in the graph. Edit-gated on the project.
    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    project_str = str(ctx.project_id)
    # Neutralize injection at queue time — the confirm endpoint writes the
    # queued text as-is, so the defense must run now, not at write time
    # (mirrors the memory_remember queue path).
    sanitized, _ = neutralize_injection(args.fact_text, project_id=project_str)
    pending = await ctx.pending_facts_repo.queue(
        owner,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        fact_type=args.fact_type,
        fact_text=sanitized,
    )
    return {
        "queued": True,
        "pending_fact_id": str(pending.pending_fact_id),
        "fact_text": pending.fact_text,
        "fact_type": pending.fact_type,
    }


async def _handle_kg_propose_edge(ctx: "ToolContext", args: KgProposeEdgeArgs) -> dict:
    # W (draft) — validate against the resolved schema, enforce temporal-
    # required at MINT, then park to the triage inbox. NEVER WRITES Neo4j
    # (INV-K1): the central write-path applies it only after human review.
    # WS-4B ADDS a read-only endpoint-existence PRECHECK (below) so an edge
    # whose endpoints aren't nodes yet is rejected UP FRONT (KG_ENDPOINT_NOT_NODE)
    # instead of parking then failing two steps later at confirm — this reads
    # Neo4j but never writes it, so the human-gated-write invariant is intact.
    from app.tools.executor import ToolExecutionError
    from app.db.neo4j_repos.entities import existing_entity_node_ids

    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    project_str = str(ctx.project_id)
    resolved = await ctx.ontology_resolver.resolve(project_str)

    # Temporal-required (spec §10.9) — a temporal edge type without valid_from
    # would create an unanchored edge; reject early at mint.
    edge_def = next((e for e in resolved.edge_types if e.code == args.edge_type), None)
    if edge_def is not None and edge_def.temporal and args.valid_from is None:
        raise ToolExecutionError(
            f"edge type '{args.edge_type}' is temporal — valid_from "
            "(the chapter ordinal it began) is required"
        )

    # Schema validation (fail-soft) → off-schema edges park with the validator's
    # taxonomy item_type/signature (unknown_edge_type / edge_kind_mismatch). A
    # well-formed on-schema edge parks as a `proposed_edge` draft — NOT a
    # cardinality conflict: the conflict is a stateful condition the tool can't
    # check (it never reads Neo4j, INV-K1), so labelling every clean proposal a
    # "conflict" overloaded the taxonomy (D-KG-LF-PROPOSE-EDGE-INBOX).
    issue = validate_edge(
        resolved,
        predicate=args.edge_type,
        source_kind=args.source_kind,
        target_kind=args.target_kind,
    )
    payload = {
        "source_entity_id": args.source_entity_id,
        "target_entity_id": args.target_entity_id,
        "predicate": args.edge_type,
        "source_kind": args.source_kind,
        "target_kind": args.target_kind,
        "valid_from": args.valid_from,
        "valid_to": args.valid_to,
        "proposed_by": "llm_tool_call",
    }
    if issue is not None:
        item_type = issue.item_type
        signature = issue.signature
    else:
        # On-schema + well-formed → a clean draft awaiting human placement.
        item_type = "proposed_edge"
        signature = f"propose_edge:{args.edge_type}:{args.source_entity_id}->{args.target_entity_id}"

    # Fail-fast endpoint precheck (WS-4B / contract C5) — the LAST gate before
    # parking, so the cheap in-memory schema/temporal checks reject first. The
    # confirm-time write (`create_relation`) matches both endpoints by
    # `Entity.id`; an edge referencing an id that isn't a node would park then
    # fail two steps later at confirm with a late, confusing error. Reject now
    # with KG_ENDPOINT_NOT_NODE and tell the agent exactly what to do: project
    # the glossary entities into the graph first (kg_project_entities_to_nodes).
    # This READS Neo4j (INV-K1 is about not WRITING it — the write stays human-
    # gated), the one stateful check worth a round-trip to avoid the dead-end.
    endpoint_ids = [args.source_entity_id, args.target_entity_id]
    async with neo4j_session() as session:
        present = await existing_entity_node_ids(
            session, user_id=str(owner), ids=endpoint_ids,
        )
    missing = [eid for eid in endpoint_ids if eid not in present]
    if missing:
        raise ToolExecutionError(
            "edge endpoint(s) are not yet graph nodes: "
            + ", ".join(missing)
            + " — project the glossary entities into the graph first "
            "(kg_project_entities_to_nodes), then propose the edge",
            code="KG_ENDPOINT_NOT_NODE",
            detail={"missing": missing},
        )

    parked = await ctx.triage_repo.park(
        user_id=owner,
        project_id=project_str,
        item_type=item_type,
        signature=signature,
        payload=payload,
        source={"proposed_by": "llm_tool_call", "session_id": ctx.session_id},
        schema_version=resolved.schema_version,
    )
    return {
        "parked": True,
        "triage_id": str(parked.triage_id),
        "item_type": parked.item_type,
        "signature": parked.signature,
        "on_schema": issue is None,
    }


async def _handle_kg_project_entities_to_nodes(
    ctx: "ToolContext", args: KgProjectEntitiesToNodesArgs,
) -> dict:
    # A (deterministic, idempotent projection). Reads the book's glossary
    # entities (all active, or the `entity_ids` subset) and upserts each as a
    # canonical :Entity node — the structured "seed the graph from recorded
    # lore" path (WS-4B / S04), so a prose-less book can build a graph without
    # chapter extraction. Runs under the project OWNER (resolve-to-owner).
    from app.tools.executor import ToolExecutionError
    from app.clients.glossary_client import get_glossary_client
    from app.extraction.anchor_loader import project_glossary_entities_to_nodes

    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    meta = await ctx.projects_repo.project_meta(ctx.project_id)
    if meta is None:  # the owner gate passed above; stay defensive
        raise ToolExecutionError("project not found")
    _, book_id = meta
    if book_id is None:
        raise ToolExecutionError(
            "this project isn't linked to a book, so it has no glossary "
            "entities to project — link a book to the project first"
        )

    entity_ids = [e.strip() for e in (args.entity_ids or []) if e and e.strip()]
    async with neo4j_session() as session:
        res = await project_glossary_entities_to_nodes(
            session,
            get_glossary_client(),
            user_id=str(owner),
            project_id=str(ctx.project_id),
            book_id=book_id,
            entity_ids=entity_ids or None,
        )
        # D-KG-STAT-CACHE-DEAD (rail HIGH): the projection just changed the graph, so
        # refresh the cached counters NOW — reusing the open Neo4j session for an
        # authoritative recount. This is the ONLY production writer of stat_updated_at:
        # the K16.14 stats_updater was never wired to a caller, so entity_count stayed
        # UNKNOWN forever, and the flagship vision-to-book rail (connect-people is
        # done_when "connections > 0") could never see its own projection land and
        # stalled at STOP_UNKNOWN. Recounting here makes `connections` become KNOWN the
        # moment the cast is placed. Best-effort: the stats are advisory (the projection
        # itself is the contract), so a recount hiccup must not fail a successful placement.
        try:
            from app.jobs.stats_updater import reconcile_project_stats

            await reconcile_project_stats(
                ctx.projects_repo._pool, session, owner, ctx.project_id
            )
        except Exception:  # pragma: no cover - advisory cache, never blocks the projection
            logger.warning(
                "kg_project_entities_to_nodes: stat recount failed (project_id=%s); "
                "counters stay stale but the projection succeeded",
                ctx.project_id,
                exc_info=True,
            )
    out: dict = {
        "nodes_created": res.created,
        "nodes_existing": res.existing,
        "entities_seen": res.seen,
        "skipped": res.skipped,
    }
    # Never report a PARTIAL projection as a complete one.
    notes: list[str] = []
    if res.truncated:
        out["truncated"] = True
        notes.append(
            "the book has more entities than one projection pass could read; "
            "re-run with explicit entity_ids to project the remainder"
        )
    if res.conflicted:
        # D-KG-GLOSSARY-FK-GLOBAL-UNIQUE: Entity.glossary_entity_id carries a GLOBAL
        # uniqueness constraint, so entities already anchored by this book's other
        # knowledge project cannot be anchored again here. Say so plainly instead of
        # silently returning a smaller nodes_created.
        out["nodes_conflicted"] = res.conflicted
        notes.append(
            f"{res.conflicted} entit{'y' if res.conflicted == 1 else 'ies'} could not "
            "be added because another knowledge project for this book already owns "
            "them in the graph; query that project, or use it for this book's graph"
        )
    if notes:
        out["note"] = " · ".join(notes)
    return out


async def _handle_kg_create_node(ctx: "ToolContext", args: KgCreateNodeArgs) -> dict:
    """A (reversible, idempotent). Manually mint ONE :Entity node so an agent can
    give kg_propose_edge a real endpoint (an edge whose endpoints aren't nodes is
    parked, then fails). Runs under the project OWNER (resolve-to-owner, EDIT grant),
    so a collaborator resolves the grant but the write is still owner-scoped."""
    from app.tools.executor import ToolExecutionError
    from app.db.neo4j_repos.entities import merge_entity

    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    name = args.name.strip()
    kind = args.kind.strip()
    if not name or not kind:
        raise ToolExecutionError("name and kind must both be non-empty")
    async with neo4j_session() as session:
        entity = await merge_entity(
            session,
            user_id=str(owner),
            project_id=str(ctx.project_id),
            name=name,
            kind=kind,
            source_type="manual",
            provenance="human_authored",
        )
    return {
        "entity_id": entity.id,
        "name": entity.name,
        "kind": entity.kind,
        "note": "node ready — pass entity_id as a subject/object endpoint to kg_propose_edge",
    }


async def _handle_kg_view_upsert(ctx: "ToolContext", args: KgViewUpsertArgs) -> dict:
    # W (reversible, owner==caller). Views are per-user; the caller owns their
    # views even in a shared project, so this enforces owner==caller (the repo
    # is keyed on (project, user, code)). A project grant is still required to
    # confirm the caller can reach the project at all.
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    view, created = await ctx.graph_views_repo.upsert(
        ctx.user_id,
        str(ctx.project_id),
        code=args.code,
        name=args.name,
        description=args.description,
        edge_type_codes=args.edge_type_codes,
        node_kind_codes=args.node_kind_codes,
    )
    return {"created": created, "view": view.model_dump(mode="json")}


async def _handle_kg_view_delete(ctx: "ToolContext", args: KgViewDeleteArgs) -> dict:
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    deleted = await ctx.graph_views_repo.delete(
        ctx.user_id, str(ctx.project_id), args.code
    )
    return {"deleted": deleted, "code": args.code}


async def _handle_kg_triage_resolve(ctx: "ToolContext", args: KgTriageResolveArgs) -> dict:
    # W (reversible) — KG-LOCAL actions ONLY (Edit-gated). The arg model already
    # constrains `action` to the KG-local set; defense-in-depth re-asserts it so
    # a schema-mutating / handoff action can never slip through to a non-confirm
    # path (those are class-C, deferred to KM6).
    from app.tools.executor import ToolExecutionError

    if args.action not in _KG_LOCAL_TRIAGE_ACTIONS:
        raise ToolExecutionError(
            f"action '{args.action}' requires human confirmation and is not "
            "available to the assistant; use the review surface"
        )
    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    project_str = str(ctx.project_id)

    # Confirm the signature group exists + the action is valid for its
    # item_type (mirrors the HTTP router's validation).
    pending = await ctx.triage_repo.list_pending_for_signature(
        user_id=owner, project_id=project_str, signature=args.signature
    )
    if not pending:
        raise ToolExecutionError("no pending triage items for this signature")
    item_type = pending[0].item_type
    from app.db.repositories.triage import SUGGESTED_ACTIONS

    if args.action not in set(SUGGESTED_ACTIONS.get(item_type, [])):
        raise ToolExecutionError(
            f"action '{args.action}' is not valid for item_type '{item_type}'"
        )

    affected = await ctx.triage_repo.resolve_signature(
        user_id=owner,
        project_id=project_str,
        signature=args.signature,
        action=args.action,
        params=args.params,
        resolved_by=str(ctx.user_id),
        new_status="resolved",
    )
    return {"status": "resolved", "affected": affected, "action": args.action}


async def _handle_kg_schema_edit(ctx: "ToolContext", args: KgSchemaEditArgs) -> dict:
    """C (confirm-token) — KM6. Adds/deprecates a project edge_type|fact_type and
    bumps schema_version. **Mints a confirm-token and returns it — performs NO
    write** (INV-K1 + INV-T3: a graph-shape change is human-confirmed). The human
    redeems the token at `POST /v1/kg/actions/confirm` (browser-JWT only; this MCP
    path can never reach it).

    Gate: MANAGE on the project. Requires an ADOPTED project-scoped schema — a project
    resolving to the System `general` template has nothing project-local to edit, and
    the System tier is admin-only (never user-editable). The token captures the live
    schema_id + schema_version so confirm rejects on drift (optimistic concurrency)."""
    from app.tools.executor import ToolExecutionError

    await _resolve_project_owner(ctx, GrantLevel.MANAGE)
    project_str = str(ctx.project_id)

    current = await ctx.graph_schemas_repo.active_project_schema(project_str)
    if current is None:
        raise ToolExecutionError(
            "this project has no adopted ontology to edit — adopt a project schema "
            "first (the System template is read-only and admin-managed)"
        )

    label = args.label.strip() or args.code  # add needs a label; default to the code
    params = {
        "verb": args.verb,
        "level": args.level,
        "code": args.code,
        "label": label,
        "schema_id": str(current.schema_id),
        "expected_schema_version": current.schema_version,
    }
    # Bind to the PROPOSER (ctx.user_id) — confirm requires redeemer == proposer.
    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),
            descriptor=DESC_SCHEMA_EDIT,
            project_id=project_str,
            params=params,
        ),
        time.time(),
    )
    if not token:  # empty secret / misconfig → fail closed (never a silent no-op)
        raise ToolExecutionError("could not mint a confirmation token")

    bump = "deprecate" if args.verb == "deprecate" else "add"
    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_SCHEMA_EDIT,
        "summary": (
            f"{bump} {args.level} '{args.code}' "
            f"(schema v{current.schema_version} → v{current.schema_version + 1} on confirm)"
        ),
        "requires": "human confirmation via the review surface (no change applied yet)",
    }


async def _handle_kg_adopt_template(ctx: "ToolContext", args: KgAdoptTemplateArgs) -> dict:
    """C (confirm-token) — KM6-M2. Copies a system/user template down into the project
    (replace-on-adopt scaffold). **Mints a confirm-token and returns it — performs NO
    write** (INV-T3). The human redeems it at `POST /v1/kg/actions/confirm` (the adopt
    runs there, with the M1 glossary node-kind gate re-checked at confirm).

    Gate: MANAGE on the project. Validates the source is a template visible to the
    caller (system, or the caller's own) before minting."""
    from app.tools.executor import ToolExecutionError

    await _resolve_project_owner(ctx, GrantLevel.MANAGE)
    project_str = str(ctx.project_id)

    try:
        source_uuid = UUID(args.source_schema_id)
    except (ValueError, TypeError):
        raise ToolExecutionError("source_schema_id must be a valid template id")
    summary = await ctx.graph_schemas_repo.template_summary(source_uuid, ctx.user_id)
    if summary is None:
        raise ToolExecutionError(
            "no such template is available to adopt (use kg_list_templates to find one)"
        )

    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),
            descriptor=DESC_ADOPT,
            project_id=project_str,
            params={"source_schema_id": args.source_schema_id},
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_ADOPT,
        "summary": (
            f"adopt template '{summary['name']}' "
            f"({summary['edge_type_count']} edge types, {summary['node_kind_count']} "
            f"node kinds, {summary['fact_type_count']} fact types)"
        ),
        "requires": "human confirmation via the review surface (no change applied yet)",
    }


async def _handle_kg_sync_apply(ctx: "ToolContext", args: KgSyncApplyArgs) -> dict:
    """C (confirm-token) — KM6-M3. Applies keep_mine/take_theirs sync decisions to the
    project ontology (overwrites/deprecates rows; bumps schema_version). **Mints a
    confirm-token and returns it — performs NO write** (INV-T3). The human redeems it at
    `POST /v1/kg/actions/confirm`; optimistic-concurrency (`base_source_hash`) is
    re-checked there (upstream moved → rejected).

    Gate: MANAGE. Requires an adopted project schema with an upstream source to sync."""
    from app.tools.executor import ToolExecutionError

    await _resolve_project_owner(ctx, GrantLevel.MANAGE)
    project_str = str(ctx.project_id)

    active = await ctx.graph_schemas_repo.active_project_schema(project_str)
    if active is None:
        raise ToolExecutionError(
            "this project has no adopted ontology to sync — adopt a template first"
        )

    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),
            descriptor=DESC_SYNC,
            project_id=project_str,
            params={
                "base_source_hash": args.base_source_hash,
                "decisions": [d.model_dump() for d in args.decisions],
            },
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    take = sum(1 for d in args.decisions if d.choice == "take_theirs")
    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_SYNC,
        "summary": f"sync from template: {take} take-theirs / "
                   f"{len(args.decisions) - take} keep-mine decisions",
        "requires": "human confirmation via the review surface (no change applied yet)",
    }


async def _handle_kg_triage_place_edge(
    ctx: "ToolContext", args: KgTriagePlaceEdgeArgs
) -> dict:
    """C (confirm-token) — E2. Places a `proposed_edge` triage item into Neo4j.
    **Mints a confirm-token and returns it — performs NO write** (INV-K1): the
    central write path runs only after a human redeems the token at
    `POST /v1/kg/actions/confirm` (browser-JWT only; this MCP path can't reach it).

    Gate: EDIT on the project (placing a drafted edge is a KG-local-grade write,
    Edit-tier — symmetric with kg_triage_resolve). Validates the item is a still-
    pending `proposed_edge` for this owner before minting (no token for a vanished
    or wrong-type item)."""
    from app.tools.executor import ToolExecutionError

    owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)
    project_str = str(ctx.project_id)

    try:
        triage_uuid = UUID(args.triage_id)
    except (ValueError, TypeError):
        raise ToolExecutionError("triage_id must be a valid id")
    item = await ctx.triage_repo.get_item(
        user_id=owner, project_id=project_str, triage_id=triage_uuid
    )
    if item is None or item.item_type != "proposed_edge" or item.status != "pending":
        raise ToolExecutionError(
            "no pending proposed edge with that id (use kg_triage_list to find one)"
        )

    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),  # bind to the PROPOSER — confirm requires redeemer==proposer
            descriptor=DESC_TRIAGE_PROPOSED_EDGE,
            project_id=project_str,
            params={"triage_id": args.triage_id},
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    payload = item.payload or {}
    subject = payload.get("source_entity_id") or payload.get("subject_id")
    obj = payload.get("target_entity_id") or payload.get("object_id")
    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_TRIAGE_PROPOSED_EDGE,
        "summary": f"place edge {subject} —{payload.get('predicate')}→ {obj}",
        "requires": "human confirmation via the review surface (no change applied yet)",
    }


async def _handle_kg_triage_schema_write(
    ctx: "ToolContext", args: KgTriageSchemaWriteArgs
) -> dict:
    """C (confirm-token) — E3. Resolves a schema-mutating triage signature by MINTING
    a `kg_triage_schema_write` confirm-token (NO write — INV-T3). The human redeems it
    at `POST /v1/kg/actions/confirm`, which applies the ontology mutation (bumps the
    schema_version) + stamps the version onto the resolved items.

    Gate: MANAGE on the project (schema mutations are Manage-tier). Requires an ADOPTED
    project-scoped schema (the System tier is admin-only). The token captures the live
    schema_id + schema_version so confirm rejects on drift (optimistic concurrency)."""
    from app.tools.executor import ToolExecutionError

    await _resolve_project_owner(ctx, GrantLevel.MANAGE)
    project_str = str(ctx.project_id)

    current = await ctx.graph_schemas_repo.active_project_schema(project_str)
    if current is None:
        raise ToolExecutionError(
            "this project has no adopted ontology to edit — adopt a project schema "
            "first (the System template is read-only and admin-managed)"
        )

    token = mint_action_token(
        settings.jwt_secret,
        ActionClaims(
            jti=str(uuid4()),
            authority=AUTH_GRANT,
            user_id=str(ctx.user_id),  # bind to the proposer
            descriptor=DESC_TRIAGE_SCHEMA_WRITE,
            project_id=project_str,
            params={
                "action": args.action,
                "signature": args.signature,
                "schema_id": str(current.schema_id),
                "expected_schema_version": current.schema_version,
                "code": args.code,
                "label": args.label,
                "set_code": args.set_code,
                "add_kinds": args.add_kinds,
            },
        ),
        time.time(),
    )
    if not token:
        raise ToolExecutionError("could not mint a confirmation token")

    return {
        "proposed": True,
        "confirm_token": token,
        "expires_in_s": ACTION_TOKEN_TTL_S,
        "descriptor": DESC_TRIAGE_SCHEMA_WRITE,
        "summary": (
            f"{args.action} '{args.code or args.set_code}' "
            f"(schema v{current.schema_version} → v{current.schema_version + 1} on confirm)"
        ),
        "requires": "human confirmation via the review surface (no change applied yet)",
    }


GRAPH_SCHEMA_HANDLERS = {
    "kg_graph_query": _handle_kg_graph_query,
    "kg_world_query": _handle_kg_world_query,
    "kg_multi_query": _handle_kg_multi_query,
    "kg_entity_edge_timeline": _handle_kg_entity_edge_timeline,
    "kg_schema_read": _handle_kg_schema_read,
    "kg_list_templates": _handle_kg_list_templates,
    "kg_sync_available": _handle_kg_sync_available,
    "kg_view_read": _handle_kg_view_read,
    "kg_triage_list": _handle_kg_triage_list,
    "kg_propose_fact": _handle_kg_propose_fact,
    "kg_propose_edge": _handle_kg_propose_edge,
    "kg_project_entities_to_nodes": _handle_kg_project_entities_to_nodes,
    "kg_create_node": _handle_kg_create_node,
    "kg_view_upsert": _handle_kg_view_upsert,
    "kg_view_delete": _handle_kg_view_delete,
    "kg_triage_resolve": _handle_kg_triage_resolve,
    "kg_schema_edit": _handle_kg_schema_edit,
    "kg_adopt_template": _handle_kg_adopt_template,
    "kg_sync_apply": _handle_kg_sync_apply,
    "kg_triage_place_edge": _handle_kg_triage_place_edge,
    "kg_triage_schema_write": _handle_kg_triage_schema_write,
}
