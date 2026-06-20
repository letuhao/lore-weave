"""Fail-soft schema validation (K3) — pure functions, never raise/reject.

Given a resolved schema (`ResolvedSchema`) and a *proposed* graph element
(node / edge / fact / vocab-value), classify whether it matches the schema and,
if not, return a structured `ValidationIssue` the caller parks to triage (or
logs). **Fail-soft is the contract:** validation NEVER raises and NEVER decides
to drop — it only describes. Hard reject + drop-and-triage live in lane L7.

The `item_type` strings for the four schema-mismatch classes that map onto the
spec §3.7 triage taxonomy are EXACTLY the enum values
(`unknown_node_kind`, `unknown_edge_type`, `edge_kind_mismatch`,
`unknown_vocab_value`) — LH stores them straight into `kg_triage_items`. The
fifth taxonomy member, `edge_cardinality_conflict`, is a stateful condition
(an open instance already exists) the pure validator can't see, so it is
detected at the write path (L7), not here.

A **fact-type** mismatch is deliberately NOT in the §3.7 enum, so we DO NOT
invent a triage item_type for it: we surface a clearly-named non-triage issue
``validation_fact_type`` the caller can log. (Mapping it to the nearest enum
value would corrupt the triage queue's signatures.)

`signature` is the normalized group key LH batches by (spec §11.3): e.g.
``drive:curiosity``, ``edge:PURSUES``, ``edge_kind:LOVER_OF:character->organization``,
``node_kind:bloodline``. Resolve one item of a signature → apply to all parked
items sharing it.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.7, §11.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.db.ontology_models import ResolvedSchema, TriageItemType

__all__ = [
    "IssueType",
    "ValidationIssue",
    "validate_node_kind",
    "validate_edge",
    "validate_vocab_value",
    "validate_fact_type",
]

# The validator emits the four §3.7 enum members that a *pure* check can
# classify, plus one non-triage diagnostic for fact-type mismatch (not in the
# taxonomy). `edge_cardinality_conflict` is intentionally absent — it needs
# write-time state, classified in L7.
IssueType = Literal[
    "unknown_node_kind",
    "unknown_edge_type",
    "edge_kind_mismatch",
    "unknown_vocab_value",
    # NOT a §3.7 triage item_type — a diagnostic the caller logs, never parks
    # as a triage row (no enum value to coerce it onto).
    "validation_fact_type",
]


class ValidationIssue(BaseModel):
    """One fail-soft mismatch between a proposed element and the schema.

    ``item_type`` carries the §3.7 triage enum value for the four mapping
    classes (so LH writes it verbatim) or ``validation_fact_type`` for the
    non-triage fact diagnostic. ``signature`` is the normalized batch key
    (§11.3). ``payload`` echoes the offending element for the triage row.
    """

    model_config = ConfigDict(frozen=True)

    item_type: IssueType
    signature: str
    payload: dict[str, Any]

    @property
    def is_triage(self) -> bool:
        """True when ``item_type`` is a real §3.7 triage enum member.

        ``validation_fact_type`` is the lone non-triage diagnostic; everything
        else this validator emits is a parkable triage class. Cross-checked
        against `TriageItemType` so a future enum change keeps this honest.
        """
        return self.item_type in _TRIAGE_ENUM


# The §3.7 enum, sourced from the model so this can't silently drift.
_TRIAGE_ENUM: frozenset[str] = frozenset(TriageItemType.__args__)  # type: ignore[attr-defined]


# ── node kind ─────────────────────────────────────────────────────────
def validate_node_kind(schema: ResolvedSchema, kind_code: str) -> ValidationIssue | None:
    """A node whose kind is not in the resolved node-kinds → ``unknown_node_kind``.

    The resolved node-kinds are the schema's ``kg_schema_node_kinds`` (M1). A
    kind outside that set is parked (`optional`-strength mismatches surface
    here at extraction time, per M1).
    """
    known = {nk.kind_code for nk in schema.node_kinds}
    if kind_code in known:
        return None
    return ValidationIssue(
        item_type="unknown_node_kind",
        signature=f"node_kind:{kind_code}",
        payload={"kind_code": kind_code},
    )


# ── edge ──────────────────────────────────────────────────────────────
def validate_edge(
    schema: ResolvedSchema,
    *,
    predicate: str,
    source_kind: str | None = None,
    target_kind: str | None = None,
) -> ValidationIssue | None:
    """Classify a proposed edge against the schema's edge-type vocab.

    * predicate ∈ ``kg_edge_types`` → check endpoint kinds (below).
    * predicate ∉ edge-types AND ``allow_free_edges`` → OK (free edge, None).
    * predicate ∉ edge-types AND closed → ``unknown_edge_type``.
    * edge-type exists but ``source_kind``/``target_kind`` not in its
      declared ``source_node_kinds``/``target_node_kinds`` → ``edge_kind_mismatch``.

    Endpoint-kind checks only fire when the edge-type *declares* a constraint
    (non-empty list) AND the caller supplied that endpoint's kind — an
    unconstrained edge-type (empty list) or an unknown endpoint kind is not a
    mismatch here (the endpoint's own kind goes through `validate_node_kind`).
    """
    by_code = {e.code: e for e in schema.edge_types}
    edge = by_code.get(predicate)
    if edge is None:
        if schema.allow_free_edges:
            return None  # free-string predicate, today's behavior (Q2)
        return ValidationIssue(
            item_type="unknown_edge_type",
            signature=f"edge:{predicate}",
            payload={"predicate": predicate},
        )

    # Edge-type known — check endpoint kinds against its declared constraints.
    if source_kind is not None and edge.source_node_kinds and source_kind not in edge.source_node_kinds:
        return _edge_kind_mismatch(predicate, source_kind, target_kind, "source")
    if target_kind is not None and edge.target_node_kinds and target_kind not in edge.target_node_kinds:
        return _edge_kind_mismatch(predicate, source_kind, target_kind, "target")
    return None


def _edge_kind_mismatch(
    predicate: str, source_kind: str | None, target_kind: str | None, end: str,
) -> ValidationIssue:
    return ValidationIssue(
        item_type="edge_kind_mismatch",
        # group by predicate + the kind pair so identical mismatches batch
        # (e.g. every LOVER_OF: character->organization).
        signature=f"edge_kind:{predicate}:{source_kind}->{target_kind}",
        payload={
            "predicate": predicate,
            "source_kind": source_kind,
            "target_kind": target_kind,
            "violating_endpoint": end,
        },
    )


# ── vocab value ───────────────────────────────────────────────────────
def validate_vocab_value(
    schema: ResolvedSchema, *, set_code: str, value: str,
) -> ValidationIssue | None:
    """A value assigned to a *closed* vocab set that isn't in it → ``unknown_vocab_value``.

    Unknown set, or an *open* set, is not an issue (open sets accept new
    values; an unknown set means the schema doesn't constrain it). Signature
    is ``<set_code>:<value>`` per §11.3 (e.g. ``drive:curiosity``).
    """
    by_code = {s.code: s for s in schema.vocab_sets}
    vset = by_code.get(set_code)
    if vset is None or not vset.closed:
        return None
    known = {v.code for v in schema.vocab_values.get(set_code, [])}
    if value in known:
        return None
    return ValidationIssue(
        item_type="unknown_vocab_value",
        signature=f"{set_code}:{value}",
        payload={"set_code": set_code, "value": value},
    )


# ── fact type ─────────────────────────────────────────────────────────
def validate_fact_type(schema: ResolvedSchema, fact_code: str) -> ValidationIssue | None:
    """A fact whose code isn't a schema ``kg_fact_types`` → ``validation_fact_type``.

    NOTE: fact-type mismatch is NOT in the §3.7 triage enum, so this returns
    the non-triage ``validation_fact_type`` diagnostic (``is_triage == False``).
    The caller logs it rather than parking a triage row — there is no taxonomy
    value to coerce it onto, and inventing one would pollute triage signatures.
    """
    known = {f.code for f in schema.fact_types}
    if fact_code in known:
        return None
    return ValidationIssue(
        item_type="validation_fact_type",
        signature=f"fact:{fact_code}",
        payload={"fact_code": fact_code},
    )
