"""Cycle 73e — unit tests for Pass2 writer autocreate (Tier A + Tier B).

Covers the four resolution tiers added in cycle 73e:

  - **Tier A.1** chapter-local name repair (free, always-on)
  - **Tier A.2** anchor pre-check repair (free, always-on)
  - **Tier B**   env-gated MERGE of a new :Entity with
                 ``auto_created=True``, ``kind="concept"``
  - **Cascade-skip** when all tiers exhaust

Plus regression-lock for the Pass2WriteResult new fields
(``entities_autocreated``, ``endpoints_repaired_by_name``) and the
per-outcome metric counter.

Mocks the same surfaces as ``test_pass2_writer.py`` for consistency.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from app.extraction.anchor_loader import Anchor
from app.extraction.pass2_writer import (
    _is_noise_subject,
    write_pass2_extraction,
)
from app.metrics import knowledge_extraction_writer_autocreate_total

# /review-impl r2 M3 fold: metric counters are process-global; under
# pytest-xdist parallel workers they accumulate across processes and
# delta assertions flake. Group all cycle-73e writer-autocreate metric
# tests onto a single xdist worker.
pytestmark = pytest.mark.xdist_group("c73e-writer-autocreate-metrics")


# ── Helpers (mirror test_pass2_writer.py shapes) ───────────────────


USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"
JOB_ID = "test-job-001"

_PATCH_BASE = "app.extraction.pass2_writer"


def _fake_session() -> Any:
    return MagicMock()


def _entity(
    name: str, kind: str = "person", confidence: float = 0.9,
    canonical_id: str | None = None,
) -> LLMEntityCandidate:
    cid = canonical_id or f"eid-{name.lower()}"
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=confidence,
        canonical_name=name.lower(), canonical_id=cid,
    )


def _relation(
    subject: str, predicate: str, obj: str,
    subject_id: str | None = None, object_id: str | None = None,
    confidence: float = 0.9,
) -> LLMRelationCandidate:
    return LLMRelationCandidate(
        subject=subject, predicate=predicate, object=obj,
        subject_id=subject_id,
        object_id=object_id,
        polarity="affirm", modality="asserted",
        confidence=confidence, relation_id=f"rid-{subject}-{predicate}-{obj}",
    )


def _make_entity_result(entity_id: str) -> MagicMock:
    result = MagicMock()
    result.id = entity_id
    return result


def _make_evidence_result(created: bool = True) -> MagicMock:
    result = MagicMock()
    result.created = created
    return result


def _make_source_result(source_id: str = "src-001") -> MagicMock:
    result = MagicMock()
    result.id = source_id
    return result


def _counter_value(role: str, outcome: str) -> float:
    """Snapshot the counter value for a (role, outcome) label pair."""
    return knowledge_extraction_writer_autocreate_total.labels(
        role=role, outcome=outcome,
    )._value.get()


# ── _is_noise_subject heuristic (H2 fold) ─────────────────────────


def test_is_noise_subject_short_name_is_not_noise():
    assert _is_noise_subject("Alice") is False
    assert _is_noise_subject("Sir William") is False
    assert _is_noise_subject("Bụt") is False  # VN single-word
    assert _is_noise_subject("白发魔女") is False  # CJK 4-char compound


def test_is_noise_subject_long_compound_english_is_noise():
    """Compound English subjects from cycle 73c findings."""
    assert _is_noise_subject("fancy words and refined speech") is True
    assert _is_noise_subject("home peace and comfort") is True


def test_is_noise_subject_long_cjk_is_noise_via_char_budget():
    """CJK doesn't split on whitespace — word-count is always 1.
    Char-budget catches long CJK strings (cycle 73e H2 fold)."""
    # 80-character CJK string
    long_cjk = "齐天大圣孙悟空" * 12
    assert _is_noise_subject(long_cjk) is True


def test_is_noise_subject_empty_after_strip_is_noise():
    assert _is_noise_subject("") is True
    assert _is_noise_subject("   ") is True
    assert _is_noise_subject("，。、") is True  # CJK punctuation only


# ── Cycle 73e end-to-end writer tests ─────────────────────────────


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_autocreate_disabled_preserves_cascade_skip_behavior(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """autocreate_enabled=False (default) → unresolved endpoint
    cascade-skips as in pre-73e behaviour. Regression-lock that the
    env-gated path doesn't silently activate."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-alice")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Alice")],
        relations=[
            _relation(
                "Alice", "saw", "White Rabbit",
                subject_id="eid-alice", object_id=None,  # object unresolved
            ),
        ],
        # autocreate_enabled defaults False
    )

    assert result.relations_created == 0  # cascade-skipped
    assert result.skipped_missing_endpoint == 1
    assert result.entities_autocreated == 0
    assert result.endpoints_repaired_by_name == 0
    mock_create_rel.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_tier_a_repair_via_chapter_entity_map_unique_kind(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Tier A.1 — relation subject name matches a chapter-extracted
    entity but with no/different subject_id → repair via name map.
    Free, always-on (no env required)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-alice-real")
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_repair = _counter_value("subject", "tier_a_name_repair")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Alice")],
        relations=[
            _relation(
                "Alice", "saw", "Alice",  # both endpoints same name (self-rel)
                subject_id=None,  # unresolved
                object_id="eid-alice-real",  # already resolved
            ),
        ],
    )

    assert result.endpoints_repaired_by_name == 1  # subject repaired
    assert result.relations_created == 1
    assert result.entities_autocreated == 0
    assert _counter_value("subject", "tier_a_name_repair") == pre_repair + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_tier_a_repair_skipped_on_kind_ambiguity(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Two chapter entities with same canonical_name but different kinds
    → don't auto-repair (would pick wrong one). Don't autocreate either
    (would create a 3rd `concept` entity polluting worse)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-phoenix-person"),
        _make_entity_result("eid-phoenix-org"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)

    pre_ambiguous = _counter_value("subject", "kind_ambiguous")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[
            _entity("Phoenix", kind="person", canonical_id="eid-phoenix-person"),
            _entity("Phoenix", kind="organization", canonical_id="eid-phoenix-org"),
        ],
        relations=[
            _relation(
                "Phoenix", "founded", "Iron Gate",
                subject_id=None,  # unresolved
                object_id="eid-iron-gate",  # also unresolved (not in entity_list)
            ),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    # Subject: kind_ambiguous → no repair, no autocreate, cascade-skip
    assert result.endpoints_repaired_by_name == 0
    assert result.relations_created == 0
    assert _counter_value("subject", "kind_ambiguous") == pre_ambiguous + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_tier_a_anchor_hit_uses_repaired_by_anchor_outcome_not_autocreate(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Tier A.2 — relation subject matches a glossary anchor.
    Reuses anchor's canonical_id; bumps tier_a_anchor_repair (NOT
    tier_b_autocreated) so we can distinguish anchor-pre-existed
    from autocreate-minted in dashboards (H4 fold)."""
    mock_upsert_source.return_value = _make_source_result()
    # Tấm entity merge returns "eid-tam-real" so object_id below matches
    # and the object is pre-resolved (skips repair path). Only subject
    # ("Bụt") hits the anchor repair.
    mock_merge.return_value = _make_entity_result("eid-tam-real")
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_anchor = _counter_value("subject", "tier_a_anchor_repair")
    pre_auto = _counter_value("subject", "tier_b_autocreated")

    anchor = Anchor(
        canonical_id="canon-but-character",
        glossary_entity_id="glossary-but-uuid",
        name="Bụt",
        kind="character",
        aliases=("Phật",),
    )

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Tấm")],
        relations=[
            _relation(
                "Bụt", "helped", "Tấm",
                subject_id=None, object_id="eid-tam-real",
            ),
        ],
        anchors=[anchor],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.endpoints_repaired_by_name == 1  # subject repaired via anchor
    assert result.entities_autocreated == 0  # NOT autocreate (anchor existed)
    assert result.relations_created == 1
    assert _counter_value("subject", "tier_a_anchor_repair") == pre_anchor + 1
    assert _counter_value("subject", "tier_b_autocreated") == pre_auto
    # /review-impl r3 M3 fold: H3 fix calls add_evidence on Tier A.2 anchor
    # repair so anchor's evidence_count bumps. Without this assertion, a
    # regression that removes the H3 add_evidence call would silently pass.
    # 1 evidence for Tấm entity (Step 2) + 1 evidence for Bụt anchor (Tier A.2).
    assert result.evidence_edges == 2


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_tier_b_autocreate_creates_entity_with_auto_created_true(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Tier B — unresolved endpoint + autocreate enabled + budget OK →
    MERGE new entity with auto_created=True, kind=concept."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-tam"),  # entity merge for Tấm
        _make_entity_result("eid-but-auto"),  # autocreate for Bụt
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_auto = _counter_value("subject", "tier_b_autocreated")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Tấm")],
        relations=[
            _relation(
                "Bụt", "helped", "Tấm",
                subject_id=None, object_id="eid-tam",
            ),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.entities_autocreated == 1
    assert result.relations_created == 1
    assert _counter_value("subject", "tier_b_autocreated") == pre_auto + 1

    # Verify autocreate call passed kind=concept + auto_created=True
    autocreate_call = mock_merge.call_args_list[-1]
    assert autocreate_call.kwargs["kind"] == "concept"
    assert autocreate_call.kwargs["auto_created"] is True


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_tier_b_autocreate_confidence_floored_from_relation_confidence(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Tier B autocreate uses min(rel.confidence, 0.3) — never above
    0.3 cap, never 0.0 hardcoded (H3 fold). Cap exists so future legit
    extraction's higher confidence dominates via merge_entity's ON MATCH
    confidence ratchet."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-tam"),
        _make_entity_result("eid-but-auto"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Tấm")],
        relations=[
            _relation(
                "Bụt", "helped", "Tấm",
                subject_id=None, object_id="eid-tam",
                confidence=0.95,  # high — should be capped to 0.3
            ),
        ],
        autocreate_enabled=True,
    )

    autocreate_call = mock_merge.call_args_list[-1]
    assert autocreate_call.kwargs["confidence"] == 0.3, (
        "rel.confidence=0.95 must cap to 0.3 (signal of weakness)"
    )


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_noise_heuristic_skips_long_compound_subject(
    mock_upsert_source, mock_merge, mock_evidence,
):
    """English compound subject ("fancy words and refined speech") →
    noise_skipped outcome, no autocreate."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-jo")
    mock_evidence.return_value = _make_evidence_result(True)

    pre_noise = _counter_value("subject", "noise_skipped")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Jo")],
        relations=[
            _relation(
                "fancy words and refined speech",
                "characterize",
                "Jo",
                subject_id=None, object_id="eid-jo",
            ),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.entities_autocreated == 0
    assert result.relations_created == 0  # cascade-skipped
    assert _counter_value("subject", "noise_skipped") == pre_noise + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_noise_heuristic_handles_cjk_long_string(
    mock_upsert_source, mock_merge, mock_evidence,
):
    """CJK long string (no whitespace splits) — char-budget catches it.
    Word-count alone would pass (always 1). H2 fold regression-lock."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-other")
    mock_evidence.return_value = _make_evidence_result(True)

    pre_noise = _counter_value("subject", "noise_skipped")

    long_cjk = "齐天大圣孙悟空" * 12  # 80 chars, 1 "word"
    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("其他", canonical_id="eid-other")],
        relations=[
            _relation(
                long_cjk, "象征", "其他",
                subject_id=None, object_id="eid-other",
            ),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.entities_autocreated == 0
    assert _counter_value("subject", "noise_skipped") == pre_noise + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_invalid_name_outcome_for_empty_canonical(
    mock_upsert_source, mock_merge, mock_evidence,
):
    """Relation subject canonicalizes to empty (e.g. CJK-only
    punctuation) → invalid_name outcome (M6 fold)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-other")
    mock_evidence.return_value = _make_evidence_result(True)

    pre_invalid = _counter_value("subject", "invalid_name")

    await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("其他", canonical_id="eid-other")],
        relations=[
            _relation(
                "，。、",  # CJK punctuation only — canonicalizes to empty
                "象征", "其他",
                subject_id=None, object_id="eid-other",
            ),
        ],
        autocreate_enabled=True,
    )

    assert _counter_value("subject", "invalid_name") == pre_invalid + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_autocreate_per_chapter_cap_exhausted(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """autocreate_max=2 + 4 unresolved relations → first 2 autocreate;
    subsequent 2 cap-exhaust + cascade-skip."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-base"),  # base entity
        _make_entity_result("eid-auto-1"),  # first autocreate
        _make_entity_result("eid-auto-2"),  # second autocreate
        # No more side_effects — if Tier B tries a 3rd, test fails loud
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_cap = _counter_value("subject", "cap_exhausted")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Base", canonical_id="eid-base")],
        relations=[
            _relation(f"Subj{i}", "relates", "Base",
                      subject_id=None, object_id="eid-base", confidence=0.5)
            for i in range(4)
        ],
        autocreate_enabled=True,
        autocreate_max=2,
    )

    assert result.entities_autocreated == 2  # exactly cap
    assert result.relations_created == 2  # first 2 succeed; last 2 skip
    assert _counter_value("subject", "cap_exhausted") >= pre_cap + 2


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_both_subject_and_object_need_autocreate_in_same_relation(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Single relation with BOTH endpoints unresolved → 2 autocreates
    + 1 relation persists. Per-endpoint counter bumps twice (L3 fold)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-subj-auto"),
        _make_entity_result("eid-obj-auto"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[],  # no chapter entities — both endpoints fall to Tier B
        relations=[
            _relation(
                "Unknown Subject", "interacts", "Unknown Object",
                subject_id=None, object_id=None,
            ),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.entities_autocreated == 2  # both endpoints autocreated
    assert result.endpoints_repaired_by_name == 0  # Tier A didn't fire
    assert result.relations_created == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_autocreate_failure_logs_warning_emits_error_outcome(
    mock_upsert_source, mock_merge, mock_evidence, caplog,
):
    """resolve_or_merge_entity raises during autocreate → cascade-skip
    + warning log + error metric (D9 + M3 fold). Failure does NOT
    escalate into orchestrator's retry budget."""
    import logging

    mock_upsert_source.return_value = _make_source_result()

    # First call: entity merge succeeds (Base entity).
    # Second call: autocreate for "BoomSubject" raises.
    mock_merge.side_effect = [
        _make_entity_result("eid-base"),
        RuntimeError("Neo4j contract violation in fake test"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)

    pre_error = _counter_value("subject", "error")

    with caplog.at_level(logging.WARNING, logger="app.extraction.pass2_writer"):
        result = await write_pass2_extraction(
            _fake_session(),
            user_id=USER_ID, project_id=PROJECT_ID,
            source_type="chapter", source_id="ch-1",
            job_id=JOB_ID,
            entities=[_entity("Base", canonical_id="eid-base")],
            relations=[
                _relation(
                    "BoomSubject", "boom", "Base",
                    subject_id=None, object_id="eid-base",
                ),
            ],
            autocreate_enabled=True,
            autocreate_max=10,
        )

    assert result.entities_autocreated == 0
    assert result.relations_created == 0
    assert _counter_value("subject", "error") == pre_error + 1
    warnings = [r for r in caplog.records if "autocreate failed" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_pass2_write_result_includes_new_fields(
    mock_upsert_source, mock_merge, mock_evidence,
):
    """Pass2WriteResult exposes entities_autocreated +
    endpoints_repaired_by_name. Regression-lock contract for callers
    (orchestrator + workers + future telemetry consumers)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-a")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Alice")],
    )

    # Fields exist (Pydantic enforces) + default to 0 when not used.
    assert result.entities_autocreated == 0
    assert result.endpoints_repaired_by_name == 0


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_cap_exhausted_high_conf_outcome_for_dropped_high_confidence_relation(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """When cap exhausted AND skipped relation's confidence > 0.8 →
    BOTH cap_exhausted AND cap_exhausted_high_conf outcomes (M4 fold —
    additive labels match eval driver semantics so dashboards can use
    cap_exhausted alone for total + high_conf as tuning subset)."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-base"),
        _make_entity_result("eid-auto-1"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_cap = _counter_value("subject", "cap_exhausted")
    pre_hc = _counter_value("subject", "cap_exhausted_high_conf")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Base", canonical_id="eid-base")],
        relations=[
            # First relation: low-conf, gets cap=1
            _relation("LowConfSubj", "rel", "Base",
                      subject_id=None, object_id="eid-base", confidence=0.5),
            # Second: HIGH-conf, cap already exhausted →
            # bumps BOTH cap_exhausted and cap_exhausted_high_conf
            _relation("HighConfSubj", "rel", "Base",
                      subject_id=None, object_id="eid-base", confidence=0.95),
        ],
        autocreate_enabled=True,
        autocreate_max=1,
    )

    assert result.entities_autocreated == 1
    # M4 fold: both labels bumped for the high-conf cap-exhausted case.
    assert _counter_value("subject", "cap_exhausted") == pre_cap + 1
    assert _counter_value("subject", "cap_exhausted_high_conf") == pre_hc + 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_self_reference_relation_subject_autocreate_then_object_tier_a_repair(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Self-reference relation `(Alice, loves, Alice)` with both endpoints
    unresolved + no chapter entities → subject autocreates Alice, object
    then hits Tier A.1 against the newly-added chapter map entry.
    Result: 1 autocreate + 1 tier_a_name_repair + relation persists.

    /review-impl r2 L3 fold — covers the intra-relation propagation case
    that previously had no regression-lock."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-alice-auto")
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    pre_auto = _counter_value("subject", "tier_b_autocreated")
    pre_repair = _counter_value("object", "tier_a_name_repair")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[],  # empty — both endpoints unresolved
        relations=[
            _relation("Alice", "loves", "Alice",
                      subject_id=None, object_id=None),
        ],
        autocreate_enabled=True,
        autocreate_max=10,
    )

    assert result.entities_autocreated == 1  # only subject autocreates
    assert result.endpoints_repaired_by_name == 1  # object repaired via tier_a
    assert result.relations_created == 1  # self-rel persists
    assert _counter_value("subject", "tier_b_autocreated") == pre_auto + 1
    assert _counter_value("object", "tier_a_name_repair") == pre_repair + 1
    # merge_entity should be called exactly ONCE — the second Alice
    # endpoint hits Tier A.1 (free, no Neo4j write).
    assert mock_merge.call_count == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_input_relation_object_id_not_mutated_when_repaired(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """/review-impl r2 H2 fold — verify resolved IDs are tracked in LOCAL
    variables, not by mutating the input ``LLMRelationCandidate``. The
    caller's ``relation_list`` must be unchanged after the write so
    retries don't inherit stale repaired IDs."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-alice")
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()

    rel = _relation(
        "Alice", "saw", "Alice",
        subject_id=None,   # will be Tier A.1 repaired
        object_id="eid-alice",
    )
    original_subject_id = rel.subject_id  # None
    original_object_id = rel.object_id     # "eid-alice"

    await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Alice", canonical_id="eid-alice")],
        relations=[rel],
        autocreate_enabled=False,
    )

    assert rel.subject_id == original_subject_id, (
        "writer must not mutate input relation's subject_id"
    )
    assert rel.object_id == original_object_id
    # /review-impl r3 L1 fold: strengthen by verifying create_relation
    # was called with the RESOLVED subject_id (not the unmutated None
    # from the input rel). Without this assertion, a regression where
    # the writer used rel.subject_id (None) for create_relation but
    # still left rel unmutated would PASS this test silently.
    mock_create_rel.assert_called_once()
    create_kwargs = mock_create_rel.call_args.kwargs
    assert create_kwargs["subject_id"] == "eid-alice", (
        "create_relation must receive the Tier A.1-resolved subject_id, "
        "not the original (None) rel.subject_id"
    )
    assert create_kwargs["object_id"] == "eid-alice"
