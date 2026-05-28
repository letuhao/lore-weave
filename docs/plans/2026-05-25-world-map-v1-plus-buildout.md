# World Map V1+ — Full Buildout Spec (11 phases G–Q)

> **Status:** DRAFT 2026-05-25 — design only, pre-implementation.
> Companion to [`2026-05-25-world-map-v1-buildout.md`](2026-05-25-world-map-v1-buildout.md)
> (V1 buildout: Phases A–F, ~25h, 6-7 sessions).
>
> **PO 2026-05-25 directive:** "tôi muốn ship hết luôn chứ không out of
> scope" — ship everything, no deferrals. This doc covers all V1+ phases
> (architecture, data depth, integration, operations) that the V1 spec
> doc explicitly deferred.
>
> **Total V1+V1+ buildout: ~125–155 hours, ~30–40 sessions of focused
> work.** This is the full roadmap to "world map system production
> complete at every layer".

---

## 1 — Context

V1 spec doc covers **flatworld rendering + data depth completion** in 6
phases (~25h). V1+ covers everything else needed for "world map system
done at every layer":

- **Architectural cleanup** (Region<N> refactor, adjacency records)
- **Multi-tier hierarchy + integration** (channels, sphere↔flatworld,
  tilemap adapter, graph adapter)
- **Data extensions** (wetlands, volcanoes, named ranges)
- **Operations** (lazy materialization, persistence)
- **Climate refinements** (v6 Holdridge, full Köppen 30-class, slope
  hillshade)
- **Time dynamics** (erosion + drift + climate-shift over time)

Without V1+, flatworld V1 is a **standalone rendering pipeline**; with
V1+ it becomes a **fully integrated world map system** consumed by
tilemap, MAP graph, settlements, routes, political, culture, knowledge
service, TVL, etc.

---

## 2 — Phases G–Q overview (Phase M deferred to V2 per PO)

| Phase | Name | Effort | Stage | Prereqs |
|---|---|---:|---|---|
| **G** | Multi-continent + N-tier channel hierarchy | 10–15h | Stage 3 (integration) | H decision |
| **H** | WorldGeometry trait abstraction (H-3 chosen) | 8–12h | Stage 3 | — |
| **I** | Adjacency records as data layer | 4–6h | Stage 2 (cleanup) | — |
| **J** | Wetlands + volcanoes + named ranges | 6–10h | Stage 4 (data polish) | Phase F (rivers) |
| **K** | TMP_001 tilemap adapter | 10–15h | Stage 3 | G + L |
| **L** | MAP_001 graph adapter | 5–8h | Stage 3 | G (channel tiers) |
| **N** | Lazy materialization | 8–10h | Stage 5 (operations) | Q (Region<N>) |
| **O** | Persistence (content-addressed RegionPath store) | 8–10h | Stage 5 | N |
| **P** | Climate v6 / advanced (Holdridge, true 30-class Köppen, slope hillshade) | 15–25h | Stage 4 | — |
| **Q** | Recursive Region<N> type refactor | 12–15h | Stage 2 (cleanup) | — |
| **Total V1+** |  | **~86–126h** | | |
| **+ V1 base** |  | **+25h** |  |  |
| **Grand total** |  | **~110–150h** | **5 stages, ~28–37 sessions** | |

**Phase M (time dynamics)** deferred to V2 — see separate roadmap when
time-evolution becomes a game requirement. Not in this V1+ buildout.

---

## 3 — Stage grouping (recommended execution order)

### Stage 1 — V1 base (Phases A–F)
**Output**: "Flatworld looks production-quality" (no longer toy-like).
- 25h, 6–7 sessions
- See V1 spec doc for details

### Stage 2 — Architectural cleanup (Phases Q, I)
**Output**: "Type system unified + adjacency data layer".
- ~16–21h, 4–5 sessions
- Foundation work; pays dividends across all later stages

### Stage 3 — Multi-tier + integration (Phases H, G, L, K)
**Output**: "Sphere/flatworld integrated, multi-continent, tilemap + graph adapters wired".
- ~33–52h, 8–13 sessions
- The "world map is now consumable by all downstream features" milestone

### Stage 4 — Data + climate polish (Phases J, P)
**Output**: "Wetlands, volcanoes, named ranges, climate v6".
- ~21–35h, 5–9 sessions
- Production-grade content depth

### Stage 5 — Operations (Phases N, O)
**Output**: "Lazy materialization + persistence for production scale".
- ~16–20h, 4–5 sessions
- Required for Megaplanet / Gigaplanet world scales

### Stage 6 — DEFERRED to V2

Phase M (time dynamics) deferred per PO decision 2026-05-25. Separate
V2 roadmap will cover time evolution when game gameplay requires it.
Not in this V1+ buildout.

---

## 4 — Phase G: Multi-continent + N-tier channel hierarchy (L+, ~10–15h)

**Goal**: support multiple continents per planet + map flatworld zones to
game tier channels (continent/country/district/town/cell).

### G.1 — Channel tier definition

Per MAP_001 spec:
```rust
pub enum ChannelTier {
    Planet,      // root: the world itself
    Continent,   // major landmass; ~1 per FlatWorld in current flat pipeline
    Country,     // political subdivision; defined by political layer (Phase A2 sphere)
    District,    // sub-country; mid-resolution gameplay tier
    Town,        // city-scale; defined by settlement layer
    Cell,        // unit gameplay scale; CSC_001 interior
}
```

### G.2 — Channel ID assignment per flatworld zone

Add to ZoneClimateExport:
```rust
pub struct ChannelBinding {
    pub continent_id: ChannelId,
    pub country_id: Option<ChannelId>,    // requires political layer
    pub district_id: Option<ChannelId>,
    pub town_id: Option<ChannelId>,
    pub cell_id: Option<ChannelId>,
}
```

Mapping rules:
- 1 FlatWorld = 1 Continent channel (V1 baseline; G.4 extends to multi-continent)
- Country = subgraph of political layer (when sphere political layer integrated)
- District = subgraph of country (mid-tier)
- Town = settlement location
- Cell = 16×16 patch within town/district (CSC_001 interior)

### G.3 — Multi-continent per planet

Currently `FlatWorld` is 1 rect = 1 world. Change:
```rust
pub struct Planet {
    pub continents: Vec<FlatWorld>,
    pub layout: PlanetLayout,        // how continents arrange in world space
    pub master_seed: u64,
    pub global_params: GlobalParams,  // shared climate scaling, sea level, etc.
}

pub enum PlanetLayout {
    Grid { rows: usize, cols: usize },  // simple grid of continents
    Sphere(SphereProjection),           // continents distributed on sphere via Phase H
    Custom(Vec<ContinentPlacement>),    // hand-placed
}
```

### G.4 — Cross-continent climate interactions

Multi-continent worlds need cross-boundary climate:
- Trade winds carry moisture from ocean to next continent
- Cold/warm currents flow between continents
- Plate tectonics may straddle continents (e.g. Asia-Pacific Ring of Fire)

V1+ Phase G ships with **independent continents** (each FlatWorld
self-contained); cross-continent climate is V1++ enhancement.

### G.5 — Sidecar export per channel

Export becomes nested:
```json
{
  "planet": { "seed": ..., "layout": ... },
  "continents": [
    {
      "channel_id": "...",
      "tier": "Continent",
      "flatworld_data": { ... },  // existing flatworld export
      "country_partition": [ { "channel_id": "...", "cells": [...] }, ... ]
    }
  ]
}
```

### G.6 — Tests

- Multi-continent generation determinism
- Channel ID assignment correctness
- Per-tier partition coverage (no overlap, no gap)

**Files**: NEW `planet.rs`, MAJOR refactor `flatworld.rs` to be
embeddable in Planet. Hash pin rebase for any test depending on
single-flatworld output.

---

## 5 — Phase H: Sphere ↔ flatworld integration decision (M, ~4–6h decide + 4–8h adapter)

**Goal**: resolve "which pipeline is canonical" question that's blocked
V1 since session 58.

### H.1 — 4 options

#### Option H-1: Sphere is canonical, flatworld becomes per-continent zoom

Sphere governs:
- Multi-continent layout
- Global ocean currents + wind patterns
- Plate tectonics at planet scale
- Settlements/routes/political/culture (already shipped on sphere)

Flatworld governs:
- Per-continent zoom: each continent on sphere expanded into 1024×640
  rectangle via stereographic projection
- Zone subdivision + climate + biome render
- Per-pixel terrain detail (relief, erosion, hydrology)

Adapter: `flatworld_from_continent(sphere_world, continent_id) -> FlatWorld`.

**Pros**:
- Sphere already shipped (no duplicate work)
- Multi-continent automatic
- Existing sphere consumers (settlements/routes/political/culture) keep working

**Cons**:
- Flatworld becomes "rendering layer", loses standalone status
- Existing flatworld defaults (12 plates etc.) need translation to per-continent semantics

#### Option H-2: Flatworld is canonical, sphere becomes wrapper

Flatworld governs everything; sphere only used when user wants "planet
view" rendering.

**Pros**:
- Flatworld already mature (v5.0 shipped)
- Sphere becomes optional cosmetic

**Cons**:
- Sphere's settlements/routes/political/culture would need re-impl on
  flatworld (massive duplicate work)
- Multi-continent requires re-architecting flatworld

#### Option H-3: Both coexist with shared trait abstraction

Define `WorldGeometry` trait:
```rust
pub trait WorldGeometry {
    fn cell_count(&self) -> usize;
    fn neighbors(&self, cell: CellId) -> Vec<CellId>;
    fn elevation(&self, cell: CellId) -> f32;
    fn biome(&self, cell: CellId) -> Biome;
    fn climate(&self, cell: CellId) -> ZoneClimate;
    // ...
}
```

Sphere + Flatworld both implement; consumers work against trait.

**Pros**:
- No migration required for either; both keep current code
- Consumers (settlements/routes/etc.) refactored ONCE to use trait

**Cons**:
- Trait design is hard (sphere has 3D cells, flatworld has 2D pixels —
  different cell semantics)
- Two parallel impls of every feature add (e.g. lakes need flatworld
  pit-fill + sphere pit-fill)

#### Option H-4: Use case split (user picks at world creation)

User declares world type:
```rust
pub enum WorldType {
    Planet { spherical: true },   // uses sphere pipeline
    Region { spherical: false },  // uses flatworld pipeline
}
```

Each world type has its own consumer subset (sphere worlds get full
political; flat worlds get rich rendering).

**Pros**:
- Clear separation; no integration cost
- Each pipeline optimized for its use case

**Cons**:
- Feature parity problem: features developed on one pipeline don't
  automatically apply to other
- User must choose upfront; not easily switchable

### H.2 — DECISION LOCKED (PO 2026-05-25): Option H-3 — Trait abstraction

**WorldGeometry trait; sphere + flatworld both implement; consumers
refactor once to use trait, not concrete type.**

Rationale: maintains both pipelines' shipped capabilities without
migration burden on either. Sphere keeps settlements/routes/political/
culture; flatworld keeps zone/biome/render. Consumers (downstream
features) write once against trait.

### H.3 — WorldGeometry trait design

Core challenge: sphere has 3D cells with arbitrary-shape Voronoi
polygons; flatworld has 2D pixels with rectangular grid. Trait must
abstract over both.

```rust
/// Abstract world geometry consumed by downstream features. Both
/// SphereWorld and FlatWorld implement.
pub trait WorldGeometry {
    /// Opaque cell identifier (u32 for sphere cells, packed (x, y) for
    /// flatworld pixels).
    type CellId: Copy + Eq + Hash;

    /// 2D world coordinates for a cell. For sphere: stereographic
    /// projection. For flatworld: direct pixel coords.
    fn cell_center_2d(&self, cell: Self::CellId) -> (f32, f32);

    /// 3D world coordinates (only meaningful for sphere; flatworld
    /// returns (x, y, 0)).
    fn cell_center_3d(&self, cell: Self::CellId) -> (f32, f32, f32);

    /// Cell neighbors (4-connected for flatworld; Delaunay neighbors
    /// for sphere).
    fn neighbors(&self, cell: Self::CellId) -> Vec<Self::CellId>;

    /// Total cell count.
    fn cell_count(&self) -> usize;

    /// Iterator over all cells.
    fn cells(&self) -> Box<dyn Iterator<Item = Self::CellId> + '_>;

    /// Latitude in [0, 1] where 0 = equator, 1 = pole.
    fn lat_dist(&self, cell: Self::CellId) -> f32;

    /// Elevation (post-erosion).
    fn elevation(&self, cell: Self::CellId) -> f32;

    /// Sea level (uniform; both pipelines define one).
    fn sea_level(&self) -> f32;

    /// Is this cell on land?
    fn is_land(&self, cell: Self::CellId) -> bool;

    /// Is this cell on a coastline (adjacent to water)?
    fn is_coast(&self, cell: Self::CellId) -> bool;

    /// Köppen biome (post-pixel-lapse if applicable).
    fn biome(&self, cell: Self::CellId) -> Biome;

    /// Full per-cell climate (temp_mean, precip_annual, monthly extremes).
    fn climate(&self, cell: Self::CellId) -> ZoneClimate;

    /// Channel ID this cell belongs to (after Phase G channel binding).
    fn channel(&self, cell: Self::CellId, tier: ChannelTier) -> Option<ChannelId>;
}

/// Capability extensions for features only one pipeline supports.
/// Consumers check `if let Some(political) = world.political() { ... }`.
pub trait WorldGeometryExt: WorldGeometry {
    fn political(&self) -> Option<&PoliticalLayer> { None }
    fn settlements(&self) -> Option<&SettlementLayer> { None }
    fn routes(&self) -> Option<&RouteLayer> { None }
    fn culture(&self) -> Option<&CultureLayer> { None }
    fn rivers(&self) -> Option<&RiverGraph> { None }       // V1 Phase F
    fn lakes(&self) -> Option<&[Lake]> { None }            // V1 Phase F
    fn features(&self) -> Option<&[Feature]> { None }      // V1 Phase D
    fn mountain_ranges(&self) -> Option<&[MountainRange]> { None } // Phase J
    fn volcanoes(&self) -> Option<&[Volcano]> { None }     // Phase J
    fn wetlands(&self) -> Option<&[Wetland]> { None }      // Phase J
}
```

**Default impls return None** — pipelines opt in to capabilities they
support. Sphere currently provides political/settlements/routes/culture;
flatworld currently provides nothing in WorldGeometryExt but will after
V1 Phases D/E/F (features/landscape/rivers) and V1+ Phase J.

### H.4 — Migration plan (H-3)

1. **Phase H.4a** (~2h): write `WorldGeometry` trait + base `WorldGeometryExt`
2. **Phase H.4b** (~2h): impl trait for `FlatWorld` (existing data → trait methods)
3. **Phase H.4c** (~2h): impl trait for `SphereWorld` (existing `WorldMap` → trait methods)
4. **Phase H.4d** (~3h): refactor first consumer (e.g., `render` module) to use trait. Validates the abstraction.
5. **Phase H.4e** (incremental, future stages): refactor remaining consumers (settlements, routes, knowledge service, tilemap K, MAP graph L) to use trait one-by-one.

After H.4d, both pipelines coexist with shared consumer code. No
migration burden — both keep their shipped state.

### H.5 — Trait design risks

| Risk | Mitigation |
|---|---|
| 3D vs 2D cell semantics leak through abstraction | Method `cell_center_3d` returns `(x, y, 0)` for flat; consumers needing true 3D use sphere-specific extension trait |
| Channel tier (Phase G) semantics differ per pipeline | Phase G defines channels per pipeline; trait method `channel()` returns Option |
| Performance overhead from dynamic dispatch | Generic `<G: WorldGeometry>` instead of `dyn WorldGeometry` — monomorphizes per consumer |
| Feature added to one pipeline but not other | WorldGeometryExt opt-in pattern; consumers check via `if let Some(...)` |
| Trait API drift as features added | Versioned trait suffix (`WorldGeometryV2`) if breaking; mostly additive via WorldGeometryExt |

### H.6 — Trait NOT required for Phase H ship

Phase H ships when:
- WorldGeometry trait defined + tested
- Both FlatWorld + SphereWorld implement
- First consumer (e.g., render) refactored to use trait
- Documentation explains pattern for future consumers

Refactoring ALL consumers happens incrementally over Phases G/J/K/L/P
(each consumer migration is a small inline change, not a separate
phase).

---

## 6 — Phase I: Adjacency records as data (M, ~4–6h)

**Goal**: per data-arch doc §5 — promote ad-hoc adjacency detection to
proper data layer.

### I.1 — Adjacency struct

```rust
pub struct Adjacency {
    pub other: RegionPath,           // neighbor (sibling OR cross-plate OR cross-tier)
    pub seam: Vec<Point>,            // shared boundary polyline (world coords)
    pub kind: SeamKind,
    pub strength: f32,               // tectonic intensity, 0 = quiet
}

pub enum SeamKind {
    SiblingInterior,                 // 2 zones, same parent plate
    CrossPlateConvergent,            // plates closing → mountains
    CrossPlateDivergent,             // plates parting → rift
    CrossPlateTransform,             // sliding → fault
    Coast,                           // land ↔ void
    River,                           // zone ↔ river-passing zone
    PoliticalBorder,                 // 2 countries (V1+ Phase G)
}
```

### I.2 — Per-zone adjacency precompute

In `compute_render_state`, build adjacency list per zone:
```rust
state.zone_adjacency: Vec<Vec<Adjacency>>;
```

Reuses the adjacency detection algorithm from V1 Phase D (which builds
adjacency ad-hoc for feature classification). I promotes it to first-
class data.

### I.3 — Sidecar export

```json
"zones": [
  {
    "plate_id": 0,
    "zone_id": 0,
    "...": "...",
    "adjacencies": [
      { "other": [0, 1], "kind": "SiblingInterior", "seam": [[x,y], ...], "strength": 0 },
      { "other": [3, 2], "kind": "CrossPlateConvergent", "seam": [...], "strength": 0.45 },
      ...
    ]
  }
]
```

### I.4 — Consumer benefit

Tilemap, MAP graph, game logic all need adjacency:
- Tilemap: where to render seam features (Phase D output, refined)
- MAP graph: which zones connect (Connection edges between channel nodes)
- Game: border-crossing detection, military front lines, trade routes

### I.5 — Tests

- Coverage: every zone has full adjacency list
- Symmetry: A.adjacent(B) iff B.adjacent(A)
- Determinism: same world → same adjacency
- Sidecar round-trip preserves adjacencies

---

## 7 — Phase J: Wetlands + volcanoes + named ranges (M-L, ~6–10h)

**Goal**: data depth — D5 + D6 + D8 in one batch.

### J.1 — Wetlands / marshes detection

Detect via:
- Sub-zone has low slope (mean elev gradient < threshold)
- AND high precip (≥ threshold)
- AND not Mountain class
- OR near river with high flux

```rust
pub struct Wetland {
    pub id: WetlandId,
    pub kind: WetlandKind,           // Marsh / Bog / Swamp / Mangrove
    pub area: f32,                    // pixels
    pub centroid: (f32, f32),
    pub shore: Vec<(f32, f32)>,       // polyline boundary
}
```

Render: dark-green with stipple pattern.

### J.2 — Named mountain ranges

Cluster Mountain-class sub-zones via spatial adjacency:
```rust
pub struct MountainRange {
    pub id: MountainRangeId,
    pub name: Option<String>,        // assigned later by naming service
    pub extent: Vec<RegionPath>,      // member sub-zones
    pub peak: (f32, f32),             // highest point
    pub avg_elev: f32,
    pub length_km: f32,
    pub orientation: f32,             // angle in degrees
}
```

Sphere pipeline already has `MountainRange`; port that logic to flatworld.

### J.3 — Volcanoes

Random spawn at convergent plate seams:
```rust
pub struct Volcano {
    pub id: VolcanoId,
    pub position: (f32, f32),
    pub kind: VolcanoKind,           // Active / Dormant / Extinct
    pub elev_bonus: f32,              // adds to local elevation
    pub influence_radius: f32,        // climate effect zone
}
```

Spawn rules:
- Sample N volcanoes per convergent plate boundary
- N depends on collision_strength (more volcanoes at stronger convergence)
- Visual: peak with crater texture
- Climate effect: local cooling from ash (small radius)

### J.4 — Sidecar export

```json
"wetlands": [...],
"mountain_ranges": [...],
"volcanoes": [...]
```

### J.5 — Tests

- Wetland detection on a 1-zone flat-precip-high world
- Mountain range clustering correctly groups adjacent Mountain sub-zones
- Volcano placement deterministic from seed

---

## 8 — Phase K: TMP_001 tilemap adapter (L+, ~10–15h)

**Goal**: per-channel tilemap_view generation consumable by frontend
(Phaser/Pixi rendering).

### K.1 — Per-channel tilemap_view aggregate

Per TMP_001 spec:
```rust
pub struct TileMapView {
    pub channel_id: ChannelId,
    pub tier: ChannelTier,
    pub grid_size: GridSize,         // 256² continent, 192² country, 128² district, 64² town
    pub skeleton_id: TileMapSkeletonId,
    pub procedural_seed: u64,
    pub procedural_params: TileMapProceduralParams,
    pub terrain_layer: Vec<u8>,      // flattened terrain kind grid
    pub roads: Vec<RoadSegment>,
    pub rivers: Vec<RiverSegment>,
    pub child_cell_placements: HashMap<ChannelId, TileCoord>,
    pub object_placements: Vec<MapObjectPlacement>,
    pub layer3_source: Layer3Source,
    pub region_narration: Option<String>,
    pub prompt_template_version: u32,
    pub last_change_fiction_time: FictionTime,
}
```

### K.2 — Generation pipeline

Per TMP_001 §3 4-layer composition:
- **L1**: hand-authored skeleton OR auto-generated from flatworld zones
- **L2**: procedural terrain placer (already in flatworld pipeline)
- **L3**: LLM zone classifier (V2 territory, defer)
- **L4**: LLM regional narration (V2 territory, defer)

V1+ Phase K ships L1+L2 (LLM layers come later).

### K.3 — Flatworld → tilemap adapter

For each channel tier, produce tilemap_view:
- Continent tier: full flatworld output at 256² (downsample 1024×640 → 256²)
- Country tier: flatworld region for country at 192² (project sub-area)
- District tier: similar at 128²
- Town tier: similar at 64²

Adapter handles projection + resampling per tier.

### K.4 — Skeleton library

Per TMP_001 §3, hand-authored skeletons drive procedural generation.
Catalog (V1+ Phase K):
- `continent_default`: standard continent layout
- `country_default`: standard country with capital + districts
- `town_default`: standard town with market + districts
- Future: per-genre variants (wuxia / scifi / steampunk)

### K.5 — Tests

- Continent tilemap_view round-trip (generate, export, import, render)
- Tier transition (click continent → drill into country)
- Determinism: same flatworld + skeleton → same tilemap_view

**Files**: NEW `tilemap.rs` module in world-gen; integration with
existing TMP_001 design docs.

---

## 9 — Phase L: MAP_001 graph adapter (M, ~5–8h)

**Goal**: per MAP_001 spec — derive logical node-link graph from
flatworld zones.

### L.1 — Graph node placement

Each channel tier has nodes:
- Continent: 1 node = the continent itself
- Country: N nodes from political subdivision (Phase A2 sphere)
- District: M nodes per country
- Town: K nodes per district (settlements)
- Cell: per-cell node within town/district

Node position derived from flatworld:
- Country: centroid of country's flatworld region
- Town: settlement location (sphere pipeline already provides)
- Cell: 16×16 patch coord within parent

### L.2 — Connection edges

Per PF_001 spec:
- **Public** connection: open roads (routes layer)
- **Private**: gated/access-controlled
- **Locked**: requires key/event to open
- **Hidden**: discovery required
- **OneWay**: directional only

Auto-derive from flatworld:
- Public if route exists between settlements (routes layer)
- Hidden if connection passes through impassable terrain (e.g., mountain pass)

### L.3 — Position abstraction

MAP_001 spec uses positions 0..1000 (abstract). Flatworld zones are at
world pixel coords. Adapter normalizes:
```rust
let abstract_pos = (zone_site.x / world.width * 1000, zone_site.y / world.height * 1000);
```

### L.4 — Sidecar export

```json
"map_graph": {
  "tiers": {
    "continent": [ { "id": ..., "pos": [500, 320] } ],
    "country": [ ... ],
    "district": [ ... ],
    "town": [ ... ],
    "cell": [ ... ]
  },
  "connections": [
    { "from": ..., "to": ..., "kind": "Public" },
    ...
  ]
}
```

### L.5 — Tests

- Coverage: every channel has a graph node
- Connection symmetry (or asymmetry for OneWay)
- Position normalization round-trip

---

## 10 — Phase M: Time dynamics — DEFERRED to V2 (PO 2026-05-25)

Time-evolution (erosion-over-time, plate drift, climate shift, snapshots,
animation) deferred to a separate V2 roadmap. Will be written when
gameplay genuinely requires temporal world evolution.

Prerequisite tracking: V2 Phase M will require **Phase N (lazy
materialization)** + **Phase O (persistence)** as snapshot mechanism
foundation. V1+ Stages 5 (operations) builds these foundations
regardless, so Phase M can ship later without rework.

Use cases that will trigger V2 Phase M ship:
- "Show this world 1M years ago" gameplay feature
- Continental-drift visualization for educational mode
- Ice-age cycle simulation for long-running campaigns
- Lore/history generation per world era

---

## 11 — Phase N: Lazy materialization (L, ~8–10h)

**Goal**: per data-arch doc §7 — virtual tree + on-demand expansion for
huge worlds.

### N.1 — Virtual Region<N> tree

Per Phase Q (prerequisite), unified Region<N> type. Lazy materialization
adds:
```rust
pub struct VirtualRegion {
    pub path: RegionPath,
    pub boundary: Polygon,
    pub seed: u64,
    pub expanded: Option<Region<N>>,  // None = not yet materialized
}
```

### N.2 — On-demand expansion

```rust
fn expand(virtual: &mut VirtualRegion, params: &LevelParams) {
    if virtual.expanded.is_some() { return; }
    let rng = Rng::for_stage(virtual.master_seed, &virtual.path);
    let children = subdivide(virtual.boundary, params, rng);
    virtual.expanded = Some(Region { ..., children });
}
```

### N.3 — LRU cache

Don't keep all expanded regions in memory:
```rust
pub struct LazyCache {
    pub cache: lru::LruCache<RegionPath, Region<N>>,
    pub max_size: usize,
}
```

Evict oldest when cache full.

### N.4 — Use case

Gigaplanet scale: 10⁶+ regions. Full materialization impossible.
Lazy enables "view only what player is near".

### N.5 — Tests

- Same expansion params + seed → same children (deterministic)
- Cache eviction doesn't lose data (re-expand identical)
- Memory ceiling enforced

---

## 12 — Phase O: Persistence (L, ~8–10h)

**Goal**: content-addressed RegionPath-keyed store for world snapshots.

### O.1 — Storage format

```rust
pub struct WorldStore {
    pub root: PathBuf,                // disk dir
    pub regions: HashMap<RegionPath, RegionFile>,
}

pub struct RegionFile {
    pub path: RegionPath,
    pub region_bytes: Vec<u8>,        // serialized Region<N>
    pub hash: [u8; 32],               // blake3 of region_bytes
}
```

### O.2 — Per-region file

One file per region: `<world_root>/<plate>/<zone>/<subzone>.region`

### O.3 — Multi-snapshot

For time dynamics (Phase M), snapshots stored as:
`<world_root>/snapshot_<tick>/<region_path>.region`

### O.4 — Atomic write + reload

```rust
impl WorldStore {
    pub fn save_region(&self, region: &Region<N>) -> Result<()>;
    pub fn load_region(&self, path: RegionPath) -> Result<Region<N>>;
    pub fn snapshot(&self, tick: u64) -> Result<SnapshotId>;
}
```

### O.5 — Integration with Phase N (lazy)

Lazy cache loads from persistence when not in memory:
```rust
fn get_region(&mut self, path: RegionPath) -> &Region<N> {
    if let Some(r) = self.cache.get(&path) { return r; }
    let region = self.store.load_region(path)?;
    self.cache.put(path, region);
    self.cache.get(&path).unwrap()
}
```

### O.6 — Tests

- Round-trip: save → load → byte-identical
- Hash verification (corruption detection)
- Snapshot rollback (load tick N from disk)

---

## 13 — Phase P: Climate v6 / advanced (L+, ~15–25h)

**Goal**: climate refinements beyond v5 Köppen-lite.

### P.1 — Sub-phases

#### P.1a — Holdridge life zones (3D)

Add **potential evapotranspiration** (PET) as 3rd axis:
```rust
pub fn pet(temp_warm: f32, lat_dist: f32) -> f32 {
    // Holdridge formula: PET = biotemp × 58.93 / precip
    // biotemp = mean of temps capped at 30°C
    ...
}
```

19-Köppen + PET axis = ~30+ Holdridge life zones. More fine-grained
biome classification, especially for Tropical/Subtropical regions.

#### P.1b — True Köppen 30-class

Currently 19 Köppen-lite. Expand to full 30-class:
- Cfa/Cfb/Cfc (oceanic warm/temperate/subpolar)
- Csa/Csb/Csc (Mediterranean)
- Cwa/Cwb/Cwc (subtropical highland monsoon)
- Dfa/Dfb/Dfc/Dfd (continental humid)
- Dsa/Dsb/Dsc/Dsd (continental dry-summer — rare)
- Dwa/Dwb/Dwc/Dwd (continental dry-winter)
- ET (tundra)
- EF (ice cap)
- + Trewartha highland H class

~30 biomes total. Eval framework + render palette updates required.

#### P.1c — W9 spec option B: slope-aware lambertian hillshade

V5 W9 ships amplitude-gated zone shading. Option B (deferred):
- Per-pixel slope normal from elev gradient
- Lambertian shading with sun direction
- Proper cartographic hillshade overlay

Actually this is similar to Phase B (V1 spec). Phase P.1c could just
formalize the V1 Phase B into a proper consumer spec.

#### P.1d — Orographic 2.0

Refinements to v4 Orographic:
- Ocean evaporation source (precip strength depends on upwind ocean area)
- Multi-direction wind (not just lat-banded 3-band model)
- Seasonal wind shift (e.g., monsoon reversal)
- Föhn/Chinook effect (warm dry leeward winds)

#### P.1e — Per-pixel seasonality for microclimates

Currently seasonality is per-zone. V1+ adds per-pixel:
- Slope aspect affects insolation (south-facing slopes warmer in NH)
- Coast distance modulates seasonality (coastal mild winters)
- Local topography (valley bottom colder than ridge in winter)

### P.2 — Effort breakdown

| Sub-phase | Effort |
|---|---:|
| P.1a Holdridge 3D | 4–6h |
| P.1b True Köppen 30-class | 5–8h |
| P.1c Slope-aware hillshade (formalize V1 Phase B) | 1–2h (rollover) |
| P.1d Orographic 2.0 | 3–5h |
| P.1e Per-pixel seasonality | 4–8h |
| **Total Phase P** | **15–25h** |

P.1c overlaps with V1 Phase B; if Phase B ships in V1, P.1c is just spec formalization.

---

## 14 — Phase Q: Recursive Region<N> refactor (L+, ~12–15h)

**Goal**: per data-arch doc §1-§4 — unify Plate/Zone/SubZone into
single recursive Region<N> type.

### Q.1 — Region<N> struct

```rust
pub struct Region {
    pub path: RegionPath,             // [plate, zone, subzone, ...] addresses any depth
    pub depth: u8,
    pub boundary: Polygon,            // world coords
    pub centroid: Point,
    pub sites: Vec<Point>,            // Voronoi sites for child partition
    pub children: Vec<Region>,        // recursive; empty = leaf or unexpanded
    pub subdividable: bool,
    pub tectonics: Tectonics,         // crust + drift + uplift
    pub elevation: ElevationProfile,  // base + relief_budget + terrain_class
    pub adjacency: Vec<Adjacency>,    // Phase I
    pub terrain: Option<TerrainTile>, // for leaf regions
}
```

### Q.2 — Migration from current 3-type system

Current: separate `Plate`, `Zone` (Voronoi inside Plate),
`SubZone` (Voronoi inside Zone).

Target: all are `Region` at different depth.

Migration steps:
1. Introduce `Region` struct (don't break existing code yet)
2. Add conversion: `Plate::to_region()`, `Zone::to_region()`,
   `SubZone::to_region()`
3. Provide adapter: convert old `FlatWorld` into `Vec<Region>`
4. Refactor consumers one-by-one to use Region instead of Plate/Zone/SubZone
5. Once all consumers migrated, delete old types

### Q.3 — LevelParams generalization

Per data-arch doc §7:
```rust
pub struct LevelParams {
    pub count: (usize, usize),
    pub radius_frac: (f32, f32),
    pub separation: f32,
    pub vertices: (usize, usize),
    pub edge_jitter: f32,
}

pub struct WorldParams {
    pub width: u32, pub height: u32, pub master_seed: u64,
    pub levels: Vec<LevelParams>,    // levels[0]=plates, [1]=zones, [2]=sub, ...
}
```

`levels.len()` = depth of tree = N-level recursion.

### Q.4 — Why this matters

Required for:
- Phase N lazy materialization (needs uniform tree)
- Phase O persistence (RegionPath addressing)
- Phase M time dynamics (snapshot system)
- Multi-level recursion beyond depth 2 (current hardcoded limit)

### Q.5 — Tests

- Conversion tests: Plate → Region preserves geometry
- Depth-3+ recursion works
- Address resolution: RegionPath → Region lookup correct
- Backward compat: old WorldData JSON still parseable during transition

### Q.6 — Effort

Major refactor. Lots of consumer changes. 12-15h, possibly 2 sessions.

---

## 15 — Dependencies graph

```
Stage 1 V1 base (A-F)
  └─ (independent of V1+ stages)

Stage 2 Cleanup
  ├─ Q: Recursive Region<N> refactor
  └─ I: Adjacency records as data (can run parallel to Q)

Stage 3 Integration
  ├─ H: WorldGeometry trait (H-3 chosen)
  │   └─ G: Multi-continent + N-tier (needs trait)
  │       ├─ L: MAP_001 graph adapter
  │       └─ K: TMP_001 tilemap adapter (also needs L)

Stage 4 Polish
  ├─ J: Wetlands/volcanoes/named ranges (needs Phase F rivers)
  └─ P: Climate v6 (independent)

Stage 5 Operations
  └─ N: Lazy materialization (needs Q)
       └─ O: Persistence (needs N)

(Stage 6 Phase M deferred to V2 separate roadmap)
```

Critical path under Linear execution (PO chosen): every stage sequential.

---

## 16 — Total roadmap (V1 + V1+, M deferred)

```
V1 base (Stage 1): A → B → C → E → D → F             25h, 6-7 sessions
V1+ cleanup (Stage 2): Q → I                         16-21h, 4-5 sessions
V1+ integration (Stage 3): H → G → L → K             33-45h, 8-12 sessions
V1+ polish (Stage 4): J → P                          21-35h, 5-9 sessions
V1+ operations (Stage 5): N → O                      16-20h, 4-5 sessions
─────────────────────────────────────────────────────────────────────────
TOTAL (V1+V1+)                                       ~110-150h, 28-37 sessions
(V2 Phase M deferred — separate roadmap when triggered)
```

Realistic completion: **5-10 months of focused part-time work** at
2-3 sessions per week.

---

## 17 — Execution order: Track 1 Linear (PO chosen 2026-05-25)

Each stage finishes before next. Safest, easiest to track, predictable
session-by-session ship cadence.

```
Stage 1 — V1 base (6-7 sessions)
  Session 1: Phase A polygon realism
  Session 2: Phase B hillshade in biome
  Session 3: Phase C coastline detail
  Session 4: Phase E L4 landscape diversity
  Sessions 5-6: Phase D L3 features (may span 2 sessions)
  Session 7: Phase F rivers + lakes

Stage 2 — Cleanup (4-5 sessions)
  Sessions 8-10: Phase Q recursive Region<N> refactor
  Session 11: Phase I adjacency records as data

Stage 3 — Integration (8-12 sessions)
  Sessions 12-14: Phase H WorldGeometry trait + impls + first consumer
  Sessions 15-17: Phase G multi-continent + N-tier hierarchy
  Sessions 18-19: Phase L MAP graph adapter
  Sessions 20-23: Phase K TMP_001 tilemap adapter

Stage 4 — Polish (8-9 sessions)
  Sessions 24-25: Phase J wetlands + volcanoes + named ranges
  Session 26: Phase P1 slope-aware hillshade (formalize V1 Phase B)
  Session 27: Phase P2 orographic 2.0
  Sessions 28-29: Phase P3 per-pixel seasonality (microclimates)
  Session 30: Phase P4 Holdridge 3D life zones
  Sessions 31-32: Phase P5 true Köppen 30-class

Stage 5 — Operations (4-5 sessions)
  Sessions 33-34: Phase N lazy materialization
  Sessions 35-36: Phase O persistence

Total: ~36 sessions of focused work.
```

Per session: M-task (~4h) sustainable; L-task may span 2 sessions.

### Why Linear over Parallel

PO chose Linear despite slower total time. Reasons:
- Single thread of attention; less context-switching cost per session
- Each stage produces shippable milestone before next starts
- Easier to insert pauses (life happens) without losing thread
- Lower risk of inter-stage conflict (e.g., refactoring Q during G ship)
- Easier to track progress (current session N of ~34)

Tradeoff: ~5h longer total than Track 2 Parallel; no track interleaving.
Acceptable per PO.

---

## 18 — Risks and mitigations (V1+)

| Risk | Phase | Mitigation |
|---|---|---|
| Phase H decision blocks everything | H | Decide at session start; commit to chosen option |
| Region<N> refactor breaks every consumer | Q | Migration adapter; incremental consumer rewrites |
| Multi-continent breaks single-continent test suite | G | Keep both modes coexistent during transition |
| Persistence format diverges from in-memory | O | Round-trip tests in CI; versioned format |
| Time dynamics is huge scope | M | Defer to V2 final; ship V1+ without if needed |
| Climate v6 expands eval framework heavily | P | Re-baseline per sub-phase; document semantic changes |
| Holdridge / 30-class Köppen palette overflow | P.1a/b | Use HSV-uniform palette generator |
| Tilemap adapter LLM layers (V2 territory) creep into V1+ | K | Strict scope: V1+ ships L1+L2 only, L3+L4 in V2 |

---

## 19 — Decisions locked (PO 2026-05-25)

| Decision | Choice | Note |
|---|---|---|
| Phase H option | **H-3 trait abstraction** | WorldGeometry trait, both pipelines impl |
| Phase M scope | **Defer to V2** | Separate roadmap when game requires time evolution |
| Execution track | **Track 1 Linear** | Sequential stages, predictable cadence |
| Phase G channel tier | **Wait sphere political layer** | Flatworld gets bindings via H-3 trait (Q1) |
| Phase K LLM L3+L4 | **Defer V2 per TMP_001 spec** | Phase K ships L1+L2 only (Q2) |
| Phase P sub-phase order | **P1 → P2 → P3 → P4 → P5** | Physics first, classification last (Q3) |
| Phase P split | **5 separate phases** (P1-P5) | Smaller chunks; Stage 4 = J + P1..P5 (Q4) |
| Phase Q depth | **Full N-level recursion** | Pay cost once; enables Phase N properly (Q5) |
| Phase I granularity | **Per-Region (every depth level)** | Natural with Q's Region<N>; adjacency on Plate/Zone/SubZone alike (Q6) |
| WorldGeometry trait | **6 minimal base + Ext grows organically** | Each capability-adding phase extends Ext (Q7) |
| CellId | **Opaque newtype per impl** | `SphereCellId(u32)` vs `FlatCellId{x,y}`; prevents swap confusion (Q8) |
| Channel tier criteria | **Political/settlement layer not area** | Country=state, District=province, Town=settlement_role (Q9) |

## 19a — Still-open questions for further doc refinement

1. **Phase G channel tier semantics**: country/district defined by political layer (sphere); does flatworld need to derive these or wait until political integrated?
2. **Phase K tilemap LLM layers**: defer L3+L4 to V2 (Track 3 already does this). Confirm scope.
3. **Phase P sub-phase order**: P.1a Holdridge first or P.1b 30-class first? Or run both in parallel?
4. **Phase P sub-phase split**: should P be 5 separate phases (P1, P2, P3, P4, P5) instead of one big phase?
5. **Phase Q migration depth**: full Region<N> generalization, or just unify current Plate/Zone/SubZone without changing depth-2 limit?
6. **Phase I adjacency**: per-zone or per-subzone? Currently spec says per-zone only.
7. **WorldGeometry trait method count**: 11 base + 9 ext methods. Too granular? Too coarse? Will trait API drift over Stages 3-5?
8. **CellId associated type**: u32 for sphere, packed (x,y) for flatworld — should we use opaque newtype to prevent confusion?
9. **Channel tier definitions need formal spec**: continent/country/district/town/cell — what exactly distinguishes country from district? Population? Area?

---

## 20 — Out of scope (truly V2++ / never)

Even with "ship everything", some things are out of THIS roadmap:
- LLM layer 3+4 for tilemap (V2 — TMP_001 design)
- LLM-driven NPC behavior (separate AI feature)
- Frontend rendering of all this (Phaser/Pixi tilemap consumer — separate frontend work)
- Backend services consuming world data (knowledge service, TVL, etc. — separate per-service work)
- Multi-player session sync (V3+ multiplayer scope)

This roadmap is **world-map architecture + data** complete. Consumer
work happens in those features' own roadmaps.

---

## 21 — Mapping to overall LLM_MMO_RPG roadmap

Per `docs/03_planning/LLM_MMO_RPG/features/00_geography/_index.md`, the
world-map system is a **foundation feature** consumed by 7+ downstream
features (PF_001 places, MAP_001 graph, CSC_001 cell scenes, EF_001
entities, RES_001 resources, settlements, routes, political, culture).

V1+ buildout completion = "GEO foundation production-complete" =
unblocks all 7+ downstream features to integrate fully.

Downstream features have their own roadmaps; not in this doc.

---

## 23 — Open-question resolutions (PO 2026-05-25)

Detailed reasoning for each of the 9 questions raised in §19a.

### Q1 — Phase G channel tier semantics (country/district)

**Decision: Flatworld waits for sphere political layer via H-3 trait.**

Rationale:
- Sphere has `political::build(seed, centers, neighbors, biome)` shipped
  with State + Province aggregates (per GEO_002)
- Flatworld doesn't have political layer; building parallel impl
  duplicates 500+ LOC + maintenance burden
- H-3 trait abstracts: consumer queries `world.channel(cell, Country)`
  → sphere returns Some(state_id); flatworld returns None until
  political layer integrated
- Phase G ships with **flatworld returning None for country/district**;
  consumer features handle gracefully or require sphere world

**Side effect**: V1+ flatworld-only worlds can't have country/district
channels. Acceptable — those tier sub-divisions are political concepts
that need political modeling. Mono-flatworld worlds = "single region",
no internal political structure.

### Q2 — Phase K tilemap LLM layers (L3+L4)

**Decision: Defer L3+L4 to V2 per TMP_001 spec. Phase K ships L1+L2 only.**

Rationale:
- TMP_001 spec explicitly defines V1+30d ships L1+L2; V2 adds L3+L4
- L3 (LLM zone classifier for object placement) needs ~3K tokens per
  tilemap × LLM cost budget; defer until cost model justified
- L4 (LLM regional narration cache) similar — V2 polish
- Phase K V1+ scope = procedural-only tilemap generation; consumers can
  use immediately without LLM dependency
- LLM layers can ship independently as V2 TMP_009 / TMP_010

### Q3 — Phase P sub-phase order

**Decision: P1 (slope hillshade) → P2 (orographic 2.0) → P3 (per-pixel
seasonality) → P4 (Holdridge) → P5 (Köppen 30-class).**

Rationale:
- **P1 first**: rollover of V1 Phase B (slope-aware hillshade was V1
  Phase B but might be lighter than the spec doc described). ~1-2h to
  formalize. Visible immediately.
- **P2 second**: orographic 2.0 = climate physics improvement; touches
  precip calculation but doesn't change biome enum. Backward-compat.
- **P3 third**: per-pixel seasonality is microclimate refinement;
  builds on existing zone-level seasonality (v5).
- **P4 fourth**: Holdridge adds 3rd axis (PET) — large addition but
  orthogonal to Köppen enum.
- **P5 last**: Köppen 30-class expansion biggest single change (biome
  enum 19→30; palette + lat-band tables full rework). Pin once at end
  rather than re-baseline through intermediate.

Build physics + microclimate first (P1-P3); add classification axes (P4)
and final biome enum (P5) at the end.

### Q4 — Phase P split into 5 phases

**Decision: SPLIT. Phase P becomes P1, P2, P3, P4, P5 — 5 separate
phases.**

Rationale:
- Current P estimate 15-25h is too big for single phase per session-
  pacing principle (M=4h sustainable, L=split across sessions)
- Each sub-phase is independently shippable + measurable via eval
- Smaller chunks reduce risk of partial-rebase
- Stage 4 becomes: J + P1 + P2 + P3 + P4 + P5 = 6 phases (more
  sessions, smaller commits)

Updated Stage 4 effort:
- J: 6-10h
- P1 slope hillshade: 1-2h
- P2 orographic 2.0: 3-5h
- P3 per-pixel seasonality: 4-8h
- P4 Holdridge axis: 4-6h
- P5 Köppen 30-class: 5-8h
- **Stage 4 total: 23-39h, 6-10 sessions**

### Q5 — Phase Q migration depth

**Decision: Full N-level recursion (option A).**

Rationale:
- Data-arch doc §1-§7 specs `Vec<LevelParams>` with `levels.len()` =
  tree depth = any N
- Option B (just unify depth-2) would force second refactor when game
  needs depth 3+ (e.g., town tier 16-tile sub-grid)
- N-level enables Phase N lazy materialization to work for any depth
  (virtual tree expands on-demand at any level)
- Pay cost ONCE at Phase Q; future depth changes are config not code
- Effort estimate stays 12-15h (vs ~8h for option B)

### Q6 — Phase I adjacency granularity

**Decision: Per-Region at every depth level.**

Rationale:
- With Q's Region<N>, adjacency is natural per-Region property (not a
  Plate-specific vs Zone-specific distinction)
- Use cases need adjacency at multiple levels:
  - Plate adjacency: tectonic seam types (convergent/divergent/transform)
  - Zone adjacency: biome ecotone classification (Phase D L3 features)
  - Sub-zone adjacency: landscape transitions (Phase E L4 features)
- Storage cost: per-zone adjacency ~10 neighbors × 16 bytes = 160
  bytes per zone; for 100 zones = 16KB. Negligible.
- Q6 = "per-Region" naturally falls out of Q5 (full N-level Region<N>)

### Q7 — WorldGeometry trait scope

**Decision: Start minimal (6 base methods); grow Ext organically.**

Rationale:
- Initial 11+9 design (in §H.3) speculative; risks API drift as we
  learn what consumers actually need
- Minimal viable base trait:
  ```rust
  pub trait WorldGeometry {
      type CellId: Copy + Eq + Hash + Debug;
      fn cell_count(&self) -> usize;
      fn cells(&self) -> Box<dyn Iterator<Item = Self::CellId> + '_>;
      fn neighbors(&self, cell: Self::CellId) -> Vec<Self::CellId>;
      fn elevation(&self, cell: Self::CellId) -> f32;
      fn biome(&self, cell: Self::CellId) -> Biome;
      fn climate(&self, cell: Self::CellId) -> ZoneClimate;
  }
  ```
- 6 methods cover ~80% of consumer use cases
- Add Ext methods as Phases G/J/K/L/P need them:
  - `political()`, `settlements()`, `routes()`, `culture()` (existing sphere)
  - `rivers()`, `lakes()`, `features()` (V1 Phases D/F)
  - `wetlands()`, `mountain_ranges()`, `volcanoes()` (V1+ Phase J)
- Channel binding (Phase G) added as Ext method `channel(cell, tier)`
  rather than base — many use cases don't need it

### Q8 — CellId opaque newtype

**Decision: YES, opaque newtype per impl.**

```rust
// Sphere impl
pub struct SphereCellId(u32);
impl WorldGeometry for SphereWorld {
    type CellId = SphereCellId;
    ...
}

// Flatworld impl
pub struct FlatCellId { pub x: u32, pub y: u32 }
impl WorldGeometry for FlatWorld {
    type CellId = FlatCellId;
    ...
}
```

Rationale:
- Prevents accidental swap: consumer holding `SphereCellId` can't pass
  to flatworld method (compile error)
- Documents intent: `fn place_settlement<G: WorldGeometry>(cell: G::CellId)`
  works against any impl via associated type
- Cost: trivial wrapping; opaque tuple-struct compiles away

### Q9 — Channel tier formal spec

**Decision: Channel tier criteria use political/settlement layer
assignments, NOT raw area thresholds.**

```rust
pub enum ChannelTier {
    Planet,      // root — the world itself; only relevant for multi-continent
    Continent,   // largest landmass unit; 1 FlatWorld OR sphere plate
    Country,     // = State (political::build assigns State per cell)
    District,    // = Province (political::build assigns Province per cell)
    Town,        // = Settlement with role ∈ {City, Town, Village}
                 //   (per settlement::SettlementRole)
    Cell,        // = CSC_001 interior 16×16 tile patch
                 //   (1 cell per CellId in current sphere or 16×16 px in flatworld)
}
```

Rationale:
- Area/population thresholds are arbitrary; political/settlement layer
  already encodes these via existing State/Province/Settlement aggregates
- Country = State (political-layer concept); District = Province
  (administrative sub-unit)
- Town = Settlement with population_tier ≥ Village (excludes hamlets)
- Cell = unit gameplay scale defined by CSC_001
- For mono-flatworld worlds without political layer (Q1 decision): only
  Planet/Continent/Cell tiers populated; Country/District/Town = None

**Side effect**: full channel hierarchy only available on sphere worlds
with political+settlement layers active. Flatworld-only worlds operate
at Continent + Cell tiers only. Acceptable per Q1.

---

## 24 — Updated Stage 4 with Phase P split

Per Q4 decision, Stage 4 phases:

| Phase | Name | Effort | Session count |
|---|---|---:|---:|
| J | Wetlands + volcanoes + named ranges | 6-10h | 2 |
| P1 | Slope-aware lambertian hillshade (formalize V1 Phase B) | 1-2h | 1 |
| P2 | Orographic 2.0 (ocean evap source + multi-wind + seasonal) | 3-5h | 1 |
| P3 | Per-pixel seasonality (microclimates) | 4-8h | 1-2 |
| P4 | Holdridge 3D life zones (add PET axis) | 4-6h | 1 |
| P5 | True Köppen 30-class (expand 19→30 biome enum) | 5-8h | 2 |
| **Stage 4 total** | | **23-39h** | **8-9 sessions** |

(Previous P = 15-25h single phase; split adds ~5h for testing per
sub-phase but each ships individually verifiable.)

---

## 25 — Updated total roadmap (post-refinement)

```
V1 base (Stage 1): A → B → C → E → D → F             25h, 6-7 sessions
V1+ cleanup (Stage 2): Q → I                         16-21h, 4-5 sessions
V1+ integration (Stage 3): H → G → L → K             33-45h, 8-12 sessions
V1+ polish (Stage 4): J → P1 → P2 → P3 → P4 → P5    23-39h, 8-9 sessions
V1+ operations (Stage 5): N → O                      16-20h, 4-5 sessions
─────────────────────────────────────────────────────────────────────────
TOTAL (V1+V1+)                                       ~113-150h, 30-38 sessions
(V2 Phase M deferred — separate roadmap when triggered)
```

Each session ships 1 phase (smaller ones may bundle; L tasks span 2).
Linear cadence: predictable per-session ship, ~30-38 sessions total
= ~5-10 months part-time.

---

## 22 — References

- [`2026-05-25-world-map-v1-buildout.md`](2026-05-25-world-map-v1-buildout.md) — V1 spec (Phases A-F)
- [`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md) — §1-§9 design baseline; this doc operationalizes §9 deferred items
- [`2026-05-23-b5-v2-weakness-analysis.md`](2026-05-23-b5-v2-weakness-analysis.md) — climate batch history; Phase P P.1c rolls forward W9 spec option B
- [`2026-05-24-v5-koppen-seasonal-design.md`](2026-05-24-v5-koppen-seasonal-design.md) — v5 Köppen reference; Phase P.1b expands to true 30-class
- TMP_001-008b — tilemap spec (consumed by Phase K)
- MAP_001 — logical graph spec (consumed by Phase L)
- PF_001 — place foundation (consumed by graph node mapping)
- GEO_001-004 — sphere pipeline features (consumed by Phase H integration)
- Köppen, W. (1936) — climate classification base
- Holdridge, L. (1947) — life zones 3D classification
- Mandelbrot, B. (1967) — fractal coastline (relevant to V1 Phase C)
