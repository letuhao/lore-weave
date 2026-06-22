"""Unit tests for lane LA fail-soft validation (app/ontology/validation.py).

No DB. Builds a small ResolvedSchema by hand and asserts each item_type
classification, the free-edge OK path, edge_kind_mismatch, closed-vocab unknown
value, and the non-triage fact-type diagnostic.
"""

from __future__ import annotations

from uuid import uuid4

from app.db.ontology_models import (
    EdgeType,
    FactType,
    ResolvedSchema,
    SchemaNodeKind,
    VocabSet,
    VocabValue,
)
from app.ontology.validation import (
    ValidationIssue,
    validate_edge,
    validate_fact_type,
    validate_node_kind,
    validate_vocab_value,
)


def _edge(code, src, tgt, **kw):
    return EdgeType(
        edge_type_id=uuid4(), schema_id=uuid4(), code=code, label=code.lower(),
        source_node_kinds=src, target_node_kinds=tgt, **kw,
    )


def _schema(*, allow_free_edges: bool) -> ResolvedSchema:
    return ResolvedSchema(
        project_id="p1",
        schema_version=3,
        allow_free_edges=allow_free_edges,
        edge_types=[
            _edge("LOVER_OF", ["character"], ["character"], temporal=True),
            _edge("PURSUES", ["character"], ["concept"]),
        ],
        fact_types=[
            FactType(fact_type_id=uuid4(), schema_id=uuid4(), code="realm_change", label="Realm"),
        ],
        vocab_sets=[
            VocabSet(vocab_set_id=uuid4(), schema_id=uuid4(), code="drive", label="Drive", closed=True),
            VocabSet(vocab_set_id=uuid4(), schema_id=uuid4(), code="tag", label="Tag", closed=False),
        ],
        vocab_values={
            "drive": [
                VocabValue(vocab_value_id=uuid4(), vocab_set_id=uuid4(), code="revenge", label="Revenge"),
                VocabValue(vocab_value_id=uuid4(), vocab_set_id=uuid4(), code="seek_dao", label="Seek Dao"),
            ],
        },
        node_kinds=[
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="character", strength="required"),
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="concept", strength="required"),
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="item", strength="optional"),
        ],
    )


# ── node kind ──────────────────────────────────────────────────────────
def test_known_node_kind_ok():
    assert validate_node_kind(_schema(allow_free_edges=True), "character") is None


def test_unknown_node_kind_issue():
    issue = validate_node_kind(_schema(allow_free_edges=True), "bloodline")
    assert isinstance(issue, ValidationIssue)
    assert issue.item_type == "unknown_node_kind"
    assert issue.signature == "node_kind:bloodline"
    assert issue.payload == {"kind_code": "bloodline"}
    assert issue.is_triage is True


# ── edge ───────────────────────────────────────────────────────────────
def test_known_edge_with_valid_endpoints_ok():
    assert validate_edge(
        _schema(allow_free_edges=False),
        predicate="LOVER_OF", source_kind="character", target_kind="character",
    ) is None


def test_free_edge_ok_when_allow_free_edges():
    # unknown predicate, but allow_free_edges → OK (today's behavior, Q2).
    assert validate_edge(
        _schema(allow_free_edges=True), predicate="WHISPERS_TO",
    ) is None


def test_unknown_edge_type_when_closed():
    issue = validate_edge(_schema(allow_free_edges=False), predicate="WHISPERS_TO")
    assert issue is not None
    assert issue.item_type == "unknown_edge_type"
    assert issue.signature == "edge:WHISPERS_TO"
    assert issue.payload == {"predicate": "WHISPERS_TO"}
    assert issue.is_triage is True


def test_edge_kind_mismatch_on_target():
    # LOVER_OF declares character->character; target organization is a mismatch.
    issue = validate_edge(
        _schema(allow_free_edges=True),
        predicate="LOVER_OF", source_kind="character", target_kind="organization",
    )
    assert issue is not None
    assert issue.item_type == "edge_kind_mismatch"
    assert issue.signature == "edge_kind:LOVER_OF:character->organization"
    assert issue.payload["violating_endpoint"] == "target"
    assert issue.is_triage is True


def test_edge_kind_mismatch_on_source():
    issue = validate_edge(
        _schema(allow_free_edges=True),
        predicate="PURSUES", source_kind="organization", target_kind="concept",
    )
    assert issue is not None
    assert issue.item_type == "edge_kind_mismatch"
    assert issue.payload["violating_endpoint"] == "source"


def test_edge_endpoint_checks_skip_when_kind_unsupplied():
    # No endpoint kinds passed → can't classify a mismatch; known edge → OK.
    assert validate_edge(_schema(allow_free_edges=False), predicate="LOVER_OF") is None


# ── vocab value ────────────────────────────────────────────────────────
def test_closed_vocab_unknown_value_issue():
    issue = validate_vocab_value(_schema(allow_free_edges=True), set_code="drive", value="curiosity")
    assert issue is not None
    assert issue.item_type == "unknown_vocab_value"
    assert issue.signature == "drive:curiosity"
    assert issue.payload == {"set_code": "drive", "value": "curiosity"}
    assert issue.is_triage is True


def test_closed_vocab_known_value_ok():
    assert validate_vocab_value(_schema(allow_free_edges=True), set_code="drive", value="revenge") is None


def test_open_vocab_accepts_any_value():
    assert validate_vocab_value(_schema(allow_free_edges=True), set_code="tag", value="anything") is None


def test_unknown_vocab_set_not_an_issue():
    assert validate_vocab_value(_schema(allow_free_edges=True), set_code="nope", value="x") is None


# ── fact type ──────────────────────────────────────────────────────────
def test_known_fact_type_ok():
    assert validate_fact_type(_schema(allow_free_edges=True), "realm_change") is None


def test_unknown_fact_type_is_non_triage_diagnostic():
    issue = validate_fact_type(_schema(allow_free_edges=True), "vibes_shift")
    assert issue is not None
    # NOT a §3.7 triage enum value — caller logs it, never parks a triage row.
    assert issue.item_type == "validation_fact_type"
    assert issue.is_triage is False
    assert issue.signature == "fact:vibes_shift"
