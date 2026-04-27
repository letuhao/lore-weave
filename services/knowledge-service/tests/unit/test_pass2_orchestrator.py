"""Phase 4b-α — service-side wrapper tests for pass2_orchestrator.

The library's pass2.py is tested in sdks/python/tests/test_extraction/
test_pass2.py. This file covers the service-side concerns the library
deliberately doesn't own:

  - `_on_dropped` callback bridges to the
    `knowledge_extraction_dropped_total` Prometheus counter
  - `_emit_log` job_logs telemetry fires at the expected stages
  - `extractor_kwargs` shape passed to library functions
  - gate-on-empty-entities → `write_pass2_extraction` skips R/E/F
  - happy path → `write_pass2_extraction` receives all 4 candidate lists
  - `extract_pass2_chat_turn` concatenates user/assistant messages

Spun up post-/review-impl MED#1 fix to restore coverage that was lost
when the orchestrator's library-side logic moved to the SDK.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


_ORCH = "app.extraction.pass2_orchestrator"
_USER_ID = str(uuid4())
_PROJECT_ID = str(uuid4())
_JOB_ID = str(uuid4())


def _entity(name: str = "Kai") -> Any:
    """Build a minimal LLMEntityCandidate (library type) — used by the
    orchestrator wrapper as a stand-in for real extractor output."""
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    return LLMEntityCandidate(
        name=name, kind="person", aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _write_result(entities: int = 1, relations: int = 0,
                  events: int = 0, facts: int = 0,
                  source_id: str = "ch-1") -> Any:
    """Build a minimal Pass2WriteResult."""
    from app.extraction.pass2_writer import Pass2WriteResult
    return Pass2WriteResult(
        source_id=source_id,
        entities_merged=entities,
        relations_created=relations,
        events_merged=events,
        facts_merged=facts,
        evidence_edges=0,
    )


# ── _on_dropped → Prometheus counter wiring ─────────────────────────


def test_on_dropped_bumps_prometheus_counter():
    """The pass2_orchestrator's _on_dropped callback MUST bump the
    `knowledge_extraction_dropped_total{operation, reason}` counter
    so dashboards keep populated. Locks the Phase 4b-α library-boundary
    bridge introduced in pass2_orchestrator.py."""
    from app.extraction.pass2_orchestrator import _on_dropped
    from app.metrics import knowledge_extraction_dropped_total

    before = knowledge_extraction_dropped_total.labels(
        operation="entity_extraction", reason="missing_name",
    )._value.get()
    _on_dropped("entity_extraction", "missing_name")
    after = knowledge_extraction_dropped_total.labels(
        operation="entity_extraction", reason="missing_name",
    )._value.get()

    assert after - before == 1.0


# ── _run_pipeline gate-on-empty-entities → write skips R/E/F ────────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_run_pipeline_gates_when_no_entities(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Zero entities short-circuits to write_pass2_extraction without
    invoking R/E/F extractors. Locks the gate the FE relies on for
    'no entities found' job_logs entry."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = []
    mock_write.return_value = _write_result(entities=0)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Quiet passage.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    mock_entities.assert_called_once()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    mock_write.assert_called_once()
    # Empty entities path — write called WITHOUT entities/relations/etc kwargs
    write_kwargs = mock_write.call_args.kwargs
    assert "entities" not in write_kwargs


# ── _run_pipeline happy path → write gets all 4 candidate lists ────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_run_pipeline_happy_path_writes_all_four_lists(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Happy path: all 4 extractors called with the merged
    known_entities, write_pass2_extraction receives the 4 candidate
    lists. Catches a future kwargs-rename or arg-order regression
    that the library tests can't see (they don't know about write)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = ["rel"]
    mock_events.return_value = ["ev1", "ev2"]
    mock_facts.return_value = ["fact"]
    mock_write.return_value = _write_result(
        entities=1, relations=1, events=2, facts=1,
    )

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        known_entities=["Zhao"],  # caller-supplied known
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    # Each downstream extractor receives Zhao + Kai (caller known +
    # extracted). entity extractor only gets caller-supplied known.
    entity_kwargs = mock_entities.call_args.kwargs
    assert entity_kwargs["known_entities"] == ["Zhao"]

    for mock in (mock_relations, mock_events, mock_facts):
        kwargs = mock.call_args.kwargs
        assert "Kai" in kwargs["known_entities"]
        assert "Zhao" in kwargs["known_entities"]
        # on_dropped wired through (the function reference, not None)
        assert callable(kwargs["on_dropped"])

    # Write received the 4 candidate lists by name
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["entities"] == [_entity("Kai")] or len(write_kwargs["entities"]) == 1
    assert write_kwargs["relations"] == ["rel"]
    assert write_kwargs["events"] == ["ev1", "ev2"]
    assert write_kwargs["facts"] == ["fact"]


# ── _emit_log job_logs telemetry hooks fire at expected stages ─────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_run_pipeline_emits_pass2_telemetry_events(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """When job_logs_repo is supplied, 3 stage events fire:
    pass2_entities (after entity stage), pass2_gather (after R/E/F),
    pass2_write (after Neo4j write). FE's JobLogsPanel reads these
    timings via the events.event field."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    job_logs_repo = MagicMock()
    job_logs_repo.append = AsyncMock()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        job_logs_repo=job_logs_repo,
    )

    events = [
        c.args[4]["event"]  # 5th positional arg is `context: dict`
        for c in job_logs_repo.append.call_args_list
    ]
    assert "pass2_entities" in events
    assert "pass2_gather" in events
    assert "pass2_write" in events


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_run_pipeline_emits_gate_event_when_no_entities(
    mock_entities, mock_write,
):
    """Empty-entities gate path fires pass2_entities + pass2_entities_gate
    (NOT pass2_gather or pass2_write — those would mislead operators
    into thinking the gate didn't fire)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = []
    mock_write.return_value = _write_result(entities=0)

    job_logs_repo = MagicMock()
    job_logs_repo.append = AsyncMock()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Quiet.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        job_logs_repo=job_logs_repo,
    )

    events = [c.args[4]["event"] for c in job_logs_repo.append.call_args_list]
    assert "pass2_entities" in events
    assert "pass2_entities_gate" in events
    assert "pass2_gather" not in events
    assert "pass2_write" not in events


# ── extract_pass2_chat_turn concatenates user/assistant messages ───


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_chat_turn_concatenates_user_and_assistant_messages(
    mock_entities, mock_write,
):
    """chat_turn entry point joins non-empty user + assistant messages
    with '\\n\\n' before passing to _run_pipeline. Locks the
    K15.8-mirrored input shape extractors expect."""
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = []
    mock_write.return_value = _write_result(entities=0)

    await extract_pass2_chat_turn(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chat_turn", source_id="turn-1", job_id=_JOB_ID,
        user_message="Hello.",
        assistant_message="Hi there.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    # extract_entities saw concatenated text
    entity_kwargs = mock_entities.call_args.kwargs
    assert entity_kwargs["text"] == "Hello.\n\nHi there."


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_chat_turn_filters_empty_halves(mock_entities, mock_write):
    """If only user_message is supplied, no leading \\n\\n separator.
    Matches K15.8's `extract_from_chat_turn` semantic."""
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = []
    mock_write.return_value = _write_result(entities=0)

    await extract_pass2_chat_turn(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chat_turn", source_id="turn-1", job_id=_JOB_ID,
        user_message="Just user.",
        assistant_message=None,
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    entity_kwargs = mock_entities.call_args.kwargs
    assert entity_kwargs["text"] == "Just user."
