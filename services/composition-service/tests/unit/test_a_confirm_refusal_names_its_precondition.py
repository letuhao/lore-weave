"""A caller can only respond to a refusal that names its precondition.

composition's confirm route answered `{"code": "action_error"}` with NO detail, while the
IMMEDIATE-path siblings say exactly what is wrong — "pause requires status=running, run is
draft". The confirm path was strictly worse than the direct one for the same failure.

🔴 THE SPLIT IS THE WHOLE POINT, AND I GOT IT WRONG FIRST. My initial sweep also named every
LookupError, reasoning "the caller already passed the book gate, so a not-found leaks nothing".
An existing guard — test_the_anti_oracle_denials_stay_bare — refuted that: "not-found and
not-permitted must stay UNIFORM". If a missing thing answers differently from a forbidden thing,
the PAIR of answers is the oracle, whatever either says alone. The guard was right; the sweep was
corrected rather than the guard relaxed.

🔴 AND THE MECHANICAL SWEEP ITSELF WAS UNSAFE. Rewriting 40 handlers by text produced TEN sites
where `exc` was not in scope — `UnboundLocalError` at runtime, caught only because the suite ran.
The whole sweep was reverted to HEAD and replaced by this narrow, verified change. A text
transform over exception handling cannot see scope, and this file's handlers come in several
shapes.

WHAT IS FIXED HERE: the two sites in composition.authoring_run_gate that are genuinely nameable —
the caller's own token payload, and an upstream BookClientError. What is NOT fixed is the other
~50 bare sites across this file; that is recorded on the ledger row, not silently widened.
"""
from __future__ import annotations

import pathlib

from app.routers import actions

SRC = pathlib.Path(actions.__file__).read_text(encoding="utf-8")
GATE = SRC[SRC.index("async def _execute_authoring_run_gate"):][:3000]


def test_the_payload_parse_names_what_is_malformed():
    """The caller minted the token and supplied the field. Naming it discloses nothing it did not
    already have."""
    seg = GATE[GATE.index("except (KeyError, ValueError, TypeError) as exc:"):][:700]
    assert '"detail": str(exc)' in seg


def test_the_upstream_failure_is_distinguishable_from_a_rejected_request():
    """A 502 the caller can retry versus a 400 it cannot: with both bare, they were the same
    answer with a different number."""
    seg = GATE[GATE.index("except BookClientError as exc:"):][:700]
    assert '"detail": str(exc)' in seg


def test_the_LOOKUP_failure_stays_UNIFORM():
    """The correction. not-found must answer exactly as not-permitted does, or the pair is an
    existence oracle — the position test_the_anti_oracle_denials_stay_bare already defends."""
    seg = GATE[GATE.index("except LookupError as exc:"):][:300]
    assert '{"code": "action_error"}' in seg
    assert '"detail": str(exc)' not in seg


def test_the_transition_reason_that_already_worked_is_untouched():
    """TOOLV2 LOOP #170 shipped this one. My reverted sweep briefly broke it, and its own guard
    caught that — pinned here too so a future edit to this effect cannot quietly undo it."""
    seg = GATE[GATE.index("except TransitionConflictError as exc:"):][:900]
    assert '"detail": str(exc)' in seg
