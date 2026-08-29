"""DQ-T33, answered by the owner 2026-08-28.

    "YES — surface the last TOOL error to the author when a turn ends with no user-visible
     text, SANITISED so an internal trace is never pasted at an author."

The owner declined a generic failure line, which is what makes this reporting rather than
invention: a blank turn cannot be told apart from a crash, a refusal or a slow turn, and this
loop has repeatedly found blank turns hiding a specific, actionable error. The string shown is
the tool's own, already in the turn's `tool_calls` record.

THE CONTROL THAT COULD HAVE REFUTED IT, run before the fix — assistant rows with EMPTY content,
no card, is_error false, grouped by how the turn ended:

    finish_reason='stop'  outcome=failed      67 turns   67 carry a tool error
    finish_reason='stop'  outcome=completed   21 turns   21 carry a tool error   (pre-guard)
    finish_reason='stop'  outcome=NULL         6 turns    6 carry a tool error
    abandoned_expired / interrupted         1,156 turns  — the author WALKED AWAY, not this

Every turn in the target population has something true to say, so the fix cannot be inert on
its own population. The abandoned population is deliberately excluded: there is nobody to tell.

Serves both D-SILENT-TURN-NO-CARD-NO-PROSE and the remedy half of
D-A-TURN-THAT-EXHAUSTS-ITS-PASSES-WRITES-AND-SAYS-NOTHING.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    _GENERIC_ERROR_TEXT,
    _client_safe_error,
    _last_tool_error_for_author,
)

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def _call(tool: str, *, ok: bool, error: str | None = None) -> dict:
    return {"id": "c1", "tool": tool, "args": {}, "ok": ok, "result": None, "error": error}


class TestItReportsRatherThanInvents:
    def test_the_last_failed_calls_own_message_is_returned(self):
        """The real shape, taken verbatim from the live store."""
        err = ("invalid arguments for jobs_list — Input should be 'pending', 'running' "
               "(you sent 'active'). Fix the argument and call the tool again.")
        history = [_call("book_read", ok=True), _call("jobs_list", ok=False, error=err)]
        assert _last_tool_error_for_author(history) == err

    def test_the_LAST_failure_wins_not_the_first(self):
        history = [_call("a", ok=False, error="first"), _call("b", ok=False, error="second")]
        assert _last_tool_error_for_author(history) == "second"

    def test_a_later_SUCCESS_does_not_hide_an_earlier_failure(self):
        """The measured turns end on a refusal the model then declines to act on; a read that
        succeeded afterwards must not erase the reason the turn produced nothing."""
        history = [_call("a", ok=False, error="the real reason"), _call("b", ok=True)]
        assert _last_tool_error_for_author(history) == "the real reason"

    def test_a_turn_with_no_failure_stays_SILENT(self):
        """🔴 ABSENCE OF AN ERROR IS NOT LICENCE TO INVENT ONE. This loop's standing rule is
        that putting words in the assistant's mouth is worse than an honest stop, and the owner
        declined a generic failure line for the same reason."""
        assert _last_tool_error_for_author([_call("a", ok=True)]) is None

    def test_a_turn_with_no_tool_calls_at_all_stays_silent(self):
        assert _last_tool_error_for_author([]) is None
        assert _last_tool_error_for_author(None) is None

    def test_an_empty_error_string_is_not_shown(self):
        """A blank 'error' is no more informative than the blank reply it would replace."""
        assert _last_tool_error_for_author([_call("a", ok=False, error="   ")]) is None
        assert _last_tool_error_for_author([_call("a", ok=False, error=None)]) is None


class TestItIsSanitisedByTheEXISTINGPath:
    """The owner's note: "this repo already has a sanitize path for prompt/reply text and the
    standing rule is that a new block reuses it rather than writing its own"."""

    def test_a_traceback_is_never_pasted_at_an_author(self):
        history = [_call("a", ok=False, error="Traceback (most recent call last): File x")]
        assert _last_tool_error_for_author(history) == _GENERIC_ERROR_TEXT

    def test_a_secret_is_never_pasted_at_an_author(self):
        history = [_call("a", ok=False, error="bad password for user")]
        assert _last_tool_error_for_author(history) == _GENERIC_ERROR_TEXT

    def test_an_ordinary_tool_message_passes_through_unchanged(self):
        """The sanitiser must not swallow the useful case — that would make the fix inert while
        still looking shipped."""
        msg = "composition_arc_get is missing required argument(s): [node_id]"
        assert _client_safe_error(msg) == msg

    def test_there_is_ONE_sanitiser_not_two(self):
        """🔴 THE DRIFT THIS PREVENTS. The `except` handler had this logic inline; a second copy
        for the new caller would be correct the day it was written and stale the first time a
        marker is added to one of them. Extracted, so both callers share it."""
        assert SRC.count('("traceback", "file ", "/usr/", "password", "secret")') == 1, (
            "the unsafe-marker list appears more than once — the sanitiser has been duplicated"
        )
        assert "safe_msg = _client_safe_error(str(exc))" in SRC, (
            "the original error handler no longer routes through the shared sanitiser"
        )


class TestItIsScopedToTurnsWithNoCard:
    def test_the_fallback_is_emitted_before_the_message_is_closed(self):
        """Emitted after `close_message()` it would land outside the frame the FE renders —
        a silent turn with extra steps."""
        assert SRC.index("full_content.append(_tool_last_word)") < SRC.index(
            "# ARCH-1 C3: token stream is done"), (
            "the fallback is appended after the assistant message is closed"
        )

    def test_the_awaiting_input_handler_is_untouched(self):
        """A carded turn's output IS the card. The 150 measured 'wrote, then asked for approval'
        turns need the CARD to name the completed write — a different, still-undecided remedy —
        and must not pick up a stray error line beside it. That handler `return`s before this
        site, and this pins that it gained no fallback of its own."""
        i = SRC.index('finish_reason="awaiting_input"')
        assert "_tool_last_word" not in SRC[i - 3000:i + 3000]
