"""A state that removes a tool from the queue has to be paid for.

    THE INVARIANT. A tool at `unmeasurable` carries a REGISTERED DEFECT ID for the platform
    failure, the ARM COUNT, and what the CLEAN runs showed — or `audit` refuses it.

OWNER RULING 2026-08-31, DQ-T40: "DO NOT widen gate.py's excused set. Add a THIRD terminal state
(`unmeasurable`) requiring a registered defect id, the arm count, and the clean-run evidence.
Widening the excuse would weaken a LIVE bar, which this loop's rules forbid; a new state records
the same fact without moving the bar."

THE INSTANCE: composition_motif_link_edit, 35 runs across four arms, 17 transport failures
(~49%), and on the 18 CLEAN runs the tool was called 3/5, 4/5 and 5/5 with its supplier armed
and reached. Thirteen hypotheses for the transport failure were tested and refuted. At 49% a
transport-clean K=5 has ~3% probability, so re-running is not a path.

🔴 WHY A NEW STATE AND NOT AN EXCUSE. The tempting fix was to excuse the LIVE clean bar whenever
every errored run is a named transport defect. That is a weaker bar for EVERY tool, bought to
move one. And filing such a tool `blocked` is not free either: `blocked` reads as a property of
the TOOL, when the failure is the platform's.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate  # noqa: E402


def _tool(**over):
    row = {"state": "unmeasurable",
           "blocked_by_defect": "D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10",
           "arms": "4 arms, 35 runs, 17 transport failures (~49%)",
           "clean_run_evidence": "18 clean runs; called 3/5, 4/5 and 5/5 with the supplier armed"}
    row.update(over)
    return {"tools": {"t": row}}


class TestTheStateIsInTheClosedSet:
    def test_it_is_terminal(self):
        assert "unmeasurable" in gate.TERMINAL

    def test_the_two_that_were_there_are_still_there(self):
        """Adding a state must not quietly retire one — every derived count reads TERMINAL."""
        assert {"proven", "blocked"} <= set(gate.TERMINAL)


class TestTheBarIsReal:
    def test_a_fully_evidenced_row_passes(self):
        assert gate.unevidenced_unmeasurable(_tool()) == {}

    def test_a_missing_defect_id_is_refused(self):
        """Without it the state is 'it did not work and I stopped' — `blocked` in kinder words,
        and a platform bug hidden inside a tool's row."""
        assert "blocked_by_defect" in gate.unevidenced_unmeasurable(
            _tool(blocked_by_defect=""))["t"]

    def test_a_missing_arm_count_is_refused(self):
        assert "arms" in gate.unevidenced_unmeasurable(_tool(arms=""))["t"]

    def test_missing_clean_run_evidence_is_refused(self):
        """🔴 THE FIELD THAT SEPARATES THIS STATE FROM `blocked`. The tool WAS exercised and did
        something; a row with no clean-run result has not earned the word."""
        assert "clean_run_evidence" in gate.unevidenced_unmeasurable(
            _tool(clean_run_evidence=""))["t"]

    def test_a_COUNTLESS_arm_claim_is_refused(self):
        """"It kept failing across several arms" is an impression. "17 of 35 across four arms"
        is a measurement, and only the second makes re-running provably not a path — the same
        rule the sibling state's `not_reproduced` already carries."""
        bad = gate.unevidenced_unmeasurable(_tool(arms="it failed on most of the arms"))["t"]
        assert any("arms" in m and "COUNT" in m for m in bad), bad

    def test_a_COUNTLESS_clean_run_claim_is_refused(self):
        bad = gate.unevidenced_unmeasurable(
            _tool(clean_run_evidence="the clean runs looked fine"))["t"]
        assert any("clean_run_evidence" in m and "COUNT" in m for m in bad), bad

    def test_other_states_are_untouched(self):
        """The bar applies to this state only — a `proven` row must not be dragged into it."""
        assert gate.unevidenced_unmeasurable({"tools": {"t": {"state": "proven"}}}) == {}
        assert gate.unevidenced_unmeasurable({"tools": {"t": {"state": "blocked"}}}) == {}


class TestAuditEnforcesIt:
    def test_the_audit_reads_the_check(self):
        """GUARD THE CALL SITE. A bar that `audit` never consults is decoration — the same
        mistake this repo has now recorded three times in one day."""
        import inspect

        src = inspect.getsource(gate.cmd_audit)
        assert "unevidenced_unmeasurable(" in src, (
            "cmd_audit never calls the check, so an unevidenced `unmeasurable` row passes")
        assert "not unmeasurable" in src, (
            "the check runs and its result is not part of the clean condition")


class TestTheLiveLedgerIsClean:
    def test_no_tool_currently_claims_it_unearned(self):
        import json

        ledger = json.loads(
            (ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(encoding="utf-8"))
        bad = gate.unevidenced_unmeasurable(ledger)
        assert not bad, f"tools at `unmeasurable` without the evidence: {bad}"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
