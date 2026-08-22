"""D-REFUSAL-NAMES-A-TOOL-THE-TURN-CANNOT-SEE — a refusal that says "call X first" must arm X.

🔴 THE DEFECT. `_missing_args_message` writes instructions like *"NOT a name — if you have the
map's NAME, call world_map_list first and match it to get the id"*, and its own comment claimed
that naming a tool also made it reachable. It did not. `_tools_named_in_refusal` + the activation
mutation ran on the DISPATCH result; the missing-required-argument arm returns before dispatch, so
for the largest refusal class on this platform (266 failures / 87 sessions) the sentence armed
nothing. The runtime told the model to call a tool that was not on the turn.

MEASURED 2026-08-22 — 35 live runs, 7 tools with a supplier, K=5, reading `advertised` off each
turn's own agentSurface event:

    supplier advertised & called          8
    supplier advertised & NOT called      0    <- the cell "the model will not walk it" needs
    NOT advertised & called               0
    NOT advertised & NOT called          27

35/35 agreement. The model walks a supplier chain exactly when it can see the supplier — so the
finding recorded against the MODEL (D-CLAIMED-ACTION-WITH-NO-FOLLOW-THROUGH: *"I'll find the ID for
you now. One moment."*) was a property of the SURFACE.

WHAT THESE TESTS PIN, and why each would have gone red on the original:
  * the arming is ONE function. The mutation was copied verbatim at two sites and absent at the
    third; a fourth copy is how this recurs, so `_arm_tools` is asserted to be the only writer.
  * `_arm_tools` does not re-arm what is already active, and reports what it actually armed —
    a caller that says "X is now available" when it armed nothing is the same false statement in
    the other direction.
  * a refusal naming a catalogue tool yields that tool from `_tools_named_in_refusal`, whole-word.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services.stream_service import _arm_tools, _missing_args_message, _tools_named_in_refusal

SRC = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"


def test_the_refusal_for_a_declared_id_names_its_supplier():
    """The message must contain the supplier NAME — arming keys off exactly this text."""
    msg = _missing_args_message(
        "world_map_delete", ["map_id"], {},
        {"map_id": {"description": (
            "the map to delete (UUID; you must own it). NOT a name — if you have the map's "
            "NAME, call world_map_list first and match it to get the id."
        )}},
    )
    assert "world_map_list" in msg


def test_a_refusal_naming_a_catalogue_tool_yields_it():
    msg = _missing_args_message(
        "world_map_delete", ["map_id"], {},
        {"map_id": {"description": "NOT a name — call world_map_list first to get the id."}},
    )
    got = _tools_named_in_refusal(msg, {"world_map_list": {}, "world_map_delete": {}}, set())
    assert "world_map_list" in got


def test_a_refusal_never_arms_the_tool_that_just_failed():
    """🔴 CAUGHT LIVE, by this feature's own log line, on the first batch after it shipped:

        armed recovery tool(s) ['composition_arc_template_edit'] named in
        composition_arc_template_edit's missing-argument refusal

    Every message `_missing_args_message` builds OPENS with the failing tool's name, so the tool is
    always a candidate against its own refusal. That is not a harmless no-op: candidates are ranked
    longest-name-first into `_RECOVERY_ARM_CAP` = 3, and a tool's own name is usually among the
    longest strings in its own refusal — so the failure takes a top slot and can push out the
    supplier the sentence is steering toward.

    Built from the REAL refusal rather than a hand-written string, because the hand-written string
    is what hid this: I wrote the fixture with only the supplier in it, and the message the platform
    actually emits contains both names.
    """
    msg = _missing_args_message(
        "world_map_delete", ["map_id"], {},
        {"map_id": {"description": "NOT a name — call world_map_list first to get the id."}},
    )
    assert "world_map_delete" in msg, "the refusal names the failing tool — that is the trap"
    catalog = {"world_map_list": {}, "world_map_delete": {}}

    unguarded = _tools_named_in_refusal(msg, catalog, set())
    assert "world_map_delete" in unguarded, (
        "the fixture no longer reproduces the trap, so the guard below proves nothing"
    )

    guarded = _tools_named_in_refusal(msg, catalog, set(), exclude="world_map_delete")
    assert guarded == ["world_map_list"], (
        f"a refusal must arm the supplier it names and never the call that just failed: {guarded}"
    )


def test_both_refusal_call_sites_exclude_the_failing_tool():
    """CALL-SITE GUARD. The parameter above defaults to None, so the helper stays green while every
    caller keeps arming the failure — which is exactly the state this feature shipped in."""
    src = SRC.read_text(encoding="utf-8")
    # `def _tools_named_in_refusal(` matches the same pattern — its own signature is not a call
    # site, and counting it made this gate red against correct code on its first run.
    sites = [m for m in re.finditer(r"(?<!def )_tools_named_in_refusal\(\s*\n", src)]
    assert len(sites) >= 2, f"expected both refusal call sites, found {len(sites)}"
    for m in sites:
        call = src[m.start():m.start() + 260]
        assert 'exclude=c["name"]' in call, (
            "a refusal call site does not exclude the failing tool:\n" + call[:200]
        )


def test_arming_reports_only_what_it_actually_armed():
    """A caller that announces a tool it did not arm makes the same false claim, reversed."""
    active = {"world_map_list"}
    state = {"activated_tools": [], "dirty": False}
    again = _arm_tools(
        ["world_map_list"], active_tool_names=active, activation_state=state,
        discovery_catalog=[], context_length=None,
    )
    assert again == [], "an already-active tool must not be reported as newly armed"
    assert state["dirty"] is False, "nothing was armed, so nothing became dirty"

    fresh = _arm_tools(
        ["world_map_list", "world_list"], active_tool_names=active, activation_state=state,
        discovery_catalog=[], context_length=None,
    )
    assert fresh == ["world_list"]
    assert "world_list" in active
    assert state["dirty"] is True


def test_arming_tolerates_no_activation_state():
    """The turn-local set is the load-bearing half; persistence is optional."""
    active: set[str] = set()
    assert _arm_tools(
        ["world_list"], active_tool_names=active, activation_state=None,
        discovery_catalog=[], context_length=None,
    ) == ["world_list"]
    assert "world_list" in active


def test_the_missing_argument_arm_arms_what_its_refusal_names():
    """🔴 THE FALSIFIER. RED on the original: that arm built the message and `continue`d.

    Read against the source rather than through a full turn because the arm sits inside an
    ~800-line async generator with a dozen upstream dependencies, and a test that has to build all
    of them tests the scaffolding. What is asserted is the thing that was missing: between building
    `_ma_msg` and appending it to `working`, this arm passes the text through
    `_tools_named_in_refusal` and `_arm_tools`.

    Anchored to the `working.append` that carries `missing_required_args`, so it cannot be
    satisfied by the arming that already existed on the dispatch path 700 lines below.
    """
    src = SRC.read_text(encoding="utf-8")
    anchor = src.find('"error": "missing_required_args"')
    assert anchor > 0, "the missing_required_args result is gone — retarget this test"
    # The window from the message being built to the result being appended.
    start = src.rfind("_ma_msg = _missing_args_message", 0, anchor)
    assert start > 0
    window = src[start:anchor]
    assert "_tools_named_in_refusal" in window, (
        "the missing-argument refusal names a supplier and does not arm it — the model is being "
        "told to call a tool that is not on the turn"
    )
    assert "_arm_tools" in window, "the named tools are found but never put on the wire"


def test_arming_the_wire_has_exactly_one_writer():
    """ARMING has one writer. Explicit ACTIVATION is a different mechanism and is left alone.

    🔴 THE FIRST VERSION OF THIS GATE OVER-REACHED AND I ONLY FOUND OUT BY RUNNING IT. It asserted
    that EVERY `merge_activated_tools` call goes through `_arm_tools` and named 7 sites. Four are
    not arming at all — `tool_load`/`find_tools` matched sets and workflow step tools, which
    activate what the caller explicitly asked for. One of those (the workflow step set) carries a
    comment saying it deliberately persists the FULL requested set rather than the turn-capped
    subset, and `_arm_tools` filters by `not in active_tool_names` — so "consolidating" it would
    have changed behaviour the comment exists to protect.

    The discriminator is the filter, not the call: ARMING computes its candidates as *names not
    already active*, because it is putting something on the wire that the model could not see.
    Explicit activation does not filter — it activates what was asked for. So the gate is scoped to
    sites carrying the arming signature, and the four activation sites are correctly ignored.
    """
    src = SRC.read_text(encoding="utf-8")
    body_start = src.find("def _arm_tools(")
    assert body_start > 0
    body_end = src.find("\ndef ", body_start + 1)
    helper, outside = src[body_start:body_end], src[:body_start] + src[body_end:]
    assert "not in active_tool_names" in helper, "the helper lost the arming filter"

    stray = []
    for m in re.finditer(r"activated_tools\"\]\s*=\s*merge_activated_tools", outside):
        window = outside[max(0, m.start() - 600):m.start()]
        if "not in active_tool_names" in window:
            stray.append(outside[:m.start()].count("\n") + 1)
    assert not stray, (
        f"arming site(s) outside _arm_tools at line(s) {stray} — a path that computes "
        "'names not already active' and then widens the wire itself is a private copy of the "
        "arming decision, which is how the missing-argument refusal came to arm nothing"
    )


def test_the_gate_above_can_still_fail():
    """A gate that cannot go red is decoration — so prove this one discriminates.

    The previous test passes over the real source. Here the same rule is executed against a
    synthetic module containing one arming site written the old way; if the rule cannot catch that,
    it cannot catch a regression either.
    """
    fake = (
        'def _arm_tools(names):\n    fresh = [n for n in names if n not in active_tool_names]\n'
        '\ndef other():\n'
        '    armed = [n for n in cands if n not in active_tool_names]\n'
        '    if armed:\n'
        '        state["activated_tools"] = merge_activated_tools(state["activated_tools"], armed)\n'
    )
    body_start = fake.find("def _arm_tools(")
    body_end = fake.find("\ndef ", body_start + 1)
    outside = fake[:body_start] + fake[body_end:]
    caught = [
        m.start() for m in re.finditer(r'activated_tools"\]\s*=\s*merge_activated_tools', outside)
        if "not in active_tool_names" in outside[max(0, m.start() - 600):m.start()]
    ]
    assert caught, "the rule cannot see a hand-rolled arming site, so it guards nothing"


@pytest.mark.parametrize("name,text,expected", [
    # whole-word, never substring: the guard `_tools_named_in_refusal` documents.
    ("kg_build", "call kg_build_wiki first", False),
    ("kg_build_wiki", "call kg_build_wiki first", True),
])
def test_arming_matches_whole_names(name, text, expected):
    got = _tools_named_in_refusal(text, {name: {}}, set())
    assert (name in got) is expected
