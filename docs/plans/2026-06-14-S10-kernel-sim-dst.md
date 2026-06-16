# S10 — Kernel sim DST — implementation plan

Spec: `docs/specs/2026-06-14-S10-kernel-sim-dst.md`. Size **XL**. 6 increments, batch cadence
(autonomous through increments → one POST-REVIEW → push-ask). `/review-impl` on this plan first.

## Guiding constraints
- **Spike-first**: Inc-1 RETIRES the madsim-vs-VOPR-executor feasibility risk empirically before any
  oracle is built. No theorizing past Inc-1.
- **Non-vacuity**: every oracle ships with a bite-test (a deliberate corruption the assert must catch).
  travel = honest deferral, never a fake stub.
- **Reuse the standalone-module pattern** (`tests/perf/`, `tests/conformance/`): `tests/sim/` is its own
  crate, NOT a workspace member that could drag a tokio-patch over the whole repo.

## Increment 1 — Feasibility spike + sim harness skeleton  `[FS]`
**Goal:** stand up `tests/sim/` and resolve Path A (madsim) vs Path B (self-owned VOPR executor), AND
establish where interleavings come from (the harness's self-non-vacuity proof).
- New isolated crate `tests/sim/Cargo.toml` (path-dep on `dp-kernel` + `crates/projections/*`; NOT added
  to root workspace members if that would force the patch repo-wide — verify the isolation first).
- **`SimEventStore` (review MED-2):** the sim owns a small `EventStore` impl (same trait + the
  `expected_version` CAS semantics from `event_store.rs:497`) with crash/fault hooks — NOT the kernel's
  non-API `InMemoryEventStore`. This is the substrate all oracles ride on.
- **Try Path A first:** add madsim dev-dep + the tokio `[patch]`; build a trivial test that spawns 2 sim
  tasks appending to `SimEventStore` under madsim's runtime. Record: does it compile past the sqlx link?
  Does a seeded run reproduce?
- **If Path A fails to build (sqlx wall):** implement Path B — a `Sim` struct owning `ChaCha8Rng(seed)` +
  a virtual clock + a ready-queue; `Sim::run(seed)` steps tasks in a seed-determined order. **Precondition
  (review MED-3):** the in-sim async surface must be reactor-free (no `tokio::time`/`net`/`spawn`) — verify
  `SimEventStore` ops are Mutex-locks with no IO await, so any executor can poll them.
- **Interleaving SOURCE (review MED-3):** actors `await sim.yield()` between ops; the seed-driven scheduler
  picks the ready-task order at each yield. Without these yield points the futures complete synchronously
  and the sim is single-path → vacuous. Name + implement this explicitly.
- **Gate (proves the harness itself is sound):** a hello-world sim run is byte-reproducible — same seed ⇒
  identical event-application trace; **bite:** a different seed ⇒ a different trace (proves the scheduler
  actually varies the interleaving via the yield points, i.e. the sim is not vacuously single-path).
- **Also in Inc-1 (review MED-1):** grep/confirm whether a Rust aggregate lifecycle state-machine exists
  (no double-spawn / illegal-transition guard) or whether that logic is Go-only — decides Oracle-3 scope.
- **Deliverable:** chosen path + the lifecycle-semantics verdict recorded in `tests/sim/README.md` + green
  skeleton.

## Increment 2 — Projection-convergence oracle (review HIGH-2)  `[BE]`
- N sim actors concurrently deliver an aggregate's events to the **real `crates/projections/*`
  `Projection::apply_event`** in a seed-chosen order, over `SimEventStore`. Actor/op count scale with seed.
- Then re-apply via the **real replay** in canonical `(aggregate_version)` order; byte-compare the two
  projection states. Mismatch ⇒ print seed + schedule, fail. **Both sides call the real crates** (no
  hand-rolled re-impl → no common-mode vacuity).
- **Name it precisely:** `apply(legal interleaving) == apply(canonical replay)` — the H1 *convergence*
  property. Does NOT replace S5's Go-vs-Rust differential (documented in the case description).
- **Bite:** a projector arm made order-sensitive (last-writer-wins on a field that should be commutative)
  → the two orders diverge. (Gated `SIM_BITE=1`, like S7/S8.)
- Seed sweep: default 64 seeds (`SIM_SEEDS` override); all clean.

## Increment 3 — Append-batch atomicity under crash (review HIGH-1)  `[BE]`
- Fault hooks on `SimEventStore` + clock: (a) clock skew/jumps between actors; (b) transient
  `append`/`read` errors → caller retries; (c) **crash mid-`append_events`** (between staging and commit).
- **Oracle (the kernel's REAL crash contract):** after a crash mid-batch, the store holds **0 or all** of
  the batch — never a torn batch — and the aggregate high-water version equals what actually landed.
  (At-least-once *delivery* is the Go publisher's property, S8 G1 — cross-ref only, NOT asserted in-sim.)
- **Bite:** a `SimEventStore` that commits a partial batch on crash → torn batch (k of n events, k<n) →
  oracle fires.

## Increment 4 — Optimistic-concurrency CAS oracle (review MED-1)  `[BE]`
- Concurrent sim actors race `append_events(expected_version)` to the **same aggregate** under the seeded
  scheduler — exercising the REAL in-process CAS (`event_store.rs:497` → `ConcurrencyConflict`).
- **Oracle:** every accepted append advanced the version by exactly its batch length; no two accepted
  appends share a version (monotonic, no lost update); a stale `expected_version` is ALWAYS rejected.
- **Bite:** a CAS-free read-high-water-then-append path under a racing seed → two actors both land
  version N → lost update detected.
- **Scope (review MED-1):** higher lifecycle semantics (double-spawn / illegal-transition / capacity
  over-commit) are asserted ONLY if Inc-1 found a Rust state-machine; otherwise out of scope (S9's model),
  with a one-line note in the case + SESSION (NOT re-modeled here).

## Increment 5 — tilemap determinism-DST + travel deferral  `[FS]`
- Seeded corpus over `place_tilemap` (vary template/seed/grid). Assert byte-identical `TilemapView`:
  (a) across repeated in-process runs; (b) across a **fresh process** (serialize → spawn → compare) to
  catch process-global nondeterminism (allocator address leaking into output, etc.).
- **Bite (review LOW-1):** a **test-local, feature-gated** order-nondeterministic step (e.g. a harness
  wrapper that iterates a `HashMap` into output order) → bytes differ → assert caught. **The engine
  (`place_tilemap`) is NOT mutated** — the bite lives entirely in the sim crate.
- **travel:** record `D-S10-TRAVEL-SIM` in SESSION_HANDOFF; a one-paragraph note in `tests/sim/README.md`
  explaining travel has no behavior to simulate yet. No travel code touched.

## Increment 6 — conformance cases + CI + SESSION + commit  `[FS]`
- Catalog cases under `tests/conformance/catalog/`: `kernel-sim-convergence`, `kernel-sim-atomicity`,
  `kernel-sim-cas`, `tilemap-determinism` — CPU-only (no `foundation-stack` require), runner shells the
  sim binary, each embeds its `--bite`. Runner may need a `cargo`/sim `lookPath` arm (mirror the S7
  `k6/hyperfine` arm).
- CI: add a `kernel-sim` job to `conformance-ci.yml` — per-PR smoke **(8 seeds, like `loom-ci`)** + a
  nightly deep sweep **(256 seeds)** under the existing `schedule`/`workflow_dispatch` gate (review LOW-2).
  exit 1 → fail; exit 2 → notrun.
- SESSION_HANDOFF + memory + `.remember` updated (S10 done, S11 next). Single commit; `/review-impl` on
  the impl before commit; push only on explicit approval.

## Risks
- **R1 madsim sqlx wall** → mitigated by Inc-1 spike + Path B fallback (same property, no patch).
- **R2 sim harness vacuity** (a "sim" that only ever runs one interleaving proves nothing) → mitigated by
  the Inc-1 gate bite (different seed must yield a different trace) — the harness proves ITSELF non-vacuous
  before any oracle rides on it.
- **R3 oracle false-green** → every oracle has a bite; CI runs the bites.
- **R4 scope creep into travel** → explicitly deferred, zero travel code.
