"""Unit tests for tests/quality/judge_ensemble.py — pure logic, no LLM calls.

Covers:
- Fleiss kappa correctness on canonical small examples
- _combine_votes: all-agree, 2/3-agree, 0-agree (disputed) cases
- D11 ensemble failure paths: complete / incomplete / failed judge_status
- D11 kappa_basis: items where ALL completed judges voted on
- D11 no-silent-2-judge fallback: ensemble_acceptable requires ≥ 2 complete
- D12 bias metric formulas: strictness_gap, language_bias, rp_bias
- assemble_report integration: end-to-end report shape

Mirrors spec sections D3, D11, D12.

NOTE on import path: this file lives at sdks/python/tests/ but the module
under test lives at services/knowledge-service/tests/quality/. Import via
explicit sys.path manipulation; running pytest from monorepo root resolves
both trees.
"""

from __future__ import annotations

import pytest

# loreweave_eval is the shared SDK home of the ensemble + judge (lifted from
# knowledge-service/tests/quality in track phase Q0). No sys.path hacks or
# app-module stubs are needed any more — these are plain installed-SDK imports,
# and the judge's LLM client is an injected Protocol, not an `app.clients` dep.
from loreweave_eval.judge_ensemble import (
    BiasMetric,
    EnsembleItemVote,
    EnsembleReport,
    JudgeRunResult,
    JudgeVerdict,
    _combine_votes,
    _compute_bias_metrics,
    _fleiss_kappa,
    _kappa_interpretation,
    assemble_report,
    chapter_language,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _v(chapter: str, category: str, kind: str, idx: int, verdict: str) -> JudgeVerdict:
    """Compact JudgeVerdict factory for test brevity."""

    return JudgeVerdict(
        chapter=chapter,
        category=category,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        idx=idx,
        verdict=verdict,  # type: ignore[arg-type]
    )


def _jr(
    uuid: str,
    label: str,
    status: str,
    verdicts: list[JudgeVerdict] | None = None,
    failure: str = "",
) -> JudgeRunResult:
    """Compact JudgeRunResult factory."""

    return JudgeRunResult(
        judge_uuid=uuid,
        judge_label=label,
        judge_status=status,  # type: ignore[arg-type]
        verdicts=verdicts or [],
        failure_reason=failure,
    )


# ── Fleiss kappa tests ────────────────────────────────────────────────────────


def test_fleiss_kappa_perfect_agreement() -> None:
    """3 raters all vote 'supported' on all items → κ should be 1.0 (single-cat
    handled as perfect agreement per implementation note)."""

    item_votes = [{"supported": 3}, {"supported": 3}, {"supported": 3}]
    kappa = _fleiss_kappa(item_votes, n_raters=3)
    assert kappa == 1.0


def test_fleiss_kappa_perfect_disagreement_on_two_categories() -> None:
    """Split 3-way → each rater chose differently. κ should be very low or
    negative. With 3 raters voting differently on a 3-category problem,
    P_i for each item = 0 → κ approaches floor."""

    item_votes = [{"a": 1, "b": 1, "c": 1}] * 10
    kappa = _fleiss_kappa(item_votes, n_raters=3)
    # κ should be ≤ 0 — chance-only or worse
    assert kappa <= 0.05


def test_fleiss_kappa_mostly_unanimous_with_one_split() -> None:
    """Strong agreement pattern: 5 items all-agree (3/0) + 1 item split (2/1).
    Expect κ in moderate range (~0.4-0.5). Verifies the chance-correction
    actually rewards substantial agreement vs. chance."""

    item_votes = [
        {"supported": 3},
        {"supported": 3},
        {"supported": 3},
        {"supported": 3},
        {"supported": 3},
        {"supported": 1, "unsupported": 2},
    ]
    kappa = _fleiss_kappa(item_votes, n_raters=3)
    assert 0.3 < kappa <= 0.6, f"expected moderate κ, got {kappa:.3f}"


def test_fleiss_kappa_2_of_3_split_yields_subchance() -> None:
    """Real Fleiss behavior: when every item is 2:1 between two categories
    AND the overall category distribution is skewed, κ comes out below
    chance (negative). This is correct math, not a bug — agreement is no
    better than what chance predicts under the marginal distribution.
    Documenting this so future maintainers don't 'fix' the formula."""

    item_votes = [
        {"supported": 2, "unsupported": 1},
        {"supported": 2, "unsupported": 1},
        {"supported": 2, "unsupported": 1},
        {"unsupported": 2, "supported": 1},
    ]
    kappa = _fleiss_kappa(item_votes, n_raters=3)
    # κ should be negative (sub-chance) given the marginal distribution
    assert kappa < 0.0, f"expected sub-chance κ, got {kappa:.3f}"
    # And the interpretation bucket should reflect that
    assert _kappa_interpretation(kappa) == "below-chance"


def test_fleiss_kappa_zero_items_returns_zero() -> None:
    """No items → κ undefined; convention returns 0.0."""

    assert _fleiss_kappa([], n_raters=3) == 0.0


def test_kappa_interpretation_bins() -> None:
    """Spec D3 Landis & Koch cutoffs."""

    assert _kappa_interpretation(-0.1) == "below-chance"
    assert _kappa_interpretation(0.10) == "poor"
    assert _kappa_interpretation(0.30) == "fair"
    assert _kappa_interpretation(0.50) == "moderate"
    assert _kappa_interpretation(0.70) == "substantial"
    assert _kappa_interpretation(0.85) == "almost-perfect"
    assert _kappa_interpretation(0.20) == "fair"  # boundary


# ── _combine_votes tests (D11 majority + disputed) ───────────────────────────


def test_combine_votes_all_agree() -> None:
    """3 judges complete, all vote 'supported' on the same item → majority."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-c", "claude", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
    ]
    votes, kappa_basis = _combine_votes(judges)
    assert len(votes) == 1
    assert votes[0].majority_verdict == "supported"
    assert votes[0].disputed is False
    assert votes[0].n_voting_judges == 3
    assert kappa_basis == 1


def test_combine_votes_two_of_three_majority() -> None:
    """2/3 same verdict → majority, NOT disputed."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-c", "claude", "complete", [_v("alice_ch01", "entity", "precision", 0, "unsupported")]),
    ]
    votes, kappa_basis = _combine_votes(judges)
    assert len(votes) == 1
    assert votes[0].majority_verdict == "supported"
    assert votes[0].disputed is False
    assert kappa_basis == 1


def test_combine_votes_all_disagree_disputed() -> None:
    """3 different verdicts → no majority → disputed."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "unsupported")]),
        _jr("u-c", "claude", "complete", [_v("alice_ch01", "entity", "precision", 0, "covered")]),
    ]
    votes, kappa_basis = _combine_votes(judges)
    assert len(votes) == 1
    # 1/3 ≤ 3/2 → no majority
    assert votes[0].majority_verdict is None
    assert votes[0].disputed is True
    # All 3 voted, so item still contributes to kappa basis
    assert kappa_basis == 1


def test_combine_votes_unjudged_excluded_from_vote_count() -> None:
    """An 'unjudged' verdict from one judge means that judge didn't vote
    on that item → kappa_basis goes to 0 (item not voted by ALL completed
    judges)."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "unjudged")]),
        _jr("u-c", "claude", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
    ]
    votes, kappa_basis = _combine_votes(judges)
    assert len(votes) == 1
    assert votes[0].n_voting_judges == 2  # only A + C
    # 2 of 3 = majority threshold (3/2 = 1.5; 2 > 1.5)
    assert votes[0].majority_verdict == "supported"
    # Not all 3 judges voted → exclude from kappa basis (D11)
    assert kappa_basis == 0


def test_combine_votes_judge_failed_drops_from_voting() -> None:
    """A judge with status='failed' should contribute no verdicts. Remaining
    2 judges vote; kappa_basis counts items they BOTH voted on."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-c", "claude", "failed", verdicts=[], failure="LM Studio HTTP 500"),
    ]
    votes, kappa_basis = _combine_votes(judges)
    assert len(votes) == 1
    assert votes[0].n_voting_judges == 2
    assert votes[0].majority_verdict == "supported"
    # Only 2 complete judges; kappa_basis includes items where ALL completed
    # judges voted (here 2/2)
    assert kappa_basis == 1


# ── D11 ensemble acceptability tests ──────────────────────────────────────────


def test_assemble_report_acceptable_with_3_complete() -> None:
    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-c", "claude", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
    ]
    report = assemble_report(judges)
    assert report.ensemble_acceptable is True


def test_assemble_report_acceptable_with_2_complete_1_failed() -> None:
    """D11: ≥ 2 complete judges → ensemble still acceptable (no silent downgrade
    to 2-judge majority — we EXPLICITLY surface the failed judge in
    judge_status). The report's `ensemble_acceptable` returns True only when
    ≥ 2 are `complete`."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-c", "claude", "failed", failure="LM Studio HTTP 500"),
    ]
    report = assemble_report(judges)
    assert report.ensemble_acceptable is True
    assert report.judge_status["u-c"] == "failed"
    assert "LM Studio" in report.judge_failure_reasons["u-c"]


def test_assemble_report_not_acceptable_with_only_1_complete() -> None:
    """D11: < 2 complete judges → not acceptable. Ensemble run must be re-tried."""

    judges = [
        _jr("u-a", "gemma", "complete", [_v("alice_ch01", "entity", "precision", 0, "supported")]),
        _jr("u-b", "qwen", "failed", failure="OOM"),
        _jr("u-c", "claude", "failed", failure="cancelled"),
    ]
    report = assemble_report(judges)
    assert report.ensemble_acceptable is False


# ── D12 bias metric tests ────────────────────────────────────────────────────


def test_bias_strictness_gap_flagged_when_outlier() -> None:
    """One lenient judge accepts everything; other two are moderate. Lenient
    judge's strictness_gap should exceed 0.15 threshold and be flagged."""

    judges = [
        _jr(
            "u-a",
            "gemma",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(5)
            ]
            + [
                _v("alice_ch01", "entity", "precision", i + 100, "unsupported")
                for i in range(5)
            ],
        ),  # 50% strictness
        _jr(
            "u-b",
            "qwen",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(5)
            ]
            + [
                _v("alice_ch01", "entity", "precision", i + 100, "unsupported")
                for i in range(5)
            ],
        ),  # 50%
        _jr(
            "u-c",
            "claude",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(10)
            ],
        ),  # 100% (lenient outlier)
    ]
    bias = _compute_bias_metrics(judges)
    by_label = {b.judge_label: b for b in bias}
    # Median strictness ≈ 0.5; claude's gap = 1.0 - 0.5 = 0.5 > 0.15 → flagged
    assert "strictness_gap" in by_label["claude"].flagged_dimensions
    # gemma and qwen are at the median, gap ≈ 0
    assert "strictness_gap" not in by_label["gemma"].flagged_dimensions


def test_bias_language_flagged_when_judge_penalizes_one_language() -> None:
    """One judge accepts EN but rejects VN → language_bias > 0.15 flagged."""

    judges = [
        _jr(
            "u-a",
            "gemma",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(5)
            ]
            + [
                _v("tam_cam_vi", "entity", "precision", i, "unsupported")
                for i in range(5)
            ],
        ),  # EN-biased: 1.0 vs 0.0
        _jr(
            "u-b",
            "qwen",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(5)
            ]
            + [
                _v("tam_cam_vi", "entity", "precision", i, "supported")
                for i in range(5)
            ],
        ),  # no bias
        _jr(
            "u-c",
            "claude",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", i, "supported")
                for i in range(5)
            ]
            + [
                _v("tam_cam_vi", "entity", "precision", i, "supported")
                for i in range(5)
            ],
        ),
    ]
    bias = _compute_bias_metrics(judges)
    by_label = {b.judge_label: b for b in bias}
    assert by_label["gemma"].language_bias == pytest.approx(1.0)
    assert "language_bias" in by_label["gemma"].flagged_dimensions
    assert by_label["qwen"].language_bias == pytest.approx(0.0)
    assert "language_bias" not in by_label["qwen"].flagged_dimensions


def test_bias_rp_metric_no_flag_threshold() -> None:
    """rp_bias is informational only; D12 says no flag threshold."""

    judges = [
        _jr(
            "u-a",
            "gemma",
            "complete",
            verdicts=[
                _v("alice_ch01", "entity", "precision", 0, "supported"),
                _v("alice_ch01", "entity", "recall", 0, "uncovered"),
            ],
        ),  # precision=1.0, recall=0.0 → rp_bias = 1.0
    ]
    bias = _compute_bias_metrics(judges)
    assert bias[0].rp_bias == pytest.approx(1.0)
    # No threshold-based flag for rp_bias even with extreme value
    assert "rp_bias" not in bias[0].flagged_dimensions


# ── chapter_language tests ──────────────────────────────────────────────────


def test_chapter_language_known_fixtures() -> None:
    assert chapter_language("alice_ch01") == "en"
    assert chapter_language("journey_west_zh_ch01") == "zh"
    assert chapter_language("tam_cam_vi") == "vi"


def test_chapter_language_unknown_chapter() -> None:
    assert chapter_language("invented_chapter_xyz") == "unk"


# ── llm_judge._chapter_judgement_to_verdicts flattening ───────────────────
# Regression-lock for the GoldVerdict.idx vs gold_idx bug discovered in the
# 2026-05-28 ensemble live-smoke (60 min of LM Studio work wasted because
# the flatten function accessed `rv.idx` on GoldVerdict, which uses
# `gold_idx`). Per `feedback_test_input_fields_from_producer_schema` —
# the unit test must access the SAME attribute the producer (ItemVerdict /
# GoldVerdict) actually exposes, not the consumer's wishful name.


def test_chapter_judgement_to_verdicts_uses_gold_idx_on_recall() -> None:
    """The flattener must read GoldVerdict.gold_idx (not .idx) for recall
    verdicts. Bug regression: cycle 2026-05-28 ensemble run crashed with
    `'GoldVerdict' object has no attribute 'idx'` on every judge's first
    chapter, wasting ~60 min of LM Studio work."""

    from loreweave_eval.judge_ensemble import chapter_judgement_to_verdicts
    from loreweave_eval.llm_judge import (
        ItemVerdict,
        GoldVerdict,
        CategoryJudgement,
        ChapterJudgement,
    )

    judgement = ChapterJudgement(
        chapter="alice_ch01",
        entity=CategoryJudgement(
            category="entity",
            n_extracted=1,
            n_gold=1,
            precision_verdicts=[
                ItemVerdict(idx=0, verdict="supported", reason="ok")
            ],
            recall_verdicts=[
                GoldVerdict(
                    gold_idx=0,
                    found=True,
                    matched_actual_idx=0,
                    reason="captured",
                    judged=True,
                )
            ],
        ),
        relation=CategoryJudgement(
            category="relation", n_extracted=0, n_gold=0,
            precision_verdicts=[], recall_verdicts=[],
        ),
        event=CategoryJudgement(
            category="event", n_extracted=0, n_gold=0,
            precision_verdicts=[], recall_verdicts=[],
        ),
    )
    verdicts = chapter_judgement_to_verdicts(judgement)
    assert len(verdicts) == 2  # 1 precision + 1 recall
    precision = next(v for v in verdicts if v.kind == "precision")
    recall = next(v for v in verdicts if v.kind == "recall")
    assert precision.idx == 0
    assert precision.verdict == "supported"
    assert recall.idx == 0  # ← THIS line crashed pre-fix with AttributeError
    assert recall.verdict == "covered"


def test_chapter_judgement_to_verdicts_unjudged_gold_label() -> None:
    """Recall verdicts marked judged=False produce verdict label 'unjudged'."""

    from loreweave_eval.judge_ensemble import chapter_judgement_to_verdicts
    from loreweave_eval.llm_judge import (
        CategoryJudgement,
        ChapterJudgement,
        GoldVerdict,
    )

    judgement = ChapterJudgement(
        chapter="alice_ch01",
        entity=CategoryJudgement(
            category="entity", n_extracted=0, n_gold=1,
            precision_verdicts=[],
            recall_verdicts=[
                GoldVerdict(
                    gold_idx=0, found=False, matched_actual_idx=None,
                    reason="judge omitted", judged=False,
                )
            ],
        ),
        relation=CategoryJudgement(category="relation", n_extracted=0, n_gold=0, precision_verdicts=[], recall_verdicts=[]),
        event=CategoryJudgement(category="event", n_extracted=0, n_gold=0, precision_verdicts=[], recall_verdicts=[]),
    )
    verdicts = chapter_judgement_to_verdicts(judgement)
    assert len(verdicts) == 1
    assert verdicts[0].kind == "recall"
    assert verdicts[0].verdict == "unjudged"
    assert verdicts[0].idx == 0
