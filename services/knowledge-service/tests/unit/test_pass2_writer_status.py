"""A2-S1b unit tests — pass2_writer status_effects consumption.

Mocks the Neo4j repos (merge_event, merge_entity_status, add_evidence,
resolve_or_merge_entity, upsert_extraction_source, upsert_for_chapter) to
verify, without a live database:

  - An event's status_effects → merge_entity_status at the event's event_order,
    with the entity_ref resolved via the chapter-local entity map.
  - event_order=None (no hierarchy / legacy / chat) → status SKIPPED (M2).
  - Unresolved entity_ref (no chapter-map / anchor match) → status SKIPPED,
    NO autocreate.
  - Kind-ambiguous entity_ref (two same-fold entities) → status SKIPPED.

The retract-idempotency invariant (status evidence returns to 1 on re-extract
with no dup node) is proven in the live integration smoke + the EntityStatus
repo integration suite (A2-S1a) — it depends on real MERGE/EVIDENCED_BY
semantics that mocks can't exercise.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate, StatusEffect
from app.extraction.hierarchy_writer import HierarchyPaths
from app.extraction.pass2_writer import write_pass2_extraction
from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"
JOB_ID = "test-job-001"
_PATCH_BASE = "app.extraction.pass2_writer"


def _fake_session() -> Any:
    return MagicMock()


def _entity(name: str, kind: str = "person", confidence: float = 0.9) -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=confidence,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _event_with_status(
    name: str, participants: list[str],
    status_effects: list[StatusEffect],
    confidence: float = 0.9,
) -> LLMEventCandidate:
    return LLMEventCandidate(
        name=name, kind="death", participants=participants,
        participant_ids=[f"eid-{p.lower()}" for p in participants],
        location=None, time_cue=None, event_date=None,
        summary="Something fatal happened.", confidence=confidence,
        event_id=f"evid-{name.lower()}", status_effects=status_effects,
    )


def _result(node_id: str) -> MagicMock:
    r = MagicMock()
    r.id = node_id
    return r


def _evidence(created: bool = True) -> MagicMock:
    r = MagicMock()
    r.created = created
    return r


def _hierarchy(chapter_index: int = 2) -> HierarchyPaths:
    return HierarchyPaths(
        book_id="bk-1", book_path="book", book_title="Demo",
        part_id="pt-1", part_path="book/part-1", part_index=1, part_title=None,
        chapter_id="ch-uuid-1", chapter_path="book/part-1/chapter-2",
        chapter_index=chapter_index, chapter_title=None, scenes=[],
    )


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity_status", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_status_written_at_event_order(
    mock_source, mock_resolve, mock_merge_event, mock_evidence,
    mock_merge_status, mock_hierarchy,
):
    """An event's status_effects writes an :EntityStatus at the event's
    event_order, with entity_ref resolved via the chapter entity map."""
    mock_source.return_value = _result("src-1")
    mock_resolve.return_value = _result("eid-kai")
    mock_merge_event.return_value = _result("evid-kai falls")
    mock_evidence.return_value = _evidence(True)
    mock_merge_status.return_value = _result("status-1")

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-uuid-1", job_id=JOB_ID,
        entities=[_entity("Kai")],
        events=[_event_with_status(
            "Kai falls", ["Kai"],
            [StatusEffect(entity_ref="Kai", status="gone")],
        )],
        hierarchy_paths=_hierarchy(chapter_index=2),
    )

    assert result.statuses_merged == 1
    mock_merge_status.assert_awaited_once()
    kwargs = mock_merge_status.call_args.kwargs
    assert kwargs["entity_id"] == "eid-kai"
    assert kwargs["status"] == "gone"
    # event_order = chapter_index(2) * stride + within-chapter idx(0)
    assert kwargs["from_order"] == 2 * EVENT_ORDER_CHAPTER_STRIDE
    assert kwargs["source_chapter"] == "ch-uuid-1"
    assert kwargs["provenance"] == "human_authored"
    # add_evidence called for the EntityStatus (label arg) too.
    labels = [c.kwargs.get("target_label") for c in mock_evidence.call_args_list]
    assert "EntityStatus" in labels


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.merge_entity_status", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_status_skipped_when_event_order_none(
    mock_source, mock_resolve, mock_merge_event, mock_evidence, mock_merge_status,
):
    """No hierarchy_paths → event_order is None → status_effects skipped
    (M2: a positionless status the packer can't gate on)."""
    mock_source.return_value = _result("src-1")
    mock_resolve.return_value = _result("eid-kai")
    mock_merge_event.return_value = _result("evid-kai falls")
    mock_evidence.return_value = _evidence(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-uuid-1", job_id=JOB_ID,
        entities=[_entity("Kai")],
        events=[_event_with_status(
            "Kai falls", ["Kai"],
            [StatusEffect(entity_ref="Kai", status="gone")],
        )],
        # no hierarchy_paths → event_order None
    )

    assert result.statuses_merged == 0
    mock_merge_status.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity_status", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_status_skipped_when_entity_unresolved(
    mock_source, mock_resolve, mock_merge_event, mock_evidence,
    mock_merge_status, mock_hierarchy,
):
    """A status_effect whose entity_ref matches no extracted entity and no
    anchor is SKIPPED — never autocreated."""
    mock_source.return_value = _result("src-1")
    mock_resolve.return_value = _result("eid-kai")
    mock_merge_event.return_value = _result("evid-kai falls")
    mock_evidence.return_value = _evidence(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-uuid-1", job_id=JOB_ID,
        entities=[_entity("Kai")],
        events=[_event_with_status(
            "Someone falls", ["Kai"],
            [StatusEffect(entity_ref="Ghost", status="gone")],  # not an entity
        )],
        hierarchy_paths=_hierarchy(),
    )

    assert result.statuses_merged == 0
    mock_merge_status.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_entity_status", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_status_skipped_when_kind_ambiguous(
    mock_source, mock_resolve, mock_merge_event, mock_evidence,
    mock_merge_status, mock_hierarchy,
):
    """Two entities sharing a fold (same name, different kind) make the
    chapter-map candidate ambiguous → status SKIPPED (don't guess)."""
    mock_source.return_value = _result("src-1")
    # Two entities resolve to distinct ids but share the fold "phoenix".
    mock_resolve.side_effect = [_result("eid-phoenix-person"), _result("eid-phoenix-place")]
    mock_merge_event.return_value = _result("evid-fall")
    mock_evidence.return_value = _evidence(True)

    result = await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-uuid-1", job_id=JOB_ID,
        entities=[_entity("Phoenix", kind="person"), _entity("Phoenix", kind="place")],
        events=[_event_with_status(
            "Phoenix falls", ["Phoenix"],
            [StatusEffect(entity_ref="Phoenix", status="gone")],
        )],
        hierarchy_paths=_hierarchy(),
    )

    assert result.statuses_merged == 0
    mock_merge_status.assert_not_awaited()
