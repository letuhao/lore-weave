"""Eval RUNNER — load→run→persist (RAID C15).

Mirrors the knowledge-service benchmark runner pattern: take a set of enriched
proposals, score each (4 deterministic sub-scores + the judge-ensemble
usefulness sub-score), aggregate the weighted composite, diff against the frozen
baseline, compute the GATE decision, and (optionally) persist the scorecard to
``enrichment_eval_runs``.

The runner is LLM-aware only through the injected judge ensemble — the four
deterministic sub-scores need no network, so a fixture run (no live judges)
still produces a real composite over schema/canon/anachronism/provenance and a
``usefulness`` of 0 with ``judge_ensemble_acceptable=False`` (which the gate
treats as a BLOCK — never a false-green). When live judges are wired, usefulness
is the ensemble credit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.config import settings
from app.db.book_profile import BookProfile
from app.eval import scorers
from app.eval.gate import GateDecision, gate_decision
from app.eval.judge_usefulness import (
    JudgeFn,
    JudgeSpec,
    JudgeUsefulnessResult,
    ProposalForJudging,
    build_usefulness_rubric,
    score_usefulness_ensemble,
)
from app.gaps.model import is_zh, kind_label_for, resolve_dimensions
from app.eval.scorers import ScorableProposal
from app.eval.suite import (
    SUBSCORE_KEYS,
    BaselineDiff,
    EvalSuite,
    Scorecard,
    composite_score,
    diff_against_baseline,
)

__all__ = ["EvalRunOutcome", "run_eval"]


@dataclass(frozen=True)
class EvalRunOutcome:
    """The full result of an eval run: the scorecard, the gate decision, and the
    baseline diff (when a baseline was supplied)."""

    scorecard: Scorecard
    decision: GateDecision
    baseline_diff: BaselineDiff | None
    usefulness: JudgeUsefulnessResult


def _mean(vals: Sequence[float]) -> float:
    return round(sum(vals) / len(vals), 1) if vals else 0.0


async def run_eval(
    proposals: Sequence[ScorableProposal],
    suite: EvalSuite,
    *,
    baseline: dict[str, Any] | None = None,
    judges: Sequence[JudgeSpec] = (),
    judge_fn_for: Callable[[JudgeSpec], JudgeFn] | None = None,
    profile: BookProfile | None = None,
) -> EvalRunOutcome:
    """Score ``proposals`` under ``suite``; diff against ``baseline`` if given;
    run the judge ensemble for usefulness if judges + judge_fn_for are supplied;
    compute the GATE decision.

    Deterministic sub-scores (schema/canon/anachronism/provenance) are computed
    per-proposal and averaged. The subjective usefulness sub-score is the judge
    ensemble's mean credit (0 with ``acceptable=False`` when no live judges).

    De-bias (LE-PROD slice D): ``profile=None`` keeps the LEGACY Fengshen-tuned
    behavior (the scorers/judge use their 封神 defaults — no regression, all
    existing callers unchanged). When a per-book ``profile`` is passed, the schema
    dims (per the proposal's KIND), the language-faithfulness check, the anachronism
    markers, and the judge rubric/kind-label are all DERIVED from it — so the gate
    that unlocks P2/P3 can pass for a NON-Fengshen book judged on its own terms."""
    per_proposal: list[dict[str, Any]] = []
    schema_vals: list[float] = []
    canon_vals: list[float] = []
    anach_vals: list[float] = []
    prov_vals: list[float] = []
    all_issues: list[str] = []

    # Profile-derived knobs (slice D). markers: the profile's per-book denylist
    # (EMPTY ⇒ anachronism check OFF for a non-Fengshen book). require_cjk: only a
    # zh book demands CJK-faithful content.
    _markers = (
        tuple(t for t, _ in (profile.anachronism_markers or ())) if profile else None
    )
    _require_cjk = is_zh(profile.language) if profile else True

    for p in proposals:
        if profile is not None:
            specs = resolve_dimensions(
                p.entity_kind, language=profile.language,
                overrides=profile.dimension_overrides,
            )
            req = tuple(s.label for s in specs if s.required)
            opt = tuple(s.label for s in specs if not s.required)
            s, s_iss = scorers.score_schema(
                p, required_dims=req, optional_dims=opt, require_cjk=_require_cjk
            )
            a, a_iss = scorers.score_anachronism(p, markers=_markers or ())
        else:
            s, s_iss = scorers.score_schema(p)
            a, a_iss = scorers.score_anachronism(p)
        c, c_iss = scorers.score_canon(p)
        pr, pr_iss = scorers.score_provenance(p)
        schema_vals.append(s)
        canon_vals.append(c)
        anach_vals.append(a)
        prov_vals.append(pr)
        issues = s_iss + c_iss + a_iss + pr_iss
        all_issues.extend(f"[{p.name}] {i}" for i in issues)
        per_proposal.append({
            "name": p.name,
            "schema": s, "canon": c, "anachronism": a, "provenance": pr,
            "issues": issues,
        })

    # ── judge-ensemble usefulness sub-score ──────────────────────────────────
    if judges and judge_fn_for is not None:
        forjudge = [
            ProposalForJudging(name=p.name, dimensions=p.dimensions)
            for p in proposals
        ]
        if profile is not None:
            # One rubric/label per batch (profile-driven). Mixed-kind batches use
            # the first proposal's kind for the label — the rubric itself is
            # kind-agnostic ("this {kind} enrichment").
            klabel = (
                kind_label_for(proposals[0].entity_kind, profile.language)
                if proposals else "条目"
            )
            usefulness_res = await score_usefulness_ensemble(
                forjudge, judges, judge_fn_for,
                kappa_floor=settings.judge_kappa_floor,
                rubric=build_usefulness_rubric(profile, kind_label=klabel),
                kind_label=klabel,
            )
        else:
            usefulness_res = await score_usefulness_ensemble(
                forjudge, judges, judge_fn_for, kappa_floor=settings.judge_kappa_floor
            )
    else:
        usefulness_res = JudgeUsefulnessResult(
            usefulness=0.0, fleiss_kappa=None, kappa_interpretation="n/a",
            n_judges=0, n_judges_voting=0, acceptable=False,
        )

    subscores: dict[str, float] = {
        "schema": _mean(schema_vals),
        "canon": _mean(canon_vals),
        "anachronism": _mean(anach_vals),
        "provenance": _mean(prov_vals),
        "usefulness": usefulness_res.usefulness,
    }
    composite = composite_score(subscores, suite.weights)

    baseline_diff: BaselineDiff | None = None
    if baseline is not None:
        baseline_diff = diff_against_baseline(
            subscores, composite, baseline, suite.regression
        )

    # Build a provisional scorecard (passed filled after the gate decides).
    provisional = Scorecard(
        suite_version=suite.version,
        baseline_version=(baseline or {}).get("version") if baseline else None,
        n_proposals=len(proposals),
        subscores=subscores,
        composite=composite,
        fleiss_kappa=usefulness_res.fleiss_kappa,
        kappa_interpretation=usefulness_res.kappa_interpretation,
        judge_ensemble_acceptable=usefulness_res.acceptable,
        passed=False,
        issues=all_issues,
        per_proposal=_merge_per_proposal(per_proposal, usefulness_res.per_proposal),
    )

    decision = gate_decision(provisional, suite, baseline_diff)

    scorecard = Scorecard(
        suite_version=provisional.suite_version,
        baseline_version=provisional.baseline_version,
        n_proposals=provisional.n_proposals,
        subscores=provisional.subscores,
        composite=provisional.composite,
        fleiss_kappa=provisional.fleiss_kappa,
        kappa_interpretation=provisional.kappa_interpretation,
        judge_ensemble_acceptable=provisional.judge_ensemble_acceptable,
        passed=decision.passed,
        issues=provisional.issues + (
            [] if decision.passed else [f"GATE: {r}" for r in decision.reasons]
        ),
        per_proposal=provisional.per_proposal,
    )

    return EvalRunOutcome(
        scorecard=scorecard,
        decision=decision,
        baseline_diff=baseline_diff,
        usefulness=usefulness_res,
    )


def _merge_per_proposal(
    deterministic: list[dict[str, Any]],
    usefulness: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fold the judge-ensemble per-proposal verdict into the deterministic
    per-proposal rows (matched by name; usefulness may be empty for a no-judge
    run)."""
    by_name = {u.get("name"): u for u in usefulness}
    out: list[dict[str, Any]] = []
    for row in deterministic:
        merged = dict(row)
        u = by_name.get(row["name"])
        if u is not None:
            merged["usefulness_verdict"] = u.get("majority_verdict")
            merged["usefulness_credit"] = u.get("credit")
            merged["judge_votes"] = u.get("judge_votes")
        out.append(merged)
    return out


# expose the subscore order for callers building reports
_ = SUBSCORE_KEYS
