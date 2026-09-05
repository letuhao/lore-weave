"""C13 — Unit tests for the internal enrichment write-back router.

Pins the H0-critical pure logic that does NOT need a live Neo4j:
  * the deterministic node/edge ids (idempotent write-back / promote / retract);
  * the request-model H0 guard: a write-back fact can NEVER carry canon
    confidence (>= 1.0) — pydantic rejects it before any Neo4j write.

The full quarantine→promote→canon round-trip against a real Neo4j is exercised
by the cross-service live-smoke in scripts/raid/verify-cycle-13.sh.
"""

from __future__ import annotations

import re

from app.db.cypher_dialect import render

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


# ── the Cypher invariants, after the queries moved (plan T17) ──────────


class TestEnrichmentCypherInvariants:
    """The write-back's safety properties live in the Cypher, and nothing asserted them.

    Every existing test above covers id derivation and confidence validation — the Python
    half. The half that decides whether enrichment can corrupt canon was only ever
    exercised against a live graph, which meant it was exercised almost never.

    These read the statements in `graph_repos/enrichment.py`. They are cheap, they need no
    database, and each one names a way canon could be damaged.
    """

    def test_on_match_never_touches_a_canon_anchors_provenance(self):
        """H0/FIX-2: a pre-existing canon anchor must stay EXACTLY as it is. If ON MATCH
        set `source_type`, `confidence` or `origin`, an enrichment write-back would relabel
        a genuine canon node as enriched — and the marker is what the reviewer trusts."""
        from app.db.graph_repos.enrichment import _UPSERT_ANCHOR_CYPHER as cypher

        # ⚠️ RESTATED 2026-08-22 (T70), because §10.1 merged the two branches: AGE has no
        # ON MATCH SET, so the query is now ONE unconditional SET whose expressions
        # degenerate correctly on create. The SAFETY PROPERTY is unchanged and is what this
        # asserts — it just cannot be read off a branch keyword any more.
        #
        # "ON MATCH must not touch it" is now "the assignment must be a coalesce", which is
        # the same guarantee expressed on the form that exists: coalesce keeps the STORED
        # value whenever there is one, so an existing canon anchor is never relabelled.
        for guarded in ("e.source_type", "e.confidence", "e.origin",
                        "e.pending_validation", "e.source_types"):
            field = guarded.split(".", 1)[1]
            assert re.search(rf"{re.escape(guarded)}\s*=\s*coalesce\({re.escape(guarded)}",
                             cypher), (
                f"{guarded} is assigned unconditionally — enrichment would overwrite what an "
                f"existing canon anchor claims about itself. It must be "
                f"coalesce({guarded}, ...) so the stored value wins."
            )
        # It may still bump the timestamp and BACK-FILL a missing glossary anchor.
        assert "e.updated_at" in cypher
        assert "coalesce(e.glossary_entity_id" in cypher

    def test_on_create_marks_the_node_as_enrichment(self):
        """The complement: when enrichment CREATES the anchor, the node must be born
        marked, so it is never indistinguishable from canon. A genuine glossary sync clears
        these on match, which is what promotion to canon actually means."""
        from app.db.graph_repos.enrichment import _UPSERT_ANCHOR_CYPHER as cypher

        # Same restatement as above: the create-side markers are now `coalesce(field, X)`,
        # which sets X exactly when the node is new and leaves it alone otherwise.
        assert "coalesce(e.origin, $origin)" in cypher
        assert "coalesce(e.pending_validation, true)" in cypher
        assert "coalesce(e.promoted_from_proposal_id" in cypher


    def test_an_enrichment_RE_RUN_replaces_its_own_output(self):
        """The complement of the anchor rule, and it had NO guard until T70.

        `_UPSERT_ANCHOR_CYPHER` must never overwrite a canon anchor, so every provenance
        field there is a `coalesce`. `_UPSERT_ENRICHED_FACT_CYPHER` is the opposite: an
        enrichment re-run REPLACES what it produced last time, which is why its old ON MATCH
        branch assigned `content`, `confidence` and `origin` outright.

        ⚠️ Found by a BITE that nothing caught. §10.1 merged the two branches into one
        unconditional SET, and the obvious way to do that — coalesce everything, as the
        anchor query legitimately does — would FREEZE every enriched fact at its first value:
        the re-run reports success, writes nothing, and the reviewer sees stale content with
        a fresh `updated_at`. Silent in exactly the direction that matters.
        """
        import re

        from app.db.graph_repos.enrichment import _UPSERT_ENRICHED_FACT_CYPHER as cypher

        for replaced in ("f.content", "f.confidence", "f.origin", "f.source_type"):
            assert re.search(rf"{re.escape(replaced)}\s*=\s*coalesce\(", cypher) is None, (
                f"{replaced} is coalesced — an enrichment re-run would leave the FIRST value "
                f"in place and report success. This field must be assigned unconditionally."
            )
        # And the identity/provenance half must still be create-only, or a re-run would
        # rewrite which proposal the fact came from.
        assert "coalesce(f.promoted_from_proposal_id" in cypher
        assert "coalesce(f.created_at" in cypher

    def test_the_stale_anchor_is_freed_only_from_a_DIFFERENT_node(self):
        """Null-before-claim. Without `stale.id <> $canon_id` the statement would strip the
        glossary anchor off the very node about to claim it — and the MERGE would then
        create a second one."""
        from app.db.graph_repos.enrichment import _FREE_STALE_GLOSSARY_ANCHOR_CYPHER as cypher

        assert "stale.id <> $canon_id" in cypher
        assert "stale.glossary_entity_id = NULL" in cypher

    def test_retract_is_soft_and_scoped_to_one_proposal(self):
        """A hard delete here would be unrecoverable, and an unscoped one would take canon
        with it. Both properties are in the Cypher and nowhere else."""
        from app.db.graph_repos.enrichment import _RETRACT_CYPHER as cypher

        assert "DELETE" not in cypher.upper(), "retract must be SOFT — set valid_until"
        assert "f.valid_until = datetime()" in render(cypher, "neo4j")
        assert "f.origin = $origin" in cypher
        assert "f.promoted_from_proposal_id = $proposal_id" in cypher

    def test_promote_retains_the_origin_marker(self):
        """Promotion makes a fact canon but must NOT erase how it got there — `origin`,
        `promoted_from_proposal_id` and `original_technique` stay so the provenance of an
        AI-suggested fact survives its approval."""
        from app.db.graph_repos.enrichment import _PROMOTE_CYPHER as cypher

        for erased in ("f.origin = null", "f.origin = NULL",
                       "f.promoted_from_proposal_id = null"):
            assert erased not in cypher, "promotion must not erase the enrichment marker"
        assert "f.pending_validation = false" in cypher
        assert "f.promoted_by = $promoted_by" in cypher

    def test_every_enrichment_statement_is_tenant_scoped(self):
        """None of these go through `run_write` — the anchor MERGE keys on `id`, so
        `$user_id` is a property rather than a filter and `assert_user_id_param` would pass
        for the wrong reason. The tenant scoping is therefore asserted here instead."""
        from app.db.graph_repos import enrichment as mod

        for name in ("_FREE_STALE_GLOSSARY_ANCHOR_CYPHER", "_UPSERT_ANCHOR_CYPHER",
                     "_UPSERT_ENRICHED_FACT_CYPHER", "_PROMOTE_CYPHER", "_RETRACT_CYPHER"):
            assert "$user_id" in getattr(mod, name), f"{name} has no tenant scoping at all"
