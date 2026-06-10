# Review — Auto-Draft Factory: draft HTML vs current FE/BE coverage

**Date:** 2026-06-10 · **Branch:** feat/advanced-translation-pipeline
**Inputs:** `design-drafts/auto-draft-factory.html` (intended UX) vs `frontend/src/features/campaigns/**` + `services/campaign-service/**` (actual).
**Purpose:** before merging `main`, confirm whether the shipped Factory truly covers the draft, or has gaps. Companion docs: `docs/plans/2026-06-10-auto-draft-factory-gap-implementation-plan.md` (fixes) and `docs/specs/2026-06-10-auto-draft-factory-e2e-scenarios.md` (E2E).

## Verdict (TL;DR)
The **engine** (saga, gating, projection, dispatch, budget cap, estimate, model-matrix, monitor table, controls) is **fully implemented and largely matches the draft's data model**. The gaps are almost entirely in the **post-run / failure-recovery / monitor-richness UX surface** the draft depicts:

- 🔴 **Missing (in original PO scope):** completion **wake-up report**, user-triggered **re-run-failed** flow.
- 🟡 **Partial:** monitor lacks ETA / throughput / in-flight panel / live log / ingest row / heatmap; campaigns list lacks progress+ETA+quick-actions; paused state lacks the explicit "switch to local model" resume option; estimate lacks per-model token breakdown + cloud/local badges.
- ⚪ **Draft-vision beyond MVP (defer, not a bug):** 7-step wizard (Pipelines/Options/Policy-scheduling steps), optional 50-chapter sample run, sub-run (#41-r1) child campaigns, CSV export.

No engine/correctness gaps — the gaps are presentation + the two missing flows.

---

## Per-screen coverage

### 1. Campaigns List — 🟡 PARTIAL
| Draft shows | Actual | Status |
|---|---|---|
| Name + **lang pair (zh→vi)** + **Run #** | name only | 🟡 missing lang-pair + run-# |
| Scope (chapter count + **mode** e.g. "cold-start two_pass") | total chapters only | 🟡 missing mode display |
| Status badge | ✅ `StatusBadge` (all 7 statuses) | ✅ |
| **Progress bar + done/total + ETA** | none (chapters total only) | 🔴 missing in-list progress/ETA |
| Cost spent / budget | ✅ spent / budget | ✅ |
| Per-row **quick actions** (View / Resume / Re-run errors) | click-to-view only | 🟡 missing inline Resume/Re-run |
| BYOK multi-tenant banner | none | ⚪ cosmetic |

### 2. Setup Wizard — 🟡 PARTIAL (functionally complete, fewer steps)
| Draft (7 steps) | Actual (4 steps) | Status |
|---|---|---|
| 1 Scope (book/range/lang) | ✅ steps 1–2 (BookProject + ChapterRange) | ✅ |
| 2 **Pipelines** (pick which of 4) | hardcoded `[knowledge,translation,eval]` | ⚪ vision-extra (factory always runs all) |
| 3 **Options** (Balanced/two_pass presets) | none | ⚪ vision-extra |
| 4 Models — 6-role BYOK matrix incl. **compact** | ✅ ModelMatrix: extractor, translator (core) + verifier, eval_judge, embedding, reranker (advanced). **No `compact` role.** | 🟡 missing compact-model role (it's implicit in V3) |
| 5 Cost & Time — band + **per-model token in/out** + **cloud/local badges** + P10–P90 | ✅ estimate (cost range + time range + per-stage status table). **No per-model token columns, no cloud/local badges.** | 🟡 partial |
| └ optional **50-chapter sample run** | none | ⚪ vision-extra (sampling deferred; estimator is heuristic-only) |
| 6 **Policy (scheduling "run at night")** | launches immediately | ⚪ vision-extra (no scheduler) |
| 7 Confirm | ✅ Review step = confirm+launch | ✅ |
| gating mode selector | ✅ added (D-S5C-GATING, this session) | ✅ |
| budget cap field | ✅ | ✅ |

### 3. Live Monitor — 🟡 PARTIAL (data present, presentation thinner)
| Draft shows | Actual | Status |
|---|---|---|
| Pipeline progress **incl. Ingest** stage | StageProgress: knowledge/translation/eval (no ingest row) | 🟡 missing ingest row (ingest is a precondition, always 100%) |
| Per-stage done/total + **error count** | ✅ `X/Y done · Z failed` per stage | ✅ |
| Stat: spent / budget | ✅ SpentBudgetBar | ✅ |
| Stat: **elapsed + ETA** | none | 🔴 missing |
| Stat: **throughput (chapters/min)** | none | 🔴 missing |
| Stat: **parallel count** | none | 🔴 missing |
| **Per-chapter heatmap** (240 cells, paginated to 4000, click→detail) | `ChapterProjectionTable` (filtered, **max 200 rows**, columns) | 🟡 table not heatmap; **caps at 200 (no paging)** |
| **In-flight "processing" panel** (batch/verify/429-backoff state) | none | 🟡 missing |
| **Recent log** (timestamped events + quality scores) | none | 🟡 missing |
| Per-chapter fidelity/quality | ✅ `Fidelity` column (eval_fidelity_score) | ✅ |
| Pause / Cancel controls | ✅ MonitorControls | ✅ |

### 4. Paused (budget cap) — 🟡 PARTIAL
| Draft shows | Actual | Status |
|---|---|---|
| Graceful-pause explanation banner | error_message "budget cap reached" (no rich banner) | 🟡 thin |
| Stats (done / remaining / spent=cap / elapsed) | spent-budget bar (no done/remaining/elapsed split) | 🟡 partial |
| Resume option A: **raise cap & resume** | ✅ inline budget edit + Resume (over-budget guard) | ✅ |
| Resume option B: **switch to local model & resume** | none — models fixed at create | 🔴 missing (can't re-pick models on resume) |
| Resume option C: stop & review | = Cancel / leave paused | ✅ (implicit) |

### 5. Failed & Re-run — 🔴 LARGELY MISSING
| Draft shows | Actual | Status |
|---|---|---|
| Failed-chapters list | ✅ table filters failed + shows last_error | ✅ (view only) |
| **Error grouping by cause** (429 vs empty-body) | none | 🔴 missing |
| **Re-run selected / re-run all failed** (user-triggered) | none — no endpoint, no UI | 🔴 **missing** |
| **Sub-run / child campaign (#41-r1)** | none | ⚪ vision-extra |
| dead-letter (empty body → skip, no retry) | backend: retry-exhausted → `failed`/`skipped`; not surfaced as "dead-letter, don't retry" | 🟡 backend-only |
| Note: gating auto-re-dispatches `failed` within `max_attempts`, but once exhausted there is **no user re-run** path. | | |

### 6. Completion Report / Wake-up Report — 🔴 MISSING
| Draft shows | Actual | Status |
|---|---|---|
| Results grid (done / errors / spent-vs-estimate / glossary count) | none — completed campaign just shows the monitor (terminal) | 🔴 **missing** |
| Error grouping table | none | 🔴 missing |
| **Download CSV** | none | ⚪ vision-extra |
| **"Review draft"** CTA → flywheel | none | 🔴 missing (the draft→review handoff) |
| Re-run errors button | none | 🔴 (ties to re-run flow) |
| (Original PO scope explicitly listed a **"wake-up report"** — currently absent.) | | |

### 7. Cancelled state — ✅ COVERED (draft didn't depict; actual handles via StatusBadge + finalize).

---

## What's solid (no gap)
- Saga driver (stateless reconcile, claim-first, HA lease), gating (phase_barrier/cold_start), per-chapter projection, idempotent event consumption — match the draft's behavioral model.
- Budget cap accumulate + graceful auto-pause + dedup (S4d, live-verified) + over-budget resume guard.
- Estimate oracle (per-stage USD band + time band) — covers the draft's cost step intent (minus token-column detail).
- Full BYOK model matrix (6 roles) + destructive-embedding-change confirm.
- Pause / resume / cancel / update-budget endpoints + controls.
- Circuit-breaker → auto-pause; autonomous-publish (this session); kproject-ownership early-400 (this session).

## Gap classification summary
- **🔴 In-scope gaps to implement:** (G1) completion/wake-up report, (G2) user re-run-failed flow, (G3) monitor ETA/throughput/elapsed stats, (G4) "review draft" CTA.
- **🟡 Polish (recommended):** monitor in-flight panel + recent log + ingest row, chapter-table paging (>200), list progress/ETA/quick-actions, paused-state rich banner + done/remaining stats, estimate per-model token columns + cloud/local badges, paused "switch to local model" resume.
- **⚪ Vision-beyond-MVP (defer, track only):** Pipelines/Options/Policy(scheduling) wizard steps, 50-chapter sample run, sub-run child campaigns, CSV export, heatmap (table is the MVP substitute), compact-model role exposure.

→ Detailed fix plan: `docs/plans/2026-06-10-auto-draft-factory-gap-implementation-plan.md`.
