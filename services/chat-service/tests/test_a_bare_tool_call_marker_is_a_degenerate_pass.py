"""D-SILENT-TURN-NO-CARD-NO-PROSE — the measured silent turn, reproduced in code.

Every silent `finish_reason='stop'` turn in the recorded population carries exactly
12 characters of reasoning, and that content is the literal string `<tool_call|>` —
this model family's tool-call CLOSING delimiter, arriving alone as the whole pass.

Forty-two calls straight at the provider (first pass, the pass after a tool result,
advertised tool counts 2/30/80, and streaming) never reproduced it, so the shape was
only ever observable by waiting for it. These tests make it deterministic: the pass
is degenerate by the content of its own two channels, and that is decidable without
a provider at all.

What the platform already does with that string is the point:

  _has_leak_marker('<tool_call|>')        -> True     it KNOWS this is a control token
  _split_safe_emit('<tool_call|>')        -> flushed  the hold is keyed on the OPENING
                                                      token `<|tool_call>`, so the
                                                      closing one is never held back
  _extract_leaked_tool_calls('<tool_call|>') -> []    there is no call to salvage

so the pass reaches the end with no tool call, no content, and a control token sitting
in the reasoning channel where the author cannot see it. The turn then ends saying
nothing. `_is_bare_toolcall_marker_only` is the predicate that names that state.
"""
import pytest

from app.services.stream_service import (
    _extract_leaked_tool_calls,
    _has_leak_marker,
    _is_bare_toolcall_marker_only,
    _split_safe_emit,
)


class TestTheMeasuredStringIsClassifiedDegenerate:
    def test_the_exact_measured_reasoning_is_degenerate(self):
        """The recorded shape: 12 chars of reasoning, no content."""
        assert _is_bare_toolcall_marker_only(text="", reasoning="<tool_call|>") is True

    def test_the_opening_delimiter_alone_is_degenerate_too(self):
        """The same family. Nothing here distinguishes which delimiter leaked."""
        assert _is_bare_toolcall_marker_only(text="", reasoning="<|tool_call>") is True

    def test_markers_in_the_content_channel_count_the_same(self):
        assert _is_bare_toolcall_marker_only(text="<tool_call|>", reasoning="") is True

    def test_whitespace_around_the_marker_does_not_save_it(self):
        assert _is_bare_toolcall_marker_only(text="  ", reasoning="\n <tool_call|> \n") is True

    def test_several_markers_and_nothing_else_are_still_degenerate(self):
        assert _is_bare_toolcall_marker_only(
            text="", reasoning="<|tool_call><tool_call|><|channel>") is True


class TestItDoesNotFireOnATurnTHatSaidSomething:
    """The precision half. A predicate that fires on a real reply would turn
    working turns into failures, which is a worse defect than the one it names."""

    def test_plain_prose_is_not_degenerate(self):
        assert _is_bare_toolcall_marker_only(
            text="Here are the models your provider offers.", reasoning="") is False

    def test_reasoning_that_is_real_thinking_is_not_degenerate(self):
        assert _is_bare_toolcall_marker_only(
            text="", reasoning="The user wants the live inventory, so I should call the "
                               "inventory tool rather than the registered-models one.") is False

    def test_a_marker_WITH_surrounding_prose_is_not_degenerate(self):
        """This is the case the salvage path already handles — real text that
        happens to carry a marker. Stripping the marker leaves content, so the
        pass produced something and is not degenerate."""
        assert _is_bare_toolcall_marker_only(
            text="", reasoning="<|tool_call>call:settings_list_models{}<tool_call|>") is False

    def test_an_empty_pass_with_no_marker_at_all_is_not_this_defect(self):
        """A turn that is simply empty is a DIFFERENT failure. Classifying it as
        this one would inflate the count with turns that never leaked anything."""
        assert _is_bare_toolcall_marker_only(text="", reasoning="") is False

    def test_angle_brackets_that_are_not_markers_are_not_degenerate(self):
        assert _is_bare_toolcall_marker_only(text="<p>hello</p>", reasoning="") is False


class TestTheHelpersThisRestsOnBehaveAsClaimed:
    """The docstring above makes four claims about existing code. If any of them
    stops holding, the predicate is guarding a state that no longer occurs and
    these tests should be the thing that says so."""

    def test_the_platform_recognises_the_string_as_a_marker(self):
        assert _has_leak_marker("<tool_call|>") is True

    def test_the_closing_delimiter_is_never_held_back(self):
        """The hold is keyed on the opening token, so the closing one flushes
        straight through to the client as reasoning."""
        flush, hold = _split_safe_emit("<tool_call|>")
        assert (flush, hold) == ("<tool_call|>", "")

    def test_there_is_no_call_to_salvage_from_it(self):
        assert _extract_leaked_tool_calls("<tool_call|>") == []

    def test_a_COMPLETE_leaked_call_is_still_recovered(self):
        """The control that keeps the above from being vacuous: the salvage path
        works, and returns nothing here only because there is nothing to return."""
        assert _extract_leaked_tool_calls(
            '<|tool_call>call:settings_list_models{"a": 1}<tool_call|>'
        ) == [("settings_list_models", '{"a": 1}')]
