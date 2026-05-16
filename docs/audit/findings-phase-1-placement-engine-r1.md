# Adversary findings — Phase 1 placement engine (round 1)

> Task: `phase-1-placement-engine` · Phase: REVIEW (code) · Round 1
> Reviewer: AMAW Adversary (cold-start) · Date: 2026-05-16
> Scope: chunks 0-6 of `tilemap-service` Phase 1 (TMP_002 placement + TMP_003 pipeline).
> Verdict: **APPROVED_WITH_WARNINGS** — 3 WARN, 0 BLOCK.

The engine is genuinely well-constructed for the TMP-A4 determinism axiom: every
hash-container iteration that reaches output was traced and is either commutative
(integer-sum scoring in `grid_seed.rs`, `in_degree` decrements in `registry.rs`)
or routed through a sorted/deduped intermediate (`classify_edges` sort+dedup,
`penrose.rs` quantize+sort+dedup, `iter_set` flat-index order). RNG draws occur in
a fixed order from labelled `sub_seed` sub-streams. `cargo test -p tilemap-service`
(13 unit + 5 determinism integration) and `cargo clippy` are green; the determinism
test is not `#[ignore]`d. No determinism, partition-disjointness, or panic defect
was found that rises to BLOCK. The three findings below are real but lower-severity.

---

## WARN 1 — wall-clock cap admits a cross-machine layout divergence the determinism test cannot catch

**File:** `services/tilemap-service/src/engine/placement/force_directed.rs:148-179`

**Problem.** `force_directed_converge` checks the iteration cap (line 148) before
the wall-clock cap (line 151). For a graph that does **not** settle before either
cap, a fast machine runs all 1000 iterations and trips `Outcome::IterationCap` —
keeping the FR best-found layout — while a slower machine trips
`Outcome::WallClockCap` first (e.g. at iteration 600) and falls back to the
grid-seed layout (`seed_layout`, line 178). The two machines then emit *different*
`assigned_tiles` / `terrain_layer` for the same `(template, seed, grid)`. This is a
direct TMP-A4 violation surface. The spec (D5 "Residual caveat") consciously
accepts this trade-off as "unavoidable for any wall-clock cap," which is why this
is a WARN and not a BLOCK — but two things are worth flagging:

1. The AC-4 determinism test (`tests/determinism.rs`) runs `place_tilemap` twice
   **in the same process on the same machine** — it is structurally incapable of
   ever exercising this divergence, so spec risk R-B's claim that "the AC-4 test
   is the guard" is overstated for the wall-clock path specifically.
2. There is no runtime signal (log line, metric, or `converged` flag surfaced to
   the caller — see WARN 3) that a wall-clock fallback occurred, so a divergence
   in production would be silent.

**Why it matters.** The load-bearing guarantee of the whole engine is byte-identical
replay across machines. A path exists — narrow, but real — that breaks it with no
detection.

**Concrete fix.** Either (a) make Phase 1's default `max_wall_clock` effectively
unreachable for Phase-1-scale fixtures and add a debug assertion / warn-log when
the wall-clock branch is taken, so production divergence is observable; or (b)
add a determinism test that drives the engine with a tiny `max_wall_clock` against
a deliberately non-converging large graph and asserts the fallback layout is the
grid seed — exercising the machine-dependent branch deterministically. Option (b)
at minimum converts an untested branch into a tested one.

---

## WARN 2 — fractalize waypoint scatter is O(candidates squared), blowing the §7 perf budget at Continent scale

**File:** `services/tilemap-service/src/engine/placement/fractalize.rs:115-138`

**Problem.** `scatter_and_connect` loops over every candidate tile (line 115) and
for each calls `nearest_cleared_dist_sq` (line 127), which linearly scans the
entire `cleared` mask via `iter_set`. As `cleared` grows during the scatter, the
cost is O(candidates x cleared). For a Continent-tier zone (grid 256x256), a large
zone can own tens of thousands of tiles; with `cleared` reaching the low thousands
this is on the order of 10^8 `distance_sq` operations **per zone**, single-threaded.
TMP_002 §7 budgets all of fractalize at <500 ms total.

**Why it matters.** Not a correctness or determinism defect — the result is
deterministic and correct — but Phase 1 explicitly tests only small fixtures
(24x24-64x64), so the quadratic blow-up is invisible until a real Continent
template is run, at which point fractalize alone could take seconds to minutes.
CLAUDE.md's "No Defer Drift" rule requires perf items to be *tracked*, not
forgotten; this one is currently neither fixed nor recorded in DEFERRED.md.

**Concrete fix.** Replace the per-candidate linear scan with a spatial structure:
maintain `cleared` waypoints in a coarse grid bucket (cell size ~= sqrt(coverage_sq))
and only test candidates against waypoints in the 3x3 neighbouring buckets; or
run a multi-source BFS distance transform from `cleared` once per scatter round.
Either keeps the result identical while dropping the cost to ~O(candidates). If a
fix is genuinely deferred to a perf phase, add a row to `docs/deferred/DEFERRED.md`.

---

## WARN 3 — convergence metadata (`converged` / `iteration_count`) is computed then silently dropped

**File:** `services/tilemap-service/src/engine/placement/mod.rs:120-133` (consumes
`ConvergenceResult` but discards `.converged` and `.iteration_count`);
`services/tilemap-service/src/engine/mod.rs:36-92` (`TilemapView` has no carrier).

**Problem.** `force_directed_converge` returns a `ConvergenceResult` whose
`converged: bool` and `iteration_count: u32` fields exist precisely so downstream
can distinguish a settled layout from a cap-hit fallback (spec D5; TMP-PLACE-Q2/Q3;
TMP_002 §6's `ZonePlacementResult` carries both). `place_zones` destructures only
`converged.zones` and throws the other two fields away; `TilemapView` /
`ZoneRuntime` have no field to hold them. The PLAN Chunk 0 explicitly listed
"add `iteration_count`/`converged` carriers as needed" to `types/tilemap.rs` — that
item was not done. The result: a tilemap produced from a non-converged (cap-hit)
run is indistinguishable from a cleanly-converged one, both in the returned value
and in any future serialized form.

**Why it matters.** Phase 1 has no HTTP/progress-streaming consumer (those are
out of scope), so nothing is *broken* today — hence WARN, not BLOCK. But D5 makes
`converged` a meaningful, spec-mandated output, and TMP-PLACE-Q2 requires logging
`tilemap.generation_failed` with `iteration_count` on a cap hit. Dropping the data
on the floor with no tracked deferral violates CLAUDE.md's "Defer must mean
tracked, not forgotten" rule and will force a schema change later.

**Concrete fix.** Either add `converged: bool` + `iteration_count: u32` (or a
`GenerationMetadata` sub-struct) to `TilemapView` now and thread them through
`place_zones` -> `place_tilemap`, or — if the carrier is genuinely deferred to the
phase that adds the HTTP surface — record an explicit row in
`docs/deferred/DEFERRED.md` (ID, origin phase Phase-1, target phase) so it is not
silently lost.

---

Captured rules: none pre-loaded (ContextHub down); Guardrails relevant: none
