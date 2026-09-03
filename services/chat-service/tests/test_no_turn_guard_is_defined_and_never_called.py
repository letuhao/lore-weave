"""Every end-of-turn guard must be CALLED, not merely defined.

🔴 THIS CLASS OF DEFECT WAS FOUND FOUR TIMES IN ONE LOOP, and each time by deleting the wiring
and watching the suite stay green:

    P14  R1's transitive supplier walk   `_pending = _next` -> `_pending = []`   4 of 4 GREEN
    P16  _asked_instead_of_acting         (pre-empted: an AST check was written with it)
    P7   memory_search's fact leg         `fact_hits = await ...` -> `[]`        20 of 20 GREEN
    P12  the silent-turn fallback         `if _silent_turn:` -> `if False and`   21 of 21 GREEN

In three of those the record CLAIMED a falsifier. P14's said the chokepoint shipped "with a
falsifier proven RED against the original" — it proved the depth-1 hop while the invariant is the
word TRANSITIVELY. P7's twenty tests exercise the repository function, which is the right thing to
test and is not what broke. The pattern is not carelessness about testing; it is that a pure
function is easy to test and a CALL SITE is not, so the tests go where the testing is easy and the
wiring is left to a code review that will not notice a deleted line among six thousand.

So this asserts the one property those tests structurally cannot: that each guard is reachable
from the turn loop at all. It is a weak property deliberately — it says nothing about WHEN a guard
fires or whether its conditions are right, which is what the per-guard tests are for. What it
makes impossible is a guard that fires never.

AST, NOT A SUBSTRING SEARCH. Every name below appears in this module's own comments and
docstrings, and three appear in `logger.warning` format strings, all of which survive deleting the
call. `ast` sees a Call node or it does not.

ADDING A GUARD HERE IS DELIBERATE. The list is written out rather than discovered by a naming
convention, because a convention that picks up helpers would make the assertion vacuous the first
time someone defines a private function that legitimately has no call site yet.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.services import stream_service

#: guard name -> the invariant it enforces and the problem that owns it.
TURN_GUARDS = {
    "_claimed_an_effect_without_acting":
        "P2 clause 1 — a turn may not assert a state change it did not make",
    "_resolve_authors_source":
        "P2 clause 2 — a turn may not act on content it invented (DQ-T55)",
    "_asked_instead_of_acting":
        "P16 — a turn holding what it needs may not ask for consent in prose",
    "_instruction_names_a_recorder":
        "P6 — an instruction naming a recorder may not be answered in prose",
    "_unanswered_data_question_reads":
        "DQ-T30 — a question about stored data must be answered from a call on THIS turn",
    "_rail_write_step_stalled":
        "D-NARRATED-WRITE — a rail's outstanding write, when the turn called nothing",
    "_last_tool_error_for_author":
        "P12 / DQ-T33 — a silent turn surfaces the last tool ERROR",
    "_last_tool_success_for_author":
        "P12 / DQ-T75 — a silent turn that had nothing fail says what it read",
}


def _called_names() -> set[str]:
    tree = ast.parse(inspect.getsource(stream_service))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name:
                out.add(name)
    return out


@pytest.mark.parametrize("guard,invariant", sorted(TURN_GUARDS.items()))
def test_the_guard_is_called_somewhere_in_the_turn_loop(guard, invariant):
    assert guard in _called_names(), (
        f"{guard} is DEFINED and never CALLED — the invariant it enforces ({invariant}) is "
        "detected by nothing. Deleting a call site is invisible to a per-guard unit test, which "
        "is how this shape was shipped four times in one loop."
    )


def test_every_listed_guard_actually_exists():
    """🔴 THE ARM THAT KEEPS THE LIST HONEST. If a guard is renamed or removed and this list is
    not updated, the parametrised test above would still pass for the survivors while silently
    covering one fewer mechanism — a shrinking guarantee that still reads green. A missing name
    must fail loudly instead."""
    missing = sorted(g for g in TURN_GUARDS if not hasattr(stream_service, g))
    assert not missing, (
        f"{missing} are listed here but no longer defined in stream_service — either they were "
        "renamed (update this list) or removed (say so, and say what replaced them)"
    )
