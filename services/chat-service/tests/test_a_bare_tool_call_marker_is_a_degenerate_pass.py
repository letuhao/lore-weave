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


class TestTheDegeneratePassIsRetried:
    """The remedy, and why it is not a new product decision.

    D-REASONING-LOOP already handles "a model that thrashes in the *reasoning stream* WITHOUT
    emitting a call", and its chosen remedy is to abort the pass, inject a steer directive,
    FORCE REASONING OFF for the retry, and cap the interventions so a persistent failure ends
    honestly rather than hanging.

    The silent turn is the same trigger shape, degenerate in ONE pass rather than across
    several — which is exactly why ReasoningLoopDetector never trips on it. And the remedy
    matches this turn's measured correlate: every turn producing PROSE has reasoning_length 0;
    every silent finish_reason='stop' turn has reasoning_length 12, carrying `<tool_call|>`.
    Forcing reasoning off targets that directly.

    So this applies a decided pattern. What the author SEES when the retry ALSO fails is
    DQ-T33 and stays the owner's — which is why the cap falls through to the existing
    silent-turn guard rather than fabricating a reply.
    """

    @staticmethod
    def _src() -> str:
        import inspect

        from app.services import stream_service

        return inspect.getsource(stream_service)

    @staticmethod
    def _joined(text: str) -> str:
        """Source with Python's implicit string concatenation collapsed.

        🔴 AN EARLIER VERSION OF THIS TEST ASSERTED ON RAW SOURCE AND WENT RED ON A LINE WRAP:
        the directive reads "... or answer the user directly in one short message", but the
        source splits it as `"... or answer the "` + `"user directly in one short message."`,
        so the phrase is not a contiguous substring. That is a fact about formatting, not about
        the message, and a test that cannot tell them apart teaches people to weaken it."""
        import re

        return re.sub(r'"\s+"', "", text)

    def test_a_degenerate_pass_is_retried_at_all(self):
        src = self._src()
        assert "degenerate_pass_interventions <" in src, (
            "a degenerate pass is detected and nothing is done about it"
        )

    def test_the_retry_forces_reasoning_off(self):
        """The remedy has to match the correlate. A retry that keeps reasoning on re-enters
        the state the silence correlates with."""
        src = self._src()
        i = src.find("if degenerate_pass_interventions <")
        block = src[i:i + 1600]
        assert "_suppress_reasoning_next_pass = True" in block
        assert "continue" in block, "it steers and never retries the pass"

    def test_it_is_capped(self):
        src = self._src()
        assert "DEGENERATE_PASS_INTERVENTION_CAP = 1" in src, (
            "an uncapped retry on a degenerate model turns a silent turn into a churning one"
        )

    def test_the_cap_falls_through_rather_than_fabricating_a_reply(self):
        """🔴 THE ONE THING THIS MUST NOT DO. The neighbouring D-REASONING-LOOP intervention
        yields a written apology when ITS cap is reached, which is right for a loop the author
        watched happen. Here the honest end is the existing silent-turn guard recording
        `failed` — putting words in the assistant's mouth is the mistake this loop keeps
        finding elsewhere, and what the author should SEE is DQ-T33's open half."""
        src = self._src()
        i = src.find("if degenerate_pass_interventions <")
        block = src[i:i + 2000]
        assert "Cap reached" in block
        assert "NOT a fabricated reply" in block, (
            "the fall-through no longer says why it refuses to invent a reply"
        )

    def test_the_steer_names_the_two_acceptable_outcomes(self):
        """A directive that only says 'try again' invites the same pass. It must name what
        counts as done: make the call, or answer plainly."""
        src = self._joined(self._src())
        i = src.find("if degenerate_pass_interventions <")
        block = src[i:i + 1600]
        assert "CALL the tool" in block
        assert "answer the user directly" in block
