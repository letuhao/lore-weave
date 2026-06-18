# P5 — Fair scheduling & per-tenant concurrency (full WFQ)

**Effort:** XL (continuous-flow, checkpoint per milestone)
**Spec:** `docs/specs/2026-06-15-unified-job-control-plane.md` §L5 + Phasing P5.
**Epic:** Unified Job Control Plane — P5 (after P4 GUI, which is complete).
**PO decisions (2026-06-16, CLARIFY):** **full WFQ dispatcher** (per-owner ready queues + round-robin, not just a cap) across **all multi-unit coordinators** (translation + knowledge + lore-enrichment).

## Problem
One huge multi-unit job (4000-chapter translation/extraction) monopolizes the worker fleet for days, starving other users (multi-tenant "noisy neighbor"). No OS-style hard preemption (can't kill an in-flight LLM call); fairness is **cooperative** at unit boundaries.

## Architecture — shared WFQ scheduler primitive (`loreweave_jobs.scheduler`)
Two dispatch substrates exist, so a single monolithic dispatcher won't fit both. Instead: a **Redis-backed WFQ scheduling primitive** in the SDK that each service wires to its own substrate.

- **PUSH services (translation, lore-enrichment fan-out):** the coordinator `enqueue`s units into per-owner ready queues instead of publishing them all; a small **dispatcher loop** `dispatch`es round-robin (≤ per-owner cap, ≤ global budget) and publishes the released units to the existing worker queue; the worker `release`s on terminal + signals the dispatcher to pull more.
- **PULL service (knowledge / worker-ai poll loop):** no ready-queue; the poll loop iterates owners **round-robin** and gates each unit with `acquire(owner, cap)` / `release(owner)` (the same per-owner in-flight accounting).

### Redis key scheme (per **lane** = a dispatch domain, e.g. `translation:chapter`)
- `p5:{lane}:ready:{owner}` — LIST (FIFO) of pending unit payloads (JSON).
- `p5:{lane}:ring` — LIST, the round-robin ring of owners with work; `p5:{lane}:ring:member` — SET guarding one-entry-per-owner.
- `p5:{lane}:inflight:{owner}` — **ZSET** of in-flight lease tokens → expiry epoch-ms (ZCARD = current in-flight; lease TTL is the crash-leak backstop). Member token rides in the dispatched unit so the worker can `release` exactly its slot.
- `p5:{lane}:inflight_total` — INT (global budget accounting).

### Core ops (Lua = atomic, race-free)
- `enqueue(lane, owner, unit)` — RPUSH ready; if `SADD ring:member` is new → RPUSH ring.
- `dispatch(lane, cap, budget, max_batch)` — loop: LPOP an owner; drop expired leases (ZREMRANGEBYSCORE); if `ZCARD < cap` and ready non-empty → LPOP a unit, stamp a lease (`ZADD token now+ttl`), INCR total, append to result; re-push owner to ring tail iff still has ready AND under cap, else SREM member. Stop at `budget` / empty ring / a full no-progress pass. Returns the released units (caller publishes).
- `acquire(lane, owner, cap)` → token|nil — pull-model gate: drop expired; if `ZCARD < cap` → stamp lease + INCR total, return token; else nil.
- `release(lane, owner, token)` — ZREM token, DECR total (floor 0); if ready non-empty and owner not in ring → re-arm ring (so a capped owner resumes after a slot frees).
- `reclaim_expired(lane)` — periodic: drop expired leases across owners (crash backstop) + re-arm ring.

### Invariants
- **Starvation-free:** round-robin ring gives each active owner one unit per pass; release re-arms a capped owner.
- **Crash-leak-safe:** lease TTL (generous, > max unit duration) frees a dead worker's slot; the worker's own `finally: release` is the fast path.
- **Cancel/pause coherent (reuse P3):** pause = stop dispatching the job's units (the dispatcher skips paused jobs); in-flight drains; ready units stay queued. The worker still checks the job's cancel/pause status at the unit boundary (existing guarded claim).
- **Config:** per-owner cap + global budget are env-driven (`P5_OWNER_CAP`, `P5_GLOBAL_BUDGET`), with a kill-switch (`P5_SCHED_ENABLED`, default off until live-smoked → then default on) so the legacy direct-publish path is the fallback.

## Milestones (risk boundaries → checkpoint/commit each)
- **M1 — shared scheduler primitive** (`sdks/python/loreweave_jobs/scheduler.py`): the Lua ops above + a thin async Python wrapper + unit tests (fakeredis or a real-redis gated test). ← THIS milestone first.
- **M2 — translation (PUSH)**: coordinator → `enqueue`; new `DispatcherLoop` in translation-worker → `dispatch` → publish `translation.chapter`; chapter_worker `release` + signal on terminal; flag-gated; cross-service live-smoke (the monopoly scenario: a big job + a small job interleave).
- **M3 — knowledge (PULL)**: worker-ai poll loop iterates owners round-robin + `acquire`/`release` per unit (per-owner cap); flag-gated; live-smoke.
- **M4 — lore-enrichment (PUSH/fan-out)**: same as M2 for its gap-fill runner.
- **M5 — GUI (optional)**: surface `queued` (ready, not yet dispatched) vs `running` per owner in the jobs dashboard; "N queued behind your cap".

## Deferred / later
- Priority/aging (MLFQ auto-demote) — only if cap+WFQ prove insufficient.
- Per-tier caps (different cap by plan) — config hook left, values flat for now.
