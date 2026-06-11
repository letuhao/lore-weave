# Phase 2b — worker-ai extraction decouple (DESIGN)

Status: **DESIGN** (build not started). Hardest of the Phase 2b decouples; the
`/warp` TRIAGE explicitly routed it to serial because it touches the **shared**
`loreweave_extraction` SDK (knowledge-service imports the same `extract_pass2`).

Companion to [`2026-06-11-llm-rearch-phase2b-decouple-design.md`](2026-06-11-llm-rearch-phase2b-decouple-design.md)
(translation, T1/T2/T3a shipped) and the spec
[`docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md`](../specs/2026-06-11-llm-execution-event-driven-rearchitecture.md).

## Why this is the hard one

Translation decoupled cleanly because its hot loop is a **linear chain** (chunk N →
chunk N+1; one LLM call per step) that could be reimplemented OUTSIDE the existing
function (`decoupled_translate.py` / `decoupled_block_translate.py`), reusing only
pure helpers. Extraction is **not linear**:

`loreweave_extraction.pass2.extract_pass2` ([pass2.py:79](../../sdks/python/loreweave_extraction/pass2.py)) per chunk:

```
1. extract_entities(text)                              ── 1 LLM call (GATING: no entities → stop)
2. asyncio.gather(                                     ── 3 CONCURRENT LLM calls
     extract_relations, extract_events, extract_facts)
3. recover_missing_entities()        [optional]        ── 1+ LLM call
4. apply_precision_filter()          [optional]        ── 1+ LLM call (per-item, can fan out)
```

Each extractor (`extractors/{entity,relation,event,fact,summarize}.py`,
`entity_recovery.py`, `pass2_filter.py`) calls `llm_client.submit_and_wait` at its
**own** site (**7+ blocking seams**), with op-specific prompt-build + parse
**interleaved** around the call. worker-ai's `runner.py` then loops `extract_pass2`
over **chunks** (and there's a summarize pipeline beyond pass2).

Three structural problems translation didn't have:

1. **Concurrent fan-in.** Step 2 submits 3 jobs at once and must wait for **all
   three** terminal events before step 3. The resume_state must track ≥3 in-flight
   `provider_job_id`s and fold each as its event lands, advancing only when the set
   is complete. (Translation only ever had ONE job in flight.)
2. **Dependency DAG, not a chain.** entity → trio → recovery → filter, with gates
   (no entities → stop; recovery/filter optional). The state machine is a small DAG.
3. **Shared SDK blast radius.** `extract_pass2` is imported by BOTH worker-ai and
   knowledge-service. The build/parse logic to decouple lives inside the SDK's
   extractors; exposing it as pure seams is a refactor that touches knowledge's path
   too (must stay byte-identical when the flag is off).

## Schema reality (vs translation)

Translation already had `chapter_translations` + `chapter_translation_chunks` + the
added `resume_state`. Extraction state lives in `extraction_jobs` (worker-ai/knowledge)
and there is **no per-chunk persistence table** and **no `resume_state` column**. So
2b-worker-ai-T1 is an additive migration: `extraction_jobs += provider_job_ids JSONB`
(the in-flight set for the fan-in) `+ resume_state JSONB + pipeline_stage TEXT`.

## Recommended slicing (each its own loom cycle)

- **WX-T1 (additive scaffolding, S):** migration above + a feature flag
  `extraction_decouple_enabled` (default off). Hot path untouched. Mirrors 2b-T1.
- **WX-T2 (SDK seam refactor, M — the unlock):** in `loreweave_extraction`, split each
  extractor into pure `build_<op>_messages(...)` + `parse_<op>_response(...)` with the
  existing `submit_and_wait` call sandwiched between them — **no behavior change**, the
  sync `extract_pass2` calls build→submit_and_wait→parse exactly as today (verified by
  the existing knowledge + worker-ai suites staying green). This is the prerequisite
  that lets a decoupled orchestrator reuse the SDK's prompt/parse without reimplementing
  per-op logic. **Do NOT add resume logic to the SDK** — keep it a pure library.
- **WX-T3 (decoupled orchestrator in worker-ai, L):** a `decoupled_extract.py` state
  machine + `extraction_jobs.resume_state`:
  - `awaiting` ∈ {`entity`, `trio`, `recovery`, `filter`}; the `trio` stage stores a
    `{op: provider_job_id}` map + a `{op: result}` accumulator and only advances when
    all three have folded (the fan-in). chunk cursor for the outer loop.
  - submit via `llm_client.submit_job` (the fire-and-forget wrapper); the worker-ai
    `llm_job_terminal` consumer (new, model on translation's `llm_terminal_consumer`)
    looks up the job by `provider_job_id` across the in-flight set, folds, and submits
    the next stage / chunk, or finalizes (the existing pass2 persist + the
    `knowledge.chapter_extracted` completion event in the same tx — finalize-FIRST then
    clear, idempotent on a status guard, exactly like translation's `_finalize_chapter`).
  - Billing: the E0-3 Phase-2a `set_billing_user_id` contextvar + dual-identity refs
    must be re-bound in the consumer before each resumed submit (as translation re-binds
    `set_campaign_id`).
- **WX-T4 (knowledge-service, optional):** knowledge calls `extract_pass2` synchronously
  on its own start path. If its latency profile wants the decouple too, it reuses WX-T2's
  seams + a parallel decoupled orchestrator. Likely deferred — knowledge extraction is
  user-triggered, not the campaign batch that caused the incident.

## Decision: does this even need doing now?

**Phase 1 already fixed the incident.** The durable queue + per-kind semaphore means
extraction's concurrent ops **WAIT** in the queue instead of failing `acquire timeout`,
and DELETE frees the GPU slot in one tick (live-proven, `D-PHASE1-QUEUE-LIVE-SMOKE`).
So the worker-coroutine-pinning that 2b removes is now an **optimization** (frees a
worker slot during a long extraction), not the Critical incident fix. Given the cost
(shared-SDK refactor + a fan-in state machine + a new consumer + billing re-bind, across
2 services), weigh WX vs Phase 3 vs other backlog. If pursued, **WX-T2 (the pure-seam
refactor) is the safe, valuable first step** even on its own — it improves SDK testability
regardless of the decouple.

## WX-T2b + WX-T3 BUILD PLAN (PO chose the full event-driven scope, 2026-06-11)

### WX-T2b — seam recovery + filter (byte-identical, mirrors WX-T2)

Both use `operation="chat"` via a `_call_*_llm` helper (submit_and_wait → `messages[0].content`).
The seams differ from the 4 simple extractors because each wraps candidate-analysis +
verdict-application around the call:

- `entity_recovery.py`: ONE classifier call. Seam → `build_recovery_submit_kwargs(system,user,config,n_items)` (the `_call_classifier_llm` body sans submit) + `parse_recovery_content(content)→verdicts`. The public `recover_missing_entities` keeps the candidate→prompt build + verdict→apply; it calls build→submit_and_wait→parse.
- `pass2_filter.py`: N **sequential** per-batch calls. Seam → `build_filter_submit_kwargs(system,user,config,n_items)` + `parse_filter_content(content)→verdicts` per batch. `apply_precision_filter` keeps the batch loop + apply.

Verify: SDK extraction suite + worker-ai 179 + knowledge extraction units stay green (the 3 `summarize_level` fails stay pre-existing).

### WX-T3 — the resume_state state machine (per chunk)

`extraction_jobs.resume_state` (mode='extract'):
```
chunk_text, known_entities, model_ref, billing_*, project_id, source_{type,id}, persist-ctx…
stage:        "entity" | "trio" | "recovery" | "filter" | "persist"
entities/relations/events/facts: accumulators (folded as each stage completes)
trio_jobs:    {op: provider_job_id}    — the fan-in set; advance only when all 3 folded
trio_done:    {op: result}
filter_batches: [...] ; filter_idx ; (filter is a sub-loop like block-translate batches)
```
`extraction_jobs.provider_job_ids` (WX-T1) = the live set (≥3 during `trio`); the consumer
looks a terminal event's job_id up across it.

Stage transitions (consumer `resume`, per terminal event):
- `entity` done → if no entities: persist-empty + advance chunk; else submit the trio (3 `submit_job`), stage=`trio`, persist all 3 in `trio_jobs`+`provider_job_ids`.
- `trio`: fold the one op whose job fired; when `trio_jobs` all folded → stage=`recovery` (if configured) else `filter` (if configured) else `persist`.
- `recovery` done → apply verdicts → stage=`filter`|`persist`.
- `filter`: fold batch, submit next batch or (last) → stage=`persist`.
- `persist` → POST `/internal/extraction/persist-pass2` (finalize-first idempotent) → advance the chunk cursor / emit `knowledge.chapter_extracted` → submit the next chunk's `entity` or complete the job.

**Runner integration (the heavy part).** Today `runner._extract_and_persist` blocks then the loop does spend/cursor/`chapter_extracted`. Decoupled: the runner submits chunk-0 `entity` + releases; the **consumer** owns persist + `_record_spending` + `_advance_cursor` + the completion event (reusing the runner's existing helpers). `set_billing_user_id` re-bound in the consumer before each resumed submit.

**Consumer** = worker-ai `llm_terminal_consumer` (model on translation's; worker-ai already runs a Redis-stream `summary_consumer` → same shape). Idempotency: persist + cursor-advance finalize-first under a status/cursor guard (a chunk already advanced → ack+ignore).

### Slices (each a checkpoint)
- **WX-T2b** — recovery + filter seams (this commit). ← BUILD START
- **WX-T3a** — `decoupled_extract.py` PURE state machine (stage transitions + trio fan-in + filter sub-loop) + unit tests. No runner wiring.
- **WX-T3b** — the worker-ai consumer + runner release-branch + persist/spend/cursor/event ownership + billing re-bind, behind the flag.
- **WX-T3c** — `D-WX-LIVE-SMOKE` (real extraction chunk through the event path).

## Reuse map

| Need | Asset |
|---|---|
| terminal-event consumer | translation `app/events/llm_terminal_consumer.py` (model) |
| idempotent finalize | translation `_finalize_chapter` status-guard pattern |
| fire-and-forget submit | `LLMClient.submit_job` (add to worker-ai's wrapper, attribution-preserving) |
| billing re-bind on resume | E0-3 P2a `set_billing_user_id` contextvar |
| resume_state crash-safety | finalize-FIRST then clear (translation `decoupled_*translate.resume`) |
