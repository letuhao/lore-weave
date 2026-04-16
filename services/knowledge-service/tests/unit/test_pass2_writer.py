"""Unit tests for K17.8 — Pass 2 writer.

Mocks K11 Neo4j repos to test write_pass2_extraction logic without
a live database. Validates:
  - Empty input → source upserted, zero counters
  - Entities merged + evidence edges created
  - Relations skip unresolvable endpoints
  - Relations skip endpoints not in merged entity set
  - Events merged + evidence edges
  - Facts merged + evidence edges
  - Injection defense applied to persisted text
  - Full pipeline with all candidate types
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_event_extractor import LLMEventCandidate
from app.extraction.llm_fact_extractor import LLMFactCandidate
from app.extraction.llm_relation_extractor import LLMRelationCandidate
from app.extraction.pass2_writer import Pass2WriteResult, write_pass2_extraction


# ── Helpers ─────────────────────────────────────────────────────

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"
JOB_ID = "test-job-001"


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
        subject_id=subject_id or f"eid-{subject.lower()}",
        object_id=object_id or f"eid-{obj.lower()}",
        polarity="affirm", modality="asserted",
        confidence=confidence, relation_id=f"rid-{subject}-{predicate}-{obj}",
    )


def _event(
    name: str, participants: list[str],
    participant_ids: list[str | None] | None = None,
    confidence: float = 0.9,
) -> LLMEventCandidate:
    return LLMEventCandidate(
        name=name, kind="action", participants=participants,
        participant_ids=participant_ids or [f"eid-{p.lower()}" for p in participants],
        location=None, time_cue=None, summary="Something happened.",
        confidence=confidence, event_id=f"evid-{name.lower()}",
    )


def _fact(
    content: str, type: str = "description",
    subject: str | None = None, subject_id: str | None = None,
    confidence: float = 0.9,
) -> LLMFactCandidate:
    return LLMFactCandidate(
        content=content, type=type, subject=subject, subject_id=subject_id,
        polarity="affirm", modality="asserted",
        confidence=confidence, fact_id=f"fid-{content[:20].lower()}",
    )


def _make_entity_result(entity_id: str) -> MagicMock:
    result = MagicMock()
    result.id = entity_id
    return result


def _make_evidence_result(created: bool = True) -> MagicMock:
    result = MagicMock()
    result.created = created
    return result


def _make_event_result(event_id: str) -> MagicMock:
    result = MagicMock()
    result.id = event_id
    return result


def _make_fact_result(fact_id: str) -> MagicMock:
    result = MagicMock()
    result.id = fact_id
    return result


def _make_source_result(source_id: str = "src-001") -> MagicMock:
    result = MagicMock()
    result.id = source_id
    return result


_PATCH_BASE = "app.extraction.pass2_writer"


# ── Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_empty_input_upserts_source(mock_upsert_source):
    """No candidates → source upserted, all counters zero."""
    mock_upsert_source.return_value = _make_source_result()

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
    )

    assert result.source_id == "src-001"
    assert result.entities_merged == 0
    assert result.relations_created == 0
    assert result.events_merged == 0
    assert result.facts_merged == 0
    mock_upsert_source.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_entities_merged_with_evidence(
    mock_upsert_source, mock_merge, mock_evidence,
):
    """Entities are merged and evidence edges created."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-kai"),
        _make_entity_result("eid-zhao"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai"), _entity("Zhao")],
    )

    assert result.entities_merged == 2
    assert result.evidence_edges == 2
    assert mock_merge.call_count == 2


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_relations_created_when_endpoints_merged(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Relations created when both endpoints are in merged entity set."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.side_effect = [
        _make_entity_result("eid-kai"),
        _make_entity_result("eid-zhao"),
    ]
    mock_evidence.return_value = _make_evidence_result(True)
    mock_create_rel.return_value = MagicMock()  # non-None = success

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai"), _entity("Zhao")],
        relations=[_relation("Kai", "trusts", "Zhao",
                             subject_id="eid-kai", object_id="eid-zhao")],
    )

    assert result.relations_created == 1
    assert result.skipped_missing_endpoint == 0


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_relations_skip_unresolvable_endpoints(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Relations with None endpoints are skipped."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-kai")
    mock_evidence.return_value = _make_evidence_result(True)

    rel = _relation("Kai", "trusts", "Unknown",
                     subject_id="eid-kai", object_id=None)
    # Force None object_id
    rel.object_id = None

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai")],
        relations=[rel],
    )

    assert result.relations_created == 0
    assert result.skipped_missing_endpoint == 1
    mock_create_rel.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_relations_skip_endpoints_not_in_merged_set(
    mock_upsert_source, mock_merge, mock_evidence, mock_create_rel,
):
    """Relations whose endpoint IDs weren't actually merged are skipped."""
    mock_upsert_source.return_value = _make_source_result()
    # Only Kai is merged — Zhao's ID won't be in the merged set
    mock_merge.return_value = _make_entity_result("eid-kai")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai")],
        relations=[_relation("Kai", "trusts", "Zhao",
                             subject_id="eid-kai", object_id="eid-zhao")],
    )

    assert result.relations_created == 0
    assert result.skipped_missing_endpoint == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_events_merged_with_evidence(
    mock_upsert_source, mock_merge_event, mock_evidence,
):
    """Events are merged and evidence edges created."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge_event.return_value = _make_event_result("evid-battle")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        events=[_event("Battle at Gate", ["Kai"])],
    )

    assert result.events_merged == 1
    assert result.evidence_edges == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_fact", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_facts_merged_with_evidence(
    mock_upsert_source, mock_merge_fact, mock_evidence,
):
    """Facts are merged and evidence edges created."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge_fact.return_value = _make_fact_result("fid-brave")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        facts=[_fact("Kai is brave.", "attribute")],
    )

    assert result.facts_merged == 1
    assert result.evidence_edges == 1


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.neutralize_injection")
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_injection_defense_applied(
    mock_upsert_source, mock_merge, mock_evidence, mock_sanitize,
):
    """Entity names go through neutralize_injection before merge."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge.return_value = _make_entity_result("eid-kai")
    mock_evidence.return_value = _make_evidence_result(True)
    mock_sanitize.return_value = ("Kai", False)

    await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai")],
    )

    mock_sanitize.assert_called()
    # First call should be for the entity name
    assert mock_sanitize.call_args_list[0][0][0] == "Kai"


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_fact", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.create_relation", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_full_pipeline_all_candidate_types(
    mock_upsert_source, mock_merge_entity, mock_create_rel,
    mock_merge_event, mock_merge_fact, mock_evidence,
):
    """All four candidate types persisted in one call."""
    mock_upsert_source.return_value = _make_source_result()
    mock_merge_entity.side_effect = [
        _make_entity_result("eid-kai"),
        _make_entity_result("eid-zhao"),
    ]
    mock_create_rel.return_value = MagicMock()
    mock_merge_event.return_value = _make_event_result("evid-battle")
    mock_merge_fact.return_value = _make_fact_result("fid-brave")
    mock_evidence.return_value = _make_evidence_result(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id=JOB_ID,
        entities=[_entity("Kai"), _entity("Zhao")],
        relations=[_relation("Kai", "trusts", "Zhao",
                             subject_id="eid-kai", object_id="eid-zhao")],
        events=[_event("Battle", ["Kai"])],
        facts=[_fact("Kai is brave.")],
    )

    assert result.entities_merged == 2
    assert result.relations_created == 1
    assert result.events_merged == 1
    assert result.facts_merged == 1
    assert result.evidence_edges == 4  # 2 entities + 1 event + 1 fact
