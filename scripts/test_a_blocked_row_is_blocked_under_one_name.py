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
    assert pointed, f"NEXT names no known defect row: {line!r}"
    assert not LEDGER["defects"][pointed].get(gate.DQ_FIELD), (
        f"NEXT points at {pointed}, which is blocked on "
        f"{LEDGER['defects'][pointed][gate.DQ_FIELD]} — the resume pointer is aimed at a "
        f"decision the owner has to make, not at work"
    )
