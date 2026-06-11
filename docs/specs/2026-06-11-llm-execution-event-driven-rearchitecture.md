# Spec — LLM-Execution Event-Driven Re-Architecture

**Date:** 2026-06-11 · **Status:** DESIGN (awaiting PO sign-off) · **Size:** XL (multi-service, phased)
**Source audit:** [`docs/reviews/2026-06-11-llm-execution-architecture-audit.md`](../reviews/2026-06-11-llm-execution-architecture-audit.md)
**Trigger incident:** a slow reasoning 35B local model held the single GPU governor slot; queued calls failed `governor: acquire timeout`; cancelling the campaign did **not** free the GPU (the in-flight generation ran to completion). Root: the LLM seam is pull-blocking by default and cancel is DB-state-only.

---

## 1. Problem

The audit found the platform is **pull-blocking at the LLM seam almost everywhere**, with three structural consequences:

- **A caller coroutine + the single GPU governor slot are pinned for the entire generation** (`submit_and_wait` poll loop with no wall-clock cap, or a held SSE stream). worker-ai/translation dispatch *serially* → one slow chapter wedges a whole replica.
- **Cancel never aborts an in-flight generation.** `observability.DetachedContext` (observability.go:135-138) strips cancellation from the job goroutine (spawned jobs_handler.go:226); `DELETE /v1/llm/jobs/{id}` only flips DB state. The abort machinery *exists but is unfed*: governor selects on `<-ctx.Done()` (governor.go:112), streamer checks `ctx.Done()` per SSE line (streamer.go:202).
- **The governor is block-acquire-then-fail** (guard.go:54 holds the slot via `defer release()`; queued calls spin to `AcquireTimeout`→`ErrGovernorTimeout`, governor.go:108). A slow job doesn't *delay* the queue — it *fails* everyone behind it.

**campaign-service is already the fully event-driven reference** (dispatch-then-forget + Redis-Stream resume + truth reaper; reconcile.py, consumer.py, driver.py) and needs no change — it only *benefits* once the seam below it is fixed.

## 2. Goals / Non-Goals

**Goals**
- G1. **Cancel/interrupt that actually stops the work** and frees the GPU slot the instant it's issued (platform-wide).
- G2. **Decouple caller occupancy from LLM wall-time** on the job path: submit → forget → resume on a completion event. Throughput stops being gated by the slowest in-flight call.
- G3. **Backpressure that queues, not fails.** A slow job delays the queue; it never cascades `ErrGovernorTimeout`.
- G4. **Self-healing** without a bespoke reaper where possible (queue redelivery), with a truth-query reaper as backstop (campaign pattern).
- G5. **Zero-break migration** — `submit_and_wait` stays a working adapter throughout; services opt in one at a time.

**Non-Goals**
- N1. **NOT converting interactive streaming chat to fire-and-forget.** Live SSE token delivery (chat, co-write) is the *correct* UX; it only needs cancel-on-disconnect + a cap (see §3).
- N2. NOT changing campaign-service's orchestration (already correct).
- N3. NOT adopting provider-native webhooks/Batch as the universal mechanism — local BYOK backends (LM Studio/Ollama) have none. Provider-native batch can be a later cloud-only optimization (§9, out of scope for v1).
- N4. NOT a provider-SDK change — the provider-gateway invariant stays; all changes are inside provider-registry + the consuming services + the loreweave_llm SDK.

## 3. Key design split: two paths, two models

The audit lumps everything as "holds a resource", but the *right* model differs by interaction class:

| Path | Examples | Correct model | What it needs |
|---|---|---|---|
| **Job path (async/batch)** | extraction, translation, verify/correct, judges, summaries, media gen, batch helpers, composition auto-generate | **Fire-and-forget + resume-on-event** (this spec's core) | submit→enqueue→event resume; cancel=abort; cap; reaper |
| **Interactive stream path (live)** | chat SSE, co-write ghost-text, voice | **Keep SSE** (live token delivery is the point) | cancel-on-disconnect (S1), wall-clock/idle cap, NOT event-driven |

This split is load-bearing: it scopes the big change to the job path and reduces the interactive path to "make the existing SSE cancellable", which S1 delivers almost for free.

## 4. Target architecture (job path)

```
caller → submit_job (202 + job_id)                         [ENQUEUE, return immediately]
            │
provider-registry: durable llm.jobs work queue (per kind)   [NEW topology over RabbitMQ]
            │
 bounded concurrency-consumer pool, size = governor maxFor(kind)
            │   (local kinds → 1 consumer = the single GPU; cloud → N)
            │   ← cancellable ctx, registered jobID→cancel  [S1]
 provider call (cancellable, wall-clock-capped)             [S2/§5.5]
            │ terminal
 outbox row + emit  llm.job.completed | llm.job.failed       [REUSE outbox→relay→Redis/RMQ]
            │
caller service: llm.job_terminal consumer group → resume the step by job_id   [REUSE campaign consumer pattern]
            │
cancel = DELETE → registry.cancel(jobID) → ctx.Done() → abort upstream + free slot   [S1]
reaper = queue redelivery on un-acked (consumer crash) + truth-query backstop   [§5.6]
```

**The governor stops being an acquire-gate and becomes the consumer-pool size.** Jobs wait *in the queue* until a consumer is free — bounded wait, never acquire-fail. This is exactly campaign's "DB-derived in-flight ceiling" idea, applied to GPU concurrency.

## 5. The pieces

### 5.1 Cancellable context + registry (S1) — **do first, alone**
- Replace `observability.DetachedContext` usage at the job-goroutine spawn with `ctx, cancel := context.WithCancel(context.Background())`, re-attaching the trace span via `trace.ContextWithSpanContext` (keep observability; drop only the *deadline/cancel* stripping).
- Process-local registry `sync.Map[jobID]context.CancelFunc`; register on spawn, delete on terminal.
- `cancelLlmJob` (jobs_handler.go:893): after the DB `status='cancelled'`, `if c,ok:=reg.Load(jobID);ok { c() }`. The governor's `<-ctx.Done()` (governor.go:112) + streamer's `ctx.Done()` (streamer.go:202) then abort the upstream read and fire `Guard`'s `defer release()` (guard.go:54) → **slot frees immediately**.
- **HA caveat (DECISION D2):** the registry is process-local. Single provider-registry replica today → correct. For multi-replica (post-queue), the cancel must reach the replica running the job. Two options: (a) a Redis `llm:cancel:{job_id}` flag the streamer/governor loop checks each tick (provider-agnostic, HA-safe, matches the "Redis cancel-flag" pattern), or (b) broadcast cancel via pub/sub to all replicas. **Recommend:** ship (a) process-local now + design the Redis-flag as the HA story landed with the queue (§5.2), since the queue is what introduces multi-replica.
- **Interactive path benefit:** chat/co-write SSE handlers already have the request ctx; wiring disconnect→`DELETE`/cancel makes live streams abortable too (closes the N1 gap for the interactive path).

### 5.2 `llm.jobs` work queue + concurrency-consumer pool (S3)
- Today: `submitLlmJob` → `go s.jobsWorker.Process(...)` (direct goroutine). New: enqueue a durable message to `llm.jobs.{kind}` (RabbitMQ; the headers already advertise this "Phase 2c" swap, worker.go:5-6).
- A consumer pool per kind with prefetch/concurrency = `governor.maxFor(kind)` (local→1, cloud→N). The pool replaces block-acquire; the governor's atomic-Lua slot logic is retained only as a *safety belt* (and for the fail-open/REDIS-unset hardening, S3 notes), not as the primary gate.
- **DECISION D1 — topology:** per-kind queues (clean isolation + per-kind concurrency, natural for "local=1") vs a single queue with kind-aware routing. **Recommend per-kind queues.**
- Backpressure = queue depth (observable, bounded). `LLM_CIRCUIT_OPEN` continues to pause campaigns (consumer.py:119) instead of failing.

### 5.3 Completion event contract `llm.job.completed` / `llm.job.failed`
- `notifier.PublishTerminal` already emits `user.{uid}.llm.{op}.{status}` to `loreweave.events` (notifier.go:117). Add a **canonical, per-job-correlated** terminal event so a caller binds a consumer to *its* job:
  - Routing key: `llm.job.completed` / `llm.job.failed` (topic exchange).
  - Payload: `{ job_id, user_id, operation, status, kind, result_ref (job row id to fetch full result), cost_usd, error_code?, error_message?, campaign_id?, correlation_id }`.
  - Emitted in the **same outbox tx** as the terminal DB write (exactly-once w.r.t. the row; relay handles delivery) — reuse `FinalizeWithUsageOutbox` precedent.
- Consumers fetch the full result via the existing `GET /internal/llm/jobs/{id}` (kept) using `result_ref`; the event carries only the correlation + summary (keeps the bus light).

### 5.4 SDK event-driven adapter (S2) — keeps `submit_and_wait` working
- `submit_and_wait(...)` signature unchanged. Internally: if a broker is configured → `submit_job` + bind an `aio_pika` consumer to the job's routing key, await the terminal event (poll remains a *fallback*/reaper, e.g. one slow poll every 30s in case the event is missed). Else → today's poll loop.
- New explicit API: `await_job_event(job_id, timeout=None)` and `submit_and_await_event(...)` for callers that want to *release the coroutine* (the real win — a consuming service submits, persists `provider_job_id`, returns, and a separate consumer resumes). `CallbackConfig(rabbitmq routing_key | webhook)` is already on `SubmitJobRequest` (models.py:198) — wire present, consume to be added.
- Batch helpers (transcribe/image/video/audio) convert cleanly (budget=0, no mid-stream state).

### 5.5 Wall-clock cap (S2)
- Per-job `context.WithTimeout` for **local kinds** (configurable, e.g. `LLM_LOCAL_JOB_TIMEOUT_S`, default generous — minutes, not seconds; this is a runaway-backstop, not the long-run mechanism). Media ops already use `WithTimeout` (worker_video.go:103) — generalize. A runaway self-frees its slot even absent a cancel.

### 5.6 Reaper (S6) — mostly free
- With the queue + ack-on-terminal, a consumer crash leaves the message **un-acked → redelivered** automatically (visibility-timeout semantics). That *is* the reaper for the execution side — "a well-built flow doesn't need a separate GC worker."
- Backstop for the rare stuck-`running` DB row: a periodic sweeper over `llm_jobs WHERE status='running' AND last_progress_at < threshold` (campaign reconcile-by-truth shape, reconcile.py). Lower priority once redelivery exists.

### 5.7 Orphaned-job + inline-handler fixes (S4/S5)
- S4: knowledge `asyncio.wait_for` / shutdown `CancelledError` paths (passages.py:547) must issue `DELETE` (now a real abort post-S1) when abandoning a wait. Quick, independent win.
- S5: move lore-enrichment `POST /jobs` (jobs.py:236) + composition auto-generate (engine.py:348) off the HTTP request path onto submit→event-resume (lore-enrichment already has a `paused→Redis→redrive` spine to generalize; composition needs a real internal worker).

## 6. Per-service migration (consumer wiring)

| # | Service | Change | Reuses |
|---|---|---|---|
| 1 | **provider-registry** | S1 cancellable ctx + registry + cancel wiring + local wall-clock cap | governor/streamer ctx.Done (exist) |
| 2 | **provider-registry** | emit canonical `llm.job.completed/failed` | outbox + notifier |
| 3 | **SDK** | event adapter behind `submit_and_wait` + `await_job_event` | CallbackConfig on the wire |
| 4 | **worker-ai** | extraction: submit→persist `provider_job_id`→resume via an `llm.job_terminal` consumer; add `cancel_job`; in-flight Semaphore | summary_consumer + FD-22 wake plumbing (main.py:141) |
| 5 | **knowledge** | S4 `wait_for`→`DELETE` (now); then Pass-2 event-resume; mandatory local-kind Semaphore | existing redis-stream consumers |
| 6 | **translation** | persist `provider_job_id`/chapter; in-loop cancel re-checks; pass `invoke_timeout_secs(300)`; event-resume | AMQP rungs already event-driven |
| 7 | **lore-enrichment + composition** | move LLM off the request path → submit + Redis resume; composition internal worker | lore-enrichment paused→redrive spine |
| 8 | **chat (interactive)** | NOT event-driven — add disconnect→cancel; adopt `suspended_runs` resume primitive (stream_service.py:803) for token delivery; route auto-title + voice STT (jobs) through the queue | suspended_runs (exists) |
| 9 | **learning + video-gen** | judges xack-then-submit + resume; video-gen real job row + status + cancel route | — |
| — | **campaign** | none (already the target); benefits from S1 (cancel frees the GPU slot) | — |

## 7. Open decisions for PO

- **D1 — Queue topology:** per-kind `llm.jobs.{kind}` queues (recommended) vs single queue + kind-aware consumers.
- **D2 — Cancel reach under HA:** process-local CancelFunc now + Redis cancel-flag when multi-replica (recommended) vs Redis-flag from the start.
- **D3 — v1 scope:** (a) S1 + the contract + worker-ai/knowledge/translation (the campaign/batch path) only, leaving chat/composition/lore-enrichment/video-gen for v2; vs (b) all-services. **Recommend (a)** — it covers the campaign factory (the incident's domain) and proves the pattern before the long tail.
- **D4 — local wall-clock default** (minutes; value?).
- **D5 — `submit_and_wait` poll fallback:** keep permanently as a belt-and-suspenders vs remove after full migration.
- **D6 — interactive streaming:** confirm we keep SSE for live chat/co-write (recommended) and only make it cancel-on-disconnect — i.e. NOT fire-and-forget there.

## 8. Risks & testing

- **Exactly-once vs at-least-once:** the terminal event is at-least-once (relay). Consumers must be **idempotent on job_id** (campaign already is; new consumers follow the convergent-projection / dedup-key discipline).
- **Lost event:** covered by the poll-fallback (SDK) + queue redelivery + truth reaper — defense in depth (mirrors campaign's events+reaper).
- **Cancel race:** cancel arriving after terminal must be a no-op (registry entry already deleted); cancel before spawn → DB cancel + the consumer checks `status='cancelled'` before running (skip). Test both.
- **Live-smoke is mandatory** (≥2 services): induce a slow local job, cancel mid-generation, assert the GPU slot frees within one tick (the exact incident, as a regression test). Fault-inject a dropped terminal event → assert reaper/poll recovers.
- **Migration safety:** each service flips behind a config flag (broker configured ⇒ event path, else poll). Roll out one service at a time; campaign E2E is the acceptance gate.

## 9. Phasing

- **Phase 0 (unblocks the incident class):** S1 cancellable context + cancel wiring + local wall-clock cap — provider-registry only. Smallest diff, makes cancel real platform-wide, regression-tests the incident. *Shippable alone.*
- **Phase 1 (enable the pattern):** `llm.jobs` queue + consumer pool (D1) + canonical terminal event (§5.3) + SDK adapter (§5.4). No consumer changes yet; `submit_and_wait` transparently moves to event-resume.
- **Phase 2 (convert the batch path):** worker-ai → knowledge (incl. S4) → translation. Campaign factory E2E is the gate.
- **Phase 3 (long tail):** lore-enrichment + composition off the request path (S5); chat disconnect-cancel; learning + video-gen job rows.
- **Out of scope (future):** provider-native OpenAI Batch/webhook fast-path for cloud kinds (50% cheaper bulk); not universal because of local backends.

### What Phase 0 alone already buys
- Cancel/interrupt that frees the GPU the instant it's issued — the exact thing missing in the incident.
- A runaway local job self-frees via the wall-clock cap.
- Every existing cancel path (campaign `_propagate_cancel`, translation `_cancel_job_core`, future video-gen) becomes real with no per-service work.

**Recommendation:** approve Phase 0 as an immediate standalone `/loom` (it's the highest-leverage, lowest-risk change and directly closes the incident), and approve Phases 1–2 scope (D3 option a) as the next design-then-build track. Phase 3 + cloud-batch tracked as follow-ons.
