"""S1/DoD-1 — a path that runs NO canon guard must SAY SO, in the same shape as one that does.

The registry row this closes, verbatim: *"the SSE generators mention `canon` zero times.
User-visible prose, no canon guard, no name grounding, no cross-scene check, and no field that
says any of that."*

Skipping the guard on an interactive surface is a design position. Being silent about it is the
defect — a `done` frame with no canon block and a `done` frame from a fully-checked draft are
identical bytes to the reader, so "nobody checked this" renders as "checked, clean".
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.engine.canon_check import CanonViolation, ReflectResult, canon_envelope, unguarded_envelope

from loreweave_guard import CheckStatus

_ROUTERS = pathlib.Path(__file__).resolve().parents[2] / "app" / "routers" / "engine.py"


# ── the declaration itself ────────────────────────────────────────────────────────────────

def test_the_status_is_NOT_RUN_and_not_the_one_that_renders_as_nothing():
    """`not_applicable` was the tempting choice and it is the wrong one: its own docstring says
    it renders as NOTHING because it is not a coverage gap. Using it here would have rebuilt
    the silence under a new name — which is the entire defect."""
    env = unguarded_envelope("because reasons that are long enough to be a reason")
    assert env["guard_status"] == CheckStatus.NOT_RUN.value
    assert env["guard_status"] != CheckStatus.NOT_APPLICABLE.value


def test_a_declaration_carries_a_REASON_an_author_can_act_on():
    env = unguarded_envelope("the co-write stream does not run the canon guard: approve first")
    assert len(env["guard_reason"].strip()) >= 40, "a status with no reason is an unactionable badge"


def test_it_claims_NOTHING_it_did_not_check():
    """The failure mode on the other side. A declaration that filled `resolved=True` or
    `verdict=True` to keep a consumer happy would be worse than the silence it replaces."""
    env = unguarded_envelope("x" * 50)
    assert env["resolved"] is None and env["verdict"] is None
    assert env["violations"] == [] and env["coverage"] == {} and env["checks"] == {}
    assert env["iterations"] == 0


def test_NOT_RUN_ranks_as_a_REAL_problem_not_a_clean_result():
    """It must not be quietly better than `checked` in the derived headline, or a stream's
    declaration would make a mixed report read green."""
    from loreweave_guard import worst

    assert worst(["checked", CheckStatus.NOT_RUN.value]) is CheckStatus.NOT_RUN
    # …and a genuine failure still outranks it, so this is a position in the order and not a
    # new top.
    assert worst([CheckStatus.NOT_RUN.value, "failed"]) is CheckStatus.FAILED


# ── one shape, whichever path produced it ─────────────────────────────────────────────────

def test_the_two_envelopes_have_IDENTICAL_key_sets_but_for_the_reason():
    """Asserted, not trusted. `canon_envelope` was extracted from SIX hand-written dicts that
    all agreed on the day they were written and then drifted — `guard_status` reached all six
    and `verdict` reached none. Two builders that must stay in step get a test, not a comment.
    """
    # Fields read off `CanonCandidateBase`, not recalled — this test's first version invented
    # `entity=`/`rule=`/`detail=` and failed for a reason that had nothing to do with its
    # subject. The repo already carries that lesson: derive a fixture from the PRODUCER schema.
    reflect = ReflectResult(
        text="draft",
        violations=[CanonViolation(entity_id="e1", name="Mina", matched="Mina", confirmed=True)],
        iterations=1,
    )
    guarded = set(canon_envelope(reflect))
    declared = set(unguarded_envelope("x" * 50))
    assert declared - guarded == {"guard_reason"}, (
        "the declaration invented a key the checked envelope does not have"
    )
    assert guarded - declared == set(), (
        f"a consumer reading the checked envelope would find {guarded - declared} missing from "
        f"a declared one — that is two shapes, which is what this test exists to prevent"
    )


# ── the streams actually emit it ──────────────────────────────────────────────────────────

def _sse_done_frames_with_canon() -> int:
    """How many `yield _sse({...'status': 'completed'...})` frames carry a `canon` key.

    Read off the AST rather than grepped: the file's comments discuss `canon` constantly, and a
    text scan would count the prose describing the fix as the fix. That confusion has cost this
    run five separate findings.
    """
    tree = ast.parse(_ROUTERS.read_text(encoding="utf-8"))
    hits = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if {"type", "job_id", "status"} <= keys and "canon" in keys:
            hits += 1
    return hits


def test_both_streams_emit_the_declaration_on_their_terminal_frame():
    """Two streams, so two frames. Counted rather than named, because naming the line number
    would rot on the next edit and naming the function would not notice a third stream added
    without one."""
    assert _sse_done_frames_with_canon() >= 2, (
        "an SSE terminal frame streams a completed draft with no canon field — the reader "
        "cannot tell it from a checked one"
    )


def test_the_frame_scanner_can_tell_a_frame_WITHOUT_canon_apart():
    """The control, driving the same predicate. `>= 2` is satisfied by a scanner that counts
    every dict in the file, which would make the assertion above meaningless."""
    tree = ast.parse(
        'yield _sse({"type": "done", "job_id": j, "status": "completed"})\n'
    )
    frames = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]
    assert len(frames) == 1
    keys = {k.value for k in frames[0].keys if isinstance(k, ast.Constant)}
    assert {"type", "job_id", "status"} <= keys and "canon" not in keys, (
        "the scanner would count a frame with no canon key as carrying one"
    )


@pytest.mark.parametrize("marker", ["unguarded_envelope("])
def test_the_streams_call_the_SHARED_builder_rather_than_hand_rolling_one(marker):
    """The lesson from the six copies, applied before there are six. Both call sites must go
    through the builder, so a key added to the declaration reaches both."""
    src = _ROUTERS.read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "unguarded_envelope"]
    assert len(calls) >= 2, f"{marker} is called {len(calls)}x — both streams must use it"
