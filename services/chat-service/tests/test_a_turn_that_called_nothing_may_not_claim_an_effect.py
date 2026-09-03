"""P2-FABRICATED-WRITE — a turn may not assert a state change it did not make.

🔴 THE MEASURED INSTANCE, batch 23, `plan_keep_material`, 4 of 5 runs. The tool was not advertised
(surfaced 0/5), the model called NOTHING (`called_tools == []`), and answered:

    "I've updated the plan to include the new details while ensuring all the existing material
     we've established remains intact. Your story foundation is now fully updated."

The store is unchanged. The author is told their plan was updated when it was not.

WHY NEITHER EXISTING GUARD SEES IT. `_narrated_uncalled_writes` keys on a snake_case TOOL NAME in
prose — here the model names no tool, it reports only the OUTCOME.
`_unanswered_data_question_reads` keys on the REQUEST matching a READ tool's vocabulary, and this
is a write. The gap is structural, not a tuning miss.

CALIBRATED, NOT GUESSED. The defect's own note said a detector for "claims an outcome without
acting" is not a name match and "needs care and a control". Three candidates were scored against
60 hand-labelled zero-call turns drawn from 2586 recorded ones; `test_the_shipped_detector_scores
_the_way_the_calibration_said` re-runs that scoring against the real corpus so the numbers in the
source comment cannot quietly stop being true.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.services.stream_service import (
    _claimed_an_effect_without_acting,
    _narrated_uncalled_writes,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
CORPUS = ROOT / "docs" / "eval" / "toolloop"
STREAM_SRC = ROOT / "services" / "chat-service" / "app" / "services" / "stream_service.py"

#: Verbatim from the run that produced this defect.
THE_MEASURED_CLAIM = (
    "I've updated the plan to include the new details while ensuring all the existing "
    "material we've established remains intact. Your story foundation is now fully updated."
)


class TestTheDetector:
    def test_it_fires_on_the_measured_instance(self):
        assert _claimed_an_effect_without_acting(THE_MEASURED_CLAIM, attempted=set())

    def test_the_existing_guard_is_blind_to_it(self):
        """Not decoration — it is the reason this guard had to exist at all. If
        `_narrated_uncalled_writes` ever grew to cover this shape, one of the two is redundant
        and somebody should find out which."""
        assert _narrated_uncalled_writes(
            THE_MEASURED_CLAIM,
            catalog_index={"plan_keep_material": {"_meta": {"tier": "W"}}},
            attempted=set(),
        ) == []

    @pytest.mark.parametrize("answer", [
        "I cannot cancel a translation job because there are no active translation jobs.",
        "I cannot turn off the `story bible` skill. It is a system-tier skill.",
        "I'm sorry, but I can't do that because there are no public books in the catalogue.",
        "I cannot delete or modify the steering rules for this book.",
        "I'm sorry, but I need you to specify which template you'd like me to use.",
    ])
    def test_it_is_silent_on_an_honest_refusal(self, answer):
        """These are real answers from the corpus. A guard that nudges an honest refusal teaches
        the model to stop refusing, which is worse than the defect."""
        assert not _claimed_an_effect_without_acting(answer, attempted=set())

    def test_a_refusal_whose_negation_is_in_another_clause_is_still_a_refusal(self):
        """The one false positive the looser candidate produced, kept as a case.

        "haven't actually recorded" satisfies the completed-claim pattern; the refusal that
        governs it sits in an earlier clause. Whole-answer refusal matching is what makes this
        silent, and that is a deliberate choice recorded in the source.
        """
        assert not _claimed_an_effect_without_acting(
            'I cannot "forget" a fact that I haven\'t actually recorded in your project\'s '
            "long-term memory or the story bible.",
            attempted=set(),
        )

    def test_a_turn_that_ATTEMPTED_anything_is_never_nudged(self):
        """Successes AND failures both count as attempted, exactly as the sister guard does: a
        model that tried and got a real error already has honest feedback to report."""
        assert not _claimed_an_effect_without_acting(
            THE_MEASURED_CLAIM, attempted={"plan_keep_material"})
        assert not _claimed_an_effect_without_acting(
            THE_MEASURED_CLAIM, attempted={"some_tool_that_errored"})

    def test_empty_and_none_text_are_safe(self):
        assert not _claimed_an_effect_without_acting("", attempted=set())
        assert not _claimed_an_effect_without_acting(None, attempted=set())


class TestTheGuardIsActuallyWIREDIN:
    """🔴 A HELPER-LEVEL TEST STAYS GREEN WHEN THE FIX IS NEVER WIRED IN.

    This repo has paid for that once already. The detector above could be perfect and unreachable.
    These read the chokepoint itself.
    """

    def test_the_stream_loop_calls_it(self):
        src = STREAM_SRC.read_text(encoding="utf-8")
        # once as the definition, at least once as a call inside the loop
        assert src.count("_claimed_an_effect_without_acting") >= 2, (
            "the detector is defined and never called — the guard does not exist at runtime")

    def test_it_shares_the_write_nudge_cap(self):
        """A turn must never collect two write-side nudges. Sharing the counter is what
        guarantees it, so the sharing is asserted rather than assumed."""
        src = STREAM_SRC.read_text(encoding="utf-8")
        i = src.index("P2-FABRICATED-WRITE — the turn called NOTHING")
        window = src[i:i + 2500]
        assert "NARRATED_WRITE_NUDGE_CAP" in window
        assert "narrated_write_nudges += 1" in window

    def test_the_directive_does_not_quote_the_model_back_at_itself(self):
        """The runtime measured two things — no tool ran, and the text reads as a completed
        change. It may assert those and nothing more. Naming WHICH claim was wrong would assert a
        reading of intent the guard never made: the same false-report shape it exists to stop."""
        src = STREAM_SRC.read_text(encoding="utf-8")
        i = src.index("[SYSTEM DIRECTIVE] This turn called no tool at all, and your reply ")
        directive = src[i:i + 900]
        assert "you just described using" not in directive.lower()
        assert "did NOT make the change" in directive


class TestAcknowledgingIsNotActing:
    """🔴 A FALSE POSITIVE THIS GUARD SHIPPED WITH, found 2026-08-26 by new evidence.

    `\\w+ed` matched "I have NOTED your instruction to stop the translation" — a conversational
    acknowledgement, in a turn that had honestly reported an error one sentence earlier — and the
    guard treated it as a narrated write. The calibration test below is what caught it: it asserts
    WHICH tools fire, not how many, so a new batch entering the corpus could not be absorbed
    silently.

    Measured over the full 2656-turn corpus before the change: 9 fires on 3 tools -> 8 fires on 2.
    Exactly the one false positive removed, every true positive kept.
    """

    @pytest.mark.parametrize("text", [
        "I have noted your instruction to stop the translation.",
        "I've noted that and will keep it in mind.",
        "I have understood the request.",
        "I have reviewed the chapter list.",
        "I have read your note.",
        "I have already considered that.",
        "I have checked the job list.",
    ])
    def test_an_acknowledgement_does_not_fire(self, text):
        assert not _claimed_an_effect_without_acting(text, attempted=set())

    @pytest.mark.parametrize("text", [
        "I have cancelled the pending translation jobs.",
        "I've deactivated Nemotron-3 Nano for you.",
        "I have forgotten that fact.",
        "I have saved the draft.",
        "I have already made those changes.",
    ])
    def test_a_real_effect_claim_still_fires(self, text):
        assert _claimed_an_effect_without_acting(text, attempted=set())

    def test_the_exclusion_is_a_PREFIX_guard_not_a_substring_ban(self):
        """'noted' must not be excluded merely because it appears somewhere — only when it is the
        verb being claimed. A turn that really did act and also says the word must still fire."""
        assert _claimed_an_effect_without_acting(
            "I have updated the note you asked about.", attempted=set())


@pytest.mark.skipif(not CORPUS.exists(), reason="recorded corpus not present")
class TestTheCalibrationStillHolds:
    """Re-score the SHIPPED detector against the real corpus, so the numbers written into the
    source comment cannot quietly stop being true."""

    @staticmethod
    def _runs():
        out = []
        for p in CORPUS.rglob("*.json"):
            if p.name.endswith("-raw.json"):
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            for row in (d.get("tools") or []):
                if not isinstance(row, dict):
                    continue
                for r in (row.get("runs") or []):
                    if isinstance(r, dict) and r.get("answer") is not None and not r.get("error"):
                        out.append((row.get("tool"),
                                    re.sub(r"\s+", " ", r.get("answer") or "").strip(),
                                    set(r.get("called_tools") or [])))
        return out

    def test_it_fires_only_on_zero_call_turns_and_only_on_real_ones(self):
        runs = self._runs()
        assert len(runs) > 1000, "corpus looks truncated; the numbers below would be meaningless"
        zero = [r for r in runs if not r[2]]
        fired = [r for r in zero
                 if _claimed_an_effect_without_acting(r[1], attempted=r[2])]

        # Every tool it fires on must be one of the two the defect names. Asserting the TOOLS
        # rather than the count, so a new recorded batch does not have to edit this test.
        assert {t for t, _a, _c in fired} <= {"plan_keep_material", "memory_forget"}, (
            f"fired on an unexpected tool: {sorted({t for t, _a, _c in fired})}")
        assert fired, "it fires on nothing — the corpus or the detector has changed"

        # And it must never fire on a turn that called something, at any point in the corpus.
        called = [r for r in runs if r[2]]
        assert not [r for r in called
                    if _claimed_an_effect_without_acting(r[1], attempted=r[2])]

    def test_the_phrase_alone_would_be_useless(self):
        """What makes the guard safe is the ZERO-CALL gate, not the wording. If the phrasing were
        rare in legitimate use this test would be pointless — it is not: it appears in hundreds of
        turns that really did work, and the guard never runs there."""
        runs = self._runs()
        called = [r for r in runs if r[2]]
        phrase_only = [r for r in called
                       if _claimed_an_effect_without_acting(r[1], attempted=set())]
        assert len(phrase_only) > 100, (
            "the completed-claim phrasing is supposed to be ORDINARY in turns that did real "
            f"work; found only {len(phrase_only)}, so the gate may not be what is doing the work")
