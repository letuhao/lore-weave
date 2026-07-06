# Context Budget quality-gate harness

Judge-driven, non-strict LLM-quality gate for the Context Budget effort. Proves the
chat agent still *answers well* on less context — a question a unit test can't
settle. Methodology: [`docs/specs/context-budget-quality-gate.md`](../../docs/specs/context-budget-quality-gate.md).

**Model under test (LOCKED):** local `google/gemma-4-26b-a4b-qat` (LM Studio), via a
chat+tool_calling `user_model` (default `019ebb72-…`, "Gemma-4 26B-A4B QAT 200K"). Never gpt-4o.

## Pieces
| File | Role |
|---|---|
| `context_budget_scenarios.json` | the scenario set (tags: no_lore_smalltalk, status_op, lore_recall, continuity, cross_chapter). `needs_lore=false` set is the mechanical driver-smoke; `needs_lore=true` needs a lore-bound session. |
| `run_quality_gate.py` | the DRIVER — drives the real chat agent per scenario, records reply + persisted `contextBudget` (token cost) + tools per turn → `transcript.jsonl`. Runs in-container. |
| `judge_prompt.md` | the BLIND judge prompt template (cold-start Agent scores RUN_A/RUN_B without knowing which is baseline). |

## The loop
```
baseline (pre-change)  ┐
                       ├─▶ driver → transcript.jsonl (×2 runs)
candidate (post-change)┘        │
                                ▼   judge Agent scores each scenario BLIND (rubric)
                                ▼   orchestrator writes docs/eval/context-budget/<tier>-<run>.md
                        decide: PASS ▸ continue · REGRESS ▸ fix+re-run · NEEDS-HUMAN ▸ defer+continue
```

## Run (in-container — the proven `smoke_compose_generate_live.py` pattern)
```bash
# 1. copy driver + scenarios in (MSYS_NO_PATHCONV=1 on Git Bash to keep /tmp paths)
docker cp scripts/eval/run_quality_gate.py           infra-chat-service-1:/tmp/qg.py
docker cp scripts/eval/context_budget_scenarios.json infra-chat-service-1:/tmp/scen.json

# 2. baseline run (bind a lore-populated book+KG for the needs_lore scenarios)
MSYS_NO_PATHCONV=1 docker exec \
  -e QG_RUN_LABEL=baseline -e QG_MODEL_REF=019ebb72-27a2-72f3-a42d-d2d0e0ded179 \
  -e QG_PROJECT_ID=<book_id> -e QG_KG_PROJECT=<kg_project_id> \
  -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/qg-out \
  infra-chat-service-1 python /tmp/qg.py

# 3. build the candidate tier (e.g. T5), then re-run with QG_RUN_LABEL=candidate
# 4. pull transcripts, dispatch judge_prompt.md per scenario (blind), write the report
docker cp infra-chat-service-1:/tmp/qg-out ./docs/eval/context-budget/runs/
```

**Mechanical smoke** (no lore needed — proves the driver drives the agent + captures tokens):
```bash
MSYS_NO_PATHCONV=1 docker exec -e QG_RUN_LABEL=smoke \
  -e QG_ONLY=smalltalk_capabilities,status_set_drafting \
  -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/qg-out \
  infra-chat-service-1 python /tmp/qg.py
# proven 2026-07-04: 2 turns, replies captured, budget=28340/28352 tok, 0 confabulation risk (no-lore).
```

## Decision policy (orchestrator)
- **PASS** ⟺ candidate mean(correctness, groundedness, continuity) ≥ baseline − 0.3 AND zero new
  `critical_confabulation=true` AND tokens ↓.
- **REGRESS** ⟺ a dimension drops > 0.3 or a new critical confabulation → fix the tier, re-run.
- **NEEDS-HUMAN** ⟺ ambiguity the ground truth can't settle → DEFER row + continue (never hard-block).

## When each tier runs it
T5 (grounding gate — first real risk), T6 (compaction — 40-turn fact retention), FINAL (standing
acceptance). T0–T4 are byte/behavior-preserving → unit + live-e2e suffice, no judge.
