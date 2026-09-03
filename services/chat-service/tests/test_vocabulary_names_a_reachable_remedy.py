"""T13-D1 — the vocabulary refusal must name a remedy the SAME TURN can actually reach.

`refusal_message` tells the model how to fix an unknown kind. When the kind is a SYSTEM STANDARD
it named exactly one repair tool: `glossary_adopt_standards`. That tool is in
`INTENT_GATED_SETUP_TOOLS`, which `filter_intent_gated_setup_tools` drops at catalog assembly
unless the turn carries world-setup intent — un-seeded, un-findable AND un-loadable.

MEASURED LIVE 2026-08-13, session 019ffa85, in ONE turn:

    refusal:        "'character' is a STANDARD kind this book has not adopted yet
                     — adopt in ONE call: glossary_adopt_standards(kinds=['character'])."
    withheld_tools: glossary_adopt_standards  stage=intent_gate
                    glossary_propose_kinds    stage=intent_gate
                    glossary_propose_batch    stage=intent_gate

The model read the book's ontology, listed the system standards, could not adopt them, and
retried the identical failing call. That is the exact shape
`filter_intent_gated_setup_tools`'s own docstring describes — "guidance and capability move as
ONE signal" — for which it exempts a pinned RAIL's step tools. A refusal emitted at runtime is
guidance too, and nothing exempted it.

`create_tool` (`glossary_ontology_upsert`) is NOT intent-gated and creates a kind directly, so
the refusal now names it as well. Whether the gate should instead unlock a tool its own refusal
names is DQ-T3 — deliberately not decided here.
"""
from __future__ import annotations

import pytest

from app.agentruntime.vocabulary import VocabularyDecision, refusal_message
from app.services.tool_discovery import INTENT_GATED_SETUP_TOOLS


def _decision(**over) -> VocabularyDecision:
    base = dict(
        tool="glossary_propose_entities", param="items[].kind", vocabulary="BookEntityKind",
        sent=("character",), allowed=(), unknown=("character",), adoptable=("character",),
        custom=(), did_you_mean=(), adopt_tool="glossary_adopt_standards",
        create_tool="glossary_ontology_upsert", outcome="unknown_value",
    )
    base.update(over)
    return VocabularyDecision(**base)


def test_the_adopt_tool_really_is_intent_gated():
    """The premise, asserted rather than assumed — if this stops being true the defect is gone
    and this whole guard should be reconsidered, not silently kept."""
    assert "glossary_adopt_standards" in INTENT_GATED_SETUP_TOOLS


def test_the_create_tool_is_not_intent_gated():
    """The fix only works because this remedy survives the gate."""
    assert "glossary_ontology_upsert" not in INTENT_GATED_SETUP_TOOLS


def test_a_standard_kind_refusal_names_the_reachable_remedy_too():
    msg = refusal_message([_decision()])
    assert "glossary_adopt_standards" in msg          # still named first — it is the better fix
    assert "glossary_ontology_upsert" in msg          # …and a reachable one is always offered


def test_the_refusal_never_offers_ONLY_gated_tools():
    """The invariant, stated over the gate itself rather than over one tool name: whatever the
    message names, at least one named tool must survive INTENT_GATED_SETUP_TOOLS."""
    msg = refusal_message([_decision()])
    named = {t for t in ("glossary_adopt_standards", "glossary_ontology_upsert",
                         "glossary_propose_kinds", "glossary_propose_batch") if t in msg}
    assert named, "the refusal names no repair tool at all"
    reachable = named - set(INTENT_GATED_SETUP_TOOLS)
    assert reachable, (
        f"every repair tool the refusal names is intent-gated ({sorted(named)}), so on a "
        "non-setup turn the model is told to call something the runtime withheld — T13-D1"
    )


def test_a_custom_kind_still_names_the_create_tool_once():
    """CONTROL. The custom branch already named the reachable tool; it must not now be doubled
    or lost."""
    msg = refusal_message([_decision(adoptable=(), custom=("power_system",),
                                     unknown=("power_system",))])
    assert msg.count("glossary_ontology_upsert") == 1


def test_the_book_s_actual_values_are_still_named():
    """CONTROL for the member this message exists for — naming the VALUES, not just the tools."""
    msg = refusal_message([_decision(allowed=("place", "item"))])
    assert "'place'" in msg and "'item'" in msg


@pytest.mark.parametrize("create_tool", [None, ""])
def test_no_fallback_clause_when_the_registry_has_no_create_tool(create_tool):
    """A vocabulary with no create_tool must not emit a dangling sentence."""
    msg = refusal_message([_decision(create_tool=create_tool)])
    assert "create it directly with" not in msg
    assert "glossary_adopt_standards" in msg
