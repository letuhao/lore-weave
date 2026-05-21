# GEO — World-Tier & Geo-Type Redesign (design spec, LOCKED 2026-05-20)

> **Status:** PO-reviewed and **LOCKED 2026-05-20**. 4 of 5 open questions
> resolved (§9); Q3 (tier-2 persistence) deferred to Phase 5. No code yet —
> Phase 1 spherical topology is the next BUILD task. Supersedes nothing; sits
> *above* the current `crates/world-gen` generator, most of whose per-cell
> machinery is reused (§7).
>
> **Origin:** the `Gigaplanet` benchmark showed a 501k-cell map still reads as
> *one province*. Cell count is **resolution**, not **scope**. The current
> generator is structurally a *region* generator; this spec defines the *world*
> tier above it. PO vision captured 2026-05-18; decisions locked 2026-05-20.
>
> **PO decisions (2026-05-20):**
> - **Topology:** true sphere (icosphere / spherical Voronoi) — §3
> - **Fantasy split:** two-level — world-archetype + anomaly-region — §6c
> - **Phasing:** default §8 order (cylinder→tectonics→climate→vocab→scale→fantasy,
>   with phase 1 retitled to *spherical* topology)
> - **Scale:** spec defaults, LLM-tunable in bands — §4 / §9 Q5

---

## 1 — What the PO asked, answered straight

### Q1 — "Does the current algorithm support multiple continents joined by ocean, seamless like a real globe?"

**No — two fundamental gaps:**

1. **Topology.** The mesh is a flat `[0,1]²` square (`mesh.rs` — a perimeter
   ring + jittered interior). It has 4 hard edges and 4 corners. A globe
   **wraps** east–west (the left and right edges are the *same* meridian) and
   has **poles**. The current map cannot wrap; it is a bounded rectangle.
2. **Single-continent by construction.** `terrain::enforce_coherence`
   *deliberately submerges every land component except the largest* for every
   non-Archipelago profile — it forces **one** continent. `Archipelago` is the
   only multi-land profile and it is **5 fixed discs**. There is no model of
   "an LLM-chosen number of continents in an ocean."

What *is* already right: generation is **one global pass over the whole mesh**
— there are no independently-generated chunks, so there are no stitch seams
*within* the map. That principle (§4) carries straight into the redesign.

### Q4 — "Split into total cells + lon/lat; ~10M cells; how do areas link seamlessly; how do other games do it; does the current algorithm support it?"

**Seamlessness, the one principle:** *one global field is the source of truth;
an area is a derived **view** of it, never an independent generation.* The
"chunk feeling" comes from generating chunks in isolation with per-chunk seeds.
The fix every game uses:

- **Minecraft-class**: terrain = a global continuous function of absolute
  `(x, z)` + world seed. A chunk is just a 16×16 *slice* — the function does
  not know chunk boundaries, so they are invisible.
- **4X / Civ / Dwarf Fortress**: the whole world is generated at once, in
  memory, then played.
- **Streaming MMO worlds**: a coarse global field is always resident; per-tile
  detail is generated **on demand**, *deterministically*, from the global
  field + a global high-frequency noise function. Adjacent tiles agree at the
  seam because they sample the *same* global field and the *same* global
  noise — tiles often overlap-sample a margin of neighbours to blend.

**Does the current algorithm support 10M?** Seamless — yes, in principle (it is
already one global pass). Scale — **no**: a 10M-cell `WorldMap` held in memory,
with Voronoi + priority-flood + erosion run on all 10M at once, is multi-GB and
minutes of compute (benchmark: 501k = 8.5 s, ~hundreds of MB; 10M extrapolates
super-linearly to minutes / several GB). 10M needs the **two-tier**
architecture in §4 — a coarse global tier always resident, a fine per-area
tier derived on demand.

---

## 2 — Vision (PO, 2026-05-18)

- The **LLM decides** how many continents, the climate of each region, and the
  scale — the generator must *support* that range, not hard-code it.
- Multiple continents joined by ocean, **seamless like a real globe**.
- Climate **at least as rich and complex as Earth**, ideally more — researched,
  written into the design.
- Geo-type vocabulary: **Earth as the standard** (researched landform +
  terrain taxonomy), **plus** many fantasy / *tiên hiệp* (xianxia) types.
- **Political layers (provinces, nations) are NOT part of this** — they are a
  separate layer on top. The GEO map is purely the **geographer's view**. The
  GEO map's own "regions" must therefore use a *geographic* regionalization
  (§6), not a political one.
- Scale: split into **total cells** and a **longitude × latitude** grid; e.g.
  10M cells over 100 lon × 100 lat ⇒ an "area" ≈ 1000 cells. Areas must link
  **seamlessly**.

---

## 3 — World topology — a true sphere

**Decision (PO 2026-05-20): a true sphere.** Points are sampled directly on a
unit sphere, with adjacency derived from the **spherical Voronoi diagram** (=
the dual of a spherical Delaunay triangulation). No edges, no poles-as-edges,
no wrap seam — the sphere has none of these by construction.

| Option | Globe-like | Fits lon/lat | Render | Cost | Verdict |
|---|---|---|---|---|---|
| Cylinder (equirectangular) | wraps E–W ✓, poles are edges | native — it *is* a lon/lat grid | trivial (it is a flat world map) | low | alternative — note for "fast ship" |
| **True sphere (spherical Voronoi)** | perfect | derived (lat=asin(z), lon=atan2(y,x)) | needs map projection | medium | **chosen** |

The PO picked sphere over cylinder for max realism — the lon/lat grid is then a
*projection* of the sphere, not the sphere's native parametrization. Pole
distortion vanishes (a Fibonacci-lattice sphere sampling is near-uniform in
solid angle). The "area grid" in §4 becomes a projection-time slicing.

### 3a — Mesh approach: Fibonacci sphere + spherical Voronoi via 3D convex hull

The standard procedure (well-conditioned, deterministic, no special pole cases):

1. **Fibonacci lattice on the unit sphere.** Place `N` points at angles
   `(θ_i, φ_i)` where `φ_i = i · (π · (3 − √5))` (golden angle) and
   `cos θ_i = 1 − (2 i + 1) / N` — near-uniform in solid angle, deterministic.
   Apply seed-driven small jitter (rotation + ±ε perturbation) for the
   "natural look" the current Voronoi mesh has.
2. **3D convex hull of points on the unit sphere.** A 3D convex hull whose
   vertices are all on a sphere has every face on the sphere — and each face is
   a **Delaunay triangle on the sphere**. Implementations: `chull` crate, or
   roll our own Quickhull (small N, easy).
3. **Spherical Voronoi = dual.** Each Voronoi cell vertex is the circumcentre
   on the sphere of one Delaunay triangle (normalized to unit length). The cell
   for a sample point is the polygon of those circumcentres, in CCW order
   around the point.
4. **Adjacency from Delaunay edges.** Two cells are neighbours iff their sample
   points share a Delaunay edge.
5. **(lat, lon) per cell** = `(asin(z), atan2(y, x))` of the cell-centre point.

This replaces today's "perimeter ring + jittered interior + `delaunator`" in
`mesh.rs`. **`delaunator` is removed** (it's 2D-only); replaced by a 3D convex
hull. The hash + ChaCha8 determinism discipline is preserved.

→ **Wrap-around adjacency**: handled automatically — a point at lon ≈ 0 and a
point at lon ≈ 2π are *3D-close* and become Delaunay neighbours. There is no
seam to glue.

→ **Pole handling**: handled automatically — Fibonacci lattice spreads points
near poles correctly; spherical Voronoi has no "edge of the world."

→ **Rendering**: a `Projection` enum (`Equirectangular` default;
`Mollweide`/`Mercator`/`Orthographic` later) handles 3D-sphere → 2D-image. The
relief renderer's per-pixel re-triangulation now does **spherical** barycentric
sampling. The relief field's `noise` / `fBm` inputs switch from `(x, y)` to
`(lat, lon)` (wrapping) or `(x, y, z)` (3D noise, naturally seamless on the
sphere — recommended; no wrap glitches at the antimeridian).

### 3b — Why not icosphere subdivision?

A subdivided icosahedron (8× = ~5k faces, 9× = ~20k, 10× = ~80k, ...) gives
*triangle* cells of near-equal area, but they are **regular hexagonal-ish**
(every cell has exactly 5–6 neighbours) — the procedural-Voronoi "organic"
look we keep is lost. Fibonacci sampling + spherical Voronoi keeps the
familiar irregular-polygon cells, with the same per-cell degree distribution
(3–10ish) we have today. Icosphere is a fallback if cell-area uniformity
becomes critical.

---

## 4 — Two-tier scale architecture

The single-tier generator cannot reach 10M cells. Split into two tiers; the
**tier-1 field is the source of truth, tier-2 is a derived view** (§1, Q4).

### Tier 1 — the global world mesh (always resident)

A coarse whole-world mesh — **target ~100k–500k cells** (benchmark says ~2–9 s,
hundreds of MB — affordable to hold resident). One global pass produces:

- tectonic plates → continents & ocean basins (§5)
- global climate → Köppen type per cell (§5b)
- physiographic regions + biomes (§6)
- the coarse heightmap, rivers, coastlines

This *is* essentially today's generator — fixed to be a wrapping cylinder and
multi-continent, with the richer climate/geo vocabulary.

### Tier 2 — per-area detail (generated on demand, cached)

The world is partitioned into a **`lon × lat` grid of areas** (the PO's
100×100). Each area's fine mesh (~1000+ cells, tunable) is generated **on
demand**, deterministically, from:

1. the **tier-1 field sampled/interpolated** across the area (elevation,
   climate, biome, region — the area inherits its big structure from tier 1);
2. **local high-frequency detail** = a *global* continuous procedural function
   of **absolute world `(lon, lat)`** + world seed (NOT a per-area seed).

**Why this is seamless:** two adjacent areas (a) inherit the *same* continuous
tier-1 field at their shared edge, and (b) add detail from the *same* global
noise function — so the detail matches across the seam by construction.
Generating area A alone vs. as part of its neighbourhood yields an identical
boundary. Areas also overlap-sample a one-cell margin of neighbours for the
mesh adjacency to stitch. **No per-area seeds, ever** — that is the rule that
kills the "chunk feeling."

`total_cells = areas × cells_per_area`; both LLM-tunable. The `WorldScale`
enum is replaced by `(global_mesh_size, area_grid: (lon, lat), cells_per_area)`.

---

## 5 — Continent model — tectonic plates

Replace `CoastlineProfile` (one landmass) + `enforce_coherence` (force-one)
with a **plate-tectonic model** — the standard for realistic multi-continent
worlds, and it yields mountains/rifts/trenches *for free*.

1. **Seed N plates** (LLM- or seed-chosen N) over the cylinder; each plate is
   **oceanic** or **continental** (continental crust = high-standing = land).
2. Give each plate a **motion vector**. Classify every plate boundary:
   - **convergent, continental–continental** → fold-mountain belt (Himalaya);
   - **convergent, oceanic–continental** → subduction → trench + volcanic arc;
   - **convergent, oceanic–oceanic** → island arc;
   - **divergent** → mid-ocean ridge, or a **continental rift valley** (the
     fantasy "great rift" is just an exaggerated divergent rift — §6c);
   - **transform** → fault zones.
3. Continental interiors → cratons (old, eroded, stable); margins → coasts.
4. The existing **stream-power erosion** then carves the uplifted belts.

This produces an LLM-chosen number of continents, real ocean basins, and
correctly *placed* mountains/rifts/trenches/arcs — none of which the current
radial-mask heightmap can do.

### 5b — Climate model — Köppen-grounded

Earth's reference standard is the **Köppen–Geiger classification**: 5 groups,
~30 types. Tier-1 climate computes, per cell, the inputs and resolves a Köppen
type:

| Group | Types (the vocabulary) |
|---|---|
| **A tropical** | Af rainforest · Am monsoon · Aw/As savanna |
| **B arid** | BWh/BWk hot/cold desert · BSh/BSk hot/cold steppe |
| **C temperate** | Cfa humid-subtropical · Cfb oceanic · Cfc subpolar-oceanic · Csa/Csb/Csc Mediterranean · Cwa/Cwb/Cwc subtropical-monsoon/-highland |
| **D continental** | Df/Dw/Ds × a/b/c/d (warm-summer … extreme-winter) |
| **E polar** | ET tundra · EF ice cap |
| **H highland** | montane — overrides by elevation |

**Inputs** (a global model, not today's single hemisphere gradient): latitude →
insolation/temperature bands; elevation lapse rate; **continentality** =
distance to ocean (interior extremes vs. maritime mildness); **orographic** rain
shadow (already built — `climate.rs`); **prevailing wind cells** (Hadley/
Ferrel/Polar — multiple bands, not one wind); **ocean currents** (warm/cold
coastal currents — new; e.g. why a west coast is mild). Seasonality from
axial tilt. Output: a Köppen type per cell — far richer than today's 8
`ClimateZone`. Climate + landform then drive the biome (§6b).

---

## 6 — Geo-type vocabulary

Three distinct axes — the current code conflates them into 14 `BiomeKind`.

### 6a — Landform types (physiographic — pure terrain)

Researched Earth taxonomy (the geographer's landform set):

- **Tectonic/structural:** fold mountains · block (fault) mountains · volcanic
  mountains · dome mountains · plateaus (tectonic / volcanic / dissected) ·
  rift valleys · escarpments · cratonic shields.
- **Fluvial:** river plains / floodplains · valleys (V- and U-shaped) ·
  canyons & gorges · deltas · alluvial fans · badlands.
- **Coastal:** beaches & barrier islands · fjords · estuaries · capes & bays ·
  cliffed coasts · atolls & coral reefs.
- **Arid:** ergs (dune seas) · regs · playas · mesas & buttes · inselbergs.
- **Glacial:** cirques · moraines · ice sheets · glacial lakes.
- **Karst:** sinkholes · karst towers · cave systems.
- **Volcanic:** calderas · lava fields · cinder-cone fields · geothermal basins.
- **Basins & lowlands:** structural basins · endorheic basins · wetlands/marsh.

### 6b — Biomes (climate × landform → ecology)

The **WWF 14-biome / Whittaker** scheme (today's `BiomeKind` is roughly this,
to be widened): tropical & subtropical moist/dry forest · tropical grassland &
savanna · desert & xeric shrubland · temperate forest (broadleaf / conifer) ·
temperate grassland · Mediterranean shrubland · boreal forest / taiga · tundra ·
montane grassland · mangrove · plus aquatic: ocean · shelf sea · lake · river.

### 6c — Fantasy / *tiên hiệp* geo-types — split by scope

A "lava world" and a "great rift" are *not* the same kind of thing. Split:

- **World archetypes** (whole-planet — set at tier-1, recolour the entire
  generation): e.g. **Lava World** (molten seas, ash skies, obsidian
  continents), **Shattered/Destroyed World** (a broken crust, floating
  fragments, a wound where an ocean was), **Ice World**, **Ocean World**,
  **Desert World**, **Verdant/Spirit World**. These map to the inert
  `world_archetype` field — finally given meaning.
- **Anomaly regions** (local — a fantasy feature *within* an otherwise
  Earth-like world): **Great Rift** (a continent-splitting chasm) ·
  **blighted/corrupted lands** · **spirit-vein mountains** (xianxia — terrain
  charged with qi) · **floating-island archipelago** · **crystal/glass desert**
  · **ashlands** · **mist-drowned lowlands** · **a god-wound crater**. These are
  placed as overrides on top of the physical model, like a biome stamp.

This two-level split (whole-world vs. regional) is the key structural decision
for fantasy support — flagged for PO confirmation (§9).

### 6d — Geographic regionalization — answering "how does geography define a region?"

Researched answer: geography's *own* regionalization — independent of politics
and of ecology — is the **physiographic region**, a hierarchy:

> **physiographic division → physiographic province → physiographic section**

— each a contiguous area of shared landform character and common geologic
origin (e.g. "the Rocky Mountain System" → "Southern Rockies" → ranges). This
is purely the landform view. The complementary climate-aware regionalization is
the **ecoregion** (realm → bioregion → ecoregion — climate + landform +
ecology).

→ **The GEO map outputs geographic regions, never political ones.** It will
emit **physiographic provinces** (landform-defined) and **ecoregions** (biome-
defined). Provinces/nations are a *separate* downstream layer that consumes
this map — exactly as the PO specified.

---

## 7 — What carries over, what is new

**Reused from the current `crates/world-gen` (the per-cell machinery is sound):**
Voronoi dual-mesh · priority-flood hydrology · stream-power erosion · the
relief renderer (supersample / complementary detail / occlusion) · the
blake3 + ChaCha8 determinism & `content_hash` discipline · LLM `CreativeSeed`
authoring · feature extraction + LLM naming.

**New / changed:**
1. Mesh → true sphere (Fibonacci sampling + spherical Voronoi via 3D convex
   hull, §3 / §3a). `delaunator` (2D) replaced by `chull` (3D) or hand-rolled
   Quickhull-on-sphere.
2. NEW tier-1 / tier-2 split (§4); `WorldScale` → `(global_mesh, area_grid,
   cells_per_area)`. The area grid is now a *projection-time slicing* of the
   sphere by (lat, lon) bands, not a native parametrization.
3. NEW plate-tectonic continent model (§5) — replaces `CoastlineProfile` +
   `enforce_coherence`.
4. Climate → global Köppen model (§5b) — replaces the 8-zone gradient.
5. Geo-type vocabulary widened (§6) — landforms + biomes + fantasy, on three
   axes instead of one 14-value enum.
6. NEW physiographic-region + ecoregion extraction (§6d).
7. `world_archetype` finally driven (§6c world archetypes).

---

## 8 — Suggested phasing (each phase = a normal 12-phase workflow task)

1. **Spherical topology** — replace flat-square `mesh.rs` with Fibonacci-sphere
   sampling + spherical Voronoi (3D convex hull). Add `Projection` for 2D
   rendering (Equirectangular default). Keep one continent
   (`enforce_coherence` adapts to a spherical mesh) — multi-continent comes in
   Phase 2.
   - **STAGE A DONE (2026-05-20, `1433f045`):** Fibonacci-sphere mesh +
     hand-rolled 3D Quickhull + spherical Voronoi polygons; `Cell.center`
     migrated to `[f32;3]`; 3D Perlin noise + sphere-native
     `terrain::height_at` (seamless across the antimeridian — proven by
     `height_at_is_continuous_across_the_antimeridian`); `CoastlineProfile`
     heuristics reframed with great-circle distance; `effective_latitude`
     swap to match (u,v) convention.
   - **STAGE B-1 DONE (2026-05-21):** `Projection` enum defined
     (Equirectangular + Orthographic — full implementation with 10 unit
     tests covering round-trip, hemisphere visibility, pole-camera safety,
     disc coverage); every downstream consumer migrated to native 3D
     (climate / hydrology / political / settlement / routes / culture);
     `(u, v)` adapter scaffold dropped from `lib::generate`; spherical
     `pathfind::spaced_ok` (radians); orographic wind march on a tangent-
     plane projection. `render.rs` + `relief.rs` still hardcode
     equirectangular internally.
   - **STAGE B-2 DONE (2026-05-21):** `Projection` threaded through every
     `render.rs` + `relief.rs` entry point; the relief renderer's per-pixel
     sampler rewritten to back-project canvas pixel → 3D point → nearest cell
     (so **Orthographic renders a real globe view** — a disc with the far
     hemisphere culled), the domain-warp + detail fBm switched to **3D** noise
     (seamless across the antimeridian), and `delaunator` **dropped** from
     `Cargo.toml`. The `SpatialIndex` is now projection-aware (visible-only
     buckets + `u`-wrap). CLI `--projection equirectangular|orthographic` +
     `--camera x,y,z`. SVG export stays equirectangular (a globe SVG is not
     meaningful). `Projection` is a render flag (like `--style`), **not** on
     `CreativeSeed` — rendering is not part of `WorldMap`/`content_hash`.
   - **PHASE 1 COMPLETE.** Next major work is **Phase 2 — plate tectonics**
     (§5): multi-continent worlds with placed mountain belts / rifts / arcs.
2. **Plate-tectonic continents** — multi-continent + ocean basins + placed
   mountains/rifts/trenches. Retire `CoastlineProfile`/`enforce_coherence`.
3. **Global Köppen climate** — the §5b model.
4. **Geo-type vocabulary** — landform + biome + region extraction (§6a/b/d).
5. **Two-tier scale** — tier-1/tier-2 split, on-demand seamless areas (§4).
6. **Fantasy geo-types** — world archetypes + anomaly regions (§6c).

Phases 1–4 already make a *believable Earth-scale world*; 5 makes it *huge*;
6 makes it *fantasy*. Each is independently shippable.

## 9 — Open questions (PO review log)

| # | Question | Resolution |
|---|---|---|
| 1 | **Topology** — cylinder or true sphere? | **RESOLVED 2026-05-20** — true sphere (§3 / §3a). |
| 2 | **Fantasy split** — world-archetype + anomaly-region two-level? | **RESOLVED 2026-05-20** — two-level per §6c. |
| 3 | **Tier-2 persistence** — generated-on-demand-and-cached, or stored? | **DEFERRED to Phase 5** — affects storage design, not the generator core. Revisit when tier-2 implementation begins. |
| 4 | **Phasing** — §8 order or move scale earlier? | **RESOLVED 2026-05-20** — default §8 order (with phase 1 retitled to *spherical topology*). |
| 5 | **Scale targets** — tier-1 100k–500k / area 100×100 / cells/area 1000? | **RESOLVED 2026-05-20** — spec defaults, LLM-tunable within bands. |
