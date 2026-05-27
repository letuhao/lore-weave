# Spec — Tilemap perf: fractalize + penrose (Deferred #016 + #018)

> **Status:** CLARIFY — draft, pending PO sign-off.
> **Track:** `LLM_MMO_RPG` (tilemap-service).
> **Size:** L (default v2.2 human-in-loop, `/review-impl` at POST-REVIEW).
> **Trigger:** 2026-05-18 continent measurement (`docs/measurements/2026-05-18-continent.md`)
> finding O-1 — a 256² `place_tilemap` takes **506–659 s** release-build
> (the deferred items #016 + #018 were tagged "fix when profiling shows pain").

---

## 1. Problem

Two algorithms inside the tilemap placement engine are quadratic in the
continent-scale input — together they consume the bulk of the 8–11 min observed
in finding O-1. Both were flagged at Phase 1 review and accepted with the
"fix when profiling shows pain" condition (DEFERRED #016 + #018). Profiling
now shows pain.

### 1.1 #016 — `fractalize::scatter_and_connect`

[`services/tilemap-service/src/engine/placement/fractalize.rs:89`](services/tilemap-service/src/engine/placement/fractalize.rs#L89)

```rust
// Greedy scatter — keep a tile only if it is farther than the coverage
// radius from every waypoint placed so far.
for t in candidates {
    if nearest_cleared_dist_sq(t, &cleared) > coverage_sq {
        cleared.set(t);
    }
}
```

`nearest_cleared_dist_sq` (line 127) linearly scans every set bit of `cleared`
via `iter_set()`. As `cleared` grows, each candidate costs O(|cleared|), so the
whole loop is O(|candidates| × |cleared|) ≈ O(zone_tiles²).

**At 256²:** the largest fixture zone has ~5500 tiles, ~10 % of which survive
greedy thinning — ~5 500 × 550 / 2 ≈ 1.5 M `distance_sq` calls per zone, **× 12
zones = ~18 M calls**. Together with the constant overhead of `iter_set()`
walking the full bit buffer each call, this matches the observed cost.

**The query is actually simpler than nearest** — we only need a boolean
"is any set tile within distance ≤ √coverage_sq of `t`?" The exact nearest
distance is discarded.

### 1.2 #018 — `penrose::assign_zone_tiles`

[`services/tilemap-service/src/engine/placement/penrose.rs:95-104`](services/tilemap-service/src/engine/placement/penrose.rs#L95-L104)

```rust
for y in 0..grid.height {
    for x in 0..grid.width {
        let p = Vec2::new(/* tile centre in [0,1]² */);
        let vi = nearest_vertex(p, &vertices);   // linear scan
        masks[vertex_zone[vi]].set(TileCoord::new(x, y));
    }
}
```

`nearest_vertex` linearly scans the entire Penrose vertex field for every grid
tile. Vertex count grows with subdivision depth — at 12 zones the target is
`max(120, 200) = 200`, but the subdivision step is "subdivide until ≥ target",
which overshoots; in practice 500–1200 vertices land at the 256² configuration.

**At 256²:** 65 536 tiles × ~1000 vertices = **~6.5 × 10⁷ `distance_sq` calls**,
single-threaded — the dominant cost of the tile-assignment pass.

### 1.3 Why fixed now, not later

Quoting the handoff (2026-05-18):

> **Promote perf items #016 + #018** — the continent measurement ([finding
> O-1](docs/measurements/2026-05-18-continent.md)) is hard evidence the O(n²)
> `fractalize` (#016) + `penrose` (#018) placement cost is severe — **~8–11 min
> for a 256² continent**, release build. Deferred as "fix when profiling shows
> pain"; it now does.

Continuing to defer would block (a) the live continent measurement once
provider-registry pricing is configured, and (b) any future iteration on the
engine (each cycle currently waits 10+ min for a continent test).

---

## 2. Goals

1. **Speed up `scatter_and_connect`** so a 256² continent zone scatter pass
   completes in well under 1 s (current per-zone wall time: ~10–60 s).
2. **Speed up `assign_zone_tiles`** so the tile-assignment loop at 256²
   completes in well under 1 s (current: dominant chunk of the 8–11 min total).
3. **Preserve byte-identical output** — both deferred items explicitly note
   "output stays identical"; the golden test
   ([`golden_baseline_byte_identical`](services/tilemap-service/tests/determinism.rs#L251))
   and AC-4 ([`ac4_same_seed_yields_byte_identical_tilemap`](services/tilemap-service/tests/determinism.rs#L85))
   must pass unchanged (no rebaseline).
4. **No new public API surface** — these are pure-internal algorithm swaps.

### Non-goals

- **Not** parallelising zone scatter (TMP_002 §5 hint — separate task; doc
  retains the `sub_seed` carve-out for the parallel future).
- **Not** changing the Penrose target-vertex count, subdivision rules, or
  rotation seeding (would change output).
- **Not** addressing DEFERRED #020 (`would_seal_a_gap` pre-filter) — different
  algorithm, different placer, separate cycle.
- **Not** addressing #017 / #015 (progress-event streaming).

---

## 3. Determinism contract (NON-NEGOTIABLE)

For both algorithms, the replacement must produce **bit-exact equal output** to
the current implementation for every (template, channel, tier, grid, seed)
tuple. Specifically:

### 3.1 fractalize — `scatter_and_connect`

The output is the final `cleared: TileMask`. The current loop is equivalent to:
"iterate `candidates` in the shuffled order; for each, set the bit iff no
already-set bit lies within `coverage_sq`". The shuffled-order iteration is
fixed by the seeded ChaCha8Rng (line 109–110). The replacement must:

- Visit candidates in **the exact same shuffled order** (no reordering for
  cache locality, no parallel work-stealing).
- Apply the **same accept rule**: "set this bit iff there is no already-set
  bit `c` with `distance_sq(t, c) ≤ coverage_sq`". The strict `>` becomes a
  weak `≤` rejection — same boolean for every input.

### 3.2 penrose — `nearest_vertex` and `nearest_zone`

Both functions document **"ties → lower index"** (lines 259, 273). At 256²
exact ties are unlikely with `f64` arithmetic but not impossible (a tile
exactly on the perpendicular bisector of two vertices). The replacement must
preserve this tie-break exactly: when multiple vertices are at the same minimum
`distance_sq` from a query point, return the **lowest vertex index**.

The grid-tile iteration order (`for y { for x { ... } }`, lines 95–96) is fixed
and must not change — it controls the `masks[...].set(TileCoord::new(x, y))`
sequence (irrelevant for a `TileMask` final state, but locked anyway).

---

## 4. Approach (per algorithm)

### 4.1 #016 — uniform spatial bucket over `cleared`

Replace `nearest_cleared_dist_sq(t, &cleared) > coverage_sq` with a
**bucket-based "any-within-radius" query** on a side structure built lazily
alongside `cleared`:

- **Bucket grid**: divide the zone bounding box into `bucket_size`-square
  cells, where `bucket_size = ceil(sqrt(coverage_sq))` (small — ≤ 7 for the
  surface span, ≤ 5 for sea). Each bucket stores a `Vec<TileCoord>` of set
  tiles currently in it.
- **Insertion**: when `cleared.set(t)` runs, also push `t` into its bucket.
- **Query**: for candidate `t`, iterate the 3×3 bucket neighbourhood (its own
  bucket + 8 neighbours, clipped to grid); for each tile `c` listed there,
  test `distance_sq(t, c) ≤ coverage_sq`; short-circuit on the first hit.

The 3×3 neighbourhood covers every possible `c` within `coverage_sq` distance
because `bucket_size ≥ ceil(sqrt(coverage_sq))` ⇒ any tile farther than
`coverage_sq` lies in a bucket more than 1 step away.

**Cost:** O(1) amortised per query (the 3×3 neighbourhood holds O(1) tiles on
average — the scatter never fills any bucket above its area), so the whole
scatter pass is O(|candidates|) ≈ O(zone_tiles).

**Determinism:** the new query is a boolean — it returns `false` (reject)
**iff** the current linear scan would return a min ≤ coverage_sq. We don't
care which `c` we hit, only that at-least-one exists. Iteration order inside
the bucket neighbourhood is irrelevant.

### 4.2 #018 — uniform spatial bucket over vertices

Replace `nearest_vertex(p, &vertices)` with a **bucket-based spiral search**:

- **Build once** (after `penrose_vertices` returns): a uniform grid of
  `bucket_dim × bucket_dim` cells over `[0,1]²`, each cell holding a sorted
  `Vec<usize>` of vertex indices whose vertex falls in that cell. Pick
  `bucket_dim = ceil(sqrt(vertex_count))` ⇒ ≈ 1 vertex per cell on average.
- **Query** for tile centre `p`:
  1. Locate `p`'s bucket `(bx, by)`.
  2. Expand outward in rings — ring 0 = `(bx, by)`; ring `r` = the bucket
     shell at Chebyshev distance `r`.
  3. Track the running `best_d` and `best_index`. Across each ring, scan
     every vertex; if `distance_sq(p, v) < best_d`, update; if `== best_d`,
     keep the lower index (tie-break).
  4. **Termination**: stop expanding when the **next ring's minimum possible
     distance** (the squared distance from `p` to the inner edge of ring
     `r+1`) exceeds `best_d`. Compute that lower bound from the bucket cell
     geometry — a vertex at distance ≥ `(r+1 - 1) × cell_size` from `p` in
     either axis can't beat `best_d` if that quantity² > `best_d`.

For exact tie-breaking, we must **fully scan every bucket within `best_d`** —
the spiral can terminate only when the closest possible vertex in unscanned
buckets is `> best_d` (strict), so any tie inside an already-scanned bucket
has been considered.

**Subtle case — tie-break across bucket boundaries:** if two vertices in
*different* buckets are at exactly equal `distance_sq` from `p`, the lower
index must win. The spiral processes ring by ring; we must process all
buckets up to the termination ring **before** committing. Since `best_d`
shrinks monotonically and tie-break is by index, the algorithm above handles
this correctly by deferring the "stop?" decision to after each ring.

**Cost:** O(1) amortised per query (constant number of rings examined ⇒
constant number of vertices visited). Tile-assignment loop drops from
~6.5 × 10⁷ `distance_sq` calls to ~10⁵–10⁶.

**Determinism:** the lookup returns the same `(vertex_index)` as the linear
scan for every `p` — by exhaustively scanning every bucket within `best_d` and
applying the documented tie-break.

`nearest_zone` (line 260, called once per vertex, total ≤ 1200 calls per
build) is **not** on the hot path — leave it unchanged.

---

## 5. Test strategy

### 5.1 Existing tests that must stay green (no rebaseline)

- `golden_baseline_byte_identical` ([tests/determinism.rs:251](services/tilemap-service/tests/determinism.rs#L251))
- `ac4_same_seed_yields_byte_identical_tilemap` ([tests/determinism.rs:85](services/tilemap-service/tests/determinism.rs#L85))
- All existing unit tests in `fractalize.rs` and `penrose.rs`
- All existing harness/integration tests

### 5.2 New tests — bit-exact equivalence at scale

The risk we're guarding against is a tie-break or rounding divergence visible
only at continent scale (the existing tests run at 16²–32², where the
algorithms might agree by coincidence).

- **AC-1** `scatter_and_connect_matches_naive_at_continent_scale` — run both
  the old (private `nearest_cleared_dist_sq`-based) implementation and the new
  bucketed implementation against a 256-tile-wide synthetic zone with several
  seeds (0xA11CE, 1, 2, 0xF00D, 0xC0FFEE), assert bit-exact equal `cleared`
  masks. The "old" function is kept in-module under `#[cfg(test)]` as a
  reference oracle.
- **AC-2** `nearest_vertex_matches_naive_oracle` — for 200 random tile centres
  in `[0,1]²` against a Penrose-derived vertex field at depth 6, assert the
  bucketed lookup returns the same `(vertex_index)` as the linear scan. Run
  for several seeds.
- **AC-3** `nearest_vertex_tie_break_prefers_lower_index` — hand-construct a
  vertex set with two vertices exactly equidistant from a query point in
  *different* buckets, assert the bucketed query returns the lower index.
- **AC-4** the golden test still passes (`golden_baseline_byte_identical`).

### 5.3 Perf assertion (informational, not a gate)

A `#[ignore]`d test that runs `place_tilemap` at 256² and prints wall-time
to stdout — for the operator to eyeball the speedup. Not a CI gate; the
target is "<60 s" but the absolute number is host-dependent.

### 5.4 No new test infrastructure needed

`engine_placeholders` already covers integration through `place_tilemap`; we
do not need to wire the LLM harness for this task.

---

## 6. Acceptance criteria

- **AC-1** `scatter_and_connect_matches_naive_at_continent_scale` passes for ≥ 5
  seeds at 256-tile-wide zones (§5.2 AC-1).
- **AC-2** `nearest_vertex_matches_naive_oracle` passes for 200 random tile
  centres × ≥ 3 vertex-field seeds (§5.2 AC-2).
- **AC-3** `nearest_vertex_tie_break_prefers_lower_index` passes — a
  hand-constructed equidistant-across-buckets fixture (§5.2 AC-3).
- **AC-4** `golden_baseline_byte_identical` and
  `ac4_same_seed_yields_byte_identical_tilemap` still pass with no rebaseline
  (§3 determinism contract).
- **AC-5** `cargo test --workspace` green; `cargo clippy --workspace
  --all-targets` 0 warnings.
- **AC-6** the offline section of `tilemap-service measure` (continent 256²)
  reports a **per-stage breakdown** (`place_zones` vs `modificators` vs total
  `place_tilemap`) so the share of fractalize/penrose vs the modificator
  pipeline is explicit — the prior 2026-05-18 measurement only carried the
  total. The `place_zones` line is the AC-6 perf gate (the area #016/#018
  cover); target: well under 1 s release-build at 256². Total
  `place_tilemap` is informational — it depends on the modificator pipeline
  which is out of scope.
- **AC-7** the existing tests catalogued in §5.1 stay green unchanged.
- **AC-8** DEFERRED.md entries #016 and #018 move to "Recently cleared".

---

## 7. Files touched (estimate)

| Path | Change |
|---|---|
| `services/tilemap-service/src/engine/placement/fractalize.rs` | bucket-based scatter loop |
| `services/tilemap-service/src/engine/placement/penrose.rs` | bucket-based nearest_vertex |
| `services/tilemap-service/src/engine/placement/mod.rs` | possible shared `UniformBuckets` helper (decide in DESIGN — could also live in either file) |
| `services/tilemap-service/tests/perf_invariants.rs` | NEW — AC-1/AC-2/AC-3 oracle tests + `#[ignore]`d perf print |
| `docs/specs/2026-05-20-tilemap-perf-fractalize-penrose.md` | THIS FILE |
| `docs/plans/2026-05-20-tilemap-perf-fractalize-penrose.md` | PLAN doc (next phase) |
| `docs/deferred/DEFERRED.md` | clear #016 + #018 to "Recently cleared" |
| `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | new session entry |

7 files modified, 1 new test file, 1 new spec, 1 new plan. **L-sized.**

---

## 8. Open questions for PO — RESOLVED

- **Q1** ✅ **Yes — fold in.** AC-6 stands: re-capture the offline 256²
  measurement post-fix and record before/after in the SESSION entry.
- **Q2** ✅ **Share** `UniformBuckets<T>` (PO overrode the recommendation —
  see §9.1).

---

## 9. DESIGN

### 9.1 `UniformBuckets<P>` — shared helper

Lives in [`services/tilemap-service/src/engine/placement/spatial.rs`](services/tilemap-service/src/engine/placement/spatial.rs)
(NEW). Two consumers (fractalize, penrose) have genuinely different query
shapes — fractalize wants "any within radius", penrose wants "nearest with
tie-break by index". They share the same **storage shape** (uniform 2D grid of
bins holding `(index, point)` pairs), so the helper exposes bucket
**iteration**; the caller writes the query.

```rust
/// A coord-system-agnostic point that knows its bucket index.
pub(super) trait BucketPoint: Copy {
    /// Map this point to bucket coordinates given `inv_bucket_size` and
    /// the bucketing origin. Returns `None` if out-of-range (the caller
    /// must have already validated extents, so this is defensive).
    fn bucket_xy(self, origin: (f64, f64), inv_bucket_size: f64) -> (i32, i32);
}

impl BucketPoint for Vec2 { /* (px - ox) * inv_bs */ }
impl BucketPoint for TileCoord { /* x / bucket_size_int (origin = (0,0)) */ }

/// 2D uniform bin grid over `[origin_x .. origin_x + cols*bucket_size]` ×
/// same for y. Bins hold `(index, point)` pairs in insertion order; the
/// caller iterates bins via `neighbours_at(bx, by, ring)`.
pub(super) struct UniformBuckets<P: BucketPoint> {
    origin: (f64, f64),
    inv_bucket_size: f64,
    cols: i32,
    rows: i32,
    bins: Vec<Vec<(usize, P)>>,  // indexed by `by * cols + bx`
}

impl<P: BucketPoint> UniformBuckets<P> {
    /// Empty grid sized to cover `[origin .. origin + cols*bucket_size]²`.
    pub fn new(origin: (f64, f64), bucket_size: f64, cols: i32, rows: i32) -> Self;

    /// Insert `point` with caller-supplied `index` into its bucket. O(1).
    pub fn insert(&mut self, index: usize, point: P);

    /// Iterate `(index, point)` pairs in the single bucket `(bx, by)` if
    /// in-range; no-op if not. Order = insertion order.
    pub fn for_each_in_bucket(&self, bx: i32, by: i32, f: impl FnMut(usize, P));

    /// Iterate `(index, point)` pairs in the ring shell at Chebyshev
    /// distance `ring` from `(cx, cy)`. Ring 0 = the single centre bucket.
    /// Order: bucket-row-major, then insertion order within each bucket.
    /// Clipped to in-range buckets.
    pub fn for_each_in_ring(&self, cx: i32, cy: i32, ring: i32, f: impl FnMut(usize, P));

    pub fn bucket_size(&self) -> f64;
    pub fn bucket_xy(&self, point: P) -> (i32, i32);  // delegates to BucketPoint
    pub fn max_dim(&self) -> i32 { self.cols.max(self.rows) }
}
```

The `for_each_in_ring` helper is the only piece penrose needs that fractalize
doesn't — fractalize hardcodes the 3×3 neighbourhood (rings 0+1). Both use
`for_each_in_bucket` underneath.

**Why iterators-by-closure** instead of `impl Iterator`: the per-bin storage is
`Vec<(usize, P)>` and a returning-iterator over the ring shell would compose
several `flat_map`s with non-obvious borrowing lifetimes — closures keep the
code direct and the borrow checker silent. The hot loops are inside the
closure; no per-element allocation.

### 9.2 fractalize — wiring

```rust
fn scatter_and_connect(/* ... */) -> TileMask {
    // ... existing setup ...
    let coverage_sq = (MIN_DISTANCE * span_factor) as i64;
    let bucket_size = (coverage_sq as f64).sqrt().ceil() as i32;        // ≤ 7
    let cols = (w as i32 + bucket_size - 1) / bucket_size;
    let rows = (h as i32 + bucket_size - 1) / bucket_size;
    let mut buckets: UniformBuckets<TileCoord> =
        UniformBuckets::new((0.0, 0.0), bucket_size as f64, cols, rows);

    let mut cleared = TileMask::new(w, h);
    cleared.set(center);
    buckets.insert(0, center);  // index unused for fractalize — pass 0

    for t in candidates {
        let (bx, by) = buckets.bucket_xy(t);
        let mut blocked = false;
        for ring in 0..=1 {
            buckets.for_each_in_ring(bx, by, ring, |_idx, c| {
                if !blocked && dist_sq(t, c) <= coverage_sq {
                    blocked = true;
                }
            });
            if blocked { break; }
        }
        if !blocked {
            cleared.set(t);
            buckets.insert(0, t);
        }
    }

    connect_components(&mut cleared, assigned);
    cleared
}
```

**Key change vs spec §4.1:** the test becomes `≤ coverage_sq` to **reject**
(matching the original's strict `>` to **accept**: `!(d > coverage_sq) ==
d ≤ coverage_sq`). Equivalent boolean ⇒ bit-exact output.

**3×3 sufficiency proof:** the maximum `coverage_sq` is `MIN_DISTANCE *
SPAN_SURFACE = 81 * 0.45 = 36.45`. `sqrt(36.45) ≈ 6.04` ⇒ `bucket_size = 7`.
Any tile `c` outside rings 0+1 lies in a bucket at Chebyshev distance ≥ 2,
meaning its bucket starts ≥ `2 × 7 = 14` cells from `t`'s bucket in one
dimension ⇒ `c`'s Euclidean distance from `t` is ≥ `(2 - 1) × 7 = 7` (the
worst case: `t` at the far corner of its bucket, `c` at the near corner of
its bucket two rings away) ⇒ `dist_sq ≥ 49 > 36.45`. Reject-decision
preserved.

### 9.3 penrose — wiring

```rust
pub fn assign_zone_tiles(zones: &[PlacedZone], grid: GridSize, seed: TilemapSeed)
    -> crate::Result<Vec<ZoneTiles>>
{
    // ... seed, rotation, penrose_vertices() unchanged ...

    // Build the vertex bucket grid — bucket_dim ≈ sqrt(N) ⇒ ~1 vertex per cell.
    let bucket_dim = (vertices.len() as f64).sqrt().ceil().max(1.0) as i32;
    let bucket_size = 1.0 / bucket_dim as f64;
    let mut vbuckets: UniformBuckets<Vec2> =
        UniformBuckets::new((0.0, 0.0), bucket_size, bucket_dim, bucket_dim);
    for (i, &v) in vertices.iter().enumerate() {
        vbuckets.insert(i, v);
    }

    // §4.3 step 1 — each vertex belongs to its nearest zone centre (NOT
    // bucketed — only |vertices| calls total).
    let vertex_zone: Vec<usize> = vertices.iter().map(|&v| nearest_zone(v, zones)).collect();

    // §4.3 step 2 — bucketed nearest_vertex per tile.
    let mut masks = /* ... */;
    for y in 0..grid.height {
        for x in 0..grid.width {
            let p = Vec2::new(/* tile centre */);
            let vi = nearest_vertex_bucketed(p, &vbuckets);
            masks[vertex_zone[vi]].set(TileCoord::new(x, y));
        }
    }
    // ... rest unchanged ...
}

fn nearest_vertex_bucketed(p: Vec2, vb: &UniformBuckets<Vec2>) -> usize {
    let (cx, cy) = vb.bucket_xy(p);
    let mut best_d = f64::INFINITY;
    let mut best_i = 0usize;

    // Spiral outward; stop once the next ring's lower-bound distance > best_d.
    let max_ring = vb.max_dim();  // grid diameter — every vertex scanned at most
    let mut ring = 0i32;
    loop {
        vb.for_each_in_ring(cx, cy, ring, |i, v| {
            let d = p.distance_sq(v);
            if d < best_d || (d == best_d && i < best_i) {
                best_d = d;
                best_i = i;
            }
        });

        // Lower bound on any vertex in ring `ring+1`: its bucket starts at
        // Chebyshev distance `ring+1` from p's bucket, so the closest
        // possible point is ≥ `ring * bucket_size` Euclidean (the inner
        // edge of ring r+1 is `r` buckets from p's bucket boundary; worst
        // case: p sits on the far edge of its bucket toward ring r+1).
        let next_lb = (ring as f64) * vb.bucket_size();
        if best_d.is_finite() && next_lb * next_lb > best_d {
            break;
        }
        ring += 1;
        if ring > max_ring { break; }   // safety — all vertices already scanned
    }

    best_i
}
```

**Tie-break correctness:** the spiral visits every vertex within Chebyshev
distance `last_scanned_ring` buckets of `p` before terminating. The
termination check `next_lb² > best_d` ensures any not-yet-scanned vertex is
strictly farther than `best_d` — so it cannot be a tie. Inside scanned rings,
the update rule `(d == best_d && i < best_i)` keeps the lowest index.

**Initial-ring `best_i = 0` is OK** because the first vertex visited (ring 0
or first non-empty ring) overwrites it via `d < best_d` (since `best_d` starts
at `+∞`). The bucket grid is non-empty (`penrose_vertices` returns ≥ 3 vertices
or errors), and the grid spans `[0,1]²` which contains every tile centre, so
the spiral always finds a vertex.

**`nearest_zone` left unchanged** — called `|vertices|` times only (≤ 1200);
not on the hot path.

### 9.4 Determinism risks reviewed

| Risk | Mitigation |
|---|---|
| Iteration order inside a bucket shifts a tie-break | Bucket bins are `Vec<(usize, P)>` in insertion order; insertion order = construction order (penrose: vertex-index ascending; fractalize: scatter-shuffled order). Tie-break in penrose is explicit by index, independent of iteration order. Fractalize doesn't tie-break (boolean any-within-radius). |
| Cross-bucket tie missed | `next_lb² > best_d` strict — any vertex with `d == best_d` in an outer ring would have `next_lb² ≤ best_d` (since `d ≥ next_lb²`), so we'd scan it. ✓ |
| Float rounding differs from linear scan | The bucket query computes the **same** `p.distance_sq(v)` for the **same** candidate vertices; the only difference is which vertices it considers. As long as every candidate that could tie-or-beat is considered, the answer matches. ✓ |
| `bucket_dim = 0` for empty vertex list | `penrose_vertices` errors on < 3 vertices; `bucket_dim.max(1.0)` guards as defense-in-depth. ✓ |
| 3×3 neighbourhood misses a candidate at exactly `coverage_sq + ε` | Proven sufficient in §9.2 for max `coverage_sq = 36.45` ⇒ rings 0+1 cover ≤ 49 sq distance. ✓ |

### 9.5 What stays unchanged

- `nearest_cleared_dist_sq` is **kept** in `fractalize.rs` under
  `#[cfg(test)]` — used as the oracle for AC-1.
- `nearest_vertex` linear-scan is **kept** in `penrose.rs` under
  `#[cfg(test)]` — used as the oracle for AC-2.
- `nearest_zone` unchanged (not on hot path).
- `connect_components` / `shortest_path` / `hub_path` unchanged (not on hot
  path: BFS over already-thinned waypoint set).
- `penrose_vertices` / `seed_wheel` / `subdivide` / `collect_vertices`
  unchanged (one-time cost, not hot path).

### 9.6a Design-review notes (Lead self-review, before BUILD)

- **R1** §9.3 had a dead `last_scanned_ring` — removed.
- **R2** §9.3 referenced `vb_max_dim(vb)` undefined; added
  `UniformBuckets::max_dim()` (§9.1).
- **R3** `dist_sq(t, c)` in §9.2 fractalize wiring must return `i64` to
  match the original i64 `coverage_sq` cast (kept the original
  `nearest_cleared_dist_sq` body inline as the per-pair test —
  `let dx = t.x as i64 - c.x as i64; let dy = ...; let d = dx*dx + dy*dy;
   if d <= coverage_sq { blocked = true; }`). Avoids any f64 conversion
  drift inside the hot loop.
- **R4** PO answer for Q2 was "share" — design exposes shared storage +
  ring iteration; query semantics stay per-module (any-within-radius
  vs nearest-with-tie-break-by-index). Matches the spirit of "share" while
  keeping each query honest about its semantics.

### 9.6 Bucket-size sanity for fractalize per zone

`bucket_size` is computed from `coverage_sq`, which depends on `span_factor`:
- Sea: `coverage_sq = 81 × 0.2 = 16.2` ⇒ `bucket_size = 5`.
- Surface: `coverage_sq = 81 × 0.45 = 36.45` ⇒ `bucket_size = 7`.

A 256² zone with `bucket_size = 7` ⇒ ~37 cols × 37 rows ≈ 1370 buckets.
Average bin occupancy after greedy thinning: `|waypoints| / 1370` ≈ 0.4 →
each 3×3 neighbourhood holds ~4 tiles on average. Query cost ~constant.
