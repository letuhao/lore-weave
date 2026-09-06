"""D-THE-MODEL-FABRICATES-A-MONEY-VALUE-ON-A-SPECULATIVE-FIRST-CALL.

    THE INVARIANT. A SPEND CEILING THE AUTHOR NEVER MENTIONED IS NOT THE MODEL'S TO CHOOSE.
    It is their money and their decision, and unlike a wrong id it cannot be detected by
    looking at the value — $50 is as well-formed as $5.

Asked only "Start an authoring run for this book — begin autopilot.", the model's FIRST call
carried `budget_usd=50`. The row records what actually saved the author: the call refused
because `pause_after_each_unit` was ALSO missing, so nothing was spent — "the guard that saved
it was an unrelated missing argument, not anything about money". Had the model filled both in,
a Tier-W card would have been minted for a $50 run nobody asked for, and a confirm card defends
against the wrong failure here: the author sees a plausible-looking run and the number on it is
invented.

🔴 THE PRECISION QUESTION THE ROW LEFT OPEN, MEASURED over every `budget_usd` call in the live
store — 16 of them, and the separation is exact:

    the author mentioned money    7 calls    budget_usd=5, and they had said "5 dollars"
    the author said NOTHING       9 calls    budget_usd = 10 (x4), 5 (x3), 50 (x2)

No overlap. The row's own candidate list — "a schema marker for author-only values; a
server-side default; a pre-dispatch guard on money-typed arguments" — said each "carries a
precision question that has not been measured". This is that measurement, for the third.

AND THE ARGUMENT SET IS MEASURED TOO, which matters because the obvious name-shaped guess is
wrong: across every recorded call, `limit` (418 calls, 8 tools) is PAGINATION and `spend` (113
calls, 12 tools) is a BOOLEAN. Both would have been swept in by matching on words like "spend"
or "limit". `budget_usd` is the only money-typed argument in live use.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    MONEY_ARGS,
    _author_named_money,
    _money_arg_note,
    invented_money_args,
)

SILENT = [{"role": "user", "content": "Start an authoring run for this book — begin autopilot."}]
NAMED = [{"role": "user", "content": "Start an authoring run for this book — begin autopilot. "
                                      "Budget it at 5 dollars and pause after each unit."}]


def test_the_MEASURED_instance_is_caught():
    """🔴 THE FALSIFIER, on the row's own call: the author said nothing about money."""
    assert invented_money_args({"book_id": "b", "budget_usd": 50}, SILENT) == ["budget_usd"]
    assert invented_money_args({"budget_usd": 10}, SILENT) == ["budget_usd"]
    assert invented_money_args({"budget_usd": 5}, SILENT) == ["budget_usd"]


def test_the_authors_OWN_number_is_kept():
    """🔴 THE PRECISION ARM, and the expensive direction. Seven of the sixteen carried a number
    the author had given; refusing those would make the guard worse than the defect."""
    assert invented_money_args({"budget_usd": 5}, NAMED) == []


def test_the_author_test_is_GENEROUS_on_purpose():
    """Any mention at all keeps the value. A false negative refuses money the author really
    gave; a false positive merely makes the model ask."""
    for said in ("cap it at $20", "spend up to twenty dollars", "what's the budget for this?",
                 "keep the spend low", "50 USD max"):
        assert _author_named_money([{"role": "user", "content": said}]), said
    assert not _author_named_money(SILENT)
    assert not _author_named_money([])
    assert not _author_named_money(None)


def test_only_the_USER_turns_count():
    """🔴 THE MODEL TALKING ABOUT MONEY MUST NOT AUTHORISE ITS OWN NUMBER. If an assistant turn
    counted, the model could licence itself by mentioning a budget first — which is exactly the
    behaviour under test."""
    assistant_said = [{"role": "assistant", "content": "I'll set a budget of $50 for this run."},
                      {"role": "user", "content": "Start an authoring run — begin autopilot."}]
    assert not _author_named_money(assistant_said)
    assert invented_money_args({"budget_usd": 50}, assistant_said) == ["budget_usd"]


def test_the_argument_set_is_the_MEASURED_one_not_a_name_guess():
    """`limit` is pagination on 8 tools and `spend` is a boolean on 12. A guard that matched on
    those words would delete a page size and a feature flag."""
    assert MONEY_ARGS == {"budget_usd"}
    assert invented_money_args({"limit": 50}, SILENT) == []
    assert invented_money_args({"spend": True}, SILENT) == []


def test_a_non_numeric_or_boolean_value_is_not_a_ceiling():
    """Booleans are ints in Python, and `spend: True` must never read as a spend of 1."""
    assert invented_money_args({"budget_usd": True}, SILENT) == []
    assert invented_money_args({"budget_usd": None}, SILENT) == []
    assert invented_money_args({"budget_usd": "50"}, SILENT) == []
    assert invented_money_args(None, SILENT) == []


def test_the_note_says_whose_decision_it_is():
    """The generic missing-argument sentence would call it forgotten. It was not forgotten."""
    note = _money_arg_note({"budget_usd": 50})
    low = note.lower()
    assert "budget_usd" in note
    assert "author" in low and "not a default for you to pick" in low
    assert "ask them" in low
    assert _money_arg_note({}) == ""
