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


# ── P2 (D3) cache integration tests ─────────────────────────────────────────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_p2_no_cache_when_book_id_chapter_id_omitted(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """P2 D3 backward-compat: when book_id+chapter_id are None (chat_turn
    path or legacy callers), _p2_cache_wrap passes through to extractors
    WITHOUT touching the cache. Mocks for cache layer would error if called."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    # No book_id / chapter_id passed -> passthrough path.
    result = await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Alice met Bob.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )
    assert result.entities_merged == 1
    # All 4 extractors called once each (no cache).
    mock_entities.assert_awaited_once()
    mock_relations.assert_awaited_once()
    mock_events.assert_awaited_once()
    mock_facts.assert_awaited_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.ExtractionLeavesRepo")
@patch(f"{_ORCH}.get_knowledge_pool")
async def test_p2_cache_hit_skips_all_4_llm_calls(
    mock_pool, mock_repo_cls,
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """P2 D3 cache-hit lock: 4 cached rows -> 0 LLM calls.

    When book_id+chapter_id provided + all 4 task_ids hit in the cache,
    extractors must NOT be called. Cached candidates flow through to writer.
    """
    from app.db.repositories.extraction_leaves import ExtractionLeaf
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    book_id = uuid4()
    chapter_id = uuid4()
    mock_pool.return_value = MagicMock()

    repo = MagicMock()
    cached_entity = ExtractionLeaf(
        id=uuid4(), book_id=book_id, scene_id=chapter_id,
        leaf_path="p", op="entity", task_id="t-e", status="completed",
        candidates_jsonb=[{
            "name": "CachedAlice", "kind": "person", "aliases": [],
            "confidence": 0.8, "canonical_name": "cachedalice",
            "canonical_id": "eid-cachedalice",
        }],
        retried_n=0, error_message=None,
        parse_version=1, extractor_version="v1", model_ref="m",
        glossary_anchor_size=None,
    )
    def _empty_cache_leaf(op: str) -> ExtractionLeaf:
        return ExtractionLeaf(
            id=uuid4(), book_id=book_id, scene_id=chapter_id,
            leaf_path="p", op=op, task_id=f"t-{op}", status="completed",
            candidates_jsonb=[],
            retried_n=0, error_message=None,
            parse_version=1, extractor_version="v1", model_ref="m",
            glossary_anchor_size=None,
        )
    # 1st call (entity) returns the entity cache; 2-4 are R/E/F empty.
    repo.fetch_cached = AsyncMock(side_effect=[
        cached_entity,
        _empty_cache_leaf("relation"),
        _empty_cache_leaf("event"),
        _empty_cache_leaf("fact"),
    ])
    mock_repo_cls.return_value = repo

    mock_write.return_value = _write_result(entities=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id=str(chapter_id), job_id=_JOB_ID,
        chapter_text="Alice met Bob.",
        model_source="user_model", model_ref="m-uuid",
        llm_client=MagicMock(),
        book_id=book_id,
        chapter_id=chapter_id,
    )

    # NONE of the 4 extractors called — pure cache-hit path.
    mock_entities.assert_not_called()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    # claim_pending + persist NOT called on the cache-hit path.
    repo.claim_pending.assert_not_called()
    repo.persist.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.ExtractionLeavesRepo")
@patch(f"{_ORCH}.get_knowledge_pool")
async def test_p2_cache_miss_calls_extractor_and_persists(
    mock_pool, mock_repo_cls,
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cache miss -> extractor called + candidates persisted via repo.persist."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    book_id = uuid4()
    chapter_id = uuid4()
    mock_pool.return_value = MagicMock()

    repo = MagicMock()
    repo.fetch_cached = AsyncMock(return_value=None)  # all misses
    repo.claim_pending = AsyncMock(return_value=True)
    repo.persist = AsyncMock(return_value=None)
    mock_repo_cls.return_value = repo

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id=str(chapter_id), job_id=_JOB_ID,
        chapter_text="Alice met Bob.",
        model_source="user_model", model_ref="m-uuid",
        llm_client=MagicMock(),
        book_id=book_id,
        chapter_id=chapter_id,
    )

    # All 4 extractors called (cache miss).
    mock_entities.assert_awaited_once()
    mock_relations.assert_awaited_once()
    mock_events.assert_awaited_once()
    mock_facts.assert_awaited_once()
    # repo.persist called once per op = 4 total.
    assert repo.persist.await_count == 4
    # repo.claim_pending called once per op.
    assert repo.claim_pending.await_count == 4


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.ExtractionLeavesRepo")
@patch(f"{_ORCH}.get_knowledge_pool")
async def test_p2_extractor_failure_marks_failed_and_reraises(
    mock_pool, mock_repo_cls,
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """When extractor raises, _p2_cache_wrap calls repo.mark_failed and re-raises."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    book_id = uuid4()
    chapter_id = uuid4()
    mock_pool.return_value = MagicMock()

    repo = MagicMock()
    repo.fetch_cached = AsyncMock(return_value=None)
    repo.claim_pending = AsyncMock(return_value=True)
    repo.mark_failed = AsyncMock(return_value=1)
    repo.persist = AsyncMock(return_value=None)
    mock_repo_cls.return_value = repo

    # Entity extractor explodes; later ops aren't reached.
    mock_entities.side_effect = RuntimeError("LLM gateway timeout")

    with pytest.raises(RuntimeError, match="LLM gateway timeout"):
        await extract_pass2_chapter(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chapter", source_id=str(chapter_id), job_id=_JOB_ID,
            chapter_text="Alice met Bob.",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
            book_id=book_id,
            chapter_id=chapter_id,
        )

    repo.mark_failed.assert_awaited_once()
    err = repo.mark_failed.call_args.kwargs["error_message"]
    assert "RuntimeError" in err and "timeout" in err


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.ExtractionLeavesRepo")
@patch(f"{_ORCH}.get_knowledge_pool")
async def test_p2_uses_per_op_extractor_version(
    mock_pool, mock_repo_cls,
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION regression-lock.

    Each op's claim_pending call MUST receive an extractor_version
    scoped to that op (format `v1-{op}-{8hex}`), NOT the global
    `v1-{8hex}` shape. The migration ensures editing one op's prompt
    only invalidates that op's cache slice.
    """
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    book_id = uuid4()
    chapter_id = uuid4()
    mock_pool.return_value = MagicMock()

    repo = MagicMock()
    repo.fetch_cached = AsyncMock(return_value=None)  # force cache miss → claim_pending
    repo.claim_pending = AsyncMock(return_value=True)
    repo.persist = AsyncMock(return_value=None)
    mock_repo_cls.return_value = repo

    # Must yield at least 1 entity so the orchestrator's "no entities"
    # gate doesn't short-circuit before R/E/F run.
    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id=str(chapter_id), job_id=_JOB_ID,
        chapter_text="Alice met Bob.",
        model_source="user_model", model_ref="m-uuid",
        llm_client=MagicMock(),
        book_id=book_id,
        chapter_id=chapter_id,
    )

    # Each claim_pending call MUST use the op-scoped extractor_version.
    # The global form would be `v1-XXXXXXXX` (no `-{op}-` segment).
    assert repo.claim_pending.await_count == 4
    seen_per_op_versions: dict[str, str] = {}
    for call in repo.claim_pending.await_args_list:
        op = call.kwargs["op"]
        ver = call.kwargs["extractor_version"]
        assert ver.startswith(f"v1-{op}-"), (
            f"op={op} got extractor_version={ver!r} — must be per-op "
            f"(starts with 'v1-{op}-')"
        )
        seen_per_op_versions[op] = ver

    # All 4 ops produced their own DISTINCT version slugs — no global
    # collapse to one shared version.
    assert sorted(seen_per_op_versions.keys()) == ["entity", "event", "fact", "relation"]
    assert len(set(seen_per_op_versions.values())) == 4


# ── Cycle 72 — precision filter integration tests ──────────────────────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_env_unset_skips_filter_call(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 72: env unset → orchestrator does NOT invoke filter.
    Regression-lock for the kwarg default."""
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    apf_calls: list[Any] = []

    async def _stub_apf(candidates, **kwargs):
        apf_calls.append(kwargs)
        return candidates

    with patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", None), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_apf):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-1", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    # apply_precision_filter must NOT have been called
    assert apf_calls == []


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_env_set_calls_filter_post_gather_pre_write(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 72: env set → filter called AFTER extractors gather, BEFORE
    write_pass2_extraction. Order matters: filter output is what gets
    persisted (not pre-filter Pass A)."""
    from loreweave_extraction import (
        Pass2Candidates, PrecisionFilterConfig,
    )
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    pass_a_entity = _entity("Alice")
    pass_a_relation = MagicMock()
    pass_a_event = MagicMock()
    pass_a_fact = MagicMock()
    mock_entities.return_value = [pass_a_entity]
    mock_relations.return_value = [pass_a_relation]
    mock_events.return_value = [pass_a_event]
    mock_facts.return_value = [pass_a_fact]
    mock_write.return_value = _write_result()

    config = PrecisionFilterConfig(model_ref="claude-4.7-opus-uuid")
    apf_calls: list[Any] = []

    async def _stub_apf(candidates, **kwargs):
        apf_calls.append((candidates, kwargs))
        # Simulate filter dropping the entity and event but keeping the relation
        return Pass2Candidates(
            entities=[],
            relations=candidates.relations,
            events=[],
            facts=candidates.facts,
            filter_status="applied",
            filter_coverage={"entity": 1.0, "relation": 1.0, "event": 1.0},
        )

    with patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", config), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_apf):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-2", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    # Filter was called exactly once
    assert len(apf_calls) == 1
    # Pass A candidates went IN
    in_cands, in_kwargs = apf_calls[0]
    assert in_cands.entities == [pass_a_entity]
    assert in_cands.relations == [pass_a_relation]
    assert in_cands.events == [pass_a_event]
    # Config got threaded through
    assert in_kwargs["config"] is config

    # write_pass2_extraction received the FILTERED candidates, not Pass A.
    mock_write.assert_awaited_once()
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["entities"] == []   # filter dropped
    assert write_kwargs["relations"] == [pass_a_relation]  # filter kept
    assert write_kwargs["events"] == []     # filter dropped
    # Facts are NEVER filtered per spec D2 — Pass A passes through
    assert write_kwargs["facts"] == [pass_a_fact]


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_filter_degraded_logs_warning_continues_write(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 72: filter returns filter_status='degraded' → write proceeds
    with Pass A candidates (filter never raises)."""
    from loreweave_extraction import (
        Pass2Candidates, PrecisionFilterConfig,
    )
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    pass_a_entity = _entity("Alice")
    mock_entities.return_value = [pass_a_entity]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    async def _stub_apf(candidates, **kwargs):
        # Degraded — return Pass A unchanged
        return Pass2Candidates(
            entities=candidates.entities,
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
            filter_status="degraded",
            filter_coverage={"entity": 0.0, "relation": 0.0, "event": 0.0},
        )

    config = PrecisionFilterConfig(model_ref="failing-filter")
    with patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", config), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_apf):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-3", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    # Write happens with Pass A candidates (filter degraded, no data loss)
    mock_write.assert_awaited_once()
    assert mock_write.call_args.kwargs["entities"] == [pass_a_entity]


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_emits_filter_applied_stage_log(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 72: when filter runs, a 'pass2_precision_filter' stage log is
    emitted to job_logs so the FE log panel can render it."""
    from loreweave_extraction import (
        Pass2Candidates, PrecisionFilterConfig,
    )
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    async def _stub_apf(candidates, **kwargs):
        return Pass2Candidates(
            entities=candidates.entities,
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
            filter_status="applied",
            filter_coverage={"entity": 1.0, "relation": 1.0, "event": 1.0},
        )

    repo = MagicMock()
    repo.append = AsyncMock()

    config = PrecisionFilterConfig(model_ref="claude-4.7-opus-uuid")
    with patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", config), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_apf):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-4", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
            job_logs_repo=repo,
        )

    # job_logs_repo.append received the precision_filter event
    appended_contexts = [
        call.args[4] if len(call.args) > 4 else call.kwargs.get("context", {})
        for call in repo.append.await_args_list
    ]
    filter_events = [
        ctx for ctx in appended_contexts
        if ctx.get("event") == "pass2_precision_filter"
    ]
    assert len(filter_events) == 1
    ev = filter_events[0]
    assert ev["filter_status"] == "applied"
    assert "filter_coverage" in ev


def test_load_precision_filter_config_orchestrator_env_set() -> None:
    """Env reader: KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF set
    → PrecisionFilterConfig parsed correctly."""
    import os
    from app.extraction.pass2_orchestrator import _load_precision_filter_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF",
            "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY",
        )
    }
    try:
        os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF"] = "claude-4.7-opus-uuid"
        os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY"] = "drop"
        config = _load_precision_filter_config()
        assert config is not None
        assert config.model_ref == "claude-4.7-opus-uuid"
        assert config.partial_policy == "drop"
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_load_precision_filter_config_orchestrator_env_unset() -> None:
    """Env reader: empty/unset → None."""
    import os
    from app.extraction.pass2_orchestrator import _load_precision_filter_config

    original = os.environ.pop("KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF", None)
    try:
        assert _load_precision_filter_config() is None
    finally:
        if original is not None:
            os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF"] = original
