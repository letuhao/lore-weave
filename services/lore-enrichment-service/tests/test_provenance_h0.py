"""H0 chokepoint tests (RAID C11) — EVERY generated fact is born NOT-canon.

The load-bearing cycle invariant: a fact with no origin / provenance /
confidence<1.0 / pending_validation MUST be impossible to construct. These tests
assert the chokepoint rejects every attempt to mark enriched lore as canon, and
that the happy path always emits a fully H0-tagged fact.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.generation.provenance import (
    ENRICHED_ORIGIN,
    GENERATION_CONFIDENCE,
    EnrichedFact,
    H0OriginError,
    SourceRef,
    build_provenance,
    make_enriched_fact,
)


def _ref(score: float = 0.8) -> SourceRef:
    return SourceRef(
        corpus_id="11111111-1111-1111-1111-111111111111",
        chunk_id="22222222-2222-2222-2222-222222222222",
        chunk_index=3,
        score=score,
    )


def _make(**overrides):
    """Build a fact via the factory with sane H0-valid defaults, overridable."""
    kwargs = dict(
        user_id="u1",
        project_id="p1",
        entity_kind="location",
        canonical_name="蓬萊",
        target_ref="loc:penglai",
        dimension="历史",
        content="蓬萊乃东海之上仙岛，自上古即为修真之地。",
        technique="retrieval",
        source_refs=[_ref()],
        model_ref="model-ref-uuid",
    )
    kwargs.update(overrides)
    return make_enriched_fact(**kwargs)


# ── happy path: every fact carries the full H0 marker set ────────────────────


def test_factory_produces_fully_h0_tagged_fact():
    fact = _make()
    assert fact.origin == "enriched:retrieval"
    assert fact.origin.startswith(ENRICHED_ORIGIN)
    assert fact.technique == "retrieval"
    assert 0.0 < fact.confidence < 1.0
    assert fact.confidence == GENERATION_CONFIDENCE
    assert fact.pending_validation is True
    assert fact.review_status == "proposed"
    assert fact.provenance  # non-empty
    assert fact.provenance["technique"] == "retrieval"
    assert fact.provenance["model_ref"] == "model-ref-uuid"
    assert fact.source_refs and fact.source_refs[0].corpus_id


def test_bare_origin_form_is_accepted_but_still_enriched():
    fact = _make(qualified_origin=False)
    assert fact.origin == ENRICHED_ORIGIN
    assert fact.origin != "glossary"


def test_provenance_records_grounding_refs_not_model_name():
    fact = _make()
    grounding = fact.provenance["grounding_ref_ids"]
    assert len(grounding) == 1
    assert grounding[0]["corpus_id"] == "11111111-1111-1111-1111-111111111111"
    # model_ref is a ref, never a literal model name
    assert fact.provenance["model_ref"] == "model-ref-uuid"


# ── property-style: EVERY fact over a batch is H0-tagged ─────────────────────


@pytest.mark.parametrize("technique", ["template", "retrieval", "fabrication", "recook"])
@pytest.mark.parametrize("dimension", ["历史", "地理", "文化", "features", "inhabitants"])
def test_every_generated_fact_is_quarantined(technique, dimension):
    fact = _make(technique=technique, dimension=dimension)
    # H0 property: non-null enriched origin, non-empty provenance, conf<1.0,
    # pending, non-empty source_refs — for EVERY technique/dimension combo.
    assert fact.origin in (ENRICHED_ORIGIN, f"{ENRICHED_ORIGIN}:{technique}")
    assert fact.origin != "glossary"
    assert fact.provenance
    assert 0.0 < fact.confidence < 1.0
    assert fact.pending_validation is True
    assert len(fact.source_refs) >= 1


# ── negative: constructing without H0 markers RAISES ─────────────────────────


def _assert_origin_rejected(origin: str) -> None:
    """A bad origin must raise. pydantic v2 wraps the field-validator's
    :class:`H0OriginError` in a :class:`ValidationError`; assert the wrapped
    failure is the H0 origin rule (cause type + message), so we prove the H0
    chokepoint fired — not some unrelated validation error."""
    with pytest.raises(ValidationError) as exc_info:
        EnrichedFact(
            user_id="u",
            project_id="p",
            entity_kind="location",
            canonical_name="蓬萊",
            dimension="历史",
            content="x",
            origin=origin,
            technique="retrieval",
            confidence=0.3,
            provenance={"technique": "retrieval"},
            source_refs=[_ref()],
        )
    # The H0 origin validator is the failing rule (message mentions H0 + origin).
    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("origin",) and "H0" in e["msg"] for e in errors
    ), errors


def test_origin_glossary_rejected():
    _assert_origin_rejected("glossary")  # authored canon — forbidden


def test_origin_canon_qualified_rejected():
    _assert_origin_rejected("glossary:something")


def test_origin_blank_rejected():
    # A blank origin is rejected (by min_length before the H0 validator even
    # runs) — either way an untagged-origin fact cannot be constructed.
    with pytest.raises(ValidationError) as exc_info:
        EnrichedFact(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="蓬萊", dimension="历史", content="x",
            origin="", technique="retrieval", confidence=0.3,
            provenance={"t": 1}, source_refs=[_ref()],
        )
    assert any(e["loc"] == ("origin",) for e in exc_info.value.errors())


def test_origin_arbitrary_word_rejected():
    # Not 'enriched' and not 'enriched:<x>' → rejected (no smuggling other origins)
    _assert_origin_rejected("canon")


def test_h0_origin_error_is_a_value_error():
    # The chokepoint type is a ValueError subclass so pydantic captures it as a
    # field-validation failure (keeping the model the single enforcement point).
    assert issubclass(H0OriginError, ValueError)


@pytest.mark.parametrize("bad_conf", [1.0, 1.5, 1.0001, 0.0, -0.1])
def test_confidence_must_be_strictly_between_0_and_1(bad_conf):
    with pytest.raises(ValidationError):
        _make(confidence=bad_conf)


def test_confidence_just_below_one_is_allowed():
    fact = _make(confidence=0.999)
    assert fact.confidence == 0.999


def test_empty_provenance_rejected():
    with pytest.raises(ValidationError):
        EnrichedFact(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="蓬萊", dimension="历史", content="x",
            origin="enriched", technique="retrieval", confidence=0.3,
            provenance={},  # empty → unprovenanced
            source_refs=[_ref()],
        )


def test_empty_source_refs_rejected():
    with pytest.raises(ValidationError):
        EnrichedFact(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="蓬萊", dimension="历史", content="x",
            origin="enriched", technique="retrieval", confidence=0.3,
            provenance={"t": 1}, source_refs=[],  # no source → unprovenanced
        )


def test_pending_validation_false_rejected():
    with pytest.raises(ValidationError):
        EnrichedFact(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="蓬萊", dimension="历史", content="x",
            origin="enriched", technique="retrieval", confidence=0.3,
            provenance={"t": 1}, source_refs=[_ref()],
            pending_validation=False,  # un-quarantine — forbidden
        )


def test_review_status_non_proposed_rejected():
    with pytest.raises(ValidationError):
        EnrichedFact(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="蓬萊", dimension="历史", content="x",
            origin="enriched", technique="retrieval", confidence=0.3,
            provenance={"t": 1}, source_refs=[_ref()],
            review_status="promoted",  # cannot start promoted (canon)
        )


def test_empty_content_rejected():
    with pytest.raises(ValidationError):
        _make(content="")


def test_fact_is_frozen():
    fact = _make()
    with pytest.raises(ValidationError):
        fact.confidence = 0.99  # type: ignore[misc]


def test_factory_default_confidence_below_one():
    # The default generation confidence must itself satisfy H0 (< 1.0, > 0).
    assert 0.0 < GENERATION_CONFIDENCE < 1.0


def test_model_construct_escape_hatch_is_forbidden():
    # ADVERSARY: pydantic's model_construct() skips validators and could mint a
    # canon-looking fact (origin='glossary', confidence=1.0). H0 forbids it —
    # the only path to a fact is the validated one.
    with pytest.raises(H0OriginError):
        EnrichedFact.model_construct(origin="glossary", confidence=1.0)


def test_validated_construction_still_works_after_closing_hatch():
    # Closing model_construct must NOT break the normal validated constructor.
    fact = _make()
    assert fact.origin == "enriched:retrieval"
    assert 0 < fact.confidence < 1.0


def test_model_copy_update_to_canon_is_rejected():
    # ADVERSARY: pydantic's model_copy(update=...) skips validators by default.
    # An update that flips origin/confidence to canon must be re-validated → raise.
    fact = _make()
    with pytest.raises((H0OriginError, ValidationError)):
        fact.model_copy(update={"origin": "glossary", "confidence": 1.0})


def test_model_copy_confidence_one_rejected():
    fact = _make()
    with pytest.raises(ValidationError):
        fact.model_copy(update={"confidence": 1.0})


def test_model_copy_benign_update_revalidates_and_succeeds():
    # A copy that keeps H0 intact still works (e.g. tweak content), proving the
    # revalidation does not break legitimate derivation.
    fact = _make()
    copy = fact.model_copy(update={"content": "蓬萊别有洞天，云海苍茫。"})
    assert copy.content == "蓬萊别有洞天，云海苍茫。"
    assert copy.origin == "enriched:retrieval"
    assert 0 < copy.confidence < 1.0
    assert copy.pending_validation is True


# ── build_provenance ─────────────────────────────────────────────────────────


def test_build_provenance_is_non_empty_and_carries_refs():
    prov = build_provenance(
        technique="retrieval", model_ref="ref-x", source_refs=[_ref(0.9)]
    )
    assert prov["technique"] == "retrieval"
    assert prov["model_ref"] == "ref-x"
    assert prov["grounding_ref_ids"][0]["score"] == 0.9
    assert "generated_at" in prov


def test_build_provenance_allows_none_model_ref_but_records_ref_only():
    prov = build_provenance(technique="template", model_ref=None, source_refs=[_ref()])
    assert prov["model_ref"] is None  # a ref slot, never a model NAME
    assert prov["technique"] == "template"
