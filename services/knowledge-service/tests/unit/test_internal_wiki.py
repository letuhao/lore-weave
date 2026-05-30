"""C5 (D4-03) — Unit tests for the internal wiki-neighborhood
source_type derivation. These pin the H0 invariant: enriched material
is never silently classed as canon.

The endpoint itself is exercised end-to-end by the cross-service
live-smoke in scripts/raid/verify-cycle-5.sh; here we lock the pure
derivation logic that decides the source_type tags.
"""

from __future__ import annotations

from app.routers.internal_wiki import _derive_source_type, _entity_source_type


class TestDeriveRelationSourceType:
    def test_validated_full_confidence_is_glossary_canon(self):
        assert (
            _derive_source_type(pending_validation=False, confidence=1.0)
            == "glossary"
        )

    def test_pending_validation_is_enriched(self):
        # Even at full confidence, a pending edge is not yet canon.
        assert (
            _derive_source_type(pending_validation=True, confidence=1.0)
            == "enriched"
        )

    def test_sub_canon_confidence_is_enriched(self):
        assert (
            _derive_source_type(pending_validation=False, confidence=0.9)
            == "enriched"
        )

    def test_pending_and_low_confidence_is_enriched(self):
        assert (
            _derive_source_type(pending_validation=True, confidence=0.5)
            == "enriched"
        )


class TestEntitySourceType:
    def test_glossary_marker_is_canon(self):
        assert _entity_source_type(["glossary"]) == "glossary"

    def test_enriched_marker_is_enriched(self):
        assert _entity_source_type(["enriched"]) == "enriched"

    def test_enriched_technique_marker_is_enriched(self):
        assert _entity_source_type(["enriched:template"]) == "enriched"

    def test_mixed_markers_prefer_enriched(self):
        # H0: if an entity carries ANY enriched marker, it is
        # enriched-origin — never silently promoted to canon by the
        # presence of a 'glossary' marker too.
        assert _entity_source_type(["glossary", "enriched:retrieval"]) == "enriched"

    def test_empty_markers_default_to_glossary(self):
        # An entity with no source_types at all is a legacy/plain node;
        # treat it as glossary canon (the wiki feature's prior default).
        assert _entity_source_type([]) == "glossary"

    def test_unknown_only_marker_is_quarantined(self):
        # A non-glossary, non-enriched marker is unknown-origin → fail
        # safe to enriched rather than silently canon.
        assert _entity_source_type(["speculative"]) == "enriched"
