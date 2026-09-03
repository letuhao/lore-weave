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


class TestADeferredCallIsEventuallyRESOLVED:
    """TOOL-V2 LOOP #3 — the other half of 5.5, and the half that made a working tool unmeasurable.

    5.5 stopped a suspension being recorded as a failure. It left the row saying `deferred`
    FOREVER: the human's decision arrives on the resume, where it became a `working` tool message
    the model reads and nothing measurable. "The user applied the edit" and "the user walked away"
    were the same row — so §1's finding that 38 of 41 deferred calls sit in abandoned turns could
    never be checked against what the other 3 did.

    🔴 **AND IT MADE A PROVEN-WORKING TOOL READ AS TOTALLY BROKEN.**
    `glossary_propose_entity_edit` was driven end to end on a throwaway book — glossary_search →
    glossary_get_entity → propose with a real entity_id, attr_value_id and base_version →
    apply-edit 200 → the description changed in the database. Its record: **0 successes in 101
    calls**, because a frontend tool SUSPENDS and `ok:true` is written only where a dispatch
    returns. A queue ranking tools by success rate therefore puts working tools at the top of its
    broken list, which is exactly what this loop's own queue did with it.
    """

    def test_AN_APPLIED_EDIT_RESOLVES_TO_DONE(self):
        got = instrumented(**instrument.resolve_deferred({"ok": True}, "applied_saved"))
        assert got["call_outcome"] == instrument.CALL_DONE
        assert got["resolves_deferred"] is True

    def test_A_DISMISSAL_IS_REFUSED_NOT_FAILED(self):
        """The user read the diff card and said no. That is the product working, and typing it
        `failed` is the denial conflation of loop #2 arriving one path over."""
        got = instrumented(**instrument.resolve_deferred({"ok": False}, "dismissed"))
        assert got["call_outcome"] == instrument.CALL_REFUSED
        assert got["refusal_kind"] == "dismissed_by_user"
        assert "error_class" not in got

    def test_A_CONFLICT_IS_RETRYABLE_MODIFIED_NOT_TERMINAL(self):
        """The entity genuinely changed since it was read, and the tool's own contract already
        tells the model to re-read and propose afresh — so this is the one failure here that a
        retry can fix, and calling it terminal would contradict the instruction the model gets."""
        got = instrumented(**instrument.resolve_deferred({"ok": False}, "applied_conflict"))
        assert got["call_outcome"] == FAILED
        assert got["error_class"] == "retryable_modified"
        assert "error_class_inferred" not in got

    def test_AN_UNKNOWN_OUTCOME_IS_NOT_GUESSED_INTO_A_SUCCESS(self):
        got = instrumented(**instrument.resolve_deferred({"ok": False}, "something_new"))
        assert got["call_outcome"] == FAILED

    def test_A_STRUCTURED_RESULT_WITH_NO_OUTCOME_WORD_IS_DONE(self):
        """The MCP fan-out shape: a `ui_*` nav resolve feeds a structured result back instead of
        an outcome word. The call demonstrably completed."""
        got = instrumented(**instrument.resolve_deferred({"ok": True}, None, had_result=True))
        assert got["call_outcome"] == instrument.CALL_DONE

    def test_THE_RESUME_SITE_ACTUALLY_RECORDS_IT(self):
        """The wiring, at the source — the end-to-end proof is the live round trip recorded in
        the tool-v2 ledger. A mechanism nothing calls is the shape this run keeps finding."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "instrument.resolve_deferred({" in src, (
            "the frontend resume records no resolution, so every suspension stays `deferred` "
            "forever and an applied edit is indistinguishable from an abandoned one"
        )
        assert "_fe_resolved_chunk, _task_chunk" in src, (
            "the resolution row is built but never reaches pre_tool_chunks, so it is never "
            "persisted — built and dropped is worse than absent, it reads as done"
        )


class TestAUserDenialIsNotAFailureEither:
    """TOOL-V2 LOOP #2 — the same conflation, a third population.

    🔴 **MEASURED: 21 calls / 17 sessions / 4 tools are a human saying no, and every one is
    recorded `failed`.** The denial site stamped `source` and stopped there, so the chokepoint
    fell through to its fail-closed default and the row says the tool broke.

    It did not break — it never ran. `kg_propose_edge` reads **0 successes in 17 calls, and 14 of
    them, across 12 of its 14 sessions, are this branch**: a Tier-A tool that has never once been
    permitted to dispatch. Its "0% success rate" was measuring the approval card.

    `refused` already existed for this (*"a call the RUNTIME declined to make"*), and the denial
    site's own comment already argued a user denial is ours.
    """

    def test_A_USER_DENIAL_IS_REFUSED_NOT_FAILED(self):
        got = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "denied by user"}, "denied_by_user"))
        assert got["call_outcome"] == instrument.CALL_REFUSED
        assert got["call_outcome"] != FAILED
        assert "call_outcome_inferred" not in got

    def test_A_DENIAL_STAYS_SEPARABLE_FROM_THE_BREAKER_REFUSALS(self):
        """"The human said no" and "we short-circuited a repeat" are both refusals and must never
        merge into one number — which is what `refusal_kind` is for."""
        denial = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "denied by user"}, "denied_by_user"))
        breaker = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "unchanged repeat"}, "repeat_unchanged"))
        assert denial["call_outcome"] == breaker["call_outcome"]
        assert denial["refusal_kind"] != breaker["refusal_kind"]

    def test_A_DENIAL_CARRIES_NO_ERROR_CLASS(self):
        """§4.2 — the error class is a sub-field of `failed`. Asking whether a human's "no" is
        retryable is a category error, and the answer it used to get was `terminal_permanent`."""
        got = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "denied by user", "error_class": "retryable_transient"},
            "denied_by_user"))
        assert "error_class" not in got

    def test_A_STANDING_NEVER_ALLOW_IS_REFUSED_AND_SEPARABLE(self):
        """🔴 **THE SAME CONFLATION ONE SITE OVER, found in tool-v2 loop iteration 49.** Loop #2
        typed the human's "no" on the RESUME path. The PERMANENT no — "Never allow" in Settings —
        was still falling through to the fail-closed default: 15 calls across 3 sessions, all
        `glossary_adopt_standards`, every one recorded as if the tool had broken.

        `denied_standing` stays separable from `denied_by_user` because a decision made ONCE for
        all future turns and a decision made about THIS call are different facts about the user.
        """
        standing = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "blocked: you chose 'Never allow'"}, "denied_standing"))
        this_call = instrumented(**instrument.stamp_refused(
            {"ok": False, "error": "denied by user"}, "denied_by_user"))
        assert standing["call_outcome"] == instrument.CALL_REFUSED
        assert "error_class" not in standing, "a refusal is not a failure with a class"
        assert standing["refusal_kind"] != this_call["refusal_kind"]

    def test_THE_STANDING_DENY_SITE_ACTUALLY_STAMPS_IT(self):
        """The wiring, at the source — the consent surface must not read as a tool defect."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert '}, "denied_standing")}' in src, (
            "a standing 'Never allow' still records as a tool failure, so the clearest refusal "
            "in the product is counted against the tool the user declined"
        )

    def test_THE_DENIAL_SITE_ACTUALLY_STAMPS_IT(self):
        """The wiring, checked at the source — a mechanism nothing calls is the shape this run has
        now found six times, and the end-to-end proof lives in
        `test_permission_modes.py::test_denied_is_recorded_REFUSED_not_failed`."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert '}, "denied_by_user"),' in src, (
            "the user-denial record does not mark itself refused, so every denial persists as a "
            "tool failure exactly as before"
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


class TestAFrontendValidationRefusalIsNotAToolFailure:
    """🔴 **THE FIFTH INSTANCE OF THE SAME CONFLATION, AND THE LARGEST SINGLE POPULATION.**

    `glossary_propose_entity_edit` is recorded at **101 calls / 12 sessions / 0% success** — the
    worst row in the corpus. Every one of them carries `result: null` and an `error` that is
    **chat-service's own validation prose**: the tool never ran. They are runtime refusals wearing
    a tool's name, exactly like 5.5's suspensions, 5.4's owed arguments and 5.7's breaker output,
    and while they are typed `failed` they inflate the very corpus every member here is measured
    against.

    ✖ **This does NOT claim to change the model's behaviour, and the evidence says not to expect
    it to.** The remedy this defect already received was PROSE — the re-route text in
    `validate_frontend_tool_args`, added 2026-07-22 after the same failure was measured at 13
    calls, telling the model in as many words not to pass a placeholder. The corpus AFTER that fix
    is the 101. What is claimed is what is verifiable: the outcome is typed and the refusal is
    counted as a refusal.
    """

    def _src(self) -> str:
        import pathlib
        return (pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
                / "stream_service.py").read_text(encoding="utf-8")

    def test_A_REFUSAL_IS_STAMPED_REFUSED_NOT_RECORDED_AS_A_FAILURE(self):
        """V6 (2026-09-03) — RE-POINTED off the v1 intercept.

        This anchored on `_fe_chunk`, the frontend branch's refusal stamp. That branch is deleted;
        the mechanism it guarded survives on the paths that remain. CP-5.4 is why it is worth
        guarding at all: 101 calls that never ran sat in the corpus as `failed`, inflating every
        rate computed over it.

        Asserting the SITE COUNT rather than one site's variable name, so the next relocation does
        not red this for a reason that has nothing to do with the invariant.
        """
        src = self._src()
        assert src.count("instrument.stamp_refused(") >= 4, (
            "refusal stamping has thinned out; a refusal recorded as a plain failure re-inflates "
            "the corpus CP-5.4 had to correct")

    # test_THE_TWO_REFUSAL_KINDS_ARE_KEPT_APART REMOVED 2026-09-03 (V6) — see below.

    # test_THE_KIND_CLAIMS_ONLY_WHAT_THE_SITE_CAN_KNOW REMOVED 2026-09-03 (V6).
    #
    # Both asserted the `unresolved_identifier` refusal kind, whose ONLY producer was the v1
    # intercept. The kind no longer occurs and appeared in NO contract — only in this file, in
    # stream_service, and in two falsifier scenarios, all three now retired together.
    #
    # Its input class (a name where a UUID was required) is handled BETTER on the surviving path:
    # CP-5.3 RESOLVES the name to an id rather than classifying the refusal. Deleting a
    # classification because its subject was repaired upstream is not a loss of coverage.

    def test_THE_MEASUREMENT_THAT_SAYS_RESOLUTION_WOULD_NOT_HELP_IS_RECORDED(self):
        """The tempting build here is to bind CP-5.3's resolver to this tool, since it declares
        `identifier_resolution`. Measured over all 94 non-UUID `entity_id` values in the corpus:
        **91 contain "placeholder", 3 are `"0"`, ZERO are names** — so resolution would have
        repaired NONE of them. The number is kept next to the code so the next reader does not
        rediscover the idea and build it."""
        assert "would have repaired **none** of them" in self._src()
