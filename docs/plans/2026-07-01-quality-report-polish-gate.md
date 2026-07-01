# Plan — Quality Report in the Polish gate (Q1 + Q2)

**Track:** "The planner exploits its own judges." Today the composition auto-loop runs several
quality judges (`critic`, `canon_reflect`, `narrative_thread`, `motif_conformance`) but their
output is stashed in `job.result["_critic"]` and never surfaced; and `promise_audit` (does the
draft pay off what it set up?) is never invoked at all. This milestone surfaces the planner's
quality judgment to the author as a **read-only Quality Report inside the existing Polish gate**.

**Size:** L (full-stack: new engine orchestrator + worker op + REST endpoint + FE section + i18n).
**Mode:** default v2.2 human-in-loop. PO checkpoint at POST-REVIEW.

---

## Design decisions (locked before build)

1. **Diagnostic, never applyable.** `promise_audit` returns short phrases, not located spans, and
   `critic` returns scores — neither is a splice-able `before→after` edit. So the Quality Report is
   **read-only** (no checkbox, no Apply). It is a *sibling* of the self-heal EditProposals, not a new
   kind of proposal. This preserves the do-no-harm invariant: the report informs, the author acts.

2. **Two engines, fresh, chapter-scoped, concurrent, degrade-safe.**
   - `critic.judge_prose(chapter_text)` → `{coherence, voice_match, pacing, canon_consistency,
     violations[]}` — covers 3 of the 4 requested categories (critic + its canon dim + violations).
   - `promise_audit.audit_promises(chapter_text)` → `{introduced, resolved, dropped, dropped_rate}`
     — the missing "plant-but-never-pay" signal, scoped to the chapter.
   - Run both with `asyncio.gather`; either failing degrades to its empty shape + `error` (mirrors
     every other advisory engine — never raises into the op).
   - **Q2 = re-run fresh, not scrape historical `_critic`.** Reading per-scene `_critic` off old job
     rows is stale after edits/stitch; one chapter-level critic pass is correct and cheap (local
     model = $0). Documented as the deliberate choice.

3. **Separate action from self-heal.** The report is its own button ("Analyze quality") with its own
   LLM cost, not folded into "Run Polish". Critic needs a judge model; keeping them separate lets the
   author run edits and analysis independently and makes the extra cost explicit (re-ranker precedent).

4. **`motif_conformance` beat-not-realized rollup is DEFERRED** — it needs per-outline-node motif
   bindings aggregated across scenes (heavier, per-scene data). Tracked as `D-QUALITY-MOTIF-ROLLUP`;
   not required for a coherent first surface. critic's `canon_consistency` + explicit `canon` grounding
   already give the author a canon signal.

5. **New engine module `quality_report.py`** (thin orchestrator) rather than inlining in the worker op
   — keeps the op a resolver and makes the orchestration unit-testable without a worker.

---

## BUILD steps

### BE
- **`app/engine/quality_report.py`** (new) — `async build_quality_report(llm, *, user_id,
  model_source, model_ref, chapter, source_language, profile_dims?, canon=None, trace_id, cancel_check)
  -> dict`. Runs `judge_prose` + `audit_promises` concurrently, shapes
  `{critic: {...}|None, promises: {...}, generated_at fields omitted}`; each side degrade-safe.
- **`app/worker/operations.py`** — `run_quality_report(llm, *, user_id, input, cancel_check)` mirroring
  `run_self_heal_propose`: reads `chapter_text`/`canon`/`source_language`/`model_*`, calls the engine,
  returns `{report, chapter_id, draft_version}`. Add to `__all__`.
- **`app/worker/constants.py`** — add `"quality_report"` to `SUPPORTED_OPERATIONS`.
- **`app/worker/job_consumer.py`** — dispatch `if op == "quality_report": return await
  run_quality_report(...)` (mirror self_heal_propose branch; import at top).
- **`app/routers/plan.py`** — `QualityReportRequest(chapter_id, model_source, model_ref, canon?)`
  + `POST /works/{project_id}/quality-report` mirroring `self_heal_propose_endpoint` (resolve draft
  text via `tiptap_doc_to_text`, canon override-else-render, worker-enqueue-or-inline).

### FE
- **`features/composition/api.ts`** — `QualityReport` + `QualityReportResponse` types;
  `compositionApi.qualityReport(projectId, {chapterId, modelRef, modelSource?}, token)` reusing the same
  202-poll path as `proposeSelfHeal`.
- **`features/composition/hooks/useQualityReport.ts`** (new) — owns `{report, loading, error, ran, run}`.
- **`features/composition/components/QualityReportSection.tsx`** (new) — read-only render: 4 critic
  dim scores, violations list, promises (introduced / resolved / dropped) with the dropped ones
  highlighted. Own "Analyze quality" button. Keeps PolishPanel small.
- **`PolishPanel.tsx`** — mount `<QualityReportSection>` below the edits (same `key={chapterId}`
  remount already on the parent).
- **i18n** `locales/{en,vi,zh,ja}/composition.json` (×4) — new keys (defaultValue inline as elsewhere,
  add keys to en at minimum + mirror).

### Tests (TDD)
- `tests/unit/test_quality_report.py` (new) — engine: both-ok shape; critic-degrade → `critic:None`
  + report still returns; promise-degrade → empty promises + error; concurrent both-degrade.
- extend `tests/unit/test_worker_jobs.py` — `run_quality_report` returns report + passthrough ids;
  dispatch recognizes the op (no `UnsupportedOperationError`).
- FE: `QualityReportSection.test.tsx` — renders scores + dropped promises; empty/degraded states.

---

## VERIFY
- `pytest services/composition-service/tests/unit/test_quality_report.py test_worker_jobs.py -q`
- full composition suite green
- `cd frontend && npm run build` + `npm test` (composition feature)
- **live smoke** (≥2 services: composition + provider-registry via the LLM gateway): run the
  quality-report endpoint against a real CH1 draft with the test account's local model; confirm a
  populated critic block + a promises block. Token: `live smoke: quality-report CH1 <one-liner>`.

## REVIEW (2-stage) → POST-REVIEW (present + WAIT) → SESSION → COMMIT

## Deferred created
- `D-QUALITY-MOTIF-ROLLUP` — surface `motif_conformance` beat-not-realized per chapter (needs
  per-node bindings aggregation). Gate #2 (structural). Target: Q-follow-on.
- `D-QUALITY-ARC-LEVEL` — arc/book-level promise coverage (v2 `score_promise_coverage` vs the
  premise+plan tracked set) as a story-level report. Gate #1/#2. Target: Q3.
