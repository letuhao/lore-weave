"""Benchmark for the auto-reasoning policy — a labeled matrix of realistic
co-write scenarios → expected effort tier. Validates (a) the rule-based scorer
makes sensible per-scenario decisions, (b) the distribution is non-degenerate
(not all-high / all-none), and (c) regression-locks the weights. Deterministic
(no LLM). The deeper PROSE-quality A/B (reasoning on vs off, LLM-judged) is the
V1 quality-eval — out of scope here.

Run with `-s` to print the benchmark report.
"""

from __future__ import annotations

from collections import Counter

from app.reasoning import ReasoningSignals, score_effort

# (label, signals, expected_effort) — `expected` is the intended behaviour a
# human author would want; a mismatch means the weights OR the label is wrong and
# must be reconciled (not silently drifted).
CASES: list[tuple[str, ReasoningSignals, str]] = [
    ("continue a simple paragraph",            ReasoningSignals(operation="continue"), "none"),
    ("rewrite one line",                        ReasoningSignals(operation="rewrite_line"), "none"),
    ("brief description",                        ReasoningSignals(operation="describe"), "none"),
    ("expand a phrase inline",                  ReasoningSignals(operation="expand_inline"), "none"),
    ("plain new scene, no canon",               ReasoningSignals(operation="draft_scene"), "medium"),
    ("scene, one canon rule",                   ReasoningSignals(operation="draft_scene", n_canon_rules=1), "medium"),
    ("scene, light canon (2 rules)",            ReasoningSignals(operation="draft_scene", n_canon_rules=2), "medium"),
    ("scene, many present entities",            ReasoningSignals(operation="draft_scene", n_present_entities=5), "medium"),
    ("plan a story beat",                       ReasoningSignals(operation="plan_beat"), "medium"),
    ("continue but author asks to foreshadow",  ReasoningSignals(operation="continue", guide="carefully foreshadow the betrayal"), "low"),
    ("canon-heavy scene (6 rules)",             ReasoningSignals(operation="draft_scene", n_canon_rules=6), "high"),
    ("reveal-gate scene (+3 rules)",            ReasoningSignals(operation="draft_scene", n_canon_rules=3, has_reveal_gate=True), "high"),
    ("high-tension climax (+4 entities)",       ReasoningSignals(operation="draft_scene", tension=90, n_present_entities=4), "high"),
    ("weave canon, many rules",                 ReasoningSignals(operation="weave_canon", n_canon_rules=6), "high"),
    ("everything at once",                      ReasoningSignals(operation="draft_scene", n_canon_rules=8, has_reveal_gate=True, n_present_entities=6, tension=95, guide="reconcile the timeline"), "high"),
]


def test_reasoning_policy_benchmark():
    results = [(label, expected, score_effort(sig)) for label, sig, expected in CASES]
    mismatches = [(l, e, g) for (l, e, g) in results if e != g]
    dist = Counter(g for (_, _, g) in results)
    accuracy = (len(results) - len(mismatches)) / len(results)

    print("\n── auto-reasoning policy benchmark ──")
    for label, expected, got in results:
        flag = "ok " if expected == got else "MISS"
        print(f"  [{flag}] {got:<6} (want {expected:<6}) · {label}")
    print(f"  accuracy: {accuracy:.0%}  ({len(results) - len(mismatches)}/{len(results)})")
    print(f"  effort distribution: {dict(dist)}")

    # Non-degenerate: the policy must produce a real spread, not collapse to one
    # tier (which would mean the scorer adds no value).
    assert len(dist) >= 3, f"degenerate distribution {dict(dist)} — scorer adds no signal"
    assert dist["none"] >= 1 and dist["high"] >= 1, "policy never reaches the extremes"
    # Regression lock: the labeled intent must hold.
    assert not mismatches, f"policy drifted from intended labels: {mismatches}"
