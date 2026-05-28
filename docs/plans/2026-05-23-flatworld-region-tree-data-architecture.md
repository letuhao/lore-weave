# Flat-World Region Tree — DATA ARCHITECTURE (design)

> **Status:** ✅ **ACCEPTED — top-down baseline LOCKED (PO, 2026-05-23).** The
> top-down data model in §1–§8 is the agreed schema. The §9 open items
> (which terrain generator per leaf, the seam blend algorithm, persistence, and
> the orogenic-belt-region question) are **deferred — to be resolved bottom-up**
> when per-zone terrain generation is actually built (PO: *"chưa vội … chơi
> bottom-up"*). No code yet; this locks the design, not the implementation.
>
> **🆕 Shipped surface (2026-05-24) → see §11.** Levels 0–2 of the tree
> (plates / zones / sub-zones) plus climate + 10-biome classification are now
> implemented in [`crates/world-gen/src/flatworld.rs`](../../crates/world-gen/src/flatworld.rs),
> [`zonegen.rs`](../../crates/world-gen/src/zonegen.rs), and
> [`flat_climate.rs`](../../crates/world-gen/src/flat_climate.rs).
> §11 documents the **consumer contract** that downstream consumers — including
> the tilemap track ([`features/00_tilemap/`](../03_planning/LLM_MMO_RPG/features/00_tilemap/_index.md))
> — can build against today: JSON export schema, Rust API, render outputs, and
> the seed-based reproducibility recipe. §1–§10 below remain unchanged.
>
> Designs the **data structures** for the recursive plate→zone→sub-zone
> hierarchy, grounded in the current
> [`flatworld.rs`](../../crates/world-gen/src/flatworld.rs) (Level 0 plates +
> Level 1 zones already built). Scope is the **data model** — the schema that
> future per-zone terrain generation will read/write — not generation
> algorithms or rendering.
>
> **Drivers (PO, 2026-05-23):**
> 1. Zones subdivide into **N smaller levels**, *file-and-folder* style.
> 2. The schema must serve **per-zone terrain generation later** — reusing the
>    current sphere logic, the optimized 1024² PNG logic, or new code.
> 3. It must carry enough data to handle **inter-zone boundary interference**
>    (the seam between zones must be stitchable / blendable).

---

## 1 — The shape of the data: one recursive node

Everything is one node type, `Region`, nested like folders. A plate is a
depth-0 region; its zones are depth-1 regions; their sub-zones depth-2; and so
on for `N` levels. A region with no children is a **leaf** (a "file") — the
unit that eventually gets a terrain tile.

```
World (root)
├─ Plate 0            depth 0   (tectonic block: crust kind + drift velocity)
│  ├─ Zone 0          depth 1   (Voronoi cell of the plate)
│  │  ├─ SubZone 0    depth 2
│  │  │  └─ …         depth 3…N
│  │  └─ SubZone 1
│  └─ Zone 1
├─ Plate 1
│  └─ …
└─ (void = area covered by no plate)
```

The same subdivision primitive (scatter Voronoi sites → partition the parent
polygon) is applied at every level; only the *parameters* (count, size) change
per level. This is exactly the Level-1 zone code generalized to recurse.

---

## 2 — Addressing: a path, like a file path

A region is identified by the child-index at each level from the root:

```rust
/// Path from the world root. `[]` = world; `[3]` = plate 3;
/// `[3,2]` = zone 2 of plate 3; `[3,2,5]` = sub-zone 5 of that zone.
#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct RegionPath(pub Vec<u32>);
```

- **Human/debuggable:** print as `/3/2/5` (the folder path).
- **Deterministic seed per node:** derive each region's RNG from the master
  seed + its path bytes, reusing the existing
  [`rng::sub_seed`](../../crates/world-gen/src/rng.rs):
  `Rng::for_stage(master, path.as_bytes())`. Consequence: any node can be
  generated **independently and reproducibly**, without materializing its
  siblings or even its parent's other branches — the precondition for lazy
  expansion (§7) and huge-scale worlds.

---

## 3 — The `Region` node (the core schema)

```rust
pub type Point = (f32, f32);
pub type Polygon = Vec<Point>;

pub struct Region {
    // ── identity & tree position ─────────────────────────────
    pub path: RegionPath,
    pub depth: u8,                 // 0 = plate, 1 = zone, 2 = sub-zone, …

    // ── geometry (WORLD coordinates; see §6 on frames) ───────
    pub boundary: Polygon,         // this region's extent (clipped to parent)
    pub centroid: Point,

    // ── subdivision (how children are defined) ───────────────
    pub sites: Vec<Point>,         // Voronoi sites → one child per site
    pub children: Vec<Region>,     // expanded children; empty = leaf or unexpanded
    pub subdividable: bool,        // false ⇒ a terminal leaf (terrain unit)

    // ── attributes (filled top-down; see §4) ─────────────────
    pub tectonics: Tectonics,      // crust, drift, collision — macro at plate level
    pub elevation: ElevationProfile,

    // ── relations (for boundary interference; see §5) ────────
    pub adjacency: Vec<Adjacency>,

    // ── terrain payload (only on leaves you actually build) ──
    pub terrain: Option<TerrainTile>,  // §6
}
```

`children` empty + `subdividable == true` ⇒ "folder not yet opened" (lazy).
`subdividable == false` ⇒ a leaf that terrain gen will fill.

---

## 4 — Attributes: top-down refinement (inheritance)

Each level **adds detail to what it inherits**, so data flows down the tree
like a cascade. The plate sets the macro; zones refine it; sub-zones refine
further.

```rust
pub enum CrustKind { Continental, Oceanic }

/// Set authoritatively at the plate level (depth 0); deeper regions inherit a
/// copy/reference and may locally bias it.
pub struct Tectonics {
    pub crust: CrustKind,
    pub velocity: Point,           // drift (current Plate.velocity)
    pub collision_uplift: f32,     // uplift inherited from plate overlaps at
                                   // this region's footprint (current
                                   // elevation_at minus base)
}

/// The elevation contract a region hands to its children: the floor they build
/// on, plus how much amplitude they're allowed to add (a detail/LOD budget).
pub struct ElevationProfile {
    pub base: f32,                 // inherited base + this level's offset
    pub relief_budget: f32,        // max amplitude children may add
    pub terrain_class: TerrainClass, // plains / hills / mountain / shelf / abyss…
}
```

- **Plate (depth 0):** `crust`, `velocity`, `base = BASE_LEVEL`, collision
  uplift from plate–plate convergence (today's `collision_strength`).
- **Zone (depth 1):** inherits the plate base + the local uplift sampled at the
  zone; picks a `terrain_class`; sets a smaller `relief_budget`.
- **Sub-zone (depth ≥2):** narrows class + budget further (e.g. a "mountain"
  zone splits into ridge / valley / foothill sub-zones).

Storing `base` as *inherited-plus-offset* (not absolute) means a parent edit
re-flows to all descendants — important for "intervene at any level later".

---

## 5 — Adjacency & seams (the boundary-interference data)

This is the part the PO flagged: terrain in one zone must **agree with its
neighbour at the shared edge**. The tree carries explicit neighbour records so
a generator never has to rediscover topology.

```rust
pub struct Adjacency {
    pub other: RegionPath,         // the neighbour (sibling OR cross-plate)
    pub seam: Vec<Point>,          // shared boundary polyline (in world coords)
    pub kind: SeamKind,
    pub strength: f32,             // tectonic intensity at the seam (0 = quiet)
}

pub enum SeamKind {
    Interior,     // two zones inside the SAME plate — gentle, no tectonics
    Convergent,   // plate boundary, plates closing — mountains / arc
    Divergent,    // plate boundary, plates parting — rift / ridge / new ocean
    Transform,    // plates sliding — fault line
    Coast,        // region edge meets the void — passive margin / shoreline
}
```

Two adjacency classes, both stored the same way:
- **Sibling seams** (same parent): the Voronoi edge between two child cells —
  trivially derived when the parent subdivides. `kind = Interior`.
- **Cross-parent seams** (plate boundaries): where two plates' footprints meet
  (today's overlap band / contact). `kind` from the plates' relative drift
  (reuse `collision_strength` sign → Convergent/Divergent/Transform); `strength`
  from its magnitude. This is where the collision mountains live.

**How terrain gen uses it (the data contract, not the algorithm):** a leaf
exposes its `adjacency`; the generator can (a) read the neighbour's boundary
height samples to **blend** across the seam, and/or (b) derive a **shared seam
seed** from the *unordered* pair `{path_a, path_b}` so both sides synthesize the
*same* boundary feature (a ridge crest, a river crossing) independently yet
identically. The `seam` polyline + `kind` + `strength` are exactly the inputs
both strategies need.

---

## 6 — Terrain payload & coordinate frames (the generation seam)

A leaf region is where terrain actually gets built. The schema holds a
**`TerrainTile`** — a passive data container any generator fills, so the
generator is swappable (current sphere logic / optimized 1024² PNG / new).

```rust
pub struct TerrainTile {
    pub resolution: (u32, u32),    // e.g. 1024×1024 (reuse the optimized path)
    pub world_origin: Point,       // tile pixel (0,0) in world coords
    pub world_per_px: f32,         // scale: world units per tile pixel
    pub skirt_px: u32,             // overlap margin generated beyond the boundary
    pub heights: Vec<f32>,         // row-major; filled by the generator
    pub mask: Vec<bool>,           // inside-region vs skirt/outside
}
```

- **Frames:** `boundary` is world-space; `TerrainTile` adds the world↔tile-pixel
  transform (`world_origin`, `world_per_px`) so a generator works in a clean
  local raster and the result maps back to the world. A `RegionPath` + this
  transform is enough to place any tile globally.
- **Skirt (for seamless stitching):** each tile is generated a few pixels
  *past* its polygon into neighbours; the overlap is reconciled using the §5
  seam data (blend, or shared-seed match). The skirt is the physical room the
  boundary-interference logic needs — without it you can't crossfade.
- **Generator seam:** define the contract as a trait so implementations vary:
  ```rust
  pub trait TerrainGenerator {
      fn fill(&self, region: &Region, ctx: &SeamContext, tile: &mut TerrainTile);
  }
  pub struct SeamContext<'a> { pub neighbours: &'a [(&'a Adjacency, &'a TerrainTile)] }
  ```
  The data architecture's only job is to **hand the generator everything it
  needs** (region attrs + neighbour seams + tile frame) — which logic runs is
  out of scope here.

---

## 7 — Materialization: virtual tree + on-demand expansion

File/folder semantics = you only "open" the branches you look at. The data
model supports both a fully-materialized tree (small worlds, tests) and a lazy
one (huge worlds):

- **Virtual node** = `(path, boundary, seed)`. Cheap; billions can exist
  notionally without being stored.
- **Expand** = run the subdivision primitive for `levels[depth+1]` with the
  node's path-derived seed → fills `sites` + `children`. Deterministic, so an
  expanded subtree is identical whether built now or later.
- **Cache** = keep expanded `children` / built `TerrainTile`s for visited
  branches; evict the rest. (LRU by `RegionPath`.)

Per-level subdivision parameters generalize today's `FlatParams` to a vector,
one entry per depth — this is what makes "N levels" concrete and tunable:

```rust
pub struct LevelParams {
    pub count: (usize, usize),     // children per region (min,max) — random in range
    pub radius_frac: (f32, f32),   // child radius ÷ child pitch (overlap control)
    pub separation: f32,           // centre spread (overlap ↓)
    pub vertices: (usize, usize),  // polygon vertex count range
    pub edge_jitter: f32,
}

pub struct WorldParams {
    pub width: u32,
    pub height: u32,
    pub master_seed: u64,
    pub collision_gain: f32,
    pub levels: Vec<LevelParams>,  // levels[0]=plates, [1]=zones, [2]=sub-zones, …
}
```

`levels.len()` = the depth of the tree = how many "folder" levels exist.

---

## 8 — Mapping the current code onto this schema

Nothing here throws away [`flatworld.rs`](../../crates/world-gen/src/flatworld.rs);
it *promotes* the existing types:

| Today (`flatworld.rs`) | Becomes |
|---|---|
| `FlatWorld { width, height, plates, collision_gain }` | the **root** `Region` (depth = −1/world) + `WorldParams` |
| `Plate { id, center, vertices, velocity, zone_sites }` | `Region` at **depth 0**: `center→centroid`, `vertices→boundary`, `velocity→tectonics.velocity`, `zone_sites→sites` |
| Voronoi zones (`zone_at`) | `Region`s at **depth 1** (`children`), built by the same site-partition primitive |
| `FlatParams` (single level) | `WorldParams` + `levels: Vec<LevelParams>` |
| `collision_strength(a,b)` | computes `Adjacency.kind` + `.strength` for **cross-plate seams** |
| `elevation_at` / `BASE_LEVEL` | `ElevationProfile.base` + `tectonics.collision_uplift` |
| `render_zones_rgb` / `render_height_rgb` | unchanged kind of consumers; now walk the tree to a chosen depth |

Migration is additive: introduce `Region` + `RegionPath`, make `generate`
emit a depth-0/1 tree, keep the renderers reading it. Deeper levels and
`TerrainTile` come online when per-zone terrain gen starts.

---

## 9 — What this schema deliberately does NOT decide (next steps)

- **Which** terrain generator runs per leaf (sphere reuse vs 1024² PNG reuse vs
  new) — that's the §6 trait's implementation, a later task.
- The exact **blend/stitch algorithm** at seams — §5 gives it the data; the
  math is a later task.
- **Persistence** (serialize the tree / tiles to disk for a real world) — the
  `RegionPath` addressing is designed to make this a content-addressed store
  later, but it's out of scope now.
- Promotion of **collision overlap bands** into their own shared "orogenic
  belt" regions vs. handling them purely as cross-plate `Adjacency` — flagged
  as the main open modelling question.

---

## 10 — One-paragraph summary

A single recursive `Region` node, addressed by a file-path-like `RegionPath`,
nests plates → zones → sub-zones to `N` levels using the same Voronoi-partition
primitive at each level with per-level `LevelParams`. Attributes (crust, drift,
elevation base + budget, terrain class) cascade **top-down**; explicit
`Adjacency`/`Seam` records (sibling-interior vs cross-plate convergent/divergent/
transform/coast) carry the **boundary-interference** data; and each leaf holds a
passive `TerrainTile` (raster + world transform + skirt) that any swappable
`TerrainGenerator` fills. Path-derived seeds make every node independently
reproducible, enabling lazy file/folder expansion for large worlds. The current
`flatworld.rs` types map onto this 1:1 — it's a promotion, not a rewrite.

---

## 11 — Shipped consumer contract (post-lock update 2026-05-24)

> **Audience:** downstream consumers (tilemap, knowledge, naming, future
> persistence) who want to **read the world** without participating in its
> generation. Promised below is what the code surface produces **today** —
> stable enough to build a parallel pipeline against, and explicitly tagged
> where the contract is partial.
>
> Scope note (per PO 2026-05-24): consumers like the tilemap track build their
> own per-tile maps from *zone-level* context (climate, biome, plate identity,
> geometry). They do **not** need per-pixel cell binding into the world map —
> the two map types are intentionally different. The contract below is shaped
> accordingly: macro structure + zone attributes + reference renders.

### 11.1 What ships today (Levels 0–2 + climate + biome)

| Layer | Status | Module | Notes |
|---|---|---|---|
| Plate polygons (depth 0) | ✅ shipped | [`flatworld`](../../crates/world-gen/src/flatworld.rs) | Polygon + drift velocity + base elevation |
| Zones (depth 1) | ✅ shipped | [`flatworld`](../../crates/world-gen/src/flatworld.rs) | Voronoi cells inside each plate (sites only; cell polygons derived by nearest-site) |
| Sub-zones (depth 2) | ✅ shipped | [`flatworld`](../../crates/world-gen/src/flatworld.rs) | Nested Voronoi inside each zone |
| Zone climate + biome | ✅ shipped | [`flat_climate`](../../crates/world-gen/src/flat_climate.rs) | 5-layer pipeline: Insolation, Circulation, OceanCurrent v3, Continentality, ZoneRefinement; 10 biomes |
| Per-pixel terrain (relief + erosion) | ✅ shipped | [`zonegen`](../../crates/world-gen/src/zonegen.rs) | 4 terrain classes + ridged fBm + hydraulic erosion + seam blend |
| Per-pixel biome render | ✅ shipped | [`zonegen::render_all_zones_biome`](../../crates/world-gen/src/zonegen.rs) | RGB buffer with snow caps, coastlines, rivers |
| Adjacency / seam records (§5) | ❌ deferred | — | Locked design only; tilemap consumers derive their own neighbour graph if needed |
| Persistence beyond JSON export (§9) | ❌ deferred | — | No `RegionPath`-keyed store yet |
| Levels ≥ 3 (`LevelParams` vec) | ❌ deferred | — | `FlatParams` only carries plate / zone / sub-zone counts; deeper levels = future work |

### 11.2 JSON contract — `WorldData` (the schema tilemap parses from disk)

Produced by [`flatworld::export(&FlatWorld, seed: u64) -> WorldData`](../../crates/world-gen/src/flatworld.rs);
serialized via `serde_json::to_string_pretty`. Field names below are the **wire
names** consumers will see in the JSON file.

```jsonc
{
  "width": 1024,            // u32 — render frame width, world pixels
  "height": 640,            // u32 — render frame height, world pixels
  "seed": 1,                // u64 — master seed; reproducibility key
  "plate_count": 12,        // usize — convenience copy of plates.len()
  "base_level": 0.35,       // f32 — flatworld::BASE_LEVEL constant snapshot
  "void_level": 0.0,        // f32 — flatworld::VOID_LEVEL constant snapshot
  "collision_gain": 0.35,   // f32 — uplift gain at converging plate seams
  "plates": [
    {
      "path": [0],          // [plate_id] — file/folder address
      "center": [x, y],     // [f32; 2] — plate centroid, world px
      "velocity": [vx, vy], // [f32; 2] — plate drift, arbitrary units/tick
      "boundary": [[x, y], ...],  // CCW polygon outline, world px
      "zones": [
        {
          "path": [0, 0],   // [plate_id, zone_id]
          "site": [x, y],   // Voronoi site (also partition key)
          "base_elevation": 0.35,  // f32 — BASE_LEVEL + collision uplift here
          "subzones": [
            {
              "path": [0, 0, 0],  // [plate_id, zone_id, subzone_id]
              "site": [x, y]      // nested Voronoi site
            }
          ]
        }
      ]
    }
  ]
}
```

**Units:** all coordinates are **world pixels** in the same frame as the render
PNGs (top-left origin, `+x` right, `+y` down). Elevations are dimensionless
in `[0, ~1.0]` with `BASE_LEVEL = 0.35` as land floor, `VOID_LEVEL = 0.0` as
ocean/void, `> 0.35` as uplift.

**Partition contract (load-bearing for tilemap):** zone boundaries are
**implicit** — a world pixel `(x, y)` belongs to the plate whose polygon
`contains(x, y)` is true, and within that plate to the zone whose `site` is
nearest (Euclidean). No edge list is shipped. Consumers replicate this with
~10 lines of point-in-polygon + nearest-site lookup; see
[`Plate::contains` and `Plate::zone_at`](../../crates/world-gen/src/flatworld.rs)
for the canonical impl.

**Gap — climate/biome are NOT in this export.** They are computed in-memory
during render but not serialized. If tilemap needs per-zone biome via JSON,
either (a) extend `ZoneData` with `temp_mean: f32`, `precip_annual: f32`,
`biome: u8` (tracked as a future lever — see §11.5), or (b) parse the biome
PNG against `Biome::color()` lookup table (§11.4).

### 11.3 Rust API surface (for in-process consumers)

If the consumer is a Rust crate it can link `world-gen` directly and skip the
JSON hop. Public surface that ships:

**Generation:**

```rust
use world_gen::flatworld::{generate, FlatParams, FlatWorld};
use world_gen::flat_climate::{WorldClimateParams, HemisphereLayout, Biome, ZoneClimate,
    compute_zone_climate, pixel_biome, whittaker_classify};
use world_gen::zonegen::{ClassRatios, render_all_zones_biome};

let params = FlatParams::default();     // 1024×640, 12 plates, seed 1
let world: FlatWorld = generate(&params);
```

**Point queries (live, no JSON):**

| Function | Returns | Use case |
|---|---|---|
| `world.plates_at(x, y)` | `Vec<usize>` — plate IDs covering pixel | Tilemap: which plate(s) own this tile |
| `world.elevation_at(x, y)` | `f32` in `[0, ~1.0]` | Tilemap: per-tile altitude |
| `plate.contains(x, y)` | `bool` | Tilemap: hit-test plate polygon |
| `plate.zone_at(x, y)` | `Option<usize>` | Tilemap: which zone owns this tile |
| `plate.subzone_at(x, y)` | `Option<(usize, usize)>` | Tilemap: depth-2 sub-zone lookup |

**Climate / biome (zone-level, the right grain for tilemap):**

```rust
// edge_dist_sea: BFS distance-to-nearest-sea over the render grid.
// Compute once with the helper inside zonegen.rs (currently private — see §11.5
// gap if you need access). Or pass `vec![0u32; w*h]` to skip continentality.
let cp: WorldClimateParams = WorldClimateParams::default()
    .scaled_for(world.width, world.height, world.plates.len());

let zc: ZoneClimate = compute_zone_climate(&world, &cp, plate_id, zone_id, &edge_dist_sea);
// zc.temp_mean   — °C
// zc.precip_annual — mm/yr
// zc.biome       — Biome enum (10 variants)

let pixel: Biome = pixel_biome(&zc, elev_pixel, zone_base_elev, &cp);
// Applies ElevLapse override: high peaks → Tundra / Ice on top of zone biome
```

**Biome enum** (stable tag bytes per `Biome::tag()`):

**🆕 v5 Köppen 19-biome enum** (2026-05-24, replaces 10-Whittaker pre-v5):

| Tag | Variant | Köppen group | Color (RGB) | Real-world analog |
|---:|---|---|---|---|
| 0 | `Ef` | E (Polar) | `[245, 248, 250]` | Ice cap (Antarctica) |
| 1 | `Et` | E (Polar) | `[184, 183, 174]` | Tundra (Arctic) |
| 2 | `Dfd` | D (Continental) | `[58, 86, 60]` | Extreme subarctic (Yakutsk) |
| 3 | `Dfc` | D (Continental) | `[74, 107, 71]` | Subarctic (Siberia) |
| 4 | `Dfb` | D (Continental) | `[100, 138, 88]` | Warm humid continental (Canada prairies) |
| 5 | `Dfa` | D (Continental) | `[125, 158, 96]` | Hot humid continental (Central US) |
| 6 | `Dwa` | D (Continental) | `[148, 175, 110]` | Continental dry-winter monsoon (NE China) |
| 7 | `Cfb` | C (Temperate) | `[79, 139, 65]` | Oceanic (UK, NW Europe) |
| 8 | `Cfa` | C (Temperate) | `[138, 171, 82]` | Humid subtropical (SE USA, Yangzi) |
| 9 | `Csa` | C (Temperate) | `[181, 165, 98]` | Mediterranean hot summer (Med basin) |
| 10 | `Csb` | C (Temperate) | `[165, 175, 115]` | Mediterranean warm summer (coastal CA) |
| 11 | `Cwa` | C (Temperate) | `[155, 180, 95]` | Subtropical monsoon (S China) |
| 12 | `Bsk` | B (Arid) | `[174, 165, 105]` | Cold steppe (Kazakh) |
| 13 | `Bwk` | B (Arid) | `[195, 165, 132]` | Cold desert (Gobi) |
| 14 | `Bsh` | B (Arid) | `[201, 192, 74]` | Hot steppe (Sahel) |
| 15 | `Bwh` | B (Arid) | `[216, 144, 96]` | Hot desert (Sahara) |
| 16 | `Af` | A (Tropical) | `[15, 77, 26]` | Tropical rainforest (Amazon) |
| 17 | `Am` | A (Tropical) | `[35, 100, 35]` | Tropical monsoon (Mumbai) |
| 18 | `Aw` | A (Tropical) | `[185, 180, 80]` | Tropical savanna (Sahel-tropics) |

`Biome::color()` is the canonical lookup if a consumer parses the rendered
PNG. **v5 tags are NOT compatible with pre-v5 (10-Whittaker) tags** — tag 0
was `Ice` (pre-v5) vs `Ef` (v5); migration required for sidecar consumers
that pinned the pre-v5 tag bytes.

**Constants stable across the contract** (snapshot via `world_gen::flatworld::*`):

- `BASE_LEVEL = 0.35` — land-floor elevation
- `VOID_LEVEL = 0.0` — ocean / between-plate void
- `zonegen::SHORE_LEVEL_OFFSET` — added to `BASE_LEVEL` to derive
  `sea_level` for the continentality BFS (also `WorldClimateParams::sea_level`'s
  default expression)

### 11.4 Render outputs (PNG / consumable images)

Driven by [`examples/flatworld.rs`](../../crates/world-gen/examples/flatworld.rs).
Run:

```bash
cargo run --release -p world-gen --example flatworld -- \
    --width 1024 --height 640 --plates 12 --seed 1 \
    --out flat.png \
    --height-out height.png \
    --zones-out zones.png \
    --all-zones-out terrain.png \
    --eroded-out terrain_eroded.png --erosion moderate \
    --biome-out biome.png \
    --data-out world.json
```

All renders share the **same frame** (`width × height` world pixels, top-left
origin). Tilemap can index any of them by `(x, y)` directly.

| File | Encoding | Content |
|---|---|---|
| `--out` plate hues | RGB8 | Per-plate distinct hue; overlaps blended; void `[10,10,14]` |
| `--height-out` | RGB8 (gray) | Elevation × 255, clamped. Void = black, BASE_LEVEL = mid-grey, peaks = white |
| `--zones-out` | RGB8 | Plate hue stepped by zone (legible per-plate partition) |
| `--all-zones-out` | RGB8 (gray) | Full-map per-pixel terrain (relief synthesized; no erosion) |
| `--eroded-out` | RGB8 (gray) | Same as all-zones with hydraulic erosion (`none` / `light` / `moderate` / `heavy`) |
| **`--biome-out`** | **RGB8** | **B5 v2.1f 10-biome render** (the headline output for visual consumers) — uses `Biome::color()` palette + beach band + river tint + snow caps |
| `--data-out` | JSON | The §11.2 `WorldData` document |
| **`--climate-out`** | **JSON** | **🆕 v4 sidecar (2026-05-24), extended v5** — per-zone climate snapshot: `temp_mean / precip_annual / temp_warm_month / temp_cold_month / precip_winter_frac / biome / koppen_group / lat_dist / site / base_elevation` for every zone + scenario `climate_params`. **v5 (2026-05-24)**: added 4 fields (seasonality + Köppen group letter); `biome` field changed from Whittaker names ("TropicalRainforest") to Köppen codes ("Af"). Pinned by `export_matches_in_memory_compute` test — same `compute_zone_climate` the renderer uses, so JSON matches painted pixels by construction. Lets consumers (eval, tilemap, knowledge service) read per-zone climate without re-implementing physics. |

Recommended for tilemap inheritance: **`--biome-out`** for the visual reference
+ **`--data-out`** for the structural skeleton + **`--climate-out`** when the
tilemap needs to inherit zone-level temperature/precip for its own biome /
weather / encounter table decisions.

### 11.5 Reproducibility recipe

The contract guarantees: **same `(seed, FlatParams, WorldClimateParams,
ClassRatios, ErosionStrength)` → byte-identical output**, on the same binary +
platform. Pinned by:

- `flatworld::is_deterministic_in_seed` test ([`flatworld.rs`](../../crates/world-gen/src/flatworld.rs))
- `zonegen` biome render hash pin (blake3, currently `b37691d0...`)
- All RNG paths derive from the master seed via [`rng::sub_seed`](../../crates/world-gen/src/rng.rs)
  with stable string salts (`"flatworld-plates"`, `"flatworld-motion"`,
  `"flatworld-zones"`, etc. — see [`flatworld::generate`](../../crates/world-gen/src/flatworld.rs))

For tilemap to **regenerate** a world locally from a shared seed, the minimal
recipe is:

1. Pin the `world-gen` crate revision (commit SHA in `Cargo.toml`)
2. Use `FlatParams::default()` + override only the fields you care about
   (`seed`, `plate_count`, `width`/`height`)
3. Use `WorldClimateParams::default().scaled_for(w, h, plate_count)`
4. Call `flatworld::generate(&params)` → `FlatWorld`
5. Optionally export JSON or render the biome PNG

Any drift in default values shifts the output — defaults are part of the
contract. Current defaults (post v2.1f / v3 OceanCurrent):
- `plate_count: 12`, `min_zones..max_zones: 3..7`, `min_subzones..max_subzones: 3..6`
- `t_eq: 28.0`, `t_pole: -15.0`, `precip_subtropic: 180.0`
- `ocean_current_strength: 5.0`, `peak_lapse_min_delta: 0.05`, `ice_precip_min: 100.0`

### 11.6 Known gaps + future levers for the contract

Items downstream consumers may want — explicitly NOT shipped yet:

| Gap | Workaround today | Future lever |
|---|---|---|
| **Zone climate/biome in JSON** | Use Rust API (`compute_zone_climate`) or parse biome PNG | Extend `ZoneData` with `temp_mean / precip_annual / biome_tag` (additive, schema-compatible) |
| **`edge_dist_sea` not exported as a helper** | Tilemap recomputes BFS from `world.elevation_at + sea_level` | Promote `zonegen`'s internal `compute_edge_dist_sea` to `pub`; or export the precomputed `Vec<u32>` as a sidecar |
| **No zone polygon export** (Voronoi cell boundaries) | Derive by nearest-site rasterization, or `concave_hull` over pixels with matching `(plate_id, zone_id)` | Add `ZoneData.boundary: Vec<[f32;2]>` (denormalized; meaningful for tilemap "draw this zone outline" use case) |
| **No seam / adjacency records** (§5 of locked design) | Tilemap must rederive neighbour pairs from polygon adjacency | Implement §5 `Adjacency` + `SeamKind` once tilemap consumer has shipped enough to define what it needs |
| **No `RegionPath` content-addressed store** (§9) | One JSON dump per world | Persistence layer; out of scope until a server-side use case demands it |
| **Levels ≥ 3** | Only depth-2 supported (sub-zones) | `FlatParams` already has the slot; needs `LevelParams` vec generalization |

When the tilemap team or any consumer hits one of these gaps in practice,
that's the signal to promote the corresponding lever. The contract is
**additive** going forward — fields will be added to `WorldData` / `ZoneData`
but not removed or retyped without a version bump alongside it.

### 11.7 Quick-start for tilemap (or any consumer)

```bash
# 1. Generate a reference world + biome render + JSON skeleton
cargo run --release -p world-gen --example flatworld -- \
    --seed 1 --biome-out biome.png --data-out world.json --height-out height.png

# 2. Parse world.json: get plates[*].zones[*] with paths + sites + base_elevation
# 3. For visual reference, sample biome.png at (x, y) → match Biome::color() table
# 4. For your own per-tile biome decisions, link world-gen crate and call
#    compute_zone_climate(&world, &params, plate_id, zone_id, &edge_dist_sea)
```

That's the minimum surface to inherit "world shape + biome distribution" into
a parallel tilemap pipeline without coupling to the per-pixel render.
