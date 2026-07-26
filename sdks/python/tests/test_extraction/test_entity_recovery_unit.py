"""Cycle 73d — unit tests for entity recovery (3-tier resolution).

Mocks `LLMClient.submit_and_wait` to control classifier responses.
Pure logic coverage of:

- Tier 1 (glossary/hints) lookup, case-insensitive
- Tier 3 (LLM) classifier promotion + abstract-relation drop
- Empty unmatched short-circuit (no LLM call)
- LLM failure → degrade-to-unjudged (no relation drop)
- MED-2: name-verdict consistency — all references dropped together
- LOW-1: unknown kind defaults to "concept"
- Immutability: returns NEW Pass2Candidates, never mutates input
- on_decision callback emits per name, exceptions don't poison

Mirrors test_pass2_filter_unit.py patterns.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from loreweave_extraction.entity_recovery import (
    EntityRecoveryConfig,
    RecoveryDecision,
    recover_missing_entities,
)
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from loreweave_extraction.pass2 import Pass2Candidates


# ── Fixtures ───────────────────────────────────────────────────────────


def _entity(name: str, kind: str = "person") -> LLMEntityCandidate:
    return LLMEntityCandidate.model_construct(
        name=name, kind=kind, aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _relation(s: str, p: str, o: str) -> LLMRelationCandidate:
    return LLMRelationCandidate.model_construct(
        subject=s, predicate=p, object=o,
        polarity="affirm", modality="actual", confidence=0.85,
        subject_id=None, object_id=None, relation_id=None,
    )


def _decisions_json(
    *items: tuple[int, str, str | None]
) -> str:
    """Build a classifier response JSON. Each item is (idx, verdict, kind|None)."""
    out = []
    for idx, verdict, kind in items:
        d = {"idx": idx, "verdict": verdict, "reason": "test"}
        if kind:
            d["kind"] = kind
        out.append(d)
    return json.dumps({"decisions": out})


def _mock_client(content_by_call: list[str] | str | Exception) -> Any:
    client = MagicMock()
    call_idx = {"n": 0}

    async def _submit(*args: Any, **kwargs: Any) -> Any:
        i = call_idx["n"]
        call_idx["n"] += 1
        if isinstance(content_by_call, Exception):
            raise content_by_call
        content = (content_by_call[i % len(content_by_call)]
                   if isinstance(content_by_call, list)
                   else content_by_call)
        job = MagicMock()
        job.status = "completed"
        job.result = {"messages": [{"role": "assistant", "content": content}]}
        return job

    client.submit_and_wait = AsyncMock(side_effect=_submit)
    return client


def _config(**overrides: Any) -> EntityRecoveryConfig:
    base = dict(model_ref="test-classifier")
    base.update(overrides)
    return EntityRecoveryConfig(**base)


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_unmatched_short_circuits_no_llm_call() -> None:
    """LOW-2: if every relation's subj/obj is in the entity set, no LLM call."""
    cands = Pass2Candidates(
        entities=[_entity("Alice"), _entity("Bob")],
        relations=[_relation("Alice", "knows", "Bob")],
    )
    client = _mock_client(_decisions_json((0, "entity", "person")))
    result = await recover_missing_entities(
        cands, text="x", config=_config(),
        user_id="u1", llm_client=client,
    )
    # No LLM call
    client.submit_and_wait.assert_not_called()
    # Returns unchanged (or new instance with same content)
    assert len(result.entities) == 2
    assert len(result.relations) == 1


@pytest.mark.asyncio
async def test_tier1_glossary_lookup_promotes_entity() -> None:
    """Tier 1: name in known_entity_kinds → promote, no LLM call."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "father", "cha Tấm")],
    )
    client = _mock_client("should not be called")
    config = _config(known_entity_kinds={"cha Tấm": "person"})
    result = await recover_missing_entities(
        cands, text="Alice met cha Tấm.", config=config,
        user_id="u1", llm_client=client,
    )
    client.submit_and_wait.assert_not_called()
    assert len(result.entities) == 2
    assert any(e.name == "cha Tấm" and e.kind == "person" for e in result.entities)
    assert len(result.relations) == 1  # kept


@pytest.mark.asyncio
async def test_tier1_lookup_case_insensitive() -> None:
    """MED-1: case-insensitive lookup; preserves original casing on promote."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "knows", "Sherlock Holmes")],
    )
    config = _config(known_entity_kinds={"sherlock holmes": "person"})
    client = _mock_client("nope")
    result = await recover_missing_entities(
        cands, text="x", config=config, user_id="u1", llm_client=client,
    )
    client.submit_and_wait.assert_not_called()
    promoted = [e for e in result.entities if e.name == "Sherlock Holmes"]
    assert len(promoted) == 1
    assert promoted[0].kind == "person"


@pytest.mark.asyncio
async def test_tier3_llm_promotes_entity_verdict() -> None:
    """LLM verdict=entity → promote with classifier-suggested kind."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "lives_in", "London")],
    )
    client = _mock_client(_decisions_json((0, "entity", "place")))
    result = await recover_missing_entities(
        cands, text="Alice lives in London.", config=_config(),
        user_id="u1", llm_client=client,
    )
    promoted = [e for e in result.entities if e.name == "London"]
    assert len(promoted) == 1
    assert promoted[0].kind == "place"
    assert len(result.relations) == 1


@pytest.mark.asyncio
async def test_tier3_llm_abstract_verdict_drops_relation() -> None:
    """LLM verdict=abstract → drop ALL relations referencing that name."""
    cands = Pass2Candidates(
        entities=[_entity("Holmes")],
        relations=[_relation("Holmes", "practiced", "civil practice")],
    )
    client = _mock_client(_decisions_json((0, "abstract", None)))
    result = await recover_missing_entities(
        cands, text="x", config=_config(), user_id="u1", llm_client=client,
    )
    # Entity unchanged
    assert len(result.entities) == 1
    # Relation dropped because object="civil practice" was verdict=abstract
    assert len(result.relations) == 0


@pytest.mark.asyncio
async def test_abstract_verdict_drops_all_relations_referencing_name() -> None:
    """MED-2: when name verdict=abstract, drop ALL relations referencing it."""
    cands = Pass2Candidates(
        entities=[_entity("Holmes"), _entity("Watson")],
        relations=[
            _relation("Holmes", "practiced", "civil practice"),
            _relation("Watson", "knew_of", "civil practice"),
            _relation("Holmes", "trusts", "Watson"),  # unaffected
        ],
    )
    client = _mock_client(_decisions_json((0, "abstract", None)))
    result = await recover_missing_entities(
        cands, text="x", config=_config(), user_id="u1", llm_client=client,
    )
    # Both relations with "civil practice" dropped; unaffected one kept
    assert len(result.relations) == 1
    assert result.relations[0].subject == "Holmes"
    assert result.relations[0].object == "Watson"


@pytest.mark.asyncio
async def test_llm_unknown_kind_defaults_to_concept() -> None:
    """LOW-1: kind outside {person,place,org,artifact,concept} defaults to 'concept'."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "studies", "alchemy")],
    )
    # Classifier returns invalid kind
    client = _mock_client(_decisions_json((0, "entity", "magic_thing")))
    result = await recover_missing_entities(
        cands, text="x", config=_config(), user_id="u1", llm_client=client,
    )
    promoted = [e for e in result.entities if e.name == "alchemy"]
    assert len(promoted) == 1
    assert promoted[0].kind == "concept"


@pytest.mark.asyncio
async def test_llm_failure_degrades_to_unjudged_keeps_relations() -> None:
    """Classifier raises → leave names as unjudged, relations untouched (writer cascades them)."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "lives_in", "London")],
    )
    client = _mock_client(RuntimeError("LLM down"))
    result = await recover_missing_entities(
        cands, text="x", config=_config(), user_id="u1", llm_client=client,
    )
    # No entity promoted (LLM failed)
    assert len(result.entities) == 1
    # Relation NOT dropped (unjudged ≠ abstract)
    assert len(result.relations) == 1


@pytest.mark.asyncio
async def test_returns_new_instance_never_mutates_input() -> None:
    """Immutability: input candidates unchanged after recovery."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "lives_in", "London")],
    )
    original_entities_id = id(cands.entities)
    original_relations_id = id(cands.relations)
    client = _mock_client(_decisions_json((0, "entity", "place")))
    result = await recover_missing_entities(
        cands, text="x", config=_config(), user_id="u1", llm_client=client,
    )
    assert result is not cands
    assert id(cands.entities) == original_entities_id
    assert id(cands.relations) == original_relations_id
    assert len(cands.entities) == 1  # input unchanged
    assert len(result.entities) == 2  # output has promoted


@pytest.mark.asyncio
async def test_on_decision_callback_invoked_per_unmatched_name() -> None:
    cands = Pass2Candidates(
        entities=[_entity("A")],
        relations=[_relation("A", "knows", "B"), _relation("A", "loves", "civil practice")],
    )
    client = _mock_client(_decisions_json(
        (0, "entity", "person"),    # B
        (1, "abstract", None),      # civil practice
    ))
    decisions: list[RecoveryDecision] = []
    await recover_missing_entities(
        cands, text="x", config=_config(),
        user_id="u1", llm_client=client,
        on_decision=decisions.append,
    )
    by_name = {d.name: d.verdict for d in decisions}
    assert by_name.get("B") == "entity"
    assert by_name.get("civil practice") == "abstract"


@pytest.mark.asyncio
async def test_on_decision_callback_exception_does_not_kill_recovery() -> None:
    cands = Pass2Candidates(
        entities=[_entity("A")],
        relations=[_relation("A", "knows", "B")],
    )
    client = _mock_client(_decisions_json((0, "entity", "person")))

    def _bad(d: RecoveryDecision) -> None:
        raise RuntimeError("observability broken")

    result = await recover_missing_entities(
        cands, text="x", config=_config(),
        user_id="u1", llm_client=client,
        on_decision=_bad,
    )
    assert len(result.entities) == 2  # promotion still happened


@pytest.mark.asyncio
async def test_mixed_tier1_and_tier3_resolution() -> None:
    """Some names resolve via glossary, rest go to LLM."""
    cands = Pass2Candidates(
        entities=[_entity("Holmes")],
        relations=[
            _relation("Holmes", "knows", "Watson"),       # glossary
            _relation("Holmes", "practiced", "law"),       # LLM → abstract
            _relation("Holmes", "lives_in", "London"),     # LLM → place
        ],
    )
    config = _config(known_entity_kinds={"watson": "person"})
    # LLM only sees 2 remaining names: law, London
    client = _mock_client(_decisions_json(
        (0, "abstract", None),         # law
        (1, "entity", "place"),         # London
    ))
    result = await recover_missing_entities(
        cands, text="x", config=config, user_id="u1", llm_client=client,
    )
    # Holmes + Watson (glossary) + London (LLM) = 3 entities
    names = [e.name for e in result.entities]
    assert "Watson" in names
    assert "London" in names
    # "law" relation dropped; Watson + London kept
    assert len(result.relations) == 2


@pytest.mark.asyncio
async def test_tier3_multi_batch_maps_local_decisions_to_global_names() -> None:
    """WX-T2c regression guard: >max_items_per_batch unmatched names split into
    multiple Tier-3 batches; each batch's decisions are LOCAL-indexed (0..n-1).
    apply_recovery_batch must map local_idx → the right name (batch[local_idx]).
    Every other recovery test is single-batch (one Tier-3 call), so this is the only
    guard on the WX-T2c build_recovery_batches + apply_recovery_batch seams."""
    cands = Pass2Candidates(
        entities=[_entity("Alice")],
        relations=[_relation("Alice", "rel", n) for n in ("N1", "N2", "N3", "N4", "N5")],
    )
    # max_items_per_batch=2 → unmatched [N1..N5] → 3 batches [N1,N2],[N3,N4],[N5].
    contents = [
        _decisions_json((0, "entity", "person"), (1, "abstract", None)),  # N1 keep, N2 abstract
        _decisions_json((0, "entity", "place"), (1, "abstract", None)),   # N3 keep, N4 abstract
        _decisions_json((0, "entity", "person")),                         # N5 keep
    ]
    client = _mock_client(contents)
    result = await recover_missing_entities(
        cands, text="x", config=_config(max_items_per_batch=2),
        user_id="u1", llm_client=client,
    )
    assert client.submit_and_wait.await_count == 3  # three Tier-3 batch calls
    names = {e.name for e in result.entities}
    assert {"N1", "N3", "N5"} <= names                # entity verdicts promoted
    assert "N2" not in names and "N4" not in names    # abstract verdicts not promoted
    # relations referencing abstract names (N2,N4) dropped; the entity ones kept —
    # proves each batch's local verdicts mapped to the right global name.
    assert {r.object for r in result.relations} == {"N1", "N3", "N5"}


@pytest.mark.asyncio
async def test_config_validates_batch_size() -> None:
    with pytest.raises(ValueError, match="max_items_per_batch"):
        EntityRecoveryConfig(model_ref="x", max_items_per_batch=0)


# ── Model-context-aware output clamp (build_recovery_submit_kwargs) ────────────

def test_recovery_submit_kwargs_unclamped_when_context_length_unknown():
    from loreweave_extraction.entity_recovery import build_recovery_submit_kwargs
    kw = build_recovery_submit_kwargs(
        config=_config(), system="s", user="u", n_items=50,
    )
    assert kw["input"]["max_tokens"] == 1024 + 200 * 50  # unclamped, today's behavior


def test_recovery_submit_kwargs_clamps_for_small_context_window():
    """A large batch against a small-context model must NOT request more output
    than the model's real window can structurally host (input + output together)."""
    from loreweave_extraction.entity_recovery import build_recovery_submit_kwargs
    kw = build_recovery_submit_kwargs(
        config=_config(), system="s", user="u", n_items=50, context_length=4000,
    )
    assert kw["input"]["max_tokens"] == int(4000 * 0.8)
