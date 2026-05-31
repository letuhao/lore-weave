"""Multi-judge ensemble runner for the eval framework overhaul cycle (2026-05-27).

Per spec D3 + D4 + D11 + D12:
- Sequential JIT-loaded judges (3 local LM Studio models, no cloud).
- Per-judge verdict files persisted to `judge_verdicts_<judge_short>.json` so
  individual judges can be inspected without re-running.
- Fleiss kappa for inter-rater reliability, computed over items where ALL 3
  judges produced a verdict (D11: never silent-downgrade to 2-judge majority).
- Per-item majority vote with `disputed` marker when no majority.
- D12 bias metrics: strictness_gap, language_bias (en/vi/zh), rp_bias.
- D11 ensemble failure handling: judge_status complete/incomplete/failed;
  acceptance gate requires ≥ 2 judges `complete`.

This module is intentionally DECOUPLED from `llm_judge.py`'s call shape: the
ensemble runner takes a per-judge async callable that returns a
`ChapterJudgement` per chapter. The integration layer in `llm_judge.py` (added
in the next sub-cycle) wires this to actual `judge_chapter()` calls; for
unit-testability we keep this module's interface as a pure callable.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Sequence

logger = logging.getLogger(__name__)


# ── Types ────────────────────────────────────────────────────────────────────

JudgeStatus = Literal["complete", "incomplete", "failed"]
VerdictLabel = Literal["supported", "unsupported", "covered", "uncovered", "unjudged"]
Category = Literal["entity", "relation", "event"]
VerdictKind = Literal["precision", "recall"]


# Canonical chapter → language mapping for D12 language_bias. Pulled from
# fixture filename conventions in tests/fixtures/golden_chapters/.
_CHAPTER_LANG: dict[str, str] = {
    "alice_ch01": "en",
    "alice_ch02": "en",
    "little_women_ch01": "en",
    "pride_prejudice_ch01": "en",
    "sherlock_scandal_ch01": "en",
    "sherlock_speckled_band": "en",
    "journey_west_zh_ch01": "zh",
    "journey_west_zh_ch14": "zh",
    "son_tinh_thuy_tinh_vi": "vi",
    "tam_cam_vi": "vi",
}


def chapter_language(chapter: str) -> str:
    """Lookup the canonical language tag for a chapter. Falls back to `unk`."""

    return _CHAPTER_LANG.get(chapter, "unk")


@dataclass
class JudgeVerdict:
    """One verdict from one judge on one extracted/gold item."""

    chapter: str
    category: Category
    kind: VerdictKind
    idx: int
    verdict: VerdictLabel


@dataclass
class JudgeRunResult:
    """One judge's complete verdict set across a dump (or partial, if
    `judge_status == 'incomplete'`)."""

    judge_uuid: str
    judge_label: str  # short human-readable name for filenames + reports
    judge_status: JudgeStatus
    failure_reason: str = ""
    chapters_complete: list[str] = field(default_factory=list)
    chapters_incomplete: list[str] = field(default_factory=list)
    verdicts: list[JudgeVerdict] = field(default_factory=list)


@dataclass
class EnsembleItemVote:
    """One item, voted across judges. `votes` maps verdict-label to count."""

    chapter: str
    category: Category
    kind: VerdictKind
    idx: int
    votes: dict[str, int]
    majority_verdict: VerdictLabel | None  # None when no majority
    disputed: bool
    n_voting_judges: int  # count of judges that produced a non-`unjudged` verdict


@dataclass
class BiasMetric:
    """D12 per-judge bias metric block."""

    judge_label: str
    strictness: float  # support-acceptance rate
    strictness_gap: float
    language_accept_rates: dict[str, float]  # {lang: accept_rate}
    language_bias: float
    precision_accept_rate: float
    recall_accept_rate: float
    rp_bias: float  # precision_accept - recall_accept
    flagged_dimensions: list[str] = field(default_factory=list)


@dataclass
class EnsembleReport:
    """Top-level ensemble result. Persists as judge_ensemble_report.json."""

    judges: list[str]  # UUIDs in slot order [A, B, C]
    judge_labels: dict[str, str]  # UUID → short label
    judge_status: dict[str, JudgeStatus]  # UUID → status (D11 surface)
    judge_failure_reasons: dict[str, str]  # UUID → reason (empty for complete)
    fleiss_kappa: float | None  # None when < 2 judges complete on overlap
    fleiss_kappa_basis: int  # # of items where all completed judges voted
    fleiss_kappa_interpretation: str  # Landis & Koch bucket
    per_chapter_majority: dict[str, dict[str, Any]]  # chapter → {votes, disputed_count}
    bias_metrics: list[BiasMetric]  # one per completed judge
    ensemble_acceptable: bool  # D11: requires ≥ 2 judges `complete`


# ── ChapterJudgement → JudgeVerdict flatten (D4 adapter) ─────────────────────


def chapter_judgement_to_verdicts(judgement: Any) -> list[JudgeVerdict]:
    """Flatten a `llm_judge.ChapterJudgement` into a list of `JudgeVerdict`
    records the ensemble consumes.

    Maps each ItemVerdict/GoldVerdict into the (chapter, category, kind, idx,
    verdict_label) shape:
      - precision verdicts (ItemVerdict): verdict_label ∈ {supported, partial,
        unsupported, unjudged}
      - recall verdicts (GoldVerdict): convert `found` bool → {covered if True,
        uncovered if False}; `judged=False` → unjudged

    The function lives here (judge_ensemble.py) rather than in llm_judge.py
    so it can be unit-tested independently of the LLMClient import surface,
    AND so the regression-lock test for the GoldVerdict.gold_idx attribute
    (not `idx`) survives across both monorepo and container test runs.

    `judgement` is typed `Any` to avoid the circular import; the duck-typing
    expects `.chapter` str + `.entity / .relation / .event` CategoryJudgement-
    shaped objects with `.precision_verdicts` (ItemVerdict-like, with `.idx`
    + `.verdict`) and `.recall_verdicts` (GoldVerdict-like, with `.gold_idx`
    + `.found` + `.judged`).
    """

    verdicts: list[JudgeVerdict] = []
    for cat_judgement, category in (
        (judgement.entity, "entity"),
        (judgement.relation, "relation"),
        (judgement.event, "event"),
    ):
        for pv in cat_judgement.precision_verdicts:
            verdicts.append(
                JudgeVerdict(
                    chapter=judgement.chapter,
                    category=category,  # type: ignore[arg-type]
                    kind="precision",
                    idx=pv.idx,
                    verdict=pv.verdict,  # type: ignore[arg-type]
                )
            )
        for rv in cat_judgement.recall_verdicts:
            if not rv.judged:
                label = "unjudged"
            else:
                label = "covered" if rv.found else "uncovered"
            verdicts.append(
                JudgeVerdict(
                    chapter=judgement.chapter,
                    category=category,  # type: ignore[arg-type]
                    kind="recall",
                    idx=rv.gold_idx,  # GoldVerdict uses `gold_idx` (NOT `idx`)
                    verdict=label,  # type: ignore[arg-type]
                )
            )
    return verdicts


# ── Fleiss kappa ─────────────────────────────────────────────────────────────


def _fleiss_kappa(
    item_votes: list[dict[str, int]],
    n_raters: int,
) -> float:
    """Compute Fleiss' kappa for `len(item_votes)` items × `n_raters` raters.

    `item_votes[i]` is a dict mapping category → count of raters who chose
    that category for item i. Sum of counts per item MUST equal `n_raters`
    (caller's responsibility — drop items where any rater is `unjudged`).

    Returns κ in [-1, 1]. Returns 0.0 if no items.
    """

    n = len(item_votes)
    if n == 0 or n_raters < 2:
        return 0.0

    # Collect all categories seen
    categories: set[str] = set()
    for votes in item_votes:
        categories.update(votes.keys())
    categories_list = sorted(categories)
    if len(categories_list) < 2:
        # Perfect agreement on a single label → kappa undefined; convention κ=1.0
        return 1.0

    # p_j = overall proportion in category j
    p_j: dict[str, float] = {c: 0.0 for c in categories_list}
    for votes in item_votes:
        for c, count in votes.items():
            p_j[c] += count
    total = n * n_raters
    for c in p_j:
        p_j[c] /= total

    # P_i = per-item agreement
    p_i_sum = 0.0
    for votes in item_votes:
        sum_sq = sum(count * count for count in votes.values())
        p_i = (sum_sq - n_raters) / (n_raters * (n_raters - 1))
        p_i_sum += p_i
    p_bar = p_i_sum / n

    p_e = sum(p * p for p in p_j.values())
    if abs(1.0 - p_e) < 1e-12:
        # Trivial agreement (only one category used at full proportion)
        return 1.0 if p_bar >= 1.0 - 1e-12 else 0.0
    return (p_bar - p_e) / (1.0 - p_e)


def _kappa_interpretation(kappa: float) -> str:
    """Landis & Koch 1977 cutoffs (spec D3)."""

    if kappa < 0.0:
        return "below-chance"
    if kappa < 0.20:
        return "poor"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost-perfect"


# ── D11 ensemble combination ─────────────────────────────────────────────────


def _combine_votes(
    judge_results: Sequence[JudgeRunResult],
) -> tuple[list[EnsembleItemVote], int]:
    """For each (chapter, category, kind, idx) tuple seen across judges,
    aggregate votes and emit one `EnsembleItemVote`. Items where any judge
    produced `unjudged` (or didn't vote at all because of `incomplete`) are
    EXCLUDED from κ basis but still surfaced in the vote list with reduced
    `n_voting_judges`.

    Returns (vote list, kappa_basis_count) where kappa_basis_count is the
    number of items voted on by ALL `complete` judges (basis for Fleiss κ).
    """

    # Index by item key
    by_item: dict[tuple[str, Category, VerdictKind, int], dict[str, int]] = {}
    judges_voting_on_item: dict[
        tuple[str, Category, VerdictKind, int], set[str]
    ] = {}
    for jr in judge_results:
        for v in jr.verdicts:
            key = (v.chapter, v.category, v.kind, v.idx)
            if v.verdict == "unjudged":
                continue  # don't count unjudged as a vote
            by_item.setdefault(key, {})
            by_item[key][v.verdict] = by_item[key].get(v.verdict, 0) + 1
            judges_voting_on_item.setdefault(key, set()).add(jr.judge_uuid)

    completed_judges = {jr.judge_uuid for jr in judge_results if jr.judge_status == "complete"}

    out: list[EnsembleItemVote] = []
    kappa_basis = 0
    for key, votes in by_item.items():
        chapter, category, kind, idx = key
        n_voting = sum(votes.values())
        # Majority requires strict > half of completed judges (e.g., 2/3 = majority)
        sorted_votes = sorted(votes.items(), key=lambda kv: -kv[1])
        top_label, top_count = sorted_votes[0]
        majority = top_label if top_count > len(completed_judges) / 2 else None
        disputed = majority is None
        out.append(
            EnsembleItemVote(
                chapter=chapter,
                category=category,
                kind=kind,
                idx=idx,
                votes=votes,
                majority_verdict=majority if majority is not None else None,
                disputed=disputed,
                n_voting_judges=n_voting,
            )
        )
        if judges_voting_on_item[key] == completed_judges and len(completed_judges) >= 2:
            kappa_basis += 1
    return out, kappa_basis


# ── D12 bias metrics ─────────────────────────────────────────────────────────


def _compute_bias_metrics(
    judge_results: Sequence[JudgeRunResult],
) -> list[BiasMetric]:
    """Per spec D12: strictness_gap, language_bias, rp_bias for each completed
    judge. Flag thresholds: strictness_gap > 0.15, language_bias > 0.15.
    rp_bias is informational (no flag threshold)."""

    complete_judges = [jr for jr in judge_results if jr.judge_status == "complete"]
    if not complete_judges:
        return []

    accept_labels = {"supported", "covered"}  # positive-verdict labels

    # Per-judge strictness (overall positive-acceptance rate)
    strictness_per_judge: dict[str, float] = {}
    for jr in complete_judges:
        non_unjudged = [v for v in jr.verdicts if v.verdict != "unjudged"]
        if non_unjudged:
            strictness_per_judge[jr.judge_uuid] = sum(
                1 for v in non_unjudged if v.verdict in accept_labels
            ) / len(non_unjudged)
        else:
            strictness_per_judge[jr.judge_uuid] = 0.0
    median_strictness = statistics.median(strictness_per_judge.values())

    results: list[BiasMetric] = []
    for jr in complete_judges:
        # Strictness gap
        s = strictness_per_judge[jr.judge_uuid]
        gap = abs(s - median_strictness)

        # Language bias: per-lang accept rate
        lang_counts: dict[str, tuple[int, int]] = {}  # lang → (accepts, totals)
        for v in jr.verdicts:
            if v.verdict == "unjudged":
                continue
            lang = chapter_language(v.chapter)
            accepts, totals = lang_counts.get(lang, (0, 0))
            totals += 1
            if v.verdict in accept_labels:
                accepts += 1
            lang_counts[lang] = (accepts, totals)
        lang_rates: dict[str, float] = {}
        for lang, (a, t) in lang_counts.items():
            lang_rates[lang] = (a / t) if t else 0.0
        lang_bias = (
            max(lang_rates.values()) - min(lang_rates.values())
            if len(lang_rates) >= 2
            else 0.0
        )

        # rp_bias: precision-accept - recall-accept
        p_accepts = p_total = r_accepts = r_total = 0
        for v in jr.verdicts:
            if v.verdict == "unjudged":
                continue
            is_accept = v.verdict in accept_labels
            if v.kind == "precision":
                p_total += 1
                if is_accept:
                    p_accepts += 1
            else:
                r_total += 1
                if is_accept:
                    r_accepts += 1
        p_rate = (p_accepts / p_total) if p_total else 0.0
        r_rate = (r_accepts / r_total) if r_total else 0.0
        rp = p_rate - r_rate

        flagged: list[str] = []
        if gap > 0.15:
            flagged.append("strictness_gap")
        if lang_bias > 0.15:
            flagged.append("language_bias")

        results.append(
            BiasMetric(
                judge_label=jr.judge_label,
                strictness=s,
                strictness_gap=gap,
                language_accept_rates=lang_rates,
                language_bias=lang_bias,
                precision_accept_rate=p_rate,
                recall_accept_rate=r_rate,
                rp_bias=rp,
                flagged_dimensions=flagged,
            )
        )
    return results


# ── Ensemble orchestration ───────────────────────────────────────────────────


async def run_ensemble_judges(
    judges: Sequence[tuple[str, str]],
    judge_fn: Callable[[str], Awaitable[JudgeRunResult]],
) -> list[JudgeRunResult]:
    """Run each (uuid, label) judge sequentially via `judge_fn`. Failures from
    `judge_fn` produce a `JudgeRunResult(judge_status='failed', ...)` rather
    than propagating exceptions — the ensemble surfaces all judges' status
    independently per D11.

    `judge_fn(judge_uuid)` is provided by the caller — typically a closure
    around `llm_judge.judge_chapter()` over a dump tree.
    """

    results: list[JudgeRunResult] = []
    for uuid, label in judges:
        try:
            jr = await judge_fn(uuid)
            # If the callable returned a result missing label, fix it up.
            if not jr.judge_label:
                jr.judge_label = label
            results.append(jr)
        except Exception as e:  # noqa: BLE001 — broad-catch is the D11 policy
            logger.warning(
                "Judge %s (%s) failed: %s", label, uuid, e, exc_info=True
            )
            results.append(
                JudgeRunResult(
                    judge_uuid=uuid,
                    judge_label=label,
                    judge_status="failed",
                    failure_reason=f"{type(e).__name__}: {e}",
                )
            )
    return results


def assemble_report(
    judge_results: Sequence[JudgeRunResult],
) -> EnsembleReport:
    """Combine per-judge run results into the canonical `EnsembleReport`."""

    judges_uuids = [jr.judge_uuid for jr in judge_results]
    judge_labels = {jr.judge_uuid: jr.judge_label for jr in judge_results}
    judge_status = {jr.judge_uuid: jr.judge_status for jr in judge_results}
    judge_failure_reasons = {
        jr.judge_uuid: jr.failure_reason for jr in judge_results if jr.failure_reason
    }
    n_complete = sum(1 for jr in judge_results if jr.judge_status == "complete")

    item_votes, kappa_basis = _combine_votes(judge_results)

    # Fleiss κ across items voted by all completed judges
    complete_judges = [jr for jr in judge_results if jr.judge_status == "complete"]
    n_raters = len(complete_judges)
    kappa: float | None = None
    if n_raters >= 2 and kappa_basis > 0:
        per_item_votes: list[dict[str, int]] = []
        # Re-iterate only the items in kappa basis (n_voting_judges == n_raters)
        for iv in item_votes:
            if iv.n_voting_judges == n_raters:
                per_item_votes.append(iv.votes)
        kappa = _fleiss_kappa(per_item_votes, n_raters)

    # Per-chapter majority summary
    per_chapter: dict[str, dict[str, Any]] = {}
    for iv in item_votes:
        ch = per_chapter.setdefault(
            iv.chapter,
            {"vote_count": 0, "majority_count": 0, "disputed_count": 0, "by_category": {}},
        )
        ch["vote_count"] += 1
        if iv.majority_verdict is not None:
            ch["majority_count"] += 1
        if iv.disputed:
            ch["disputed_count"] += 1
        cat_block = ch["by_category"].setdefault(
            iv.category, {"vote_count": 0, "majority_count": 0, "disputed_count": 0}
        )
        cat_block["vote_count"] += 1
        if iv.majority_verdict is not None:
            cat_block["majority_count"] += 1
        if iv.disputed:
            cat_block["disputed_count"] += 1

    bias = _compute_bias_metrics(judge_results)

    ensemble_acceptable = n_complete >= 2  # D11 acceptance gate

    return EnsembleReport(
        judges=judges_uuids,
        judge_labels=judge_labels,
        judge_status=judge_status,
        judge_failure_reasons=judge_failure_reasons,
        fleiss_kappa=kappa,
        fleiss_kappa_basis=kappa_basis,
        fleiss_kappa_interpretation=_kappa_interpretation(kappa) if kappa is not None else "n/a",
        per_chapter_majority=per_chapter,
        bias_metrics=bias,
        ensemble_acceptable=ensemble_acceptable,
    )


def persist_verdicts(
    judge_results: Sequence[JudgeRunResult],
    out_dir: Path,
) -> dict[str, Path]:
    """Write each judge's verdicts to `judge_verdicts_<label>.json`.
    Returns map of judge_label → file path."""

    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for jr in judge_results:
        # Filesystem-safe label
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in jr.judge_label)
        path = out_dir / f"judge_verdicts_{safe_label}.json"
        payload = {
            "judge_uuid": jr.judge_uuid,
            "judge_label": jr.judge_label,
            "judge_status": jr.judge_status,
            "failure_reason": jr.failure_reason,
            "chapters_complete": jr.chapters_complete,
            "chapters_incomplete": jr.chapters_incomplete,
            "verdicts": [asdict(v) for v in jr.verdicts],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[jr.judge_label] = path
    return written


def persist_ensemble_report(report: EnsembleReport, out_dir: Path) -> Path:
    """Write the assembled ensemble report to `judge_ensemble_report.json`."""

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "judge_ensemble_report.json"
    path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path
