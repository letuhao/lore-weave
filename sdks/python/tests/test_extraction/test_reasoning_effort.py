"""D-KG-WORKER-GRADED-EFFORT — graded reasoning effort threads from
extract_pass2 → the four per-op submit builders → the LLM `input`.

Covers:
  - reasoning_wire_fields: "none"/None ⇒ {} (byte-identical default); a graded
    value ⇒ {reasoning_effort, chat_template_kwargs}.
  - each builder's input carries the wire fields for a graded effort + is
    byte-identical to the pre-effort dict for the default.
  - extract_pass2(reasoning_effort=...) forwards it to every extractor; the
    default omits it (back-compat).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loreweave_extraction.extractors.entity import (
    LLMEntityCandidate,
    build_entity_submit_kwargs,
)
from loreweave_extraction.extractors.event import build_event_submit_kwargs
from loreweave_extraction.extractors.fact import build_fact_submit_kwargs
from loreweave_extraction.extractors.relation import build_relation_submit_kwargs
from loreweave_extraction.pass2 import extract_pass2
from loreweave_extraction.reasoning_wire import reasoning_wire_fields

_PASS2 = "loreweave_extraction.pass2"

_BUILDERS = [
    build_entity_submit_kwargs,
    build_relation_submit_kwargs,
    build_event_submit_kwargs,
    build_fact_submit_kwargs,
]


# ── reasoning_wire_fields ───────────────────────────────────────────


@pytest.mark.parametrize("effort", ["none", None, ""])
def test_wire_fields_default_is_empty(effort):
    """"none"/None/"" emit NO wire fields — byte-identical for non-opt-in
    callers (differs from loreweave_llm.reasoning_fields(effort='none'),
    which emits an explicit disable)."""
    assert reasoning_wire_fields(effort) == {}


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_wire_fields_graded_emits_reasoning_and_template(effort):
    fields = reasoning_wire_fields(effort)
    assert fields["reasoning_effort"] == effort
    assert fields["chat_template_kwargs"] == {"thinking": True, "enable_thinking": True}


# ── per-op submit builders ──────────────────────────────────────────


@pytest.mark.parametrize("builder", _BUILDERS)
def test_builder_default_input_has_no_reasoning_fields(builder):
    """Default (reasoning_effort omitted) ⇒ no reasoning_effort /
    chat_template_kwargs in the input — back-compat byte-identical."""
    kwargs = builder(
        system_prompt="sys", text="body",
        model_source="user_model", model_ref="m", project_id=None,
    )
    assert "reasoning_effort" not in kwargs["input"]
    assert "chat_template_kwargs" not in kwargs["input"]


@pytest.mark.parametrize("builder", _BUILDERS)
def test_builder_default_equals_explicit_none(builder):
    """Passing reasoning_effort='none' is identical to omitting it."""
    base = builder(
        system_prompt="sys", text="body",
        model_source="user_model", model_ref="m", project_id=None,
    )
    explicit_none = builder(
        system_prompt="sys", text="body",
        model_source="user_model", model_ref="m", project_id=None,
        reasoning_effort="none",
    )
    assert base == explicit_none


@pytest.mark.parametrize("builder", _BUILDERS)
def test_builder_graded_input_carries_wire_fields(builder):
    kwargs = builder(
        system_prompt="sys", text="body",
        model_source="user_model", model_ref="m", project_id=None,
        reasoning_effort="high",
    )
    assert kwargs["input"]["reasoning_effort"] == "high"
    assert kwargs["input"]["chat_template_kwargs"] == {
        "thinking": True, "enable_thinking": True,
    }


# ── extract_pass2 threading ─────────────────────────────────────────


def _entity(name: str) -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind="person", aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_extract_pass2_threads_effort_to_every_extractor(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """A graded effort reaches all four extractor calls."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id="u", project_id="p",
        model_source="user_model", model_ref="m",
        llm_client=MagicMock(),
        reasoning_effort="high",
    )

    for mock in (mock_entities, mock_relations, mock_events, mock_facts):
        assert mock.call_args.kwargs["reasoning_effort"] == "high"


@pytest.mark.asyncio
@patch(f"{_PASS2}.extract_facts", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_events", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_relations", new_callable=AsyncMock)
@patch(f"{_PASS2}.extract_entities", new_callable=AsyncMock)
async def test_extract_pass2_default_effort_is_none(
    mock_entities, mock_relations, mock_events, mock_facts,
):
    """Omitting reasoning_effort defaults to "none" on every extractor call."""
    mock_entities.return_value = [_entity("Kai")]
    mock_relations.return_value = []
    mock_events.return_value = []
    mock_facts.return_value = []

    await extract_pass2(
        text="Kai walks.",
        known_entities=[],
        user_id="u", project_id="p",
        model_source="user_model", model_ref="m",
        llm_client=MagicMock(),
    )

    for mock in (mock_entities, mock_relations, mock_events, mock_facts):
        assert mock.call_args.kwargs["reasoning_effort"] == "none"
