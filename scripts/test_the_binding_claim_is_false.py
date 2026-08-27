"""D-THE-MODEL-CLAIMS-A-BINDING-IT-NEVER-MADE, and the silent-turn probe that found it.

    THE INVARIANT. A reply that reports a write is evidence about the model, not about the
    store — and the store is what says whether it happened.

Asked "Attach Emberfall Seam to the opening arc as this book's motif.", the model calls
composition_motif_search and composition_package_tree — both READS — and then reports the
binding as done, on 5 of 5 runs, in 86–143 characters of confident prose phrased differently
each time. The store is unchanged on every one.

WHY IT IS NOT A FIXTURE ARTEFACT, which is the first thing that could make this a false alarm:
the scenario's own seed_assert requires ZERO bindings for the motif before the turn and it
passed, so nothing arrived pre-bound. `motif_application` is swept by the DATA bar and DOES
appear in a diff when a binding is written. composition_motif_bind_edit was called 0 of 5 times
and was on the wire in 0 of 27 passes, so the tool that performs the binding was never reached.

🔴 REATTRIBUTED 2026-08-27, AND THE 5/5 ABOVE IS THE REASON THE ARM WAS RUN. The row's own
open question was whether the tool's absence LICENSES the confabulation or whether the model
would claim it anyway. c-bindwire1 answers it: same scenario, same fixture, one word changed so
the turn reaches the tool by its own declared synonym —

                                        c-silentprobe1        c-bindwire1
    composition_motif_bind_edit advertised   0 of 27 passes      5 of 5 runs
    the tool CALLED                          0 of 5              5 of 5
    reply claims the binding is DONE         5 of 5              0 of 5
    motif_application changed                0 of 5              0 of 5

The confabulation did not survive the tool. Given something to call the model called it every
time and reported the failure honestly. So the row is PLATFORM-class now, and this suite
asserts that rather than the model attribution it was written under — the claim below is not
weakened, it is re-pointed at what the evidence says.

THE BATCH WAS RUN FOR A DIFFERENT ROW. D-SILENT-TURN-NO-CARD-NO-PROSE calls this scenario its
reliable trigger — 0 clean runs in 23 attempts — and it had not been exercised since
2026-08-22, which meant the recent absence of silent turns was the absence of the TRIGGER
rather than of the defect. The probe found 0 of 5 silent turns, which is the first evidence in
either direction since then and is weaker than it looks: a turn that never reaches for the tool
has not tested a defect about emitting a call.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

RAW = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-silentprobe1-raw.json"
LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))
CLAIM = ("attached", "i've attached", "bound", "added the motif")


def _runs():
    if not RAW.exists():
        pytest.skip("the probe batch is not on disk")
    return json.loads(RAW.read_text(encoding="utf-8"))


def test_every_run_CLAIMS_the_binding():
    runs = _runs()
    assert len(runs) == 5
    claimed = [r for r in runs if any(c in (r.get("text") or "").lower() for c in CLAIM)]
    assert len(claimed) == 5, [r.get("text") for r in runs]


def test_and_the_STORE_never_moved():
    """🔴 THE HALF THAT MAKES IT A DEFECT RATHER THAN A STYLE NOTE."""
    for r in _runs():
        assert not (r.get("store_diff") or {}), r.get("store_diff")


def test_the_TOOL_that_binds_was_never_even_advertised():
    """It cannot have run. 0 calls and 0 passes carrying it — so this is not 'the tool failed
    and the model misread the result', it is a claim with no attempt behind it."""
    for r in _runs():
        assert "composition_motif_bind_edit" not in fr.called_names(r)
        names = {n for p in (r.get("wire_passes") or []) for n in p.get("names") or []}
        if names:
            assert "composition_motif_bind_edit" not in names, "the tool WAS on the wire"


def test_the_fixture_was_NOT_pre_bound():
    """The control that could have made this a false alarm: the scenario asserts zero bindings
    before the turn, so the model is not truthfully reporting a seeded state.

    Read from scenarios-batch26.json, the scenario the batch was RUN against. A copy of it was
    made for the probe and then DELETED — three guards fired on it and all three were right,
    including the reachability gate added earlier the same day, which flagged the turn as unable
    to reach the tool before the live run confirmed 0 of 27 passes."""
    d = json.loads((ROOT / "scripts" / "toolloop" / "scenarios-batch26.json").read_text(
        encoding="utf-8"))
    sc = next(s for s in d["scenarios"] if s["id"] == "composition-motif-bind-edit")
    asserts = json.dumps(sc.get("seed_assert") or [])
    assert "motif_application" in asserts and '"expect": "0"' in asserts, asserts


def test_no_run_errored_so_this_is_not_a_dead_turn():
    for r in _runs():
        assert not r.get("error"), r.get("error")
        assert not r.get("pending_approval"), "a card is not a claim"


def test_the_probe_found_ZERO_silent_turns():
    """What the batch was actually run for."""
    silent = [r for r in _runs()
              if not (r.get("text") or "").strip()
              and not r.get("pending_approval") and not r.get("error")]
    assert silent == [], silent


def test_both_rows_carry_the_result():
    assert "D-THE-MODEL-CLAIMS-A-BINDING-IT-NEVER-MADE" in LEDGER["defects"]
    new = LEDGER["defects"]["D-THE-MODEL-CLAIMS-A-BINDING-IT-NEVER-MADE"]
    assert new["state"] == "open"
    # 🔴 PLATFORM, NOT MODEL, and the guard names WHY so the reattribution cannot be undone by
    # someone who only reads this line. c-bindwire1 put the tool on the wire and the claim
    # disappeared — 5/5 -> 0/5 — so the behaviour is a property of the surface, not the model.
    assert new["defect_class"] == "platform", (
        "the row is back to model-class; if that is deliberate it must answer c-bindwire1, "
        "where the same scenario with the tool advertised produced 0 of 5 false claims"
    )
    assert new.get("blocked_by_dq") == "DQ-T58"
    assert "c-bindwire1" in json.dumps(new), "the row no longer cites the arm it rests on"
    old = LEDGER["defects"]["D-SILENT-TURN-NO-CARD-NO-PROSE"]
    assert "the_trigger_was_re_run_2026_08_27" in old
    assert "WEAKER EVIDENCE THAN IT LOOKS" in old["the_trigger_was_re_run_2026_08_27"]
