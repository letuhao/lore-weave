"""Unit tests for the disjoint-judge metric of record (cycle 74e Phase A).

Locks: per-chapter P/R, macro harmonic F1, the disjoint filter (exclude the
extractor + filter models), and a DETERMINISTIC bootstrap CI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.quality.compute_ensemble_macros import (
    _DEFAULT_EXTRACTOR_UUID,
    _DEFAULT_FILTER_UUID,
    _macro_f1,
    _per_chapter_pr,
    disjoint_median_with_ci,
    load_judge,
)


def _verdicts(chapter: str, prec: list[str], rec: list[str]) -> list[dict]:
    out = []
    for i, v in enumerate(prec):
        out.append({"chapter": chapter, "category": "entity", "kind": "precision",
                    "idx": i, "verdict": v})
    for i, v in enumerate(rec):
        out.append({"chapter": chapter, "category": "entity", "kind": "recall",
                    "idx": i, "verdict": v})
    return out


def _write_judge(d: Path, label: str, uuid: str, verdicts: list[dict]) -> Path:
    p = d / f"judge_verdicts_{label}.json"
    p.write_text(json.dumps({
        "judge_uuid": uuid, "judge_label": label, "judge_status": "complete",
        "verdicts": verdicts,
    }), encoding="utf-8")
    return p


def test_per_chapter_pr_credits_and_skips_unjudged():
    v = _verdicts("ch1", prec=["supported", "partial", "unsupported", "unjudged"],
                  rec=["covered", "supported", "uncovered", "unjudged"])
    chap_p, chap_r = _per_chapter_pr(v)
    # precision: (1.0 + 0.5 + 0.0) / 3 judged  (unjudged excluded)
    assert chap_p["ch1"] == pytest.approx((1.0 + 0.5) / 3)
    # recall: 2 found (covered, supported) / 3 judged
    assert chap_r["ch1"] == pytest.approx(2 / 3)


def test_macro_f1_is_harmonic_of_macro_p_and_r():
    chap_p = {"a": 1.0, "b": 0.5}   # P = 0.75
    chap_r = {"a": 1.0, "b": 1.0}   # R = 1.0
    assert _macro_f1(chap_p, chap_r) == pytest.approx(2 * 0.75 * 1.0 / 1.75)


def test_disjoint_filter_excludes_extractor_and_filter(tmp_path):
    v = _verdicts("ch1", prec=["supported"], rec=["covered"])
    _write_judge(tmp_path, "gemma", "019dc3df-0000", v)
    _write_judge(tmp_path, "qwen30b", _DEFAULT_EXTRACTOR_UUID, v)
    _write_judge(tmp_path, "claude", _DEFAULT_FILTER_UUID, v)

    judges = [load_judge(f) for f in sorted(tmp_path.glob("judge_verdicts_*.json"))]
    excluded = {_DEFAULT_EXTRACTOR_UUID, _DEFAULT_FILTER_UUID}
    disjoint = [j for j in judges if j["uuid"] not in excluded]
    assert [j["label"] for j in disjoint] == ["gemma"]
    # only 1 disjoint judge → no robust CI
    res = disjoint_median_with_ci(disjoint, n_boot=200)
    assert res["n_judges"] == 1
    assert res["ci_low"] is None


def test_disjoint_median_and_ci_are_deterministic(tmp_path):
    # Two independent judges across 4 chapters with differing per-chapter scores.
    for label, uuid in (("gemma", "019dc3df-0000"), ("phi4", "019dc3ab-0000")):
        verdicts: list[dict] = []
        for ch, (p, r) in {
            "c1": (["supported"], ["covered"]),
            "c2": (["partial"], ["uncovered"]),
            "c3": (["supported", "unsupported"], ["covered", "covered"]),
            "c4": (["supported"], ["covered"]),
        }.items():
            verdicts += _verdicts(ch, p, r)
        _write_judge(tmp_path, label, uuid, verdicts)

    judges = [load_judge(f) for f in sorted(tmp_path.glob("judge_verdicts_*.json"))]
    r1 = disjoint_median_with_ci(judges, n_boot=500)
    r2 = disjoint_median_with_ci(judges, n_boot=500)
    assert r1 == r2  # fixed seed → reproducible
    assert r1["n_judges"] == 2
    assert r1["ci_low"] is not None and r1["ci_high"] is not None
    assert r1["ci_low"] <= r1["median_f1"] <= r1["ci_high"]
    assert r1["n_common_chapters"] == 4
