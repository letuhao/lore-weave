"""D-THE-RESUME-POINTER-AIMS-AT-A-BLOCKED-ROW — the cause was two names for one concept.

`goal_prompt_defects.py` reads `blocked_by_dq` and nothing else: it sorts those rows last,
never points NEXT at one, and `--check` ENDS THE WHOLE RUN when every open contract row carries
it. Measured 2026-08-26, five OPEN rows carried `dq` instead (DQ-T31, T44, T45, T46, T47) — all
of them stamped during this run by someone who did not check what the reader looked for.

Two consequences, both silent:

  * the QUEUE offered rows whose next step is an OWNER DECISION as ordinary work. It pointed
    NEXT at D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-RESTORABLE (blocked on DQ-T44), and all three
    rows it displayed were blocked, while seven unblocked contract rows existed and had to be
    derived by hand.
  * the STOP CONDITION under-counts blocked rows, so a run that is genuinely finished cannot
    be told so by its own instrument.

The gate refuses an alias rather than migrating it: a row rewritten by a tool is a row nobody
re-read, and each of these needed a human decision (one held PROSE under the marker's name, not
an id).
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "toolloop"))

import gate  # noqa: E402

LEDGER = json.loads((REPO / "contracts" / "tool-deep-dive-ledger.json").read_text(encoding="utf-8"))
GENERATOR = (REPO / "scripts" / "toolloop" / "goal_prompt_defects.py").read_text(encoding="utf-8")


def test_the_live_ledger_has_no_aliased_block():
    """The state the gate exists to hold. Every DQ block is under the one name."""
    assert gate.dq_alias_drift(LEDGER) == {}


def test_the_gate_catches_every_alias_it_declares():
    """Each alias must actually be detected — a name listed and not checked is decoration."""
    for alias in gate.DQ_ALIASES:
        fake = {"defects": {"D-X": {"state": "open", alias: "DQ-T99"}}}
        assert gate.dq_alias_drift(fake) == {"D-X": [alias]}, alias


def test_the_canonical_name_is_the_one_the_generator_READS():
    """The whole defect was a field nobody read. Pin the two ends together: if the generator is
    ever changed to read a different name, this fails rather than the queue going quietly
    wrong again."""
    assert gate.DQ_FIELD == "blocked_by_dq"
    assert f'v.get("{gate.DQ_FIELD}")' in GENERATOR, (
        "the generator no longer reads the field the gate calls canonical"
    )


def test_the_canonical_name_is_not_itself_an_alias():
    assert gate.DQ_FIELD not in gate.DQ_ALIASES


def test_an_unblocked_row_is_not_flagged():
    """PRECISION. The gate must not fire on ordinary rows, or it becomes noise that gets
    switched off — 169 of the ledger's rows carry no DQ at all."""
    fake = {"defects": {
        "D-OPEN": {"state": "open", "status": "..."},
        "D-FIXED": {"state": "fixed", "blocked_by_dq": "DQ-T31"},
    }}
    assert gate.dq_alias_drift(fake) == {}


def test_a_falsy_alias_value_is_not_a_block():
    """An empty string is not a DQ. Flagging it would make the gate impossible to satisfy for a
    row that legitimately carries the key with no value."""
    fake = {"defects": {"D-X": {"state": "open", "dq": ""}}}
    assert gate.dq_alias_drift(fake) == {}


def test_the_audit_REFUSES_when_an_alias_exists(tmp_path, monkeypatch, capsys):
    """The check has to be wired into the command, not merely defined. A helper nothing calls
    is the same shape of defect as a field nothing reads."""
    poisoned = json.loads(json.dumps(LEDGER))
    first = next(iter(poisoned["defects"]))
    poisoned["defects"][first]["dq"] = "DQ-T99"
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps(poisoned), encoding="utf-8")
    monkeypatch.setattr(gate, "LEDGER", p)
    monkeypatch.chdir(REPO)

    rc = gate.cmd_audit(pytest.importorskip("argparse").Namespace(fix_progress=False))
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "cannot read" in out and first in out, out
    assert "blocked_by_dq" in out, "the refusal must name the field to rename TO"


def test_the_generator_points_NEXT_at_something_actionable():
    """The user-visible symptom, asserted against the generator's REAL output.

    🔴 THE FIRST VERSION OF THIS TEST WAS A TAUTOLOGY: it partitioned the rows into blocked and
    actionable and then asserted no name was in both — true by construction, and it would have
    stayed green through the entire defect. Run the thing and read what it says.
    """
    import subprocess
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "toolloop" / "goal_prompt_defects.py")],
        cwd=REPO, capture_output=True, text=True,
    ).stdout
    line = next((ln for ln in out.splitlines() if ln.startswith("NEXT.")), "")
    assert line, f"the generator emitted no NEXT pointer:\n{out[-400:]}"
    pointed = next((n for n in LEDGER["defects"] if n in line), None)
    if pointed is None:
        # THE TERMINAL STATE IS A VALID POINTER. When every open contract defect is DQ-blocked
        # the generator says so instead of naming a row, and that is the run's stop condition —
        # not a broken pointer. The BAR is "never aim at a blocked row", which this satisfies
        # by aiming at no row at all. Asserting a row is always named would have made the
        # finished state look like a failure.
        assert "blocked on a dq" in line.lower() or "no unblocked contract work" in line.lower(), (
            f"NEXT names no known defect row and is not the terminal message: {line!r}"
        )
        return
    assert not LEDGER["defects"][pointed].get(gate.DQ_FIELD), (
        f"NEXT points at {pointed}, which is blocked on "
        f"{LEDGER['defects'][pointed][gate.DQ_FIELD]} — the resume pointer is aimed at a "
        f"decision the owner has to make, not at work"
    )


# ── The DQ block, added 2026-08-26 ────────────────────────────────────────────────────────
# The alias gate above deliberately covered only the DEFECTS block, and its row said so. That
# gap was real: censused, of 25 deferred questions 18 carried `state`, 3 carried `status`, 5
# carried NEITHER, and `state` was not a token at all — one held a whole paragraph.
#
# It matters because `blocked_by_dq` is only HALF a link. A defect points at a question, and
# whether that defect is ACTIONABLE depends on whether the question is still open.


def test_every_deferred_question_has_a_readable_state():
    assert gate.dq_state_drift(LEDGER) == {}


def test_no_defect_is_blocked_by_an_unregistered_question():
    """A row blocked on a question nobody wrote down can never be unblocked, and the owner has
    nothing to decide — it just silently shrinks the actionable queue."""
    assert gate.dangling_dq_links(LEDGER) == {}


def test_the_dq_state_check_catches_both_ways_of_being_unreadable():
    missing = {"deferred_questions": {"DQ-X": {"question": "?"}}}
    assert "DQ-X" in gate.dq_state_drift(missing)
    prose = {"deferred_questions": {"DQ-Y": {"state": "recommend withdrawn — pending owner"}}}
    assert "DQ-Y" in gate.dq_state_drift(prose)
    for good in gate.DQ_STATES:
        assert gate.dq_state_drift({"deferred_questions": {"DQ-Z": {"state": good}}}) == {}


def test_a_substring_is_not_a_state():
    """🔴 THE NEAR-MISS THIS WHOLE CHECK EXISTS FOR. Transcribing the state-less rows, a first
    pass tested `"ANSWERED" in status.upper()` before the open branch — and DQ-T31's status
    reads "OPEN — product decision, recorded per the RUNBOOK rather than answered". An OPEN
    product decision was marked ANSWERED. That question BLOCKS THREE contract defects, so the
    wrong token would have presented all three as ready to work on a decision the owner never
    made."""
    dq = LEDGER["deferred_questions"]["DQ-T31"]
    assert dq["state"] == "open", "DQ-T31 is an open product decision"
    assert "rather than answered" in dq["status"], (
        "the phrase that caused the mis-transcription is gone — if the status was rewritten, "
        "re-check that the state still matches what it says"
    )


def test_the_blocking_questions_are_all_genuinely_open():
    """The run's STOP CONDITION rests on this: 'every open contract defect is DQ-blocked' only
    means the work is finished if those questions are actually unanswered. A defect blocked by
    an ANSWERED question is work, not a block."""
    dqs = LEDGER["deferred_questions"]
    stale = {
        name: row[gate.DQ_FIELD]
        for name, row in LEDGER["defects"].items()
        if row.get("state") == "open"
        and row.get("defect_class") == "contract"
        and row.get(gate.DQ_FIELD)
        and dqs.get(row[gate.DQ_FIELD], {}).get("state") != "open"
    }
    assert not stale, f"blocked on a question that is no longer open: {stale}"
