"""D-ASKED-TO-STOP-WORK-THE-MODEL-PROPOSED-STARTING-IT (and its 5/5 sibling,
D-A-STOP-REQUEST-PROPOSES-A-COST-BEARING-START).

MEASURED: asked "Cancel my translation job — stop the runaway translation run", the model checked
jobs_list, found nothing running, and then called translation_start_job AND
translation_retranslate_dirty — minting a confirm token for each. Asked to STOP work, it proposed
STARTING it, twice, on two spend-bearing tools. Its own reply showed it knew: "I don't see any
translation jobs currently running." The correct turn ends there.

Nothing executed — the Tier-W cards held — but a confirm card is the LAST line, not the only one.
The click is a human's to make on a card that says "start translation" when they asked to cancel.

🔴 THE TEST IS THE TOOL'S OWN DECLARED VOCABULARY, NEVER ITS NAME. There is no `starts_work` flag:
against the live catalogue those four tools carry only {tier, scope, synonyms, async}. A
`*_start_*` prefix rule would be the name classifier CP-4.d deleted for inferring a property from
fragments of an identifier. So the gate asks the question `answerable_tools` already answers
everywhere else — does THIS tool's declaration answer THIS request?

    translation_job_control          answerable   ("cancel the translation", …)
    jobs_cancel                      answerable   on "Stop the translation one."
    translation_start_job            NOT          ("translate", "start translation", …)
    translation_retranslate_dirty    NOT
    translation_start_extraction     NOT
    composition_authoring_run_create NOT
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.request_mood import CONSTRUCT, HALT, INSPECT, UNKNOWN, request_mood  # noqa: E402
from app.services.stream_service import _halt_turn_refusal  # noqa: E402

STOP = "Cancel my translation job — stop the runaway translation run"


def _t(name: str, tier: str, synonyms: list[str]) -> dict:
    return {"function": {"name": name, "description": "", "parameters": {},
                         "_meta": {"tier": tier, "scope": "book", "synonyms": synonyms}}}


START_JOB = _t("translation_start_job", "W",
               ["translate", "translate book", "start translation", "translate chapters"])
JOB_CONTROL = _t("translation_job_control", "W",
                 ["cancel the translation", "pause the translation", "resume the translation"])
JOBS_LIST = _t("jobs_list", "R", ["list jobs", "show my jobs"])


class TestTheMoodIsNarrowedByItsOwnFalsePositives:
    """Each narrowing below was FORCED by a false positive the previous version produced against
    1,917 real user messages — not chosen up front. v1 bare verb: 47 matched, including "Count
    from 1 to 2000 … Do NOT stop early". v2 + work noun + no construct: 12, still catching probe
    LABELS. v3 + verb not hyphen-joined: 8 (0.42%), all genuine."""

    def test_the_rows_own_instances_are_halt(self):
        for m in (STOP, "Stop the translation one.", "Cancel that job.",
                  "Pause the authoring run for this book — stop run."):
            assert request_mood(m) == HALT, m

    def test_a_NEGATED_verb_is_not_a_stop_request(self):
        """v1's worst false positive, and it asks for the OPPOSITE."""
        assert request_mood(
            "Count from 1 to 2000. Output one number per line. Do not stop early.") != HALT

    def test_a_hyphenated_probe_LABEL_is_not_a_stop_request(self):
        """v2's residue: the label says KILL, the request says "list the chapters"."""
        assert request_mood("RUN-D7-KILL: list the chapters, then list the worlds.") != HALT

    def test_a_bare_verb_with_no_WORK_named_is_not_halt(self):
        assert request_mood("Stop.") != HALT
        assert request_mood("Please stop being so verbose.") != HALT

    def test_a_MIXED_request_is_not_halt(self):
        """Mirrors how `inspect` is built: a construct verb anywhere disqualifies it, so every
        existing behaviour is untouched on a mixed turn."""
        assert request_mood("Cancel the translation job and then rewrite chapter 2.") == CONSTRUCT
        assert request_mood("Stop the run and create a new chapter.") == CONSTRUCT

    def test_the_existing_moods_are_unchanged(self):
        assert request_mood("Show me the outline I have planned for this book") == INSPECT
        assert request_mood("Add a chapter called Ash") == CONSTRUCT
        assert request_mood("") == UNKNOWN
        assert request_mood(None) == UNKNOWN


class TestTheGateRefusesAStartOnAStopTurn:
    def test_a_start_tool_is_refused(self):
        err = _halt_turn_refusal("translation_start_job", START_JOB, STOP)
        assert err and "asked to STOP work" in err

    def test_the_refusal_tells_the_model_what_to_do_instead(self):
        """A refusal that only blocks leaves the turn stuck — and the measured reply shows the
        model already KNEW nothing was running. It must be told to say so and stop."""
        err = _halt_turn_refusal("translation_start_job", START_JOB, STOP)
        assert "SAY SO and stop" in err
        assert "do not propose new work" in err

    def test_the_RIGHT_tool_is_allowed_through(self):
        """🔴 THE CONTROL. A gate that blocked the cancel tool too would break the very request
        it exists to protect."""
        assert _halt_turn_refusal("translation_job_control", JOB_CONTROL, STOP) is None

    def test_a_READ_is_always_allowed(self):
        """jobs_list is how the turn FINDS the job to stop — the correct first move."""
        assert _halt_turn_refusal("jobs_list", JOBS_LIST, STOP) is None


class TestItIsInertEverywhereElse:
    def test_a_normal_turn_is_untouched(self):
        assert _halt_turn_refusal(
            "translation_start_job", START_JOB, "Translate this book into French") is None

    def test_a_MIXED_turn_is_untouched(self):
        assert _halt_turn_refusal(
            "translation_start_job", START_JOB,
            "Cancel the translation job and then rewrite chapter 2.") is None

    def test_an_unknown_tool_def_is_not_refused(self):
        """Fail OPEN on a tool we cannot read. A gate that blocks what it cannot classify would
        break calls on any surface whose defs are not in the index."""
        assert _halt_turn_refusal("mystery_tool", None, STOP) is None

    def test_no_request_text_is_inert(self):
        assert _halt_turn_refusal("translation_start_job", START_JOB, None) is None
        assert _halt_turn_refusal("translation_start_job", START_JOB, "") is None
