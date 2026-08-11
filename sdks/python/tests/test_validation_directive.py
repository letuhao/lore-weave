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


def test_A_REAL_TYPE_ERROR_KEEPS_ITS_TYPE_CLAUSE():
    """The clause is correct where `input` really is the offending value. Removing it there
    would trade one lost signal for another — the fix is accuracy, not silence."""
    got = validation_directive("memory_remember", _err(
        {"fact_text": "x", "fact_type": "y", "weight": ["not", "an", "int"]}))

    assert "`weight`" in got and "you sent a list" in got, got
    # ...and a call that DID carry arguments must not be told it sent none.
    assert "no arguments at all" not in got, got


def test_A_MIXED_ERROR_SET_DESCRIBES_EACH_ERROR_ON_ITS_OWN_TERMS():
    """A missing field and a mistyped field in one call are two different faults, and folding
    them into one clause is how the original bug survived: it treated every error identically."""
    got = validation_directive("memory_remember", _err({"weight": "abc"}))

    assert "`fact_text`: Field required" in got, got
    assert "you sent a str" in got, f"the mistyped field keeps its (correct) clause: {got!r}"
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
