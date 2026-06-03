"""C15 — deterministic sub-score scorers + weighted aggregation + baseline-diff.

These tests pin the schema/canon/anachronism/provenance scorers and the suite
aggregation on FIXED inputs so the eval is reproducible (never a false-green).
The judge-ensemble usefulness sub-score is tested separately (test_eval_judge).
"""

from __future__ import annotations

from pathlib import Path

from app.eval import scorers
from app.eval.scorers import ScorableProposal
from app.eval.suite import composite_score, diff_against_baseline, load_suite

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE_TOML = REPO_ROOT / "eval" / "enrichment-eval-suite.toml"


def _good_proposal(**over) -> ScorableProposal:
    base = dict(
        name="蓬萊",
        entity_kind="location",
        dimensions={
            "历史": "蓬萊乃东海仙山，相传为群仙修真之所，自上古有之。",
            "地理": "孤悬东海之上，云雾缭绕，凡舟不能至。",
            "文化": "岛上仙家以琼浆玉露为食，崇尚清修无为之道。",
            "features": "有琼楼玉宇，瑶池仙草，灵禽异兽。",
            "inhabitants": "多为得道散仙与上古真人。",
        },
        origin="enrichment",
        technique="retrieval",
        confidence=0.30,
        review_status="proposed",
        pending_validation=True,
        source_refs=[{"corpus_id": "c1", "chunk_id": "k1", "score": 0.8}],
        provenance={"technique": "retrieval", "model_ref": "ref-123",
                    "canon_verify": {"flags": []}},
        canon_verify={"flags": []},
    )
    base.update(over)
    return ScorableProposal(**base)


# ── schema ──────────────────────────────────────────────────────────────────────

def test_schema_full_proposal_scores_high():
    s, issues = scorers.score_schema(_good_proposal())
    assert s == 100.0
    assert issues == []


def test_schema_missing_required_dimension_loses_slice():
    p = _good_proposal(dimensions={
        "历史": "有内容", "地理": "有内容",  # 文化 missing
        "features": "有", "inhabitants": "有",
    })
    s, issues = scorers.score_schema(p)
    # lost the 20pt 文化 slice → 80.
    assert s == 80.0
    assert any("文化" in i for i in issues)


def test_schema_english_leaked_required_dim_partial_credit():
    p = _good_proposal(dimensions={
        "历史": "this is entirely english prose with no chinese content here",
        "地理": "孤悬东海之上。", "文化": "崇尚清修。",
        "features": "瑶池。", "inhabitants": "散仙。",
    })
    s, issues = scorers.score_schema(p)
    assert any("Chinese-faithful" in i for i in issues)
    assert s < 100.0


# ── canon ─────────────────────────────────────────────────────────────────────

def test_canon_clean_no_flags():
    s, issues = scorers.score_canon(_good_proposal())
    assert s == 100.0


def test_canon_contradiction_lowers_score():
    p = _good_proposal(canon_verify={
        "flags": [{"kind": "CONTRADICTION", "severity": "HIGH", "evidence": "x"}]
    })
    s, issues = scorers.score_canon(p)
    assert s == 60.0
    assert any("contradiction" in i for i in issues)


def test_canon_degraded_never_auto_passes():
    p = _good_proposal(canon_verify={"flags": [], "verify_degraded": True})
    s, _ = scorers.score_canon(p)
    assert s <= 70.0  # degraded is capped — never a green 100


def test_canon_no_annotation_capped():
    p = _good_proposal(canon_verify={})
    s, _ = scorers.score_canon(p)
    assert s == 50.0


# ── anachronism ──────────────────────────────────────────────────────────────

def test_anachronism_clean_full_score():
    s, issues = scorers.score_anachronism(_good_proposal())
    assert s == 100.0
    assert issues == []


def test_anachronism_modern_term_penalized():
    p = _good_proposal(dimensions={
        "历史": "岛上仙人乘汽车出行，并用电脑记录。",  # 汽车 + 电脑
        "地理": "东海之上。", "文化": "清修。",
        "features": "瑶池。", "inhabitants": "散仙。",
    })
    s, issues = scorers.score_anachronism(p)
    assert s == 50.0  # two distinct markers → 100 - 25*2
    assert len(issues) >= 2


def test_anachronism_era_appropriate_thunder_not_flagged():
    # C12 lesson: bare 电 false-positived on 雷电/电光 — must NOT flag those.
    p = _good_proposal(dimensions={
        "历史": "雷电交加，电光闪烁，仙人显神通。",
        "地理": "东海。", "文化": "清修。", "features": "瑶池。", "inhabitants": "散仙。",
    })
    s, _ = scorers.score_anachronism(p)
    assert s == 100.0


# ── provenance (H0) ────────────────────────────────────────────────────────────

def test_provenance_full_h0_high():
    s, issues = scorers.score_provenance(_good_proposal())
    assert s == 100.0
    assert issues == []


def test_provenance_canon_origin_is_h0_leak_zero():
    p = _good_proposal(origin="glossary")
    s, issues = scorers.score_provenance(p)
    assert s == 0.0
    assert any("H0 LEAK" in i for i in issues)


def test_provenance_canon_confidence_is_h0_leak_zero():
    p = _good_proposal(confidence=1.0)
    s, issues = scorers.score_provenance(p)
    assert s == 0.0
    assert any("H0 LEAK" in i for i in issues)


def test_provenance_no_grounding_refs_lowers():
    p = _good_proposal(source_refs=[])
    s, issues = scorers.score_provenance(p)
    assert s == 75.0  # lost the 25pt grounding slice
    assert any("grounding" in i for i in issues)


# ── aggregation + baseline-diff ─────────────────────────────────────────────────

def test_composite_weighted_sum():
    suite = load_suite(SUITE_TOML)
    subs = {"schema": 100.0, "canon": 100.0, "anachronism": 100.0,
            "provenance": 100.0, "usefulness": 100.0}
    assert composite_score(subs, suite.weights) == 100.0


def test_composite_partial():
    suite = load_suite(SUITE_TOML)
    subs = {"schema": 80.0, "canon": 60.0, "anachronism": 100.0,
            "provenance": 100.0, "usefulness": 0.0}
    # 0.2*80 + 0.15*60 + 0.15*100 + 0.25*100 + 0.25*0 = 16+9+15+25+0 = 65
    assert composite_score(subs, suite.weights) == 65.0


def test_baseline_diff_detects_regression():
    suite = load_suite(SUITE_TOML)
    baseline = {"version": "enrichment-v1",
                "subscores": {"schema": 100.0, "canon": 100.0, "anachronism": 100.0,
                              "provenance": 100.0, "usefulness": 80.0},
                "composite": 95.0}
    subs = {"schema": 100.0, "canon": 80.0, "anachronism": 100.0,
            "provenance": 100.0, "usefulness": 60.0}  # usefulness -20, canon -20
    comp = composite_score(subs, suite.weights)
    diff = diff_against_baseline(subs, comp, baseline, suite.regression)
    assert diff.regressed
    assert any("usefulness" in r for r in diff.regressions)


def test_baseline_diff_no_regression_on_improvement():
    suite = load_suite(SUITE_TOML)
    baseline = {"version": "enrichment-v1",
                "subscores": {"schema": 80.0, "canon": 80.0, "anachronism": 80.0,
                              "provenance": 80.0, "usefulness": 50.0},
                "composite": 72.0}
    subs = {"schema": 100.0, "canon": 100.0, "anachronism": 100.0,
            "provenance": 100.0, "usefulness": 80.0}
    comp = composite_score(subs, suite.weights)
    diff = diff_against_baseline(subs, comp, baseline, suite.regression)
    assert not diff.regressed
