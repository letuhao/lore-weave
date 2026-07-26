"""KG customizable-ontology models (epic 2026-06-20, lane L1).

Pydantic projections of the `kg_*` graph-schema tables (DDL in migrate.py).
Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.

Tiered system/user/project graph schemas — the KG-owned equivalent of the
glossary genre·kind·attribute tiering, but for *graph shape* (edge types,
fact/state types, controlled vocab) rather than node identity. Node identity
stays in glossary; KG anchors expected node-kinds by code (soft ref) and
carries an adopt `strength` per kind (M1, LOCKED S0).

This module is imported once by app/db/models.py so the package exposes a
single `app.db.models` surface (mirrors the existing house pattern).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

# ── shared enums (mirror the DB CHECK constraints in migrate.py) ──────
Scope = Literal["system", "user", "project"]
Strength = Literal["required", "optional"]
Cardinality = Literal["single_active", "multi_active"]
# The triage item taxonomy (spec §3.7) — the five ways an extracted element can
# fail to match the resolved schema, plus `proposed_edge` (D-KG-LF-PROPOSE-EDGE-
# INBOX): a well-formed on-schema edge the agent DRAFTED via kg_propose_edge,
# awaiting human placement (distinct from the extraction-mismatch types — it is
# not a failure, just an unconfirmed proposal).
TriageItemType = Literal[
    "unknown_node_kind",
    "unknown_edge_type",
    "edge_kind_mismatch",
    "unknown_vocab_value",
    "edge_cardinality_conflict",
    "proposed_edge",
]
TriageStatus = Literal["pending", "pending_glossary", "resolved", "dismissed"]

# `code` is a stable slug: lower/upper snake, 1..120 chars. Validated in
# Pydantic for early 422s; mirrored by DB CHECK length caps.
SchemaCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
SchemaName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class GraphSchema(BaseModel):
    """A tiered graph schema (kg_graph_schemas)."""

    model_config = ConfigDict(from_attributes=True)

    schema_id: UUID
    scope: Scope
    # NULL for system; user_id for user; project_id for project. Stored as
    # TEXT because project_id/user_id are different id-spaces at this tier.
    scope_id: str | None = None
    code: str
    name: str
    description: str = ""
    schema_version: int = 1
    # Q2 (LOCKED S0): true => off-vocab free-string predicates allowed
    # (today's behavior); false => closed to kg_edge_types (off-vocab → triage).
    allow_free_edges: bool = True
    content_hash: str | None = None
    source_ref: str | None = None
    source_hash: str | None = None
    deprecated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EdgeType(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    edge_type_id: UUID
    schema_id: UUID
    code: str
    label: str
    directed: bool = True
    source_node_kinds: list[str] = []
    target_node_kinds: list[str] = []
    # true => every instance must carry valid_from + :EVIDENCED_BY (enforced L7).
    temporal: bool = False
    provenance_required: bool = False
    # single_active => opening a new instance auto-closes the open one (L7);
    # multi_active => coexisting instances (e.g. PURSUES — multiple drives).
    cardinality: Cardinality = "multi_active"
    description: str = ""
    deprecated_at: datetime | None = None


class FactType(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_type_id: UUID
    schema_id: UUID
    code: str
    label: str
    description: str = ""
    deprecated_at: datetime | None = None


class VocabSet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vocab_set_id: UUID
    schema_id: UUID
    code: str
    label: str
    description: str = ""
    # true => extractor may only assign existing values, never coin new ones.
    closed: bool = True
    deprecated_at: datetime | None = None


class VocabValue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vocab_value_id: UUID
    vocab_set_id: UUID
    code: str
    label: str
    metadata: dict[str, Any] = {}


class SchemaNodeKind(BaseModel):
    """Expected node-kind a schema anchors to glossary, with adopt strength.

    M1 (LOCKED S0): `required` kinds gate adopt (block if glossary missing);
    `optional` kinds warn + park unknown_node_kind triage at extraction.
    """

    model_config = ConfigDict(from_attributes=True)

    schema_node_kind_id: UUID
    schema_id: UUID
    kind_code: str
    strength: Strength
    deprecated_at: datetime | None = None


class GraphView(BaseModel):
    """A per-user named lens over a project graph (READ-only; kg_views)."""

    model_config = ConfigDict(from_attributes=True)

    view_id: UUID
    project_id: str
    user_id: UUID
    code: str
    name: str
    description: str = ""
    edge_type_codes: list[str] = []
    node_kind_codes: list[str] = []
    created_at: datetime
    updated_at: datetime


class TriageItem(BaseModel):
    """A parked extraction element that didn't match the resolved schema."""

    model_config = ConfigDict(from_attributes=True)

    triage_id: UUID
    user_id: UUID
    project_id: str
    source: dict[str, Any] = {}
    item_type: TriageItemType
    payload: dict[str, Any] = {}
    signature: str
    status: TriageStatus = "pending"
    resolution: dict[str, Any] | None = None
    schema_version: int | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None


# ── resolved (merged) schema — the extraction/query effective view ────
class ResolvedSchema(BaseModel):
    """system→user→project merge, shadowing by `code` (spec §3.5)."""

    project_id: str
    schema_version: int
    allow_free_edges: bool
    edge_types: list[EdgeType] = []
    fact_types: list[FactType] = []
    vocab_sets: list[VocabSet] = []
    vocab_values: dict[str, list[VocabValue]] = {}  # keyed by vocab_set code
    node_kinds: list[SchemaNodeKind] = []
