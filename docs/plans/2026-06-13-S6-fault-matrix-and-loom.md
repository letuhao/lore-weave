# S6 — Build plan (Fault matrix + history checker + H1-loom)

**Plan date:** 2026-06-13 · **Size:** XL · **Spec:** `docs/specs/2026-06-13-S6-fault-matrix-and-loom.md`
Two parallel increment tracks under one task: **H1-loom** (Inc 1) and **Battery D** (Inc 2-6).

## Increment 1 — H1-loom: exhaustive CircuitBreaker race-check
**Files:** `crates/dp-kernel/Cargo.toml` (+`[target.'cfg(loom)'.dev-dependencies] loom="0.7"`),
`crates/dp-kernel/src/resilience.rs` (cfg-gated `sync` import alias + a `#[cfg(loom)] mod loom_tests`
UNIT-test module — private access to `record`/`BreakerInner`, NOT a `tests/` integration test, NO
`harness=false`; review-impl #2).
**Build:** swap `std::sync::{Mutex, atomic::*}` → a module alias selecting `loom::sync` under
`cfg(loom)`; the loom model spawns **2 threads × 1-2 ops** (review-impl #5) driving
`record(success/failure)` + reading `state()`; assert in-every-interleaving invariants (total≥failures,
valid state, monotonic transition counters, no panic, no torn `state` read). A `broken` variant
(lock-free counter / torn `state` read) for the bite.
**Verify:** `RUSTFLAGS="--cfg loom" cargo test -p dp-kernel loom_tests` green (explores >1 interleaving
— assert loom's branch count); the bite variant FAILS under loom (data race / assertion). **Time the
run** — if > ~a few seconds, the loom case is nightly-only (not per-PR). Also `cargo build --workspace`
+ `cargo test -p dp-kernel` (non-loom) still green (the cfg alias must not regress the normal build).
**Bite:** lock-free counter access under loom → loom reports a race; removing it → green.

## Increment 2 — Injection harness (toxiproxy)
**Files:** `infra/foundation-dev/docker-compose.yml` (+`toxiproxy-foundation` service, pinned 2.x;
admin :8474; **proxy listen ports pinned + published** — pg_proxy :55433, redis_proxy :56380, since
toxiproxy binds them at runtime and Docker only forwards declared ports, review-impl #6),
`scripts/chaos/toxic.sh` (HTTP-API driver: `create-proxy`, `add-latency`, `add-timeout`, `down`,
`up`, `reset`). Setup (migrations/psql) goes DIRECT; only the workload DSN goes through the proxy.
**Verify (live):** boot toxiproxy; create pg_proxy→postgres; baseline `psql` RTT via the proxy;
`add-latency 500ms`; assert RTT jumps ~500ms; `reset`; RTT back to baseline. (Proves the toxic sits
on the real path.)
**Bite:** n/a (harness, not an oracle) — but the RTT-delta assertion IS the proof the toxic took effect.

## Increment 3 — Graceful-degradation drill: PG-down (emit path) — review-impl #1/#4
**Files:** `scripts/chaos/fault-pg-down.sh`. NO convergence-to-seed claim (emit is non-idempotent;
an interrupted emit can't be completed and C3 would flag it incomplete).
**Flow (deterministic bracket):** boot stack+toxiproxy; `down` pg_proxy; attempt `workload-gen -emit
-dsn <pg_proxy>` → **assert it fails FAST + cleanly** (error < timeout, no hang, and the DB has NO
partial/half-written aggregate — the fault-real + no-corruption guard); `up`; a **fresh** emit on a
clean shard DB → `workload-gen -verify` (C3) clean. Proves graceful failure + clean recovery.
**Verify (live):** drill exits 0; emit-under-down failed fast; fresh emit converged C3-clean.

## Increment 4 — Publisher-driven CONVERGENCE drill + history checker (combined — review-impl #1/#3)
**Files:** `scripts/chaos/_lib.sh` (quiesce detector, converge=C3+B+outbox-empty, fault-real helpers),
`scripts/chaos/fault-redis-partition.sh`, `tests/workload-gen/internal/history/history.go` (+ a
`-history` mode or `cmd/history-check`: record events.global_seq + outbox.published_at + redis XID →
analyze no-loss / no-dup / per-aggregate ordering / atomic-outbox → verdict + JSON to results/).
**Dependency (called out, not a side note):** this needs the **Go publisher binary built + booted**
against the proxies (it drains outbox→Redis) — the heaviest piece of S6.
**Flow:** seed (committed events, DIRECT) → start publisher draining outbox→Redis via redis_proxy →
`down` redis_proxy mid-drain → assert publisher stalls, no crash, no loss → `up` → publisher resumes
from last XID → quiesce → converge (C3 + B + outbox-empty) + history checker clean.
**Verify (live):** drill exits 0; fault-real fired; converged; history clean. **Bite:** drop one
outbox row mid-fault → history checker flags the loss (the clean→injected-loss teeth).

## Increment 5 — 2nd convergence drill: PG-slow (publish path)
**Files:** `scripts/chaos/fault-pg-slow.sh` (reuses `_lib.sh`).
**Flow:** seed → publisher draining → `latency`+`timeout` on pg_proxy DURING the drain → assert I16
timeouts fire, no pool-exhaustion cascade, publisher keeps making progress → remove → quiesce →
converge (C3 + B + outbox-empty).
**Verify (live):** drill exits 0; timeouts observed; converged clean.

## Increment 6 — Conformance cases + CI + docs
**Files:** `tests/conformance/catalog/generic/{fault-pg-down,fault-pg-slow,fault-redis-partition,
loom-circuit-breaker}.yaml`; `.github/workflows/conformance-ci.yml` (a `fault-drill-nightly` job
booting toxiproxy + a fast `loom-ci` step `RUSTFLAGS=--cfg loom cargo test -p dp-kernel`);
`docs/sessions/SESSION_PATCH.md` + deferred rows.
**Verify:** each case through the runner via the isolated temp-catalog pattern (Git Bash on PATH for
the env-propagation, as S5); loom case green via `cargo test`; YAML parses.

## Cross-cutting
- **VERIFY honesty:** fault drills are live + timing-sensitive → nightly/`workflow_dispatch`, not
  per-PR. The loom case IS per-PR-able (CPU only). Quiesce timeouts → notrun.
- **Deferred rows to open:** `D-S6-MAELSTROM-HISTORY`, `D-S6-BULKHEAD-SHUTTLE`,
  `D-S6-PARTITION-ROLLOVER`, `D-S6-META-HA-SPLITBRAIN`, `D-S6-SUSTAINED-WORKLOAD` (loop-workload for
  transient during-fault coverage vs the deterministic bracket).
- **`/review-impl` on this plan** (user cadence) before BUILD; then per-increment checkpoints.
