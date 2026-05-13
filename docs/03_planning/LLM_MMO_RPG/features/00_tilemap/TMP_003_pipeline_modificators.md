# TMP_003 — Pipeline Modificators

> **Conversational name:** "Pipeline" (TMP-PIPE). The modificator pattern + dependency graph + execution engine. Each generation step (terrain paint, treasure place, obstacle fill, etc.) is a Modificator with declared dependencies; the engine sorts them topologically and runs them in parallel where dependencies allow.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **CANDIDATE-LOCK 2026-05-13** (DRAFT 2026-05-13 → revised 2026-05-13 for license-hygiene framing → CANDIDATE-LOCK closure pass: TMP-PIPE-Q1..Q4 RESOLVED at §6)
> **Owns:** TMP-9 + TMP-10 + TMP-29 catalog entries
> **Architectural foundations:** Strategy + Visitor patterns (Gamma et al. 1994); topological sort (Kahn 1962); dependency-graph scheduling. Full citations in §7 Prior Art.
> **Cross-refs:** Mirrors [EVT-G1..G6 + Coordinator](../../07_event_model/12_generation_framework.md) Generator framework architecture — same topology-graph + dependency pattern.

---

## §1 Why pipeline pattern

Random map generation is inherently **multi-phase**:
- Can't paint terrain until zone tiles are assigned
- Can't place treasures until zones know their `area_open`
- Can't fill obstacles until treasures placed (need to know what tiles are `Occupied`)
- Can't draw roads until towns + treasure-pile guards are placed (roads connect them)
- Can't draw rivers until mountain placement (rivers flow from mountains to lakes)
- Some phases need **all zones to complete prior phase** before they can start (e.g., underground rock-fill needs all underground zones to finish treasure placement)

Standard architectural answer: each phase is a **Modificator** (a Strategy in the GoF sense) with explicit `dependency()` declarations. Engine topologically sorts (Kahn 1962) and runs with a thread pool, respecting deps. This is the same pattern used at LoreWeave's EVT-G* Generator framework, and the pattern found across procedural map generators in the genre prior art (§7).

V1+30d ships **7 modificators** + adds 2-3 V2.

---

## §2 The Modificator base

Standard Strategy + Visitor pattern (Gamma et al. 1994), adapted for our concurrent-execution context:

```rust
pub trait Modificator: Send + Sync {
    /// Modificator declares dependencies + postfunctions during init.
    /// Called once per zone after all modificators are added but before any process() runs.
    fn init(&mut self, zone: &Zone, tilemap: &TilemapContext);

    /// The actual generation step. Mutates zone state + tilemap state.
    /// Called when all dependencies have completed (or in parallel for independent modificators).
    fn process(&mut self, zone: &mut Zone, tilemap: &mut TilemapContext) -> Result<(), TilemapError>;

    /// Modificator name for logging + perf metrics.
    fn name(&self) -> &str;
}

pub struct ModificatorRegistry {
    modificators: Vec<Box<dyn Modificator>>,
    deps: HashMap<ModificatorId, Vec<ModificatorId>>,     // forward deps (this depends on those)
    postfns: HashMap<ModificatorId, Vec<ModificatorId>>,  // reverse deps (those depend on this)
}

impl ModificatorRegistry {
    pub fn add(&mut self, mod: Box<dyn Modificator>);
    pub fn dependency(&mut self, mod_id: ModificatorId, dep_id: ModificatorId);
    pub fn postfunction(&mut self, mod_id: ModificatorId, post_id: ModificatorId);

    /// Topological order (Kahn 1962); respects deps. Returns iterator of (parallel-runnable batch).
    pub fn iter_topological_batches(&self) -> impl Iterator<Item = Vec<&dyn Modificator>>;

    /// Execute pipeline (parallel or single-thread per config).
    pub fn execute(&self, tilemap: &mut TilemapContext, single_thread: bool) -> Result<(), TilemapError>;
}
```

### 2.1 dependency() vs postfunction()

Two API forms for the same DAG edge:
- `dependency(X)` — this modificator must run AFTER X (X is a prerequisite)
- `postfunction(X)` — this modificator must run BEFORE X (X is a consumer)

These are duals. In a single-edge view of the dependency DAG, `M.dependency(X)` is equivalent to `X.postfunction(M)`. Both API forms exist for ergonomic reasons (writing per-modificator code, sometimes you want to say "I follow X" vs "X follows me").

Convenience macros:
```rust
macro_rules! DEPENDENCY      { ($x:ty) => { dependency(zone.get_modificator::<$x>()) } }
macro_rules! POSTFUNCTION    { ($x:ty) => { postfunction(zone.get_modificator::<$x>()) } }
macro_rules! DEPENDENCY_ALL  { ($x:ty) => { for z in map.zones() { dependency(z.get_modificator::<$x>()); } } }
macro_rules! POSTFUNCTION_ALL{ ($x:ty) => { for z in map.zones() { postfunction(z.get_modificator::<$x>()); } } }
```

`DEPENDENCY_ALL` / `POSTFUNCTION_ALL` create **cross-zone dependencies** (e.g., a rock-fill modificator depends on all zones' treasure placement completing). LoreWeave V1+30d retains this pattern.

### 2.2 Modificator ownership of zone state

Each Modificator mutates **a specific zone's state** (terrain, objects, paths) — one Modificator instance per (Zone, ModificatorType) pair. Modificator base holds a reference to its zone:

```rust
pub struct ModificatorContext<'a> {
    pub zone: &'a mut Zone,                    // the zone this modificator operates on
    pub tilemap: &'a mut TilemapContext,       // shared tilemap state (read + cross-zone)
    pub rng: &'a mut ChaCha8Rng,                // per-(zone, modificator) deterministic sub-RNG
}
```

`tilemap.zones[]` — for cross-zone reads (e.g., ConnectionsPlacer needs neighbor zone state). Uses `RwLock` per zone for thread-safety (see §4).

### 2.3 Registration

Pseudo-Rust skeleton (specific modificator wiring at LoreWeave's chosen tilemap-service):

```rust
pub fn add_modificators(tilemap: &mut TilemapContext) {
    let mut has_object_distributor = false;
    let mut has_hero_placer = false;

    for zone in tilemap.zones.iter_mut() {
        zone.add_modificator::<ObjectManager>();
        if !has_object_distributor {
            zone.add_modificator::<ObjectDistributor>();   // V2; some types are global, not per-zone
            has_object_distributor = true;
        }
        zone.add_modificator::<TreasurePlacer>();
        zone.add_modificator::<ObstaclePlacer>();
        zone.add_modificator::<TerrainPainter>();

        if zone.spec.zone_role == ZoneRole::Sea {
            for z in tilemap.zones.iter_mut() {
                z.add_modificator::<WaterAdopter>();
            }
            zone.add_modificator::<WaterProxy>();          // V2
            zone.add_modificator::<WaterRoutes>();         // V2
        } else {
            zone.add_modificator::<TownPlacer>();           // V2 — V1+30d: MAP_001 supplies positions
            zone.add_modificator::<MinePlacer>();           // V2
            zone.add_modificator::<ConnectionsPlacer>();
            zone.add_modificator::<RoadPlacer>();
            zone.add_modificator::<RiverPlacer>();
        }

        if zone.is_underground() {  // V3 TMP-D9 — V1+30d no underground
            zone.add_modificator::<RockPlacer>();
        }
    }
}
```

Some modificators are **global** (one instance per tilemap, not per zone): `ObjectDistributor`, `PrisonHeroPlacer`, `RockFiller`. Pattern: `has_X` flag in registration loop.

---

## §3 Modificator catalog V1+30d

7 modificators that ship V1+30d. Each has a dedicated subsection.

### 3.1 TerrainPainter

**Purpose:** Set each tile's `terrain_kind` based on zone's selected terrain type.

**Algorithm:**
```
1. Determine zone's terrain_kind:
   - IF zone.zone_role == Sea: random from allowed water terrains
   - ELIF zone.spec.match_terrain_to_town && zone.town_type != Neutral:
       use faction-native terrain (lookup table by FactionId)
   - ELSE:
       random from zone.spec.terrain_types (or all surface terrains if empty)
2. Validate against level constraint:
   - IF zone.is_underground && !terrain.is_underground: fall back to Subterranean
   - IF zone.is_surface && !terrain.is_surface: fall back to Dirt
3. Apply to all tiles in zone.assigned_tiles:
   - Set tilemap_view.terrain_layer[y*width+x] = terrain_kind
4. Apply decoration percentage: 15% of tiles get "decoration variant"
   (e.g., grass with daisies, sand with rock; cosmetic-only; doesn't affect TileState)
```

**Dependencies:**
- `DEPENDENCY(TownPlacer)` — town's faction determines native terrain (V2 active; V1+30d TownPlacer is no-op)
- `DEPENDENCY_ALL(WaterAdopter)` — water tile reassignments must complete first
- `POSTFUNCTION_ALL(WaterProxy)` — water routes use terrain
- `POSTFUNCTION_ALL(ConnectionsPlacer)` — connections check terrain for `prohibitTransitions` (e.g., direct passage forbidden between Snow ↔ Lava)
- `POSTFUNCTION(ObjectManager)` — objects need terrain-aware placement

### 3.2 ObstaclePlacer

**Purpose:** Fill `Obstacle` tiles with obstacle objects (mountains, trees, rocks). Uses biome obstacle-set selection.

**Detailed algorithm:** see [TMP_005](TMP_005_biome_and_obstacles.md).

**Dependencies:**
- `DEPENDENCY(ObjectManager)` — placed objects must be known (so we don't overlap)
- `DEPENDENCY(TreasurePlacer)` — treasure piles must be known
- `DEPENDENCY(RoadPlacer)` — roads must be known (no obstacles on roads)
- (Underground only) `DEPENDENCY_ALL(RockFiller)` — V3 reserved
- (Surface only) `DEPENDENCY(WaterRoutes)` + `DEPENDENCY(WaterProxy)` — V2

### 3.3 ConnectionsPlacer

**Purpose:** Realize zone-graph edges as actual tile-level passages (guards + roads OR water routes OR teleport portals).

**Detailed algorithm:** see [TMP_007](TMP_007_connections_and_guards.md).

**Algorithm summary:**
```
3-pass with cross-zone locking on shared state:

Pass 1: Portal-kind passages — always place monolith pair
Pass 2: Direct passages (zones share border):
  - Find border tiles adjacent to neighbor zone
  - Pick passage point (away from other zones; not too close to existing objects)
  - Place monster guard (strength from connection.guard_strength)
  - Connect with road (calls RoadPlacer.addRoadNode on both zones)
Pass 3: Indirect passages (zones don't share border):
  - Attempt water route (if Sea zone exists between them)
  - Fall back to monolith portal pair (zones get a teleport entry/exit)
```

**Dependencies:**
- `DEPENDENCY(WaterAdopter)` — water tile reassignment
- `DEPENDENCY(TownPlacer)` — towns occupy area; connections shouldn't be near towns
- `POSTFUNCTION(RoadPlacer)` — roads consume connection-defined waypoints
- `POSTFUNCTION(ObjectManager)` — objects placed AFTER connections (so guards exist)

### 3.4 RoadPlacer

**Purpose:** Draw road tile lines connecting all road-anchor positions (zone centers + connection guards + town entrances).

**Algorithm:**
```
1. Collect road nodes:
   - Zone center (always)
   - Guard tile from each Threshold-kind passage
   - Town entrance (if town present)
   - Mine entrance (if mine present)
2. Build minimum spanning tree (Prim 1957 or Kruskal 1956) over nodes:
   - Edge weight: Manhattan distance (favors road over flat tiles, avoids mountains)
3. For each MST edge:
   - Run A* search from src node to dst node (Hart, Nilsson & Raphael 1968):
     - Heuristic: Manhattan distance
     - Cost: tile-traversal cost (Walkable=1, Open=2, Obstacle=∞, Mountain=∞ for highway, etc.)
   - Smooth path (remove 3-point detours)
   - Add tiles to road_segments[i].waypoints
4. Apply road kind:
   - Default RoadKind::Highway for main MST edges (zone-zone backbone)
   - RoadKind::DirtPath for secondary (town→mine, etc.)
5. Set TileState to Occupied for road tiles (roads don't block but can't host objects)
```

**Dependencies:**
- `DEPENDENCY(TownPlacer)` — town entrance position
- `DEPENDENCY(ConnectionsPlacer)` — guard positions
- (No POSTFUNCTION; roads finalize before obstacles + treasures)

### 3.5 RiverPlacer

**Purpose:** Draw river tile lines from "river source" zones (mountains) to "river sink" zones (lakes/water).

**Algorithm:**
```
1. Identify river sources:
   - Mountain obstacle objects (placed by ObstaclePlacer; objTypeName=="mountain")
   - Author-flagged ZoneSpec with river_source: true
2. Identify river sinks:
   - Lake obstacle objects (objTypeName=="lake")
   - Sea zone borders
3. For each (source, sink) pair within Manhattan range:
   - Run flow algorithm: pick neighbor tile with steepest descent (using terrain elevation
     proxy — Mountain=high, Hill=medium, Plain=low, Water=lowest)
   - Width: 1 tile by default; 2-3 for major rivers (author-flag)
   - Mark river tiles in tilemap_view.river_segments
4. Identify crossable points:
   - Bridge: where road crosses river (auto-detect; insert bridge sprite)
   - Ford: shallow river point (every Nth tile)
```

**Dependencies:**
- `DEPENDENCY(ObstaclePlacer)` — mountains + lakes placed first (river sources + sinks)
- `DEPENDENCY(RoadPlacer)` — for bridge detection (road over river)

### 3.6 ObjectManager

**Purpose:** Generic object placement engine. Handles all `TilemapObject` placement with collision detection + connectivity invariant.

Provides `placeAndConnectObject` API used by TreasurePlacer + TownPlacer + MinePlacer + ConnectionsPlacer (for guards). Doesn't itself place objects — it's a service. But registered as a modificator so dependency tracking works.

**Algorithm:**
```rust
pub fn place_and_connect_object(
    search_area: TileMask,
    object: &TilemapObject,
    min_distance: f32,
    needs_guard: bool,
    is_treasure: bool,
    optimize_type: OptimizeType,  // Distance | BothDistanceAndCenter | Center
) -> Result<Path, PlacementError> {
    // 1. Filter search_area: only tiles where object footprint fits
    // 2. For each candidate tile, score it:
    //    - distance to existing objects (favor far)
    //    - distance to zone center (favor close for Optimize::Center)
    //    - penalty if would seal a gap (connectivity check)
    // 3. Pick best-scoring tile
    // 4. Verify path from zone.free_paths to object.access_point
    // 5. Mark object tiles Occupied; update nearest-object-distance grid
    // 6. Return path (used for road generation, etc.)
}
```

`nearest_object_distance` grid maintained by ObjectManager — priority queue of tiles sorted by distance to closest object. Updated incrementally on each placement. Provides O(1) "farthest from objects" query.

**Dependencies:**
- (No deps; called by other modificators which add their own deps)

### 3.7 TreasurePlacer

**Purpose:** Generate + place treasure piles per zone's treasure-tier spec.

**Detailed algorithm:** see [TMP_006](TMP_006_treasure_and_objects.md).

**Algorithm summary:**
```
1. Build object pool: filter all known TilemapObject types by zone's allowed/banned config
2. Apply inheritance: zones with inherit_treasure_from: 1 copy zone 1's treasure config
3. For each treasure tier (highest value first):
   - target_count = density * zone.assigned_tiles.len() / 1000
   - Generate target_count piles by sampling from object pool weighted by value+rarity
   - For each pile, try placement via ObjectManager.place_and_connect_object:
     - min_distance scales with pile value (high-value piles farther apart)
     - "Never seal a gap" check (Tarjan 1976 connected components)
     - Add guard if needs_guard (value > min_guard_strength)
4. Lower tiers placed with lower min-distance (denser)
```

**Dependencies:**
- `DEPENDENCY(ObjectManager)` — uses ObjectManager service
- `DEPENDENCY(ConnectionsPlacer)` — guards placed first (treasures avoid)
- `DEPENDENCY_ALL(PrisonHeroPlacer)` — V2; for prison-treasure type
- `DEPENDENCY(RoadPlacer)` — roads placed first (treasures off roads)

---

## §4 Execution model

### 4.1 Topological sort + thread pool

Algorithm: Kahn's algorithm (Kahn 1962) for topological sort, augmented with a ready-queue for parallel execution:

```
Build a queue containing all modificators (across all zones).
Each modificator has a `preceeders` list (deps not yet finished).
Each modificator has an `isReady()` check: preceeders empty.

WHILE queue is not empty:
  FOR each modificator in queue:
    IF modificator.isFinished:
      Remove from queue
    ELIF modificator.isReady:
      IF single_thread_mode:
        modificator.run() synchronously
        Remove from queue
        BREAK (restart iteration to honor ordering)
      ELSE:
        Spawn modificator.run() on thread pool
        Remove from queue
    ELSE:
      Continue (still has unfinished preceeders)
END WHILE
Wait for all spawned tasks to complete.
```

Once a modificator runs, it removes itself from all other modificators' `preceeders` lists (via atomic op), enabling them to become ready.

### 4.2 Parallelism + locking

Implementation choice: Rust `tokio` task pool, `rayon::scope`, or similar work-stealing pool. (Specific implementation deferred to impl phase.)

**Locking:**
- Each zone has a `RwLock<ZoneRuntime>` (state: terrain, objects, paths, free_paths, etc.)
- Modificator `process()` acquires write lock on its own zone for the duration
- Cross-zone reads acquire read lock on the other zone (e.g., ConnectionsPlacer reading neighbor's area_open)
- Cross-zone writes (e.g., ConnectionsPlacer placing guard that affects 2 zones) acquire write locks on BOTH zones via **dining-philosopher try_lock pattern** to avoid deadlock — see Dijkstra 1965 ("Cooperating sequential processes").

Pseudocode:
```rust
fn lock_two_zones(z1: &Zone, z2: &Zone) -> (ZoneWriteGuard, ZoneWriteGuard) {
    if z1.id == z2.id { panic!() }
    loop {
        let l1 = z1.try_write();
        let l2 = z2.try_write();
        if l1.is_ok() && l2.is_ok() {
            return (l1.unwrap(), l2.unwrap());
        }
        // both released on drop; spin
        std::thread::yield_now();
    }
}
```

### 4.3 Single-thread mode

`tilemap_defaults.single_thread = true` runs modificators sequentially in deterministic order. Used for:
- **Deterministic-debug builds** (reproducible across machines for bug repros)
- **Property-based tests** (deterministic shrinking)
- **CI environments** with low core counts

Per TDIL-A9 replay-determinism: even in parallel mode, RNG sub-seeds are per-(zone, modificator) so output is deterministic. Single-thread mode is for debugging the parallelism layer itself.

### 4.4 Progress reporting

Emit progress events via DP-Ch24 subscribe channel. UI subscribes to receive:
- `GenerationStarted { reality_id, channel_id, total_modificators: u32 }`
- `GenerationProgress { reality_id, channel_id, modificator_name: String, completed: u32, total: u32 }`
- `GenerationCompleted { reality_id, channel_id, duration_ms: u64 }`

Used by FE progress bar during long generations (continent ~5s; can feel long without feedback).

---

## §5 Error handling

Each modificator can fail with `TilemapError`. Failures map to:
- **Recoverable:** retry with different RNG sub-seed (e.g., obstacle placement failed → try different biome set).
- **Unrecoverable:** emit `tilemap.generation_failed` with detailed cause; UI shows error + suggests Forge:RegenTilemap.

Common failures:
- `EmptyZone` (tiling assignment produced empty zone) → unrecoverable; template misconfigured
- `NoSpaceForObject` (couldn't place treasure tier within max-attempts) → recoverable; reduce density + retry
- `ConnectionRouteFailed` (no path between two zones) → recoverable; try water OR portal fallback
- `Timeout` (modificator exceeded its budget) → unrecoverable; emit `tilemap.generation_timeout`

---

## §6 Resolved questions (closure pass 2026-05-13)

| ID | Question | Locked decision | How resolved |
|---|---|---|---|
| TMP-PIPE-Q1 | Modificator budget config | **V1+30d hardcoded 10s per modificator** (emit `tilemap.generation_timeout` if exceeded); **V2 author-configurable** via `tilemap_defaults.modificator_budgets: HashMap<ModificatorName, Duration>` schema-additive | ✅ ACCEPT default |
| TMP-PIPE-Q2 | Slow-modificator-on-some-templates handling | **Per-modificator timing logged** to `GenerationMetadata.modificator_durations`; ops dashboard flags outliers (>2σ from rolling p95); author Forge can re-roll affected template | ✅ ACCEPT default |
| TMP-PIPE-Q3 | Dry-run mode for template debugging | **V2+ Forge:ValidateTemplate** action runs deps + reports rule_id violations without writes (schema-reserved V1+30d via TMP-D15); V1+30d: author iterates by Forge:RegenTilemap CosmeticOnly | ✅ ACCEPT (defer V2+) |
| TMP-PIPE-Q4 | Single-thread mode scope | **Per-reality V1+30d** via `tilemap_defaults.single_thread: bool`; **process-wide for CI** via `TILEMAP_SINGLE_THREAD=1` env var (CI engineers can force determinism without touching reality config) | ✅ ACCEPT default |

---

## §7 Prior Art

### Academic foundations (architecture sources)

- **Gamma, E., Helm, R., Johnson, R. & Vlissides, J. (1994).** *Design Patterns: Elements of Reusable Object-Oriented Software.* Addison-Wesley. — §2 Strategy + Visitor patterns.
- **Kahn, A. B. (1962).** "Topological sorting of large networks." *Communications of the ACM* 5(11), 558–562. — §4.1 dependency-DAG topological ordering.
- **Dijkstra, E. W. (1965).** "Cooperating sequential processes." Technical Report EWD-123. Eindhoven University of Technology. — §4.2 dining-philosophers pattern for cross-zone locking.
- **Prim, R. C. (1957).** "Shortest connection networks and some generalizations." *Bell System Technical Journal* 36(6), 1389–1401. — §3.4 minimum spanning tree for road network.
- **Kruskal, J. B. (1956).** "On the shortest spanning subtree of a graph and the traveling salesman problem." *Proceedings of the AMS* 7(1), 48–50. — alternative MST algorithm.
- **Hart, P. E., Nilsson, N. J. & Raphael, B. (1968).** "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Trans. on Systems Science and Cybernetics* 4(2), 100–107. — §3.4 A* search for path generation.

### Genre prior art (procedural pipelines in similar games)

- **Heroes of Might and Magic III** (1999). New World Computing. Original genre prior art — multi-pass procedural map generation with zone graphs.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented modificator system under `lib/rmg/modificators/`. Cited as one well-documented open-source implementation of the genre pattern.
- **Dwarf Fortress** (2002+). Bay 12 Games. 4-pass world generation (terrain → erosion → biomes → civilizations + history). Demonstrates multi-pass pipeline at scale.
- **Civilization V / VI** (Firaxis Games). Map generation pipeline with climate bands + resource placement passes.
- **Caves of Qud** (Freehold Games). Pipeline with procedural biome composition + hand-authored set-piece interleaving.

### Concurrent-programming + scheduling pedagogy

- **Lea, D. (2000).** *Concurrent Programming in Java* (2nd ed.). Addison-Wesley. — Reader-writer locking patterns underlying §4.2.
- **Herlihy, M. & Shavit, N. (2008).** *The Art of Multiprocessor Programming.* Morgan Kaufmann. — Modern locking + lock-free patterns.
