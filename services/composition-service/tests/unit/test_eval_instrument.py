"""Teeth for the seeded-defect instrument (spec §S10).

The instrument's own failure mode is the one it was built to fix: a suite that reports a
clean green while measuring nothing. `eval_a2_canon.py` gates on the detector FIRING across
five scenarios of one class, with no control — a result produced identically by a working
canon loop and by an engine that revises every scene unconditionally.

So these tests attack the scorer and the gate, not the engine.
"""
from __future__ import annotations

import pytest

from app.eval.defects import DEFECTS, MIN_CLASSES, DefectClass, Observation, Outcome
from app.eval.gate import main as gate_main
from app.eval.suite import observe, score_class, score_suite

_CANON = DEFECTS[0]
_FIRES = Observation(fields={"status": "checked", "iterations": 1})
_QUIET = Observation(fields={"status": "checked", "iterations": 0})


# ── the property the old harness could not express ────────────────────────────────────────

def test_a_detector_that_also_fires_on_the_clean_control_is_not_detection():
    """THE test. `eval_a2_canon.py` would report this as 5/5 PASS."""
    r = score_class(_CANON, seeded=_FIRES, control=_FIRES)
    assert not r.detected
    assert r.over_flagged
    assert "OVER-FLAGS" in r.verdict()


def test_fired_on_the_defect_and_quiet_on_the_control_is_detection():
    r = score_class(_CANON, seeded=_FIRES, control=_QUIET)
    assert r.detected and r.verdict() == "detected"


def test_quiet_everywhere_is_a_miss_not_a_pass():
    r = score_class(_CANON, seeded=_QUIET, control=_QUIET)
    assert not r.detected and r.missed and "MISSED" in r.verdict()


def test_an_inverted_detector_is_named_as_such():
    """Quiet on the defect, loud on the clean run — the worst case, and one that a
    fires-count would score as 0/1 without saying why."""
    r = score_class(_CANON, seeded=_QUIET, control=_FIRES)
    assert "INVERTED" in r.verdict()


# ── an outage must never read as a clean engine ───────────────────────────────────────────

def test_a_failed_run_is_its_own_outcome():
    """Folding ERROR into QUIET scores an outage as a detector that correctly stayed silent —
    a MISS on the seeded run, a PASS on the control. Either number is fiction."""
    assert observe(_CANON, Observation(failed=True)) is Outcome.ERROR
    r = score_class(_CANON, seeded=Observation(failed=True), control=_QUIET)
    assert r.errored and not r.detected and "ERROR" in r.verdict()


def test_an_errored_variant_contributes_no_confusion_pair():
    """Scoring it either way invents a data point in the 2x2 the report is built on."""
    clean = score_suite([(_CANON, _FIRES, _QUIET)]).confusion
    assert clean.n == 2
    errored = score_suite([(_CANON, Observation(failed=True), _QUIET)]).confusion
    assert errored.n == 1, "the failed run leaked into the confusion matrix"


def test_over_flagging_is_visible_as_a_number_not_just_a_verdict():
    """`fp` is the count the old harness had no way to produce."""
    cm = score_suite([(_CANON, _FIRES, _FIRES)]).confusion
    assert cm.tp == 1 and cm.fp == 1
    assert "over-flagged 1" in score_suite([(_CANON, _FIRES, _FIRES)]).summary()


# ── the registry must stay able to measure ────────────────────────────────────────────────

def test_the_registry_carries_enough_classes_to_catch_a_new_regression():
    assert len(DEFECTS) >= MIN_CLASSES


@pytest.mark.parametrize("d", DEFECTS, ids=lambda d: d.code)
def test_every_class_has_a_distinct_control_and_a_provenance(d: DefectClass):
    assert d.control.strip(), "a seeded hit alone cannot prove the detector is specific"
    assert d.control.strip() != d.seeded.strip()
    assert d.provenance.strip(), "an invented defect drifts from the engine and rots"


@pytest.mark.parametrize("d", DEFECTS, ids=lambda d: d.code)
def test_no_detector_is_a_constant(d: DefectClass):
    """A detector reading fields that no longer exist degrades to a constant, which is
    invisible in the source and reports a clean green forever."""
    empty = Observation(fields={})
    saturated = Observation(fields={
        "status": "checked", "iterations": 9, "scenes_covered": 9,
        "target_words": 900, "actual_words": 1, "finish_reason": "length",
        "unresolved_refs": 3,
    })
    assert d.detector(empty) != d.detector(saturated)


def test_no_two_classes_share_a_detector():
    ids = [id(d.detector) for d in DEFECTS]
    assert len(set(ids)) == len(ids), "two classes sharing a detector inflate the class count"


# ── the gate itself ───────────────────────────────────────────────────────────────────────

def test_the_gate_passes_on_the_real_registry(capsys):
    assert gate_main() == 0
    assert "PASS" in capsys.readouterr().out


def test_the_gate_reds_when_the_registry_is_degenerate(monkeypatch, capsys):
    """Injected rather than asserted: a gate whose red path is never exercised is the same
    unproven claim it exists to reject."""
    import app.eval.gate as gate

    monkeypatch.setattr(gate, "DEFECTS", DEFECTS[:1])
    assert gate.main() == 1
    assert "MIN_CLASSES" in capsys.readouterr().out


def test_the_gate_reds_on_a_class_with_no_control(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    monkeypatch.setattr(gate, "DEFECTS",
                        tuple([replace(DEFECTS[0], control="")] + list(DEFECTS[1:])))
    assert gate.main() == 1
    assert "no control" in capsys.readouterr().out


def test_the_gate_reds_on_a_constant_detector(monkeypatch, capsys):
    import app.eval.gate as gate
    from dataclasses import replace

    monkeypatch.setattr(gate, "DEFECTS",
                        tuple([replace(DEFECTS[0], detector=lambda o: True)] + list(DEFECTS[1:])))
    assert gate.main() == 1
    assert "reads nothing that varies" in capsys.readouterr().out
