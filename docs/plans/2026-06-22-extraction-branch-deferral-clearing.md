# Extraction-branch deferral clearing ("sạch nợ") — PLAN

Status: **PLAN — awaiting approval** · 2026-06-22 · branch `feat/extraction-knowledge-architecture`
Goal: clear the deferrals THIS branch created, so the extraction re-arch closes with no debt.
Scope: only branch-created deferrals (pre-existing/other-track ones are explicitly excluded).

## Already cleared this session (for the record)
`D-CACHE-REPLAY`, `D-RAWCACHE-MINIO-OFFLOAD`, keep-K retention, `D-CACHE-PLANNER-WIRING`
(Part 1+2), `D-SDK-DISTRIBUTION-SPLIT`, `D-MERGE-APPEND`, `D-MERGE-STRATEGY-ONTOLOGY`,
`D-MERGE-RESTORE-VERIFY`, `D-OBS-RECONCILE-SWEEP`, `D-OBS-BATCH-OUTCOME-PROJECTION`,
`D-PROV-EVIDENCE-INV6-REUSE`, `D-PROV-MODEL-OFFSET-HINT`, `D-EXTRACTION-FND-E2E-SMOKE`.

## The remaining branch-created deferrals — triage

| ID | Origin | Scope | Size | Verdict |
|---|---|---|---|---|
| **D-RE-EFFORT-COST-ESTIMATE** | RE lane | estimate doesn't grow with effort | **XS** | **CLEAR NOW** — planner Policy already has `reasoning_effort`; thread the clamped effort into `estimate_extraction_cost`'s `Policy`. |
| **D-CACHE-MODEL-KEY** | CACHE S1 | model not in cache key ⇒ a model switch reuses the prior parse | **S** | **CLEAR NOW** — `model_ref` is already on the row; add an opt-in force-refresh: on a hit, if the resolved model ≠ the cached row's model, skip the cache. Config-gated, default off (content-addressed stays the default). |
| **D-RE-WORKER-GRADED-EFFORT** | RE lane | worker still uses `thinking_enabled`→medium; low/high not honored | **M** | **CLEAR NOW** — thread the clamped `reasoning_effort` through `CreateExtractionJobPayload`→job row→worker→`reasoning_fields`; unify `thinking_llm_fields`. Mechanical but multi-file (payload + 1 job column + worker). |
| **D-EXTRACTION-ADMISSION-CONTROL** | FND /review-impl MED#2 | per-user job fan-out cap + per-book-lock pool pressure | **S (re-eval)** | **RE-EVALUATE** — P5 (`p5_owner_cap=5` WFQ) ALREADY caps in-flight LLM concurrency per owner. The remaining gap is only concurrent JOB count + advisory-lock pool pressure. Likely **close as "covered by P5"** with a 1-paragraph rationale, or a tiny per-user job-count guard if a real gap shows. |
| **D-RE-OTHER-AGENTIC-EFFORT** | RE lane | replicate the effort param+clamp to `glossary_deep_research` (Go) + other agentic MCP tools | **M-L (cross-service)** | **CLEAR (last)** — crosses into glossary-service Go + other MCP tools. Finishes the effort-control theme; do it after the translation-side effort work so the pattern is fully proven. |
| **D-EXTRACTION-REHOME-KNOWLEDGE** | CACHE design | move the cache physical store to knowledge-service | **XL (structural)** | **KEEP DEFERRED (conscious)** — the interface seam (`extraction_cache.py` get/put) was built EXACTLY so this is a later impl swap. The cache works in translation-service today; re-homing has no functional driver until knowledge-service owns extraction. Document as won't-fix-now; revisit when KG owns the pipeline. |
| **D-GLOSSARY-MULTIROW-ATTR-VALUES** | pre-existing (not this branch) | multi-row EAV for per-list-item provenance + append tombstones | **XL (structural)** | **KEEP DEFERRED** — pre-existing; the interim JSON-array append ships without per-item tombstones. Out of this branch's scope (a glossary-schema epic). |

## Recommended sequence (one coherent run, theme-ordered)

**Wave 1 — effort-control theme (translation side):**
1. `D-RE-EFFORT-COST-ESTIMATE` (XS) — thread effort into the estimate Policy. +1-2 tests.
2. `D-RE-WORKER-GRADED-EFFORT` (M) — graded effort end-to-end through the worker. +tests + a live check that low/high actually change the call.

**Wave 2 — cache correctness:**
3. `D-CACHE-MODEL-KEY` (S) — opt-in model-change cache-bust. +test (model-switch miss when the flag is on, hit when off).

**Wave 3 — admission control:**
4. `D-EXTRACTION-ADMISSION-CONTROL` — first a 30-min investigation: does P5 already cover it? If yes → close with rationale (no code). If a real job-count gap exists → a small per-user concurrent-job guard.

**Wave 4 — cross-service (own milestone):**
5. `D-RE-OTHER-AGENTIC-EFFORT` (M-L) — replicate param+clamp to glossary deep-research (Go) + other agentic MCP tools. Its own CLARIFY + live smoke (≥2 services).

**Conscious keep-deferred (write the won't-fix rationale, stop re-surfacing):**
- `D-EXTRACTION-REHOME-KNOWLEDGE`, `D-GLOSSARY-MULTIROW-ATTR-VALUES`.

## Outcome
After Waves 1-4, the only extraction-branch debt left is the two structural items, each with a
documented conscious-defer rationale — i.e. the branch is genuinely "sạch nợ": every quick/medium
item cleared, every remaining one a deliberate decision, not a forgotten TODO.

Net new work: ~3 small/medium BUILD increments (Waves 1-3) + 1 cross-service milestone (Wave 4)
+ 1 investigation. Each its own VERIFY + /review-impl + commit, per the standing gate.
