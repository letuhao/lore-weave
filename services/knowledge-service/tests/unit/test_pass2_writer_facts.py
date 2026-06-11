"""T2.1 unit tests — pass2_writer fact→subject linking.

Mocks the Neo4j repos to verify (without a live DB) that a fact links to its
subject entity via the SAME Tier-A name-repair status/relations use — NOT a plain
match on the extractor's pre-resolved `subject_id`. The name-repair regression test
(`test_fact_links_subject_via_name_repair`) is the one that would have caught
/review-impl HIGH-1: a stale extraction `subject_id` that no longer matches the
writer's merged id must still link via the subject NAME.

Decorator/arg order mirrors test_pass2_writer_status.py: the BOTTOM @patch
(upsert_extraction_source) is the FIRST positional arg.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from app.extraction.hierarchy_writer import HierarchyPaths
from app.extraction.pass2_writer import write_pass2_extraction
from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"
JOB_ID = "test-job-001"
_PATCH_BASE = "app.extraction.pass2_writer"


def _fake_session() -> Any:
    return MagicMock()


def _entity(name: str, kind: str = "person") -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _fact(content: str, subject: str | None, subject_id: str | None, ftype: str = "decision") -> LLMFactCandidate:
    return LLMFactCandidate(
        content=content, type=ftype, subject=subject, subject_id=subject_id,
        polarity="affirm", modality="asserted", confidence=0.9, fact_id=f"fid-{content[:6]}",
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


async def _run(mock_source, mock_resolve, mock_fact, mock_evidence, *, facts):
    mock_source.return_value = _result("src-1")
    mock_resolve.return_value = _result("eid-kai")  # entity "Kai" → merged id
    mock_fact.return_value = _result("fact-1")
    mock_evidence.return_value = _evidence(True)
    return await write_pass2_extraction(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-uuid-1", job_id=JOB_ID,
        entities=[_entity("Kai")],
        facts=facts,
        hierarchy_paths=_hierarchy(chapter_index=2),
    )


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_fact", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_fact_links_subject_via_name_repair(
    mock_source, mock_resolve, mock_event, mock_evidence, mock_fact, mock_hier,
):
    """/review-impl HIGH-1 regression: the extractor's `subject_id` is STALE (no
    longer matches the merged id), but the subject NAME "Kai" resolves via the
    chapter map → the fact still links. A plain id-match would have dropped it."""
    result = await _run(
        mock_source, mock_resolve, mock_fact, mock_evidence,
        facts=[_fact("broke the oath", subject="Kai", subject_id="STALE-EXTRACTION-ID")],
    )
    assert result.facts_merged == 1
    mock_fact.assert_awaited_once()
    kwargs = mock_fact.call_args.kwargs
    assert kwargs["subject_id"] == "eid-kai"  # repaired by name, not the stale id
    assert kwargs["from_order"] == 2 * EVENT_ORDER_CHAPTER_STRIDE


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_fact", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_fact_universal_claim_unlinked(
    mock_source, mock_resolve, mock_event, mock_evidence, mock_fact, mock_hier,
):
    """A universal claim (no subject) is stored but NOT linked to any entity."""
    result = await _run(
        mock_source, mock_resolve, mock_fact, mock_evidence,
        facts=[_fact("the empire was vast", subject=None, subject_id=None, ftype="milestone")],
    )
    assert result.facts_merged == 1
    assert mock_fact.call_args.kwargs["subject_id"] is None


@pytest.mark.asyncio
@patch(f"{_PATCH_BASE}.upsert_for_chapter", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_fact", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.add_evidence", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.merge_event", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.resolve_or_merge_entity", new_callable=AsyncMock)
@patch(f"{_PATCH_BASE}.upsert_extraction_source", new_callable=AsyncMock)
async def test_fact_unresolved_subject_unlinked(
    mock_source, mock_resolve, mock_event, mock_evidence, mock_fact, mock_hier,
):
    """A subject that matches neither a chapter entity NOR a merged id keeps the
    fact, unlinked (never invents an entity to hang it on)."""
    result = await _run(
        mock_source, mock_resolve, mock_fact, mock_evidence,
        facts=[_fact("the ghost decided", subject="Ghost", subject_id="not-merged")],
    )
    assert result.facts_merged == 1
    assert mock_fact.call_args.kwargs["subject_id"] is None
