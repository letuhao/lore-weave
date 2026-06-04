"""C13 — Unit tests for the internal enrichment write-back router.

Pins the H0-critical pure logic that does NOT need a live Neo4j:
  * the deterministic node/edge ids (idempotent write-back / promote / retract);
  * the request-model H0 guard: a write-back fact can NEVER carry canon
    confidence (>= 1.0) — pydantic rejects it before any Neo4j write.

The full quarantine→promote→canon round-trip against a real Neo4j is exercised
by the cross-service live-smoke in scripts/raid/verify-cycle-13.sh.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.internal_enrichment import (
    EnrichedDimensionFact,
    EnrichedWritebackRequest,
    _enriched_edge_id,
    _enriched_node_id,
    _ENRICHMENT_ORIGIN,
)


class TestDeterministicIds:
    def test_node_id_is_deterministic_per_proposal_dimension(self):
        a = _enriched_node_id("p1", "历史")
        b = _enriched_node_id("p1", "历史")
        assert a == b  # idempotent write-back MERGEs the same node

    def test_node_id_differs_per_dimension(self):
        assert _enriched_node_id("p1", "历史") != _enriched_node_id("p1", "地理")

    def test_node_id_differs_per_proposal(self):
        assert _enriched_node_id("p1", "历史") != _enriched_node_id("p2", "历史")

    def test_node_and_edge_ids_disjoint(self):
        # A node id and its edge id must never collide.
        assert _enriched_node_id("p1", "历史") != _enriched_edge_id("p1", "历史")

    def test_ids_are_prefixed(self):
        assert _enriched_node_id("p1", "历史").startswith("enr_")
        assert _enriched_edge_id("p1", "历史").startswith("enre_")


class TestH0ConfidenceGuard:
    def test_fact_rejects_canon_confidence(self):
        # H0: an enriched dimension fact may never carry canon confidence (1.0).
        with pytest.raises(ValidationError):
            EnrichedDimensionFact(dimension="历史", content="x", confidence=1.0)

    def test_fact_rejects_super_canon_confidence(self):
        with pytest.raises(ValidationError):
            EnrichedDimensionFact(dimension="历史", content="x", confidence=1.5)

    def test_fact_rejects_zero_confidence(self):
        with pytest.raises(ValidationError):
            EnrichedDimensionFact(dimension="历史", content="x", confidence=0.0)

    def test_fact_accepts_sub_canon_confidence(self):
        f = EnrichedDimensionFact(dimension="历史", content="上古仙山", confidence=0.30)
        assert 0.0 < f.confidence < 1.0

    def test_writeback_request_requires_at_least_one_fact(self):
        import uuid

        with pytest.raises(ValidationError):
            EnrichedWritebackRequest(
                user_id=uuid.uuid4(),
                proposal_id=uuid.uuid4(),
                glossary_entity_id=uuid.uuid4(),
                canonical_name="蓬萊",
                entity_kind="location",
                technique="template",
                facts=[],
            )


def test_origin_marker_constant_is_enrichment():
    # The permanent origin marker must be 'enrichment' (never 'glossary').
    assert _ENRICHMENT_ORIGIN == "enrichment"
    assert _ENRICHMENT_ORIGIN != "glossary"
