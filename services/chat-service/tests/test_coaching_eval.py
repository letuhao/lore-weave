"""WS-5.16/5.17/5.18 — the coaching eval harness (Gate 4 MECHANISM).

The load-bearing test is `test_gate_never_clears_in_a_code_run`: the whole point of SD-7 is
that no self-run may clear the numeric gate. The QWK tests use small HAND-VERIFIABLE
confusion matrices (not a scorer self-run) to prove the computation.
"""
from __future__ import annotations

import pytest

from app.services.coaching_eval import (
    GateStatus, evaluate_gate, judge_vs_consensus_qwk,
    quadratic_weighted_kappa, range_over_runs,
)


def test_qwk_perfect_agreement_is_one():
    assert quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0


def test_qwk_chance_agreement_is_zero():
    # 2x2, every cell equal → observed == expected → QWK 0 (hand-computed).
    assert quadratic_weighted_kappa([1, 1, 2, 2], [1, 2, 1, 2], min_rating=1, max_rating=2) == 0.0


def test_qwk_complete_disagreement_is_minus_one():
    assert quadratic_weighted_kappa([1, 1, 2, 2], [2, 2, 1, 1], min_rating=1, max_rating=2) == -1.0


def test_qwk_is_symmetric():
    a, b = [1, 3, 5, 2, 4], [2, 3, 4, 2, 5]
    assert quadratic_weighted_kappa(a, b) == pytest.approx(quadratic_weighted_kappa(b, a))


def test_qwk_all_same_rating_is_perfect():
    assert quadratic_weighted_kappa([3, 3, 3], [3, 3, 3]) == 1.0


def test_qwk_raises_on_mismatch_or_empty():
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([1, 2], [1])
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([], [])


def test_judge_vs_consensus_delegates():
    assert judge_vs_consensus_qwk([1, 2, 3], [1, 2, 3]) == 1.0


def test_range_over_runs_flags_single_run():
    assert range_over_runs([0.7])["single_run"] is True
    r = range_over_runs([0.6, 0.7, 0.8])
    assert r["min"] == 0.6 and r["max"] == 0.8 and r["single_run"] is False


# ── SD-7 — the gate can NEVER be cleared inside a code run ────────────────────
def test_gate_never_clears_in_a_code_run():
    # a code run has ZERO human raters → fail-closed, always.
    st = evaluate_gate(n_transcripts=1000, n_human_raters=0, threshold_qwk=0.6,
                       run_qwks=[0.99, 0.99, 0.99])
    assert isinstance(st, GateStatus)
    assert st.cleared is False
    assert st.reason == "no_human_labels"


def test_gate_reports_shortfall_reasons_with_synthetic_human_data():
    # These use SYNTHETIC labels to prove the gate LOGIC — not a scorer self-run.
    assert evaluate_gate(n_transcripts=10, n_human_raters=2, threshold_qwk=0.6,
                         run_qwks=[0.9, 0.9, 0.9]).reason == "insufficient_sample"
    assert evaluate_gate(n_transcripts=60, n_human_raters=2, threshold_qwk=0.6,
                         run_qwks=[0.9]).reason == "need_range_over_3_runs"
    assert evaluate_gate(n_transcripts=60, n_human_raters=2, threshold_qwk=0.6,
                         run_qwks=[0.4, 0.5, 0.55]).reason == "below_threshold"


def test_gate_logic_clears_only_with_full_synthetic_inputs():
    # Proves the CLEAR branch exists + uses the RANGE FLOOR (min), not the mean. This is a
    # logic test with fabricated inputs; a real clearance requires a human-rating milestone.
    st = evaluate_gate(n_transcripts=60, n_human_raters=2, threshold_qwk=0.6,
                       run_qwks=[0.61, 0.7, 0.8])
    assert st.cleared is True and st.reason == "cleared"
    # if the FLOOR dips below threshold the gate does NOT clear, even if the mean is high
    st2 = evaluate_gate(n_transcripts=60, n_human_raters=2, threshold_qwk=0.6,
                        run_qwks=[0.59, 0.9, 0.9])
    assert st2.cleared is False
