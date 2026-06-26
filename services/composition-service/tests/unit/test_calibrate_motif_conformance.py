"""Unit tests for the conformance calibration harness gate logic (W5, §3 + §7).

These are the OFFLINE, pure-logic guards (no live stack): the gate calibrates
INDEPENDENTLY on conformance-specific pairs (F-3 — it does NOT inherit the
extraction judge's F1), a single-class seed yields SHIP-UNCALIBRATED (gap5 /
calibrate_judge degeneracy), and shipping uncalibrated is an accepted outcome.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the script module by path (scripts/ is not a package). Register in
# sys.modules BEFORE exec so the @dataclass field-type resolution can find the
# module's namespace (dataclasses looks up cls.__module__ in sys.modules).
_SPEC = importlib.util.spec_from_file_location(
    "calibrate_motif_conformance",
    Path(__file__).resolve().parents[2] / "scripts" / "calibrate_motif_conformance.py",
)
cal = importlib.util.module_from_spec(_SPEC)
sys.modules["calibrate_motif_conformance"] = cal
_SPEC.loader.exec_module(cal)  # type: ignore[union-attr]


def _row(gold_r, gold_t, judge_r, judge_t):
    return {
        "scene_text": "x", "gold_beat_realized": gold_r, "gold_tension_band_match": gold_t,
        "tension_band": [50, 70],
        "_judge": {"beat_realized": judge_r, "tension_band_match": judge_t},
    }


def test_gate_ship_uncalibrated_on_empty_seed():
    # the §6.2 ship condition: an empty seed prints SHIP UNCALIBRATED, never crashes.
    g = cal.compute_gate([], [])
    assert g.verdict == "SHIP UNCALIBRATED"
    assert g.calibrated is False
    assert g.n_a == 0


def test_gate_single_class_does_not_calibrate():
    # gap5 / kappa-degeneracy: all-positive gold → kappa undefined → NOT calibrated
    # even though the judge "agrees" — the harness needs both classes.
    rows = [_row(True, True, True, True) for _ in range(6)]
    g = cal.compute_gate(rows, [])
    assert g.calibrated is False
    assert g.verdict == "SHIP UNCALIBRATED"
    # the sub-flag calibration ran (F-3 — independent), it just can't pass single-class
    assert g.cal_realized_a is not None
    assert g.cal_realized_a.cohen_kappa is None  # degenerate single-class


def test_gate_calibrates_when_both_classes_agree():
    # a balanced seed where the judge agrees perfectly on BOTH classes + BOTH flags
    # → CALIBRATED (the harness independently earns trust, F-3).
    rows = (
        [_row(True, True, True, True) for _ in range(5)]
        + [_row(False, False, False, False) for _ in range(5)]
    )
    g = cal.compute_gate(rows, [])
    assert g.calibrated is True
    assert g.verdict == "CALIBRATED"
    assert g.cal_realized_a.passed and g.cal_tension_a.passed


def test_gate_decision_rests_on_A_not_AB():
    # B (model-as-gold) is reported but NEVER flips the decision: a perfect A that
    # fails because tension disagrees stays uncalibrated even if B "agrees".
    rows_a = (
        [_row(True, True, True, False) for _ in range(5)]      # tension judge always wrong
        + [_row(False, False, False, False) for _ in range(5)]
    )
    rows_b = [_row(True, True, True, True) for _ in range(20)]  # B floods agreement
    g = cal.compute_gate(rows_a, rows_b)
    # beat_realized passes on A, but tension_band_match does not → not calibrated
    assert g.calibrated is False
    # A+B is computed for the report (coverage), but did not drive the decision
    assert g.cal_realized_ab is not None


def test_pairs_drop_unjudged_rows():
    # a judge None (unjudged) is NOT a label — it must be dropped, not coerced.
    rows = [
        _row(True, True, True, True),
        {"scene_text": "y", "gold_beat_realized": True, "gold_tension_band_match": True,
         "_judge": {"beat_realized": None, "tension_band_match": None}},
    ]
    pr = cal._pairs(rows, "beat_realized")
    assert len(pr) == 1  # the unjudged row dropped


def test_load_gold_skips_meta_and_seeds_present():
    # the committed PO seed loads (skipping the _comment/schema header lines).
    rows = cal.load_gold(cal.PO_SEED)
    assert len(rows) >= 2  # the illustrative rows
    assert all("scene_text" in r for r in rows)
    # the seed carries BOTH classes (drift negatives present) — the calibrate-ability
    # precondition the §3.3 note demands.
    realized = {r["gold_beat_realized"] for r in rows}
    assert realized == {True, False}
