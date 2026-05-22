# Flat-World Region Tree — DATA ARCHITECTURE (design)

> **Status:** ✅ **ACCEPTED — top-down baseline LOCKED (PO, 2026-05-23).** The
> top-down data model in §1–§8 is the agreed schema. The §9 open items
> (which terrain generator per leaf, the seam blend algorithm, persistence, and
> the orogenic-belt-region question) are **deferred — to be resolved bottom-up**
> when per-zone terrain generation is actually built (PO: *"chưa vội … chơi
> bottom-up"*). No code yet; this locks the design, not the implementation.
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
