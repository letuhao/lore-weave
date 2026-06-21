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

import time
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

# KG-LOCAL triage actions this lane resolves directly (Edit-gated, reversible).
# The schema-mutating + glossary-handoff actions are class-C (KM6) and rejected
# here with a clear tool error pointing the agent at the human-confirm surface.
_KG_LOCAL_TRIAGE_ACTIONS = ("map", "re_target", "drop_edge", "close_previous", "dismiss")

# Schema-mutating triage actions the kg_triage_schema_write tool mints for (E3).
_ACTIONS_SCHEMA_WRITE = (
    "add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active",
)


# ── arg models (extra="forbid"; envelope keys are NEVER fields) ───────


class KgGraphQueryArgs(BaseModel):
    """`kg_graph_query` — nodes+edges for a view, as-of a chapter."""

    model_config = ConfigDict(extra="forbid")

    view: str | None = Field(default=None, max_length=_CODE_MAX)
    as_of_chapter: int | None = Field(default=None, ge=0)
    limit: int = Field(default=GRAPH_LIMIT_DEFAULT, ge=1, le=GRAPH_LIMIT_MAX)


class KgEntityEdgeTimelineArgs(BaseModel):
    """`kg_entity_edge_timeline` — the temporal instance chain for one
    entity + edge type (e.g. a drive arc)."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1, max_length=200)
    edge_type: str = Field(min_length=1, max_length=_CODE_MAX)
    limit: int = Field(default=TIMELINE_LIMIT_DEFAULT, ge=1, le=TIMELINE_LIMIT_MAX)


class KgSchemaReadArgs(BaseModel):
    """`kg_schema_read` — the resolved (effective) project graph schema."""

    model_config = ConfigDict(extra="forbid")


class KgListTemplatesArgs(BaseModel):
    """`kg_list_templates` — system + the caller's user templates."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["system", "user"] | None = None


class KgSyncAvailableArgs(BaseModel):
    """`kg_sync_available` — does the project schema have upstream updates?"""

    model_config = ConfigDict(extra="forbid")


class KgViewReadArgs(BaseModel):
    """`kg_view_read` — list the caller's views in the project."""

    model_config = ConfigDict(extra="forbid")


class KgTriageListArgs(BaseModel):
    """`kg_triage_list` — the triage queue grouped by signature."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "pending_glossary", "resolved", "dismissed"] = "pending"
    limit: int = Field(default=TRIAGE_LIMIT_DEFAULT, ge=1, le=TRIAGE_LIMIT_MAX)


class KgProposeFactArgs(BaseModel):
    """`kg_propose_fact` — draft a narrative fact into the inbox (reviewed)."""

    model_config = ConfigDict(extra="forbid")

    fact_text: str = Field(min_length=1, max_length=2000)
    fact_type: Literal["decision", "preference", "milestone", "negation"]


class KgProposeEdgeArgs(BaseModel):
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


class KgViewUpsertArgs(BaseModel):
    """`kg_view_upsert` — create/replace one of the caller's views."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=_CODE_MAX)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str = Field(default="", max_length=2000)
    edge_type_codes: list[str] = Field(default_factory=list, max_length=200)
    node_kind_codes: list[str] = Field(default_factory=list, max_length=200)


class KgViewDeleteArgs(BaseModel):
    """`kg_view_delete` — delete one of the caller's views by code."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=_CODE_MAX)


class KgTriageResolveArgs(BaseModel):
    """`kg_triage_resolve` — resolve a triage signature with a KG-LOCAL action.

    Only the reversible KG-local actions are accepted here (Edit-gated). The
    schema-mutating (add_to_vocab/add_to_schema/widen/set_multi_active) and
    glossary-handoff (promote/demote) actions are class-C and require the KM6
    confirm machinery — this tool rejects them with a clear tool error."""

    model_config = ConfigDict(extra="forbid")

    signature: str = Field(min_length=1, max_length=500)
    action: Literal["map", "re_target", "drop_edge", "close_previous", "dismiss"]
    params: dict = Field(default_factory=dict)


class KgSchemaEditArgs(BaseModel):
    """`kg_schema_edit` — class-C. Adds or deprecates a project edge_type/fact_type
    and bumps the schema_version. Mints a confirm-token (no write); a human confirms
    via the review surface (INV-K1: graph-shape changes are human-gated)."""

    model_config = ConfigDict(extra="forbid")

    verb: Literal["add", "deprecate"]
    level: Literal["edge_type", "fact_type"]
    code: str = Field(min_length=1, max_length=_CODE_MAX)
    label: str = Field(default="", max_length=_NAME_MAX)


class KgAdoptTemplateArgs(BaseModel):
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


class KgSyncApplyArgs(BaseModel):
    """`kg_sync_apply` — class-C. Applies per-child keep_mine/take_theirs decisions to
    bring the project ontology in line with its upstream template. Mints a confirm-token
    (no write). `base_source_hash` is the upstream hash from `kg_sync_available`."""

    model_config = ConfigDict(extra="forbid")

    base_source_hash: str = Field(min_length=1, max_length=128)
    decisions: list[KgSyncDecision] = Field(default_factory=list)


class KgTriagePlaceEdgeArgs(BaseModel):
    """`kg_triage_place_edge` — class-C. Places a drafted `proposed_edge` triage item
    into the graph. Mints a `kg_triage_proposed_edge` confirm-token (NO write — INV-K1);
    a human redeems it on the review surface. `triage_id` is from `kg_triage_list`."""

    model_config = ConfigDict(extra="forbid")

    triage_id: str = Field(min_length=1, max_length=64)


class KgTriageSchemaWriteArgs(BaseModel):
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


GRAPH_SCHEMA_ARG_MODELS: dict[str, type[BaseModel]] = {
    # ── R (read) ──────────────────────────────────────────────────────
    "kg_graph_query": KgGraphQueryArgs,
    "kg_entity_edge_timeline": KgEntityEdgeTimelineArgs,
    "kg_schema_read": KgSchemaReadArgs,
    "kg_list_templates": KgListTemplatesArgs,
    "kg_sync_available": KgSyncAvailableArgs,
    "kg_view_read": KgViewReadArgs,
    "kg_triage_list": KgTriageListArgs,
    # ── W (low-impact, reversible, owner/grant-gated) ─────────────────
    "kg_propose_fact": KgProposeFactArgs,
    "kg_propose_edge": KgProposeEdgeArgs,
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
        },
        [],
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
        },
        ["entity_id", "edge_type"],
    ),
    _tool(
        "kg_schema_read",
        "Read the resolved (effective) graph schema for the current project — "
        "the edge types, fact types, controlled vocab, and expected node "
        "kinds. Use this to learn what relationship and fact codes are valid "
        "before proposing an edge or fact.",
        {},
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
        {},
        [],
    ),
    _tool(
        "kg_view_read",
        "List the caller's saved views (named lenses of edge/node kinds) for "
        "the current project. Views are per-user — you only ever see your own.",
        {},
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
        },
        ["source_entity_id", "target_entity_id", "edge_type"],
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
        raise ToolExecutionError("a project must be in scope for this tool")
    meta = await ctx.projects_repo.project_meta(ctx.project_id)
    if meta is None:
        raise ToolExecutionError("project not found")
    owner, book_id = meta
    if ctx.user_id == owner:
        return owner
    if book_id is None:
        raise ToolExecutionError("project not found")  # book-less → owner-only
    lvl = await ctx.grant_client.resolve_grant(book_id, ctx.user_id)
    if lvl == GrantLevel.NONE:
        raise ToolExecutionError("project not found")  # non-grantee → no oracle
    if not lvl.at_least(need):
        raise ToolExecutionError("insufficient access for this action")
    return owner


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
    return slice_.model_dump(mode="json")


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
            args.entity_id, ctx.user_id, ctx.grant_client, ctx.projects_repo
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
    return build_timeline(args.entity_id, args.edge_type, records).model_dump(mode="json")


async def _handle_kg_schema_read(ctx: "ToolContext", args: KgSchemaReadArgs) -> dict:
    await _resolve_project_owner(ctx, GrantLevel.VIEW)
    resolved = await ctx.ontology_resolver.resolve(str(ctx.project_id))
    return resolved.model_dump(mode="json")


async def _handle_kg_list_templates(ctx: "ToolContext", args: KgListTemplatesArgs) -> dict:
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
    return {
        "groups": [
            {
                "signature": g.signature,
                "item_type": g.item_type,
                "count": g.count,
                "status": g.status,
                "sample_payload": g.sample_payload,
                "suggested_actions": g.suggested_actions,
            }
            for g in groups
        ],
        "has_more": has_more,
    }


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
    # required at MINT, then park to the triage inbox. NEVER writes Neo4j
    # (INV-K1): the central write-path applies it only after human review.
    from app.tools.executor import ToolExecutionError

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
    "kg_entity_edge_timeline": _handle_kg_entity_edge_timeline,
    "kg_schema_read": _handle_kg_schema_read,
    "kg_list_templates": _handle_kg_list_templates,
    "kg_sync_available": _handle_kg_sync_available,
    "kg_view_read": _handle_kg_view_read,
    "kg_triage_list": _handle_kg_triage_list,
    "kg_propose_fact": _handle_kg_propose_fact,
    "kg_propose_edge": _handle_kg_propose_edge,
    "kg_view_upsert": _handle_kg_view_upsert,
    "kg_view_delete": _handle_kg_view_delete,
    "kg_triage_resolve": _handle_kg_triage_resolve,
    "kg_schema_edit": _handle_kg_schema_edit,
    "kg_adopt_template": _handle_kg_adopt_template,
    "kg_sync_apply": _handle_kg_sync_apply,
    "kg_triage_place_edge": _handle_kg_triage_place_edge,
    "kg_triage_schema_write": _handle_kg_triage_schema_write,
}
