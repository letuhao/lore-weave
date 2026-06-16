# S10 — Rust kernel simulation DST (H1-madsim / VOPR-lite)

**Slice:** S10 of the foundation runtime test plan (`docs/specs/2026-06-04-foundation-runtime-test-plan.md`, §9 Technique H, §10 roadmap).
**Date:** 2026-06-14 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** XL (new crate + CI + multi-oracle).
**Depends on:** the spine (`B ∧ C ∧ C2 ∧ C3`), S9 (Stateright model), S6 (loom). **Complements, does not duplicate** them — see §2.

---

## 1. Goal

Run the **real Rust kernel code** (not an abstract model) under a **deterministic simulator** —
seeded scheduler + virtual clock + injected faults — and assert the load-bearing spine invariants
hold across a large sweep of fault schedules, **seed-reproducibly**. This is the VOPR/Flow tier the
plan defers to "after spine" (§9 row H1-madsim), now feasible because the Rust replay path is already
deterministic (the hardest VOPR precondition is already paid for).

The single load-bearing invariant remains **`projection == replay(events)`**; S10 stresses it (and two
companions) under concurrency + faults that the structural oracle (C) and the from-spec oracle (C2)
are blind to.

## 2. Why this is not a duplicate of S6 / S9

| Slice | What it checks | Surface | Limitation S10 fills |
|---|---|---|---|
| **S6 — loom** | exhaustive interleavings of ONE small sync primitive (CircuitBreaker) | a few atomics | tiny state; no clock/IO/crash |
| **S9 — Stateright** | an **abstract MODEL** of lifecycle-CAS / outbox / fan-out | hand-written model, not the kernel | model ≠ code: a model bug ≠ a code bug |
| **S10 — sim DST** | the **REAL kernel code** under seeded scheduling + clock-skew + store-faults + crash/restart | append→outbox→apply→project→replay over `InMemoryEventStore` | runs the actual code paths the model abstracts; finds code-vs-model drift |

S10 is the bridge: S9 proves the *design* is correct; S10 proves the *implementation* matches it under
adversarial scheduling. Different failure class (code-vs-model drift, real-clock races, crash-recovery
in the actual apply path).

## 3. Scope (CLARIFY answers: full 3-service · full VOPR fault model · full spine oracle)

The user chose maximal on all three axes, **knowing the 3-service end-to-end was flagged partly
infeasible**. The honest maximal build reconciles intent with feasibility — all three services are
addressed; none is fake-sim'd:

| Service | Real simmable surface | S10 treatment |
|---|---|---|
| **world-service / dp-kernel** | event-sourcing core: append→outbox→apply→project→replay; lifecycle CAS; capacity — all expressible over the existing sqlx-free `OutboxWriter` trait + `InMemoryEventStore` | **PRIMARY: VOPR-DST** (oracles B + at-least-once + I9) |
| **tilemap-service** | `place_tilemap` is **synchronous + deterministic** (TMP-A4: same seed ⇒ byte-identical). No concurrency to interleave → madsim is the wrong tool | **determinism-DST**: seeded corpus, byte-identical across runs + across a process boundary; its own bite |
| **travel-service** | **none** — Cycle-0 empty stub (`fn main(){ println!() }`), explicitly "no behavior", blocked on unbuilt TVL_001..005 aggregates | **honest no-op**: tracked deferral `D-S10-TRAVEL-SIM`, revisit when TVL_001 ships. NOT fake-sim'd. |

This is non-vacuity applied to scope: travel "can't be simulated because there is no code" is the
*correct* answer, recorded as a deferral — not a skip and not a stub we pretend covers something.

## 4. The feasibility wall and the resolution (spike-first)

**Wall:** madsim works by globally patching `tokio` (a Cargo `[patch]` + `--cfg madsim`). `dp-kernel`
transitively links **`sqlx`**, which is **not madsim-compatible** — under the patch its `tokio::net`
usage may fail to compile. Verified: `crates/dp-kernel/Cargo.toml` has `sqlx = { workspace = true }`
as a hard (non-optional) dependency for `PgEventStore`.

**Resolution — Increment 1 is a hard feasibility gate**, not a guess:

- **Path A (preferred): madsim** in an isolated `tests/sim/` workspace. If the kernel's pure async
  surface (outbox/apply/replay over `InMemoryEventStore`) builds + runs under madsim's runtime, use it.
- **Path B (documented fallback): self-owned deterministic executor (VOPR pattern)** — a single-threaded
  scheduler that owns a seeded RNG (chooses ready-task order), a virtual clock, and fault hooks. **No
  tokio patch ⇒ no sqlx wall.** This is exactly TigerBeetle's VOPR (cited in plan §9 H-row) — madsim is
  merely one implementation of the same idea. The deliverable PROPERTY is identical: a seed → a
  reproducible fault schedule → invariant assertion.

Either path yields the same artifact contract (§6). Inc-1 picks the path **empirically** and records the
verdict; the plan does not pretend to know which compiles. (Resolves open decision §11.5 of the parent
plan for the H1 tier.)

## 5. Oracles (each pinned to a REAL Rust-kernel contract — each non-vacuous, each with a bite)

**Targeting discipline (review HIGH-1/HIGH-2):** an in-sim oracle may only assert a property the Rust
kernel *actually implements*. Properties that live in the Go publisher (at-least-once delivery) or in
Postgres are NOT in scope — simming them would re-model a behavior the sim doesn't run = vacuous. Each
oracle below is mapped to a concrete kernel code path. Run after every seed; a violation in ANY = the
seed is a counterexample (printed for replay).

1. **Projection convergence — `apply(any legal interleaving) == apply(canonical replay order)`.**
   The sim drives the **real `crates/projections/*` `Projection::apply_event`** (sqlx-free — verified, the
   only `sqlx` refs there are doc comments) under a seed-chosen concurrent delivery order, then re-applies
   the **real replay** in canonical `(aggregate_version)` order, and byte-compares the two resulting
   projection states. This is the **H1 concurrency property** (does out-of-order concurrent delivery +
   replay converge?). **It does NOT replace S5's cross-implementation differential** (Go-write vs
   Rust-replay) — both sides here are the same Rust code, by design, so this catches *ordering/idempotence*
   bugs, not impl drift. Both sides MUST call the real crates (no hand-rolled re-impl → no common-mode
   vacuity). *Bite:* a projector arm made order-sensitive (last-writer-wins on a field that should be
   commutative) → the two orders diverge.
2. **Append-batch atomicity under crash** (review HIGH-1 — the kernel's REAL crash contract, NOT
   at-least-once). `append_events` is atomic all-or-none (`event_store.rs:128`). The sim injects a crash
   mid-`append_events` (between staging and commit in the `SimEventStore`) and asserts the store holds
   **0 or all** of the batch — never a torn batch — and the aggregate high-water version is consistent with
   what landed. (At-least-once *delivery* is the Go publisher's property, covered by S8 G1 — cross-ref
   only, not asserted here.) *Bite:* a `SimEventStore` that commits a partial batch on crash → torn batch
   detected.
3. **Optimistic-concurrency CAS (I9 foundation) — version monotonic / no lost update.** The CAS is a REAL
   in-process Rust path: `append_events(expected_version)` → `ConcurrencyConflict` when stale
   (`event_store.rs:497`). Concurrent sim actors race appends to the same aggregate; assert every accepted
   append advanced the version by exactly its batch length, no two appends share a version, and a stale
   `expected_version` is *always* rejected (never a silent lost update). *Bite:* a CAS-free
   read-high-water-then-append path → two actors both write version N → lost update detected.
   **Scope note (review MED-1):** higher lifecycle *semantics* (no double-spawn / illegal-transition /
   capacity over-commit) require a Rust aggregate state-machine; Inc-1 verifies whether one exists in-Rust
   — if the decision logic is Go-only, that assertion is **out of scope here** (it is S9's model), not
   re-modeled.

**+ tilemap determinism oracle** (its own surface): same `(template, seed, grid)` ⇒ byte-identical
`TilemapView` across repeated runs AND across a fresh process. *Bite:* a **test-local, feature-gated**
order-nondeterministic step (NOT a mutation of the engine — review LOW-1) → bytes differ.

**`SimEventStore` (review MED-2).** The sim owns its own `EventStore` impl rather than borrowing the
kernel's `InMemoryEventStore` (which is explicitly documented "not part of the public API",
`event_store.rs:~442`, and offers no fault hooks). `SimEventStore` re-uses the same trait + version-CAS
semantics and adds the crash/fault injection points oracles 2 and 3 require. This closes the
non-contract-dependency risk AND unblocks fault injection in one move.

## 6. Artifact contract (path-independent)

- **`tests/sim/`** — isolated Rust crate (mirrors the `tests/perf/`, `tests/conformance/` standalone
  pattern). Owns the simulator (Path A or B), the **`SimEventStore`** (its own fault-injectable
  `EventStore` impl), the sim actors, the fault injectors, the oracle asserts. Drives the **real**
  `crates/projections/*` + replay (no hand-rolled re-impl).
- A **seeded run** prints, on failure, the seed + the fault schedule so any counterexample replays with
  `SIM_SEED=<n>`. Clean run over a seed sweep (default N seeds, `SIM_SEEDS` overridable) exits 0.
- **Conformance cases** (`tests/conformance/catalog/`): CPU-only, no live stack (like the loom case) —
  the runner shells the sim binary; verdict pass/fail/notrun. Each embeds its `--bite` non-vacuity proof.
- **CI**: a `kernel-sim` job. Per-PR smoke (small seed sweep, fast — like `loom-ci`) + a nightly deep
  sweep (large seed count). exit 1 → fail; exit 2 → notrun (green).

## 7. Out of scope (tracked)

- `D-S10-TRAVEL-SIM` — travel-service in-sim once TVL_001..005 exist.
- `D-S10-SQLX-SIM` — running the real sqlx service main loops under sim (the H2 / whole-stack DST tier,
  S11 / Antithesis covers near-prod; not H1).
- `D-S10-MADSIM-NET` — sim-network partitions between services (only meaningful once >1 service has
  behavior; today the kernel is in-process).

## 8. Acceptance criteria

- [ ] Inc-1 feasibility gate resolved (Path A or B) with an empirical build/run record; the interleaving
      mechanism (seed-ordered `yield` points) is named and its self-non-vacuity bite (different seed ⇒
      different trace) passes.
- [ ] Kernel VOPR-DST asserts projection-convergence + append-batch atomicity + version-CAS across a seed
      sweep, over the REAL projection crates + `SimEventStore`; all 3 oracles bite.
- [ ] tilemap determinism-DST byte-identical across process boundary; bite fires (test-local, engine
      untouched).
- [ ] travel deferral recorded (`D-S10-TRAVEL-SIM`), not stubbed.
- [ ] Conformance cases + CI job wired; a failing seed is replayable from its printed seed.
- [ ] `/review-impl` on the plan AND the impl; findings folded.
