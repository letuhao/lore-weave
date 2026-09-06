"""The temporal-capability rule, now owned by the service that owns the substrate (T26).

These tests came from `knowledge-gateway/test/temporal.spec.ts`. They did not move because
Python is nicer: they moved because the gateway was deciding, from its OWN environment,
whether a graph it does not own could answer a story-time question. A gateway with
`KG_TEMPORAL_ENABLED=true` in front of an unmigrated knowledge-service advertised
`ordinal_valid_time` and forwarded `as_of` to a substrate answering in transaction time —
a spoiler leak produced by two processes disagreeing about a boolean.
"""

from __future__ import annotations

import pytest

from app.kal.temporal import kg_as_of_or_drop, temporal_capability


@pytest.fixture
def kg_temporal(monkeypatch):
    def _set(enabled: bool):
        from app.config import settings

        monkeypatch.setattr(settings, "kg_temporal_enabled", enabled)

    return _set


def test_glossary_is_always_ordinal_valid_time(kg_temporal):
    """Not a config knob, and it should not become one: `entity_facts` carries half-open
    story intervals by construction (foundation F1). A deployment cannot turn that off, so
    reporting it as conditional would invite a caller to handle a state that cannot occur."""
    for enabled in (True, False):
        kg_temporal(enabled)
        assert temporal_capability()["glossary"] == "ordinal_valid_time"


def test_the_kg_reports_what_it_can_actually_honour(kg_temporal):
    kg_temporal(True)
    assert temporal_capability()["kg"] == "ordinal_valid_time"
    kg_temporal(False)
    assert temporal_capability()["kg"] == "temporal_unsupported"


def test_as_of_is_dropped_rather_than_answered_dishonestly(kg_temporal):
    """Degrade-safe means losing PRECISION, not losing the plot. Answering untimed returns
    more than was asked for; answering with transaction-time rows dressed as story-time ones
    hands the reader events that have not happened yet."""
    kg_temporal(True)
    assert kg_as_of_or_drop(500) == 500

    kg_temporal(False)
    assert kg_as_of_or_drop(500) is None


def test_dropping_is_not_an_error(kg_temporal):
    """A caller asking for a story position the KG cannot serve is the normal state of a
    graph mid-migration. Raising would take out every timeline-aware read the moment a
    deployment lagged, which is a worse failure than the imprecision it prevents."""
    kg_temporal(False)
    assert kg_as_of_or_drop(500) is None  # no exception
    assert kg_as_of_or_drop(None) is None


def test_no_as_of_is_unaffected_by_the_flag(kg_temporal):
    for enabled in (True, False):
        kg_temporal(enabled)
        assert kg_as_of_or_drop(None) is None
