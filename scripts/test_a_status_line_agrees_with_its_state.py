"""D-A-ROWS-STATUS-PROSE-CONTRADICTS-ITS-OWN-STATE.

    THE INVARIANT. A defect row's `status` may say anything after its first word, but it may
    not OPEN by asserting a disposition the row does not have.

🔴 FOUND BY A READER GETTING IT WRONG, which is the only way this kind of drift ever surfaces.
A stop hook read the ledger on 2026-08-27 and reported three CONTRACT defects as open and
actionable:

    D-A-REQUIRED-ARGUMENT-ONLY-THE-AUTHOR-CAN-SUPPLY-HAS-NO-ASK-PATH
    D-A-REQUIRED-ID-NO-TOOL-CAN-SUPPLY
    D-KG-BUILD-TAKES-A-PROJECT-ID-AND-NOTHING-TELLS-THE-MODEL-WHERE-TO-GET-IT

All three carry `state: fixed`. The first two OPEN their `status` with the word "OPEN", because
that line was written when the row was FILED and never rewritten when it was closed — the real
disposition went into `state_reason` instead. Seven rows were in that condition.

NO DERIVED NUMBER WAS EVER WRONG. `state` is the machine-readable field and every count,
including the run's own stop condition, already reads it. What was wrong is that the FIRST LINE
A HUMAN READS said the opposite of the row, and a reader who trusts the part written for them
is not being careless.

THE ORIGINAL SENTENCE IS KEPT VERBATIM on every repaired row, labelled as what the status said
when filed. A status is a historical record as well as a claim, and deleting the history to fix
the claim would trade one wrong reading for a missing one.

WHY A GATE AND NOT SEVEN EDITS: the drift is created by the ordinary act of closing a row, so
it regenerates. `gate.py audit` refuses on it, and refuses by NAME rather than rewriting — a
row edited by a tool is a row nobody re-read, which is the rule `dq_alias_drift` states one
block up in the same file.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate as gt  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))


def _led(**rows):
    return {"defects": rows}


def test_OPEN_prose_on_a_fixed_row_is_refused():
    out = gt.status_state_drift(_led(D_X={"state": "fixed", "status": "OPEN — measured today"}))
    assert "D_X" in out and "'OPEN'" in out["D_X"]


def test_FIXED_prose_on_an_open_row_is_refused_too():
    """Both directions. A row that reads FIXED while its state is open is the same lie, and it
    is the more dangerous one — it retires work that was never done."""
    out = gt.status_state_drift(_led(D_X={"state": "open", "status": "FIXED 2026-08-01 by …"}))
    assert "D_X" in out


def test_a_matching_lead_passes():
    assert gt.status_state_drift(_led(
        D_X={"state": "fixed", "status": "FIXED 2026-08-27 — the disposition is on …"})) == {}
    assert gt.status_state_drift(_led(
        D_X={"state": "open", "status": "OPEN — measured today"})) == {}


def test_a_lead_that_is_NOT_a_disposition_is_left_alone():
    """PRECISION, and it is why the hook's THIRD row is not on the list: D-KG-BUILD-… opens with
    "DECLARED and DEPLOYED …", which asserts nothing about open-vs-closed. A blanket check on
    "does the prose contain the word open" would have flagged half the ledger and been turned
    off."""
    for lead in ("DECLARED and DEPLOYED 2026-08-24 — and UNMEASURED.",
                 "MEASURED 2026-08-23, K=5.",
                 "REOPENED by its own gate.",
                 "STILL OPEN — the residual cause is unknown."):
        assert gt.status_state_drift(_led(D_X={"state": "fixed", "status": lead})) == {} or \
            lead.startswith("STILL"), lead


def test_the_em_dash_and_colon_forms_are_both_read():
    """The ledger writes `OPEN —`, `OPEN -`, `OPEN:` and bare `OPEN`. A lead parser that only
    handled one of them would silently pass most of the population."""
    # NOTE: a bare "OPENx" is NOT a lead of OPEN — the word has to end. That is the point of
    # splitting on whitespace first, and testing it as if it were would be testing the wrong
    # rule.
    for sep in ("— x", "- x", ": x", " x", ", x", ""):
        out = gt.status_state_drift(_led(D_X={"state": "fixed", "status": f"OPEN{sep}"}))
        assert "D_X" in out, sep


def test_a_row_with_no_status_or_no_state_is_not_invented():
    assert gt.status_state_drift(_led(D_X={"state": "fixed"})) == {}
    assert gt.status_state_drift(_led(D_X={"status": "OPEN — x"})) == {}
    assert gt.status_state_drift(_led(D_X="not a dict")) == {}


def test_the_REAL_ledger_is_clean():
    """ANTI-VACUITY against the live file — the seven originals are repaired and no new row has
    drifted since."""
    assert gt.status_state_drift(LEDGER) == {}


def test_the_repaired_rows_KEPT_their_original_sentence():
    """A status is a historical record as well as a claim. Deleting the history to fix the claim
    would trade one wrong reading for a missing one."""
    for name in ("D-A-REQUIRED-ARGUMENT-ONLY-THE-AUTHOR-CAN-SUPPLY-HAS-NO-ASK-PATH",
                 "D-A-REQUIRED-ID-NO-TOOL-CAN-SUPPLY"):
        st = LEDGER["defects"][name]["status"]
        assert st.startswith("FIXED"), st[:40]
        assert "WHAT THIS STATUS SAID WHEN THE ROW WAS FILED" in st
        assert "OPEN" in st, "the original wording was deleted rather than kept"


def test_audit_REFUSES_on_it():
    """🔴 THE CALL SITE. A checker `cmd_audit` does not read is a checker that never fires, and
    this loop has shipped that shape more than once."""
    src = (ROOT / "scripts" / "toolloop" / "gate.py").read_text(encoding="utf-8")
    at = src.index("def cmd_audit(")
    body = src[at:]
    assert "status_state_drift(ledger)" in body, "cmd_audit never calls the check"
    assert "not status_drift" in body, "the clean-exit branch does not consider it"
    assert "defect row(s) open their `status` prose with a " in body, "no refusal message"
    assert "disposition the row does not have" in body


def test_it_does_NOT_rewrite_the_row():
    """The repair is deliberately manual: a row rewritten by a tool is a row nobody re-read."""
    src = (ROOT / "scripts" / "toolloop" / "gate.py").read_text(encoding="utf-8")
    at = src.index("def status_state_drift(")
    body = src[at:src.index("def dangling_dq_links(", at)]
    assert "row[" not in body.replace('row.get(', ''), "the check mutates the row it is auditing"
