# LoreWeave LLM-Execution Architecture Audit — Decision Report

**Date:** 2026-06-11 · **Method:** 12-area multi-agent code audit (provider-registry core + governor/streamer/cancel, SDK, worker-ai, translation, knowledge, chat, learning, lore-enrichment, composition, video-gen, campaign reference).
**Trigger:** a real incident — a slow reasoning 35B local model held the single GPU governor slot, queued calls failed `governor: acquire timeout`, and cancelling the campaign did **not** free the GPU (the in-flight generation kept running). Question raised: is the platform's LLM-interaction architecture fundamentally wrong for long-running, indeterminate LLM work?

## 1. TL;DR

**The system is pull-blocking at the LLM seam almost everywhere — and it is not by design, it is by default.** Every AI-consuming service (worker-ai, translation, knowledge, chat, learning, lore-enrichment, composition, video-gen) reaches the LLM through one of two synchronous shapes: `submit_and_wait` (SDK `submit_job` + a `wait_terminal` poll loop, 0.25→5s backoff, **no wall-clock cap**) or a **held-open SSE stream** with `httpx.Timeout(None)`. In both, a single coroutine is pinned for the entire generation, and — because local kinds serialize to one GPU governor slot — that coroutine transitively holds the single GPU slot too. **Cancel is DB-state-only across the entire platform**: `DELETE /v1/llm/jobs/{id}` flips a row but never aborts the in-flight provider call, because the worker runs under `observability.DetachedContext` which deliberately strips cancellation (observability.go:135-138, spawned at jobs_handler.go:226). The abort machinery *physically exists* (governor selects on `ctx.Done()` at governor.go:112, the streamer checks `ctx.Done()` per SSE line at streamer.go:202) but is never fed a cancellable context. **Exactly one service — campaign-service — is already fully event-driven** (dispatch-then-forget + Redis-Stream resume + truth-query reaper) and is the proven in-repo template.

**Recommendation: the re-architecture is warranted, and the cheapest highest-leverage starting point is provider-registry-service** — fix the detached context there and every downstream cancel becomes real for free; then move the SDK's `submit_and_wait` onto a `llm.job.completed` event so the poll-block disappears platform-wide.

## 2. System map

| Service | LLM-call path | Pattern | Cancel aborts in-flight? | Holds resource on slow/cancel? | location |
|---|---|---|---|---|---|
| provider-registry | Job submit → detached goroutine (202) | fire-and-forget | n/a (inbound returns) | no | jobs_handler.go:226-235 |
| provider-registry | Worker provider call under S3a governor | block-acquire-then-fail | **no** | **yes (GPU slot)** | worker.go:467/513; governor.go:79-117; guard.go:49-55 |
| provider-registry | Streaming SSE hold (`adapter.Stream`) | streaming-sync-hold | no (ctx detached) | **yes** | worker.go:393/514; streamer.go:257-380 |
| provider-registry | Terminal event emit (outbox→RabbitMQ) | event-driven-resume | n/a | no | worker.go:98-175; notifier.go:117-160 |
| provider-registry | `DELETE /v1/llm/jobs/{id}` cancel | other (DB-state only) | **no** | **yes** | jobs_handler.go:893-951; observability.go:135-138 |
| sdk (python) | `submit_job` | fire-and-forget | n/a | no | client.py:263-299 |
| sdk (python) | `wait_terminal` poll loop (workhorse) | pull-blocking-poll | no | **yes (gateway slot)** | client.py:327-392 |
| sdk (python) | `stream` / `stream_tts` SSE | streaming-sync-hold | no | **yes** | client.py:122-204 |
| sdk (python) | batch helpers (transcribe/image/video/audio) | pull-blocking-poll | no | **yes** | client.py:394-960 |
| worker-ai | chapter/chat Pass-2 extraction | pull-blocking-poll | no (between-items only) | **yes** | runner.py:1516→llm_client.py:124 |
| worker-ai | serial job dispatch loop | pull-blocking-poll | no | **yes** | runner.py:2066-2070 |
| worker-ai | FD-22 wake (Redis XREAD BLOCK) | event-driven-resume | n/a | no | wake.py:52-80 |
| translation | block/text translate, QA verify/correct, two-pass | pull-blocking-poll | no | **yes** | session_translator.py:916/508; v3/llm_verifier.py:105; v3/corrector.py:70; v3/orchestrator.py:90 |
| translation | AMQP backoff rungs | event-driven-resume | n/a | no | worker.py:144 |
| knowledge | `submit_and_wait` chokepoint | pull-blocking-poll | no | **yes** | llm_client.py:168-295 |
| knowledge | Pass-2 R/E/F `asyncio.gather` (3 concurrent slots) | pull-blocking-poll | no (between-items) | **yes** | pass2_orchestrator.py:926-954 |
| knowledge | generative rerank (`wait_for` 1s, abandons job) | pull-blocking-poll | **abandons, doesn't abort** | **yes (orphaned slot)** | passages.py:547-564 |
| knowledge | embedding / cross-encoder rerank HTTP | streaming-sync-hold | no | **yes** | embedding_client.py:86; reranker_client.py:59 |
| chat | text chat / tool-loop / composer SSE | streaming-sync-hold | no (no job id) | **yes** | stream_service.py:102/290/210 |
| chat | suspended_runs SUSPEND/RESUME | event-driven-resume | n/a (no resource held) | **no** | stream_service.py:803/1037 |
| chat | voice STT→LLM→TTS, auto-title | streaming-sync-hold / detached task | no | **yes** | voice_stream_service.py:94/365/124; stream_service.py:1001 |
| learning | extraction + translation online judges | pull-blocking-poll | no (no cancel path at all) | **yes** | llm_client.py:29-64; handlers.py:547-617 |
| lore-enrichment | POST /jobs full pipeline INLINE in request | streaming-sync-hold | no | **yes** | jobs.py:236; complete.py:228 |
| lore-enrichment | eval judge ensemble (N×M serial) | streaming-sync-hold | no | **yes** | judge_binding.py:60; judge_usefulness.py:356 |
| composition | auto "agent loop" inline in request | pull-blocking-poll | no | **yes** | engine.py:348-445 |
| composition | diverge K-fan-out (K concurrent slots) | pull-blocking-poll | no | **yes** | select.py:106-114 |
| composition | reflect_revise / co-write stream | streaming-sync-hold | no | **yes** | canon_check.py:280-299; cowrite.py:187 |
| video-gen | POST /generate (5-20min ComfyUI hold) | pull-blocking-poll | **no cancel route exists** | **yes (longest hold on platform)** | generate.py:249 |
| **campaign** | **saga dispatch (translation/knowledge)** | **fire-and-forget** | partial (DB+downstream POST) | **no** | driver.py:134-207 |
| **campaign** | **projection / spend / circuit consumers** | **event-driven-resume** | n/a | **no** | consumer.py:211-264; spend_consumer.py:69-152 |
| **campaign** | **stuck-dispatch reaper (truth-query)** | **event-driven-resume** | n/a | **no** | reconcile.py:42-220 |

## 3. The reference pattern (campaign-service already does it right)

campaign-service makes **zero direct LLM calls** and never waits on a job. It is the model every other seam should converge to:

1. **Claim-first, dispatch-then-forget.** Flips a projection row to `dispatched` *before* the POST (driver.py:127-132), POSTs **one batched** downstream job, stamps `job_id`, returns immediately — no wait. Crash between claim and POST → a stuck row the reaper fixes; never double-dispatched → no double-spend.
2. **Resume purely on a Redis-Stream completion event.** The `campaign-collector` consumer group reads `chapter.translated` / `knowledge.chapter_extracted` off the outbox→relay→Redis spine and convergently flips stages to `done` (consumer.py:211-264). The saga never polls — it *reacts*. **This is the mechanism that replaces `submit_and_wait`.**
3. **Backpressure without holding a slot.** Fan-out capped by a DB-derived in-flight ceiling (`budget = max_inflight − count_inflight`, driver.py:102-105) — a pure count, not a governor slot acquire. No `ErrGovernorTimeout` cascade possible.
4. **Two-tier completion: events + truth-query reaper.** Lost events self-heal via reconcile-by-truth (reconcile.py:42-220): rows stuck past `stuck_timeout_s` ask the downstream done-predicate and mark done (no re-spend) or reset; conservative on uncertainty.
5. **Event-driven pause as the governor-cascade answer.** A `LLM_CIRCUIT_OPEN` failure event **pauses** the campaign (consumer.py:119-148) instead of block-acquiring and failing.
6. **Ack discipline matches the fold.** Convergent projection → always-ack (self-heals via reaper); non-idempotent spend SUM → never-ack-on-failure, reclaim via `_drain_pending`.

The only remaining gap even here is platform-wide, not campaign's fault: `_propagate_cancel` frees campaign's own projection slots but the running generation keeps its GPU slot — because provider-registry `DELETE` only flips DB state.

## 4. Gaps, ranked by severity

### S1 — Cancel never aborts in-flight generation (whole platform). **Critical.**
`observability.DetachedContext` (observability.go:135-138) returns `trace.ContextWithSpanContext(context.Background(), …)` — carrying the trace span but dropping cancellation. The worker goroutine is spawned under it (jobs_handler.go:226). So `DELETE /v1/llm/jobs/{id}` (jobs_handler.go:893-951) + `repo.Cancel` (repo.go:342-353) only `UPDATE status='cancelled'`. The streaming goroutine keeps reading upstream to completion, holding the governor slot + HTTP connection. **The abort machinery already exists** — governor selects on `<-ctx.Done()` (governor.go:112), streamer checks `ctx.Done()` per SSE line (streamer.go:202) — it is simply never given a cancellable ctx.
**Affects:** every cancel path (worker-ai, translation `_cancel_job_core`, knowledge, chat, learning, lore-enrichment, composition, video-gen, and campaign's `_propagate_cancel`).
**Hostage risk:** the literal incident — a cancelled slow 35B keeps the single GPU slot until it finishes; video-gen worst-case pins the GPU 5-20+ min.
**Fix surface is small:** replace `DetachedContext` with `context.WithCancel` derived from `Background()` (keep span ctx), store the `CancelFunc` in a `jobID→CancelFunc` registry, have `cancelLlmJob` invoke it after the DB cancel. This is the code's own deferred "Phase 6 worker-context cancellation" (jobs_handler.go:894-896).

### S2 — `submit_and_wait` poll-block pins a coroutine + GPU slot for the whole generation. **Critical.**
The SDK's `wait_terminal` (client.py:327-392) is an unbounded poll loop with **no wall-clock timeout** (client.py:338-339), the workhorse every batch helper + consuming service funnels through. Held call has no server-side wall-clock cap for chat/extraction/translation text — only the SDK's `httpx.Timeout(None)`.
**Affects:** worker-ai (runner.py:1516→llm_client.py:124), translation (session_translator.py:916), knowledge (llm_client.py:168), learning (llm_client.py:29), composition (engine.py:348), video-gen (generate.py:249).
**Hostage risk:** a slow generation holds **both** the caller coroutine **and** the single GPU slot. worker-ai/translation dispatch is **serial** (runner.py:2066) — one slow chapter wedges every other job in that replica.

### S3 — Governor is block-acquire-then-fail, not enqueue-and-dispatch. **High.**
`Guard` holds the slot via `defer release()` (guard.go:54) for the entire `adapter.Stream`; queued calls spin-poll `Acquire` until `AcquireTimeout` (30s) → `ErrGovernorTimeout` (governor.go:108-109). Local kinds serialize to 1. The error is classed transient → `retryTransient` re-acquires, extending occupancy. Amplified by fan-out (knowledge R/E/F gather 3-concurrent; composition diverge K-wide). Plus **fail-open**: Redis down → no-op release, ungoverned (governor.go:92-97) → GPU oversubscription; `REDIS_URL` unset → pure pass-through (guard.go:43).

### S4 — Orphaned-job leak: `asyncio.wait_for` / `CancelledError` abandons the wait but not the job. **High.**
knowledge generative rerank wraps `submit_and_wait` in `asyncio.wait_for(timeout=1.0)` (passages.py:547-564); on timeout returns MMR fallback but the provider job **keeps running on its slot** — never `DELETE`s. Summary-regen scheduler's `CancelledError` on shutdown does the same. Under load these pile up orphaned jobs each holding the local-kind=1 slot.

### S5 — LLM work executed INLINE in HTTP request handlers. **High (correctness + availability).**
lore-enrichment `POST /jobs` declared 202 but `await`s the full `run_job` inline (jobs.py:236, "Synchronous for the demo"); composition auto "agent loop" runs the whole pipeline inline in `POST /works/{id}/generate` (engine.py:348-445); composition eval `/run` blocks O(judges×proposals) serial (eval.py:218). Request coroutine + httpx connection + GPU slot held for minutes; client disconnect strands work with no resumption.

### S6 — No crash/stale-job reaper in provider-registry. **Medium.**
A goroutine panic / process exit leaves a job stuck in `running` forever (acknowledged worker.go:266-268, migrate.go:136-137). A queue consumer with visibility-timeout requeue gives this for free.

### S7 — Non-LLM coroutine holds. **Medium.**
`summary_processor.py:146-148` blocks the serial consumer up to 120s on a retry sleep with no LLM running; `embedding_client.py:86` is a 30s blocking POST on the summary write-critical path.

## 5. Target architecture — fire-and-forget + queue-throughout

```
caller → submit_job (202, job_id)              [ENQUEUE, return immediately]
            │
provider-registry: llm.jobs work queue          [NEW — RabbitMQ consumer]
            │
 bounded concurrency-consumer pool (per kind)    [REUSE governor maxFor() as pool size]
            │  ← cancellable ctx in jobID→CancelFunc registry  [NEW, small]
 provider call (cancellable, wall-clock-capped)
            │
 terminal → outbox row + emit llm.job.completed/failed   [REUSE outbox→relay→Redis]
            │
worker resumes on event via consumer group       [REUSE campaign's consumer pattern]
            │
cancel = registry.cancel(jobID) → ctx.Done() → abort call + free slot   [NEW wiring, machinery EXISTS]
reaper (truth-query / visibility-timeout)         [REUSE campaign reconcile.py shape]
```

| Piece | Reuse what exists | What's new |
|---|---|---|
| Submit → enqueue | `submit_job` 202 returns `job_id` (client.py:263); headers promise the RabbitMQ swap (jobs_handler.go:11-13, worker.go "Phase 2c") | Bind submit to a durable `llm.jobs` queue instead of `go s.jobsWorker.Process(...)` |
| Concurrency = consumer pool | Governor `maxFor()` / `localKinds`→1 | Pool of N consumers per kind pulling the queue → replaces block-acquire-then-fail; cascade becomes bounded queue wait |
| Emit completion event | Terminal outbox + `notifier.PublishTerminal` (notifier.go:117-160) emit `user.{uid}.llm.{op}.{status}` | A canonical `llm.job.completed/failed` routing key + per-job correlation |
| Worker resume | campaign consumer groups, worker-ai FD-22 wake + summary_consumer redis-stream loop | Each service runs an `llm.job_terminal` consumer mapping `job_id`→pending row, resumes the step (replaces `wait_terminal`) |
| Cancel = abort ctx | governor `<-ctx.Done()` (governor.go:112) + streamer `ctx.Done()` (streamer.go:202) **already work** | Replace `DetachedContext` with `WithCancel`; `jobID→CancelFunc` registry; `cancelLlmJob` invokes it |
| Wall-clock cap | media ops already use `WithTimeout` (worker_video.go:103) | Configurable per-job (local-kind) `WithTimeout` for text ops |
| Reaper | campaign reconcile-by-truth (reconcile.py:42-220) | Visibility-timeout requeue, or sweeper over `llm_jobs WHERE status='running' AND last_progress_at < threshold` |
| SDK event API | `CallbackConfig(rabbitmq routing_key | webhook)` already on `SubmitJobRequest` (models.py:198-227) — wire present, consume absent | `submit_and_await_event(...)` + `await_job_event(job_id)` consumer |

## 6. Migration path (incremental, nothing breaks)

**Keep `submit_and_wait` as a compatibility adapter the whole time.** The SDK becomes: `submit_and_wait()` internally either polls (today) *or*, when a broker is configured, binds an `aio_pika` consumer to the job's routing key and resumes on `llm.job.completed`. Same signature/return — callers don't change until they opt in. The contract already supports it (`CallbackConfig` on the wire, terminal event already emitted).

1. **provider-registry — cancellation first (S1).** Smallest diff, biggest blast radius: swap `DetachedContext`→`WithCancel` + `jobID→CancelFunc` registry + `cancelLlmJob` lookup. Every downstream cancel becomes real for free. Add the text-op wall-clock cap (S2/S3 mitigation) in the same change. **Do this first regardless of the rest.**
2. **provider-registry — emit canonical `llm.job.completed/failed` + correlation.** Reuses outbox/notifier; no consumer changes yet. Enabling event for everyone.
3. **SDK — add the event-driven adapter path** behind `submit_and_wait` + standalone `await_job_event`. Polling stays as fallback. Opt-in per caller.
4. **worker-ai first among consumers.** Already has redis-stream consumer plumbing (summary_consumer + FD-22 wake, main.py:141-149). Convert chapter extraction to submit→persist `provider_job_id`→resume-on-event; add the missing `cancel_job` call + an in-flight Semaphore cap. Highest value: it's the serial-dispatch wedge.
5. **knowledge-service.** Wire `wait_for`/`CancelledError`→`DELETE` immediately (S4 quick win), then convert Pass-2 to event-resume; mandatory context-budget Semaphore for local kinds.
6. **translation-service.** Persist `provider_job_id` per chapter, add in-loop cancel re-checks, pass `invoke_timeout_secs(300)` into the wait, convert to resume-on-event.
7. **lore-enrichment + composition.** Move LLM work off the HTTP request path onto the existing Redis resume stream (lore-enrichment already has the `paused→Redis→redrive` spine — generalize from cost-cap-only to job-completion + cancel). Composition needs a real internal queue/worker first.
8. **chat-service.** Adopt the `suspended_runs`/resume primitive (stream_service.py:803/1037) as the general token-delivery model; add disconnect→`cancel_job`; route auto-title + voice STT through the queue.
9. **learning + video-gen.** Lower volume; judges → xack-then-submit + resume; give video-gen a real job row, status endpoint, cancel route.

campaign-service needs **no work** — it's already the target; it only *benefits* once S1 lands.

## 7. What this would have prevented

- **The governor cascade** (slow 35B starves queued calls into `ErrGovernorTimeout`): block-acquire-then-fail held the single slot for the full generation (guard.go:54, governor.go:108). The concurrency-consumer model converts "spin-poll Acquire until 30s then fail" into bounded queue wait.
- **The worker poll wedge** (one slow chapter freezes a whole replica): serial dispatch + `await wait_terminal` inline (runner.py:2066, session_translator.py:916). Fire-and-forget submit + resume-on-event releases the coroutine during the LLM wall-time.
- **GPU held by a cancelled 35B job:** cancel flips `status='cancelled'` (repo.go:342) but the detached goroutine runs to completion holding the slot. The `WithCancel`-registry fix feeds `ctx.Done()` to governor (governor.go:112) + streamer (streamer.go:202), firing `Guard`'s `defer release()` (guard.go:54) — slot frees the instant cancel is issued.
- **Orphaned rerank jobs** burning the slot after the user left (passages.py:547) — eliminated once `wait_for` cancellation issues a `DELETE`.
- **Stuck `running` jobs after a crash** (worker.go:266) — a queue with visibility-timeout requeue or the campaign-style truth reaper recovers them.

**Bottom line:** the re-architecture is warranted and mostly *wiring*, not invention — the outbox/relay/Redis spine, the terminal event, the governor's cancellation selects, and a complete event-driven reference (campaign-service) all already exist. Start at provider-registry's `DetachedContext` (S1): the single smallest change that makes cancel real platform-wide and the prerequisite for every other gain.
