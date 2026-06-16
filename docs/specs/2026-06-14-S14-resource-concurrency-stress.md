# S14 — Resource & Concurrency Stress (spec)

**Status:** CLARIFY → DESIGN. Size **XL**. Post-arc slice (after S1–S13).
Author: Claude (Opus 4.8). Date: 2026-06-14.

## Why

S12 proved the architecture *scales* (throughput on cheap axes; the I7 XACK ceiling
fixed). S9/S10/S11/S6 proved *concurrency correctness* (model-check, DST, fault
matrix, loom). **The remaining gap is resource exhaustion UNDER concurrency** — what
happens when disk, memory, the connection pool, or the lock manager hits its wall
while many realities/sessions hammer the box. In an MMO "song song là cơn ác mộng"
(parallelism is the nightmare): the system must degrade *gracefully* and *recover*,
never crash / corrupt / deadlock / silently drop data.

**S14 is resource-exhaustion, NOT correctness.** Correctness under concurrency is
already covered; S14 asks "does the system stay safe when a resource runs out?"

## CLARIFY decisions (2026-06-14, user)

1. **Scope = all four dimensions** (disk I/O, memory, connection-pool, deadlock/locks).
2. **Both passes:** a CONSTRAINED drill (artificially cap the resource so exhaustion is
   reachable on the 96GB/i9 dev box → the pass/fail gate) **plus** an UNCONSTRAINED
   capture pass (real-hardware curves, no gate). The constraint is the honest
   single-box analog of a production resource wall.
3. **Discipline = mechanism + recovery + bite + relative gates.** Every drill proves
   (a) the resource genuinely saturates, (b) the system degrades gracefully (no
   crash/corruption/deadlock/loss), (c) it RECOVERS when load drops, and (d) a
   **non-vacuity bite**. PLUS **relative regression bounds** (e.g. recovery within Nx
   of a captured baseline, error-rate ceiling) — NO absolute pre-baseline thresholds
   (the S7/S12 rule), but relative gates ARE asserted.

## The four dimensions

### D1 — Disk I/O saturation + WAL pressure + dataset>RAM thrash
- **Constrained:** a shard PG with small `shared_buffers` + production fsync; drive
  heavy event-insert load (the spine T2 write shape) + a dataset larger than
  shared_buffers → forces buffer eviction + disk reads (cache thrash). Multi-shard
  concurrent writes → WAL fsync contention. Capture committed-events/s + p99 commit
  latency as disk saturates; assert **graceful**: commits keep landing, no write
  errors, latency rises but BOUNDED; recovers when load drops.
- **Unconstrained:** same load on the real 980 PRO, no buffer cap → capture the
  real-hardware ceiling. `fio` measures the raw device IOPS/throughput ceiling so the
  PG write path can be expressed as a fraction of raw (not a collapse).
- **Relative gate:** under thrash, committed-events/s stays ≥ (1/N)× the unthrashed
  baseline (degrades, doesn't collapse); p99 commit latency ≤ Mx baseline.
- **Bite:** move the shard's data dir to **tmpfs (RAM)** → throughput jumps sharply →
  proves disk was the real bound (the drill measures the durable path, not RAM).

### D2 — Memory: RSS leak soak + Redis eviction (absorbs D-S12-RSS-MEMORY-SOAK)
- **RSS leak soak (constrained):** run a long-lived service (publisher and/or
  meta-worker) under sustained load inside a container with a `--memory` cap; sample
  RSS over a soak window. Assert RSS **plateaus** (slope ≈ 0) and NO OOM-kill.
  - **Bite:** lower the `--memory` cap below the steady-state working set (or run a
    deliberately leaky loop) → OOM-kill / RSS-slope alarm fires → proves the
    leak/OOM detector has teeth.
- **Redis eviction (constrained):** set `maxmemory` + the SAFE policy
  `noeviction`; fill the `xreality.*` streams past `maxmemory` → new XADD is REJECTED
  (publisher sees the error + backs off) rather than silently dropping undelivered
  events. Assert: no silent loss; the publisher surfaces the back-pressure.
  - **Bite:** switch policy to `allkeys-lru` → stream entries SILENTLY evicted →
    undelivered events lost → the no-loss check catches it. Proves `noeviction` is the
    correct config for an event-stream (LRU would lose data).
- **Relative gate:** RSS slope over the soak ≤ small ε (no monotonic growth);
  back-pressure error rate visible but bounded.

### D3 — Connection-pool exhaustion at large N
- The S12 `max_connections=300` wall (capped the rig at ~20 realities). **Constrained:**
  cap `max_connections` low (e.g. 20) with **pgbouncer (transaction pooling)** in
  front; drive N ≫ cap concurrent clients → pgbouncer QUEUES (graceful) while direct
  connections would exhaust. Assert: clients complete (queued), no crash; the pool
  recovers (queue drains) when load drops; error rate during exhaustion bounded.
- **Unconstrained:** drive large-N against the real `max_connections=300` through
  pgbouncer → capture the connection-multiplexing headroom.
- **Relative gate:** with the pool, completion rate ≥ (1/N)× baseline + recovery time
  ≤ Mx baseline; error rate bounded.
- **Bite:** bypass the pool (direct connections past `max_connections`) → PG
  `FATAL: sorry, too many clients already` → proves the pool is what prevents
  exhaustion (without it, N>max → hard failures).

### D4 — Deadlock / lock-contention probe (validates I6)
- I6 claims multi-aggregate deadlocks are *solved* by one-command-processor-per-session
  serial FIFO. **Probe:** the classic deadlock recipe — concurrent transactions each
  locking multiple aggregates in OPPOSING orders (T1: A→B, T2: B→A). Under I6's
  serial-per-session ordering the opposing-order interleave cannot occur → **no PG
  deadlock**; lock waits stay bounded. Assert: 0 `deadlock detected`, all txns commit,
  lock-wait p99 bounded; recovers (no stuck locks) after.
- **Bite:** bypass I6 — fire the opposing-order concurrent txns DIRECTLY (no
  serialization) → real PG `deadlock detected` (one txn aborted) → proves I6's
  ordering is what prevents the deadlock (not luck).
- **Relative gate:** lock-wait p99 ≤ Mx baseline under contention; 0 deadlocks under
  I6 vs ≥1 under the bite.

## Honesty rails (single box)

- **Constraint ≠ cheating.** Capping memory/connections/shared_buffers is the honest
  way to reach a prod resource wall on one box; the UNCONSTRAINED pass records the real
  hardware so we never mistake an artificial limit for the real ceiling.
- **No absolute thresholds pre-baseline** (S7/S12 rule). Each drill captures its own
  baseline in the same run, then asserts RELATIVE bounds against it.
- **Every drill self-proves saturation** before asserting graceful-degradation — a
  drill that didn't actually saturate the resource is NOTRUN, not PASS (non-vacuity).
- **Reuses the S12 scale rig** (`infra/scale/`) + adds pgbouncer + resource-capped
  variants; new tooling under `scripts/perf/` + small Go/SQL harnesses.

## In / Out

- **IN:** the 4 exhaustion dimensions, each constrained-gate + unconstrained-capture +
  bite + relative bound; conformance cases + CI; SESSION.
- **OUT:** concurrency CORRECTNESS (S9/S10/S11/S6 + S12 I6 bite); multi-host
  (D-S12-MULTI-HOST); absolute SLOs (no production baseline exists yet).

## Acceptance

Each dimension ships: a constrained drill that saturates + proves graceful
degradation + recovery (relative gate) + a non-vacuity bite + an unconstrained capture;
a `requires:[scale-rig]` conformance case; a CI wiring (build/vet + nightly live
sweep); SESSION updated. Absorbs **D-S12-RSS-MEMORY-SOAK**; records any new gaps.
