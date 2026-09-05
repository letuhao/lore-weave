"""`value: false` is an ANSWER, not an absence. The arg check read it as missing.

🔴 FOUND 2026-08-22 BY A CONTROL THAT REFUTED ITS OWN HYPOTHESIS.

`settings_model_set_active` and `registry_set_skill_enabled` were each called 5/5 through the real
chat path and failed 5/5 with *"is missing required argument(s): ['value']"*, then hit the
blank-args cap. `settings_model_set_favorite` declares the SAME shape — a required bare boolean
with no default — and passed. The obvious reading was that the model omits the argument, and the
difference looked like "mark as a favourite" needing **true** while "deactivate" and "turn off"
need **false**.

So the hypothesis was: *the model omits a required boolean when the correct value is false.* One
tool, one fixture, two arms differing only in which value the sentence implies.

THE CONTROL KILLED IT. The false arm's RECORDED ARGUMENTS were
``{"user_model_id": "…", "value": false}`` — the model supplied the boolean, correctly, every
time — and the platform still answered "missing required argument(s): ['value']". The model was
never at fault.

    _missing_required_names:  return [r for r in required if not args_obj.get(r)]

A TRUTHINESS test where presence was meant. `not False` is `True`, so a legitimate `false` is
reported absent, the repair message tells the model to supply what it already sent, it retries
identically, and the blank-args cap then stops the turn. On one of those turns the model went on
to tell the author *"I've deactivated Nemotron-3 Nano for you"* — a false claim of a write, caused
by a check that discarded the correct argument.

BLAST RADIUS, swept from the live catalogue rather than guessed: **37 required arguments across 36
tools** can legitimately be falsy —

    boolean  6   `false` unreachable: registry_set_skill_enabled.enabled, settings_model_set_active.value,
                 book_chapter_set_kg_exclude.kg_exclude, plan_review_checkpoint.approved, …
    integer  10  `0` unreachable: composition_authoring_run_accept_unit.unit_index (the FIRST unit),
                 expected_version (optimistic-concurrency zero), …
    number   2   world_map_add_marker.x / .y — a pin cannot be placed on the left or top edge
    array    19  `[]` unreachable: book_chapter_bulk_create.chapters, glossary_book_sync_apply.items, …

THE INVARIANT: presence is `in`, not truthiness. An argument that was SENT is present whatever its
value. The one exception is deliberate and is the reason the check existed at all — a required
STRING that is empty or whitespace really is blank, and catching that is what the blank-args cap
is for.

WHAT THIS DOES NOT FIX: it does not make the model choose the right value, and it does not touch
the cap's counting. It only stops a correct answer being classified as an absence.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "services" / "stream_service.py"
sys.path.insert(0, str(ROOT))


def _fn():
    """Load just the helper, without importing the whole service (which needs a live stack)."""
    import ast
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_missing_required_names":
            mod = ast.Module(body=[node], type_ignores=[])
            ns: dict = {}
            exec(compile(mod, str(SRC), "exec"), ns)  # noqa: S102 — one pure function, no imports
            return ns["_missing_required_names"]
    pytest.fail("_missing_required_names not found in stream_service.py")


def _tool(name: str, ptype, required: list[str]) -> dict:
    return {"function": {"name": "t", "parameters": {
        "type": "object", "properties": {name: {"type": ptype}}, "required": required}}}


def test_a_required_boolean_set_to_false_is_present():
    """The original instance, verbatim: settings_model_set_favorite with value=false."""
    missing = _fn()({"user_model_id": "u", "value": False},
                    _tool("value", "boolean", ["user_model_id", "value"]))
    assert missing == [], (
        "a required boolean sent as false was reported missing — the model supplied the correct "
        "answer and the platform told it to supply the answer"
    )


@pytest.mark.parametrize("ptype, value, why", [
    ("boolean", False, "turn off / deactivate / unfavourite"),
    ("integer", 0, "unit_index 0 is the FIRST unit; expected_version 0 is a real version"),
    ("number", 0.0, "world_map_add_marker.x=0 is the left edge of the map"),
    ("array", [], "book_chapter_bulk_create.chapters=[] is the empty-import case"),
])
def test_every_falsy_kind_that_a_real_tool_declares_is_present(ptype, value, why):
    assert _fn()({"a": value}, _tool("a", ptype, ["a"])) == [], why


def test_an_absent_required_argument_is_still_missing():
    """The check must keep doing its job — this is what would break if `in` were used naively
    without keeping the blank-string case."""
    assert _fn()({}, _tool("a", "boolean", ["a"])) == ["a"]
    assert _fn()({"a": None}, _tool("a", "boolean", ["a"])) == ["a"]


def test_a_blank_required_string_is_still_missing():
    """The reason the truthiness check existed. A required string that is empty or whitespace IS
    blank, and the blank-args cap depends on seeing it."""
    assert _fn()({"q": ""}, _tool("q", "string", ["q"])) == ["q"]
    assert _fn()({"q": "   "}, _tool("q", "string", ["q"])) == ["q"]
    assert _fn()({"q": "x"}, _tool("q", "string", ["q"])) == []


def test_an_unknown_tool_def_still_blocks_nothing():
    """Unchanged behaviour, asserted so the fix cannot quietly widen the check's reach."""
    assert _fn()({"anything": False}, None) == []
