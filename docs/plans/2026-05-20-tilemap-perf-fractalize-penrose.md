# Plan — Tilemap perf: fractalize + penrose

> **Spec:** [`docs/specs/2026-05-20-tilemap-perf-fractalize-penrose.md`](../specs/2026-05-20-tilemap-perf-fractalize-penrose.md)
> **Workflow:** default v2.2 human-in-loop, `/review-impl` at POST-REVIEW.
> **TDD:** each chunk writes the test BEFORE flipping the call site to the
> bucketed implementation. The oracle (naive) version stays under `#[cfg(test)]`
> in the same file so the equivalence test compiles offline.

---

## Chunk 1 — `spatial.rs` + `UniformBuckets<P>` (no consumer yet)

**Files:**
- NEW `services/tilemap-service/src/engine/placement/spatial.rs`
- MOD `services/tilemap-service/src/engine/placement/mod.rs` (add `mod spatial;`
  + re-export `UniformBuckets`/`BucketPoint` to crate-internal scope).

**Build steps:**
1. Define `BucketPoint` trait (§9.1) + `impl BucketPoint for Vec2` + `impl
   BucketPoint for TileCoord`.
2. Define `UniformBuckets<P>` struct + `new`, `insert`, `bucket_xy`,
   `bucket_size`, `max_dim`, `for_each_in_bucket`, `for_each_in_ring`.
3. Unit tests (in-file `mod tests`):
   - `new_empty_grid_has_no_pairs` — fresh grid iterates nothing.
   - `insert_then_for_each_in_bucket_round_trips` — insert + locate via
     `bucket_xy` + iterate that bucket returns the inserted pair.
   - `for_each_in_ring_zero_visits_centre_only` — ring 0 is the single
     centre bucket.
   - `for_each_in_ring_one_visits_eight_neighbours` — ring 1 is the 8-cell
     shell (or fewer on grid edges).
   - `for_each_in_ring_clips_to_grid_edges` — a corner bucket has ring 1
     of 3 cells, not 8.
   - `for_each_in_ring_skips_negative_ring_safely` — defensive: ring < 0 is
     a no-op.
   - `bucket_xy_of_vec2_at_origin` + `bucket_xy_of_tilecoord_at_origin` —
     coord-to-bucket math sanity.
   - `out_of_range_bucket_xy_is_handled` — query a point past
     `cols*bucket_size` returns an out-of-range bucket; `for_each_in_bucket`
     no-ops.

**Done when:** `cargo test --package tilemap-service spatial::` green;
crate compiles (no consumers wired yet).

---

## Chunk 2 — fractalize bucketed scatter + AC-1 oracle test

**Files:**
- MOD `services/tilemap-service/src/engine/placement/fractalize.rs`

**Build steps:**
1. Rename current `scatter_and_connect` body to `scatter_and_connect_naive`
   under `#[cfg(test)]` (kept as oracle). Keep `nearest_cleared_dist_sq` under
   `#[cfg(test)]` too — only the naive uses it.
2. Add new public `scatter_and_connect` per spec §9.2 — bucket-based any-
   within-radius using `UniformBuckets<TileCoord>`. Inline the per-pair test
   as i64 arithmetic (per R3).
3. **AC-1 test** `scatter_and_connect_matches_naive_at_continent_scale` — for
   each seed in `[0xA11CE, 1, 2, 0xF00D, 0xC0FFEE]`, for each role-span pair
   in `[(Wilderness, SURFACE), (Sea, SEA)]`, run a full 256-tile-wide synthetic
   zone through both implementations and `assert_eq!(bucketed, naive)` on the
   resulting `TileMask`.
4. Keep all five existing tests; they must pass unchanged.

**Done when:** `cargo test --package tilemap-service fractalize::` green
including the new AC-1 test (which will assert bit-exact equivalence).

---

## Chunk 3 — penrose bucketed nearest_vertex + AC-2/AC-3 tests

**Files:**
- MOD `services/tilemap-service/src/engine/placement/penrose.rs`

**Build steps:**
1. Rename current `nearest_vertex` body to `nearest_vertex_naive` under
   `#[cfg(test)]`.
2. Add `nearest_vertex_bucketed(p, vb) -> usize` per spec §9.3 — spiral
   search with index tie-break.
3. In `assign_zone_tiles`, build the `UniformBuckets<Vec2>` once
   post-`penrose_vertices`, swap the per-tile call from `nearest_vertex(p,
   &vertices)` → `nearest_vertex_bucketed(p, &vbuckets)`.
4. **AC-2 test** `nearest_vertex_matches_naive_oracle` — for each
   `(rotation_seed, vertex_target)` in `[(0.3, 200), (1.7, 500), (2.5, 200)]`,
   build a real Penrose vertex field, then build the bucket grid, then for 200
   random Vec2 points in `[0,1]²` (seeded from the rotation_seed) assert the
   bucketed lookup returns the same index as the naive scan.
5. **AC-3 test** `nearest_vertex_tie_break_prefers_lower_index` — construct a
   `Vec<Vec2>` with two vertices placed at exact float coords equidistant from
   a query point, in *different* buckets; assert the bucketed lookup returns
   the lower index.
6. Keep all eight existing tests; they must pass unchanged.

**Done when:** `cargo test --package tilemap-service penrose::` green
including AC-2 + AC-3.

---

## Chunk 4 — `tests/perf_invariants.rs` `#[ignore]` perf print

**Files:**
- NEW `services/tilemap-service/tests/perf_invariants.rs`

**Build steps:**
1. Add a single `#[ignore]`d test `perf_continent_place_tilemap_release` that
   runs `place_tilemap` at `GridSize::CONTINENT_DEFAULT` (256²) against a
   12-zone synthetic template and prints `wall_time_ms = N` via `println!`
   (visible with `cargo test -- --ignored --nocapture`).
2. The test asserts only `result.is_ok()` — the wall-time number is for
   operator inspection (§5.3 — not a CI gate).

**Done when:** the file compiles; the test passes with `--ignored`.

---

## Chunk 5 — Full VERIFY + continent re-measurement (AC-5, AC-6, AC-7)

**Build steps (run from repo root):**
1. `cargo build --workspace --release` — clean.
2. `cargo test --workspace` — all green; the **golden test**
   (`golden_baseline_byte_identical`) and AC-4
   (`ac4_same_seed_yields_byte_identical_tilemap`) must pass unchanged (no
   rebaseline). Total expected: prior 329 (Phase E) + AC-1 + AC-2 + AC-3 +
   UniformBuckets unit tests (~8) ≈ 340.
3. `cargo clippy --workspace --all-targets` — 0 warnings.
4. **AC-6 perf gate** — `cargo run --release --package tilemap-service -- measure`
   (offline section only — live still blocked on provider-registry pricing).
   Record the new `place_tilemap` wall time. Target: under 60 s release-build.
5. Append a section to
   [`docs/measurements/2026-05-18-continent.md`](../measurements/2026-05-18-continent.md)
   (or create `docs/measurements/2026-05-20-continent-perf.md` if cleaner) with
   the before/after numbers and the speedup factor.

**Done when:** all VERIFY evidence captured for the SESSION entry.

---

## Chunk 6 — REVIEW (code), QC, POST-REVIEW (`/review-impl`)

Per the standard 12-phase flow. POST-REVIEW: present a summary; if approved,
invoke `/review-impl` per the spec's correctness-critical assessment (the
golden test is the safety net, but the bucket tie-break math is subtle).

---

## Chunk 7 — SESSION + COMMIT + RETRO

1. **SESSION** — append a new session entry to
   [`docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md`](../03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md):
   files touched, before/after wall time, test delta, deferrals cleared
   (#016, #018).
2. **DEFERRED update** — move entries #016 + #018 to "Recently cleared" in
   [`docs/deferred/DEFERRED.md`](../deferred/DEFERRED.md).
3. **COMMIT** — stage the touched files only (no `git add -A`); message names
   the phase + the cleared deferrals + the speedup.
4. **RETRO** — if anything non-obvious about the bucket tie-break math is
   worth keeping for future sessions, `add_lesson` to ContextHub MCP under
   `project_id = mmo-rpg-zone-map-design-non-human-in-loop`. Skip if not.

---

## Risk register (for BUILD phase)

| Risk | Mitigation |
|---|---|
| Bucket tie-break drift across rings produces different vertex index | AC-2 oracle test covers 200 × 3 = 600 random points across multiple vertex fields. AC-3 covers the explicit cross-bucket tie. |
| `coverage_sq` cast to i64 loses precision vs original `(MIN_DISTANCE * span_factor) as i64` | We literally reuse `(MIN_DISTANCE * span_factor) as i64` — same expression. |
| Floating-point in `bucket_xy` for `Vec2` differs by ULP vs the linear scan's bucket placement | Bucket placement is one-time (vertex insertion) and consistent (query uses the same `bucket_xy`). Bit-exact answer hinges on which vertices the spiral considers — the oracle test catches any mismatch end-to-end. |
| Empty vertex list crashes the spiral | `penrose_vertices` errors on < 3 vertices; defensively `bucket_dim = sqrt(N).max(1.0)`. |
| Insert into out-of-range bucket silently drops | `insert` should panic in debug, no-op in release (defensive; `for_each_in_bucket` already no-ops on out-of-range). Decide in Chunk 1. |
| `cargo test` timeout for AC-1/AC-2 at continent scale | AC-1: 256-tile zone is ~1 s with naive at this size (we tested manually). AC-2: 200 points × ~500 vertices = 10⁵ ops. Both finish in seconds. |
