"""WS-5.16/5.17/5.18 (spec 08 Gate-4) — the coaching-scorer EVAL HARNESS.

⚠️ SD-7 / X-4 BOUNDARY (the single sharpest risk in P5): this module builds the eval
MECHANISM — it can NEVER clear the numeric gate. The gate needs N≥50 transcripts × ≥2
independent HUMAN raters × QWK vs consensus. **No code produces human annotations.** A build
agent that commits a QWK point number from a self-run repeats the retracted-93.75% failure.
So:
- `quadratic_weighted_kappa` / `judge_vs_consensus_qwk` COMPUTE agreement when given labels;
- `GateStatus.evaluate` returns `cleared=False` with reason `no_human_labels` whenever the
  human-rater set is absent — which is ALWAYS, in a code run;
- the scorer therefore stays `quarantine`-tier (shown, never trended) until a HUMAN-rating
  milestone supplies labels and a person certifies the number. This module must not be edited
  to hardcode a passing verdict.

WS-5.16: report a RANGE over ≥3 runs, never a point estimate.
WS-5.17: the ceiling is human–human agreement; the LLM judge is compared to the human
CONSENSUS, never to a single annotator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


def quadratic_weighted_kappa(rater_a: list[int], rater_b: list[int], *, min_rating: int = 1, max_rating: int = 5) -> float:
    """Cohen's kappa with quadratic weights over an ordinal scale [min_rating, max_rating].
    +1 = perfect agreement, 0 = chance, <0 = worse than chance. Pure; raises on mismatch."""
    if len(rater_a) != len(rater_b):
        raise ValueError("rater vectors must be the same length")
    if not rater_a:
        raise ValueError("cannot compute QWK on empty ratings")
    n_ratings = max_rating - min_rating + 1
    idx = lambda r: r - min_rating  # noqa: E731

    # observed confusion matrix
    O = [[0] * n_ratings for _ in range(n_ratings)]
    for a, b in zip(rater_a, rater_b):
        O[idx(a)][idx(b)] += 1

    # histograms → expected matrix (outer product), quadratic weights
    hist_a = [sum(O[i]) for i in range(n_ratings)]
    hist_b = [sum(O[i][j] for i in range(n_ratings)) for j in range(n_ratings)]
    total = len(rater_a)
    denom_w = (n_ratings - 1) ** 2 or 1

    num = 0.0
    den = 0.0
    for i in range(n_ratings):
        for j in range(n_ratings):
            w = ((i - j) ** 2) / denom_w
            e = hist_a[i] * hist_b[j] / total
            num += w * O[i][j]
            den += w * e
    if den == 0:
        return 1.0  # no disagreement possible (all one rating) → perfect
    return 1.0 - num / den


def judge_vs_consensus_qwk(judge: list[int], human_consensus: list[int], **kw) -> float:
    """WS-5.17 — the LLM judge is scored against the HUMAN CONSENSUS, not one annotator."""
    return quadratic_weighted_kappa(judge, human_consensus, **kw)


def range_over_runs(run_qwks: list[float]) -> dict:
    """WS-5.16 — never a point estimate. Returns {min, max, mean, runs}; a single run is
    explicitly flagged so a caller can't quote it as 'the' number."""
    if not run_qwks:
        return {"min": None, "max": None, "mean": None, "runs": 0, "single_run": False}
    return {
        "min": min(run_qwks), "max": max(run_qwks), "mean": mean(run_qwks),
        "runs": len(run_qwks), "single_run": len(run_qwks) < 3,
    }


@dataclass(frozen=True)
class GateStatus:
    """The Gate-4 verdict. In a CODE RUN this is ALWAYS cleared=False — clearing needs a
    human-rating milestone (SD-7). `reason` names why it isn't cleared."""

    cleared: bool
    reason: str
    detail: dict = field(default_factory=dict)


# The minimum sample the gate requires (WS-5.18). Present so the harness can REPORT how far
# short a run falls — not so a code run can meet it.
MIN_TRANSCRIPTS = 50
MIN_HUMAN_RATERS = 2


def evaluate_gate(
    *,
    n_transcripts: int,
    n_human_raters: int,
    threshold_qwk: float,
    run_qwks: list[float] | None = None,
) -> GateStatus:
    """Decide whether the numeric gate clears. FAIL-CLOSED on missing human data: a code run
    has n_human_raters == 0, so this returns cleared=False (reason=no_human_labels) every time.
    Even WITH raters, a self-run cannot legitimately call this — it exists so the human-rating
    milestone has a single, auditable decision point."""
    if n_human_raters < MIN_HUMAN_RATERS:
        return GateStatus(False, "no_human_labels", {
            "have_raters": n_human_raters, "need_raters": MIN_HUMAN_RATERS,
            "note": "a code run cannot produce human annotations (SD-7); scorer stays quarantine-tier",
        })
    if n_transcripts < MIN_TRANSCRIPTS:
        return GateStatus(False, "insufficient_sample", {
            "have": n_transcripts, "need": MIN_TRANSCRIPTS,
        })
    rng = range_over_runs(run_qwks or [])
    if rng["runs"] < 3:
        return GateStatus(False, "need_range_over_3_runs", rng)
    # The floor of the RANGE must clear the threshold (WS-5.16 — not the mean, not a point).
    if rng["min"] < threshold_qwk:
        return GateStatus(False, "below_threshold", {**rng, "threshold": threshold_qwk})
    return GateStatus(True, "cleared", {**rng, "threshold": threshold_qwk,
                                        "n_transcripts": n_transcripts, "n_human_raters": n_human_raters})


# ── WS-5.19 (P5-D8/D11) — dismiss-rate is an OPERATIONAL self-disarm signal, NOT validity ──
# Dismiss-rate does NOT measure whether a score is TRUE — optimizing for "not dismissed"
# selects for flattery (P5-D8). It is only a circuit-breaker: if the user dismisses most
# coaching over a meaningful sample, stop coaching them (self-disarm) until they re-opt-in.
# Validity is precision against a hand-labeled set, split into 3 questions (accurate? / useful?
# / dismiss) — never conflated into one thumbs signal.
SELF_DISARM_MIN_N = 5
SELF_DISARM_RATE = 0.6


def should_self_disarm(dismiss_count: int, total: int) -> bool:
    """True when the user dismissed > 60% of coaching over >= 5 items — stop coaching, don't
    tune the content to avoid dismissal. Under the sample floor, never disarm (too little data)."""
    if total < SELF_DISARM_MIN_N:
        return False
    return (dismiss_count / total) > SELF_DISARM_RATE
