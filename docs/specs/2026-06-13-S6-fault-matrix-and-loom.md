# S6 — Fault matrix + history checker + H1-loom (Batteries D + H1-loom)

**Spec date:** 2026-06-13 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** XL
**Parent plan:** `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §3 (Battery D), §9 (H1-loom)
**Depends on:** S3 (generator) ✅, S2b/C3 (ledger) ✅, S5 (B gate) ✅
**CLARIFY decisions (user, 2026-06-13):** build **both halves as one XL slice**; H1-loom uses **loom** (exhaustive, std-sync) — the tokio-async bulkhead is deferred.

---

## 0. Why two halves in one slice
The roadmap bundles S6 = **D** (Jepsen-style fault injection + history checker) **and** **H1-loom**
(kernel-local interleaving model-checking). They share a theme — *find the bugs the post-quiesce
structural oracle is blind to* — but differ in mechanism: D is **live-stack chaos** (greenfield
infra), H1-loom is **in-process Rust** race exploration. They're independent; the plan builds them
as parallel increment tracks under one task.

## 1. Honest scope corrections (from the code survey)
- **The publisher is Go and effectively single-goroutine** (two tickers → one `select` loop;
  per-reality work serialized by `FOR UPDATE SKIP LOCKED`). So "loom on outbox→publisher→apply"
  as literally written is **not** a Rust-loom target — the Go side has little in-process race
  surface, and the outbox *atomicity* (I13) is a **DB-transaction** property already model-checked
  design-altitude by S9 (`crates/foundation-model/src/outbox.rs`). loom tests **thread
  interleavings**, not SQL.
- **The genuine Rust loom target is the `dp-kernel` CircuitBreaker** (`resilience.rs:186-204`):
  `std::sync::Mutex<BreakerInner>` + `AtomicUsize` — a real concurrent state machine
  (Closed/HalfOpen/Open with windowed counters). Its bulkhead sibling uses `tokio::sync`
  (Semaphore/Notify) → **not loom-able** → deferred (`D-S6-BULKHEAD-SHUTTLE`).
- **The history checker:** the spec names Maelstrom (Jepsen Elle/Knossos, JVM). That's a heavy
  greenfield dep. v1 ships a **custom history analyzer tailored to our append-only event log**
  (the meaningful subset of Elle for an event-sourced system); full Maelstrom/Elle linearizability
  for the general meta-HA split-brain path is **deferred** (`D-S6-MAELSTROM-HISTORY`).

## 2. Half A — H1-loom (exhaustive race-check of the CircuitBreaker)
**Target:** `crates/dp-kernel/src/resilience.rs` `CircuitBreaker` sync core (`gate`/`record`/
`transition` under `Mutex<BreakerInner>` + `AtomicUsize`).
**Mechanism (standard loom pattern):**
- `[target.'cfg(loom)'.dev-dependencies] loom = "0.7"` on `dp-kernel`.
- A `sync` module alias in `resilience.rs`: `#[cfg(loom)] use loom::sync::{Mutex, atomic::*};`
  `#[cfg(not(loom))] use std::sync::{Mutex, atomic::*};` — so the SAME code runs under both, and
  loom swaps in its instrumented primitives only under `cfg(loom)`. The async `call()`/bulkhead
  paths are NOT exercised by the loom model; loom drives `record`/`gate` synchronously.
- **The loom model lives as a `#[cfg(loom)] mod loom_tests { … }` UNIT-test module INSIDE
  `src/resilience.rs`** (review-impl #2) — NOT a `tests/` integration test. Reason: integration
  tests are a separate crate and cannot reach `record()`/`BreakerInner` (private); a unit module has
  private access. No `harness = false` (loom::model runs inside a normal `#[test]`).
- **The model:** **N=2 loom threads × 1-2 ops** (review-impl #5 — keep the exhaustive state space
  small enough to stay seconds, not minutes) concurrently drive record(success/failure) against one
  breaker; loom explores ALL interleavings and asserts the invariants hold in every one:
  windowed_total ≥ windowed_failures; state ∈ valid set; transition counters monotonic; no panic;
  no lost counter update; no torn `state()` read. Measure the run time before claiming per-PR; if it
  exceeds ~a few seconds, the loom case is nightly-only.
- **Bite (non-vacuity):** a `broken` variant that reads/writes a counter OUTSIDE the lock (or a
  `state()` that reads `inner.state` lock-free) → loom must report a data race / failed assertion.
  A bite that doesn't fire is a harness bug.

## 3. Half B — Battery D (fault matrix + history checker)
### 3.1 Injection harness (greenfield)
- Add **`toxiproxy-foundation`** (`ghcr.io/shopify/toxiproxy`, pinned 2.x) to
  `infra/foundation-dev/docker-compose.yml`, on the same network, with proxies:
  `pg_proxy` → `foundation-dev-postgres:5432`, `redis_proxy` → `foundation-dev-redis:6379`.
  Admin API on `:8474`; proxy listen ports host-exposed (e.g. `:55433` pg, `:56380` redis).
- A thin **toxic driver** (`scripts/chaos/toxic.sh`, wrapping the toxiproxy HTTP API): add/remove
  `latency`, `timeout`, `bandwidth` toxics; `down`/`up` (disable/enable a proxy). No `tc`/root needed.
- Fault drills point the workload-gen / publisher DSN at the **proxy** port, so a toxic sits on the
  real data path.

### 3.2 Fault catalog — split by which path the fault hits (review-impl #1, the HIGH)
**Why the split:** C3 `against-ledger` reconciles vs the FULL deterministic seed (reports missing AND
unexpected events), and emit is **non-idempotent** (deterministic `event_id`s → unique-index conflict
on re-run). So a fault that interrupts the **emit** path leaves a partial ledger that can't be
completed and that C3 correctly flags as incomplete — "C3 log-complete after an interrupted emit" is
contradictory. The convergence oracle only applies when the workload reaches EXACTLY the seeded
end-state. That holds for faults on the **publish/apply** path (events already committed; the
publisher *retries to completion*), NOT the emit path.

**Convergence drills** (end-state == full seed → C3 + B legitimately clean) — fault the publish/apply path:
| Fault | Injection | During-fault assertion | Post-quiesce convergence |
|---|---|---|---|
| **PG slow (publish)** | `latency`+`timeout` on pg_proxy DURING the publisher's outbox drain | I16 timeouts fire; no pool-exhaustion cascade; publisher keeps draining | publisher drains to empty; **C3 log-complete**; **B drift=0**; outbox→empty |
| **Redis partition** | `down` redis_proxy while the publisher drains | publisher stalls, no crash, no event loss | publisher resumes from last XID; **no loss/dup (C3 + history §3.3)**; outbox→empty; B clean |

**Graceful-degradation drills** (NO convergence-to-seed claim — the emit is deliberately incomplete):
| Fault | Injection | Assertion |
|---|---|---|
| **PG down (emit)** | `down` pg_proxy, THEN attempt an emit | the writer **fails fast + cleanly** (error < timeout, no hang, no partial-corruption / half-written aggregate); `up`; a **fresh** emit on a clean DB converges (C3 clean). No claim that the interrupted ledger is "complete". |

Both kinds use the **deterministic bracket** (review-impl #4): inject the fault, assert a unit of work
fails/stalls *while the fault is active*, lift it, assert recovery — never race a toxic against an
in-flight sub-second batch. Sustained/transient during-fault coverage needs a loop-workload mode →
`D-S6-SUSTAINED-WORKLOAD` (deferred).

### 3.3 History recorder + during-fault checker (the part B/post-quiesce miss)
**Scope (review-impl #7):** the history checker's NEW value over C3 is the **stream-delivery**
dimension — no-loss/no-dup/ordering of `events_outbox → Redis stream`. That data exists ONLY when the
**publisher actually ran** (the convergence drills, §3.2). For append-log-only drills (no publisher)
the history reduces to events↔outbox, which C3 already covers — so the history checker is wired into
the **publisher-driven** drills, not the emit-path ones.
- **Record** the operation history across the fault window: from `events` (global_seq order), the
  `events_outbox` (published_at), and the Redis stream (XID order) — a per-aggregate timeline.
- **Analyze** (custom, append-log-tailored): **no-loss** (every committed event eventually in the
  stream), **no-dup** (no event_id twice in the stream), **per-aggregate ordering** (stream order
  respects `aggregate_version` monotonicity), **atomic outbox** (no event without its outbox row).
  This catches transient violations *during* the window that a post-quiesce C3 would miss.
- **Bite:** inject a real loss (drop an outbox row mid-fault) → the history checker must flag it.

### 3.4 Quiesce detector
Poll until: outbox count → 0 (drained) ∧ publisher heartbeat current ∧ stream lag 0 → "quiesced",
THEN run the post-quiesce oracles (C3 `-verify`, the S5 B gate, outbox-empty). A bounded timeout →
notrun (not a false green).

### 3.5 Convergence oracles (REUSED, not rebuilt)
- **C3 log-complete:** `workload-gen -verify -dsn <proxy>` (version completeness, events↔outbox, checksums).
- **B differential:** the S5 `standing-integrity-gate-smoke.sh` path (sample → replay → byte-compare).
- **Outbox drains:** `SELECT count(*) FROM events_outbox WHERE published_at IS NULL` → 0.

## 4. Conformance + CI wiring
- New `kind: live-probe` cases under `tests/conformance/catalog/generic/`:
  `fault-pg-down`, `fault-pg-slow`, `fault-redis-partition`, `loom-circuit-breaker` (rust-test),
  each `requires: ["foundation-stack"]` (+ toxiproxy boot) → notrun on bare.
- Extend the `standing-integrity-nightly` job (or a sibling `fault-drill-nightly`) to boot toxiproxy
  and run the fault battery. The loom case is a fast `cargo test` (a `loom-ci` step, since loom under
  `RUSTFLAGS=--cfg loom` is CPU-only, no stack).

## 5. Non-vacuity (every drill + the loom test has a bite)
- loom: the lock-free-counter `broken` variant → loom reports the race.
- fault drills: the **convergence oracles already have bites** (S5 `--bite`, C3 baseline); the
  history checker adds an injected-loss bite. Each drill also proves the fault was REAL (assert the
  during-fault symptom actually occurred — e.g. appends failed while PG was down — else the drill
  "passed" without injecting anything = vacuous).

## 6. Increments (each: BUILD → VERIFY → checkpoint)
1. **H1-loom** — loom dep + cfg(loom) sync alias + `#[cfg(loom)]` unit-test module in `resilience.rs`
   (2 threads × 1-2 ops) + lock-free-counter bite. (Rust, no stack; measure runtime for per-PR.)
2. **Injection harness** — toxiproxy compose service (pinned ports pre-published) + `toxic.sh` driver.
   Verify: inject latency on pg_proxy, observe added RTT live.
3. **Graceful-degradation drill: PG-down (emit path)** — deterministic bracket: down → fresh emit
   fails fast + cleanly (no partial corruption) → up → fresh emit converges (C3 clean) + fault-real assert.
4. **Publisher-driven CONVERGENCE drill + history checker (combined — review-impl #3)** — build/boot
   the Go publisher against the proxies; PG-slow-during-drain + Redis-partition; record the op-history;
   converge (C3 + B + outbox-empty) AND analyze no-loss/no-dup/ordering; injected-loss bite.
5. **2nd convergence drill** — the other of {PG-slow, Redis-partition} not finished in Inc 4, sharing
   `_lib.sh` (quiesce detector, converge, fault-real helpers).
6. **Conformance cases + CI + docs.**

## 7. Risks / deferrals
- **toxiproxy DSN routing:** consumers must dial the proxy, not the container directly — the drills
  set the DSN explicitly; production code is untouched.
- **CI cost/flakiness:** fault drills are live + timing-sensitive → nightly + `workflow_dispatch`,
  not per-PR. Quiesce timeouts → notrun, never flaky-fail.
- **Deferred:** `D-S6-MAELSTROM-HISTORY` (full Elle/Knossos linearizability for meta-HA split-brain),
  `D-S6-BULKHEAD-SHUTTLE` (async bulkhead via shuttle), `D-S6-PARTITION-ROLLOVER` (partition-boundary
  fault), `D-S6-META-HA-SPLITBRAIN` (Patroni split-brain drill — needs an HA meta cluster the
  dev compose doesn't have), `D-S6-SUSTAINED-WORKLOAD` (loop-workload mode for genuine transient
  during-fault coverage on an in-flight batch, vs the deterministic bracket).
- **Honesty:** the publisher's limited Go race surface means H1 assurance is the CircuitBreaker, not
  the full outbox path; that's tracked, not papered over.
