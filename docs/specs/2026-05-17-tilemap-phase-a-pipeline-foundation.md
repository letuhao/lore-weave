# Spec — tilemap-service Phase A: Pipeline Foundation

> **Status:** CLARIFY+DESIGN done · REVIEW(design) r1-r4 REJECTED, r5 APPROVED_WITH_WARNINGS — 3 WARN folded in 2026-05-17 · **Size:** XL · **Mode:** AMAW (`/amaw`)
> **Roadmap:** [`docs/plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md`](../plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md) §4 Phase A
> **Source specs:** TMP_001 §5 (tile-state machine), TMP_003 §2/§3.6 (modificator
> base + ObjectManager), TMP_006 §4/§5 (connectivity invariant + ObjectManager),
> TMP_007 §5 (path search).

## §1 Context & goal

The engine (`place_tilemap`) runs `place_zones` then a modificator pipeline
holding only `TerrainPainter`; `ModificatorContext` carries just the terrain
layer. The five remaining V1+30d placers (Obstacle / Treasure / Connections /
Road / River) all need shared infrastructure the docs do not decompose per-doc:
a per-tile `TileState` grid, a mutable object list, the "never seal a gap"
connectivity check (TMP_006 §4 — *"the most important invariant in the whole
pipeline"*), A\* path search (TMP_007 §5), and the `ObjectManager` placement
service (TMP_006 §5). Phase A builds exactly that — no new visible placement
output, but the load-bearing correctness core for Phases B–E.

## §2 Scope

### In scope

1. `TilemapBuildState` — owns all mutable generation state; an extended
   `ModificatorContext` exposes it to modificators.
2. The per-tile `TileState` build-grid (TMP_001 §5).
3. `TilemapObjectTemplate` — object footprint descriptor.
4. `connected_components` + `would_seal_a_gap` connectivity check (TMP_006 §4).
5. `search_path` — A\* over a tile mask (TMP_007 §5, TMP_003 §3.4).
6. `ObjectManager` service — `place_and_connect_object`, `choose_guard`, the
   `nearest_object_distance` grid (TMP_006 §5, TMP_003 §3.6).
7. Additive (TMP-A8) template-schema extensions whose types are self-contained.

### Out of scope (deferred to later phases / versions)

- Any actual placer (ObstaclePlacer → B, TreasurePlacer → C, etc.).
- `BiomeSelectionRules` / banned-required-object schema fields — added by their
  consuming phase (B / C) where the field types are defined (avoids Phase A
  pulling in TMP_005/006 type definitions speculatively).
- Parallel execution + `RwLock` per zone + dining-philosopher locking — the
  engine is single-threaded, a first-class V1+30d mode (TMP_003 §4.3,
  TMP-PIPE-Q4). Not built.
- Roads / rivers / connection records on `TilemapView` — added by D / E.
- The TMP_006 §4.3 connectivity pre-filter optimization — see D5.

## §3 Design decisions

**D1 — `TilemapBuildState` as the mutable generation state.** A new struct owns
the `TileState` grid, `terrain_layer`, `zone_terrain`, `object_placements`, the
`nearest_object_distance` grid, and a `Vec<ZoneBuildState>`. `ModificatorContext`
becomes a thin handle: `{ template, grid, seed, state: &mut TilemapBuildState }`.
This realizes the TMP_003 §2.2 "modificator mutates shared tilemap state" model
for a single-threaded engine without per-(zone,modificator) instances.

**D2 — The `tile_state` grid is the single source of truth.** `Vec<TileState>`
indexed `y*width+x`, length `grid.tile_count()`. Per-zone `area_open` / `area_used`
are **derived** by helper methods (`assigned_tiles` filtered by tile state), never
stored — eliminates the dual-source-of-truth drift bug class. Init rule after
`place_zones`: a tile in some zone's `free_paths` → `Walkable`; else if its zone
is `Forbidden` → `Obstacle`; else → `Open`. (`Forbidden` = "completely blocked"
per `ZoneRole`; blocking it at init is consistent with TMP_001 §5's end-state
invariant — §5's "Obstacle introduced by ObstaclePlacer" describes the common
path, not the only one.) `TileState` stays build-internal — **not** added to
`TilemapView` (TMP_001 §5: "NOT stored in tilemap_view directly"). **`Sea` zones
are not special-cased** — non-free-path `Sea` tiles take the general path to
`Open`. This is intentional: TMP_003 §2.3 registers ObstaclePlacer +
TreasurePlacer on `Sea` zones, and TMP_005 §6 ships Water-terrain biomes
(`underwater_ridge`, `coral_reef`, `seaweed_cluster`, `shipwreck`), so Phases
B/C *do* populate `Sea` zones. The cut V2 water modificators (WaterAdopter /
WaterProxy / WaterRoutes, TMP_003 §2.3) remove inter-zone water *routes*, not
`Sea`-zone object placement; whether a given placer runs on `Sea` zones is that
placer's eligibility decision in B–E. Phase A's init stays uniform.

**D3 — `ObjectManager` is a service module, not a registered pipeline pass.**
Free functions over `&mut TilemapBuildState` (`place_and_connect_object`,
`choose_guard`) plus the `nearest_object_distance` grid living in
`TilemapBuildState`. Placers call it directly. TMP_003 §3.6's "registered as a
modificator so dependency tracking works" is a parallel-framework artifact;
single-threaded, placers declare their real ordering deps by name directly.

**D4 — One modificator, `process` iterates all zones.** Phase 1's model is kept:
a modificator is a single registry entry whose `process(&self, ctx)` loops over
all zones (as `TerrainPainter` already does). No per-zone modificator instances.
Cross-zone passes (ConnectionsPlacer, D) see every zone in one `process` call.

**D5 — Connectivity check.** `connected_components(&TileMask) -> usize` —
4-connected flood-fill (deterministic flat-index order). `would_seal_a_gap(
blocking: &TileMask, passable: &TileMask) -> bool` — `blocking` is the object's
**blocking-cell mask** (`blocking_footprint_at`, §6.2); `passable` is the region
that must stay connected, **`Walkable ∪ Open`** (not the Walkable-only
`free_paths`). TMP_006 §4.2 names the parameter `free_paths`, but objects are
placed on `Open` tiles (TMP_006 §3.4), disjoint from the `Walkable` skeleton —
a literal Walkable-only check would be **inert** (subtracts nothing, always
`false`). The region that fragments when an object blocks `Open` tiles is
`Walkable ∪ Open`; that is what TMP_006 §4.1's "free area split in two" diagram
protects.

`would_seal_a_gap` returns `true` iff placing the object **disconnects a
previously-connected tile pair**. With `blocked_after = passable − blocking`:
true iff `blocked_after.is_empty()` while `!passable.is_empty()` (elimination)
**OR** some connected component of `passable` has surviving tiles (∈
`blocked_after`) that fall into **two or more** distinct components of
`blocked_after` (a split). A naive `connected_components(blocked_after) >
connected_components(passable)` test is **wrong** for a multi-component
`passable` — one footprint can split one component while entirely eliminating
another, leaving the total count unchanged though a real split occurred — and
`zone_passable` is routinely multi-component mid-pipeline as earlier objects
carve the zone. The correct check is O(n): flood-fill-label `passable` and
`blocked_after`, then in one pass flag any `passable`-label that maps to >1
`blocked_after`-label. The elimination clause is load-bearing — a footprint
covering a whole zone's passable area (routine for a thin `Hub` strip, TMP_001
§2.1) leaves no surviving tile. Cost is two flood-fills + an O(n) pass — TMP_006
§4.2 blesses this order as "cheap enough to run on every candidate placement";
the §4.3 pre-filter is a Deferred perf-item. D5 is a deliberate, pinned
correction of TMP_006 §4.2's loose `free_paths` naming and its count-delta test.

**Scope — per-zone.** The check runs against one zone's `zone_passable` (§6.3
step 2a). The player-walkable graph is map-wide (TMP_001 §5 — adjacent `Walkable`
tiles connect across zone borders), but ConnectionsPlacer (Phase D, TMP_007 §3.1)
lays a thin blocked border between zones *before* TreasurePlacer / ObstaclePlacer
run (pipeline order TMP_006 §7), so an object footprint sits wholly inside one
zone, and a cross-zone passage is an explicit `Walkable` corridor whose tiles are
in that zone's `zone_passable` — sealing it is a within-zone seal the per-zone
check catches. A cut that strands two regions joined *only* by a detour through a
neighbour zone makes the per-zone check *over*-reject (conservative, safe), never
under-accept. So a genuinely cross-zone-only seal is not reachable in the V1+30d
pipeline; re-validating this if the border guarantee changes is a Deferred item
(Phase D).

**D6 — Path search.** `search_path(area: &TileMask, start: TileCoord, goals:
&TileMask, cost) -> Option<Path>` — shortest path from `start` to the nearest
set tile of `goals`, over 4-connected moves restricted to `area`. **Dijkstra
(uniform-cost search), not A\*:** Dijkstra is correct for any non-negative `cost`
with no heuristic-admissibility precondition — a Manhattan A\* heuristic is
admissible only when a per-edge cost lower bound ≥ 1 is pinned, and TMP_007 §5's
"curved cost function" / TMP_003 §3.4 terrain costs can fall below 1, so A\* is
deferred as a perf-item. The multi-tile `goals` mask matches TMP_007 §5's real
need — a path from a point to *any* tile of a set (the zone's whole
`free_paths`); a single-target search is just a one-bit `goals` mask.
`cost(from, to) -> f32` contract: finite and ≥ 0. **Determinism is fully pinned**
(TMP-A4), not left to heap-pop chance: the frontier is a min-heap keyed
`(cost, tile.flat_index())`; tiles settle in that order; a tile's predecessor is
set when it is **first settled** and never overwritten by an equal-cost
alternative (only a strictly-lower cost replaces it); neighbours are relaxed in
flat-index order. The reached goal is the lowest-flat-index goal tile among those
at minimal cost. This pins exactly one path — goal choice and every path tile —
so AC-4 checks the path against this stated rule, not against incidental queue
order. `None` when no goal is reachable. `Path` is an ordered `Vec<TileCoord>`
from `start` to the reached goal.

**D7 — Determinism.** Phase A adds no RNG-driven output; every primitive is a
deterministic algorithm. `place_tilemap`'s `TilemapView` output is byte-identical
before and after Phase A — Phase A is a pure refactor plus new *dormant*
primitives; `object_placements` stays empty until a placer registers in Phase B.
The gate is a **committed golden snapshot** (AC-9), not merely a same-seed
`a == b` check — the latter cannot observe the pre-Phase-A baseline, so a
deterministic regression in the `TerrainPainter` rewrite would pass it. The
`seed::sub_seed` helper (already present) serves B–E.

**D8 — Template-schema additive extensions.** All `#[serde(default)]`, no
existing fixture breaks: `TemplateConnection` gains `guard_strength: u32` and
`road: RoadOption`; a `RoadOption` enum (`True` / `False` / `Random`, TMP_007
§2.2) is added; `ZoneSpec` gains `treasure_tiers: Vec<TreasureTierSpec>`; a
`TreasureTierSpec` type (`min`/`max`/`density`, TMP_006 §2) is added. Fields
needing TMP_005/006-defined types (`biome_selection_rules`, banned/required
objects) are deferred to Phase B/C.

**D9 — `ObjectManager` placement contract.** `place_and_connect_object(state,
zone_idx, template, search_area, min_distance, optimize: OptimizeType)
-> Result<PlacementResult, PlacementError>`: (1) keep candidate anchors whose
full footprint `fits` in `search_area`; (2) reject an anchor whose blocking
footprint `would_seal_a_gap` against the zone's passable area, or that sits
closer than `min_distance` to an existing object, or that has no
footprint-excluded access path (see §6.3 step 2); score the survivors per
`OptimizeType` (`Distance` / `BothDistanceAndCenter` / `Center`); (3) place on
the best deterministic-tie-broken anchor — **blocking** footprint tiles →
`Occupied`, push a `TilemapObjectPlacement`, update the distance grid; (4)
return the access `Path`. `PlacementError::NoSpace` when no anchor survives.

**D10 — `nearest_object_distance` is a map-wide, uncapped oracle.** `Vec<f32>`
indexed `y*width+x`, init `f32::INFINITY`; on each placement **every** tile is
lowered to `min(current, euclidean_distance_to_object_anchor)` — the full grid,
no influence-radius cap. It is therefore a *correct* global "distance to nearest
object" oracle **once any object exists**, read directly by both the
`min_distance` reject (§6.3 step 2b) and `OptimizeType::Distance` scoring (§6.3
step 3); before the first object every tile reads `INFINITY` and §6.3 step 3's
first-placement fallback applies. TMP_006 §5.1's "e.g. 20-tile
radius" cap is **rejected**: a capped grid reads `INFINITY` beyond the cap, so
`Distance` scoring would tie-degenerate to the lowest-flat-index anchor on
sparse regions (contradicting §5.2 "maximize distance from existing objects" —
the *common* high-tier-treasure case, TMP_006 §1) and the `min_distance` reject
would under-reject whenever `min_distance` exceeds the cap. The full-grid update
is O(W·H) per placement — for a 256² continent over all placements that is tens
of millions of ops, within the §4.2 flood-fill budget, and it runs once per
placement (not per candidate). Map-wide (not §5.1's "per-zone") is also
deliberate — a border tile can be nearest to an object in the neighbouring zone.

**D11 — `choose_guard` is V1+30d-minimal and infallible.** `choose_guard(terrain:
TerrainKind, strength: u32) -> MonsterTemplate` — `MonsterTemplate` is
`{ strength: u32, terrain_tag: &'static str }`: the `terrain_tag` from a fixed
table **total over all 10 `TerrainKind` variants**, the `strength` carried
through from the argument. It always succeeds — **no `Option`**. TMP_006 §5.3's
`Option`/`None` ("no creature available at this strength") is a **V2** concern —
the V2 faction-weighted creature pool can lack a strength bracket; the V1+30d
flat table cannot. Whether to place a guard *at all* is the caller's decision
(the `needs_guard` / `min_guard_value` gate, TMP_006 §3.3 — a Phase C concern),
not `choose_guard`'s.

**D12 — Error variants.** Phase A's one fallible entry point is
`place_and_connect_object`, which returns a **module-local `PlacementError`**
enum (`#[derive(thiserror::Error)]`; variants `NoSpace`, `NoSuchZone`) per §6.2 /
D9 — *not* a `crate::Error` extension. `crate::Error` already carries
`Placement(String)` (the TMP_002 zone-placement engine) and `Modificator { name,
reason }`; the geometry primitives and `from_zones` are infallible, so Phase A
adds no `crate::Error` variant. A `From<PlacementError> for crate::Error` bridge
lands in Phase C, when the first placer needs to `?`-propagate from
`Modificator::process`. Recoverable-vs-unrecoverable (TMP_003 §5) is a placer
concern (B–E). (This pins §6.2/D9's local-enum design and supersedes an earlier
D12 draft that spoke of extending `crate::Error` — code-review r3 WARN-3.)

## §4 Acceptance criteria

- **AC-1** — `TilemapBuildState` built from `place_zones` output has a
  `tile_state` grid covering every grid tile, each exactly one `TileState`;
  `Walkable` ⟺ tile ∈ some zone's `free_paths`; `Forbidden`-zone non-free tiles
  → `Obstacle`; all other assigned tiles → `Open`. A test asserts a `Sea` zone's
  non-free tiles are `Open` (D2 — `Sea` is not special-cased).
- **AC-2** — `would_seal_a_gap(blocking, passable)` returns true exactly when
  placing the object **disconnects a previously-connected tile pair, or
  eliminates** the passable region (`passable = Walkable ∪ Open`, D5). Verified
  by **(a)** hand-built fixtures with independently-known outcomes — a corridor
  split (true), a footprint covering the *entire* `passable` region (true —
  elimination), a one-tile footprint on an interior tile (false), a footprint
  removing a dead-end stub (false), a footprint over an already-isolated pocket
  (false), a three-way split (true), and — exercising the multi-component case —
  a `passable` of two disjoint blobs with an **empty** `blocking` (false) and one
  where the footprint **splits one blob while eliminating the other** (true,
  though the total component count is unchanged); **and (b)** a *differential*
  property test over random `(passable, blocking)` masks against an **independent
  pairwise-reachability oracle** — expected `true` iff `blocked_after` is empty
  with `passable` non-empty, or some pair of surviving tiles is mutually
  reachable within `passable` but not within `blocked_after` (all-pairs BFS in
  the test, structurally independent of the implementation's flood-fill-label
  algorithm). A count-delta oracle (`connected_components(after) >
  connected_components(before)`) is **not** acceptable — it is wrong for
  multi-component inputs (D5).
- **AC-3** — `connected_components` counts 4-connected regions: empty → 0, one
  blob → 1, two disjoint blobs → 2; diagonal-only adjacency does **not** connect.
- **AC-4** — `search_path` returns a contiguous 4-adjacent shortest path from
  `start` to the nearest tile of `goals` when one exists in `area`, `None` when
  none is reachable. Determinism is verified not by a single input asserted twice
  but by **tie-break fixtures**: a mask with ≥2 equidistant goal tiles asserts
  the pinned nearest-goal choice (lower flat-index), and a mask with ≥2
  equal-length paths to the chosen goal asserts the pinned path choice — both per
  D6's "lower flat-index wins" rule.
- **AC-5** — `TilemapObjectTemplate::fits(anchor, &mask)` is true iff every
  occupied footprint cell lands in-bounds inside `mask`; `footprint_at` projects
  exactly the occupied cells and `blocking_footprint_at` exactly the blocking
  cells; both return `None` if any cell is out of bounds. A test with a mixed
  template (blocking + non-blocking cells) confirms the two projections differ.
- **AC-6** — `place_and_connect_object` places on the best-scoring anchor for
  the given `OptimizeType`, marks the **blocking** footprint `Occupied`, appends
  one `TilemapObjectPlacement`, updates the distance grid, and returns an access
  path; it rejects anchors that seal a gap, lack an access path, or violate
  `min_distance`; `PlacementError::NoSpace` when none survive. A test asserts the
  returned `access_path` (a) shares **no tile** with the placed object's
  `footprint_at` and (b) is the shortest among the footprint-adjacent access
  routes (ties → lower-flat-index start) — the pinned deterministic choice. A
  further test asserts the first placement into an object-free map under
  `BothDistanceAndCenter` is centre-biased, not at a corner (§6.3 step 3).
- **AC-7** — `choose_guard` returns a `MonsterTemplate` carrying the requested
  `strength` and a `terrain_tag` appropriate to the terrain, for **every** one
  of the 10 `TerrainKind` variants — the table is total, `choose_guard` is
  infallible in V1+30d (no `Option`).
- **AC-8** — `TemplateConnection` round-trips JSON with and without
  `guard_strength`/`road` (defaults applied); `ZoneSpec` round-trips with and
  without `treasure_tiers`; every existing Phase-0a/1/2/3 fixture still
  deserializes unchanged.
- **AC-9** — Phase A changes **no** generation output. A golden `TilemapView`
  JSON snapshot, captured from the **pre-Phase-A** engine (BUILD chunk 1, before
  any Phase A change) for the `tests/determinism.rs` fixture(s) and committed,
  is reproduced **byte-identically** by the post-Phase-A engine — a true
  before/after gate (a same-seed `a == b` check alone cannot see the pre-Phase-A
  side). The existing same-seed determinism assertion is kept; `object_placements`
  stays empty. (Phase B regenerates the golden when it legitimately changes the
  output.)
- **AC-10** — `cargo test --workspace` green; `cargo clippy --workspace` clean.

## §5 Test plan

- Unit tests inline per module; connectivity + path search additionally get
  **property-style tests** (random masks, invariant assertions) — Phase A is the
  foundation and a bug here compounds into B–E.
- `tests/determinism.rs` extended with the before/after byte-identity check
  (AC-9).
- `cargo test --workspace` + `cargo clippy --workspace` are the VERIFY gate.

## §6 Module design (DESIGN)

### §6.1 File layout

```
src/
  engine/
    build_state.rs       NEW  TilemapBuildState · ZoneBuildState · init + derived helpers
    object_manager.rs    NEW  place_and_connect_object · choose_guard · distance grid
    geometry/
      mod.rs             NEW  module re-exports
      connectivity.rs    NEW  connected_components · would_seal_a_gap
      pathfind.rs        NEW  search_path · Path
    mod.rs               MOD  place_tilemap threads TilemapBuildState
    pipeline/
      modificator.rs     MOD  ModificatorContext reshaped to { template, grid, seed, state }
      registry.rs        MOD  test fixtures rebuilt on the new context
    modificators/
      terrain_painter.rs MOD  reads/writes via ctx.state; tests updated
  types/
    object_template.rs   NEW  TilemapObjectTemplate · FootprintCell
    treasure.rs          NEW  TreasureTierSpec
    template.rs          MOD  TemplateConnection +guard_strength +road · ZoneSpec +treasure_tiers
    zone.rs              MOD  RoadOption enum
    mod.rs               MOD  re-exports
  error.rs               MOD  Error::Placement variant
  lib.rs                 MOD  module declarations
```

### §6.2 Key signatures

```rust
// engine/build_state.rs
pub struct TilemapBuildState {
    pub grid: GridSize,
    pub tile_state: Vec<TileState>,                  // y*width+x, len = tile_count
    pub terrain_layer: Vec<u8>,
    pub zone_terrain: Vec<Option<TerrainKind>>,
    pub object_placements: Vec<TilemapObjectPlacement>,
    pub nearest_object_distance: Vec<f32>,           // y*width+x, init f32::INFINITY
    pub zones: Vec<ZoneBuildState>,
}
pub struct ZoneBuildState {
    pub id: ZoneId, pub role: ZoneRole, pub center: TileCoord,
    pub assigned_tiles: TileMask,                    // immutable post-placement
    pub free_paths: TileMask,                        // grows in Phase D
}
impl TilemapBuildState {
    pub fn from_zones(zones: Vec<ZoneTiles>, grid: GridSize) -> Self;   // D2 init rule
    pub fn tile_state_at(&self, c: TileCoord) -> TileState;
    pub fn set_tile_state(&mut self, c: TileCoord, s: TileState);
    pub fn zone_area_open(&self, zone_idx: usize) -> TileMask;          // assigned ∩ Open
    pub fn zone_passable(&self, zone_idx: usize) -> TileMask;           // assigned ∩ {Walkable|Open}
}

// engine/pipeline/modificator.rs
pub struct ModificatorContext<'a> {
    pub template: &'a TilemapTemplate,
    pub grid: GridSize,
    pub seed: TilemapSeed,
    pub state: &'a mut TilemapBuildState,
}

// types/object_template.rs
pub struct FootprintCell { pub dx: i32, pub dy: i32, pub blocking: bool }
pub struct TilemapObjectTemplate { pub name: String, pub cells: Vec<FootprintCell> }
impl TilemapObjectTemplate {
    pub fn footprint_at(&self, anchor: TileCoord, grid: GridSize) -> Option<TileMask>;          // all cells; None if OOB
    pub fn blocking_footprint_at(&self, anchor: TileCoord, grid: GridSize) -> Option<TileMask>; // blocking cells only
    pub fn fits(&self, anchor: TileCoord, area: &TileMask) -> bool;
    pub fn area(&self) -> usize;                     // occupied-cell count — largest-first sort key
}

// engine/geometry/connectivity.rs
pub fn connected_components(mask: &TileMask) -> usize;                       // 4-connected
pub fn would_seal_a_gap(blocking: &TileMask, passable: &TileMask) -> bool;   // label-map: disconnects a connected pair, OR elimination (D5)

// engine/geometry/pathfind.rs
pub type Path = Vec<TileCoord>;
pub fn search_path(
    area: &TileMask, start: TileCoord, goals: &TileMask,
    cost: impl Fn(TileCoord, TileCoord) -> f32,      // finite, ≥ 0; RoadPlacer (E) terrain cost
) -> Option<Path>;                                   // Dijkstra; nearest goal; flat-index tie-break

// engine/object_manager.rs
pub enum OptimizeType { Distance, BothDistanceAndCenter, Center }
pub struct PlacementResult { pub anchor: TileCoord, pub footprint: TileMask, pub access_path: Path }
pub enum PlacementError { NoSpace }
pub struct MonsterTemplate { pub strength: u32, pub terrain_tag: &'static str }

pub fn place_and_connect_object(
    state: &mut TilemapBuildState, zone_idx: usize,
    template: &TilemapObjectTemplate, kind: TilemapObjectKind,
    search_area: &TileMask, min_distance: f32, optimize: OptimizeType,
) -> Result<PlacementResult, PlacementError>;
pub fn choose_guard(terrain: TerrainKind, strength: u32) -> MonsterTemplate;  // total table — infallible
```

### §6.3 `place_and_connect_object` algorithm (D9 detail)

1. **Candidates** — every anchor in `search_area` whose `template.footprint_at`
   is `Some` (in-bounds) and `fits` inside `search_area`.
2. **Reject** an anchor if any of: **(a)** `would_seal_a_gap(
   blocking_footprint_at(anchor), &zone_passable(zone_idx))` is true
   (`zone_passable` = the zone's `Walkable ∪ Open` mask, D5); **(b)** the
   anchor's `nearest_object_distance` is below `min_distance` (D10 — the grid is
   an exact uncapped oracle, so this holds for any `min_distance`); **(c)** no
   access path exists. Take the footprint-adjacent passable tiles in **ascending
   flat-index order**; for each `adj`, compute `search_path(zone_passable(zone_idx)
   − footprint_at(anchor), adj, &zone.free_paths, uniform_cost)` (`uniform_cost ≡
   1.0`; the candidate's own full footprint is subtracted so the access path
   cannot thread the not-yet-placed object). Reject if **every** `adj` yields
   `None`; otherwise the anchor's **access path** is pinned as the **shortest**
   path produced (fewest tiles; ties broken by the lower-flat-index `adj`) — a
   single deterministic choice, required for TMP-A4.
3. **Score** survivors per `OptimizeType` — `Distance` = `nearest_object_distance`
   at the anchor; `Center` = `-dist(anchor, zone.center)`; `BothDistanceAndCenter`
   = their sum. Best score wins; ties break to the lower flat-index anchor
   (TMP-A4). **First-placement fallback:** when `object_placements` is empty
   (every `nearest_object_distance` is `INFINITY` — only the first placement of
   the whole generation), the distance term is undefined and would tie every
   candidate; `Distance` and `BothDistanceAndCenter` fall back to the `Center`
   term for that call, so the first pile is centre-biased, not corner-biased
   (TMP_006 §5.2 — `BothDistanceAndCenter` is "scattered but not all on map edge").
4. **Commit** — blocking footprint cells → `Occupied`; push
   `TilemapObjectPlacement { kind, anchor, canon_ref: None }`; lower
   `nearest_object_distance` over the **whole grid** (D10). Return
   `PlacementResult { anchor, footprint, access_path }` — `access_path` is the
   one pinned in step 2(c).
5. No survivor → `Err(PlacementError::NoSpace)`.

### §6.4 Build-state init (`from_zones`, D2)

`tile_state` length `grid.tile_count()`, every entry written exactly once:
for each zone, for each `assigned_tiles` tile — `Walkable` if in `free_paths`,
else `Obstacle` if `role == Forbidden`, else `Open` (`Sea` zones included — not
special-cased, per D2). `place_zones` already guarantees `assigned_tiles` is a
disjoint full-grid partition (its own AC-2), so every grid index is covered. A
debug assertion checks total coverage.
