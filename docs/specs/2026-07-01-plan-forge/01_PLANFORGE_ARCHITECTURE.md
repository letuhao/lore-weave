# PlanForge Architecture

> **Date:** 2026-07-01 · **Status:** BLUEPRINT SHIPPED · **Implement SSOT:** [`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md) · **POC:** `scripts/plan-forge-poc/`

## Overview

PlanForge reads natural-language planning documents, **proposes** a typed `NovelSystemSpec`, decomposes with human checkpoints, compiles to LoreWeave platform artifacts, and bridges to `composition-service` `run_planning_pipeline`.

```
NL markdown → PlanDocument → NovelSystemSpec → PlanGraph → CompileTargets → PlanningPackage → pipeline
```

## Contracts

| Schema | Path | Role |
|--------|------|------|
| `PlanDocument` | [`plan_document.schema.json`](../../../contracts/plan-forge/plan_document.schema.json) | Parsed source + section spans |
| `NovelSystemSpec` | [`novel_system_spec.schema.json`](../../../contracts/plan-forge/novel_system_spec.schema.json) | Proposed system design (primary) |
| `PlannerState` | [`planner_state.schema.json`](../../../contracts/plan-forge/planner_state.schema.json) | PA/HA/CD/THR runtime |
| `PlanningPackage` | [`planning_package.schema.json`](../../../contracts/plan-forge/planning_package.schema.json) | Arc input for composition pipeline |
| `PlanRevisionRequest` | [`plan_revision.schema.json`](../../../contracts/plan-forge/plan_revision.schema.json) | Surgical HIL edit |
| `FeedbackInterpretation` | [`feedback_interpretation.schema.json`](../../../contracts/plan-forge/feedback_interpretation.schema.json) | Vague user message → scoped revision |

## Workflow phases

| Phase | Engine | Checkpoint |
|-------|--------|------------|
| 0 Ingest | Rules parser | — |
| 1 Propose | Rules + optional LLM | Blocking: approve spec |
| 2 Decompose | Graph builder | Blocking: per-layer |
| 3 Link | Traceability | Blocking: missing links |
| 4 PlanParts | Package compiler + pipeline | Blocking per arc |
| 5 Integrate | Cross-arc threading | Advisory |
| 6 Validate | Golden linter | Fail → loop |
| 7 Commit | Glossary + outline persist | Blocking |

## Platform compile map

| Spec field | LW artifact | Service |
|------------|-------------|---------|
| `layers.characters[]` | Glossary entity seeds | glossary-service |
| `layers.mechanics[]` | Wiki stubs + entity kinds | glossary-service |
| `charter.*` | `working_memory.charter` | knowledge-service |
| `planner_state_init` | `plan_runs.state` (future) / session | composition-service |
| `outline_skeleton[]` | `outline_node` tree | composition-service |
| `PlanningPackage` | `DecomposeRequest` + chapters | composition-service |

## Checkpoint protocol

- **Blocking gates:** after propose, after event extract, after per-arc package, before commit.
- **Edit-merge:** user edits JSON at checkpoint; re-run downstream phases only.
- **POC CLI:** `--approve-all` for CI; `--interactive` prompts y/n per gate.

## Fuzzy HIL + chat orchestration (POC validated)

Users paste plans into chat and give **vague** feedback (*"sai chỗ này"*, *"check lại"*, *"làm đi"*). Pattern mirrors glossary assistant: **chat orchestrates**, planner owns SSOT.

```
Chat message → interpret_feedback → apply_policy (confirm | auto | handoff)
  → refine_spec → accept_refine + fidelity gate → short chat summary
```

Anti-noise rules:

- SSOT = persisted `NovelSystemSpec` (`run_id` / file path) — no re-ingest of 22k markdown each turn
- `plan_self_check` supplies gaps for *"check lại"* without user pointing fields
- `spec_index` + section excerpts bound interpret/refine working set
- Chat history not injected into refine prompts (only last summary ~200 chars)

POC: [`run_poc_chat_hil.py`](../../../scripts/plan-forge-poc/run_poc_chat_hil.py) · Eval: [`08_CHAT_HIL_POC_EVAL.md`](08_CHAT_HIL_POC_EVAL.md)

## Validation rules (novel-spec linter)

| Rule ID | Check |
|---------|-------|
| `vars_four` | Exactly PA, HA, CD, THR defined |
| `pa_not_realm` | No `coupled_to_realm` on var deltas |
| `arc2_discovery` | Arc 2 `arc_kind` = `discovery` |
| `anchors_min` | ≥4 consistency anchors |
| `thr_no_early_explain` | No event synopsis explains THR origin in arc ≤2 |
| `open_questions_preserved` | All §7 items in `meta.open_questions` |
| `premise_max` | PlanningPackage.premise ≤4000 chars |
| `notes_linked` | ≥80% planner notes have graph edges |

## MCP tools (post-POC sketch)

| Tool | Phase |
|------|-------|
| `plan_propose_spec` | 1 |
| `plan_review_checkpoint` | 1–3 |
| `plan_self_check` | HIL |
| `plan_interpret_feedback` | HIL |
| `plan_apply_revision` | HIL |
| `plan_handoff_autofix` | HIL |
| `plan_compile` | 4 |
| `plan_validate` | 6 |

Owned by composition-service; federated via ai-gateway.

## POC success criteria

| ID | Criterion | Threshold |
|----|-----------|-----------|
| S1 | Ingest 7 top sections | 7/7 classified |
| S2 | 4 variables + transition rules | Match §4 semantics |
| S3 | Consistency anchors | ≥4 from §1 |
| S4 | Arc 2 discovery-not-power | `arc_kind=discovery` |
| S5 | Arc 2 events + links | ≥5 events, ≥80% notes linked |
| S6 | Premise ≤4000 | Readable arc theme |
| S7 | Compile artifacts schema-valid | glossary + planner_state |
| S8 | Negative tests | ≥3 rule types fire |

Golden file: [`scripts/plan-forge-poc/fixtures/story-plan-v1.expectations.yaml`](../../../scripts/plan-forge-poc/fixtures/story-plan-v1.expectations.yaml).

## References

- **[`09_PLANFORGE_BLUEPRINT.md`](09_PLANFORGE_BLUEPRINT.md)** — implement handoff SSOT
- [`00_MARKET_AND_GAP.md`](00_MARKET_AND_GAP.md)
- [`2026-06-30-planning-pipeline-architecture.md`](../2026-06-30-planning-pipeline-architecture.md)
- [`2026-06-23-interview-roleplay.md`](../2026-06-23-interview-roleplay.md)
