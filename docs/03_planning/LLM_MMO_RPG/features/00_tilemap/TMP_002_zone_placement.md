# TMP_002 — Zone Placement Algorithm

> **Conversational name:** "Zone Placement" (TMP-PLACE). The geometric algorithm that takes a zone-graph template and produces zone centers + zone-tile-assignments on the tilemap grid.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **CANDIDATE-LOCK 2026-05-13** (DRAFT 2026-05-13 → revised 2026-05-13 for license-hygiene framing → CANDIDATE-LOCK closure pass: TMP-PLACE-Q1..Q3 RESOLVED at §9)
> **Owns:** zone-placement algorithm (TMP-5 + TMP-6 + TMP-8 catalog entries)
> **Algorithm foundations:** Fruchterman & Reingold (1991) force-directed placement; Penrose (1974) aperiodic tiling; standard pathfinding + procedural-level-generation literature. Full citations in §10 Prior Art.

---

## §1 The problem

Given an undirected graph of zones with sizes + edges (connections), find a 2D layout where:

- **Connected zones are close** (so passage between them feels natural)
- **Distant zones are far apart** (so the map has spatial coherence)
- **Zones don't overlap** (each zone owns its own tile region)
- **Zones don't extend past map boundary**
- **Author-tagged repulsive (`PassageKind::Adversarial`) edges** push zones apart explicitly

Naive solutions:
- **Grid placement only:** stiff, predictable, doesn't respect edge density variations.
- **Voronoi from random points:** produces overlapping or empty zones often.
- **Pure force-directed:** can get stuck in local minima for large zone graphs.

Combining 3 phases solves it. This is a standard pattern in procedural map generation across the genre prior art (§10) — every game in the survey uses some variant of (initial seed → force-relaxation → polygon assignment):

1. **Initial grid seed** — N×N grid sized to zone count; deterministic baseline.
2. **Force-directed convergence** — Fruchterman-Reingold (Fruchterman & Reingold 1991) with simulated annealing.
3. **Vertex-based polygon assignment** — Penrose tiling (Penrose 1974) gives each zone a natural-feeling irregular polygon (not rectangles, not Voronoi).

Then **fractalize** (separate phase, per zone) — carves a path skeleton inside each zone using a random-distant-tile algorithm common to roguelike level generators (cf. Žára 2014, RogueDev talks).

---

## §2 Inputs + outputs

### 2.1 Inputs

From `tilemap_template`:
- `zones: HashMap<ZoneId, ZoneSpec>` — N zones with `size: u32` (relative size weight)
- `connections: Vec<ZoneEdgeSpec>` — M edges with `PassageKind`
- `applicable_tier`, `default_grid_size` — determines `grid_width × grid_height`

From `RmgMap`/runtime context:
- `seed: u64` — deterministic RNG seed (per TMP-A4)
- `tilemap_defaults.single_thread: bool` — debug determinism mode

### 2.2 Outputs

Per zone in `tilemap_view`:
- `center_position: (u32, u32)` — final tile coordinate of zone center
- `assigned_tiles: TileMask` — bitmask of which grid tiles belong to this zone (per-zone disjoint partition)
- `free_paths: TileMask` — post-fractalize, the connected free-path skeleton within the zone

---

## §3 Phase 1: Force-directed placement

### 3.1 Initial grid seed

Goal: produce a sane starting layout based on zone graph distances.

Algorithm:
```
1. Compute distance graph between zones (BFS over connections; PassageKind::Adversarial
   + PassageKind::Portal connections excluded — they don't impose proximity constraints)
2. Determine grid dimension N = ceil(sqrt(num_zones)):
   - 5 zones → 3×3 grid
   - 10 zones → 4×4 grid
   - 24 zones → 5×5 grid
3. Assign each zone to a grid cell:
   - Iterate zones in deterministic order (zone_id ascending)
   - For each zone, find the grid cell that minimizes:
     sum over already-placed neighbors: |grid_pos(neighbor) - grid_pos(candidate)|
     PLUS for each Adversarial-connected zone: -|grid_pos(adversarial) - candidate|
4. Convert grid cell to normalized 0..1 (zone_pos.x = (grid_x + 0.5) / N)
5. Set zone.center = (zone_pos.x, zone_pos.y, level)
```

`level` is the Z coordinate (V1+30d always 0; V3 underground via TMP-D9 introduces verticality).

### 3.2 Fruchterman-Reingold convergence

Algorithm reference: Fruchterman, T. M. J. & Reingold, E. M. (1991). "Graph Drawing by Force-Directed Placement." *Software—Practice and Experience* 21(11), 1129–1164. Method specifics below adapted from the original paper.

Conceptual model:
- Each zone is a **soft sphere** with radius proportional to `sqrt(size)`
- Connected zones **attract** each other like springs (attractive force proportional to distance squared divided by an "optimal distance" constant — the FR formula)
- Overlapping zones **repel** with force inversely proportional to distance (FR repulsion formula)
- **`PassageKind::Adversarial` edges:** always push apart regardless of overlap
- **Player-color scaling** (V2+ multiplayer): low-index players get extra distance scaling for fairness; V1+30d zones have no `owner` so this term is 0.
- Map boundary repulsion: zones too close to edge get pushed inward.

Annealing schedule (FR with simulated annealing — Kirkpatrick, Gelatt & Vecchi 1983):
```
temperature = T_initial          (FR: roughly grid_size / num_zones)
WHILE temperature > T_minimum:
    1. Compute attractive forces from connected zones (FR formula)
    2. Compute repulsive forces from overlapping zones + Adversarial connections + boundaries
    3. Sum forces; move each zone by force vector capped at `temperature`
    4. Evaluate solution: fitness = (total_distance_excess + 1) * (total_overlap + 1)
    5. IF improvement: save as best; continue
    6. ELSE:
       a. Try "drastic move": swap two most-misplaced zones (escape local minimum)
       b. IF still no improvement: temperature *= cooling_factor (0.97 typical; FR uses linear cooling, we adopt exponential for smoother annealing)
END WHILE
```

Convergence criteria (LoreWeave-specific):
- **Max iterations:** 1000 (TMP-Q5 default)
- **Max wall-clock:** 5 seconds (TMP-Q5 default)
- **No-improvement threshold:** 50 iterations without improvement → declare converged

If neither converges → emit `tilemap.generation_failed` or `tilemap.generation_timeout`; UI falls back to MAP_001 graph view for this channel.

### 3.3 Misplaced-zone swap heuristic (escape local minima)

Force-directed methods are notorious for local minima. When an iteration produces no improvement, identify the worst-placed zone (highest misplacement-to-movement ratio) and try:

1. **Swap with another misplaced zone** on same level, NOT connected to first zone (avoids breaking adjacency requirements).
2. If swap impossible: **move toward most-distant-connected zone** (reduce distance) OR **move away from most-overlapping zone** (reduce overlap), based on which is the worse violation.

`lastSwappedZones` set prevents oscillation (no zone is swapped twice in consecutive iterations). This is a standard local-search escape mechanism (Glover 1990, "Tabu Search").

### 3.4 LoreWeave-specific tuning vs FR original

| Aspect | FR original (1991) | LoreWeave V1+30d |
|---|---|---|
| Time limit | None (anneals until stable) | 5s wall-clock OR 1000 iterations cap (TMP-Q5) |
| Cooling schedule | Linear | Exponential (smoother convergence near minimum) |
| Map levels | Single layer (FR is 2D-only) | Single level V1+30d (no underground; V3 TMP-D9 may add Z dimension) |
| Player owner scaling | N/A (FR is generic graph drawing) | Active only when `ZoneSpec.owner: Some(_)` is set (V2+ multiplayer scenario; V1+30d zones have no owner) |
| Water zone special case | N/A | One extra zone added by engine when `default_water_content != None` |
| Logging | N/A | Per-iteration metric in `GenerationMetadata.iteration_count` + ops dashboard timing |

---

## §4 Phase 2: Penrose tiling for zone shapes

### 4.1 Why irregular polygons (not Voronoi)

Naive approaches:
- **Voronoi from zone centers:** produces straight-edged polygons, looks artificial. Doesn't match organic narrative feel.
- **Random circular zones:** produces overlaps + gaps.
- **Force-directed shape relaxation:** expensive + still looks artificial.

**Penrose tiling** (Penrose 1974) — aperiodic non-repeating triangular subdivision — generates a set of vertices distributed irregularly over the plane. Assign each vertex to its closest zone, then assign each tile to the zone whose vertex it's closest to. Result: zones have **irregular, organic-feeling polygon boundaries** with natural-looking variation between generations.

Mathematical foundation: Penrose's P3 tiling uses two rhombus prototiles (acute + obtuse), subdivided by the golden ratio φ = (1 + √5) / 2. Repeated subdivision generates a quasi-crystalline vertex pattern with 5-fold rotational symmetry that does NOT tile periodically.

Different tilings per Z-level (different random rotation per channel) so surface + underground would feel distinct. V1+30d single-level: still re-rolls tiling per channel for variety.

### 4.2 Algorithm

```
1. Initialize Penrose seed with 5 isoceles triangles around (0, 0):
   - Each triangle has angle 36° at origin
   - Vertices: { (0, 0), (cos(k*72°), sin(k*72°)) for k in 0..5 }
2. Iteratively subdivide:
   - For each triangle, apply "sun" or "star" subdivision rules
   - Subdivision uses golden ratio phi = (1 + sqrt(5)) / 2 proportions
   - Repeat until vertex count >= target (LoreWeave: target = max(zones × 10, 200))
3. Normalize all vertices to [0, 1] × [0, 1] (center over middle of map)
4. Random rotation (deterministic from seed) so tiling orientation varies
5. Output: Vec<(f64, f64)> of vertex positions (deduplicated)
```

### 4.3 Assign vertices to zones; tiles to vertices

```
1. For each Penrose vertex:
   - Find closest zone center; mark vertex → zone
2. For each tile (x, y) in 0..grid_width × 0..grid_height:
   - Convert to normalized: (x / grid_width, y / grid_height)
   - Find closest Penrose vertex
   - Tile belongs to vertex's zone
   - Update tilemap_view.zones[zone_id].assigned_tiles bit
3. Update zone_id-per-tile grid (denormalized for fast lookup at runtime)
```

### 4.4 Post-assignment center-of-mass adjustment

After polygon assignment, recompute each zone's center to be the centroid of its assigned tiles. This ensures `center_position` reflects actual tile assignment, not force-directed circular approximation.

```rust
for zone in zones:
    let tiles = zone.assigned_tiles.to_vec();
    let cx = tiles.iter().map(|t| t.x).sum::<u32>() / tiles.len() as u32;
    let cy = tiles.iter().map(|t| t.y).sum::<u32>() / tiles.len() as u32;
    zone.center_position = (cx, cy);
```

### 4.5 Edge cases

- **Empty zone after tiling assignment:** emit `tilemap.empty_zone`; likely template misconfiguration (zone size too small for grid resolution); UI shows error + suggests scaling up.
- **Degenerate Penrose (all vertices coincide):** shouldn't happen with proper seed; defensively detect and emit `tilemap.generation_failed`.

---

## §5 Phase 3: Fractalize (zone interior path skeleton)

Algorithm pattern: random-distant-tile path-extension. Common in roguelike level generators; see Žára (2014, RogueDev talks) for pedagogical treatment.

### 5.1 Goal

After polygon assignment, **all tiles in a zone are `Open`** (passable but empty). Fractalize:

1. Picks a free starting point (zone center).
2. Iteratively grows a **free-path skeleton** of tiles by picking distant tiles and routing paths to them.
3. Final result: every zone has a connected `free_paths` (`Walkable`) network; remaining tiles stay `Open` (for objects) or get marked `Obstacle` later (for fill).

This produces interior structure: zones aren't just blob-filled, they have meandering open paths that objects + roads can attach to.

### 5.2 Algorithm

```
Constants (LoreWeave defaults; per-template tunable):
  min_distance = 9 * 9                              (squared distance threshold)
  free_distance = level == surface ? 9*9 : 10*10    (V1+30d only surface)
  span_factor = level == surface ? 0.45 : 0.3       (path narrowness; lower = wider paths)
  margin_factor = 1.0

Adjust based on treasure density:
  total_treasure_value = sum over zone.treasure_tiers: (min+max)/2 * density / 1000
  treasure_density = sum over zone.treasure_tiers: density

  IF treasure_value > 250:
    margin_factor scales 0.6..1.0 (more value → less margin → more obstacles)
    span_factor scales similarly
  ELIF treasure_value < 100:
    span_factor scaled 0.5 * (treasure_value/100); minimum 0.15
  IF treasure_density <= 10:
    span_factor capped (add extra obstacles to fill empty space)

Special zone roles:
  - Sea: span_factor = 0.2 (sparse obstacles on water)
  - Hub: skip fractalize entirely (hub is single straight path)
  - Forbidden: BLOCK all tiles; clear assigned_tiles; return

block_distance = min_distance * span_factor
free_distance = free_distance * margin_factor (min 4*4)

Main loop (non-hub non-forbidden):
  cleared_tiles = zone.free_paths (initially just center)
  open_tiles = zone.assigned_tiles
  tiles_to_ignore = empty

  WHILE open_tiles is non-empty:
    candidate_list = open_tiles
    REMOVE tiles within MARGIN=3 of map boundary (avoid paths adjacent to map edge)
    SHUFFLE candidate_list (deterministic from seed)

    node_found = None
    FOR each tile in candidate_list:
      closest_free = cleared_tiles.nearest(tile)
      IF tile.distSq(closest_free) <= free_distance:
        tiles_to_ignore.add(tile)  # tile is close enough to existing path; doesn't need new path
      ELSE:
        node_found = tile
        cleared_tiles.add(tile)  # new path waypoint
        BREAK

    open_tiles.subtract(tiles_to_ignore)
    IF node_found is None: BREAK  # all tiles are close to free-paths
    tiles_to_ignore.clear()
  END WHILE

Connect free areas (handle disconnected fragments):
  areas = connected_components(cleared_tiles)
  FOR each fragment area:
    IF area not connected to main:
      Find shortest path from area to main_cleared_tiles (Dijkstra over Open tiles)
      Add path tiles to cleared_tiles

zone.free_paths = cleared_tiles
zone.area_open = assigned_tiles - cleared_tiles  # remaining for objects/obstacles
```

### 5.3 Why this works

- Random distant-tile picks ensure paths reach all parts of the zone, not just clustered near center.
- `free_distance` threshold prevents wasteful path redundancy (don't route to tiles already near path).
- `span_factor` controls path density: low value → dense paths → less obstacle space; high value → sparse paths → more obstacle space.
- Treasure-density scaling: zones with more treasures get more free-paths so treasures have room.

### 5.4 LoreWeave-specific additions

| Addition | Reason |
|---|---|
| `MARGIN=3` from map edge | Paths adjacent to map boundary look bad in render. |
| Connected-components fixup at end | Handles fragmented zones (rare but possible). |
| Per-zone seed sub-derivation | Per-zone parallelism without breaking determinism (TMP_003 §4 parallel mode). |

---

## §6 Pseudo-implementation sketch

```rust
pub struct ZonePlacementContext<'a> {
    pub template: &'a TilemapTemplate,
    pub grid_size: GridSize,
    pub seed: u64,
    pub level: u8,                 // V1+30d always 0
    pub max_iterations: u32,       // TMP-Q5 default 1000
    pub max_wall_clock: Duration,  // TMP-Q5 default 5s
}

pub struct ZonePlacementResult {
    pub zones: Vec<ZoneRuntime>,         // populated with center_position + assigned_tiles + free_paths
    pub iteration_count: u32,
    pub converged: bool,                  // true if reached fitness threshold; false if hit cap
}

pub fn place_zones(ctx: &ZonePlacementContext) -> Result<ZonePlacementResult, TilemapError> {
    let mut rng = ChaCha8Rng::seed_from_u64(ctx.seed);
    let zones = compute_distance_graph_and_initial_grid(ctx.template, &mut rng);
    let (zones, iters, converged) = force_directed_converge(zones, ctx, &mut rng)?;
    let zones = assign_tiles_via_penrose(zones, ctx.grid_size, &mut rng);
    let zones = zones.into_iter().map(|z| fractalize_zone(z, ctx, &mut rng)).collect::<Vec<_>>();
    Ok(ZonePlacementResult { zones, iteration_count: iters, converged })
}
```

Concrete sub-function shapes:
- `compute_distance_graph_and_initial_grid` — BFS distance + grid placement (§3.1)
- `force_directed_converge` — main FR loop (§3.2-§3.3)
- `assign_tiles_via_penrose` — Penrose generation + assignment (§4)
- `fractalize_zone` — per-zone path skeleton (§5)

`fractalize_zone` can be parallelized via Rayon (per-zone independent) when `single_thread == false`. See TMP_003 §4.

---

## §7 Performance + complexity

| Phase | Complexity | V1+30d budget |
|---|---|---|
| Initial grid placement | O(N × M) where N=zones, M=edges | <1ms for 20 zones |
| Force-directed convergence | O(N² × iterations) per step | <2s for 20 zones × 1000 iters |
| Penrose tiling | O(V) vertices subdivided + O(W × H) tile assignment | <500ms for 256×256 |
| Fractalize | O(W × H) per zone, parallel | <500ms total parallel |
| **Total** | | **<5s for 256×256 continent w/ 20 zones** |

For comparison, mature open-source implementations of similar pipelines (e.g., VCMI's RMG; see §10) achieve ~5-30 seconds for typical large maps. LoreWeave V1+30d aims for similar.

---

## §8 Determinism + parallelism

Per TMP-A4 + TMP-A10:

- **Determinism:** all RNG derived from `seed` via Blake3-chained ChaCha8 sub-seeds. Per-zone fractalize uses sub-seed `blake3(seed || zone_id)` so per-zone parallelism doesn't break determinism.
- **Parallelism:** force-directed convergence is **inherently sequential** (each iteration depends on previous). Penrose tile-assignment **can be parallelized** (per-tile classification is independent). Fractalize **can be parallelized per-zone** (zones disjoint after Penrose).
- **Single-thread mode (`tilemap_defaults.single_thread = true`):** runs everything sequentially; for deterministic-debug; slower but reproducible across machines.

---

## §9 Resolved questions (closure pass 2026-05-13)

| ID | Question | Locked decision | How resolved |
|---|---|---|---|
| TMP-Q5 (cross-ref TMP_001) | Force-directed convergence cap | **1000 iters OR 5s wall-clock**, whichever first; emit `tilemap.generation_timeout` on cap hit | ✅ ACCEPT (resolved at TMP_001 §12) |
| TMP-PLACE-Q1 | Penrose tiling vs hex-grid alternative | **Penrose V1+30d** — organic feel matches author intent; hex-grid alternative reserved as V2+ TMP-D14 if author demand emerges | ✅ ACCEPT default |
| TMP-PLACE-Q2 | Convergence-failure fallback | **Fall back to grid-only placement + log warning** V1+30d; always log `tilemap.generation_failed` info-event to ops dashboard with iteration_count + reason | ✅ ACCEPT default |
| TMP-PLACE-Q3 | Expose iteration progress to UI | **YES** — stream `GenerationMetadata.iteration_count` + per-modificator timing via DP-Ch24 subscribe to UI; FE renders progress bar during continent-tier bootstrap (~5s typical) | ✅ ACCEPT default |

---

## §10 Prior Art

### Academic foundations (algorithm sources)

- **Fruchterman, T. M. J. & Reingold, E. M. (1991).** "Graph Drawing by Force-Directed Placement." *Software—Practice and Experience* 21(11), 1129–1164. — §3 force-directed algorithm.
- **Kirkpatrick, S., Gelatt, C. D. & Vecchi, M. P. (1983).** "Optimization by Simulated Annealing." *Science* 220(4598), 671–680. — §3.2 annealing schedule.
- **Penrose, R. (1974).** "Role of aesthetics in pure and applied mathematical research." *Bulletin of the IMA* 10, 266–271. — §4 aperiodic tiling for zone polygons.
- **Glover, F. (1990).** "Tabu Search — Part I." *ORSA Journal on Computing* 1(3), 190–206. — §3.3 misplaced-zone swap pattern (tabu list).
- **Dijkstra, E. W. (1959).** "A note on two problems in connexion with graphs." *Numerische Mathematik* 1, 269–271. — §5.2 shortest-path connection of fragments.
- **Tarjan, R. E. (1976).** "Edge-disjoint spanning trees and depth-first search." *Acta Informatica* 6, 171–185. — §5.2 connected-components fixup.

### Genre prior art (procedural map generation in similar games)

- **Heroes of Might and Magic III** (1999). New World Computing. Pioneered the zone-graph procedural map generator. Genre prior art for the overall shape.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented RMG implementation at <https://github.com/vcmi/vcmi/tree/develop/lib/rmg> and design notes at <https://github.com/vcmi/vcmi/blob/develop/docs/developers/RMG_Description.md>. Cited as one mature open-source reference implementation of the genre patterns.
- **Battle for Wesnoth** (2003+, GPL v2+). Tile-based fantasy TBS with author-extensible map generators.
- **Civilization V / VI** (Firaxis Games). Climate-band procedural map generation.
- **Caves of Qud** (Freehold Games). Procedural biome composition with hand-authored set-piece interleaving.

### Roguelike + procedural-generation pedagogy

- **Žára, O. (2014).** "Procedural map generation in roguelikes." *RogueDev online talks.* — Pedagogical introduction to tile state machines + free-path generation algorithms similar to §5.
- **Bob Nystrom (2014).** "Rooms and Mazes: A Procedural Dungeon Generator." Blog post + algorithm walkthrough. — Reference implementation of room-graph + corridor connection.
- **Yannakakis, G. N. & Togelius, J. (2018).** *Artificial Intelligence and Games.* Springer. Chapter 5: Procedural Content Generation. — Academic survey of PCG techniques.
