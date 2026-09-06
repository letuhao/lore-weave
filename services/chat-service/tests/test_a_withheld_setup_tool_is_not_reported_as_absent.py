"""DQ-T3 — a gated tool must be reported as WITHHELD, never as non-existent.

MEASURED 2026-08-13. `filter_intent_gated_setup_tools` drops five glossary tools
(adopt_standards, propose_kinds, plan, propose_batch, book_sync_apply) at CATALOG ASSEMBLY unless
the turn is world-setup — so they are un-seeded, un-findable AND un-loadable. That is deliberate
(N5a-FULL, the confirmed over-reach) and it IS instrumented via record_surface_withheld
(stage='intent_gate') — but only into telemetry the model never sees. From the model's side they
are indistinguishable from tools that do not exist, and it says so to the user.

Owner's decision: option (a) — stamp them the way T7-D2 stamps always-on tools, naming the gate
and how to open it.

🔴 THE OPPOSITE ERROR IS ALSO MEASURED AND IT IS WORSE. Naming a tool the capability floor had
made unreachable produced 40,597 characters of ONE REPEATED PARAGRAPH on the dogfood book before
the author hit Stop. That is option (b)'s entire case, and it is why the wording is tested here as
carefully as the presence of the stamp: this must never read as "here is a tool, go get it". It
must say the tools are not callable, that the model cannot open the gate itself, and that the way
out is to ASK THE USER — a route that is not a retry.

This is the same class the file already handles twice: `always_available` (T7-D2, the exclusion
that emptied a category) and `provider_unavailable` (an outage making non-existence unknowable).
A listing that omits without saying so reads as a complete, healthy answer.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services import instrument  # noqa: E402
from app.services.tool_discovery import (  # noqa: E402
    INTENT_GATED_SETUP_TOOLS,
    filter_intent_gated_setup_tools,
    tool_list_result,
    tool_load_result,
)

SETUP_INTENT_SKILL = "glossary_shaping"


def _tool(name: str, desc: str = "d") -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": {}},
        "_meta": {"tier": "W"},
    }}


#: A catalog holding the gated tools plus one ordinary glossary tool, before the gate runs.
FULL = [_tool(n) for n in sorted(INTENT_GATED_SETUP_TOOLS)] + [_tool("glossary_search")]


@pytest.fixture(autouse=True)
def _no_instrument_residue():
    """🔴 `filter_intent_gated_setup_tools` RECORDS what it withheld into the instrument's
    module-level sink, and `arm_turn_surface` only releases a previous registration when that
    sink is EMPTY. Computing the gated catalogs at import time therefore left rows behind and
    broke four unrelated `test_cp0_instrument` cases — green in isolation, red in the full run,
    which is the worst shape a test failure can have.

    `arm_turn_surface` cannot be the cleanup: it deliberately ADOPTS an existing sink rather than
    replacing it, because a narrowing that predates its sink is lost, not late. So the isolation
    is the ContextVar's own save/restore — this file's rows never leave this file."""
    token = instrument.surface_withheld.set(None)
    try:
        yield
    finally:
        instrument.surface_withheld.reset(token)


def _gated() -> list[dict]:
    """What an ORDINARY turn actually gets — the gate has removed the five."""
    return filter_intent_gated_setup_tools(FULL, injected_skill_codes=[])


def _open() -> list[dict]:
    """What a WORLD-SETUP turn gets — the gate returns the catalog unchanged."""
    return filter_intent_gated_setup_tools(FULL, injected_skill_codes=[SETUP_INTENT_SKILL])


def test_the_gate_really_removes_them_so_the_premise_holds():
    """CONTROL. If the gate stopped dropping them, every test below would pass vacuously — the
    stamp would be absent because there is nothing to withhold, not because it works."""
    names = {t["function"]["name"] for t in _gated()}
    assert not (names & INTENT_GATED_SETUP_TOOLS), "the gate must have dropped them"
    assert {t["function"]["name"] for t in _open()} >= INTENT_GATED_SETUP_TOOLS


def test_the_listing_names_what_it_withheld():
    """THE FALSIFIER. Before this, the five were simply absent and the listing read complete."""
    payload = tool_list_result(_gated(), "glossary")
    held = payload.get("withheld_pending_setup_intent")
    assert held, "a listing that omits without saying so reads as a complete, healthy answer"
    assert set(held["tools"]) == INTENT_GATED_SETUP_TOOLS


def test_a_setup_turn_stamps_nothing_because_nothing_is_withheld():
    """The stamp is derived from ABSENCE, not from re-evaluating the gate — so on a turn where
    the gate stood down there is nothing to report, and the payload must be unchanged."""
    payload = tool_list_result(_open(), "glossary")
    assert "withheld_pending_setup_intent" not in payload
    assert {t["name"] for t in payload["tools"]} >= INTENT_GATED_SETUP_TOOLS


def test_an_unrelated_category_is_not_stamped():
    """A `book` listing must not carry a glossary gate notice — noise on every listing is how a
    stamp stops being read at all."""
    assert "withheld_pending_setup_intent" not in tool_list_result(_gated(), "book")


def test_tool_load_stops_asserting_the_tool_does_not_exist():
    """THE SECOND HALF, and the one that actually reaches the user. `not_found` ASSERTS
    non-existence — the file already records that exact lie costing an incident during a provider
    outage. A gated name is 'not on THIS turn', which is a different sentence."""
    payload, activated = tool_load_result(_gated(), name="glossary_adopt_standards")
    assert "not_found" not in payload, "a gated tool is withheld, not absent"
    assert payload["withheld_pending_setup_intent"]["tools"] == ["glossary_adopt_standards"]
    assert activated == []


def test_a_genuinely_unknown_name_is_still_not_found():
    """The stamp must not swallow real non-existence — an invented name is still an honest
    `not_found`, or the model loses the signal that it guessed."""
    payload, _ = tool_load_result(_gated(), names=["glossary_adopt_standards", "no_such_tool_xyz"])
    assert payload["not_found"] == ["no_such_tool_xyz"]
    assert payload["withheld_pending_setup_intent"]["tools"] == ["glossary_adopt_standards"]


class TestTheWordingCannotRestartTheRetryLoop:
    """40,597 characters of one repeated paragraph is what the wrong wording costs. These pin the
    three properties that make this a route OUT rather than an invitation to retry."""

    def _held(self):
        return tool_list_result(_gated(), "glossary")["withheld_pending_setup_intent"]

    def test_it_says_plainly_they_are_not_callable_now(self):
        blob = " ".join(str(v) for v in self._held().values()).lower()
        assert "not callable on this turn" in blob

    def test_it_says_the_model_cannot_open_the_gate_itself(self):
        blob = " ".join(str(v) for v in self._held().values()).lower()
        assert "cannot enable them yourself" in blob, (
            "without this the model treats the gate as something to keep trying"
        )

    def test_it_gives_a_non_retry_route_out(self):
        blob = " ".join(str(v) for v in self._held().values()).lower()
        assert "do not retry" in blob
        assert "ask whether they want to start world setup" in blob, (
            "the move is to ask the USER; a stamp with no next action is an invitation to retry"
        )

    def test_it_forbids_the_false_report_it_exists_to_stop(self):
        blob = " ".join(str(v) for v in self._held().values()).lower()
        assert "do not tell the user they do not exist" in blob


def test_both_halves_describe_the_same_gate():
    """One gate, one description. Two copies drift, and a listing that says one thing while the
    load says another is worse than either alone."""
    listed = tool_list_result(_gated(), "glossary")["withheld_pending_setup_intent"]
    loaded, _ = tool_load_result(_gated(), name="glossary_plan")
    held = loaded["withheld_pending_setup_intent"]
    for key in ("why", "how_to_open", "do"):
        assert listed[key] == held[key]
