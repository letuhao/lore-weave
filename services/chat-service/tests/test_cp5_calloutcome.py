"""CP-5.5 — the typed CALL outcome, and why a suspension is not a failure.

🔴 **THE VOCABULARY EXISTED AND HAD NEVER BEEN WRITTEN ONCE.** `observation.py` defines C-14's
call outcome and says in its own comment that it *"replaces `ok: bool`"*, because *"ok=true is
untyped and means seven different things"*. Measured across **7,990 recorded tool calls** before
this landed: `outcome` 0, `error_class` 0. A clause with a subject and no producer.

🔴 **AND §1's ERROR-CONTRACT POPULATION HAS NO GENUINE MEMBER.** It files 41 calls / 29 sessions as
*"failures carrying NO MESSAGE AT ALL"*. Measured: **every one of the 41 is a call that stopped to
ask a human** — consumer-local confirm/propose tools, tier `A` writes raising a mutation card, and
tier `W` human-confirmed tools. **Not one is a tier-R read**, and **38 of the 41 sit in turns the
human never came back to** (`abandoned_by_user`). So the row is not "add a message"; it is "stop
recording a deferred call as a failure", which is what the PO ordered.
"""
from __future__ import annotations

import pytest

from app.agentruntime.observation import (
    ERROR_CLASSES, FAILED, OUTCOMES, UNCLASSIFIABLE,
)
from app.services import instrument


def instrumented(**chunk) -> dict:
    chunk.setdefault("tool", "book_list")
    return instrument.ensure_tool_call_instrumented(dict(chunk))


class TestTheCallOutcomeIsWrittenAtAll:
    """The producer that C-14's enum never had."""

    def test_A_SUCCESSFUL_CALL_IS_DONE(self):
        assert instrumented(ok=True)["call_outcome"] == "done"

    def test_A_FAILED_CALL_IS_FAILED(self):
        assert instrumented(ok=False, error="boom")["call_outcome"] == FAILED

    def test_EVERY_PERSISTED_CALL_CARRIES_ONE(self):
        """`ensure_tool_call_instrumented` is the chokepoint both INSERT paths run, so a call
        reaching persistence without a typed outcome is unrepresentable."""
        for chunk in ({"ok": True}, {"ok": False}, {}, {"ok": None}):
            got = instrumented(**chunk)
            assert got["call_outcome"] in OUTCOMES, got

    def test_THE_OUTCOME_IS_A_MEMBER_OF_THE_DECLARED_VOCABULARY(self):
        assert instrument.CALL_DONE in OUTCOMES
        assert instrument.CALL_DEFERRED in OUTCOMES
        assert instrument.CALL_FAILED in OUTCOMES


class TestASuspensionIsNotAFailure:
    """The conflation the PO ordered split, and the whole of §1's error-contract population."""

    def test_A_DEFERRED_CALL_IS_NOT_FAILED(self):
        got = instrumented(**instrument.stamp_deferred({"ok": False, "pending": True}))
        assert got["call_outcome"] == instrument.CALL_DEFERRED
        assert got["call_outcome"] != FAILED

    def test_A_DEFERRED_CALL_CARRIES_NO_ERROR_CLASS(self):
        """§4.2 — the error class is a SUB-FIELD of `failed`, not a peer taxonomy. Asking whether
        a deferred call is retryable is a category error."""
        got = instrumented(**instrument.stamp_deferred(
            {"ok": False, "error_class": "retryable_transient"}))
        assert "error_class" not in got

    def test_DEFERRED_IS_STAMPED_AT_THE_SITE_NOT_INFERRED_FROM_AN_EMPTY_ERROR(self):
        """🔴 The rule that keeps this from becoming the same conflation as a heuristic. A failure
        with no message must NOT be guessed into `deferred` — 'it stopped to ask a human' is
        structural where the suspension happens and an inference anywhere else."""
        got = instrumented(ok=False)          # no error text, not stamped
        assert got["call_outcome"] == FAILED, (
            "an unstamped empty failure must stay FAILED — inferring `deferred` from a missing "
            "message would rebuild the conflation this row exists to end"
        )
        assert got["call_outcome_inferred"] is True

    def test_THE_SUSPEND_SITE_ACTUALLY_STAMPS_IT(self):
        """A source-level check, because the claim is that the ONE place a call suspends marks it
        — and a mechanism nothing calls is the shape this run has found five times."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "instrument.stamp_deferred({" in src, (
            "the suspend record does not mark itself deferred, so every suspension persists as a "
            "failure exactly as before"
        )


class TestAFailureCarriesAClassOrFailsClosed:

    def test_AN_UNCLASSIFIED_FAILURE_GETS_C7S_FAIL_CLOSED_ANSWER(self):
        got = instrumented(ok=False, error="boom")
        assert got["error_class"] == UNCLASSIFIABLE == "terminal_permanent"
        assert got["error_class_inferred"] is True

    def test_THE_FAIL_CLOSED_DIRECTION_IS_NOT_RETRYABLE(self):
        """An unclassifiable failure reading as retryable is what feeds the measured 74%
        byte-identical repeat calls."""
        assert "retryable" not in instrumented(ok=False)["error_class"]

    def test_A_SITE_SUPPLIED_CLASS_IS_KEPT(self):
        got = instrumented(ok=False, error="timeout", error_class="retryable_transient")
        assert got["error_class"] == "retryable_transient"
        assert "error_class_inferred" not in got

    def test_A_BOGUS_CLASS_IS_REPLACED_RATHER_THAN_TRUSTED(self):
        got = instrumented(ok=False, error_class="probably_fine")
        assert got["error_class"] in ERROR_CLASSES

    def test_A_FAILURE_WITH_NO_MESSAGE_IS_MARKED_NOT_SILENT(self):
        """C-7's other half. This cannot RAISE — a turn must not die because a raising site was
        terse — so the residual is made countable rather than invisible, which is the honest
        option when the fix belongs at a site this code does not own. §1 filed 41 calls here and
        every one was a suspension, so the field starts life measuring an EMPTY set."""
        assert instrumented(ok=False)["error_message_missing"] is True
        assert instrumented(ok=False, error="   ")["error_message_missing"] is True

    def test_A_FAILURE_WITH_A_MESSAGE_IS_NOT_MARKED(self):
        assert "error_message_missing" not in instrumented(ok=False, error="boom")

    def test_A_DEFERRED_CALL_IS_NEVER_MARKED_MESSAGE_MISSING(self):
        """A suspension has nothing to say and owes no message; marking it would recreate the
        conflation in a second field."""
        got = instrumented(**instrument.stamp_deferred({"ok": False, "pending": True}))
        assert "error_message_missing" not in got

    def test_NOTHING_HERE_READS_THE_ERROR_TEXT(self):
        """V-METRIC proved the best possible regex insufficient over 834 rows, so classification
        is set where the failure is RAISED. Two failures whose only difference is their prose must
        classify identically."""
        a = instrumented(ok=False, error="connection reset by peer, please retry")
        b = instrumented(ok=False, error="the book was deleted and cannot be restored")
        assert a["error_class"] == b["error_class"] == UNCLASSIFIABLE


class TestTheTwoVocabulariesStaySeparate:
    """Turn-outcome and call-outcome overlap only at `failed`; a query joining them by name would
    compare two different questions."""

    def test_THE_CHUNK_KEY_IS_NOT_THE_TURN_KEY(self):
        got = instrumented(ok=True)
        assert "call_outcome" in got
        assert "outcome" not in got, (
            "`outcome` on a tool_call would collide with chat_messages.outcome, which is the TURN "
            "vocabulary — the two answer different questions and must not share a name"
        )

    def test_THE_TURN_VOCABULARY_STILL_HAS_ITS_OWN_AWAITING_INPUT(self):
        assert instrument.OUTCOME_AWAITING_INPUT == "awaiting_input"
        assert instrument.OUTCOME_AWAITING_INPUT not in OUTCOMES, (
            "the turn's `awaiting_input` must not leak into the CALL vocabulary; the call's name "
            "for that state is `deferred`"
        )

    def test_THE_ONLY_SHARED_MEMBER_IS_FAILED(self):
        shared = set(OUTCOMES) & set(instrument.OUTCOMES)
        assert shared == {FAILED}, f"the vocabularies now share {shared}"
