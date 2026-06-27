# Plan — Bug #37: Job GUI shows LLM calls (done / estimated total)

**Scope (user-confirmed):** all 3 producers that already compute a call estimate —
glossary **extraction**, glossary **translation**, **KG-build** (worker-ai). translation-chapter
& composition have no clean upfront estimate → out of scope (no defer row; they can adopt the
same two params keys later if an estimate is added).

## Contract (no schema change — uses the existing whitelisted `params` JSONB)
- `params.estimated_llm_calls: int` — total estimated LLM calls, set on the **pending** create event.
- `params.llm_calls_done: int` — calls completed so far, updated on each **running** progress event.

Both are null-safe: the FE shows the row only when `estimated_llm_calls` is present; `llm_calls_done`
defaults to 0 until the first progress emit.

## FE (generic — one render, all producers benefit)
1. `JobProgressPanel.tsx` — add an "LLM calls: {done} / {total}" stat from `job.params`.
2. `JobParametersPanel.tsx` — exclude the two call-count keys from the raw params grid (shown in Progress instead).
3. i18n `jobs.json` ×4 locales — `detail.llmCalls` label.
4. Tests: `JobDetailPanels.test.tsx` — renders calls when present, hidden when absent.

## BE per-producer (each: +estimate at create, +running counter in worker)
1. **Extraction** (`routers/extraction.py` create + `workers/extraction_worker.py`):
   - create: `job_params["estimated_llm_calls"] = cost_estimate["llm_calls"]`.
   - worker: `_process_extraction_chapter` returns `llm_calls` (= realized window×batch outcomes);
     accumulate `total_llm_calls`; `_emit_unified_progress` emits `params={"llm_calls_done": total_llm_calls}`.
2. **Glossary-translate** (`routers/glossary_translate.py` create + `workers/glossary_translate_worker.py`):
   - estimate `llm_calls = max(entity_count, 1)`; counter = entities translated.
3. **KG-build** (knowledge-service create + worker-ai decoupled consumer): DONE — second commit.
   - **Decoupled** is the production default (`EXTRACTION_DECOUPLE_ENABLED=true`): LLM calls are
     fire-and-forget `submit_job` fan-outs across terminal events, so inline counting is impossible.
   - New `extraction_jobs.llm_calls_made` column (migration); incremented at the submit chokepoints —
     +1 at the inline entity submit (`runner._start_decoupled_chunk`) and +len at the consumer's
     `_submit_map` fan-out (trio/recovery/filter), on the locked conn (no deadlock).
   - `llm_extract_consumer._emit_kg_progress` emits unified progress at the per-chunk finalize —
     `params.llm_calls_done` (the column) + `estimated_llm_calls` (items_total × [1 + requested trio]);
     ALSO fixes KG-build's previously-frozen progress bar (worker-ai emitted only the terminal event).
   - knowledge-service create also sets the estimate upfront when items_total is known at create.
   - Inline path (decouple OFF, non-default fallback) is intentionally not counted — documented.

## Verify
- Unit: producer emit carries `estimated_llm_calls`/`llm_calls_done`; FE render tests.
- Live-smoke: one extraction job on the real stack → Job detail shows "N / M calls" advancing.
