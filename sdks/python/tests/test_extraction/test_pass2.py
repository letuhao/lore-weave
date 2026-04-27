"""Unit tests for K17.8 — Pass 2 high-level orchestrator.

Phase 4b-α: orchestrator moved into ``loreweave_extraction`` library.
The library version is a pure pipeline (entities -> gate -> parallel
R/E/F) with no Neo4j writes, no job_logs emit, no anchors. Tests
focused on persistence/logging/anchors are owned by the service-side
wrapper (``services/knowledge-service/tests/unit/test_pass2_orchestrator.py``
in earlier history) — those concerns remain in the service.

This file covers the library's contract:
  - Empty text returns empty Pass2Candidates, no extractor calls
  - Zero entities gates the downstream extractors
  - Happy path runs all four extractors, gather is concurrent
  - ExtractionError from any stage propagates
  - Known entities are merged with extracted entity names for downstream
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.pass2 import Pass2Candidates, extract_pass2


# ── Helpers ─────────────────────────────────────────────────────

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"

_PASS2 = "loreweave_extraction.pass2"


def _entity(name: str, kind: str = "person") -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _fake_llm_client() -> Any:
    """Extractors are mocked here so the client object is never used —
    a plain MagicMock satisfies the LLMClientProtocol."""
    return MagicMock()


# ── Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_empty_text_skips_extractors(mock_entities):
    """Empty text -> empty Pass2Candidates, no extractor calls."""
    result = await extract_pass2(
        text="",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    assert isinstance(result, Pass2Candidates)
    assert result.is_empty()
    mock_entities.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_whitespace_text_skips_extractors(mock_entities):
    """Whitespace-only text is treated the same as empty."""
    result = await extract_pass2(
        text="   \n\t ",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )
    assert result.is_empty()
    mock_entities.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_zero_entities_gates_downstream(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """Zero entities -> relations/events/facts extractors not called."""
    mock_entities.return_value = []

    result = await extract_pass2(
        text="A quiet passage.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    mock_entities.assert_called_once()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    assert result.is_empty()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_happy_path_runs_all_four_extractors(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """Entities found -> all four extractors invoked, candidates aggregated."""
    mock_entities.return_value = [_entity("Kai"), _entity("Zhao")]
    mock_relations.return_value = [MagicMock()]
    mock_events.return_value = [MagicMock(), MagicMock()]
    mock_facts.return_value = [MagicMock()]

    result = await extract_pass2(
        text="Kai and Zhao met at the gate.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_called_once()
    mock_facts.assert_called_once()

    assert len(result.entities) == 2
    assert len(result.relations) == 1
    assert len(result.events) == 2
    assert len(result.facts) == 1
    assert not result.is_empty()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_known_entities_merged_with_extracted(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """Known entities are merged with extracted entity names for
    downstream extractors so R/E/F can anchor against both."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai met Zhao.",
        known_entities=["Zhao"],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    # Each downstream extractor receives the union of caller-supplied
    # known_entities + extracted entity display names.
    for mock in (mock_relations, mock_events, mock_facts):
        kwargs = mock.call_args.kwargs
        known = kwargs["known_entities"]
        assert "Zhao" in known
        assert "Kai" in known


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_extraction_error_from_entities_propagates(mock_entities):
    """ExtractionError from the entity stage halts the pipeline and
    propagates to the caller (no swallow)."""
    mock_entities.side_effect = ExtractionError(
        "bad key", stage="provider",
    )

    with pytest.raises(ExtractionError) as exc_info:
        await extract_pass2(
            text="Some text.",
            known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref="test-model",
            llm_client=_fake_llm_client(),
        )
    assert exc_info.value.stage == "provider"


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_extraction_error_from_relation_stage_propagates(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """ExtractionError from any of the parallel R/E/F extractors
    propagates through asyncio.gather to the caller."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.side_effect = ExtractionError(
        "rate limited", stage="provider_exhausted",
    )
    mock_events.return_value = []
    mock_facts.return_value = []

    with pytest.raises(ExtractionError) as exc_info:
        await extract_pass2(
            text="Kai walks.",
            known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref="test-model",
            llm_client=_fake_llm_client(),
        )
    assert exc_info.value.stage == "provider_exhausted"


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_pass2_candidates_dataclass_shape(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """Sanity: the returned Pass2Candidates exposes the four lists as
    attributes (not a dict). Locks the contract any caller relies on."""
    e = _entity("Kai")
    rel = MagicMock()
    ev = MagicMock()
    fact = MagicMock()
    mock_entities.return_value = [e]
    mock_relations.return_value = [rel]
    mock_events.return_value = [ev]
    mock_facts.return_value = [fact]

    result = await extract_pass2(
        text="Kai exists.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    assert result.entities == [e]
    assert result.relations == [rel]
    assert result.events == [ev]
    assert result.facts == [fact]
