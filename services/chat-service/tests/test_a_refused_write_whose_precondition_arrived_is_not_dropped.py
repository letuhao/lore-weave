"""F1 — a tool refused for a precondition that then ARRIVES must not be quietly abandoned.

🔴 THE MEASURED INSTANCE, 2026-09-04, driving the real Studio as an author. Asked for Chapter One,
the assistant wrote ~2000 words into the reply and called `book_chapter_save_draft`. The tool gave
the correct refusal:

    book_chapter_save_draft — this book has no chapters yet — create one first with
    book_chapter_create

The refusal seam did its job: it armed `book_chapter_create` and injected *"Call them to clear
this, then retry."* The model called it. **And the turn ended.** Verified in the book database a
minute later — one chapter, `word_count=0`, whose only revision was that create's own 64-byte
empty seed:

    {"type": "doc", "content": [{"type": "paragraph", "_text": ""}]}   message='seed from assistant'

The author was left with an empty chapter and their novel in a chat bubble. They only got it back
because they went and looked.

🔴 WHY THE OTHER SEVEN GUARDS ARE ALL SILENT HERE, which is the whole reason this one exists:

    _claimed_an_effect_without_acting   the turn was HONEST — it claimed nothing
    _asked_instead_of_acting            it did not ask in prose; it used the approval card
    _instruction_names_a_recorder       a recorder WAS called. It was refused, not skipped
    _rail_write_step_stalled            fires when the turn called NOTHING. This one called six

A turn silent about a write it ABANDONED is the shape none of them can see.

🔴 THE FIRST DRAFT OF THIS GUARD COULD NEVER HAVE FIRED, and it is worth recording because it
looked right. It took a third parameter, `attempted_after`, and the call site passed
`turn_attempted` — which contains the refused tool's own FIRST call. `refused not in retried` was
therefore False on exactly the shape the guard exists for. "Not retried" is the dict itself:
`refusal_pending` is popped the moment the tool is called again.
"""
from __future__ import annotations

from collections import Counter

from app.services.stream_service import _refusal_precondition_met_but_never_retried as _guard


def test_the_measured_instance_is_detected():
    """save_draft refused for a missing chapter, chapter_create succeeded, no retry."""
    pending = {"book_chapter_save_draft": "book_chapter_create"}
    succeeded = Counter({"book_chapter_create": 1})
    assert _guard(pending, succeeded) == ["book_chapter_save_draft"]


def test_a_retry_that_happened_is_silent():
    """🔴 THE ARM THAT KEEPS THIS HONEST. A retry pops the entry at the dispatch site, so the
    dict is empty and there is nothing to report — including a retry that failed a SECOND time,
    which clears it too. That turn carries a real error the author needs to read, and nagging on
    top of it would bury the error under advice about a call they can see was made."""
    assert _guard({}, Counter({"book_chapter_create": 1})) == []


def test_a_prerequisite_that_did_NOT_succeed_is_silent():
    """The retry would fail for the same reason. Nudging for it is noise on a turn already
    carrying the real error."""
    pending = {"book_chapter_save_draft": "book_chapter_create"}
    assert _guard(pending, Counter()) == []
    assert _guard(pending, Counter({"something_else": 1})) == []


def test_nothing_pending_reports_nothing():
    """The common turn: no refusal named a prerequisite at all."""
    assert _guard({}, Counter({"book_read": 3})) == []
    assert _guard({}, Counter()) == []


def test_several_pending_report_in_a_stable_order():
    """Two writes can be blocked behind the same setup call, and the message names them. Sorted
    so the directive text does not reshuffle between passes of the same turn."""
    pending = {
        "book_chapter_save_draft": "book_chapter_create",
        "composition_scene_write": "book_chapter_create",
    }
    got = _guard(pending, Counter({"book_chapter_create": 1}))
    assert got == ["book_chapter_save_draft", "composition_scene_write"]


def test_only_the_entries_whose_prerequisite_ARRIVED_are_reported():
    """The discriminating case. One prerequisite ran and one did not; reporting both would
    accuse the model of ignoring an instruction it could not yet follow."""
    pending = {
        "book_chapter_save_draft": "book_chapter_create",
        "kg_build": "kg_project_set_embedding_model",
    }
    assert _guard(pending, Counter({"book_chapter_create": 1})) == ["book_chapter_save_draft"]


def test_a_plain_set_of_successes_works_too():
    """The call site passes a Counter, but the guard must not depend on that — a set is the
    obvious thing a future caller reaches for, and failing on it would be a trap."""
    pending = {"book_chapter_save_draft": "book_chapter_create"}
    assert _guard(pending, {"book_chapter_create"}) == ["book_chapter_save_draft"]


def test_the_guard_is_actually_CALLED_by_the_turn_loop():
    """🔴 A DETECTOR NOTHING CALLS IS A DEAD MECHANISM, and every test above would pass with the
    wiring deleted — they exercise the pure function. AST, not a substring search: grepping the
    name matches this file's docstring and the comment beside the call site."""
    import ast
    import inspect

    from app.services import stream_service

    tree = ast.parse(inspect.getsource(stream_service))
    called = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_refusal_precondition_met_but_never_retried" in called, (
        "_refusal_precondition_met_but_never_retried is defined but never CALLED — F1 is "
        "detected by nothing, which is the state the live run found it in"
    )


# ── F1b — the shape row V found with F1 already deployed ─────────────────────────────────────

def test_a_failed_write_with_NO_prerequisite_is_reported_unconditionally():
    """🔴 ROW V, 2026-09-04, WITH F1 ALREADY LIVE. The model called `book_chapter_create` (ok),
    then `book_chapter_save_draft` WITHOUT its `body`, and the turn ended: chapter created, 0
    words, prose in the reply. F1 was SILENT and rightly so — a missing-argument refusal names no
    prerequisite, so nothing armed and the dict stayed empty. **The blind spot was one step
    over.** A failed write that is never retried loses the work whatever the reason, so the
    missing-argument seam records it with an EMPTY prerequisite, meaning "nothing to wait for"."""
    assert _guard({"book_chapter_save_draft": ""}, Counter()) == ["book_chapter_save_draft"]
    # and still reported when unrelated tools succeeded
    assert _guard({"book_chapter_save_draft": ""},
                  Counter({"book_chapter_create": 1})) == ["book_chapter_save_draft"]


def test_the_two_shapes_coexist_in_one_turn():
    """One write blocked behind a prerequisite that arrived, one that simply failed. Both are
    lost work and both must be named; reporting only one would leave the author to find the
    other for themselves, which is the whole defect."""
    pending = {
        "book_chapter_save_draft": "",                     # F1b — just failed
        "composition_scene_write": "book_chapter_create",   # F1  — prerequisite arrived
        "kg_build": "kg_project_set_embedding_model",       # neither — prerequisite never ran
    }
    assert _guard(pending, Counter({"book_chapter_create": 1})) == [
        "book_chapter_save_draft", "composition_scene_write"]


def _f1b_recording_if():
    """The `if` whose OWN body holds the empty-prerequisite recording.

    Immediate body, not `ast.walk` — walk is breadth-first from the module, so it hands back an
    ENCLOSING `if` (here `if discovery:`) before the one that actually gates the statement, and an
    arm anchored on that would ask its question of the wrong test expression."""
    import ast
    import inspect

    from app.services import stream_service

    def is_recording(node):
        return (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "setdefault"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "refusal_pending"
            and len(node.value.args) == 2
            and isinstance(node.value.args[1], ast.Constant)
            and node.value.args[1].value == ""
        )

    tree = ast.parse(inspect.getsource(stream_service))
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and any(is_recording(st) for st in node.body):
            return node, ast
    raise AssertionError(
        "no `if` directly gates an empty-prerequisite recording — F1b is detected by nothing, "
        "which is the state row V found the build in: chapter created, 0 words, prose in the reply"
    )


def test_the_missing_argument_seam_ACTUALLY_records_the_failed_write():
    """🔴 F1b IS TWO PARTS AND THE ABOVE ONLY EXERCISES ONE. The guard is a pure function;
    every test in this file would still pass with the recording deleted, and the deployed build
    would go straight back to the silence row V measured. So this checks the OTHER half exists:
    the missing-argument seam records the tool with an EMPTY prerequisite.

    AST, not a substring search — `refusal_pending` appears in this module's docstrings and in
    four comments, and a grep would go green on any of them (a source-substring guard matching
    non-behavioural text has gone green-with-the-fix-deleted here before).

    ⚠️ WHAT THIS DOES NOT PROVE: that the seam is REACHED on a real turn, or that the tier
    filter admits the right tools. Only a live run shows that, and row V is that proof — the
    deployed image, a real chapter, `word_count` in the book database."""
    import ast
    import inspect

    from app.services import stream_service

    tree = ast.parse(inspect.getsource(stream_service))
    setdefaults = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "setdefault"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "refusal_pending"
    ]
    assert len(setdefaults) >= 2, (
        f"expected both recording seams (F1 names a prerequisite, F1b records an empty one); "
        f"found {len(setdefaults)} refusal_pending.setdefault call(s)"
    )
    empty = [
        n for n in setdefaults
        if len(n.args) == 2 and isinstance(n.args[1], ast.Constant) and n.args[1].value == ""
    ]
    assert empty, (
        "no seam records a failed write with an EMPTY prerequisite — F1b is detected by nothing, "
        "which is the state row V found the build in: chapter created, 0 words, prose in the reply"
    )


def test_the_F1b_recording_is_limited_to_WRITES():
    """🔴 THE ARM THAT KEEPS THE RECORDING HONEST. A failed READ the model moves on from is
    ordinary traffic, and nudging on every one of them would fire the directive constantly and
    train the reader to ignore it. The recording must sit under a tier test, so it cannot silently
    widen to every refused tool on the turn."""
    node, ast = _f1b_recording_if()
    assert any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tool_tier"
        for n in ast.walk(node.test)
    ), (
        "the empty-prerequisite recording is not gated on tool_tier — it would record every "
        "refused READ as lost work and the directive would fire on ordinary traffic"
    )


def test_the_F1b_recording_EXCLUDES_browser_executed_tools():
    """🔴 THE FIRST DRAFT OF THE GATE WAS TOO WIDE AND A TEST CAUGHT IT.
    `tool_tier(...) in ("A","W")` alone admitted `confirm_action`, so a rejected approval card made
    the guard nudge and `test_bad_frontend_args_rejected_and_not_suspended` failed on the extra
    model pass.

    **Tier answers "does this need approval". It does not answer "did this hold the author's
    prose".** The directive tells the model to *"call the refused tool again now, passing the work
    you already wrote"* — for a confirm card there is no such work, and a directive that
    misdescribes what happened is the same defect as the three log lines corrected alongside it.

    `is_browser_executed` is the existing named predicate, and a prefix rule or a hand-listed set
    here would be a second membership rule to drift from that one."""
    node, ast = _f1b_recording_if()
    assert any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "is_browser_executed"
        for n in ast.walk(node.test)
    ), (
        "the F1b recording does not exclude browser-executed tools — a rejected `confirm_action` "
        "would be nudged with a directive telling the model to re-pass prose that does not exist"
    )
