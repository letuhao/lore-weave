# tests/sim — S10 kernel simulation DST (H1 / VOPR-lite)

Runs the **real `dp-kernel` event-sourcing surface** under a deterministic,
seed-reproducible simulator and asserts the spine invariants hold across a sweep
of fault schedules. Spec: `docs/specs/2026-06-14-S10-kernel-sim-dst.md`. Plan:
`docs/plans/2026-06-14-S10-kernel-sim-dst.md`.

This is an **isolated Cargo workspace** (own `[workspace]` table) — excluded from
the repo-root workspace, so its build (and the rejected Path-A patch) stay local.

## Decision: Path B (self-owned deterministic executor), NOT madsim — empirical

The plan's Inc-1 feasibility gate had to choose between **Path A (madsim)** and
**Path B (a self-owned VOPR-style executor)**. Path A was attempted and rejected
on evidence:

**Path A — madsim — fails to build, twice over:**

1. **OS wall (decisive on our dev platform).** A throwaway probe crate depending
   on `dp-kernel` with madsim's `tokio` `[patch]` + `--cfg madsim` fails to
   compile on **Windows**: madsim's runtime hooks Unix-only syscalls
   (`compile_error!("unsupported os")`, plus `dlsym` / `RTLD_NEXT` /
   `_SC_NPROCESSORS_ONLN` / `pthread_attr_t` / `CLOCK_REALTIME` "not found in
   `libc`"). madsim intercepts time/scheduling via `dlsym(RTLD_NEXT, …)`, which
   only exists on Unix. It never even reaches our code.
2. **sqlx wall (would block even on Linux).** `dp-kernel` hard-links `sqlx`
   (`crates/dp-kernel/Cargo.toml`, non-optional — visible as `Compiling sqlx`
   ahead of `dp-kernel` in any build). madsim's global `tokio` patch requires
   every transitive crate to build against `madsim-tokio`; `sqlx` is not on
   madsim's supported-driver list (madsim ships `madsim-tokio-postgres`, not
   sqlx). So a dp-kernel consumer cannot build under the patch regardless of OS.

**Path B — self-owned executor — works.** A single-threaded cooperative
scheduler ([`src/exec.rs`]) owns a `ChaCha8Rng(seed)` and at each step polls one
runnable task; `sim_yield()` points are where interleavings arise. No `tokio`
patch ⇒ no OS wall, no sqlx wall. `dp-kernel` (sqlx and all) compiles normally as
an ordinary path dependency. This is exactly TigerBeetle's VOPR pattern (cited in
the parent plan §9 H-row) — madsim is merely one implementation of the same
seed-reproducible-simulation idea, and a non-portable one here.

The deliverable PROPERTY is identical either way: a seed fixes the entire
interleaving; same seed ⇒ identical observable trace; a failing seed replays.

## Oracle-3 scope verdict (review MED-1)

Checked during Inc-1: `crates/dp-kernel/src/aggregate.rs` exposes only
`Aggregate::apply` (concrete aggregates implement it); there is **no
kernel-level lifecycle state-machine** that rejects illegal transitions, and
`entity_status.rs` has no transition guards. So the higher lifecycle semantics
(no double-spawn / illegal-transition / capacity over-commit) have **no reusable
Rust implementation to exercise** — that logic is Go / S9's abstract model.
**Oracle 3 is therefore scoped to the real `append_events` optimistic-concurrency
CAS** (`event_store.rs:497`), which IS in-process Rust. The semantic-transition
assertion is explicitly out of scope here (not re-modeled).

## How interleavings arise (non-vacuity precondition)

`SimEventStore` ops are reactor-free (`Mutex` lock, no IO `await`), so their
futures resolve on first poll. Interleavings exist ONLY at explicit
`sim_yield().await` points between actor ops. Without them the sim would be
single-path and every oracle vacuous — so Inc-1's gate (`src/skeleton.rs`,
`tests/skeleton.rs`) PROVES the yields produce genuine interleaving (a
`has_interleaving` check over a 64-seed sweep) before any oracle rides on it.

## travel-service — not simulated (deferred `D-S10-TRAVEL-SIM`)

The CLARIFY scope was "full 3-service". `travel-service` is a **Cycle-0 empty
scaffold** — its `main()` is a single `println!`, it has zero dependencies, and
its own header states it "compiles empty and has no behavior", blocked on the
unbuilt TVL_001..TVL_005 aggregates + foundation actor substrate. There is no
code to put under simulation. That is recorded honestly as a deferral
(`D-S10-TRAVEL-SIM`, SESSION_HANDOFF), NOT stubbed or fake-sim'd — when the
travel aggregates land, a follow-up adds a VOPR oracle for them like the kernel's.

## Run

```sh
cargo test                          # all gates + oracles (incl. cross-process)
cargo run --bin sim <case> [--bite] # case ∈ skeleton|convergence|atomicity|cas|tilemap
                                    # exit 0=pass · 1=fail · 2=notrun
```

## Increment status

- **Inc-1** ✅ skeleton + `SimEventStore` + Path-B executor + self-non-vacuity gate.
- **Inc-2** ✅ projection-convergence oracle (real `projections-pc`); bite = global-order-dependent projection.
- **Inc-3** ✅ append-batch atomicity under crash; bite = torn batch.
- **Inc-4** ✅ optimistic-concurrency (version) CAS; bite = CAS-disabled lost update.
- **Inc-5** ✅ tilemap determinism-DST (in-process + cross-process); bite = injected nondeterminism. travel deferred.
- **Inc-6** — conformance cases + CI.
