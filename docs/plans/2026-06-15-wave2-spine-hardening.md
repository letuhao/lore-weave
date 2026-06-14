# Wave 2 — Spine hardening & fault coverage — implementation plan

Spec: `docs/specs/2026-06-15-wave2-spine-hardening.md`. Size **XL**, 6 increments,
batch cadence (autonomous → one POST-REVIEW → push-ask). `/review-impl` plan
first, then impl. Each increment ships a non-vacuity **bite** + a `w2-*`
conformance case; the 3 Linux-only drills are CI-verified (notrun on WSL2).

## Guiding constraints
- **Reuse the rig + patterns:** the S12 scale rig (meta-pg + pg-shard-0), the S6
  chaos-script shape (`scripts/chaos/*.sh`), the S14 throwaway-container pattern,
  the loom-ci shape for the shuttle job. Locate-first confirmed (recon map).
- **Non-vacuity discipline:** every check must be ABLE to fail; prove it with a
  bite. For the Linux-only drills the bite must be expressible in the same script
  so the Linux nightly proves it (not just the happy path).
- **Honest dev-box reporting:** a drill that needs Linux infra detects its absence
  and exits `notrun` (rc=2) with a clear reason — never a false pass.

## Increment order (dependency-aware)
W2.1 (sustained) **first** — W2.3 soak + W2.2-under-load consume it. Then W2.2 →
W2.4b (partition, local) → W2.5 (shuttle, local, independent) → W2.3 + W2.4a
(Linux-only, grouped last so the local battery is green before the CI-only work) →
W2.6 (conformance/CI/SESSION).

## Increment 1 — W2.1 sustained-workload mode `[BE/Go]` (local)
- `tests/workload-gen/cmd/workload-gen`: add `-duration <secs>` + `-rate <eps>`.
  When `-duration > 0`, `run` enters a paced loop: each tick generate a fresh
  batch (`gen.Generate(profile)` with **seed = base + iteration** so aggregate ids
  don't collide) → emit; sleep to hold ~`rate` events/sec; stop at `duration`.
  Emits a running JSON summary `{emitted, elapsed_s, target}`.
- Keep one-shot behavior when `-duration` is unset (back-compat — soak.sh /
  fault-redis-partition.sh call the burst form).
- **Locate-first at build:** the seed→aggregate-id derivation in `internal/gen`
  (confirm a seed delta yields disjoint aggregate ids, not a reshuffle of the same
  ids — else versions WOULD collide across iterations).
- **Drill + bite** (`scripts/perf/w2-sustained.sh`): run `-duration 5 -rate 200`
  → assert `emitted ∈ [rate×dur×0.7, rate×dur×1.3]` AND `elapsed ≈ duration`.
  **Bite:** `-rate 0` (or an env that forces single-iteration) → emits one burst
  ≪ target → caught. Unit test the pacing math (no DB).

## Increment 2 — W2.2 history ordering monotonicity `[BE/Go]` (local)
- `tests/workload-gen/internal/ledger`: add `CheckAggregateMonotonicity(log)` —
  iterate events in `recorded_at` (tiebreak a stable seq) order; per
  `(reality_id, aggregate_type, aggregate_id)` track the last version and assert
  the next is exactly `last+1` (strictly increasing, no gap, no dup, no reorder).
  Distinct from `checkVersionCompleteness` (set has no gap) — this is ORDER over
  the stream. Returns a `Report` consistent with the existing checker.
- **Drill + bite** (`scripts/perf/w2-history.sh`, reuses the rig PG): emit a
  workload → read events ordered by `recorded_at` → monotonicity PASS. **Bite:**
  inject an out-of-order row (a version `N+2` with a `recorded_at` BEFORE `N+1`)
  → monotonicity FAILS while completeness still PASSES (proves the new check is
  the one that catches reorder). Unit test the checker over an in-memory log
  (ordered ok; reordered → fail) — the non-vacuity lives in the unit + the live bite.

## Increment 3 — W2.4b partition-boundary rollover `[BE/Go]` (local)
- New drill `scripts/perf/w2-partition.sh` + a small Go probe (reuse the
  meta-worker module or a throwaway PG): create a per-reality `events` table
  (migration 0002, monthly RANGE) on a throwaway/rig DB; ensure partitions for
  month M and M+1 exist; INSERT events with explicit `recorded_at` in M and M+1
  (spanning the boundary); read/replay across the boundary → assert count + order
  preserved (no loss, monotonic per aggregate — reuses W2.2).
- **Bite:** drop/omit the M+1 partition, INSERT an M+1 event → Postgres rejects
  ("no partition of relation events found for row") → proves the next-month
  partition must be provisioned (the rollover is load-bearing; silent loss is
  impossible because the INSERT fails loudly).
- **Locate-first:** how 0002 names/creates partitions (`events_p_YYYY_MM`) +
  whether a default partition exists (if a DEFAULT partition catches overflow, the
  bite changes to "lands in default, not the month partition" — confirm at build).

## Increment 4 — W2.5 async bulkhead shuttle `[BE/Rust]` (local, CPU-only)
- Add `shuttle` as a `cfg(shuttle)` dev-dependency to `crates/dp-kernel`
  (mirrors breaker-core's `cfg(loom)` loom dep). New `#[cfg(shuttle)]` test module
  (inline in `resilience.rs` or `resilience_shuttle.rs`): under
  `shuttle::check_random` (or `check_dfs` bounded), spawn K tasks contending for a
  `Bulkhead{max_concurrent, queue_depth}` via `Bulkhead::call`; assert invariants
  hold across interleavings: `active ≤ max_concurrent` always, total
  `completed + rejected == K`, no deadlock (all tasks finish), rejected count
  matches the over-capacity arrivals.
- **shuttle vs tokio:** shuttle replaces `tokio::sync::Semaphore` with its own
  model only under `cfg(shuttle)`. **Locate-first:** confirm `Bulkhead` uses
  `tokio::sync` primitives shuttle can intercept; if it uses a primitive shuttle
  can't model, the test wraps the contended core in a shuttle-friendly shim (note
  the limitation honestly rather than a vacuous green).
- **Bite:** a deliberately-racy variant (e.g. a non-atomic `active` counter or a
  check-then-acquire gap) compiled only for the bite → shuttle finds an
  interleaving violating `active ≤ max_concurrent` (mirrors the loom
  `bite_unsynchronized_counter` pattern). Gated so the bite is a `should_panic`.
- CI: a per-PR `bulkhead-shuttle` job (`RUSTFLAGS=--cfg shuttle cargo test -p
  dp-kernel ...`), fast, like loom-ci.

## Increment 5 — W2.3 + W2.4a (Linux-only, CI-verified) `[BE]`
- **W2.3a service RSS soak** (`scripts/perf/w2-rss-soak.sh` + a small Go runner if
  needed): detect Linux + `/proc` (else `notrun`); spawn the REAL `services/
  publisher` subprocess against the rig, drive W2.1 sustained load for the window,
  sample `/proc/<pid>/status` `VmRSS` every interval, assert plateau (end ≤ 1.5×
  post-warmup base). **Bite:** reuse the S14 in-process count-bounded retain
  (`rss-soak -mode bite`) as the mechanism-level non-vacuity proof (plateau
  detector CAN fail), documented as such.
- **W2.3b disk read-thrash** (`scripts/perf/w2-disk-read.sh`): detect Linux +
  `fio` + cgroup (else `notrun`); `fio` random-read a dataset > a cgroup mem cap
  → high cache-miss read latency. **Bite:** dataset < the cap (fits page cache) →
  fast reads → contrast proves the eviction is the bound. (Complements S14 D1
  write-fsync.)
- **W2.4a clock-skew recovery** (`scripts/perf/w2-clock-skew.sh`): detect Linux +
  `libfaketime` (else `notrun`); LD_PRELOAD faketime on the publisher under load,
  apply a skew/rewind, assert recovery (heartbeat resumes; `recorded_at` ordering
  / W2.2 monotonicity still holds after the skew). **Bite:** a property that only
  holds with the skew-tolerant path (or skew-off vs skew-on contrast).
- All three: `notrun` (rc=2) with a clear reason off-Linux; the Linux nightly is
  where they actually run + prove their bites.

## Increment 6 — conformance + CI + SESSION `[FS]`
- `w2-*` conformance cases: `w2-sustained`, `w2-history`, `w2-partition`
  (requires:[scale-rig]); `w2-bulkhead-shuttle` (kind:rust-test, requires:[cargo]);
  `w2-rss-soak`, `w2-disk-read`, `w2-clock-skew` (requires:[scale-rig] + a `linux`
  marker → notrun off-Linux / on the bare runner).
- CI: extend `scale-build`/`w1-rust-build` (build/vet/`bash -n` the W2 Go + scripts
  + `cargo build` the shuttle module) + a new per-PR `bulkhead-shuttle` job;
  `scale-nightly` gains the W2 live + Linux-only drill steps.
- SESSION + memory + prune; **close D-S6-SUSTAINED-WORKLOAD, D-S6-HISTORY-ORDERING,
  D-S6-PARTITION-ROLLOVER, D-S6-BULKHEAD-SHUTTLE, D-S14-SERVICE-RSS-SOAK,
  D-S14-DISK-READ-THRASH, D-S8-CLOCK-SKEW-RECOVERY.** Check the cleardown Wave-2 box.

## Risks
- **R1 shuttle ↔ tokio fit.** If `Bulkhead` uses a tokio primitive shuttle can't
  intercept under `cfg(shuttle)`, the race-check is vacuous. Mitigation:
  locate-first the semaphore type; if needed, model the contended core with
  shuttle's sync primitives + document the boundary (never a fake green). The bite
  proves the harness catches a real race before any invariant rides on it.
- **R2 sustained seed→aggregate-id collision.** If a seed delta reshuffles the
  SAME aggregate ids, sustained iterations would write conflicting versions →
  false version errors. Mitigation: confirm disjoint ids per seed at build; else
  derive a per-iteration reality/aggregate namespace.
- **R3 Linux-only drills unverifiable locally.** W2.3a/3b/4a can't run on WSL2.
  Mitigation (user-approved): build + `bash -n` + the Linux nightly is the real
  gate; each script self-detects and `notrun`s off-Linux with a reason, so a green
  local run never implies they passed.
- **R4 partition default-partition.** If 0002 ships a DEFAULT partition, the
  rollover bite (missing-partition INSERT) wouldn't fail. Confirm at build; if a
  default exists, the bite becomes "row lands in DEFAULT not the month partition →
  archive/replay-by-month misses it."
- **R5 history-ordering tiebreak.** `recorded_at` can tie at sub-ms; the
  monotonicity check needs a stable secondary order (a seq/ctid) or it could
  false-flag a same-timestamp pair. Use a deterministic tiebreak.
