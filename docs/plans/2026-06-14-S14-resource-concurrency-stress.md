# S14 — Resource & Concurrency Stress — implementation plan

Spec: `docs/specs/2026-06-14-S14-resource-concurrency-stress.md`. Size **XL**, 5
increments, batch cadence (autonomous → one POST-REVIEW → push-ask). `/review-impl`
on this plan first, then on the impl.

## Guiding constraints
- **Both passes per drill:** CONSTRAINED (cap the resource → reachable exhaustion →
  the gate) + UNCONSTRAINED (real-hardware capture, no gate). The constrained pass
  proves graceful-degradation + recovery; the unconstrained pass records the true
  ceiling so the artificial limit is never mistaken for the real one.
- **Relative gates, no absolute thresholds.** Each drill captures its OWN baseline in
  the same run, then asserts relative bounds (degrades ≥1/N× baseline; recovers ≤Mx
  baseline; error rate bounded). N/M are conservative constants chosen per drill +
  documented, NOT prod SLOs.
- **Self-proves saturation first.** A drill that did not actually saturate the
  resource is **NOTRUN**, never PASS (non-vacuity). Each ships an explicit bite.
- **Reuse the S12 scale rig** (`infra/scale/`). Prefer dependency-free mechanisms
  (app-level bounded `pgxpool`, `docker --memory`, redis `CONFIG SET maxmemory`,
  per-container `shared_buffers`/tmpfs) over new images; `fio`/`pgbouncer` are
  OPTIONAL captures, gracefully skipped (NOTRUN) when absent.
- **Resource-exhaustion, NOT correctness** (S9/S10/S11/S6 own correctness).

## Relative-gate constants (pinned, conservative — NOT prod SLOs)
To keep the gates non-flaky AND non-vacuous, every drill uses the SAME conservative
constants unless noted: **degrade floor = throughput ≥ (1/10)× baseline**, **recovery
ceiling = ≤ 10× baseline latency/time**, **error-rate ceiling during exhaustion ≤
50%** (graceful = the system keeps making progress, not zero-error). These are wide
on purpose; the saturation self-proof + the bite are what give the drills teeth, not
tight numbers. Each drill prints baseline + observed so the constants can tighten once
a real baseline exists.

## Increment 1 — D1 Disk I/O saturation + WAL pressure + dataset>RAM thrash `[FS]`
- **Dedicated throwaway PG, NOT the shared rig shard.** `shared_buffers` is not
  runtime-settable (needs a server restart), so D1 spins its OWN PG container(s) with
  the target `shared_buffers` rather than mutating/restarting a rig shard other tests
  depend on. (Same throwaway-instance approach the tmpfs bite needs — R6.)
- **CRITICAL (review #1): `shared_buffers` alone does NOT reach disk on a 96GB box** —
  the OS page cache absorbs the whole dataset, so small `shared_buffers` only causes
  PG-*buffer* thrash, not *disk* thrash (latency never rises → vacuously green). D1
  MUST also cap the **container `--memory`** (cgroup v2 limits the page cache too) so
  the dataset genuinely exceeds available RAM and reads hit the 980 PRO. Size:
  container mem cap ≪ dataset (e.g. cap 256MB, dataset ≥ 1GB).
- `scripts/perf/s14-disk.sh`: baseline event-insert burst (generous `shared_buffers`
  + mem, warm cache) capturing committed-events/s + p99 commit latency; then a
  CONSTRAINED run (tiny `shared_buffers` + tight container `--memory` + a dataset >
  RAM → real disk thrash) + multi-instance concurrent writes (device-level fsync
  contention — N PGs each fsync their OWN WAL onto the SHARED disk). Assert graceful:
  commits keep landing, 0 write errors, throughput ≥ degrade floor, p99 ≤ recovery
  ceiling; recovers after.
- **Unconstrained capture:** `fio` raw-device IOPS/throughput if available (else
  skip-capture); express the PG write path as a fraction of raw.
- **Self-saturation proof — at the DISK level, not PG buffers** (review #1): PG
  buffer-hit ratio drops AND a disk-level signal confirms real I/O — the **tmpfs-bite
  throughput delta** (below) being large is the primary disk-bound proof; `iostat
  %util`/`blks_read`-rate as corroboration. If the constrained run is NOT meaningfully
  slower than tmpfs → NOTRUN (RAM absorbed it; the mem cap was too loose).
- **Bite:** run the SAME load on a PG whose data dir is on **tmpfs (RAM)** → throughput
  jumps sharply vs the on-disk constrained run → proves disk was the real bound (the
  drill measures the durable path, and the constrained run really hit the disk).

## Increment 2 — D2 Memory: RSS leak soak + Redis eviction `[FS]`
- `scripts/perf/s14-memory.sh`.
- **RSS soak:** run a long-lived service under sustained load in a `docker --memory`-
  capped container; sample RSS (`docker stats`) over a soak window; assert RSS slope ≈
  0 (no monotonic growth) + no OOM-kill. **Absorbs D-S12-RSS-MEMORY-SOAK.**
  - **LOCATE FIRST (review #4):** confirm a subject that runs a SUSTAINED load for the
    soak window. `metaworker-bench` may be a one-shot drain — if so, loop it (re-fill →
    drain in a loop) or pick a genuinely long-lived subject (e.g. the publisher tailing
    the outbox). Do NOT assume sustained; verify, then cap its container `--memory`.
  - **Bite:** lower `--memory` below the steady working set (or run a leaky probe) →
    OOM-kill / slope alarm fires → the detector has teeth. (R5: if WSL2 hides the
    OOM-kill, fall back to the in-process RSS-slope assertion + record the
    OOM-observability limitation as a deferred row — never fake the OOM.)
- **Redis eviction — LOCATE FIRST.** Before asserting "publisher back-pressures",
  read the publisher's XADD error path (`services/publisher/`): does it surface an
  XADD ENOMEM/OOM error and retry/back off, or swallow it? If it handles it → drive
  the drill through the real publisher. If it does NOT → that's a FINDING (record it),
  and the drill instead asserts at the Redis layer (a raw XADD past `maxmemory
  noeviction` returns an OOM error = no silent accept) so the no-loss property is still
  proven without faking publisher behavior.
  - `CONFIG SET maxmemory` very low (e.g. 1–2MB so a modest XADD burst fills it) +
    `noeviction`; fill `xreality.*` past maxmemory → XADD REJECTED (OOM error). **No
    silent loss = assert the source event is still RECOVERABLE** (review #5): the
    outbox row stays UNpublished / un-acked (so it redelivers later), NOT just that
    XADD returned an error. Verify the outbox/source state, not only the XADD return.
  - **Bite:** `maxmemory-policy allkeys-lru` → entries silently evicted → undelivered
    events lost → the no-loss check catches it (proves `noeviction` is the correct
    event-stream config). **R4: snapshot the rig redis's original maxmemory +
    maxmemory-policy and RESTORE in a trap/finally** so the shared rig is left intact.
- **Relative gate:** RSS slope ≤ ε; back-pressure surfaced (≥1 OOM error observed) not
  silently absorbed.
- **Both-passes note:** D2's "unconstrained" pass is the uncapped slope-only soak (no
  `--memory`, no `maxmemory`) — there is no separate hardware "ceiling" to capture as
  there is for D1/D3.

## Increment 3 — D3 Connection-pool exhaustion at large N `[FS]`
- **Dedicated throwaway PG (review #2):** `max_connections` is not runtime-settable
  (needs a restart), so D3 spins its OWN PG container with a low `max_connections`
  (e.g. 20) rather than restarting the shared rig shard. (Same pattern as D1.)
- `services/meta-worker/cmd/connpool-stress` (Go, reuses metapg/pgx deps) + 
  `scripts/perf/s14-connpool.sh`. Drive N ≫ `max_connections` concurrent workers.
  - **Graceful mechanism (drill):** a BOUNDED `pgxpool` (MaxConns ≤ max_connections)
    → all N units of work complete by queueing on the pool; 0 `too many clients`;
    pool recovers (in-use drains) when load drops.
  - **Bite:** the SAME load with UNBOUNDED connections (a fresh conn per op, no pool
    cap) past `max_connections` → PG `FATAL: sorry, too many clients already` →
    proves the bounded pool is what prevents exhaustion.
- **Unconstrained capture:** large-N against the real `max_connections=300` through
  the bounded pool → connection-multiplexing headroom.
- **Baseline = the pooled run at LOW concurrency** (≤ cap, no queue contention),
  captured in the same run. **Relative gate:** pooled completion rate at large-N ≥
  degrade floor × that baseline; recovery ≤ recovery ceiling; error rate bounded.
  **Self-saturation:** assert the unbounded bite actually hit the FATAL (else NOTRUN —
  the cap wasn't low enough to exhaust).

## Increment 4 — D4 Deadlock / lock-contention probe (validates the I6 ordering principle) `[FS]`
- **Honesty:** roleplay-service is `missing` (the shipped one-processor-per-session
  command processor does not exist yet — same status as S12's I6 skeleton). So D4
  tests the **ORDERING PRINCIPLE I6 relies on** (consistent global lock order ⇒ no
  deadlock), driven directly against real Postgres — NOT the shipped processor. Labeled
  as such everywhere; it proves the principle is sound, which is what I6 will enforce.
- `services/meta-worker/cmd/deadlock-probe` (Go, pgx) + `scripts/perf/s14-deadlock.sh`.
  Seed two aggregates A, B on a shard. Concurrent txns each lock multiple aggregates;
  the classic deadlock recipe is OPPOSING orders (T1: A→B, T2: B→A).
  - **Consistent-order path (the I6 principle — drill):** all txns lock in the SAME
    order → 0 `deadlock detected`, all commit, lock-wait p99 bounded; no stuck locks.
  - **Bite (review #3 — needs an interleaving BARRIER):** PG's deadlock detector only
    fires when both txns are in hold-and-wait, so the bite must orchestrate it: T1
    `SELECT … FOR UPDATE` on A, T2 on B, **both rendezvous at a barrier** (each confirms
    it holds its first lock), THEN T1 grabs B and T2 grabs A concurrently → real PG
    `deadlock detected` (≥1 txn aborted, SQLSTATE 40P01) after `deadlock_timeout`. A
    naive "fire both and hope" is racy (one may finish first → no deadlock → flaky
    NOTRUN); the barrier makes it deterministic.
- **Relative gate:** 0 deadlocks under the consistent-order path vs ≥1 under the bite;
  lock-wait p99 ≤ recovery ceiling × the uncontended baseline. **Self-proof:** the bite
  MUST produce a real 40P01 (else NOTRUN — the recipe didn't actually race).
- **Both-passes note:** D4 has no meaningful "unconstrained ceiling" capture (deadlock
  is binary); the two passes are the consistent-order drill vs the opposing-order bite.

## Increment 5 — conformance + CI + SESSION `[FS]`
- `s14-{disk,memory,connpool,deadlock}` conformance cases (`requires:[scale-rig]`,
  live-probe, → notrun in a bare runner like s12/l1).
- CI: extend `scale-build` (build/vet the 2 new Go harnesses + `bash -n` the 4
  s14-* scripts) + add an S14 live sweep to `scale-nightly` (each drill + its bite).
  **Short CI windows (review #7):** scale-nightly already runs S12 + S13-L1; S14 drills
  (esp. the RSS soak) MUST use SHORT windows in CI (e.g. soak 60s, small N/dataset) to
  avoid a nightly timeout — the long soak / large-N capture is `workflow_dispatch`/manual.
- SESSION + memory + remember; coverage note. **Close D-S12-RSS-MEMORY-SOAK.**

## Risks
- **R1 fio/pgbouncer image availability (offline).** Both are OPTIONAL captures —
  the GATE mechanisms are dependency-free (app-level bounded pgxpool; tmpfs bite;
  redis CONFIG SET; docker --memory). Missing fio/pgbouncer → capture skipped
  (NOTRUN), never a FAIL.
- **R2 96GB box won't naturally exhaust.** That's why every dimension is
  CONSTRAINED (small shared_buffers, low max_connections, docker --memory, redis
  maxmemory). The constraint is the explicit, documented analog of a prod wall.
- **R3 relative-bound flakiness.** Pick conservative N/M (e.g. ≥1/10× baseline,
  ≤10x recovery) so normal noise never trips the gate; saturation self-proof prevents
  a vacuous pass. A drill whose baseline run itself was noisy → NOTRUN + re-run.
- **R4 Redis policy mutation on a shared rig.** s14-memory MUST snapshot the rig
  redis's original `maxmemory`/`maxmemory-policy` and RESTORE them in a trap/finally,
  so the eviction drill doesn't leave the rig misconfigured for other tests.
- **R5 docker --memory on Docker Desktop/WSL2.** cgroup memory limits + OOM-kill
  semantics differ under WSL2; if `--memory` OOM-kill isn't observable, fall back to
  an in-process RSS-slope assertion (still catches a leak) + record the OOM-kill
  limitation as a deferred row rather than faking it.
- **R6 tmpfs data-dir relocation.** Re-init a PG data dir on tmpfs is heavy; the
  bite may instead spin a SECOND throwaway PG with its data dir on a tmpfs mount and
  compare its insert throughput to the on-disk shard — same conclusion (disk-bound),
  simpler. Pick whichever the rig supports; record the choice.
