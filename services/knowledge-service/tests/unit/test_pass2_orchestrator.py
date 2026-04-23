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


# ── C3 (D-K19b.8-02) — stage producer for JobLogsPanel ─────────────


# Use real UUIDs so the emit helper's UUID(...) parse succeeds and we
# can assert the repo was called. Existing tests above use string
# sentinels — safe because they pass job_logs_repo=None (default).
from uuid import uuid4  # noqa: E402

_UID = str(uuid4())
_JID = str(uuid4())
_PID = str(uuid4())


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_happy_path_emits_four_stage_events(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """C3: happy-path extraction emits 4 ``info`` events via
    ``job_logs_repo.append`` — entities/gather/write plus the entity
    pre-stage event (gate is skipped because entities were produced).
    Asserts event names + that all calls are ``info`` level."""
    mock_entities.return_value = [_entity("Kai"), _entity("Zhao")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _full_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-1",
        job_id=_JID, chapter_text="Kai met Zhao.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    # 3 events on happy path: entities, gather, write. Gate is skipped
    # because entities returned > 0.
    assert fake_repo.append.await_count == 3
    events = [
        c.args[4]["event"]  # context dict is the 5th positional arg
        for c in fake_repo.append.await_args_list
    ]
    assert events == ["pass2_entities", "pass2_gather", "pass2_write"]
    # All emits are info level.
    for call in fake_repo.append.await_args_list:
        assert call.args[2] == "info"


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_gate_emits_pass2_entities_plus_gate(
    mock_entities, mock_write,
):
    """C3: zero-entity gate fires. Must emit BOTH the entity count
    event (len=0) AND the gate event to give operators a clear signal
    ('entities=0 -> gate taken, no relations/events/facts ran')."""
    mock_entities.return_value = []
    mock_write.return_value = _empty_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-1",
        job_id=_JID, chapter_text="No entities here.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    assert fake_repo.append.await_count == 2
    events = [c.args[4]["event"] for c in fake_repo.append.await_args_list]
    assert events == ["pass2_entities", "pass2_entities_gate"]
    # Entity count = 0 in the first emit's context.
    assert fake_repo.append.await_args_list[0].args[4]["count"] == 0


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_empty_text_emits_no_events(mock_entities, mock_write):
    """C3: empty text short-circuits BEFORE _emit_log runs. No log
    noise for empty turns — prevents the log panel from filling up
    with 'Pass 2: 0 entities' for every trivial chat turn."""
    mock_write.return_value = _empty_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-1",
        job_id=_JID, chapter_text="",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    assert fake_repo.append.await_count == 0
    mock_entities.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_log_emit_failure_does_not_break_extraction(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """C3: a Postgres hiccup during `job_logs_repo.append` must NOT
    kill the pipeline — extraction proceeds, warning logged. Locks
    the best-effort contract in `_emit_log`."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _full_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(
        side_effect=ConnectionError("simulated pg outage"),
    )

    # Must not raise.
    result = await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-1",
        job_id=_JID, chapter_text="Kai lived.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    # Extraction completed successfully despite log failures.
    assert result.entities_merged == 2  # from _full_write_result
    mock_write.assert_called_once()
    # append was attempted 3 times (each raised, each was caught).
    assert fake_repo.append.await_count == 3


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_repo_none_is_back_compat_no_emit(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """C3 regression: all existing pass2_orchestrator test callers
    pass job_logs_repo=None (the default) and must still work —
    guarantees the repo thread-through didn't accidentally make the
    repo mandatory. This test is the explicit lock for that contract."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _full_write_result()

    # No job_logs_repo passed — defaults to None.
    result = await extract_pass2_chapter(
        _fake_session(),
        user_id=USER_ID, project_id=PROJECT_ID,  # string sentinels, not UUIDs
        source_type="chapter", source_id="ch-1",
        job_id="j-1", chapter_text="Kai lived.",
        model_source="user_model", model_ref="test-model",
    )

    assert result.entities_merged == 2  # from _full_write_result
    # No UUID parse errors reached — _emit_log short-circuited on None.


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_pass2_entities_event_carries_duration_and_count(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """C3: context payload shape lock — a regression dropping
    ``duration_ms`` or renaming ``count`` would break any dashboard
    scraping the logs."""
    mock_entities.return_value = [_entity("Kai"), _entity("Zhao")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _full_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-1",
        job_id=_JID, chapter_text="Kai met Zhao.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    # Find the entities event
    entities_call = next(
        c for c in fake_repo.append.await_args_list
        if c.args[4]["event"] == "pass2_entities"
    )
    ctx = entities_call.args[4]
    assert ctx["count"] == 2
    assert "duration_ms" in ctx
    assert isinstance(ctx["duration_ms"], int)
    assert ctx["source_type"] == "chapter"
    assert ctx["source_id"] == "ch-1"


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_pass2_gather_event_payload_shape(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """/review-impl L4 parallel coverage: lock the gather event's
    context schema. A field rename (``relations`` → ``relation_count``)
    or dropped field would silently break any dashboard scraping
    the log stream for per-stage counts."""
    mock_entities.return_value = [_entity("Kai")]
    # Return non-zero counts so the context values are meaningful.
    mock_relations.return_value = [MagicMock(), MagicMock()]
    mock_events.return_value = [MagicMock()]
    mock_facts.return_value = [MagicMock(), MagicMock(), MagicMock()]
    mock_write.return_value = _full_write_result()

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chat_turn", source_id="turn-42",
        job_id=_JID, chapter_text="Kai met Zhao.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    gather_call = next(
        c for c in fake_repo.append.await_args_list
        if c.args[4]["event"] == "pass2_gather"
    )
    ctx = gather_call.args[4]
    # Required fields — any rename breaks this.
    assert ctx["relations"] == 2
    assert ctx["events"] == 1
    assert ctx["facts"] == 3
    assert "duration_ms" in ctx
    assert isinstance(ctx["duration_ms"], int)
    # source metadata echoed through
    assert ctx["source_type"] == "chat_turn"
    assert ctx["source_id"] == "turn-42"


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_pass2_write_event_payload_shape(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """/review-impl L4 parallel coverage for the write event +
    L2 (duration_ms presence): a regression dropping any of the
    five counter fields OR the newly-added duration_ms would
    invalidate dashboards tracking per-batch write cost."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = Pass2WriteResult(
        source_id="ch-7",
        entities_merged=5,
        relations_created=3,
        events_merged=2,
        facts_merged=4,
        evidence_edges=12,
    )

    fake_repo = MagicMock()
    fake_repo.append = AsyncMock(return_value=1)

    await extract_pass2_chapter(
        _fake_session(),
        user_id=_UID, project_id=_PID,
        source_type="chapter", source_id="ch-7",
        job_id=_JID, chapter_text="Kai met Zhao.",
        model_source="user_model", model_ref="test-model",
        job_logs_repo=fake_repo,
    )

    write_call = next(
        c for c in fake_repo.append.await_args_list
        if c.args[4]["event"] == "pass2_write"
    )
    ctx = write_call.args[4]
    assert ctx["entities_merged"] == 5
    assert ctx["relations_created"] == 3
    assert ctx["events_merged"] == 2
    assert ctx["facts_merged"] == 4
    assert ctx["evidence_edges"] == 12
    # /review-impl L2: duration_ms now present on write event too.
    assert "duration_ms" in ctx
    assert isinstance(ctx["duration_ms"], int)
    assert ctx["source_type"] == "chapter"
    assert ctx["source_id"] == "ch-7"
