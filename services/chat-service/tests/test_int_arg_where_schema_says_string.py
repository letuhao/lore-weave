"""TOOL DEEP-DIVE `book_chapter_save_draft` — a JSON number where the schema declares string-only.

🔴 MEASURED. `book_chapter_save_draft.chapter` is declared `type: "string"`, and its OWN description
tells the caller to pass "its NUMBER (e.g. '1', 'chapter 3')". The model reads "number", sends the
JSON number `1`, and the gateway refuses the call before the tool ever runs:

    validating "arguments": validating root: validating /properties/chapter:
        type: 1 has type "integer", want "string"

Recorded 2026-08-04 and again 2026-08-12, so it recurs. The 2026-08-12 instance is the costly one:
it came one step AFTER the same turn had finally supplied the prose, so a complete, correct write
was blocked on the container of a value that was already right.

Same family as D-FJ-7 (`["vi"]` for a scalar enum) and repaired with the same discipline: the
narrowest rule that fixes the measured shape, declining anything it cannot reason about.
"""

from app.services.stream_service import _stringify_int_args_declared_string as fix


def _def(props: dict) -> dict:
    return {"function": {"name": "t", "parameters": {"type": "object", "properties": props}}}


SAVE_DRAFT = _def({
    "book_id": {"type": "string"},
    "chapter": {"type": "string"},
    "base_version": {"type": "integer"},
    "body": {"type": "string"},
})


def test_the_measured_call_is_repaired():
    """🔴 The exact recorded arguments."""
    args = {"book_id": "019f9a02-f3a3-7cf5-b6e8-a7891bf3a249", "chapter": 1,
            "body": "The smell of old parchment", "commit_message": "Drafting the opening scene."}
    assert fix(args, SAVE_DRAFT) == ["chapter"]
    assert args["chapter"] == "1", "the selector is still an integer, so the gateway still refuses"
    assert args["body"] == "The smell of old parchment", "an unrelated argument was touched"


def test_an_INTEGER_declared_param_is_left_alone():
    """THE CONTROL that matters most. `base_version` really is an integer; coercing it to "1" would
    turn a legal call into a rejected one — this repair inventing the very failure it exists to
    remove."""
    args = {"base_version": 3, "chapter": 2}
    assert fix(args, SAVE_DRAFT) == ["chapter"]
    assert args["base_version"] == 3
    assert args["chapter"] == "2"


def test_a_param_that_accepts_EITHER_is_left_alone():
    """A schema that admits a number is not confused — it is being handed a legal value."""
    args = {"n": 5}
    assert fix(args, _def({"n": {"type": ["string", "integer"]}})) == []
    assert args["n"] == 5


def test_an_optional_string_still_repairs():
    """`type: ["null","string"]` and pydantic's `anyOf` are how OPTIONAL string params actually
    render in this catalogue. Declining unions outright would have left the repair unable to fire on
    most of the surface — the mistake D-FJ-7's first draft made."""
    for spec in ({"type": ["null", "string"]},
                 {"anyOf": [{"type": "string"}, {"type": "null"}]}):
        args = {"chapter": 7}
        assert fix(args, _def({"chapter": spec})) == ["chapter"], spec
        assert args["chapter"] == "7"


def test_a_bool_is_not_a_container_slip():
    """Python calls bool an int; the schema does not. True -> "True" is a guess about intent, and a
    wrong coercion corrupts a write instead of refusing it."""
    args = {"chapter": True}
    assert fix(args, SAVE_DRAFT) == []
    assert args["chapter"] is True


def test_a_float_is_declined():
    """1.0 -> "1.0" is lossy and would not match a selector like "1" anyway — a repair that emits
    parseable-but-wrong output is worse than the refusal it replaces."""
    args = {"chapter": 1.0}
    assert fix(args, SAVE_DRAFT) == []
    assert args["chapter"] == 1.0


def test_a_richer_schema_is_declined():
    """items/$ref/allOf/nested unions mean the schema says more than this rule can reason about."""
    for spec in ({"type": "string", "items": {"type": "string"}},
                 {"$ref": "#/defs/x"},
                 {"allOf": [{"type": "string"}]},
                 {"anyOf": [{"anyOf": [{"type": "string"}]}, {"type": "null"}]}):
        args = {"chapter": 1}
        assert fix(args, _def({"chapter": spec})) == [], spec
        assert args["chapter"] == 1


def test_an_undeclared_param_is_never_touched():
    """A tool with additionalProperties:false would reject an arg we invented a type for."""
    args = {"mystery": 4}
    assert fix(args, SAVE_DRAFT) == []
    assert args["mystery"] == 4


def test_a_string_value_is_left_exactly_as_sent():
    args = {"chapter": "3"}
    assert fix(args, SAVE_DRAFT) == []
    assert args["chapter"] == "3"


def test_the_repair_is_actually_WIRED_INTO_dispatch():
    """🔴 Guard the CALL SITE, not the helper. Every assertion above passes against a repair that
    is never called — which is the same as not having it. It must also sit BEFORE the
    missing-argument interception and the dispatch, exactly where its D-FJ-7 sibling does, or the
    call is refused before the repair can fire.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    call = "_stringified = _stringify_int_args_declared_string(args_obj, _tool_def_for_args)"
    assert call in body, "the repair is defined but never called, so nothing is ever repaired"
    at = body.index(call)
    sibling = body.index("_unwrapped = _unwrap_single_element_scalar_args(args_obj,")
    assert sibling < at, "the two container repairs have drifted apart"
    assert at < body.index("_missing_args ="), (
        "the repair runs after the missing-argument interception, so the call is already refused"
    )
