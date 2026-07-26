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
async def test_context_budget_threaded_to_all_four_extractors(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """A caller-supplied context_budget must reach entity AND all three trio
    extractors — omitting it (None, the default) is the exact bug class that let
    a fixed window silently override every model's real context (see budget.py)."""
    from loreweave_extraction.context_budget import ContextBudget

    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []
    budget = ContextBudget(model_context=1_000_000)

    await extract_pass2(
        text="Kai met Zhao.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        context_budget=budget,
    )

    for mock in (mock_entities, mock_relations, mock_events, mock_facts):
        assert mock.call_args.kwargs["context_budget"] is budget


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
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_cancel_check_forwarded_to_all_extractors(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """bug #34 — extract_pass2 threads cancel_check to entity + R/E/F so an
    in-flight LLM call aborts on job cancellation."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    async def _cancel() -> bool:
        return False

    await extract_pass2(
        text="Kai met Zhao.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        cancel_check=_cancel,
    )

    for mock in (mock_entities, mock_relations, mock_events, mock_facts):
        assert mock.call_args.kwargs["cancel_check"] is _cancel


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_cancel_check_defaults_none(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """bug #34 — omitting cancel_check forwards None (back-compat)."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai met Zhao.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
    )

    for mock in (mock_entities, mock_relations, mock_events, mock_facts):
        assert mock.call_args.kwargs["cancel_check"] is None


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


# ── Cycle 72 — precision filter kwarg tests ────────────────────────


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_precision_filter_none_zero_behavior_change(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """precision_filter=None (default) preserves pre-cycle-72 contract."""
    e = _entity("Kai")
    mock_entities.return_value = [e]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    result = await extract_pass2(
        text="Kai exists.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        # precision_filter omitted = None (default)
    )

    # filter never ran → filter_status default
    assert result.filter_status == "skipped"
    assert result.filter_coverage == {}


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_precision_filter_set_chains_filter_call(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """precision_filter=<config> invokes apply_precision_filter once."""
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig

    e = _entity("Kai")
    mock_entities.return_value = [e]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    apf_calls: list[Any] = []

    async def _stub_apf(candidates, **kwargs):
        apf_calls.append(kwargs)
        # Return a new candidates with applied status (mimics filter result)
        from loreweave_extraction.pass2 import Pass2Candidates
        return Pass2Candidates(
            entities=candidates.entities,
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
            filter_status="applied",
            filter_coverage={"entity": 1.0, "relation": 1.0, "event": 1.0},
        )

    config = PrecisionFilterConfig(
        model_ref="test-filter", categories=("entity",),
    )

    with patch(
        "loreweave_extraction.pass2_filter.apply_precision_filter",
        new=_stub_apf,
    ):
        result = await extract_pass2(
            text="Kai exists.",
            known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref="test-model",
            llm_client=_fake_llm_client(),
            precision_filter=config,
        )

    assert len(apf_calls) == 1
    assert apf_calls[0]["config"] is config
    assert result.filter_status == "applied"


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_filter_status_field_populated_correctly_per_status(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """When extract_pass2 short-circuits (no entities), filter_status
    is still 'skipped' regardless of precision_filter."""
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig

    mock_entities.return_value = []  # gate -> empty Pass2Candidates
    config = PrecisionFilterConfig(model_ref="test-filter")

    result = await extract_pass2(
        text="empty result",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        precision_filter=config,
    )

    # No entities → gated; filter never invoked
    assert result.filter_status == "skipped"
    mock_relations.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_filter_coverage_populated_per_category(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """When filter runs, coverage is preserved on the returned candidates."""
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig

    e = _entity("Kai")
    mock_entities.return_value = [e]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    async def _stub_apf(candidates, **kwargs):
        from loreweave_extraction.pass2 import Pass2Candidates
        return Pass2Candidates(
            entities=candidates.entities,
            relations=candidates.relations,
            events=candidates.events,
            facts=candidates.facts,
            filter_status="applied",
            filter_coverage={"entity": 0.8, "relation": 1.0, "event": 1.0},
        )

    with patch(
        "loreweave_extraction.pass2_filter.apply_precision_filter",
        new=_stub_apf,
    ):
        result = await extract_pass2(
            text="Kai walks.",
            known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref="test-model",
            llm_client=_fake_llm_client(),
            precision_filter=PrecisionFilterConfig(
                model_ref="test-filter",
            ),
        )

    assert result.filter_coverage["entity"] == 0.8
    assert result.filter_coverage["relation"] == 1.0


# ── C12 — target-typed extraction tests ────────────────────────────
#
# `targets` selects which Pass-2 passes run. The taxonomy uses the
# PLURAL contract names (entities/relations/events/facts) — `summaries`
# is orchestrator-gated (NOT an SDK op) so the SDK ignores it.
# Back-compat: targets=None / empty ⇒ ALL passes run (every prior caller
# is unaffected). Dependent targets {relations,events,facts} silently
# force `entities` in (they anchor to entity names).


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_none_runs_all_passes(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """targets=None (default) ⇒ ALL four extractors run (back-compat)."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        # targets omitted = None
    )

    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_called_once()
    mock_facts.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_empty_runs_all_passes(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """targets=set() (empty) ⇒ ALL four extractors run (back-compat)."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        targets=set(),
    )

    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_called_once()
    mock_facts.assert_called_once()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_entities_only(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """targets={entities} ⇒ only entity extractor runs, no R/E/F."""
    mock_entities.return_value = [_entity("Kai")]

    result = await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        targets={"entities"},
    )

    mock_entities.assert_called_once()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    assert len(result.entities) == 1
    assert result.relations == []
    assert result.events == []
    assert result.facts == []


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_entities_and_events_only(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """targets={entities,events} ⇒ entities + events, NO relations/facts."""
    mock_entities.return_value = [_entity("Kai")]
    mock_events.return_value = [MagicMock(), MagicMock()]

    result = await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        targets={"entities", "events"},
    )

    mock_entities.assert_called_once()
    mock_events.assert_called_once()
    mock_relations.assert_not_called()
    mock_facts.assert_not_called()
    assert len(result.events) == 2
    assert result.relations == []
    assert result.facts == []


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_relations_auto_includes_entities(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """targets={relations} ⇒ entities auto-included (anchor) + relations;
    no events/facts."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = [MagicMock()]

    result = await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        targets={"relations"},
    )

    # entities run even though not explicitly requested (dependency)
    mock_entities.assert_called_once()
    mock_relations.assert_called_once()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()
    assert len(result.entities) == 1
    assert len(result.relations) == 1


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_summaries_only_is_entities_only(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """`summaries` is NOT an SDK op — targets={summaries} carries no SDK
    op, so the SDK runs only entities (its mandatory first pass) and no
    R/E/F. The orchestrator handles the summaries enqueue separately."""
    mock_entities.return_value = [_entity("Kai")]

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        targets={"summaries"},
    )

    mock_entities.assert_called_once()
    mock_relations.assert_not_called()
    mock_events.assert_not_called()
    mock_facts.assert_not_called()


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_targets_without_entities_disables_recovery_and_filter(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """When `entities ∉ targets` (e.g. {events}), entity_recovery /
    precision_filter are no-ops (nothing to recover/filter against an
    intentionally non-canonical set) — they must NOT be invoked even if
    the caller passed configs."""
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig

    mock_entities.return_value = [_entity("Kai")]
    mock_events.return_value = []

    recovery_calls: list[Any] = []
    filter_calls: list[Any] = []

    async def _stub_recover(candidates, **kwargs):
        recovery_calls.append(kwargs)
        return candidates

    async def _stub_apf(candidates, **kwargs):
        filter_calls.append(kwargs)
        return candidates

    with patch(
        "loreweave_extraction.entity_recovery.recover_missing_entities",
        new=_stub_recover,
    ), patch(
        "loreweave_extraction.pass2_filter.apply_precision_filter",
        new=_stub_apf,
    ):
        await extract_pass2(
            text="Kai walks.",
            known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref="test-model",
            llm_client=_fake_llm_client(),
            targets={"events"},  # entities NOT requested
            precision_filter=PrecisionFilterConfig(model_ref="f"),
            entity_recovery=MagicMock(),
        )

    assert recovery_calls == []
    assert filter_calls == []


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_concurrency_level_caps_parallel_trio_calls(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """concurrency_level=1 serialises the R/E/F gather — at most 1 extractor
    runs at a time (observed via a concurrency counter)."""
    import asyncio as _asyncio

    mock_entities.return_value = [_entity("Kai")]

    running = 0
    max_seen = 0

    async def _tracked(*_a, **_k):
        nonlocal running, max_seen
        running += 1
        max_seen = max(max_seen, running)
        await _asyncio.sleep(0.01)
        running -= 1
        return []

    mock_relations.side_effect = _tracked
    mock_events.side_effect = _tracked
    mock_facts.side_effect = _tracked

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        concurrency_level=1,
    )

    assert max_seen == 1  # serialised by the semaphore


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_concurrency_level_none_is_unbounded(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """concurrency_level=None (default) runs all three trio ops in parallel."""
    import asyncio as _asyncio

    mock_entities.return_value = [_entity("Kai")]

    running = 0
    max_seen = 0

    async def _tracked(*_a, **_k):
        nonlocal running, max_seen
        running += 1
        max_seen = max(max_seen, running)
        await _asyncio.sleep(0.01)
        running -= 1
        return []

    mock_relations.side_effect = _tracked
    mock_events.side_effect = _tracked
    mock_facts.side_effect = _tracked

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref="test-model",
        llm_client=_fake_llm_client(),
        # concurrency_level omitted = None
    )

    assert max_seen == 3  # all three concurrent
