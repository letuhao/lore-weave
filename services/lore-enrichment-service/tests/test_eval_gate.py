"""C15 — the P2/P3 GATE. The load-bearing piece: the gate must ACTUALLY gate.

Asserts: below threshold → P2/P3 blocked (registry.select raises
InactiveStrategyError); at/above threshold + acceptable ensemble + critical
floors met → P2/P3 enabled. A false-green gate (always passes) is the worst
failure — these tests prove a low score does NOT unlock the higher tiers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.eval.gate import GATE_CRITICAL_FLOORS, gated_feature_flags
from app.eval.judge_usefulness import JudgeSpec
from app.eval.runner import run_eval
from app.eval.scorers import ScorableProposal
from app.eval.suite import load_suite
from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
)
from app.strategies.registry import (
    InactiveStrategyError,
    StrategyRegistry,
)


class _FabricationProbe(EnrichmentStrategy):
    """A test-only stand-in registered under the P2 'fabrication' key so the
    gate test can prove the registry REFUSES to select it while gated OFF. This
    is NOT a real C16 strategy — it has no enrichment logic, just the technique
    identity needed to exercise the registry's flag gating."""

    technique = Technique.FABRICATION

    def estimate_cost(self, gap_batch):
        return CostEstimate(technique=self.technique, gap_count=len(gap_batch),
                            units=0.0, cost=0.0)

    async def run(self, gap_batch, context: StrategyContext):
        raise NotImplementedError("probe — never run (C16 is out of scope)")

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE_TOML = REPO_ROOT / "eval" / "enrichment-eval-suite.toml"


def _suite():
    return load_suite(SUITE_TOML)


def _good_prop(name="蓬萊"):
    return ScorableProposal(
        name=name, entity_kind="location",
        dimensions={
            "历史": "东海仙山，群仙修真之所。", "地理": "孤悬东海，云雾缭绕。",
            "文化": "崇尚清修无为之道。", "features": "琼楼玉宇，瑶池仙草。",
            "inhabitants": "得道散仙与上古真人。",
        },
        origin="enrichment", technique="retrieval", confidence=0.30,
        review_status="proposed", pending_validation=True,
        source_refs=[{"corpus_id": "c1", "chunk_id": "k1", "score": 0.8}],
        provenance={"technique": "retrieval", "model_ref": "ref-1"},
        canon_verify={"flags": []},
    )


def _bad_prop(name="坏地点"):
    # H0 leak (canon confidence) + anachronism + no grounding → low everything.
    return ScorableProposal(
        name=name, entity_kind="location",
        dimensions={
            "历史": "岛上仙人开汽车，用电脑。",  # anachronism
            "地理": "", "文化": "",  # missing required
        },
        origin="glossary",  # H0 LEAK → provenance 0
        technique="fabrication", confidence=1.0, review_status="proposed",
        pending_validation=False, source_refs=[], provenance={},
        canon_verify={},
    )


def _judge_all(verdict):
    def judge_fn_for(judge):
        async def _fn(system, user):
            return f'{{"verdict":"{verdict}"}}'
        return _fn
    return judge_fn_for


# ── gate decision: pure ─────────────────────────────────────────────────────────

def test_gate_blocks_below_threshold():
    suite = _suite()
    judges = [JudgeSpec("a", "r1"), JudgeSpec("b", "r2")]
    outcome = asyncio.run(run_eval(
        [_bad_prop()], suite, judges=judges, judge_fn_for=_judge_all("poor"),
    ))
    assert not outcome.scorecard.passed
    assert outcome.decision.blocks_p2_p3
    assert outcome.decision.reasons  # has explicit block reasons


def test_gate_passes_good_output_with_acceptable_ensemble():
    suite = _suite()
    judges = [JudgeSpec("a", "r1"), JudgeSpec("b", "r2"), JudgeSpec("c", "r3")]
    outcome = asyncio.run(run_eval(
        [_good_prop("蓬萊"), _good_prop("玉虛宮")], suite,
        judges=judges, judge_fn_for=_judge_all("excellent"),
    ))
    assert outcome.scorecard.passed
    assert not outcome.decision.blocks_p2_p3


def test_gate_blocks_when_ensemble_not_acceptable_even_if_deterministic_high():
    # Deterministic sub-scores are perfect, but no live judges → usefulness 0 +
    # ensemble not acceptable → BLOCK (can't trust usefulness to unlock cost).
    suite = _suite()
    outcome = asyncio.run(run_eval([_good_prop()], suite))  # no judges
    assert not outcome.scorecard.passed
    assert any("ensemble" in r for r in outcome.decision.reasons)


def test_gate_blocks_on_provenance_floor_breach():
    # One proposal is an H0 leak (provenance 0) — even mixed with good ones the
    # mean provenance drops below the critical floor → BLOCK regardless of a
    # high composite. H0 can never be averaged away.
    suite = _suite()
    judges = [JudgeSpec("a", "r1"), JudgeSpec("b", "r2")]
    props = [_good_prop("a"), _good_prop("b"), _bad_prop("leak")]
    outcome = asyncio.run(run_eval(
        props, suite, judges=judges, judge_fn_for=_judge_all("excellent"),
    ))
    assert not outcome.scorecard.passed
    assert any("provenance" in r for r in outcome.decision.reasons)


def test_gate_blocks_on_baseline_regression():
    suite = _suite()
    judges = [JudgeSpec("a", "r1"), JudgeSpec("b", "r2")]
    # Baseline expects high usefulness; current run scores 'fair' (0.5) → -50 reg.
    baseline = {"version": "enrichment-v1",
                "subscores": {"schema": 100.0, "canon": 100.0, "anachronism": 100.0,
                              "provenance": 100.0, "usefulness": 100.0},
                "composite": 100.0}
    outcome = asyncio.run(run_eval(
        [_good_prop()], suite, baseline=baseline,
        judges=judges, judge_fn_for=_judge_all("fair"),
    ))
    assert outcome.baseline_diff is not None and outcome.baseline_diff.regressed
    assert not outcome.scorecard.passed


# ── gate ACTUALLY gates the C8 registry (the real wiring) ────────────────────────

def test_gated_flags_block_fabrication_when_gate_fails():
    suite = _suite()
    outcome = asyncio.run(run_eval([_bad_prop()], suite))  # fails
    flags = gated_feature_flags(
        outcome.decision,
        base_overrides={Technique.FABRICATION: True, Technique.RECOOK: True},
    )
    # Even though the override TRIED to turn P2/P3 on, the failed gate forces OFF.
    assert not flags.is_active(Technique.FABRICATION)
    assert not flags.is_active(Technique.RECOOK)
    # P1 untouched.
    assert flags.is_active(Technique.TEMPLATE)
    assert flags.is_active(Technique.RETRIEVAL)

    # And the REAL registry built from these flags refuses to select P2.
    reg = StrategyRegistry(flags=flags)
    reg.register(_FabricationProbe())
    with pytest.raises(InactiveStrategyError):
        reg.select(Technique.FABRICATION)


def test_gated_flags_enable_fabrication_when_gate_passes_and_override_on():
    suite = _suite()
    judges = [JudgeSpec("a", "r1"), JudgeSpec("b", "r2"), JudgeSpec("c", "r3")]
    outcome = asyncio.run(run_eval(
        [_good_prop("a"), _good_prop("b")], suite,
        judges=judges, judge_fn_for=_judge_all("excellent"),
    ))
    assert outcome.scorecard.passed
    flags = gated_feature_flags(
        outcome.decision,
        base_overrides={Technique.FABRICATION: True},
    )
    # Gate passed → the override is honored → P2 active.
    assert flags.is_active(Technique.FABRICATION)
    # RECOOK had no override → still default OFF (passing the gate UNLOCKS the
    # ability to turn it on; it does not force every higher tier on).
    assert not flags.is_active(Technique.RECOOK)


def test_critical_floors_pinned():
    # Lock the gate-critical floors so a future relaxation is a conscious change.
    assert GATE_CRITICAL_FLOORS["provenance"] == 90.0
    assert GATE_CRITICAL_FLOORS["anachronism"] == 75.0
