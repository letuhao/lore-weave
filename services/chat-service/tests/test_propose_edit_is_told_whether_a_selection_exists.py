"""D-PROPOSE-EDIT-ACTS-ON-EDITOR-STATE-THE-TURN-CANNOT-SEE.

propose_edit declares two operations — insert_at_cursor and replace_selection — and both
presuppose editor state (a cursor, a selection) the turn never carried. `EditorContext` was
book_id + chapter_id + an optional chapter_title; nothing told the model whether a selection
existed, so a request to rewrite a passage could not ground replace_selection in anything real.
Measured K=5: the model correctly declined the guess and answered in prose instead — a defensible
answer to an affordance it could not confirm applied.

THE FE ALREADY HAS THE SELECTION. TiptapEditorHandle.getSelection() returns {from, to, empty,
text} and ProposeEditCard already reads it twice (propose-time snapshot, apply-time abort-on-move).
This is additive, exactly like chapter_title: `has_selection` / `selected_text` on EditorContext,
sent only when a real editor is mounted (older FEs / a popped-out window simply omit them, and
`None` is treated as "unknown" — today's behaviour, unchanged).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.models import EditorContext  # noqa: E402

STREAM_SRC = (pathlib.Path(__file__).resolve().parents[1]
              / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def test_EditorContext_carries_the_selection_fields():
    """Real Pydantic introspection, not source text — the model actually validates these."""
    fields = EditorContext.model_fields
    assert "has_selection" in fields and "selected_text" in fields
    assert fields["has_selection"].default is None, "must default to unknown, not False"
    assert fields["selected_text"].default is None


def test_omitting_selection_is_still_valid_older_FEs_keep_working():
    ctx = EditorContext(book_id="b1", chapter_id="c1")
    assert ctx.has_selection is None
    assert ctx.selected_text is None


def _note_block():
    i = STREAM_SRC.index('book_context_note = (\n            "You are working in the CURRENT book')
    return STREAM_SRC[i:][:3500]


def test_a_real_selection_is_named_to_the_model():
    seg = _note_block()
    i = seg.index("_has_sel = ")
    branch = seg[i:][:900]
    assert 'if _has_sel is True:' in branch
    assert 'SELECTED in the editor' in branch
    assert "propose_edit's replace_selection targets exactly that span" in branch


def test_no_selection_tells_the_model_replace_selection_has_no_target():
    seg = _note_block()
    i = seg.index("_has_sel = ")
    branch = seg[i:][:900]
    assert 'elif _has_sel is False:' in branch
    assert "NOTHING selected" in branch
    # Precisely what happens today — not "refused", a wasted round trip the FE already handles.
    assert "wasted round trip" in branch
    assert "insert_at_cursor" in branch


def test_UNKNOWN_selection_state_adds_no_note_older_FEs_are_silent():
    """`has_selection is None` (the FE didn't send it) must fall through both branches — the note
    stays exactly as it was before this fix, matching chapter_title's own additive precedent."""
    seg = _note_block()
    i = seg.index("_has_sel = ")
    branch = seg[i:i + 900]
    # Neither branch's marker text should appear when has_selection is simply absent — asserted
    # structurally: both are gated behind `is True` / `is False`, never a truthy/falsy check that
    # would also fire on None.
    assert "if _has_sel:" not in branch, "must distinguish None (unknown) from False (empty)"
    assert "if not _has_sel:" not in branch
