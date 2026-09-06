"""D-SILENT-TURN-NO-CARD-NO-PROSE — a turn with no user-visible text recorded as a success.

MEASURED 2026-08-14 over 347 recorded runs of the tool-deep-dive loop: 21 turns across 8 tools
ended with NO prose, NO confirm card and no approval —

    composition_arc_get 5, glossary_curation_list 3, plan_compile 3, jobs_get 3,
    translation_job_status 3, settings_model_delete 2, jobs_list 1, memory_recall_entity 1

— and every one was stored outcome='completed', is_error=false, finish_reason='stop'. Every count
that reads outcomes saw a success; the author saw an empty reply. The commonest trigger is a tool
returning an argument-repair message ("... is missing required argument(s) ... do NOT guess a
value"): the model reads it, correctly declines to guess, and then says nothing at all.

🔴 THE CONTROL THAT SHRANK THIS BY 4x, recorded so it is not relearned. The first measurement was
113 of 347 turns (32%). But 92 of those 113 ended SUSPENDED ON A CONFIRM CARD, where the card IS
the output and prose is legitimately absent — failing those would fail correct Tier-A behaviour,
and would have wrongly withdrawn glossary_extract_entities_from_doc. Those turns are persisted by
the awaiting_input handler and never reach the clean-finish site this guard lives at, which is why
the guard is scoped THERE rather than in a shared helper.

WHAT THE FIX DELIBERATELY DOES NOT DO: invent a reply. Putting words in the assistant's mouth in
service code would be this loop's own "prose is not the lever" mistake, and three prose
interventions were measured and refuted on 2026-08-14. The turn is recorded honestly instead.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services import instrument  # noqa: E402

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


class TestTheRowModelCanEvenExpressThis:
    """`is_error` is the seam the vocabulary already had; the guard did not need a new column."""

    def test_stop_with_is_error_is_failed(self):
        assert instrument.outcome_for_finish_reason("stop", is_error=True) == "failed"

    def test_stop_without_it_is_still_completed(self):
        """The overwhelming majority of turns must be untouched by this."""
        assert instrument.outcome_for_finish_reason("stop") == "completed"

    def test_finish_reason_is_NOT_rewritten(self):
        """F-19: finish_reason and outcome must derive from one signal or the row contradicts
        itself. The guard changes only the OUTCOME — the row keeps reporting the loop's real
        terminal reason. 🔴 The first version of this test asserted `"stop" == "stop"`, which is
        the vacuous-assertion defect this repo has already paid for twice; it now reads the bind."""
        i = SRC.index("is_error=_silent_turn")
        tail = SRC[i:i + 3000]
        assert '_loop_finish_reason or "stop",' in tail, (
            "the finish_reason bind must still be the loop's own value")
        assert "_silent_turn" not in tail.split('_loop_finish_reason or "stop",')[1][:200], (
            "finish_reason must not be rewritten from the silent flag")


class TestTheCallSiteIsActuallyWired:
    """🔴 CALL-SITE GUARD, NOT A HELPER GUARD. `outcome_for_finish_reason` already accepted
    is_error before this fix and every helper-level test passed while the clean-finish INSERT
    bound the default. A helper test would have stayed green over the whole defect."""

    def test_the_silent_flag_is_computed_from_the_visible_text(self):
        """UPDATED 2026-08-28 — the EXPRESSION moved, the guarantee did not.

        DQ-T33's answer appends the last tool error to `full_content` for a turn that produced
        none of its own, so `final_text` is no longer empty on exactly the turns this guard
        exists to catch. The flag is therefore taken from `full_content` BEFORE that append —
        see the test below, which is the one that keeps the guarantee honest."""
        assert '_silent_turn = not "".join(full_content).strip()' in SRC

    def test_the_clean_finish_insert_binds_it(self):
        """The bind, not merely the variable: this is the exact expression whose absence IS the
        defect."""
        m = re.search(
            r"instrument\.outcome_for_finish_reason\(\s*"
            r"_loop_finish_reason or \"stop\", is_error=_silent_turn\s*\)", SRC)
        assert m, "the clean-finish INSERT no longer passes is_error=_silent_turn"

    def test_no_clean_finish_bind_is_left_defaulted(self):
        """Falsifier-proof: if a later edit adds a second derivation that drops the flag, this
        catches it rather than the suite staying green on the one that kept it."""
        binds = re.findall(r"outcome_for_finish_reason\(\s*_loop_finish_reason[^)]*\)", SRC)
        assert binds, "the clean-finish derivation vanished"
        assert all("is_error=_silent_turn" in b for b in binds), binds

    def test_it_is_computed_before_it_is_bound(self):
        assert SRC.index('_silent_turn = not "".join(full_content).strip()') < SRC.index(
            "is_error=_silent_turn")

    def test_the_flag_is_taken_BEFORE_the_tool_error_fallback_is_appended(self):
        """🔴 THE REGRESSION THIS EXISTS TO STOP, and it would be invisible in every count.

        DQ-T33 makes a silent turn speak the tool's own last error, which lands in
        `full_content`. If the flag were recomputed after that append — or simply left reading
        `final_text` — every rescued turn would record `completed`, and the 67 measured failures
        this guard converted would silently become successes again. The turn still failed: the
        MODEL produced nothing. Only the author's experience improved."""
        flag = SRC.index('_silent_turn = not "".join(full_content).strip()')
        append = SRC.index("full_content.append(_tool_last_word)")
        assert flag < append, (
            "the silent flag is computed AFTER the fallback is appended, so a rescued turn now "
            "records as a completion — the guard has been inverted"
        )
        # …and it must not be recomputed from the post-append text anywhere later.
        assert "_silent_turn = not final_text" not in SRC, (
            "the flag is recomputed from final_text, which now contains the surfaced tool error"
        )


class TestItIsScopedAwayFromTheCardCase:
    def test_the_awaiting_input_persist_does_not_carry_the_flag(self):
        """92 of 113 empty replies suspended on a card. That handler must remain untouched — a
        suspended turn is `awaiting_input`, which is neither completed nor failed."""
        i = SRC.index('finish_reason="awaiting_input"')
        assert "_silent_turn" not in SRC[i - 2000:i + 2000]

    def test_awaiting_input_is_its_own_outcome(self):
        assert instrument.outcome_for_finish_reason("awaiting_input") == "awaiting_input"


class TestItSaysSoInTheLog:
    """A turn recorded `failed` with nothing naming why is the next person's mystery."""

    def test_the_warning_names_the_last_tool(self):
        i = SRC.index("silent turn: session=%s")
        assert "tool_calls_history[-1]" in SRC[i:i + 600]
        assert "logger.warning" in SRC[i - 200:i]
