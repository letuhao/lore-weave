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


def _hierarchy_paths() -> Any:
    """Minimal valid HierarchyPaths for the C12 summary-gate tests."""
    from app.extraction.pass2_writer import HierarchyPaths
    return HierarchyPaths(
        book_id="b1", book_path="book", book_title="B",
        part_id="p1", part_path="book/part-1", part_index=1, part_title="P",
        chapter_id="c1", chapter_path="book/part-1/chapter-1",
        chapter_index=1, chapter_title="C", scenes=[],
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


# ── L7B (D-KG-L7B-EXTRACT-ITEM) — schema split reaches the writer ──────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_write_schema_and_triage_repo_reach_writer(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """L7B: when the caller (/extract-item) splits the advisory prompt schema
    from the authoritative write schema, the orchestrator feeds the SDK with the
    advisory `schema` but hands the WRITER the authoritative `write_schema` +
    `triage_repo` — so the closed-edge guard + off-schema park run at the write
    boundary (the same activation /persist-pass2 has)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter
    from loreweave_extraction.schema_projection import ExtractionSchema

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = ["rel"]
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1, relations=1)

    advisory = ExtractionSchema(
        edge_predicates=("disciple_of",), allow_free_edges=True,
        schema_version=2, label="p@v2",
    )
    authoritative = ExtractionSchema(
        edge_predicates=("disciple_of",), allow_free_edges=False,
        schema_version=2, label="p@v2",
    )
    triage_repo = MagicMock()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai bows to the master.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        schema=advisory,
        write_schema=authoritative,
        triage_repo=triage_repo,
    )

    # SDK extractors received the ADVISORY schema (hint, never pre-drops).
    assert mock_entities.call_args.kwargs["schema"] is advisory
    assert mock_relations.call_args.kwargs["schema"] is advisory
    # The writer received the AUTHORITATIVE schema (real closed flag) + the
    # triage_repo so an off-schema drop PARKS instead of vanishing.
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["schema"] is authoritative
    assert write_kwargs["triage_repo"] is triage_repo


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_write_schema_none_falls_back_to_advisory_schema_no_triage(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Back-compat: when write_schema/triage_repo are omitted (every pre-L7B
    caller), the writer receives the single `schema` and triage_repo=None —
    byte-identical to before the split."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter
    from loreweave_extraction.schema_projection import ExtractionSchema

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = ["rel"]
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1, relations=1)

    schema = ExtractionSchema(
        edge_predicates=("x",), allow_free_edges=True, schema_version=1, label="p@v1",
    )

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        schema=schema,  # no write_schema / triage_repo
    )

    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["schema"] is schema  # fell back to the single schema
    assert write_kwargs["triage_repo"] is None


# ── C13 — glossary pinning: pinned names reach EVERY window ─────────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_pinned_names_injected_into_known_entities_when_absent_from_text(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """C13 acceptance: pinned glossary names appear in known_entities for a
    window whose chapter text NEVER mentions them. This is the whole point of
    pinning — a sparse-but-critical entity (a god in ch1 & ch5000) must be in
    the prompt context of every chapter, even ones it doesn't appear in."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-42", job_id=_JOB_ID,
        # The text mentions only Kai — NOT the pinned god "PanGu".
        chapter_text="Kai walks alone through the empty hall.",
        known_entities=["Zhao"],          # caller-supplied known
        pinned_names=["PanGu", "Nuwa"],   # C13 pinned glossary entities
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    # entity extractor's known_entities = pinned (first, priority) + caller
    # known, even though neither pinned name appears in the chapter text.
    entity_known = mock_entities.call_args.kwargs["known_entities"]
    assert "PanGu" in entity_known
    assert "Nuwa" in entity_known
    assert "Zhao" in entity_known
    # Pinned names come FIRST (anchor priority).
    assert entity_known[:2] == ["PanGu", "Nuwa"]

    # R/E/F gather also carries the pinned names (merged with extracted Kai).
    for mock in (mock_relations, mock_events, mock_facts):
        rkn = mock.call_args.kwargs["known_entities"]
        assert "PanGu" in rkn
        assert "Nuwa" in rkn


def test_merge_pinned_dedupes_and_prepends_order_stable():
    """C13 _merge_pinned: pinned first, dedup (exact), blanks dropped,
    None pinned ⇒ legacy known_entities unchanged."""
    from app.extraction.pass2_orchestrator import _merge_pinned

    # pinned ahead of known; duplicate "Kai" collapses to the pinned slot.
    assert _merge_pinned(["PanGu", "Kai"], ["Kai", "Zhao"]) == [
        "PanGu", "Kai", "Zhao",
    ]
    # blank / whitespace pinned dropped.
    assert _merge_pinned(["  ", "PanGu", ""], ["Zhao"]) == ["PanGu", "Zhao"]
    # None pinned ⇒ identical to known list (back-compat).
    assert _merge_pinned(None, ["A", "B"]) == ["A", "B"]
    # None known + None pinned ⇒ empty.
    assert _merge_pinned(None, None) == []


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
        id=uuid4(), book_id=book_id, chapter_id=chapter_id, scene_id=chapter_id,
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
            id=uuid4(), book_id=book_id, chapter_id=chapter_id, scene_id=chapter_id,
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


def test_load_precision_filter_config_ignores_env_model_ref() -> None:
    """D-WX-PRECISION-FILTER-MODEL-ARCH — the env is NO LONGER a filter-model source.
    Even with KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF set, the loader returns
    None: a global env model is cross-tenant (404'd for every non-owning user, stalling
    the decoupled fold). The filter model now comes ONLY from the per-project
    extraction_config.precision_filter override, resolved per-user. Regression-lock."""
    import os
    from app.extraction.pass2_orchestrator import _load_precision_filter_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF",
            "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY",
            "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES",
        )
    }
    try:
        os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF"] = "some-cross-tenant-uuid"
        os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY"] = "drop"
        os.environ["KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES"] = "relation"
        assert _load_precision_filter_config() is None
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ── Cycle 73d — entity recovery env loader ─────────────────────────────


def test_load_entity_recovery_config_env_unset_returns_none() -> None:
    import os
    from app.extraction.pass2_orchestrator import _load_entity_recovery_config

    saved = os.environ.pop("KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF", None)
    try:
        assert _load_entity_recovery_config() is None
    finally:
        if saved is not None:
            os.environ["KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF"] = saved


def test_load_entity_recovery_config_env_set_builds_config() -> None:
    import os
    from app.extraction.pass2_orchestrator import _load_entity_recovery_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF",
            "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE",
            "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MAX_BATCH",
        )
    }
    try:
        os.environ["KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF"] = "claude-4.7-opus-uuid"
        os.environ["KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE"] = "platform_model"
        os.environ["KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MAX_BATCH"] = "10"
        config = _load_entity_recovery_config()
        assert config is not None
        assert config.model_ref == "claude-4.7-opus-uuid"
        assert config.model_source == "platform_model"
        assert config.max_items_per_batch == 10
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ── Cycle 73e writer autocreate env loader (regression-lock) ─────


def test_load_writer_autocreate_config_env_unset_defaults_disabled() -> None:
    """Default state: autocreate OFF + max=20 (the soft cap).
    Pre-73e callers preserve cascade-skip behaviour."""
    import os
    from app.extraction.pass2_orchestrator import _load_writer_autocreate_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED",
            "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER",
        )
    }
    try:
        config = _load_writer_autocreate_config()
        assert config == {
            "autocreate_enabled": False,
            "autocreate_max": 20,
        }
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_load_writer_autocreate_config_env_set_enables_with_cap() -> None:
    """ENABLED=true + MAX_PER_CHAPTER=5 → spread-ready dict for
    write_pass2_extraction."""
    import os
    from app.extraction.pass2_orchestrator import _load_writer_autocreate_config

    saved = {
        k: os.environ.pop(k, None) for k in (
            "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED",
            "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER",
        )
    }
    try:
        os.environ["KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED"] = "true"
        os.environ["KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER"] = "5"
        config = _load_writer_autocreate_config()
        assert config == {
            "autocreate_enabled": True,
            "autocreate_max": 5,
        }
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


@pytest.mark.asyncio
async def test_hydrate_precision_filter_config_seeds_cache_from_redis(monkeypatch):
    """Cycle 73g L1 fold (closes r3 L1): KS hydrate on lifespan startup
    GETs Redis key + swaps module-level cache. Without this test, a
    regression in the hydrate path (signature change, import-path drift)
    only surfaces at container boot, not in CI."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.extraction.pass2_orchestrator as orch

    persisted = PrecisionFilterConfig(
        model_ref="hydrated-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    async def fake_get_filter_config(redis_client):
        return persisted

    saved = orch._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await orch.hydrate_precision_filter_config_from_redis("redis://fake")
        assert orch._PRECISION_FILTER_CONFIG is persisted
    finally:
        orch.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_hydrate_precision_filter_config_no_op_when_redis_empty(monkeypatch):
    """L1 edge: Redis key absent → hydrate leaves cache at env-default
    (no clobber)."""
    import app.extraction.pass2_orchestrator as orch

    async def fake_get_filter_config(redis_client):
        return None

    saved = orch._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await orch.hydrate_precision_filter_config_from_redis("redis://fake")
        # Cache unchanged.
        assert orch._PRECISION_FILTER_CONFIG is saved
    finally:
        orch.set_precision_filter_config(saved)


@pytest.mark.asyncio
async def test_consume_filter_reload_reverts_to_env_when_key_absent(monkeypatch):
    """Cycle 74b: pubsub re-read with the key absent (e.g. after a
    disable=true DELETE) reverts to ENV config, NOT None — the runtime
    path now matches startup hydrate. Closes the cycle-73f live-smoke
    cross-path divergence (runtime set None while a restart reloaded env)."""
    from loreweave_extraction import PrecisionFilterConfig
    import app.extraction.pass2_orchestrator as orch

    env_config = PrecisionFilterConfig(
        model_ref="env-revert-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    async def fake_subscribe_filter_reload(redis_client, on_reload, **kwargs):
        await on_reload()  # simulate one pubsub signal
        return

    async def fake_get_filter_config(redis_client):
        return None  # key absent

    saved = orch._PRECISION_FILTER_CONFIG
    monkeypatch.setattr(
        "loreweave_extraction.subscribe_filter_reload",
        fake_subscribe_filter_reload,
    )
    monkeypatch.setattr(
        "loreweave_extraction.get_filter_config",
        fake_get_filter_config,
    )
    monkeypatch.setattr(orch, "_load_precision_filter_config", lambda: env_config)
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        "redis.asyncio.from_url",
        lambda *args, **kwargs: fake_redis,
    )

    try:
        await orch.consume_filter_reload_signal("redis://fake")
        # Reverted to env config, not None.
        assert orch._PRECISION_FILTER_CONFIG is env_config
    finally:
        orch.set_precision_filter_config(saved)


def test_set_precision_filter_config_real_function_mutates_module_binding():
    """Cycle 73g L2 fold (closes r3 L2): mock-only tests verify
    mock_set_local.assert_called_once_with(None) but don't prove the
    REAL `set_precision_filter_config` actually mutates the module-level
    binding. This test calls the real function (no mock) and verifies."""
    import app.extraction.pass2_orchestrator as orch

    saved = orch._PRECISION_FILTER_CONFIG
    try:
        # Disable path: set to None.
        result = orch.set_precision_filter_config(None)
        assert result is None
        assert orch._PRECISION_FILTER_CONFIG is None

        # Re-enable path: set to a fresh config.
        from loreweave_extraction import PrecisionFilterConfig
        new = PrecisionFilterConfig(model_ref="real-mutation-test")
        result = orch.set_precision_filter_config(new)
        assert result is new
        assert orch._PRECISION_FILTER_CONFIG is new
    finally:
        # Restore for downstream tests.
        orch.set_precision_filter_config(saved)


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_filter_config_snapshot_at_entry_survives_concurrent_reload(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 73f r3 H2 fold — `_maybe_apply_precision_filter` MUST
    snapshot the module-level `_PRECISION_FILTER_CONFIG` to a local
    var at function entry. Without that, a concurrent pubsub-driven
    reload that swaps `_PRECISION_FILTER_CONFIG = None` between the
    `is None` check and the `config=...` parameter pass would push
    None into `apply_precision_filter`, crashing the call.

    This test simulates the race by making `apply_precision_filter`
    rebind `_PRECISION_FILTER_CONFIG = None` mid-call, then asserts
    that the orchestrator's invocation received the ORIGINAL config
    (proving snapshot semantics)."""
    from loreweave_extraction import (
        Pass2Candidates, PrecisionFilterConfig,
    )
    import app.extraction.pass2_orchestrator as orch
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    pass_a_entity = _entity("Alice")
    mock_entities.return_value = [pass_a_entity]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    config = PrecisionFilterConfig(
        model_ref="snapshot-test-uuid",
        categories=("relation",),
        partial_policy="drop",
    )

    apf_calls: list[Any] = []

    async def _race_apf(candidates, **kwargs):
        # Simulate a concurrent pubsub callback that swaps the
        # module-level binding to None DURING our call.
        orch._PRECISION_FILTER_CONFIG = None
        apf_calls.append(kwargs.get("config"))
        return candidates  # return inputs unchanged

    with patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", config), \
         patch(f"{_ORCH}.apply_precision_filter", new=_race_apf):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-race", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    # apply_precision_filter was called exactly once with the ORIGINAL
    # snapshot config (not None — even though the race fake swapped
    # the module-level binding to None before returning).
    assert len(apf_calls) == 1
    assert apf_calls[0] is config, (
        "filter config must be snapshotted at function entry; "
        "found a concurrent rebind leaked into apply_precision_filter "
        "call → r3 H2 atomicity fold regressed"
    )


def test_load_writer_autocreate_config_accepts_truthy_variants() -> None:
    """1 / yes / on / TRUE are all truthy; anything else is False."""
    import os
    from app.extraction.pass2_orchestrator import _load_writer_autocreate_config

    saved = os.environ.pop("KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", None)
    try:
        for truthy in ("true", "True", "TRUE", "1", "yes", "YES", "on", "On"):
            os.environ["KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED"] = truthy
            assert _load_writer_autocreate_config()["autocreate_enabled"] is True, (
                f"{truthy!r} should be truthy"
            )
        for falsy in ("false", "no", "off", "0", "", "  ", "anything-else"):
            os.environ["KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED"] = falsy
            assert _load_writer_autocreate_config()["autocreate_enabled"] is False, (
                f"{falsy!r} should be falsy"
            )
    finally:
        os.environ.pop("KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", None)
        if saved is not None:
            os.environ["KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED"] = saved


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_env_set_calls_recovery_before_filter(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 73d: when both recovery + filter env-set, recovery runs
    FIRST. Filter sees enriched candidates."""
    from loreweave_extraction import (
        EntityRecoveryConfig, Pass2Candidates, PrecisionFilterConfig,
    )
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    pass_a_entity = _entity("Alice")
    pass_a_relation = MagicMock()
    mock_entities.return_value = [pass_a_entity]
    mock_relations.return_value = [pass_a_relation]
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    recovery_calls: list[Any] = []
    filter_calls: list[Any] = []

    async def _stub_recovery(candidates, **kwargs):
        recovery_calls.append(kwargs)
        # Promote a recovered entity to verify the filter sees it
        from loreweave_extraction.extractors.entity import LLMEntityCandidate
        recovered = LLMEntityCandidate.model_construct(
            name="Recovered", kind="person", aliases=[], confidence=0.7,
            canonical_name="recovered", canonical_id="eid-recovered",
        )
        return Pass2Candidates(
            entities=list(candidates.entities) + [recovered],
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
        )

    async def _stub_filter(candidates, **kwargs):
        filter_calls.append((len(candidates.entities), list(kwargs.keys())))
        return Pass2Candidates(
            entities=candidates.entities,
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
            filter_status="applied",
            filter_coverage={"entity": 1.0, "relation": 1.0, "event": 1.0},
        )

    recovery_config = EntityRecoveryConfig(model_ref="recov-test")
    filter_config = PrecisionFilterConfig(model_ref="filter-test")

    with patch(f"{_ORCH}._ENTITY_RECOVERY_CONFIG", recovery_config), \
         patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", filter_config), \
         patch(f"{_ORCH}.recover_missing_entities", new=_stub_recovery), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_filter):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-1", job_id=_JOB_ID,
            user_message="hello",
            assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    # Recovery was called once, filter was called once
    assert len(recovery_calls) == 1
    assert len(filter_calls) == 1
    # Filter saw 2 entities (1 Pass A + 1 recovered) — confirms ordering
    assert filter_calls[0][0] == 2


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_entity_recovery_override_wins_over_module_config(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """KN model-roles A-wire: an endpoint-resolved `entity_recovery_override`
    ENABLES recovery even when the module-level env config is None (off), and its
    model is the one used — proving the per-project/per-user resolution reaches
    the recovery pass (the drift a `**kwargs`-swallowing stub would hide)."""
    from loreweave_extraction import EntityRecoveryConfig, Pass2Candidates
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    seen_configs: list[Any] = []

    async def _stub_recovery(candidates, **kwargs):
        seen_configs.append(kwargs.get("config"))
        return Pass2Candidates(
            entities=candidates.entities, relations=candidates.relations,
            events=candidates.events, facts=candidates.facts,
        )

    # Module-level env config OFF; override supplies the model per-project.
    with patch(f"{_ORCH}._ENTITY_RECOVERY_CONFIG", None), \
         patch(f"{_ORCH}.recover_missing_entities", new=_stub_recovery):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-2", job_id=_JOB_ID,
            user_message="hello", assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
            entity_recovery_override=EntityRecoveryConfig(model_ref="per-project-model"),
        )

    assert len(seen_configs) == 1, "override must enable recovery despite env-off"
    assert seen_configs[0].model_ref == "per-project-model"


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_no_override_no_env_recovery_off(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Back-compat: no override + env off → recovery does NOT run (byte-identical
    to pre-KN default)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chat_turn

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    called = []

    async def _stub_recovery(candidates, **kwargs):
        called.append(True)
        return candidates

    with patch(f"{_ORCH}._ENTITY_RECOVERY_CONFIG", None), \
         patch(f"{_ORCH}.recover_missing_entities", new=_stub_recovery):
        await extract_pass2_chat_turn(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chat_turn", source_id="t-3", job_id=_JOB_ID,
            user_message="hello", assistant_message="hi",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
        )

    assert called == [], "recovery must stay off when nothing is configured"


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_recovery_merges_glossary_anchors_as_hints(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """Cycle 73d: glossary anchors flow into recovery's known_entity_kinds."""
    from loreweave_extraction import (
        EntityRecoveryConfig, Pass2Candidates,
    )
    from app.extraction.anchor_loader import Anchor
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Alice")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result()

    recovery_capture: list[dict[str, str]] = []

    async def _stub_recovery(candidates, **kwargs):
        # Snapshot the known_entity_kinds the orchestrator built
        config = kwargs.get("config")
        recovery_capture.append(dict(config.known_entity_kinds))
        return candidates

    recovery_config = EntityRecoveryConfig(model_ref="recov-test")
    anchors = [
        Anchor(canonical_id="eid-watson", glossary_entity_id="ge-1",
               name="Watson", kind="person", aliases=("Dr. Watson", "John Watson")),
        Anchor(canonical_id="eid-london", glossary_entity_id="ge-2",
               name="London", kind="place", aliases=()),
    ]

    with patch(f"{_ORCH}._ENTITY_RECOVERY_CONFIG", recovery_config), \
         patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", None), \
         patch(f"{_ORCH}.recover_missing_entities", new=_stub_recovery):
        await extract_pass2_chapter(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
            chapter_text="text",
            model_source="user_model", model_ref="m-uuid",
            llm_client=MagicMock(),
            anchors=anchors,
        )

    assert len(recovery_capture) == 1
    hints = recovery_capture[0]
    # Both name + aliases injected
    assert hints.get("Watson") == "person"
    assert hints.get("Dr. Watson") == "person"
    assert hints.get("John Watson") == "person"
    assert hints.get("London") == "place"


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


# ── C12 — target-typed extraction (orchestrator) ───────────────────


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_targets_events_only_skips_relations_facts(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """targets={entities,events} ⇒ orchestrator runs entities+events, NOT
    relations/facts. Only the gather task-list is conditional."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_events.return_value = ["ev1"]
    mock_write.return_value = _write_result(entities=1, events=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        targets={"entities", "events"},
    )

    mock_entities.assert_called_once()
    mock_events.assert_called_once()
    mock_relations.assert_not_called()
    mock_facts.assert_not_called()
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["events"] == ["ev1"]
    assert write_kwargs["relations"] == []
    assert write_kwargs["facts"] == []


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_targets_none_runs_all(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """targets=None (default) ⇒ all four extractors run (back-compat)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        # targets omitted
    )

    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_called_once()
    mock_facts.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.enqueue_chapter_and_maybe_book_summaries", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_summaries_gated_out_when_not_in_targets(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_enqueue,
):
    """When summaries ∉ targets, the summary enqueue is NOT fired even
    though hierarchy + embedding deps are present."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    hp = _hierarchy_paths()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        targets={"entities", "relations"},  # summaries NOT requested
        hierarchy_paths=hp,
        embedding_model_uuid="emb-uuid",
        embedding_dimension=1024,
        summary_enqueue=AsyncMock(),
    )

    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_ORCH}.enqueue_chapter_and_maybe_book_summaries", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_summaries_enqueued_when_in_targets(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_enqueue,
):
    """When summaries ∈ targets (and deps present), enqueue fires."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    hp = _hierarchy_paths()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        targets={"entities", "summaries"},
        hierarchy_paths=hp,
        embedding_model_uuid="emb-uuid",
        embedding_dimension=1024,
        summary_enqueue=AsyncMock(),
    )

    mock_enqueue.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.enqueue_chapter_and_maybe_book_summaries", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_summaries_default_targets_enqueues(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_enqueue,
):
    """targets=None (default all) ⇒ summaries enqueue fires (back-compat)."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)

    hp = _hierarchy_paths()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        hierarchy_paths=hp,
        embedding_model_uuid="emb-uuid",
        embedding_dimension=1024,
        summary_enqueue=AsyncMock(),
    )

    mock_enqueue.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_orchestrator_recovery_filter_disabled_when_entities_not_requested(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
):
    """When entities ∉ requested targets (e.g. {events}), recovery +
    precision-filter are NOT applied even when env-configured."""
    from loreweave_extraction import EntityRecoveryConfig, PrecisionFilterConfig
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_events.return_value = []
    mock_write.return_value = _write_result(entities=1)

    recovery_calls: list[Any] = []
    filter_calls: list[Any] = []

    async def _stub_recovery(candidates, **kwargs):
        recovery_calls.append(kwargs)
        return candidates

    async def _stub_filter(candidates, **kwargs):
        filter_calls.append(kwargs)
        return candidates

    with patch(f"{_ORCH}._ENTITY_RECOVERY_CONFIG", EntityRecoveryConfig(model_ref="r")), \
         patch(f"{_ORCH}._PRECISION_FILTER_CONFIG", PrecisionFilterConfig(model_ref="f")), \
         patch(f"{_ORCH}.recover_missing_entities", new=_stub_recovery), \
         patch(f"{_ORCH}.apply_precision_filter", new=_stub_filter):
        await extract_pass2_chapter(
            session=MagicMock(),
            user_id=_USER_ID, project_id=_PROJECT_ID,
            source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
            chapter_text="Kai walks.",
            model_source="user_model", model_ref="test-model",
            llm_client=MagicMock(),
            targets={"events"},  # entities NOT explicitly requested
        )

    assert recovery_calls == []
    assert filter_calls == []


# ── D-KG-EXTRACTION-CANON-WIRE — quarantine gate ────────────────────


def _canon_candidate(*, confirmed: bool | None, name: str = "Alice") -> Any:
    from app.extraction.canon_check import ExtractionCanonCandidate
    return ExtractionCanonCandidate(
        kind="gone_entity_asserted_active_in_extraction", source="symbolic",
        entity_id="e-alice", name=name, status="gone", gone_from_order=1_000_010,
        span="Alice smiled", matched=name, confirmed=confirmed,
        why="acting in present tense" if confirmed else "",
    )


@pytest.mark.asyncio
@patch(f"{_ORCH}.check_extraction_canon", new_callable=AsyncMock)
@patch(f"{_ORCH}.list_gone_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_canon_check_gate_noop_when_no_gone_entities(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_list_gone, mock_check,
):
    """No gone entities for the project -> the judge is never called (cheap
    early exit), no canon-flag log, write proceeds normally."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)
    mock_list_gone.return_value = []

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

    mock_check.assert_not_called()
    mock_write.assert_called_once()
    events = [c.args[4]["event"] for c in job_logs_repo.append.call_args_list]
    assert "pass2_canon_flag" not in events


@pytest.mark.asyncio
@patch(f"{_ORCH}.check_extraction_canon", new_callable=AsyncMock)
@patch(f"{_ORCH}.list_gone_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_canon_check_gate_logs_confirmed_and_write_still_proceeds(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_list_gone, mock_check,
):
    """A CONFIRMED contradiction is logged (quarantine signal) but the write
    proceeds unconditionally -- this is advisory, never a hard block."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)
    mock_list_gone.return_value = [
        {"entity_id": "e-alice", "name": "Alice", "canonical_name": "alice", "from_order": 1_000_010}
    ]
    mock_check.return_value = [_canon_candidate(confirmed=True)]

    job_logs_repo = MagicMock()
    job_logs_repo.append = AsyncMock()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Alice smiled and picked up her sword.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        job_logs_repo=job_logs_repo,
    )

    mock_check.assert_called_once()
    mock_write.assert_called_once()  # write is UNCONDITIONAL
    flag_calls = [c for c in job_logs_repo.append.call_args_list if c.args[4]["event"] == "pass2_canon_flag"]
    assert len(flag_calls) == 1
    assert flag_calls[0].args[4]["entity_id"] == "e-alice"
    assert flag_calls[0].args[4]["name"] == "Alice"


@pytest.mark.asyncio
@patch(f"{_ORCH}.check_extraction_canon", new_callable=AsyncMock)
@patch(f"{_ORCH}.list_gone_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_canon_check_gate_skips_log_when_not_confirmed(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_list_gone, mock_check,
):
    """confirmed=False (judge cleared it, e.g. a flashback) or confirmed=None
    (degraded, symbolic-only) -> no canon-flag log, write proceeds."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)
    mock_list_gone.return_value = [
        {"entity_id": "e-alice", "name": "Alice", "canonical_name": "alice", "from_order": 1_000_010}
    ]
    mock_check.return_value = [_canon_candidate(confirmed=False), _canon_candidate(confirmed=None)]

    job_logs_repo = MagicMock()
    job_logs_repo.append = AsyncMock()

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="He remembered how Alice used to smile.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
        job_logs_repo=job_logs_repo,
    )

    mock_write.assert_called_once()
    events = [c.args[4]["event"] for c in job_logs_repo.append.call_args_list]
    assert "pass2_canon_flag" not in events


@pytest.mark.asyncio
@patch(f"{_ORCH}.list_gone_entities", new_callable=AsyncMock)
@patch(f"{_ORCH}.write_pass2_extraction", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_facts", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_events", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_relations", new_callable=AsyncMock)
@patch(f"{_ORCH}.extract_entities", new_callable=AsyncMock)
async def test_canon_check_gate_degrades_safely_on_exception(
    mock_entities, mock_relations, mock_events, mock_facts, mock_write,
    mock_list_gone,
):
    """CC4 -- a canon-check gate failure (e.g. a Neo4j hiccup on
    list_gone_entities) must NEVER break real extraction. Write still
    proceeds; the failure is swallowed + logged via `logger.warning`."""
    from app.extraction.pass2_orchestrator import extract_pass2_chapter

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    mock_write.return_value = _write_result(entities=1)
    mock_list_gone.side_effect = RuntimeError("neo4j hiccup")

    await extract_pass2_chapter(
        session=MagicMock(),
        user_id=_USER_ID, project_id=_PROJECT_ID,
        source_type="chapter", source_id="ch-1", job_id=_JOB_ID,
        chapter_text="Kai walks.",
        model_source="user_model", model_ref="test-model",
        llm_client=MagicMock(),
    )

    mock_write.assert_called_once()
