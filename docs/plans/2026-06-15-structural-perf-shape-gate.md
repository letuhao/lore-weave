# Plan — Structural perf-shape gate (G1+G2+G3)

- **Date:** 2026-06-15 · **Spec:** `docs/specs/2026-06-15-structural-perf-shape-gate.md`
- **Size:** XL (new Rust criterion bench + gate script + 2 live scripts + USL extension + CI + 3 conformance cases + SESSION/DEFERRED). Spec + plan both written.
- **Mode:** default v2.2; `/review-impl` on this plan + impl.
- **Discipline:** every gate ships a demonstrated BITE (red→green). No absolute-µs thresholds.

## DESIGN corrections (grounded in the real code — supersede the spec sketch)

1. **G3 — Rust criterion, per-PR, hermetic.** `ProjectionRunner::apply_one`
   (`crates/dp-kernel/src/projection.rs:206`) and `build_stmt`
   (`services/world-service/src/rebuild/writer.rs:83`) are **pure, DB-free** functions —
   the projection hot loop a higher-layer rebuild change would regress. Criterion benches them
   hermetically; a `rust-bench-gate.sh --ci-ab <ref>` runs same-runner A/B via criterion's
   `--save-baseline`/`--baseline` (parses "Performance has regressed"), mirroring `bench-gate.sh`.
   **This is the per-PR structural gate.** (The Go `tests/perf/bench` harness can't reach these —
   they're Rust; that's why a Rust criterion gate is the right home, not more Go benches.)
2. **G1 — live, nightly, statement-shape via `pg_stat_statements`.** Real `append_events`
   (`event_store_pg.rs:248`) runs `BEGIN` + **1** high-water `SELECT MAX` + **K** event INSERTs
   + `COMMIT`; the outbox is filled by a SEPARATE publisher, NOT by append and NOT by a trigger.
   So the honest invariant is: **the high-water SELECT executes exactly once per append,
   independent of batch size K** (event INSERTs scaling with K is correct-by-design, not a
   regression). `sqlx` over a concrete `PgPool` is not hermetically mockable → observe it LIVE:
   reset `pg_stat_statements`, append K=1 and K=64 to fresh aggregates, assert the SELECT-MAX
   `calls` count does NOT scale with K. Nightly, on foundation-dev/scale rig (like W4.2/W4.3).
3. **G2 — live, nightly, USL exponent band.** Reuse `tests/perf/usl/usl.go`; gate the empirical
   log-log slope `p = Δlog(time)/Δlog(N)` (and/or fitted USL γ) ≤ `1 + ε` over the sweep.
   Machine-independent (ratios across N on one run). Needs a one-time band calibration.

## /review-impl(plan) fixes folded (2026-06-15) — mechanism corrections, no scope change

The plan review confirmed THREE vacuity traps against the code and seven calibration/coverage
gaps. All folded below; the originals are struck so BUILD cannot regress to them.

- **F1 (HIGH, struck):** G1 must NOT drive the Go workload generator. Confirmed `emit.go:60`
  uses `insertEventsSQL` directly — a Go re-impl with **no `SELECT MAX` at all** and a different
  codebase from Rust `append_events`. G1 drives the **real Rust `append_events`** via a tiny
  Rust harness only.
- **F2 (HIGH, struck):** G1's bite has NO "force a known-bad capture" escape hatch. The bite is
  a **real instrumented append** that issues a per-event SELECT; its live `pg_stat_statements`
  capture must genuinely show the SELECT `calls` scaling with K.
- **F3 (HIGH, struck):** G3 must NOT replicate `build_stmt` in the bench (a copy drifts → the
  real regression hides). Confirmed `build_stmt` is private in the `world_service` lib. Bench the
  **real** function via a `pub` bench-only shim in `world-service`, in a world-service criterion
  bench. No copy.
- **F4 (MED):** G3 `apply_one` bench registers the **full 11-projection set** (`mod.rs:182`
  asserts 11), not a 2–6 subset — else regressions in unregistered arms are invisible.
- **F5 (MED):** G1 must show ONE real green + the bite red on a rig with `pg_stat_statements`
  enabled. NOTRUN-green is an unverified gate → enable the extension on foundation-dev and run it.
- **F6 (MED):** bites sized to the gate's **sensitivity floor** (catch a realistic ~15–30%
  regression), not an arbitrary 10×; state the magnitude each gate catches.
- **F7 (MED):** G2 ε tied to the **observed nightly sweep variance**; document the smallest
  exponent bump it catches — no untightenable wide band shipped as green.
- **F8 (LOW):** G2 fits the log-log slope over **all sweep points** (regression), not a 2-point
  secant.
- **F9 (LOW):** G2 gates the **log-log slope**, NOT USL γ (γ models contention saturation, not
  polynomial blowup).
- **F10 (LOW):** the G3 conformance *case* is a `--bite` / `bash -n` quick check; the full
  criterion bench stays in the dedicated CI job.
- **F11 (COSMETIC):** pin criterion + self-test the regression-output parser (F2-CSV lesson).
- **F12 (COSMETIC):** verify catalog count empirically at BUILD (don't assert 63 blind).

## Increments

### Inc-G3 (per-PR, hermetic) — Rust criterion projection-shape bench + gate
- **Files:**
  - `crates/dp-kernel/benches/projection_hotpath.rs` — criterion bench over `apply_one`,
    registering the **full 11-projection set** (F4), fed the relationship/canon + representative
    events; `LW_PERF_BITE` injects the bite.
  - `services/world-service/benches/build_stmt_hotpath.rs` — criterion bench over the **real**
    `build_stmt` via a `pub` bench-only shim (F3); `world-service/src/rebuild/writer.rs` gains
    `pub fn build_stmt_for_bench(...)` (or makes `build_stmt`+`Stmt` `pub(crate)` + a `pub`
    wrapper), documented bench-only.
  - `crates/dp-kernel/Cargo.toml` + `services/world-service/Cargo.toml` — `[[bench]]` +
    `criterion` dev-dep, **pinned version** (F11).
  - `scripts/perf/rust-bench-gate.sh` — `--bite | --ci-ab <ref> | local`, mirrors
    `bench-gate.sh`; parses criterion's regression verdict with a **self-tested parser** (F11).
  - CI `perf-rust-bench` per-PR job; conformance case `w5-projection-shape-bench.yaml` =
    `--bite` quick check + `bash -n` (F10).
- **Bite (F6):** `LW_PERF_BITE=1` injects a regression sized near the detection floor (target a
  ~20% slowdown, not 10×); `--bite` asserts criterion flags it (else vacuous → exit 1).
- **VERIFY:** `cargo bench` builds + runs both benches; `rust-bench-gate.sh --bite` fires on a
  ~20% bite; `--ci-ab HEAD~1` green on no-op; parser self-test passes.

### Inc-G1 (live, nightly) — append statement-shape invariant
- **Files:** `crates/dp-kernel/examples/append_stmt_harness.rs` (or a `tests/`-gated bin) that
  drives the **real `append_events`** (F1) for K∈{1,64} to one fresh aggregate against live PG;
  `scripts/perf/w5-append-stmt-shape.sh` (brackets the harness with
  `pg_stat_statements_reset()`); conformance case `w5-append-stmt-shape.yaml`; nightly CI step.
- **Mechanism:** assert the `SELECT MAX(aggregate_version)` `calls` is **constant in K** (1 per
  append) while `INSERT INTO events` `calls` == ΣK. Statement identity via the
  `pg_stat_statements` normalized `query`.
- **Bite (F2):** a real `--bite` harness variant whose `append` issues a per-event high-water
  SELECT → live capture shows SELECT `calls` scaling with K → invariant FIRES. No fabricated
  capture.
- **Setup (F5):** enable `shared_preload_libraries=pg_stat_statements` on **foundation-dev**;
  demonstrate one real green + the bite red there. Only if a rig truly can't load it → NOTRUN
  (setup) + a tracked deferred row — never a silent green.
- **VERIFY:** live foundation-dev run: SELECT calls constant, INSERT calls = ΣK; bite red.

### Inc-G2 (live, nightly) — USL scaling-exponent band
- **Files:** extend `tests/perf/usl/usl.go` (+ `usl_test.go`) with an `ExponentBand` check;
  `scripts/perf/w5-usl-exponent-band.sh`; conformance case `w5-usl-exponent-band.yaml`; nightly CI.
- **Mechanism (F8/F9):** fit the **log-log slope** `p` by least-squares over **all** sweep
  points (not a 2-point secant); assert `p ≤ 1 + ε`. Gate the slope, **not** USL γ.
- **Bite (F6):** feed the known-coefficient synthesizer a super-linear series with the exponent
  just past `1+ε` (near the floor, not a 2× blowup) → slope exits band → fail. Unit-testable in
  `usl_test.go`, no live rig.
- **Calibration (F7):** one empirical sweep on the scale rig sets ε from the **observed slope
  variance**; record ε + provenance + the smallest exponent bump it catches. If calibration is
  deferred, ship the unit-level bite green + a tracked tightening row (the live gate stays
  NOTRUN until ε is measured — not a wide vacuous green).

### Inc-G4 — conformance catalog + CI + SESSION
- 3 new `w5-*` conformance cases; **verify the catalog count empirically** at BUILD (F12),
  don't assert 63 blind. `conformance-ci.yml` gains a per-PR `perf-rust-bench` job (G3) and
  nightly steps (G1, G2); SESSION_HANDOFF + DEFERRED updated.

## Non-vacuity ledger (every gate must show a red — sized to the sensitivity floor, F6)
| Gate | Bite | Expected red |
|---|---|---|
| G3 | `LW_PERF_BITE=1` ~20% alloc/spin in the benched closure | criterion flags regression; `--bite` passes |
| G1 | **real** per-event-SELECT append harness (no fabricated capture) | SELECT `calls` scales with K → invariant fails |
| G2 | synthetic series with exponent just past `1+ε` | fitted log-log slope exits band → check fails |

## Risks / open (post-review)
- G3 `build_stmt` shim widens `world-service` lib surface by one `pub` bench-only fn — accepted,
  documented bench-only (the alternative, a drifting copy, is worse — F3).
- G1 hard-depends on `pg_stat_statements` on foundation-dev (F5); enabling it is part of this task.
- G2 ε is calibration-gated (F7); the live gate stays NOTRUN until ε is measured, unit bite green.

## Acceptance (from spec §7, post-review)
- [ ] G3 per-PR Rust gate (`apply_one` over 11 projections + real `build_stmt` shim) with a
      floor-sized demonstrated bite; `--ci-ab` green on no-op; parser self-tested + criterion pinned.
- [ ] G1 live invariant driven by the **real Rust `append_events`**, with one real green + a real
      per-event-SELECT bite red on foundation-dev (pg_stat_statements enabled).
- [ ] G2 fitted-log-log-slope band with a floor-sized unit bite; ε calibrated (or live gate NOTRUN
      + tracked row until calibrated).
- [ ] 3 conformance cases (catalog count verified empirically); CI wired (per-PR G3, nightly
      G1/G2); SESSION + DEFERRED updated.
