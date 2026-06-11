# Plan — LLM re-arch Phase 1: durable terminal event + `llm.jobs` queue + SDK adapter

**Date:** 2026-06-11 · **Size:** XL (provider-registry Go + loreweave_llm SDK Python) · **Spec:** [`docs/specs/2026-06-11-llm-execution-event-driven-rearchitecture.md`](../specs/2026-06-11-llm-execution-event-driven-rearchitecture.md) §5.2–5.4 · **Phase 0 (cancel):** shipped `d7875d28`.

Phase 1 enables the event-driven pattern **without touching consumers** — `submit_and_wait` transparently moves from pure-poll to event-resume, and the governor stops being an acquire-gate. Built in **3 independently-sound commits**, lowest-risk first.

## Current plumbing (mapped 2026-06-11)
- Terminal event already exists but is **fire-and-forget + not job-correlated**: `notifier.PublishTerminal` (`internal/jobs/notifier.go:117`) → RabbitMQ `loreweave.events` topic, routing key `user.{uid}.llm.{op}.{status}`. Lost if RabbitMQ is down at publish; a caller can't bind to *its* job by key.
- The **durable** path is `usage_outbox` → `UsageRelay.drainOnce` (`internal/jobs/usage_relay.go:123`) → Redis streams (`loreweave:events:usage`, `:campaign_usage`), written in the finalize tx (`repo.go:240 FinalizeWithUsageOutbox`), at-least-once + `request_id` dedup. **campaign-service consumes Redis streams** (`spend_consumer.py`, `events/consumer.py` XREADGROUP).
- Finalize gate: `worker.go:143-151` — `rows==0` ⇒ cancel won, skip emit. Cancel path (`api/cancelLlmJob`) finalizes + publishes independently.
- Governor: `ratelimit/governor.go:23 maxFor(kind)` → local (`lm_studio`/`ollama`) = 1, cloud = `GOVERNOR_CLOUD_MAX`. Acquire = atomic-Lua slot in Redis zset `gov:conc:{kind}`, blocks to `AcquireTimeout` then **fails** (acquire-or-die — the incident class; band-aided this session with `GOVERNOR_ACQUIRE_TIMEOUT_MS=600000`).
- Job spawn: `jobs_handler.go:230` (Process) + `:705` (audio) via `spawnJob` (Phase 0 cancellable ctx + registry).
- SDK: `sdks/python/loreweave_llm/client.py:327 wait_terminal` (poll loop, 0.25→5s backoff); `submit_job:263`; `CallbackConfig` already on `SubmitJobRequest` (`models.py:198`).

## DECISION (PO) — terminal-event transport
Spec §5.3 wording says "topic exchange" (RabbitMQ). **This plan uses Redis streams via the existing outbox→relay instead**, because: (a) it's the established **durable at-least-once** path (RabbitMQ notifier is fire-and-forget); (b) the event-driven **reference (campaign) already consumes Redis streams** — one bus, one consumer idiom; (c) reuses `UsageRelay` machinery (FOR UPDATE SKIP LOCKED, dedup, maxlen) instead of adding a parallel durable-RabbitMQ outbox. The RabbitMQ `loreweave.events` notifier stays for user-facing notifications (notification-service). *If PO prefers literal RabbitMQ topic for cross-language/non-Redis consumers, swap the relay sink — the outbox row + payload are transport-agnostic.*

---

## Commit 1 — durable, job-correlated terminal event (keystone, additive, low-risk)
**Goal:** every terminal transition (completed|failed|cancelled) durably emits a per-job event a caller can resume on. No behavior change to existing callers (they still poll; this is additive).

- **Migration** `NNNN_job_event_outbox.sql`: new table `job_event_outbox(id bigserial pk, job_id uuid, owner_user_id uuid, operation text, status text, kind text, cost_usd numeric null, error_code text null, error_message text null, campaign_id uuid null, correlation_id text null, created_at timestamptz default now(), published_at timestamptz null)`. Index `(published_at) WHERE published_at IS NULL`.
- **repo.go** — generalize the finalize tx: write a `job_event_outbox` row in the SAME tx as the `llm_jobs` UPDATE, on **every** rows=1 transition (not just completed+usage). Pass the extra fields via a `TerminalOutbox` struct (operation, kind, costUSD, errorCode/message, correlationID/traceID); campaign_id parsed from job_meta (reuse `parseJobMetaCampaignID`). `kind` derived from model_source/provider_kind (resolve once, like billing).
- **Cancel path** (`api/cancelLlmJob`): write the same `job_event_outbox` row in its finalize tx so cancel emits the canonical event too.
- **usage_relay.go** — add a sibling drain `drainTerminalOnce` (same FOR UPDATE SKIP LOCKED shape) → `XADD loreweave:events:llm_job_terminal` with payload `{job_id, owner_user_id, operation, status, kind, result_ref=job_id, cost_usd, error_code, error_message, campaign_id, correlation_id}`. Pure `buildTerminalFields` (unit-tested). Run it in the same relay tick loop.
- **config.go** — `LLM_JOB_TERMINAL_STREAM` (default `loreweave:events:llm_job_terminal`) + `LLM_JOB_TERMINAL_STREAM_MAXLEN`.
- **Tests:** repo tx writes the row for each status (pgxmock); `buildTerminalFields` wire contract; cancel path writes it; relay drains + marks published + dedup.
- **Verify:** `go build ./... && go vet ./...`, package tests. Live-smoke deferred (`D-PHASE1-TERMINAL-EVENT-LIVE-SMOKE`): submit a job → assert a `llm_job_terminal` stream entry with the job_id.

## Commit 2 — SDK event-driven adapter (backward-compatible)
**Goal:** `submit_and_wait` resumes on the event when a broker/Redis is configured; poll remains the fallback. Add explicit `await_job_event` / `submit_and_await_event` for callers that want to release the coroutine.
- **client.py** — `wait_terminal`: if a Redis stream client is configured, race a stream-read (XREAD on `llm_job_terminal`, filtered to this job_id) against a slow poll (e.g. 1 poll / 30s as the lost-event backstop); first terminal wins. Else today's poll loop unchanged.
- New `await_job_event(job_id, timeout=None)` + `submit_and_await_event(...)`.
- Idempotent on job_id; tolerate at-least-once (the stream entry + a final poll agree on the DB row, the SoT).
- **Tests:** event-arrives path returns without polling; lost-event falls back to poll; signature of `submit_and_wait` unchanged (existing callers unaffected).

## Commit 3 — `llm.jobs.{kind}` queue + bounded consumer pool (the acquire-or-die fix)
**Goal:** replace `go Process(...)` + acquire-gate with enqueue + a per-kind consumer pool sized `governor.maxFor(kind)`. Jobs **wait in queue** (bounded), never `ErrGovernorTimeout`. Governor demoted to a safety belt.
- **Topology (D1 = per-kind queues):** durable `llm.jobs.{kind}` queues (RabbitMQ; headers already advertise this "Phase 2c" swap, worker.go:5-6). `submitLlmJob` enqueues instead of spawning.
- **Consumer pool**: per kind, prefetch/concurrency = `maxFor(kind)` (local→1 = the single GPU; cloud→N). Each delivery → `spawnJob`(cancellable ctx, Phase 0) → `Process`. Ack on terminal; un-acked on crash → redelivered (that's the reaper, §5.6).
- Governor's atomic-Lua retained as a belt + the fail-open/REDIS-unset hardening, NOT the primary gate.
- `LLM_CIRCUIT_OPEN` still pauses campaigns (consumer.py:119).
- **Decision D4** — local wall-clock cap default (minutes; reuse Phase 0 `LLM_JOB_WALLCLOCK_TIMEOUT_S`, set a generous default for local kinds).
- **Tests + mandatory live-smoke** (≥2 services): induce >poolsize concurrent local jobs → assert they queue + all complete (none `acquire timeout`); cancel mid-generation → slot frees in one tick (the incident regression).
- **Risk:** this rewrites the core dispatch path. Behind a config flag (broker configured ⇒ queue path, else today's direct goroutine) so it's reversible and rolls out safely. **This is the commit that lets us REVERT the `GOVERNOR_ACQUIRE_TIMEOUT_MS=600000` band-aid.**

---

## Sequencing / checkpoints
- Commit 1 → VERIFY → review → commit. Commit 2 → VERIFY → commit. Commit 3 → VERIFY + **live-smoke** (the incident regression) → commit.
- Phase 2 (convert worker-ai/knowledge/translation to event-resume) and Phase 3 (long tail) follow as separate `/loom` cycles — the spec §6 migration table is the per-service checklist.
- Deferred rows opened: `D-PHASE1-TERMINAL-EVENT-LIVE-SMOKE`, `D-PHASE1-QUEUE-LIVE-SMOKE` (the acquire-or-die regression), revert-`GOVERNOR_ACQUIRE_TIMEOUT_MS`-band-aid after Commit 3.
