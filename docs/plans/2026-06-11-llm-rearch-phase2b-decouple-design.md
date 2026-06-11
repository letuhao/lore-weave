# Phase 2b — full event-driven decouple (submit→persist→separate-consumer→resume)

**Date:** 2026-06-11 · **Size:** XL, multi-session · **Spec:** [`docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md`](../specs/2026-06-11-llm-execution-event-driven-rearchitecture.md) §6 rows 4-6 · **Builds on:** Phase 2a (event-resume opt-in, `67a5e432`).

## What 2b is (and what 2a already did)
- **2a (done):** the consumer's `submit_and_wait` resumes on the terminal event instead of polling — but it **still holds a coroutine** for the whole LLM call. The queue (provider-registry) already bounds GPU concurrency, so **2a + queue already meet G2's throughput goal** (a slow call no longer blocks other jobs).
- **2b (this):** **release the coroutine entirely.** submit → persist `provider_job_id` on the work unit → return; a SEPARATE `llm_job_terminal` consumer resumes the step when the event arrives. Adds **crash-resilience** (a consumer restart mid-wait doesn't lose the resume) + full occupancy-decouple at scale.

## Surface discovered (2026-06-11 mapping)
The `submit_and_wait` calls are **deep inside libraries + multi-step in-memory pipelines, with NO per-LLM-call persistence**:
- **worker-ai extraction (HARD):** the call happens inside `loreweave_extraction` (entity/event/relation/fact extractors), per-op × per-chunk, **aggregated in-memory** into `Pass2Candidates` → persisted once per chapter. Only a per-CHAPTER cursor exists (`extraction_jobs.current_cursor`); **no per-chunk/per-op checkpoint**. Decoupling needs an extraction-SDK refactor to surface per-call resume points.
- **translation V3 (MEDIUM-HARD):** a per-chapter state machine (bilingual-extract → translate → verify → correct), each step a `submit_and_wait`, in-memory. `chapter_translations` is the per-chapter row but has no `provider_job_id`/stage.
- **knowledge (MEDIUM):** several disjoint **one-shot** calls — summary regen (`regenerate_summaries.py:375`, has `knowledge_summaries{,_versions}`), wiki gen (`wiki/generate.py:69`), coref verify (`coref_detect.py:272`, looped), passage rerank (`passages.py:547`, ephemeral + the §5.7-S4 `wait_for`-without-DELETE bug).

**Non-target:** synchronous request/response endpoints (`/translate-text` translate.py:178) are **NOT** decouple targets — the HTTP handler must block to return the response, so releasing the coroutine is pointless. Only **batch/background** work units (claimed by a worker/consumer) benefit.

## The shared pattern (build once, reuse)
Each service gets the same three pieces:

1. **Persistence — `pending_llm_jobs` (per service DB):**
   `(provider_job_id UUID PK, work_kind TEXT, work_ref TEXT/JSONB, stage TEXT, model_ref, created_at, status)`. One row per in-flight LLM job, carrying the **resume context** (what work unit + which stage). `work_ref` is the key back into the service's own state (e.g. `{chapter_translation_id, stage:'verify'}`, `{summary_scope_id}`).

2. **A `llm_job_terminal` consumer** (model on the existing `app/events/consumer.py` XREADGROUP, group `<svc>-llm-resume`): on a terminal event, look up `pending_llm_jobs[provider_job_id]`; if found → dispatch to the registered **resume handler** for that `work_kind`; delete the row; XACK. Idempotent on `provider_job_id` (at-least-once). Unknown job_id → ignore+ack (another service's job).

3. **Per-call-site split:** replace `result = await submit_and_wait(...)` with:
   - `submit_job(...)` → `provider_job_id`; INSERT `pending_llm_jobs` (work_ref + stage); **return/release**.
   - a `resume_<work_kind>(job_id, result)` handler that does what came *after* the await (similarity check + upsert / aggregate / next stage), driven by the consumer.

The SDK's `await_job_event` (D-SDK-AWAIT-JOB-EVENT) + `get_job` (fetch the full result by `result_ref`) are the resume primitives.

## Phased order (simplest real batch path → hardest)
- **2b-1 (proof): knowledge summary regen** — MEDIUM, one-shot, background, has a state table. Establishes the shared `pending_llm_jobs` + consumer + resume-dispatch pattern on a contained path. Gate: a summary regen completes via the consumer (no held coroutine).
- **2b-2: knowledge one-shots (wiki, coref) + §5.7-S4 fix** — apply the pattern; add the missing DELETE-on-abandon at `passages.py` (now a real abort post-Phase-0).
- **2b-3: translation V3** — persist `provider_job_id` + `stage` on `chapter_translations`; resume the per-chapter state machine stage-by-stage on events. MEDIUM-HARD.
- **2b-4: worker-ai extraction** — HARDEST; needs `loreweave_extraction` to surface per-op resume points + a per-op `pending_llm_jobs` set on `extraction_jobs`. Do last, behind a flag, with the campaign factory E2E as the gate.

Each step is its own commit + validation; the campaign factory E2E is the overall gate (2b-3/2b-4).

## Cross-cutting
- **In-flight Semaphore** (spec rows 4-5): even before full decouple, bound the concurrent in-flight LLM coroutines per worker (memory/backpressure guard) — cheap, independent, do alongside 2b-1.
- **cancel_job** threading: each persisted `provider_job_id` makes a real DELETE possible on user-cancel / abandon (Phase-0 abort).
- **Idempotency:** resume handlers must be idempotent on `provider_job_id` (at-least-once event delivery) — mirror the campaign convergent-projection discipline.
- **Backstop:** the existing campaign reconcile-by-truth + the provider-registry stuck-running sweeper remain the safety net for lost events.
