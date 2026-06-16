# Wave 2 — Spine hardening & fault coverage (spec)

**Status:** CLARIFY → DESIGN. Size **XL** (bundled). One task per the batch cadence:
spec+plan once, `/review-impl` plan + impl, autonomous through increments → one
POST-REVIEW → push-ask.

## Why

After the S1–S14 test program + Wave 1 production wiring, the architecture is
validated and L1 is production-runnable. Wave 2 is the **Category A** do-now slice
from `docs/plans/2026-06-14-post-S14-deferred-cleardown.md`: deeper fault/coverage
that the S1–S14 batteries left as deferred technique. Each item un-vacuums or
extends an existing battery; none is production wiring.

CLARIFY (2026-06-15): **one bundled XL task**; the drills WSL2 can't truthfully
run (disk read-thrash needs fio+cgroup; clock-skew needs libfaketime; real-service
RSS needs `/proc`) are **built now + CI-verified on the Linux nightly**, and
honestly report `notrun`/`skip` on the Windows/WSL2 dev box (the S14 precedent).

## Items (cleardown Wave 2)

### W2.1 — Sustained-workload generator mode (closes D-S6-SUSTAINED-WORKLOAD)
- `tests/workload-gen` is one-shot (burst → emit/verify → exit). Add a
  **steady-rate loop**: `-duration <secs>` + `-rate <events/sec>` → repeatedly
  generate (seed delta per iteration → fresh aggregate ids, no version collision)
  + emit, paced to the rate, until duration elapses.
- **Prerequisite for the wave:** genuine *transient-during-fault* (W2.3 soak,
  W2.2 history under load) needs a workload that keeps running while a fault is
  injected — not a single burst that finishes before the fault lands.
- **Bite:** a "sustained" run whose loop is broken (exits after 1 iteration) emits
  ≪ `rate×duration` events → the sustained-throughput assertion catches it.
- **Dev box:** local ✓ (writes to a PG via the existing `-emit`).

### W2.2 — History ordering: per-aggregate version monotonicity (closes D-S6-HISTORY-ORDERING)
- The ledger checker (`internal/ledger`) checks per-aggregate version
  *completeness* (no gaps in 1..N) but NOT *monotonicity over the stream's
  recorded order*. Add a check that replays events in `recorded_at` order and
  asserts `aggregate_version` is strictly increasing per
  `(reality_id, aggregate_type, aggregate_id)` — catching a reorder/dup that a
  set-completeness check passes.
- **Bite:** inject an out-of-order pair (version N+2 recorded before N+1) → the
  monotonicity check FAILS; the completeness check would still pass (proving the
  new check adds coverage).
- **Dev box:** local ✓ (PG).

### W2.3 — Service RSS soak + disk read-thrash (closes D-S14-SERVICE-RSS-SOAK, D-S14-DISK-READ-THRASH)
- **3a Service RSS soak (Linux-CI):** S14's `rss-soak` is an in-process pure-alloc
  loop. Soak the **real** long-lived publisher: spawn `services/publisher` as a
  subprocess, drive W2.1 sustained load through it, sample `/proc/<pid>/status`
  `VmRSS` over the window, assert a plateau (end ≤ 1.5× the post-warmup base).
  - **Bite:** the in-process count-bounded retain (S14 mechanism) proves the
    plateau detector is non-vacuous (a real service can't be made to leak on
    demand without a debug hook; the mechanism-level bite is the honest proof).
- **3b Disk read-thrash (Linux-CI):** dataset > cgroup-constrained RAM, `fio`
  random-read → page-cache thrash. Assert the read path stays correct under the
  thrash; **bite** = dataset < RAM (fits in page cache) → no thrash → proves the
  cache-eviction is the measured bound (the S14 D1 write-path complement).
- **Dev box:** both **Linux-CI-only** → `notrun` on WSL2 (no `/proc` for a
  Windows-built binary; cgroup can't constrain the WSL2 page cache).

### W2.4 — Clock-skew recovery + partition-boundary rollover (closes D-S8-CLOCK-SKEW-RECOVERY, D-S6-PARTITION-ROLLOVER)
- **4a Clock-skew recovery (Linux-CI):** inject clock skew via `libfaketime`
  (LD_PRELOAD) on a service under sustained load → assert recovery/correctness
  (the spine's `recorded_at` ordering + publisher heartbeat survive a skew/rewind).
  **Bite:** the assertion with skew NOT applied vs applied (or a property that
  only a clock-aware path satisfies). **Dev box:** Linux-CI-only.
- **4b Partition-boundary rollover (local):** the per-reality `events` table is
  monthly RANGE-partitioned. Write events spanning a month boundary (explicit
  `recorded_at` — no real clock needed), create the next-month partition, replay
  → assert no loss across the boundary. **Bite:** write a next-month event with
  the partition MISSING → INSERT rejected (no partition) → proves the partition
  must exist (the rollover is load-bearing). **Dev box:** local ✓ (PG).

### W2.5 — Async bulkhead shuttle race-check (closes D-S6-BULKHEAD-SHUTTLE)
- The tokio `Bulkhead` (`crates/dp-kernel/src/resilience.rs`, `tokio::Semaphore` +
  queue) has NO concurrency race-check — loom (the breaker-core check) can't model
  tokio async. Add a **`shuttle`** test (cfg-gated dev-dep) exercising concurrent
  `Bulkhead::call()` under shuttle's scheduler: assert `active ≤ max_concurrent`,
  rejected-count accuracy, no deadlock, across all interleavings.
- **Bite:** a deliberately-racy invariant (mirror the loom bite) → shuttle catches
  it. **Dev box:** local ✓ (shuttle is pure Rust, builds on Windows).

### W2.6 — conformance + CI + SESSION
- `w2-*` conformance cases (kind/requires gated per item — `cargo`/`scale-rig`/
  `linux` as appropriate); CI: per-PR build/vet/`bash -n` + a `bulkhead-shuttle`
  per-PR job (CPU-only, like loom-ci); nightly extends with the live + Linux-only
  drills. SESSION + memory + close the 6 deferred rows.

## Out of scope (→ later / go-live)
- The cycle-9 partition-manager service + cycle-11 archive-worker partition detach
  (W2.4b uses explicit partitions, not the manager). HA/multi-host. The remaining
  Wave 3/4 cleardown items.

## Acceptance
Each item: a drill with a non-vacuity bite + a `w2-*` conformance case + CI. The
4 locally-verifiable items (W2.1, W2.2, W2.4b, W2.5) are live-proven on the dev
box; the 3 Linux-only (W2.3a, W2.3b, W2.4a) are built + wired into the Linux
nightly and `notrun` locally. SESSION updated; 6 deferred rows closed; the
cleardown Wave-2 box checked.
