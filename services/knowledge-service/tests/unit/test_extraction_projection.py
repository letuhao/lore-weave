"""Unit tests for the ResolvedSchema → ExtractionSchema projection (L7 activation).

Covers the two postures (authoritative vs advisory) + the empty-event-kinds and
schema_version provenance contract.
"""

from __future__ import annotations

from uuid import uuid4

from app.db.ontology_models import EdgeType, FactType, ResolvedSchema, SchemaNodeKind
from app.ontology.extraction_projection import (
    build_extraction_schema,
    resolved_to_extraction_dict,
)


def _resolved(*, allow_free_edges: bool, schema_version: int = 7) -> ResolvedSchema:
    sid = uuid4()
    return ResolvedSchema(
        project_id="proj-1",
        schema_version=schema_version,
        allow_free_edges=allow_free_edges,
        edge_types=[
            EdgeType(edge_type_id=uuid4(), schema_id=sid, code="disciple_of", label="Disciple Of"),
            EdgeType(edge_type_id=uuid4(), schema_id=sid, code="pursues", label="Pursues"),
        ],
        fact_types=[
            FactType(fact_type_id=uuid4(), schema_id=sid, code="realm", label="Realm"),
        ],
        node_kinds=[
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=sid, kind_code="cultivator", strength="required"),
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=sid, kind_code="sect", strength="optional"),
        ],
    )


def test_projection_maps_codes_and_version():
    d = resolved_to_extraction_dict(_resolved(allow_free_edges=False))
    assert d["entity_kinds"] == ["cultivator", "sect"]
    assert d["edge_predicates"] == ["disciple_of", "pursues"]
    assert d["fact_types"] == ["realm"]
    assert d["event_kinds"] == []  # not modeled — stays permissive
    assert d["schema_version"] == 7
    assert d["label"] == "proj-1@v7"


def test_authoritative_carries_real_allow_free_edges():
    closed = resolved_to_extraction_dict(_resolved(allow_free_edges=False), advisory=False)
    assert closed["allow_free_edges"] is False
    open_ = resolved_to_extraction_dict(_resolved(allow_free_edges=True), advisory=False)
    assert open_["allow_free_edges"] is True


def test_advisory_forces_free_edges():
    """The SDK-prompt posture: a closed schema is projected as advisory so the SDK
    injects the vocab as a hint but never pre-drops (the writer stays the sole
    enforce+park point)."""
    d = resolved_to_extraction_dict(_resolved(allow_free_edges=False), advisory=True)
    assert d["allow_free_edges"] is True
    # vocab still carried for the prompt hint
    assert d["edge_predicates"] == ["disciple_of", "pursues"]


def test_build_extraction_schema_roundtrips():
    schema = build_extraction_schema(_resolved(allow_free_edges=False))
    assert schema.entity_kinds == ("cultivator", "sect")
    assert schema.edge_predicates == ("disciple_of", "pursues")
    assert schema.fact_types == ("realm",)
    assert schema.event_kinds == ()
    assert schema.allow_free_edges is False
    assert schema.schema_version == 7
    assert schema.label == "proj-1@v7"

    advisory = build_extraction_schema(_resolved(allow_free_edges=False), advisory=True)
    assert advisory.allow_free_edges is True
