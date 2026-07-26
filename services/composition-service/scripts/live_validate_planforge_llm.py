"""D-PLANFORGE-PA-REALM-FALSE-POSITIVE audit harness — repeatedly run the REAL
production async LLM propose path (propose_spec_llm_async / ProviderPlanForgeLLM,
NOT the regex-only fixture-quality propose_spec) against the real
story-plan-v1.md fixture, and score the 8 PlanForge core rules
(validate.run_rules) against each run's output.

WHY THIS EXISTS: the original PlanForge POC + this session's Story Grid POC
addendum both only ever exercised the 7-8 core rules against (a) the
regex-only parser's output or (b) synthetic negative-test patches — NEVER
against real LLM output, across multiple runs. That gap let a real false
positive in `pa_not_realm` go unnoticed (see
docs/eval/plan-forge-story-grid-poc-2026-07-06.md addendum). A single live run
is not enough evidence either (the canon-check judge-eval lesson: one run can
be an optimistic or pessimistic draw) — this harness runs N times and reports
a stability count per rule, plus every observed PA-delta `reason` phrasing
that mentions realm/cảnh giới, to design (and verify) a real fix against
actual model phrasing variance, not a single anecdote.

PROVIDER RULE: resolves the model via provider-registry (BYOK `user_model`),
no direct SDK/provider call. The `MODEL_REF` constant below is a live-eval
harness default (same exception class as `run_canon_check_eval.py`'s hardcoded
eval model refs — provider-rule exceptions cover test fixtures / eval
harnesses, not runtime service code) — override with --model-ref.

Usage (run inside the composition-service container — needs the internal
provider-registry route):
    docker cp services/composition-service/scripts/live_validate_planforge_llm.py \\
        infra-composition-service-1:/app/scripts/live_validate_planforge_llm.py
    docker cp services/composition-service/tests/fixtures/plan-forge/story-plan-v1.md \\
        infra-composition-service-1:/app/tests/fixtures/plan-forge/story-plan-v1.md
    docker exec -w /app infra-composition-service-1 \\
        python scripts/live_validate_planforge_llm.py --runs 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.llm_client import LLMClient  # noqa: E402
from app.engine.plan_forge.compile import compile_artifacts  # noqa: E402
from app.engine.plan_forge.llm import ProviderPlanForgeLLM  # noqa: E402
from app.engine.plan_forge.propose_llm_async import propose_spec_llm_async  # noqa: E402
from app.engine.plan_forge.validate import run_rules  # noqa: E402
from loreweave_llm.client import Client as SDKClient  # noqa: E402

TEST_USER_ID = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"  # Gemma-4 26B-A4B QAT (200K), $0 local
GATEWAY_URL = "http://provider-registry-service:8085"
INTERNAL_TOKEN = "dev_internal_token"
FIXTURE = Path("tests/fixtures/plan-forge/story-plan-v1.md")


async def one_run(run_idx: int) -> dict:
    sdk = SDKClient(
        base_url=GATEWAY_URL, auth_mode="internal", internal_token=INTERNAL_TOKEN, user_id=None,
    )
    llm = LLMClient(sdk)
    client = ProviderPlanForgeLLM(
        llm,
        user_id=TEST_USER_ID,
        model_source="user_model",
        model_ref=MODEL_REF,
        usage_purpose=f"plan_forge_llm_validator_audit_run{run_idx}",
    )
    try:
        spec, _analyze, _io_log = await propose_spec_llm_async(
            FIXTURE.read_text(encoding="utf-8"), client,
        )
    finally:
        await sdk.aclose()

    compiled = compile_artifacts(spec, arc_id="arc_2")
    rules = run_rules(spec, compiled["planning_package"])

    pa_realm_reasons = [
        d.get("reason", "")
        for e in spec.get("events", [])
        if e.get("arc_id") == "arc_2"
        for d in e.get("var_deltas", [])
        if isinstance(d, dict) and d.get("variable") == "PA"
    ]

    return {
        "run": run_idx,
        "rules": {r["rule"]: r["pass"] for r in rules},
        "rule_details": {r["rule"]: r.get("detail", "") for r in rules},
        "pa_delta_reasons": pa_realm_reasons,
    }


async def main(n_runs: int) -> None:
    results = []
    for i in range(1, n_runs + 1):
        print(f"--- run {i}/{n_runs} ---", file=sys.stderr)
        results.append(await one_run(i))

    all_rules = sorted({rule for r in results for rule in r["rules"]})
    stability = {
        rule: sum(1 for r in results if r["rules"].get(rule)) for rule in all_rules
    }

    print(json.dumps({"runs": results, "stability": stability, "n_runs": n_runs}, ensure_ascii=False, indent=2))

    print("\n=== Rule stability across runs ===", file=sys.stderr)
    for rule, passed in stability.items():
        print(f"  {rule}: {passed}/{n_runs} PASS", file=sys.stderr)

    print("\n=== All observed PA-delta reasons mentioning cảnh giới/realm ===", file=sys.stderr)
    all_reasons = [r for run in results for r in run["pa_delta_reasons"]]
    for reason, count in Counter(all_reasons).most_common():
        flag = " <-- contains 'cảnh giới'" if "cảnh giới" in reason.lower() else ""
        print(f"  x{count}: {reason!r}{flag}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--model-ref", type=str, default=None, help="override BYOK user_model_id")
    args = parser.parse_args()
    if args.model_ref:
        MODEL_REF = args.model_ref
    asyncio.run(main(args.runs))
