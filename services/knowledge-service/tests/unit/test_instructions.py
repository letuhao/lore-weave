"""K18.6 — unit tests for the CoT instructions block builder."""
from __future__ import annotations

import pytest

from app.context.formatters.instructions import build_instructions_block
from app.context.intent.classifier import Intent


@pytest.mark.parametrize(
    "intent",
    [Intent.SPECIFIC_ENTITY, Intent.RELATIONAL, Intent.HISTORICAL,
     Intent.RECENT_EVENT, Intent.GENERAL],
)
def test_always_emits_base_and_intent_hint(intent):
    text = build_instructions_block(
        intent, has_facts=False, has_passages=False, has_absences=False,
    )
    assert "authoritative context" in text  # base line
    # One of the intent hints must be present.
    assert any(
        keyword in text
        for keyword in (
            "specific named entity", "relationship between entities",
            "earlier events", "current moment", "general background",
        )
    )


def test_facts_line_toggles_on_has_facts():
    off = build_instructions_block(
        Intent.GENERAL, has_facts=False, has_passages=False, has_absences=False,
    )
    on = build_instructions_block(
        Intent.GENERAL, has_facts=True, has_passages=False, has_absences=False,
    )
    assert "<facts>" not in off
    assert "<facts>" in on
    assert "<negative>" in on  # negative-fact guardrail


def test_passages_line_toggles_on_has_passages():
    off = build_instructions_block(
        Intent.GENERAL, has_facts=False, has_passages=False, has_absences=False,
    )
    on = build_instructions_block(
        Intent.GENERAL, has_facts=False, has_passages=True, has_absences=False,
    )
    assert "<passages>" not in off
    assert "<passages>" in on


def test_absences_line_toggles_on_has_absences():
    off = build_instructions_block(
        Intent.GENERAL, has_facts=False, has_passages=False, has_absences=False,
    )
    on = build_instructions_block(
        Intent.GENERAL, has_facts=False, has_passages=False, has_absences=True,
    )
    assert "<no_memory_for>" not in off
    assert "<no_memory_for>" in on


def test_historical_intent_mentions_earlier_events():
    text = build_instructions_block(
        Intent.HISTORICAL, has_facts=True, has_passages=False, has_absences=False,
    )
    assert "earlier events" in text
    assert "older" in text


def test_specific_entity_intent_prioritizes_entity():
    text = build_instructions_block(
        Intent.SPECIFIC_ENTITY, has_facts=True, has_passages=True,
        has_absences=False,
    )
    assert "specific named entity" in text


def test_locale_parameter_accepted_but_no_op():
    """Track 1 is English-only — locale is reserved for future i18n but
    must not raise. Verifies the signature stability across locales."""
    en = build_instructions_block(
        Intent.GENERAL, has_facts=True, has_passages=True, has_absences=True,
        locale="en",
    )
    vi = build_instructions_block(
        Intent.GENERAL, has_facts=True, has_passages=True, has_absences=True,
        locale="vi",  # not wired yet; must still return English
    )
    assert en == vi  # same English output
