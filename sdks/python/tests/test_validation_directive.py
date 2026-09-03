"""TOOLV2 LOOP #65 — the validation directive's type clause used to lie.

Three services carried a byte-identical copy of this function, each rendering
``(you sent a {type(err["input"]).__name__})`` for EVERY pydantic error. For a ``missing``
error pydantic sets ``input`` to the parent object — the field was never sent, so there is no
value to describe — and the clause reported the type of the arguments dict.

Measured on the corpus before the fix: **79 calls, 7 tools, 16 sessions, and the arguments
were `{}` in 100% of them.** Every rendering of that clause was false. `memory_remember` was
told ``fact_text: Field required (you sent a dict)`` having sent nothing at all.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from loreweave_mcp import validation_directive


class _Args(BaseModel):
    fact_text: str
    fact_type: str
    weight: int = 1


def _err(payload: dict) -> ValidationError:
    with pytest.raises(ValidationError) as exc:
        _Args(**payload)
    return exc.value


def test_A_MISSING_FIELD_IS_NEVER_DESCRIBED_AS_A_VALUE_THE_CALLER_SENT():
    """THE defect. A field that was not sent has no type, and claiming one misattributes the
    cause — which is what makes a caller 'fix' something it never did wrong."""
    got = validation_directive("memory_remember", _err({}))

    assert "you sent a dict" not in got, (
        f"the caller sent no arguments; describing a missing field as a dict is false: {got!r}")
    assert "you sent a" not in got, (
        f"a missing field has no sent value to describe at all: {got!r}")
    assert "`fact_text`" in got and "Field required" in got, got


def test_AN_EMPTY_CALL_IS_TOLD_THAT_IT_WAS_EMPTY():
    """100% of the measured population sent `{}`. 'You sent no arguments' is the one fact that
    separates an empty call from a wrongly-typed one, and it was the fact never stated."""
    got = validation_directive("memory_remember", _err({}))
    assert "no arguments at all" in got, got


def test_A_REAL_TYPE_ERROR_KEEPS_ITS_VALUE_CLAUSE():
    """The clause is correct where `input` really is the offending value. Removing it there
    would trade one lost signal for another — the fix is accuracy, not silence.

    TOOLV2 LOOP #172 sharpened it further: the clause now shows the VALUE rather than its
    type. A caller told "you sent a list" learns nothing it did not already know; shown
    ['not', 'an', 'int'] it can see exactly what it put in the field.
    """
    got = validation_directive("memory_remember", _err(
        {"fact_text": "x", "fact_type": "y", "weight": ["not", "an", "int"]}))

    assert "`weight`" in got, got
    assert "'not', 'an', 'int'" in got, f"the offending value must be visible: {got!r}"
    # ...and a call that DID carry arguments must not be told it sent none.
    assert "no arguments at all" not in got, got


def test_A_MIXED_ERROR_SET_DESCRIBES_EACH_ERROR_ON_ITS_OWN_TERMS():
    """A missing field and a mistyped field in one call are two different faults, and folding
    them into one clause is how the original bug survived: it treated every error identically."""
    got = validation_directive("memory_remember", _err({"weight": "abc"}))

    assert "`fact_text`: Field required" in got, got
    # The mistyped field keeps its value clause -- now showing the VALUE rather than its type
    # (TOOLV2 LOOP #172): 'abc' is what lets the caller see its own mistake; 'a str' is not.
    assert "you sent 'abc'" in got, f"the mistyped field keeps its clause: {got!r}"
    assert "`fact_text`: Field required (you sent" not in got, (
        f"the missing field must not borrow the mistyped one's clause: {got!r}")
    # Not an empty call — it carried `weight`.
    assert "no arguments at all" not in got, got


def test_THE_ERROR_LIST_IS_CAPPED_AND_THE_OVERFLOW_IS_DECLARED():
    """A truncated list that does not say it was truncated reads as the complete set of
    problems, so the caller fixes three things and is surprised by a fourth."""
    class _Wide(BaseModel):
        a: str
        b: str
        c: str
        d: str
        e: str

    with pytest.raises(ValidationError) as exc:
        _Wide()
    got = validation_directive("wide_tool", exc.value, max_errors=3)

    assert "(+2 more)" in got, got


# TOOLV2 LOOP #172 — the clause described the TYPE of what was sent, not the value.
#
# Measured on composition_authoring_run_review with unit_index=-1 against a `minimum: 0` bound:
#
#     `unit_index`: Input should be greater than or equal to 0 (you sent a int)
#
# "a int" is a fact the caller already had. The one it needed was -1. This is the same affordance
# #148 had to hand-roll inside composition-service for uuid parsing ("received '…9fb4-9fb4-…'",
# which is how a model sees its own duplicated group) — except here it belongs in the kit, so every
# Python MCP service gets it from one place.
def test_the_clause_shows_the_value_not_its_type():
    from pydantic import BaseModel, Field, ValidationError

    from loreweave_mcp.errors import validation_directive

    class Args(BaseModel):
        unit_index: int = Field(ge=0)

    try:
        Args(unit_index=-1)
    except ValidationError as exc:
        msg = validation_directive("composition_authoring_run_review", exc)
    assert "-1" in msg, f"the offending value must appear: {msg}"
    assert "you sent a int" not in msg, f"the type clause is back: {msg}"


def test_a_huge_input_falls_back_to_its_type():
    """A refusal that pastes an entire document back at the model is its own failure — the clause
    has to stay one readable line, so the value is only shown while it is short enough to read."""
    from pydantic import BaseModel, Field, ValidationError

    from loreweave_mcp.errors import validation_directive

    class Args(BaseModel):
        name: str = Field(max_length=5)

    try:
        Args(name="x" * 4000)
    except ValidationError as exc:
        msg = validation_directive("some_tool", exc)
    assert "xxxxxxxxxx" not in msg, f"a 4000-char input was pasted into the refusal: {msg[:200]}"
    assert "str of" in msg and "chars" in msg, f"the fallback must still say what arrived: {msg}"


def test_a_missing_field_still_has_no_value_clause():
    """The #-earlier fix this file already guards: for a `missing` error pydantic sets `input` to
    the PARENT object, so ANY rendering of it is false. Showing the value instead of the type must
    not resurrect that on the most common failure there is."""
    from pydantic import BaseModel, ValidationError

    from loreweave_mcp.errors import validation_directive

    class Args(BaseModel):
        needed: str

    try:
        Args()
    except ValidationError as exc:
        msg = validation_directive("some_tool", exc)
    assert "you sent" not in msg.split("You sent no arguments")[0], (
        f"a missing field must not describe a value it never received: {msg}"
    )
