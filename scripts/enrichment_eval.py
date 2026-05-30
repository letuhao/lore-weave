"""Enrichment eval (RAID C15) — cultural-fidelity quality measurement + GATE for
enriched 封神演义 lore proposals.

EXTENDS the platform eval pattern (``scripts/climate_eval.py`` +
``eval/*-suite.toml`` + ``eval/baselines/*.json``) ADDITIVELY in a SEPARATE
namespace — it NEVER touches the climate/geo eval files.

Scores enriched proposals on five weighted sub-scores
(schema/canon/anachronism/provenance/usefulness — cultural-fidelity) using
deterministic rule scorers + a judge-ENSEMBLE (gemma + qwen-30b + claude via
provider-registry; majority + Fleiss κ + partial-credit) for the subjective
usefulness sub-score. Diffs against a versioned baseline, persists the run to
``enrichment_eval_runs``, and computes the GATE decision that blocks the
higher-cost techniques (C16 fabrication / C17 re-cook) below threshold.

Usage:
  # score a replay fixture (deterministic; no DB, no judges):
  python scripts/enrichment_eval.py --fixture eval/fixtures/enrichment_demo.json

  # diff against the frozen baseline + emit scorecard JSON:
  python scripts/enrichment_eval.py --fixture <f> \
       --baseline eval/baselines/enrichment-v1.json --out /tmp/scorecard.json

  # freeze a new baseline from the current scores:
  python scripts/enrichment_eval.py --fixture <f> --output eval/baselines/enrichment-v1.json

  # LIVE: score the demo project's promoted proposals with the REAL judge
  # ensemble (provider-registry) + persist to enrichment_eval_runs:
  python scripts/enrichment_eval.py --live --project <uuid> --user <uuid> \
       --judges gemma=<ref>,qwen30b=<ref>,claude=<ref>

Exit codes:
  0 — gate PASSED (composite >= threshold, no regression, ensemble acceptable).
  1 — gate FAILED / regression detected (P2/P3 stay BLOCKED). This is the
      cost-discipline checkpoint — a failing exit is the EXPECTED signal for a
      below-threshold demo, not a crash.
  3 — live infra unavailable (DB/provider-registry unreachable) — honest skip.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LE_SVC = REPO_ROOT / "services" / "lore-enrichment-service"
SUITE_TOML = REPO_ROOT / "eval" / "enrichment-eval-suite.toml"

# Make the lore-enrichment-service app package importable when run from repo root.
if str(LE_SVC) not in sys.path:
    sys.path.insert(0, str(LE_SVC))

# Tests/standalone import-time fail-fast: app.config needs these (throwaway).
os.environ.setdefault("LORE_ENRICHMENT_DB_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "enrichment_eval_jwt")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "enrichment_eval_token")


def _load_app():
    """Import the eval app modules (after sys.path + env are set)."""
    from app.eval.runner import run_eval  # noqa: PLC0415
    from app.eval.scorers import ScorableProposal  # noqa: PLC0415
    from app.eval.suite import load_suite  # noqa: PLC0415
    return run_eval, ScorableProposal, load_suite


def _proposals_from_fixture(path: Path, ScorableProposal):
    """Load proposals from a replay fixture JSON.

    Fixture shape: {"proposals": [{"name","entity_kind","origin","technique",
    "confidence","review_status","provenance_json","source_refs_json"}, ...]}.
    Mirrors the persisted-proposal columns so the SAME scorer code path scores a
    fixture and a live row identically.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for p in data.get("proposals", []):
        out.append(ScorableProposal.from_provenance_json(
            name=p["name"],
            entity_kind=p.get("entity_kind", "location"),
            origin=p["origin"],
            technique=p["technique"],
            confidence=float(p["confidence"]),
            review_status=p.get("review_status", "proposed"),
            provenance_json=p.get("provenance_json", {}),
            source_refs_json=p.get("source_refs_json", []),
        ))
    return out


def _parse_judges(spec: str | None):
    """Parse '--judges label=ref,label2=ref2' into JudgeSpec list."""
    from app.eval.judge_usefulness import JudgeSpec  # noqa: PLC0415
    if not spec:
        return []
    judges = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        label, ref = chunk.split("=", 1)
        judges.append(JudgeSpec(label=label.strip(), model_ref=ref.strip()))
    return judges


def _print_report(outcome, suite) -> None:
    sc = outcome.scorecard
    print(f"# Enrichment eval — suite {sc.suite_version} — {sc.n_proposals} proposal(s)\n")
    print(f"{'sub-score':<14} {'weight':>7} {'value':>7}")
    print("-" * 32)
    for k in ("schema", "canon", "anachronism", "provenance", "usefulness"):
        print(f"{k:<14} {suite.weights[k]:>7.2f} {sc.subscores[k]:>7.1f}")
    print("-" * 32)
    print(f"{'COMPOSITE':<14} {'':>7} {sc.composite:>7.2f}  (gate min "
          f"{outcome.decision.min_composite})")
    print(f"judge κ: {sc.fleiss_kappa} ({sc.kappa_interpretation}); "
          f"ensemble acceptable: {sc.judge_ensemble_acceptable}")
    if outcome.baseline_diff is not None:
        bd = outcome.baseline_diff
        print(f"\n## Diff vs baseline (composite {bd.composite_delta:+.2f})")
        for k, d in bd.subscore_deltas.items():
            print(f"  {k:<14} {d:+.1f}")
        if bd.regressions:
            print("  REGRESSIONS:")
            for r in bd.regressions:
                print(f"    - {r}")
    print(f"\nGATE: {'PASS — P2/P3 may activate' if sc.passed else 'BLOCK — P2/P3 stay OFF'}")
    if not sc.passed:
        for r in outcome.decision.reasons:
            print(f"  - {r}")


async def _live_proposals(project: str, user: str, ScorableProposal, status: str):
    """Load the demo project's proposals (the promoted/enriched 4 locations) from
    the real DB. Returns (proposals, pool) or (None, None) on infra-unavailable."""
    import asyncpg  # noqa: PLC0415
    from uuid import UUID  # noqa: PLC0415
    from app.services.review import ProposalsRepo  # noqa: PLC0415

    dsn = os.environ.get("LORE_ENRICHMENT_DB_URL_LIVE") or os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    if not dsn or "test:test@localhost" in dsn:
        return None, None
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=15)
    except (OSError, asyncpg.PostgresError):
        return None, None
    repo = ProposalsRepo(pool)
    rows, _ = await repo.list(
        user_id=UUID(user), project_id=UUID(project),
        review_status=(status or None), limit=100,
    )
    props = [
        ScorableProposal.from_provenance_json(
            name=(r.canonical_name or r.target_ref or str(r.proposal_id)),
            entity_kind=r.entity_kind,
            origin=r.origin, technique=r.technique,
            confidence=float(r.confidence), review_status=r.review_status,
            provenance_json=r.provenance_json, source_refs_json=r.source_refs_json,
        )
        for r in rows
    ]
    return props, pool


def _make_judge_fn_for(pr_url: str, token: str):
    """Build a judge_fn_for(judge) bound to provider-registry /internal/llm/stream
    (same shape as C14 complete.make_complete_fn) — judges resolved by model_ref,
    NO model name. Tolerates JIT load via a generous timeout."""
    from app.generation.complete import collect_stream_text  # noqa: PLC0415
    import httpx  # noqa: PLC0415

    base = pr_url.rstrip("/")

    def judge_fn_for(judge):
        async def _fn(system: str, user: str) -> str:
            body = {
                "operation": "chat",
                "model_source": "user_model",
                "model_ref": judge.model_ref,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {"X-Internal-Token": token,
                       "Content-Type": "application/json; charset=utf-8"}
            params = {"user_id": os.environ.get("EVAL_JUDGE_USER", "")}
            timeout = httpx.Timeout(240.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/internal/llm/stream",
                    headers=headers, params=params, content=content,
                )
            if resp.status_code != 200:
                raise RuntimeError(f"judge call {resp.status_code}: {resp.text[:200]}")
            return collect_stream_text(resp.text)
        return _fn
    return judge_fn_for


async def _run(args) -> int:
    run_eval, ScorableProposal, load_suite = _load_app()
    suite = load_suite(SUITE_TOML)

    baseline = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    judges = _parse_judges(args.judges)
    judge_fn_for = None
    pool = None

    if args.live:
        props, pool = await _live_proposals(
            args.project, args.user, ScorableProposal, args.status
        )
        if props is None:
            print("live infra unavailable: lore-enrichment DB unreachable/unset", file=sys.stderr)
            return 3
        if judges:
            pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
            token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
            judge_fn_for = _make_judge_fn_for(pr_url, token)
    else:
        if not args.fixture:
            print("error: --fixture required (or --live)", file=sys.stderr)
            return 2
        props = _proposals_from_fixture(Path(args.fixture), ScorableProposal)

    try:
        outcome = await run_eval(
            props, suite, baseline=baseline,
            judges=judges, judge_fn_for=judge_fn_for,
        )
        _print_report(outcome, suite)

        if args.out:
            Path(args.out).write_text(
                json.dumps(outcome.scorecard.to_json(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nscorecard → {args.out}")

        if args.output:
            # Freeze a baseline (subscores + composite + version).
            sc = outcome.scorecard
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps({
                "version": sc.suite_version,
                "subscores": sc.subscores,
                "composite": sc.composite,
                "n_proposals": sc.n_proposals,
                "fleiss_kappa": sc.fleiss_kappa,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"baseline frozen → {args.output}")

        # Persist to enrichment_eval_runs (live runs only — needs a real DB).
        if args.live and pool is not None and args.persist:
            from uuid import UUID  # noqa: PLC0415
            from app.db.repositories.eval_runs import EvalRunsRepo  # noqa: PLC0415
            import datetime as _dt  # noqa: PLC0415
            repo = EvalRunsRepo(pool)
            sc = outcome.scorecard
            run_id = args.run_id or _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            persisted = await repo.persist(
                user_id=UUID(args.user), project_id=UUID(args.project),
                run_id=run_id, suite_version=sc.suite_version,
                baseline_version=sc.baseline_version, n_proposals=sc.n_proposals,
                subscores=sc.subscores, composite=sc.composite,
                fleiss_kappa=sc.fleiss_kappa,
                judge_ensemble_acceptable=sc.judge_ensemble_acceptable,
                passed=sc.passed, raw_report=sc.to_json(),
            )
            print(f"persisted eval_run {persisted.eval_run_id} "
                  f"(passed={persisted.passed}, deduped={persisted.deduped})")
    finally:
        if pool is not None:
            await pool.close()

    return 0 if outcome.scorecard.passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", type=str, help="replay fixture JSON of proposals")
    ap.add_argument("--baseline", type=str, help="diff against this baseline JSON")
    ap.add_argument("--output", type=str, help="freeze a baseline JSON here")
    ap.add_argument("--out", type=str, help="write the scorecard JSON here")
    ap.add_argument("--live", action="store_true", help="load proposals from the real DB")
    ap.add_argument("--project", type=str, default=os.environ.get("DEMO_PROJECT", ""))
    ap.add_argument("--user", type=str, default=os.environ.get("DEMO_USER", ""))
    ap.add_argument("--status", type=str, default="",
                    help="filter live proposals by review_status (e.g. promoted)")
    ap.add_argument("--judges", type=str,
                    help="comma list label=model_ref (provider-registry refs, NO names)")
    ap.add_argument("--persist", action="store_true",
                    help="persist the live run to enrichment_eval_runs")
    ap.add_argument("--run-id", type=str, help="explicit run_id (default timestamp)")
    args = ap.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
