"""DQ-T5 — OWNER 2026-08-31: "(a) A REFUSAL UNLOCKS THE TOOL IT NAMES, for the rest of that turn."

THE QUESTION IT ANSWERS: how does a NEW book get its first glossary entity?

MEASURED 2026-08-13 across sessions 019ffa85 / 019ffa92 / 019ffa96 on a throwaway book, every
branch tried. A fresh book has no kinds, so `glossary_propose_entities` refuses — and its remedy,
`glossary_adopt_standards`, is intent-gated and was recorded WITHHELD at stage=intent_gate IN THE
SAME TURN AS THE REFUSAL THAT NAMED IT. It stayed withheld even on the explicit prose "Set up my
book — adopt the standard lore categories for it". The glossary had no entry point for a new book.

WHY THE EXISTING MECHANISM DID NOT ALREADY DO IT. `_arm_tools` is "THE one place" that puts a
name on the wire, and the D-FJ-4 path already arms tools named in a refusal. Both were INERT for
a gated tool, for two independent reasons, and fixing either alone changes nothing:

  1. `_tools_named_in_refusal` matches against `cat_index`, which is built from the FILTERED
     catalogue — so a gated name is not in it and is never matched.
  2. `merge_activated_tools` merges NAMES; the schema comes from `discovery_catalog`, which the
     capability floor filtered ONCE before the tool loop — so an armed gated name had no def.

The ruling's own words: "the platform already does exactly this for a pinned rail's step tools,
so the mechanism exists and only its trigger is new." A pinned rail is exempted INSIDE
`filter_intent_gated_setup_tools`; a refusal cannot be, because it happens after that filter has
run. Hence the unlock lives at the arming site.

🔴 SCOPE IS THE POINT. Only a REFUSAL unlocks. A tool named in ordinary prose still cannot open
the floor — that is the over-reach N5a-FULL exists to stop, and its docstring records the cost:
40,597 characters of one repeated paragraph on the Mị Đế dogfood before the author hit Stop.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import _arm_tools, _tools_named_in_refusal  # noqa: E402

GATED = "glossary_adopt_standards"


def _def(name: str) -> dict:
    return {"function": {"name": name, "description": f"{name} does a thing",
                         "parameters": {"type": "object", "properties": {}}}}


def _state():
    return {"activated_tools": [], "dirty": False}


def test_a_gated_tool_named_in_a_refusal_gets_its_DEF_restored():
    """Arming the NAME is not enough — without the def the wire has no schema to advertise."""
    catalog = [_def("glossary_propose_entities")]           # the floor already removed GATED
    active: set[str] = set()
    armed = _arm_tools(
        [GATED], active_tool_names=active, activation_state=_state(),
        discovery_catalog=catalog, context_length=100_000,
        unlockable_gated={GATED: _def(GATED)},
    )
    assert armed == [GATED]
    names = [(d.get("function") or {}).get("name") for d in catalog]
    assert GATED in names, (
        "the gated tool's def was not restored into the turn catalogue, so the armed name has no "
        "schema and nothing reaches the wire — the state DQ-T5 measured"
    )


def test_without_the_unlock_the_arming_is_INERT():
    """🔴 THE ORIGINAL BEHAVIOUR, pinned so the fix cannot be quietly reverted. The name goes into
    the active set either way; only the def decides whether the model can see the tool."""
    catalog = [_def("glossary_propose_entities")]
    active: set[str] = set()
    _arm_tools([GATED], active_tool_names=active, activation_state=_state(),
               discovery_catalog=catalog, context_length=100_000)  # no unlockable_gated
    assert GATED in active, "the name is still armed — that half always worked"
    assert GATED not in [(d.get("function") or {}).get("name") for d in catalog], (
        "a gated def appeared without being unlocked — the capability floor is no longer a floor"
    )


def test_the_refusal_must_be_able_to_MATCH_the_gated_name():
    """The other half, and it is independent: if the recovery index is the FILTERED one, the name
    is never matched and the def-restore above is dead code."""
    refusal = ("This book has no kinds yet. Call glossary_adopt_standards to adopt the standard "
               "lore categories, then try again.")
    filtered_only = {"glossary_propose_entities": _def("glossary_propose_entities")}
    assert _tools_named_in_refusal(refusal, filtered_only, set(),
                                   exclude="glossary_propose_entities") == [], (
        "matched a gated tool against the filtered index — this test's premise is wrong"
    )
    widened = {**filtered_only, GATED: _def(GATED)}
    assert _tools_named_in_refusal(refusal, widened, set(),
                                   exclude="glossary_propose_entities") == [GATED]


def test_an_already_active_tool_is_not_re_armed_and_the_catalog_is_not_duplicated():
    catalog = [_def("glossary_propose_entities"), _def(GATED)]
    active = {GATED}
    armed = _arm_tools([GATED], active_tool_names=active, activation_state=_state(),
                       discovery_catalog=catalog, context_length=100_000,
                       unlockable_gated={GATED: _def(GATED)})
    assert armed == [], "an already-active tool was re-armed"
    assert sum(1 for d in catalog if (d.get("function") or {}).get("name") == GATED) == 1, (
        "the def was appended a second time — the turn catalogue now carries a duplicate schema"
    )


def test_an_unnamed_gated_tool_stays_off_the_wire():
    """🔴 THE TEETH. The unlock is keyed to what a refusal NAMED. Everything else the floor
    removed must stay removed, or this becomes a way to open the gate for the whole turn."""
    catalog = [_def("glossary_propose_entities")]
    active: set[str] = set()
    _arm_tools(["glossary_propose_entities"], active_tool_names=active,
               activation_state=_state(), discovery_catalog=catalog, context_length=100_000,
               unlockable_gated={GATED: _def(GATED), "glossary_book_sync_apply": _def("x")})
    names = [(d.get("function") or {}).get("name") for d in catalog]
    assert GATED not in names and len(names) == 1, (
        f"an un-named gated tool was unlocked: {names} — the floor is now open to anything in "
        "the unlockable map, not to what the refusal actually said"
    )
