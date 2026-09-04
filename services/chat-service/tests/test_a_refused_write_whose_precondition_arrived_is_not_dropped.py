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
