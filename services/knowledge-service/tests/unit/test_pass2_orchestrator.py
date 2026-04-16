"""Unit tests for K17.8 — Pass 2 orchestrator.

Mocks K17.4–K17.7 extractors and the pass2_writer to test pipeline
flow without LLM or Neo4j calls. Validates:
  - Happy path: entities → concurrent relations/events/facts → write
  - Empty text → write empty source, no extractor calls
  - Zero entities → gate blocks relations/events/facts
  - Chat turn concatenation
  - Chapter entry point
  - ExtractionError propagation from extractor
  - Known entities merged with extracted entity names
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_json_parser import ExtractionError
from app.extraction.pass2_orchestrator import (
    extract_pass2_chapter,
    extract_pass2_chat_turn,
)
from app.extraction.pass2_writer import Pass2WriteResult


# ── Helpers ─────────────────────────────────────────────────────

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"

_ORCH = "app.extraction.pass2_orchestrator"


def _fake_session() -> Any:
    return MagicMock()


def _entity(name: str, kind: str = "person") -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _empty_write_result(source_id: str = "src-001") -> Pass2WriteResult:
    return Pass2WriteResult(source_id=source_id)


def _full_write_result() -> Pass2WriteResult:
    return Pass2WriteResult(
        source_id="src-001",
        entities_merged=2, relations_created=1,
        events_merged=1, facts_merged=1, evidence_edges=4,
    )


# ── Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_empty_text_skips_extractors(mock_entities, mock_write):
    """Empty text → write empty source, no extractor calls."""
    mock_write.return_value = _empty_write_result()

    result = await extract_pass2_chapter(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id="j-1", chapter_text="",
        model_source="user_model", model_ref="test-model",
    )

    assert result.entities_merged == 0
    mock_entities.assert_not_called()
    mock_write.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_zero_entities_gates_downstream(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Zero entities → relations/events/facts extractors not called."""
    mock_entities.return_value = []
    mock_write.return_value = _empty_write_result()

    result = await extract_pass2_chapter(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id="j-1", chapter_text="A quiet passage.",
        model_source="user_model", model_ref="test-model",
    )

    mock_entities.assert_called_once()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    assert result.entities_merged == 0


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_happy_path_full_pipeline(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Entities found → all extractors called → write called with all candidates."""
    mock_entities.return_value = [_entity("Kai"), _entity("Zhao")]
    mock_relations.return_value = [MagicMock()]
    mock_events.return_value = [MagicMock()]
    mock_facts.return_value = [MagicMock()]
    mock_write.return_value = _full_write_result()

    result = await extract_pass2_chapter(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id="j-1", chapter_text="Kai and Zhao met at the gate.",
        model_source="user_model", model_ref="test-model",
    )

    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_called_once()
    mock_facts.assert_called_once()

    # Writer called with all candidate types
    write_kwargs = mock_write.call_args.kwargs
    assert len(write_kwargs["entities"]) == 2
    assert len(write_kwargs["relations"]) == 1
    assert len(write_kwargs["events"]) == 1
    assert len(write_kwargs["facts"]) == 1

    assert result.entities_merged == 2


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_chat_turn_concatenates_messages(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Chat turn concatenates user + assistant messages."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _empty_write_result()

    await extract_pass2_chat_turn(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chat_message", source_id="turn-1",
        job_id="j-1",
        user_message="Who is Kai?",
        assistant_message="Kai is a warrior.",
        model_source="user_model", model_ref="test-model",
    )

    # Entity extractor receives concatenated text
    call_kwargs = mock_entities.call_args.kwargs
    assert "Who is Kai?" in call_kwargs["text"]
    assert "Kai is a warrior." in call_kwargs["text"]


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_chat_turn_empty_messages_skip(mock_entities, mock_write):
    """Chat turn with no messages → empty source, no extractors."""
    mock_write.return_value = _empty_write_result()

    await extract_pass2_chat_turn(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chat_message", source_id="turn-1",
        job_id="j-1",
        user_message=None, assistant_message="   ",
        model_source="user_model", model_ref="test-model",
    )

    mock_entities.assert_not_called()
    mock_write.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_extraction_error_propagates(mock_entities, mock_write):
    """ExtractionError from K17.4 propagates to caller."""
    mock_entities.side_effect = ExtractionError(
        stage="provider", message="bad key",
    )

    with pytest.raises(ExtractionError) as exc_info:
        await extract_pass2_chapter(
            _fake_session(),
            user_id=USER_ID, project_id=PROJECT_ID,
            source_type="chapter", source_id="ch-1",
            job_id="j-1", chapter_text="Some text.",
            model_source="user_model", model_ref="test-model",
        )

    assert exc_info.value.stage == "provider"
    mock_write.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_known_entities_merged_with_extracted(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Known entities are merged with extracted entity names for downstream extractors."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _empty_write_result()

    await extract_pass2_chapter(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,
        source_type="chapter", source_id="ch-1",
        job_id="j-1", chapter_text="Kai met Zhao.",
        known_entities=["Zhao"],
        model_source="user_model", model_ref="test-model",
    )

    # Downstream extractors get merged known_entities
    rel_kwargs = mock_relations.call_args.kwargs
    known = rel_kwargs["known_entities"]
    assert "Zhao" in known
    assert "Kai" in known
