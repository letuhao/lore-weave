"""The P2/P3 enablement GATE (RAID C15) — cost-discipline enforcement.

This gate AUTO-BLOCKS the higher-cost techniques (C16 fabrication = P2, C17
re-cook = P3) until an enrichment eval clears threshold. It is LOAD-BEARING:
a false-green gate that always passes defeats the whole cycle, so the gate
decision is computed conservatively and ACTUALLY gates the C8 feature-flags.

Two surfaces:

  1. :func:`gate_decision` — pure: given a scorecard + suite, decide whether the
     enriched output is good enough to unlock P2/P3. PASS requires ALL of:
       * ``composite >= gate.min_composite``;
       * NO baseline regression (when a baseline is supplied);
       * the judge ensemble was ACCEPTABLE (≥ 2 judges voted) — a single-judge
         (or no-judge) usefulness score is not trustworthy enough to unlock cost;
       * each gate-critical sub-score (provenance, anachronism) meets its floor
         (H0/era-fidelity must hold regardless of a high mean composite — a
         provenance leak can never be averaged away into a pass).

  2. :func:`gated_feature_flags` — applies the decision to the C8 flags: P2/P3
     are forced OFF unless the gate PASSED. This is the switch the registry
     consults; with the gate blocking, ``registry.select('fabrication')`` raises
     ``InactiveStrategyError`` exactly as before the gate existed.

The gate reads the LATEST persisted eval run for the current suite_version (via
the runner/repo) so C16/C17 activation is driven by real, persisted data — not
an advisory print.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.eval.suite import BaselineDiff, EvalSuite, Scorecard
from app.strategies.base import Technique, Tier
from app.strategies.feature_flags import FeatureFlags, load_feature_flags

__all__ = [
    "GateDecision",
    "gate_decision",
    "gated_feature_flags",
    "GATE_CRITICAL_FLOORS",
]

#: Hard floors a gate-critical sub-score must meet REGARDLESS of the composite.
#: H0 (provenance) + era-fidelity (anachronism) can never be averaged away by a
#: high schema/usefulness score — a provenance leak or an anachronism is a
#: categorical defect that must block the higher-cost tier on its own.
GATE_CRITICAL_FLOORS: dict[str, float] = {
    "provenance": 90.0,    # H0: enriched markers must be near-perfect
    "anachronism": 75.0,   # source-faithful 封神 frame: at most one slip tolerated
}


@dataclass(frozen=True)
class GateDecision:
    """The gate verdict + the reasons (for audit + the scorecard)."""

    passed: bool
    composite: float
    min_composite: float
    reasons: list[str]

    @property
    def blocks_p2_p3(self) -> bool:
        return not self.passed


def gate_decision(
    scorecard: Scorecard,
    suite: EvalSuite,
    baseline_diff: BaselineDiff | None = None,
) -> GateDecision:
    """Decide PASS/FAIL. Conservative: ANY failing condition blocks P2/P3.

    Note the scorecard's own ``composite`` is recomputed-independent here — we
    re-check it against ``suite.gate.min_composite`` so a scorecard with a
    stale/forged ``passed`` flag cannot smuggle a pass (the gate is the
    authority, not the scorecard's self-reported field).
    """
    reasons: list[str] = []
    min_composite = float(suite.gate.get("min_composite", 0.0))

    if scorecard.composite < min_composite:
        reasons.append(
            f"composite {scorecard.composite} < gate min {min_composite}"
        )

    if not scorecard.judge_ensemble_acceptable:
        reasons.append(
            "judge ensemble not acceptable — needs ≥2 judges from ≥2 DISTINCT "
            "model families AND inter-rater κ at/above the floor (C2/LE-056); "
            "usefulness untrustworthy, P2/P3 stay blocked"
        )

    for sub, floor in GATE_CRITICAL_FLOORS.items():
        val = float(scorecard.subscores.get(sub, 0.0))
        if val < floor:
            reasons.append(f"gate-critical sub-score {sub}={val} < floor {floor}")

    if baseline_diff is not None and baseline_diff.regressed:
        for r in baseline_diff.regressions:
            reasons.append(f"baseline regression: {r}")

    passed = not reasons
    return GateDecision(
        passed=passed,
        composite=scorecard.composite,
        min_composite=min_composite,
        reasons=reasons,
    )


def gated_feature_flags(
    decision: GateDecision,
    *,
    base_overrides: Mapping[Technique, bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> FeatureFlags:
    """Build the C8 feature-flags WITH the gate applied.

    When the gate did NOT pass, every P2/P3 technique is forced OFF (overriding
    any env/override that tried to turn it on) — this is the actual gating: the
    registry built from these flags will raise ``InactiveStrategyError`` for
    fabrication/recook. When the gate PASSED, the flags resolve normally (P2/P3
    follow their env/override), so a passing eval is what UNLOCKS the tier.

    P1 (template/retrieval) is never touched by the gate — it ships active and
    is what produces the proposals the gate scores in the first place.
    """
    overrides: dict[Technique, bool] = dict(base_overrides or {})
    if not decision.passed:
        # Force every non-P1 technique OFF — the gate blocks the higher tiers.
        for t in Technique:
            if t.tier is not Tier.P1:
                overrides[t] = False
    return load_feature_flags(overrides=overrides, env=env)
