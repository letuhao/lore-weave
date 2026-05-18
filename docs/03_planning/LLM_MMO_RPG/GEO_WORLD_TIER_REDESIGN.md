# GEO — World-Tier & Geo-Type Redesign (design spec, DRAFT)

> **Status:** DRAFT spec for PO review — no code yet. Supersedes nothing; it
> sits *above* the current `crates/world-gen` generator, most of whose
> per-cell machinery is reused (§7).
>
> **Origin:** the `Gigaplanet` benchmark showed a 501k-cell map still reads as
> *one province*. Cell count is **resolution**, not **scope**. The current
> generator is structurally a *region* generator; this spec defines the *world*
> tier above it. PO vision captured 2026-05-18.

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

## 3 — World topology — a wrapping cylinder

**Recommendation: an equirectangular (plate-carrée) cylinder.** The world is a
`lon × lat` rectangle where **longitude wraps** (column 0 and column `W` are the
same meridian) and **latitude is bounded** by the two poles.

| Option | Globe-like | Fits lon/lat | Render | Cost | Verdict |
|---|---|---|---|---|---|
| **Cylinder** (equirectangular) | wraps E–W ✓, poles are edges | native — it *is* a lon/lat grid | trivial (it is a flat world map) | low | **chosen** |
| True sphere (geodesic / icosphere) | perfect | no clean lon/lat grid | needs map projection | high | alternative — note for "max realism" |

A cylinder gives the PO's exact lon/lat framing, wraps east–west (the seam that
matters for "a globe"), and renders directly as the flat world map a player
expects. The only compromise is **pole distortion** — cells near a pole cover
less real surface; handled by latitude-weighting area calculations and letting
the poles be ice caps anyway. The mesh changes: the current 4-edge perimeter
ring becomes **2 edges** (north pole, south pole); the east and west sides are
**stitched** — cells at lon 0 are neighbours of cells at lon `W`.

→ **Mesh work:** `mesh.rs` gains longitude-wrapping adjacency; the Voronoi/
Delaunay must wrap (duplicate a margin of cells across the seam before
triangulating, then merge — a standard technique).

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
1. Mesh → wrapping cylinder (§3).
2. NEW tier-1 / tier-2 split (§4); `WorldScale` → `(global_mesh, area_grid,
   cells_per_area)`.
3. NEW plate-tectonic continent model (§5) — replaces `CoastlineProfile` +
   `enforce_coherence`.
4. Climate → global Köppen model (§5b) — replaces the 8-zone gradient.
5. Geo-type vocabulary widened (§6) — landforms + biomes + fantasy, on three
   axes instead of one 14-value enum.
6. NEW physiographic-region + ecoregion extraction (§6d).
7. `world_archetype` finally driven (§6c world archetypes).

---

## 8 — Suggested phasing (each phase = a normal 12-phase workflow task)

1. **Cylinder topology** — wrap `mesh.rs` E–W, poles; reproject; keep one
   continent for now. Smallest first step, de-risks the mesh change.
2. **Plate-tectonic continents** — multi-continent + ocean basins + placed
   mountains/rifts/trenches. Retire `CoastlineProfile`/`enforce_coherence`.
3. **Global Köppen climate** — the §5b model.
4. **Geo-type vocabulary** — landform + biome + region extraction (§6a/b/d).
5. **Two-tier scale** — tier-1/tier-2 split, on-demand seamless areas (§4).
6. **Fantasy geo-types** — world archetypes + anomaly regions (§6c).

Phases 1–4 already make a *believable Earth-scale world*; 5 makes it *huge*;
6 makes it *fantasy*. Each is independently shippable.

## 9 — Open questions for the PO

1. **Topology** — cylinder (recommended, §3), or hold out for a true sphere?
2. **Fantasy split** — agree with world-archetype (whole-planet) vs.
   anomaly-region (local) as two separate mechanisms (§6c)?
3. **Tier-2 persistence** — are detail areas generated-on-demand-and-cached, or
   generated-once-and-stored? (Affects storage design, not this generator.)
4. **Phasing** — is the §8 order right, or should "huge scale" (phase 5) come
   earlier?
5. **Scale targets** — confirm rough numbers: tier-1 ~100k–500k cells, area
   grid ~100×100, cells/area ~1000 ⇒ ~10M effective. LLM-tunable within bands?
