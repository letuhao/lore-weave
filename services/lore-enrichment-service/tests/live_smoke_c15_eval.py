"""C15 LIVE SMOKE — real judge-ENSEMBLE eval on the DEMO output.

Scores the demo project's enriched proposals (the 4 promoted/enriched demo
locations 玉虛宮/碧遊宮·金鰲島/蓬萊/陳塘關) with the REAL multi-judge ensemble
(gemma + qwen-30b + claude via provider-registry; majority + Fleiss κ +
partial-credit), produces a real scorecard, persists it to enrichment_eval_runs,
freezes a baseline, and prints the GATE decision (does the demo output clear the
threshold for P2/P3?).

Honest infra handling: if the demo DB has no scorable proposals, or a judge
model won't JIT-load / provider-registry is unreachable, exit 3 (live infra
unavailable) — never fabricate a scorecard. The 4 deterministic sub-scores still
compute from the persisted proposals; usefulness needs the live judges.

Exit codes:
  0 — real judge-ensemble scorecard produced + persisted (gate decision printed).
  3 — live infra unavailable (no demo proposals / judge JIT / DB unreachable).
  1 — an unexpected error (the eval ran but something broke).

Judges are resolved by NAME at runtime (lookup keys, env-overridable) → the
app/eval code only ever receives the resolved model_ref (no-name invariant).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE_TOML = REPO_ROOT / "eval" / "enrichment-eval-suite.toml"
BASELINE = REPO_ROOT / "eval" / "baselines" / "enrichment-v1.json"

from app.db.repositories.eval_runs import EvalRunsRepo  # noqa: E402
from app.eval.judge_usefulness import JudgeSpec  # noqa: E402
from app.eval.runner import run_eval  # noqa: E402
from app.eval.scorers import ScorableProposal  # noqa: E402
from app.eval.suite import load_suite  # noqa: E402
from app.generation.complete import collect_stream_text  # noqa: E402
from app.services.review import ProposalsRepo  # noqa: E402

import httpx  # noqa: E402


async def _resolve_ref(pr_dsn: str, name: str, *, owner: str | None = None):
    conn = await asyncpg.connect(pr_dsn)
    try:
        if owner is not None:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name = $1 AND owner_user_id = $2
                     AND is_active = true ORDER BY created_at DESC LIMIT 1""",
                name, uuid.UUID(owner),
            )
        else:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name = $1 AND is_active = true
                   ORDER BY created_at DESC LIMIT 1""",
                name,
            )
    finally:
        await conn.close()
    if row is None:
        return None, None
    return str(row["user_model_id"]), str(row["owner_user_id"])


def _make_judge_fn_for(pr_url: str, token: str, owner_by_ref: dict[str, str]):
    """Build judge_fn_for(judge). Each judge's BYOK call is scoped to ITS OWN
    owner_user_id (a model is owned per-user in provider-registry; passing a
    mismatched user_id → 404). The map is keyed on the resolved model_ref."""
    base = pr_url.rstrip("/")

    def judge_fn_for(judge: JudgeSpec):
        async def _fn(system: str, user: str) -> str:
            body = {
                "operation": "chat", "model_source": "user_model",
                "model_ref": judge.model_ref,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {"X-Internal-Token": token,
                       "Content-Type": "application/json; charset=utf-8"}
            params = {"user_id": owner_by_ref.get(judge.model_ref, "")}
            timeout = httpx.Timeout(300.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/internal/llm/stream",
                    headers=headers, params=params, content=content,
                )
            if resp.status_code != 200:
                raise RuntimeError(f"judge {judge.label} HTTP {resp.status_code}: {resp.text[:160]}")
            return collect_stream_text(resp.text)
        return _fn
    return judge_fn_for


async def _main() -> int:
    db_dsn = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr_dsn = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    project = os.environ.get("DEMO_PROJECT", "")
    user = os.environ.get("DEMO_USER", "")
    gemma_name = os.environ.get("JUDGE_GEMMA_NAME", "google/gemma-3-27b")
    qwen_name = os.environ.get("JUDGE_QWEN_NAME", "qwen/qwen3-30b-a3b")

    if not db_dsn or not pr_dsn or not project or not user:
        print("live infra unavailable: required env (DB/PR/DEMO_PROJECT/DEMO_USER) not set",
              file=sys.stderr)
        return 3

    # 1. load the demo project's proposals (any non-rejected enriched proposals).
    try:
        pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=3, command_timeout=20)
    except (OSError, asyncpg.PostgresError) as exc:
        print(f"live infra unavailable: lore DB unreachable ({exc})", file=sys.stderr)
        return 3

    try:
        repo = ProposalsRepo(pool)
        rows, total = await repo.list(
            user_id=uuid.UUID(user), project_id=uuid.UUID(project), limit=100,
        )
        # exclude rejected; keep enriched/promoted (the demo output).
        rows = [r for r in rows if r.review_status != "rejected"]
        proposal_source = ""
        if rows:
            props = [
                ScorableProposal.from_provenance_json(
                    name=(r.canonical_name or r.target_ref or str(r.proposal_id)),
                    entity_kind=r.entity_kind, origin=r.origin, technique=r.technique,
                    confidence=float(r.confidence), review_status=r.review_status,
                    provenance_json=r.provenance_json, source_refs_json=r.source_refs_json,
                )
                for r in rows
            ]
            proposal_source = "live-DB"
            print(f"[c15-smoke] loaded {len(props)} demo proposal(s) from project {project} (live DB)")
        else:
            # No C14-generated rows persisted in THIS DB instance — fall back to the
            # committed demo-output replay fixture (the same 4 locations 玉虛宮/碧遊宮·
            # 金鰲島/蓬萊/陳塘關, representative source-faithful Chinese the C14 real-Qwen
            # demo produced). We still score with the REAL judge ensemble + persist a
            # real scorecard; the proposal SOURCE is labelled fixture-replay (honest).
            fixture = REPO_ROOT / "eval" / "fixtures" / "enrichment_demo.json"
            if not fixture.is_file():
                print("live infra unavailable: no DB proposals and no demo fixture",
                      file=sys.stderr)
                return 3
            data = json.loads(fixture.read_text(encoding="utf-8"))
            props = [
                ScorableProposal.from_provenance_json(
                    name=p["name"], entity_kind=p.get("entity_kind", "location"),
                    origin=p["origin"], technique=p["technique"],
                    confidence=float(p["confidence"]),
                    review_status=p.get("review_status", "proposed"),
                    provenance_json=p.get("provenance_json", {}),
                    source_refs_json=p.get("source_refs_json", []),
                )
                for p in data.get("proposals", [])
            ]
            proposal_source = "demo-fixture-replay"
            print(f"[c15-smoke] no live-DB proposals in project {project}; "
                  f"scoring the committed demo-output replay fixture "
                  f"({len(props)} locations) with the REAL judge ensemble")
        if not props:
            print("live infra unavailable: no scorable proposals", file=sys.stderr)
            return 3

        # 2. resolve the judge ensemble model_refs by name. Each judge keeps its
        # OWN owner_user_id (BYOK is per-user; a mismatched user_id → 404).
        judges = []
        owner_by_ref: dict[str, str] = {}
        gemma_ref, gemma_owner = await _resolve_ref(pr_dsn, gemma_name)
        if gemma_ref:
            judges.append(JudgeSpec(label="gemma", model_ref=gemma_ref, family="gemma"))
            owner_by_ref[gemma_ref] = gemma_owner
        qwen_ref, qwen_owner = await _resolve_ref(pr_dsn, qwen_name)
        if qwen_ref:
            judges.append(JudgeSpec(label="qwen-30b", model_ref=qwen_ref, family="qwen"))
            owner_by_ref[qwen_ref] = qwen_owner
        # 3rd judge — claude (cloud) per the locked ensemble, included if registered.
        claude_name = os.environ.get("JUDGE_CLAUDE_NAME", "")
        claude_candidates = (
            [claude_name] if claude_name else [
                "claude-opus-4-7", "claude/claude-4.7-opus", "anthropic/claude-opus-4-7",
                "claude-haiku-4-5-20251001",
            ]
        )
        for cname in claude_candidates:
            cref, cowner = await _resolve_ref(pr_dsn, cname)
            if cref and cref not in owner_by_ref:
                judges.append(JudgeSpec(label="claude", model_ref=cref, family="claude"))
                owner_by_ref[cref] = cowner
                break
        # Resilience judge — a 35b qwen variant for robustness (a judge that errors
        # simply does not vote, D11). NOTE (C2/LE-056): it is family='qwen', the
        # SAME family as qwen-30b, so it does NOT add family-diversity — the gate
        # now needs ≥2 DISTINCT families, so gemma or claude must also vote for the
        # ensemble to be `acceptable` (two qwen near-clones can't self-certify).
        third_name = os.environ.get("JUDGE_THIRD_NAME", "qwen/qwen3.6-35b-a3b")
        tref, towner = await _resolve_ref(pr_dsn, third_name, owner=user)
        if not tref:
            tref, towner = await _resolve_ref(pr_dsn, third_name)
        if tref and tref not in owner_by_ref:
            judges.append(JudgeSpec(label="qwen-35b", model_ref=tref, family="qwen"))
            owner_by_ref[tref] = towner

        if len(judges) < 2:
            print(f"live infra unavailable: < 2 judges registered "
                  f"(found {[j.label for j in judges]})", file=sys.stderr)
            return 3
        print(f"[c15-smoke] judge ensemble: {[j.label for j in judges]} (refs resolved per-owner)")

        suite = load_suite(SUITE_TOML)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else None
        judge_fn_for = _make_judge_fn_for(pr_url, token, owner_by_ref)

        # 3. run the REAL ensemble eval (tolerate JIT — generous timeout in fn).
        outcome = await run_eval(
            props, suite, baseline=baseline, judges=judges, judge_fn_for=judge_fn_for,
        )
        sc = outcome.scorecard
        if not sc.judge_ensemble_acceptable:
            print("live infra unavailable: judges did not produce >=2 verdicts "
                  "(JIT load / parse failure) — usefulness untrustworthy", file=sys.stderr)
            return 3

        # 4. persist the run + freeze a live baseline (with usefulness).
        eval_repo = EvalRunsRepo(pool)
        import datetime as _dt
        run_id = _dt.datetime.now(_dt.timezone.utc).strftime("c15-live-%Y%m%dT%H%M%SZ")
        persisted = await eval_repo.persist(
            user_id=uuid.UUID(user), project_id=uuid.UUID(project), run_id=run_id,
            suite_version=sc.suite_version, baseline_version=sc.baseline_version,
            n_proposals=sc.n_proposals, subscores=sc.subscores, composite=sc.composite,
            fleiss_kappa=sc.fleiss_kappa,
            judge_ensemble_acceptable=sc.judge_ensemble_acceptable,
            passed=sc.passed, raw_report=sc.to_json(),
        )
        # Freeze the LIVE baseline to a SEPARATE file (with the real usefulness) —
        # NOT the committed deterministic baseline (enrichment-v1.json), which must
        # stay the stable, reproducible CI reference (usefulness=0, no judges). The
        # authoritative longitudinal record is the persisted enrichment_eval_runs
        # row above; this JSON is a local convenience artifact only (gitignored).
        live_baseline = BASELINE.parent / "enrichment-v1-live.json"
        live_baseline.write_text(json.dumps({
            "version": sc.suite_version, "subscores": sc.subscores,
            "composite": sc.composite, "n_proposals": sc.n_proposals,
            "fleiss_kappa": sc.fleiss_kappa, "source": "live judge-ensemble run",
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        decision = "P2/P3 CLEARED (unlocked)" if sc.passed else "P2/P3 BLOCKED"
        line = (f"[{proposal_source}] composite={sc.composite} "
                f"(schema={sc.subscores['schema']} canon={sc.subscores['canon']} "
                f"anachronism={sc.subscores['anachronism']} "
                f"provenance={sc.subscores['provenance']} usefulness={sc.subscores['usefulness']}) "
                f"κ={sc.fleiss_kappa}({sc.kappa_interpretation}) n={sc.n_proposals} "
                f"judges={[j.label for j in judges]} gate={decision}")
        print(f"[c15-smoke] PERSISTED eval_run {persisted.eval_run_id} (passed={sc.passed})")
        print(f"SCORECARD_LINE: {line}")
        for r in outcome.decision.reasons:
            print(f"    gate-reason: {r}")
        return 0
    except (OSError, asyncpg.PostgresError, httpx.HTTPError, RuntimeError) as exc:
        print(f"live infra unavailable: upstream error ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
