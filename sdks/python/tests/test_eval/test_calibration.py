"""Q3.5 — judge calibration + panel safety (pure math, synthetic pairs)."""

from __future__ import annotations

from loreweave_eval.calibration import (
    balanced_accuracy,
    calibrate_judge,
    cohen_kappa,
    confusion,
    panel_safety,
    raw_agreement,
)


# ── cohen_kappa ───────────────────────────────────────────────────────


def test_kappa_perfect_agreement_is_one():
    pairs = [(True, True), (False, False), (True, True), (False, False)]
    assert cohen_kappa(pairs) == 1.0


def test_kappa_perfect_disagreement_is_minus_one():
    pairs = [(True, False), (False, True), (True, False), (False, True)]
    assert cohen_kappa(pairs) == -1.0


def test_kappa_chance_is_zero():
    pairs = [(True, True), (True, False), (False, True), (False, False)]
    assert abs(cohen_kappa(pairs)) < 1e-9


def test_kappa_degenerate_single_class_is_none():
    assert cohen_kappa([(True, True), (True, True)]) is None  # pe == 1


def test_kappa_empty_is_none():
    assert cohen_kappa([]) is None


# ── balanced_accuracy ─────────────────────────────────────────────────


def test_ba_perfect_is_one():
    assert balanced_accuracy([(True, True), (False, False)]) == 1.0


def test_ba_judge_misses_every_error_is_half():
    # one human-correct (judge agrees) + one human-incorrect (judge says correct)
    assert balanced_accuracy([(True, True), (False, True)]) == 0.5


def test_ba_none_when_a_class_is_absent():
    assert balanced_accuracy([(True, True), (True, False)]) is None  # no negatives


# ── confusion / raw_agreement ─────────────────────────────────────────


def test_confusion_counts():
    c = confusion([(True, True), (False, False), (False, True), (True, False)])
    assert (c.tp, c.tn, c.fp, c.fn) == (1, 1, 1, 1)
    assert c.n == 4


def test_raw_agreement():
    assert raw_agreement([(True, True), (False, False), (True, False)]) == 2 / 3
    assert raw_agreement([]) is None


# ── calibrate_judge gate ──────────────────────────────────────────────


def test_calibrate_passes_strong_judge():
    pairs = [(True, True)] * 8 + [(False, False)] * 8 + [(True, False), (False, True)]
    cal = calibrate_judge("strong", pairs)
    assert cal.passed is True
    assert cal.balanced_accuracy is not None and cal.balanced_accuracy >= 0.75
    assert cal.cohen_kappa is not None and cal.cohen_kappa >= 0.4
    assert cal.n_pairs == 18


def test_calibrate_fails_chance_judge():
    pairs = [(True, True), (True, False), (False, True), (False, False)]
    assert calibrate_judge("random", pairs).passed is False


def test_calibrate_fails_degenerate_set():
    cal = calibrate_judge("one-class", [(True, True)] * 5)
    assert cal.passed is False
    assert cal.balanced_accuracy is None


def test_calibrate_thresholds_tunable():
    # a moderate judge: passes a low bar, fails a high one
    pairs = [(True, True)] * 6 + [(False, False)] * 4 + [(True, False)] * 2 + [(False, True)] * 2
    assert calibrate_judge("mod", pairs, min_balanced_accuracy=0.5, min_kappa=0.1).passed is True
    assert calibrate_judge("mod", pairs, min_balanced_accuracy=0.95, min_kappa=0.9).passed is False


# ── panel_safety (anti-self-reinforcement) ────────────────────────────


def test_panel_safe_two_independent_judges():
    s = panel_safety({"ext", "filt"}, ["gemma", "phi4"])
    assert s.safe is True
    assert s.n_disjoint_judges == 2
    assert s.generators_in_panel == []


def test_panel_unsafe_when_generator_is_a_judge():
    s = panel_safety({"ext", "filt"}, ["gemma", "ext"])
    assert s.safe is False
    assert "ext" in s.generators_in_panel


def test_panel_unsafe_when_too_few_disjoint():
    s = panel_safety({"ext"}, ["gemma"])
    assert s.safe is False
    assert s.n_disjoint_judges == 1


def test_panel_safety_ignores_empty_excluded_refs():
    s = panel_safety({"", None}, ["a", "b"])  # type: ignore[arg-type]
    assert s.safe is True
    assert s.n_disjoint_judges == 2
