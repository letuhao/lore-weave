"""The two ledger-integrity seams added 2026-08-30, and the controls that keep them honest.

`gate.py audit` already asks five versions of "does the ledger agree with itself?" — orphaned
evidence, progress drift, a DQ block under an unreadable field name, an unreadable DQ state, a
row blocked on an UNREGISTERED question, and status prose contradicting `state`. Two questions it
did not ask were being answered by hand instead, once, in a session that happened to look:

  * A row blocked on a question that IS registered and has since been ANSWERED or WITHDRAWN.
    `dangling_dq_links` catches the unregistered case only. This is the opposite failure and the
    worse one: a dangling link makes a row unblockable forever, a STALE block makes an ACTIONABLE
    row look like it is waiting on the owner — so the queue hides work that is ready, and
    `--check` can report "everything left is blocked" while real work sits behind a closed
    decision. That is the stop condition failing silently.

  * A row citing an evidence file that is not on disk. A claim nobody can re-open is a claim
    nobody can check, and this loop's standing rule is that a ledger claim is a lead, not a fact.

🔴 EACH GUARD HAS A CONTROL, because a check that cannot go red is worse than no check: it
reports "clean" forever and nobody looks again. Both are proven to FIRE on injected drift, and
the evidence check is proven NOT to fire on the two shapes it must tolerate.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate  # noqa: E402

LEDGER = json.loads(
    (ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(encoding="utf-8"))


def _an_open_row() -> str:
    return next(k for k, v in LEDGER["defects"].items() if v.get("state") == "open")


def _a_closed_dq() -> str:
    return next(q for q, v in LEDGER["deferred_questions"].items()
                if v.get("state") in ("answered", "withdrawn"))


class TestTheLedgerIsCleanRightNow:
    """The baseline. If either of these ever fails, the finding is real — fix the LEDGER."""

    def test_no_open_row_is_blocked_on_a_closed_question(self):
        assert gate.stale_dq_blocks(LEDGER) == {}

    def test_every_cited_evidence_file_exists(self):
        assert gate.missing_evidence_paths(LEDGER) == {}


class TestTheStaleBlockGuardCanGoRed:
    def test_it_fires_when_an_open_row_points_at_a_closed_question(self):
        led = copy.deepcopy(LEDGER)
        row, dq = _an_open_row(), _a_closed_dq()
        led["defects"][row]["blocked_by_dq"] = dq
        found = gate.stale_dq_blocks(led)
        assert found.get(row) == (dq, led["deferred_questions"][dq]["state"])

    def test_a_FIXED_row_keeps_its_historical_block_without_being_flagged(self):
        """Scoped to OPEN rows on purpose: a closed row may legitimately keep the block it
        carried while it was open, as part of its own history. Flagging that would push people
        to delete history to quiet an instrument."""
        led = copy.deepcopy(LEDGER)
        row = next(k for k, v in led["defects"].items() if v.get("state") == "fixed")
        led["defects"][row]["blocked_by_dq"] = _a_closed_dq()
        assert row not in gate.stale_dq_blocks(led)

    def test_an_UNREGISTERED_question_is_left_to_its_own_check(self):
        """One question, one owner. `dangling_dq_links` already reports this shape, and two
        checks reporting the same row would double-count a single defect."""
        led = copy.deepcopy(LEDGER)
        row = _an_open_row()
        led["defects"][row]["blocked_by_dq"] = "DQ-T99999"
        assert row not in gate.stale_dq_blocks(led)
        assert gate.dangling_dq_links(led).get(row) == "DQ-T99999"


class TestTheEvidenceGuardCanGoRedAndDoesNotCryWolf:
    def test_it_fires_on_a_path_that_is_not_on_disk(self):
        led = copy.deepcopy(LEDGER)
        row = _an_open_row()
        led["defects"][row]["measured_by"] = "docs/eval/toolloop/2026-08-28/does-not-exist.json"
        assert gate.missing_evidence_paths(led).get(row) == [
            "docs/eval/toolloop/2026-08-28/does-not-exist.json"]

    def test_it_does_NOT_fire_on_prose_shorthand_for_a_SET_of_batches(self):
        """🔴 THE CONTROL THAT SHAPED THE REGEX. A row writes
        "…/c-motiflink10/11/15/16/17/18.json" as shorthand for six files. That is prose about a
        set, not a path, and a looser pattern reports it as one missing file on every single run.
        An instrument that cries wolf every run is one people learn to skip."""
        led = copy.deepcopy(LEDGER)
        row = _an_open_row()
        led["defects"][row]["note"] = (
            "see docs/eval/toolloop/2026-08-14/c-motiflink10/11/15/16/17/18.json")
        assert row not in gate.missing_evidence_paths(led)

    def test_it_does_NOT_fire_on_a_path_that_exists(self):
        led = copy.deepcopy(LEDGER)
        row = _an_open_row()
        led["defects"][row]["note"] = "docs/eval/toolloop/2026-08-28/c-canonrestore3.json"
        assert row not in gate.missing_evidence_paths(led)


class TestTheAuditActuallyCALLSThem:
    """🔴 CALL-SITE GUARD. Both helpers can be perfect and unreferenced — the exact shape of
    "a registry absent from the image is a silently dead mechanism". `audit` prints "clean" from
    ONE condition, so the names must appear in it or the checks never run."""

    SRC = (ROOT / "scripts" / "toolloop" / "gate.py").read_text(encoding="utf-8")

    def test_both_are_computed_in_cmd_audit(self):
        i = self.SRC.index("def cmd_audit(")
        body = self.SRC[i:i + 4000]
        assert "stale_dq_blocks(ledger)" in body
        assert "missing_evidence_paths(ledger)" in body

    def test_both_gate_the_clean_verdict(self):
        i = self.SRC.index("def cmd_audit(")
        clean = self.SRC[i:self.SRC.index("audit clean —", i)]
        assert "not stale_blocks" in clean, "a stale block would still print 'audit clean'"
        assert "not missing_ev" in clean, "a dead evidence pointer would still print 'audit clean'"
