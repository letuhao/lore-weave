"""A turn that produced no text and had NOTHING FAIL still says what it read.

DQ-T75, owner 2026-08-31: "(a) REPORT WHAT THE TOOL RETURNED. A turn that produced no text and
had nothing fail is not empty-handed -- it holds a successful tool result, and it says what it
read, from the record already in the turn. No new prose is invented, which is the same rule that
made DQ-T33 answerable and the reason a generic line was declined there."

    THE INVARIANT. A turn that produced nothing of its own says why, from its own record --
    never in invented words.

THE POPULATION. DQ-T33's fallback surfaces the last tool ERROR and reaches 74 of the 94 recorded
blank turns. The other TWENTY are the worst subset, not an edge: single-call turns that ran a
read tool, got `ok: true`, and said nothing. The tool worked, the data came back, and the author
got a blank reply -- so there is no error and the sibling correctly returns None.
"""
from __future__ import annotations

import inspect

import pytest

from app.services.stream_service import (
    _last_tool_error_for_author,
    _last_tool_success_for_author,
)


class TestItReportsWhatRan:
    def test_the_measured_shape_a_single_ok_read(self):
        """The uncovered twenty, in their most common form: one call, ok, no text."""
        line = _last_tool_success_for_author([
            {"tool": "composition_package_tree", "ok": True, "result": {"arcs": []}},
        ])
        assert line and "composition_package_tree" in line, (
            f"a blank turn whose only call succeeded says {line!r} — it must name the tool it ran")

    def test_several_calls_are_all_named(self):
        line = _last_tool_success_for_author([
            {"tool": "book_read", "ok": True},
            {"tool": "glossary_search", "ok": True},
        ])
        assert "book_read" in line and "glossary_search" in line

    def test_a_repeated_call_is_named_once(self):
        line = _last_tool_success_for_author([
            {"tool": "jobs_get", "ok": True}, {"tool": "jobs_get", "ok": True},
        ])
        assert line.count("jobs_get") == 1, f"{line!r} names the same tool twice"


class TestItDoesNotInvent:
    def test_nothing_successful_means_silence(self):
        """Absence of a result is not licence to invent one -- the same rule as the sibling."""
        assert _last_tool_success_for_author([]) is None
        assert _last_tool_success_for_author([{"tool": "x", "ok": False, "error": "boom"}]) is None
        assert _last_tool_success_for_author(None) is None

    def test_a_CARDED_call_is_not_a_completed_read(self):
        """A pending call is a PROPOSAL the author has still to approve. Counting it as something
        the turn 'read' would tell the author a write had happened."""
        assert _last_tool_success_for_author(
            [{"tool": "book_chapter_create", "ok": True, "pending": True}]) is None

    def test_it_never_quotes_the_RESULT(self):
        """🔴 THE LINE THIS FIX MUST NOT CROSS. Summarising a result payload would be inventing:
        nothing here knows which part of it the author wanted, and a wrong summary of a real
        result is worse than silence because it reads as an answer."""
        secret = "THE-DROWNED-ROAD-CHAPTER-TEXT"
        line = _last_tool_success_for_author(
            [{"tool": "book_read", "ok": True, "result": {"body": secret}}])
        assert secret not in line, f"the result payload leaked into the reply: {line!r}"

    def test_it_says_the_turn_wrote_nothing(self):
        """The author must not read it as an answer to their question."""
        line = _last_tool_success_for_author([{"tool": "book_read", "ok": True}])
        assert "did not write a reply" in line


class TestTheErrorAlwaysWins:
    def test_a_turn_with_both_reports_the_FAILURE(self):
        """Order matters and is asserted, not assumed. A turn that failed a call and succeeded at
        another must report the failure: the error is the actionable half, and DQ-T33's ruling
        exists because a blank turn was hiding a specific error."""
        history = [
            {"tool": "book_read", "ok": True},
            {"tool": "book_chapter_create", "ok": False, "error": "book not found"},
        ]
        assert _last_tool_error_for_author(history) is not None
        src = inspect.getsource(
            __import__("app.services.stream_service", fromlist=["x"])._emit_chat_turn)
        i_err = src.find("_last_tool_error_for_author(tool_calls_history)")
        i_ok = src.find("_last_tool_success_for_author(tool_calls_history)")
        assert i_err != -1 and i_ok != -1, "one of the two fallbacks is not wired at this site"
        assert i_err < i_ok, (
            "the success fallback is consulted BEFORE the error one, so a turn that failed a "
            "call would report a success instead")


class TestTheCallSiteUsesIt:
    def test_the_blank_turn_site_calls_the_success_fallback(self):
        """🔴 THE HELPER PASSING PROVES NOTHING IF NOTHING CALLS IT. Every test above invokes the
        function directly; this one reads the site that must consult it."""
        import app.services.stream_service as ss

        src = inspect.getsource(ss._emit_chat_turn)
        assert "_last_tool_success_for_author" in src, (
            "the blank-turn site does not consult the success fallback, so the twenty turns "
            "DQ-T75 is about still reach the author blank")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
