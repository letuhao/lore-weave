"""A row that stopped reproducing must leave the open set — and must not claim it was fixed.

    THE INVARIANT. A defect sits in the OPEN set only while it can be made to happen again.
    A defect that no longer reproduces is TERMINAL but NOT `fixed`, and the state that says so
    costs three named pieces of evidence: the original instance, the re-run that no longer shows
    it WITH A COUNT, and what was never demonstrated.

OWNER RULING 2026-08-31, verbatim:

    "mark as cannot produce or something, it gone dont mean it fix but dont mean it open,
     an open one must be reproduce"

WHY THE STATE WAS NEEDED — three rows, all blocked on a question that was really this one:

    T1-D2                                        DQ-T84  trigger is a MODEL ERROR, not commandable
    D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT     DQ-T81  a fix elsewhere destroyed the trigger
    D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10  DQ-T79  instrument row, cause never bought

Each had been repaired or had expired, and each reported itself as outstanding work, because the
vocabulary offered only `fixed` (which overstates) and `open` (which misreports). `--check` then
counted them as work nobody could do.

🔴 AND THE STATE IS A DRAIN IF IT IS NOT GUARDED, which is the half these tests exist for. It
removes a row from the queue and from `--check` exactly as `fixed` does, while asking for no fix
— so "it does not reproduce" would become the cheapest exit in the ledger. The bar makes the
claim checkable rather than true: an instance to go back to, a count, and the un-demonstrated
half in writing. No check here can re-run a scenario, and none of them pretends to.

WHAT WOULD MAKE THESE VACUOUS, tested explicitly below: a guard that refuses every row (so it
proves nothing about the ones it lets past), and a guard that is never called by `audit` (the
call site, not the helper — a mechanism absent from the path that runs is a dead mechanism).
"""
from __future__ import annotations

import inspect
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate  # noqa: E402

LEDGER_PATH = ROOT / "contracts" / "tool-deep-dive-ledger.json"

#: A row that has paid the bar in full. Used as the anti-vacuity control.
PAID = {
    "state": "cannot_reproduce",
    "original_instance": "docs/eval/toolloop/2026-08-14/c-override3-raw.json — 4 of 4",
    "not_reproduced": "0 of 20 post-fix runs across three configurations",
    "never_demonstrated": "no stalling instance of THIS row was ever captured and shown to be "
                          "the mechanism that was fixed.",
}


def _ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def test_the_state_exists_and_is_terminal_but_is_not_fixed():
    """The vocabulary has a word between `open` and `fixed`, and it is not a synonym for either."""
    assert "cannot_reproduce" in gate.DEFECT_STATES
    assert "cannot_reproduce" in gate.DEFECT_TERMINAL_STATES
    assert "cannot_reproduce" not in gate.DEFECT_OPEN_STATES
    # The two it must not collapse into. `withdrawn` means it was never a defect; this means it
    # was one and the evidence that it still is has expired.
    assert "fixed" in gate.DEFECT_TERMINAL_STATES and "withdrawn" in gate.DEFECT_TERMINAL_STATES


def test_a_row_cannot_assert_the_state_about_itself():
    """The drain, closed. Each of the three fields is load-bearing and is checked one at a time."""
    for field in gate.CANNOT_REPRODUCE_FIELDS:
        row = dict(PAID)
        row.pop(field)
        got = gate.unevidenced_cannot_reproduce({"defects": {"D-X": row}})
        assert "D-X" in got, f"a row missing {field!r} was allowed to leave the open set"
        assert any(field in g for g in got["D-X"])


def test_it_does_not_reproduce_is_refused_without_a_count():
    """0-of-N is a measurement; 'it does not reproduce' is an absence of looking.

    This ledger has already recorded reading the second as the first — absence of recent traffic
    taken as evidence of removal — so the count is required rather than encouraged.
    """
    row = dict(PAID, not_reproduced="it does not reproduce any more")
    got = gate.unevidenced_cannot_reproduce({"defects": {"D-X": row}})
    assert "D-X" in got and any("count" in g for g in got["D-X"])

    assert not gate.unevidenced_cannot_reproduce({"defects": {"D-X": dict(PAID)}}), \
        "the fully-paid control is refused — the guard would prove nothing about what it passes"


def test_the_guard_does_not_touch_rows_in_any_other_state():
    """Scoped to the state it guards. A guard that fires on `open` rows would be measuring
    something else entirely, and its refusals would be read as this bar."""
    for state in gate.DEFECT_STATES:
        if state == "cannot_reproduce":
            continue
        bare = {"state": state}
        assert not gate.unevidenced_cannot_reproduce({"defects": {"D-X": bare}}), state


def test_audit_actually_calls_the_guard():
    """GUARD THE CALL SITE. `unevidenced_cannot_reproduce` returning the right answer is worth
    nothing if `audit` never asks it, and this loop has shipped exactly that failure before."""
    src = inspect.getsource(gate.cmd_audit)
    assert "unevidenced_cannot_reproduce(ledger)" in src
    # It must also be able to make the audit REFUSE — being computed and then ignored is the
    # same as not being called.
    assert "not unevidenced" in src, "the guard is computed but does not gate the clean verdict"


def test_every_such_row_in_the_shipped_ledger_has_paid():
    """The rows this state was created for, held to the bar it was created with."""
    ledger = _ledger()
    rows = {k: v for k, v in ledger["defects"].items()
            if isinstance(v, dict) and v.get("state") == "cannot_reproduce"}
    assert rows, "the state exists and nothing uses it — either the rows moved back or the " \
                 "ruling was never applied"
    assert not gate.unevidenced_cannot_reproduce(ledger)
    for name, row in rows.items():
        # The row must still name the question whose answer moved it, so the ruling stays
        # traceable from the row rather than only from this file.
        # 🔴 THE WINDOW MISSED WHERE THE LEDGER ACTUALLY WRITES DATES. This read the
        # VALUES only, and only the hyphenated form. This ledger dates a development by
        # naming a KEY for it, with underscores — `unblocked_2026_08_31_round3`,
        # `currency_extended_to_the_newest_data__2026_08_31` — so two rows that trace the
        # ruling perfectly well read as undated. Measured over all eight cannot_reproduce
        # rows: six carry the hyphenated form in a value, and ALL EIGHT carry the ruling in
        # the row somewhere. Widen the window to the whole row and accept the separator the
        # file uses; the requirement — the ruling is traceable FROM THE ROW — is unchanged.
        blob = json.dumps(row)
        assert "2026-08-31" in blob or "2026_08_31" in blob, (
            f"{name} does not date the ruling that moved it — a row in this state must "
            "carry the 2026-08-31 ruling, in a value or in a key, or the ruling is "
            "traceable only from this test file")


def test_the_open_count_no_longer_carries_them():
    """The point of the exercise: `--check` stops reporting work nobody can do."""
    ledger = _ledger()
    progress = gate.recompute_progress(ledger)
    assert progress["defects_cannot_reproduce"] >= 3
    still_open = {k for k, v in ledger["defects"].items()
                  if isinstance(v, dict) and v.get("state") in gate.DEFECT_OPEN_STATES}
    for gone in ("T1-D2", "D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT",
                 "D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10"):
        assert gone not in still_open


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
