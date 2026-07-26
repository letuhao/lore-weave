# PlanForge POC Results

> **Date:** 2026-07-01 · **Fixture:** `scripts/plan-forge-poc/fixtures/story-plan-v1.md`

## Verdict

**PASS** — all success criteria S1–S8 met on golden fixture.

## Evidence

```bash
python scripts/plan-forge-poc/run_poc.py
# exit code 0
```

| ID | Result | Evidence |
|----|--------|----------|
| S1 | PASS | 7/7 sections ingested |
| S2 | PASS | PA, HA, CD, THR + transition rules |
| S3 | PASS | 6 consistency anchors |
| S4 | PASS | `arc_2.arc_kind = discovery` |
| S5 | PASS | 7 arc_2 events, notes link ratio 1.0 |
| S6 | PASS | premise 747 chars |
| S7 | PASS | glossary_seeds + planner_state JSON emitted |
| S8 | PASS | 3/3 negative test variants fire expected rules |

## Artifacts (generated)

- `scripts/plan-forge-poc/out/novel_system_spec.json` — primary deliverable
- `scripts/plan-forge-poc/out/plan_graph.json`
- `scripts/plan-forge-poc/out/compile/` — LW-ready seeds + `planning_package.json`
- `scripts/plan-forge-poc/out/arc_2_pipeline.json` — mock pipeline
- `scripts/plan-forge-poc/out/validation_report.md`

## Unit tests

```bash
pytest scripts/plan-forge-poc/test_plan_forge.py -q
```

## Recommendation

**Blueprint shipped** — implement in a separate session. Start at [`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md) (SSOT handoff). Promote detail: [`docs/plans/2026-07-01-plan-forge-promote.md`](../../plans/2026-07-01-plan-forge-promote.md).

1. Wire MCP tools (`plan_propose_spec`, `plan_validate`, fuzzy HIL) via ai-gateway — M4
2. ~~Add LLM propose path~~ — **done** — see [`03_LLM_POC_EVAL.md`](03_LLM_POC_EVAL.md)
3. Writing Studio planner dock with checkpoint UI — M5
4. Persist `plan_runs` + `planner_state` per `book_id` — M3

## LLM live run (2026-07-01)

**PASS** — `google/gemma-4-26b-a4b-qat` via direct LM Studio; golden S1–S8 on LLM spec.

```bash
python scripts/plan-forge-poc/run_poc_llm.py --compare-rules
# or: python scripts/plan-forge-poc/run_poc.py --llm --compare-rules
```

| ID | Result | Notes |
|----|--------|-------|
| L1–L3 | PASS | 2 LLM calls, ~41s, valid analyze + spec JSON |
| L4 | PASS | S1–S8 on `novel_system_spec.llm.json` (after link normalize) |
| L5 | PASS | Compare report — 100% arc_2 title overlap, 0% ID overlap |

Artifacts: `out/plan_analyze.json`, `out/novel_system_spec.llm.json`, `out/llm_io/`, `out/validation_report.llm.md`, `out/llm_vs_rules_report.md`.

Full evaluation: [`03_LLM_POC_EVAL.md`](03_LLM_POC_EVAL.md).

## POST-POC evaluation (2026-07-01)

**GO — Promote engine pattern** ([`04_PO_REVIEW.md`](04_PO_REVIEW.md))

| Phase | Result |
|-------|--------|
| A Automated reverify | PASS — rules + LLM S1–S8, A5 notes_linked 1.00 without manual fix |
| B Semantic rubric | avg **4.67** (min 4) — B3/B6: intermittent drop of Event 3 Thử Nghiệm |
| C Stress | 3/3 stability linter pass; 2/3 full golden; braindump smoke 7/7 events |
| D Decision | **GO** → [`docs/plans/2026-07-01-plan-forge-promote.md`](../../plans/2026-07-01-plan-forge-promote.md) |

## HIL refine POC (2026-07-01)

**PASS** — scripted human-in-the-loop via [`run_poc_hil.py`](../../../scripts/plan-forge-poc/run_poc_hil.py).

| Metric | Result |
|--------|--------|
| Thử Nghiệm | Present — analyze refine 6→7 events |
| Golden | S1–S8 PASS on `novel_system_spec.hil.json` |
| Accept gate | Both refine rounds accepted, no regression |

Full evaluation: [`05_HIL_POC_EVAL.md`](05_HIL_POC_EVAL.md).

## Limitations (POC scope)

- **Rules path:** deterministic header/regex propose — sufficient for fixture TOC
- **LLM path:** direct LM Studio (not provider-registry); string `planner_notes` need normalize pass
- No DB persist / glossary API calls
- Single arc compile (`arc_2`) only

## Eval index (POC complete)

| Doc | Topic |
|-----|-------|
| [`03_LLM_POC_EVAL.md`](03_LLM_POC_EVAL.md) | LLM path |
| [`04_PO_REVIEW.md`](04_PO_REVIEW.md) | GO decision |
| [`05_HIL_POC_EVAL.md`](05_HIL_POC_EVAL.md) | Scripted HIL |
| [`06_FIDELITY_POC_EVAL.md`](06_FIDELITY_POC_EVAL.md) | Fidelity gate |
| [`07_ELABORATION_POC_EVAL.md`](07_ELABORATION_POC_EVAL.md) | Elaboration |
| [`08_CHAT_HIL_POC_EVAL.md`](08_CHAT_HIL_POC_EVAL.md) | Fuzzy chat HIL |
| **[`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md)** | **Implement handoff SSOT** |
