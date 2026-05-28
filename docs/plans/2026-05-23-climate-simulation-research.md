# Climate Simulation — Research & Architecture

> **Status:** RESEARCH + recommended architecture, 2026-05-23. Long-term
> reference for the flatworld bottom-up track (and any future spherical-world
> climate work). Written after the B5 v1 ("per-pixel from lat + elev + coast")
> was rejected as **too random** — it lacks layered physical drivers and the
> hierarchical inheritance that real climate exhibits. PO directive: research
> properly, design a **decorator-style composition** that aggregates many
> factors into a final climate per zone, then generate at multiple levels.
>
> Builds on the locked region-tree data architecture
> ([`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md))
> and the hierarchy-depth decision
> ([`2026-05-23-hierarchy-depth-and-diversity-decision.md`](2026-05-23-hierarchy-depth-and-diversity-decision.md)).

---

## 0 — TL;DR

Real climate emerges from **many independent physical drivers stacked in a
specific order**. To simulate it well, we compose drivers as **decorator
layers** (each one pure, testable, swappable) and apply them at the
**appropriate hierarchical level**:

```
World (latitude-only) → Plate (regional) → Zone (local) → Pixel (snow caps only)
```

Per-pixel ad-hoc formulas (B5 v1) fail because they conflate levels and
factors. The fix: factor decomposition + hierarchical inheritance.

---

## 1 — Why climate is complex

A point's climate is the joint result of many fields, each from a different
physical mechanism. None alone is enough. Standard climatology decomposes
climate into 6–10 drivers; procedural worldgen can mimic this by **composing
the drivers as separate fields** then classifying.

**The "too random" failure mode** of an ad-hoc per-pixel formula:

- It mashes drivers into one expression, losing physical structure.
- It applies every driver at the pixel level — even those that should be
  shared by a whole plate (e.g. continentality is a regional property).
- Discrete biome classification at the pixel level amplifies tiny driver
  noise into visible biome-class jitter at boundaries.

The fix is structural: separate the drivers, apply each at its proper level,
classify at the zone level.

---

## 2 — The major climate drivers (in order of dominance)

Listed roughly by how much variance each explains globally.

### 2.1 Insolation — the latitude base

Solar energy received per unit area depends on the sun's angle, which depends
on latitude (and obliquity / season). At the equator the sun is near vertical;
at the poles it grazes. To first order:

$$ \text{insolation}(\phi) \propto \cos\phi $$

Plus an albedo feedback: ice and snow reflect more sunlight → reinforce
polar cold. Forest / ocean absorb more → warm reinforcement.

**Procedural shorthand:**

```
temp_base(lat_dist) = T_eq − (T_eq − T_pole) × |lat_dist|
```

This alone gives the *zeroth-order* hot-equator / cold-pole pattern.

### 2.2 Atmospheric circulation — the bands

Earth has **3 vertical circulation cells per hemisphere**:

| Cell | Latitude | Pressure | Effect |
|---|---|---|---|
| **Hadley** | 0°–30° | Low at equator (ITCZ), high at ~30° subtropical | Warm air rises at equator (rain); descends at 30° (dry → **deserts**) |
| **Ferrel** | 30°–60° | Variable | Westerlies, frontal storms — **wet** mid-latitudes |
| **Polar** | 60°–90° | High at pole | Polar easterlies, cold + **dry** |

**Trade winds** (low latitudes): blow east → west (easterlies).
**Westerlies** (mid lat): blow west → east.
**Polar easterlies**: blow east → west.

The wet/dry bands fall out of cell boundaries:

| Lat | Precip | Why |
|---|---|---|
| 0° (equator) | **HIGH** | ITCZ rising air → cools → condenses |
| ~30° (subtropics) | **LOW** | Descending dry air (subtropical highs) — Sahara, Australia, Atacama |
| ~50–60° (mid lat) | **MEDIUM-HIGH** | Frontal storms in westerly belt |
| 90° (poles) | **LOW** | Cold air holds little moisture |

**Procedural shorthand:** a piecewise lat-precip curve with stops at
[equator, 30°, 55°, polar] = [high, low, medium-high, low]. This is the
foundation of every latitudinal banding you see on biome maps.

### 2.3 Ocean currents — the asymmetry

Ocean gyres run **clockwise in the N hemisphere, anti-clockwise in S**.
Consequence:

- **Western boundary currents** push **warm** water poleward (Gulf Stream,
  Kuroshio, Brazil Current) — these warm the western edges of oceans /
  eastern coasts of continents poleward.
- **Eastern boundary currents** push **cold** water equator-ward (California,
  Humboldt, Benguela) — these chill the eastern edges of oceans / western
  coasts of continents equator-ward.

This is why 50°N in London (eastern Atlantic, warm Gulf Stream) is mild while
50°N in Newfoundland (western Atlantic, cold Labrador Current) is harsh.

Without ocean currents, climate is **east-west symmetric** within each
latitudinal band — which is unrealistic.

### 2.4 Continentality — the moderator vs amplifier

Water has very high thermal inertia; land cools and warms quickly. So:

- **Coastal** cells: moderated. Mild winters, cool summers. Smaller annual
  range.
- **Interior** cells: continental. Cold winters, hot summers. Large annual
  range. Less precipitation (moisture depletes as air travels inland).

A simple proxy: `continentality = clamp(coast_distance / reach, 0, 1)`. Use
it to *expand the annual temperature range* and *attenuate precipitation*.

### 2.5 Topography — the local sculptor

Three distinct effects from elevation:

**Lapse rate** (vertical temperature drop):

| Air condition | °C / km |
|---|---|
| Dry adiabatic | 9.8 |
| Saturated (moist) | ~6.0 |
| Environmental (typical) | **6.5** |

So a 3-km mountain in the tropics is ~20°C colder than the lowland → snow.

**Orographic precipitation** (windward / leeward):

When wind hits a mountain, it's forced up. Rising air cools → moisture
condenses → **rain on windward side**. The dried-out air descends on the
**leeward side** → desert (rain shadow). Examples: Olympic Mts ↔ Eastern
Washington, Andes ↔ Patagonia, Sierra Nevada ↔ Death Valley.

**Slope aspect & valley microclimate:**

- In the N hemisphere, **south-facing** slopes get more sun → warmer, drier
  (vines on south slopes of Burgundy).
- **Valleys** trap cold air at night (inversions), prone to frost.

### 2.6 Altitudinal zonation — vertical climate

The lapse rate creates **vertical biome bands mirroring the latitudinal
ones**. Climbing a tropical mountain you cross every climate zone:

| Elevation (tropics, °N or °S) | Climate analog | Biome |
|---|---|---|
| 0–1000 m | Tropical | Rainforest |
| 1000–2000 m | Subtropical | Cloud / montane forest |
| 2000–3500 m | Temperate | Mid-mountain forest |
| 3500–4500 m | Subarctic | Páramo / alpine grass |
| 4500–5500 m | Polar | Alpine tundra |
| > 5500 m | Ice cap | Glacier / snow |

This is *automatically captured* by the lapse rate on temperature: a high
pixel in a tropical zone classifies as Boreal/Tundra/Ice by the same temp →
biome function as a low-lat low-elev cell.

### 2.7 Local features (smaller-scale)

- **Lakes**: lake-effect snow downwind, moderate local temp.
- **Wetlands / dense forest**: increase local humidity via evapotranspiration.
- **Coastal upwelling**: cold deep water rises near coast (Humboldt, Benguela)
  → very cool dry coastal climate (Atacama, Namib are paradoxical *coastal*
  deserts because of this).
- **Urban heat island**: not relevant for us.

---

## 3 — Biome classification systems

Once you have `(temp, precip[, seasonality, evaporation])` per cell, you
classify it into a biome.

### 3.1 Köppen-Geiger (the gold standard)

5 main groups × subtypes for precip pattern × subtypes for warmth → **30+
classes**:

| Code | Climate | Examples |
|---|---|---|
| **A** Tropical (all months > 18°C) | | |
| Af | Tropical rainforest | Amazon, Congo |
| Am | Tropical monsoon | Mumbai |
| Aw / As | Tropical savanna (wet/dry season) | African savanna |
| **B** Dry (evap > precip) | | |
| BWh | Hot desert | Sahara, Arabian |
| BWk | Cold desert | Gobi, Atacama |
| BSh / BSk | Hot / cold steppe | Sahel, Kazakh steppe |
| **C** Temperate (coldest -3..18°C, warmest > 10°C) | | |
| Cfa | Humid subtropical | SE USA, Yangzi |
| Cfb / Cfc | Oceanic | UK, NW Europe, NZ |
| Csa / Csb | Mediterranean | California, Italy, S Australia |
| Cwa / Cwb | Subtropical monsoon-influenced | N India, Hong Kong |
| **D** Continental (coldest < -3°C, warmest > 10°C) | | |
| Dfa / Dfb | Hot / warm summer | Central US, Canada prairies |
| Dfc / Dfd | Subarctic | Siberia |
| **E** Polar (warmest < 10°C) | | |
| ET | Tundra | Arctic coast |
| EF | Ice cap | Antarctica, Greenland interior |
| **H** Highland (often added; varies by altitude) | Various | Andes, Tibet |

**To classify** you need **seasonal** data, not just annual:
- Warmest month temp
- Coldest month temp
- Annual precip + precip seasonality (winter vs summer dry)

### 3.2 Whittaker biome diagram (simpler 2D)

Mean annual **temperature** (x) × mean annual **precipitation** (y) → a 2D
plot with biome regions:

```
          P
          ▲
 5000 mm  │   Tropical rainforest
          │
          │     Temperate rainforest
          │
          │     Temperate seasonal forest
          │
 1500 mm  │   Boreal forest          Woodland/shrubland
          │
          │     Temperate grassland
  500 mm  │   Tundra              Subtropical desert
          │
        0 │___Arctic ice___|________________________________> T
         -10     0    10    20    30
```

Used by **Dwarf Fortress, Minecraft, Civ**, and many procedural games. Good
fit for our zone-level annual averages.

### 3.3 Holdridge life zones (3D)

Adds **potential evapotranspiration ratio** = (mean biotemp × 58.93 / precip).
More accurate but more complex; defer.

---

## 4 — Procedural techniques

### 4.1 Decorator / layer composition

Each driver is a **layer**, a pure function from world state to climate field.
The composite climate field is built by stacking layers:

```
ClimateField = Insolation
             + Circulation
             + OceanCurrents       // east-west asymmetry
             + Continentality
             + ElevationLapse
             + Orographic          // windward / leeward
             + LocalNoise           // small organic variation
```

This is the **decorator pattern** the PO asked for: each layer is independent,
testable, and swappable.

**Sketch (Rust):**

```rust
pub struct ClimateField {
    pub temp_mean: f32,
    pub temp_warm_month: f32,
    pub temp_cold_month: f32,
    pub precip_annual: f32,
    pub precip_seasonality: f32,  // 0 = even, 1 = single wet season
}

pub trait ClimateLayer {
    /// Modify `field` in place, given the world state and the region (which
    /// level — World/Plate/Zone/Pixel — being computed for).
    fn apply(&self, ctx: &ClimateCtx, field: &mut ClimateField);
}

pub struct InsolationLayer { pub t_eq: f32, pub t_pole: f32, pub lapse: f32 }
pub struct CirculationLayer;        // lat precip bands
pub struct OceanCurrentLayer { ... }
pub struct ContinentalityLayer { pub reach: f32 }
pub struct OrographicLayer { pub wind_dir: (f32, f32) }
pub struct ElevationLapseLayer { pub lapse_rate: f32 }
// ... etc

let pipeline: Vec<Box<dyn ClimateLayer>> = vec![
    Box::new(InsolationLayer { ... }),
    Box::new(CirculationLayer),
    Box::new(OceanCurrentLayer { ... }),
    Box::new(ContinentalityLayer { reach }),
    Box::new(ElevationLapseLayer { lapse_rate }),
    Box::new(OrographicLayer { wind_dir }),
];
let mut field = ClimateField::default();
for layer in &pipeline { layer.apply(&ctx, &mut field); }
let biome = classify(&field);
```

Benefits:
- **Independently testable**: each layer has its own unit tests.
- **Swappable**: try with/without ocean currents to A/B.
- **Phaseable**: ship v1 with 3 layers, add 2 more in v2.
- **Inspectable**: log per-layer contribution to debug.

### 4.2 Multi-level (hierarchical) computation

The region-tree architecture says attributes inherit top-down. Climate must
follow:

| Level | What's computed | Why this level |
|---|---|---|
| **World** | Lat-band base insolation + precipitation circulation pattern | Affects every plate at the same lat identically |
| **Plate** | + ocean-current bias (plate's coastal vs interior position) + plate avg elev correction | A plate-wide climate signature: "this plate is in the subtropical dry belt, on the warm-current side" |
| **Zone** | + zone site lat (refines within plate) + zone continentality (zone site's coast distance) + base zone elevation | **The biome decision happens here**: each zone resolves to one biome |
| **Pixel** | + elevation lapse only (snow caps inside a zone with high peaks) | Pixel-level only modifies temp for altitudinal zonation; doesn't introduce noise |

This is the *correct* fix to B5 v1: per-pixel climate computation was too
fine-grained. The biome should be **decided at the zone level** (so a zone
reads as one ecosystem), with pixel-level only allowed to flip mountain
cells to colder biomes via lapse rate.

### 4.3 Orographic rain shadow (wind routing)

For each cell, simulate moisture transport:

1. Define wind direction by latitude (E↔W from circulation).
2. From each cell, **walk N steps upwind**.
3. Record cumulative elevation gain along the path.
4. If the path crossed high mountains: **moisture was depleted on the
   windward side** → this cell is leeward → less rain.
5. If the path traversed open ocean recently: more moisture available → more
   rain.

Simple formula:

```
moisture(cell) = base_moisture(lat)
               × ocean_proximity(upwind_path)
               × exp(−mountain_gain(upwind_path) × shadow_factor)
```

This produces realistic rain shadows: Patagonia, Death Valley, Central Asia.

### 4.4 Ocean current model (simplified gyres)

For an Earth-like world:
- Hemisphere N: gyres are **clockwise**.
- Hemisphere S: gyres are **anti-clockwise**.

So:
- **W coast of continent in N hemisphere mid-lat** (e.g. Europe): warm,
  poleward current → mild oceanic climate.
- **E coast of continent in N hemisphere mid-lat** (e.g. NE Canada): cold,
  equator-ward current → harsh continental climate.
- (Mirror for S.)

For each coastal cell, find which side of the ocean basin it's on (east or
west of the ocean), apply a temperature bias accordingly.

### 4.5 Seasonality (annual range)

For Köppen subtypes you need **cold-month temp** and **warm-month temp**, not
just annual mean. A simple model:

```
temp_warm_month = temp_mean + amplitude
temp_cold_month = temp_mean − amplitude
```

Where **amplitude** depends on lat (small near equator, large in mid/high
lat) and continentality (small near coast, large inland):

```
amplitude = (a0 + a1 × lat_dist) × (1 + cont × continentality_factor)
```

This lets you distinguish:
- Oceanic Cfb (small amp, mild winter) vs continental Dfb (large amp, cold
  winter) at the same lat.
- Mediterranean Csa (summer dry) vs humid subtropical Cfa (summer wet) by
  precip seasonality.

---

## 5 — Recommended architecture for LoreWeave flatworld

### 5.1 Core principle

**Decorator layers composed at the level appropriate to each driver.** The
zone is the unit at which biome is decided; pixels only deviate via lapse.

### 5.2 Climate field

```rust
pub struct ClimateField {
    pub temp_mean: f32,
    pub temp_warm_month: f32,
    pub temp_cold_month: f32,
    pub precip_annual: f32,
    pub precip_seasonality: f32,  // 0..1 wet/dry season strength
}
```

For first cut you can collapse to `(temp_mean, precip_annual)` (Whittaker
2D) and add seasonal fields when you want Köppen subtypes.

### 5.3 Layer pipeline (in apply order)

1. **InsolationLayer** — temp_mean(lat), warm/cold-month via amplitude.
2. **CirculationLayer** — precip_annual base latitudinal pattern.
3. **OceanCurrentLayer** *(defer v1)* — plate-level temp bias from current
   side.
4. **ContinentalityLayer** — boost amplitude, reduce precip by coast
   distance.
5. **ElevationLayer (plate avg)** — plate-wide cooling from avg elev.
6. **ZoneRefinementLayer** — zone-site lat + zone-site continentality.
7. **OrographicLayer** *(defer v1)* — upwind elev gain → precip drop.
8. **ClassificationLayer** — Whittaker (v1) or Köppen-lite (v2).

### 5.4 Level mapping

| Layer | Level applied |
|---|---|
| Insolation, Circulation | **World** (parameters of the world; sampled when computing each plate/zone) |
| OceanCurrent | **Plate** (which side of ocean does this plate sit on) |
| Continentality | **Plate average + Zone refinement** |
| Elevation | **Plate average + Zone average** |
| Orographic | **Zone** (wind path within a couple of zones up-wind) |
| Classification | **Zone** — *the biome decision lives here* |
| Lapse-for-snow | **Pixel** only, to flip Ice/Tundra on tall cells |

### 5.5 Phased roadmap

| Phase | Layers in pipeline | Visible effect |
|---|---|---|
| **B5 v2 (next)** | Insolation + Circulation + Continentality + ZoneRefinement + plate-elev cooling + pixel lapse for snow caps + Whittaker classification | **Hierarchical** climate: plates at same lat read as same family, zones within a plate vary by coastal vs inland, snow caps emerge naturally |
| B5 v3 | + Simple OceanCurrent (east/west bias) | E-W asymmetry: warm-current coasts vs cold-current coasts |
| B5 v4 | + Orographic (wind-routing precip) | Rain shadows behind mountains |
| B5 v5 | + Seasonality (warm/cold month) → Köppen subtypes | Cfa vs Cfb vs Dfa distinguishable; Mediterranean vs humid subtropical |
| B5 v6 | + Holdridge / true Köppen 30-class | Production-grade biome map |

The **v2** phase is what should replace the B5 MVP — keep the layered pipeline
but only the first 5 layers, classify with Whittaker. Ship that, then iterate.

### 5.6 Mapping to the region tree

The layered pipeline is **explicitly hierarchical**:

```
WorldClimate                       — Insolation + Circulation precomputed
  │
  ├── PlateClimate(plate)          — + OceanCurrent + plate avg elev
  │      │
  │      ├── ZoneClimate(zone)     — + zone continentality + zone elev + orographic
  │      │      │
  │      │      └── biome = classify(zone field)
  │      │      │
  │      │      └── pixel = zone biome [+ lapse override → Ice/Tundra if cold enough]
```

Each level's `ClimateField` is **inherited from the parent** and decorated.
A child can't ignore its parent's climate — it can only refine it. This is
the **top-down inheritance** the data architecture committed to.

---

## 6 — Design decisions (LOCKED 2026-05-23 PO)

| Question | Decision | Note |
|---|---|---|
| Annual-mean only vs seasonal | **annual only → Whittaker** | seasonal/Köppen reserved for v5 |
| Hemisphere layout | **configurable enum** `HemisphereLayout { Equatorial, NorthOnly, SouthOnly }` | author-set per seed; default `Equatorial` (y = h/2 is equator, both caps) |
| Wind direction model | **latitude-banded** | applied implicitly by the circulation curve in v2; explicit wind field arrives with the orographic layer in v4 |
| Ocean current model | **skip in v2** | plate-level slot reserved in the pipeline so v3 OceanCurrent is purely additive (no refactor) |
| Number of biomes v1 | **8 Whittaker** | locked table in §10.4 |
| Local noise on top | **none** | zones stay flat-coloured; pixel-level only diverges via lapse override |
| Pipeline composition style | **function composition** | not trait-objects — research-doc "decorator" is conceptual, implementation uses plain function calls in `compute_zone_climate` |
| Sea proxy for continentality | **`is_sea[i] = !is_land[i] OR elev[i] < sea_level`** | reuses `edge_dist_from_void` BFS over `is_sea`; in v2 identical to "void only" because the coast taper holds all land ≥ shore_level, but the API is v3-lake-ready |

---

## 7 — References / further reading

### Academic
- Köppen, W. (1936). *Das geographische System der Klimate.*
- Köppen-Geiger update: Beck, H. E. et al. (2018) *Present and future
  Köppen-Geiger climate classification maps at 1-km resolution.*
- Whittaker, R. H. (1975). *Communities and Ecosystems.* — the biome diagram.
- Holdridge, L. R. (1947). *Determination of world plant formations from
  simple climatic data.* Science 105: 367–368.
- Trewartha, G. T. (1968). *An Introduction to Climate.* (modified Köppen)
- Pidwirny, M. *Fundamentals of Physical Geography* — open textbook.

### Procedural / game implementations
- **Worldengine** (Mindwerks). Python procedural climate w/ wind +
  orographic. <https://github.com/Mindwerks/worldengine>
- **Dwarf Fortress** climate model (community wiki).
- **Civilization VI / VII** latitudinal band climate.
- **Minecraft 1.18+** multi-noise biome system (3D climate noise +
  Whittaker-style classification).
- **Songs of Syx**, **Stellaris**, **Anno** — various procedural climate
  approaches.
- Whittaker-style game examples: Don't Starve, Subnautica.

### Atmospheric reference data (for calibration)
- NCEP/NCAR Reanalysis — real-world climate by lat/elev/season.
- IPCC AR6 chapters on regional climate (calibration / extreme cases).
- WorldClim (high-res global climate) — pixel-level temp/precip data.

---

## 8 — Glossary

| Term | Meaning |
|---|---|
| **ITCZ** | Inter-Tropical Convergence Zone — equatorial band of converging trade winds → rising air → **rainy** belt |
| **Hadley cell** | Vertical circulation 0°–30°; up at equator, down at 30° |
| **Ferrel cell** | Vertical circulation 30°–60°; westerlies, fronts |
| **Polar cell** | Vertical circulation 60°–90°; polar easterlies, cold dry |
| **Lapse rate** | Rate at which temperature drops with elevation (typ. 6.5°C / km) |
| **Orographic precipitation** | Rain forced by terrain (mountain rising air) |
| **Rain shadow** | Dry zone leeward of a mountain |
| **Föhn / Chinook** | Warm dry wind descending on leeward side of mountain |
| **Continentality** | Tendency to extreme climate with distance from sea |
| **Albedo** | Fraction of incoming solar radiation reflected back |
| **Upwelling** | Cold deep ocean water rising near coast — chills + dries coast |
| **Gyre** | Large rotating ocean current system (clockwise N, anti-CW S) |
| **Trade winds** | Easterlies in tropics (low-lat, equatorward of Hadley descent) |
| **Westerlies** | Mid-lat winds from the west |
| **Polar easterlies** | High-lat winds from the east |

---

## 9 — Action items (what becomes B5 v2)

Superseded by the detailed plan in §10. The high-level summary is unchanged:
v2 = 5 layers (Insolation + Circulation + Continentality + ZoneRefinement +
ElevLapse) + Whittaker 8-biome classifier; classification at zone level, lapse
override at pixel level.

This unlocks `Hydrology extras` (lakes need water balance = precip −
evaporation, which needs proper climate) and richer terrain colouring.

---

## 10 — B5 v2 implementation plan (LOCKED 2026-05-23)

### 10.1 Module layout

NEW file `crates/world-gen/src/flat_climate.rs`. Pure-procedural, no
RNG (climate is deterministic in the world layout + climate params). Hooks
into [`zonegen::render_all_zones_eroded`] only at the colour-pass step —
terrain pipeline (rasterize → erode → coast taper → drainage) is untouched.

### 10.2 Data types

```rust
// flat_climate.rs

pub enum HemisphereLayout { Equatorial, NorthOnly, SouthOnly }

impl HemisphereLayout {
    /// Normalized "latitude distance from equator" ∈ [0, 1] for pixel y on a
    /// map of height h. 0 = equator (warm), 1 = pole (cold).
    pub fn lat_dist(self, y: f32, h: f32) -> f32 {
        match self {
            // y = h/2 is equator; either edge is a pole.
            HemisphereLayout::Equatorial => ((y - h * 0.5).abs() / (h * 0.5)).clamp(0.0, 1.0),
            // y = 0 is equator; y = h is the (north) pole.
            HemisphereLayout::NorthOnly  => (y / h).clamp(0.0, 1.0),
            // y = h is equator; y = 0 is the (south) pole.
            HemisphereLayout::SouthOnly  => ((h - y) / h).clamp(0.0, 1.0),
        }
    }
}

pub struct WorldClimateParams {
    pub hemisphere_layout: HemisphereLayout,
    // Insolation
    pub t_eq:        f32,   // °C at equator at sea level         (default 28.0)
    pub t_pole:      f32,   // °C at pole at sea level            (default −25.0)
    // Circulation — piecewise stops at lat_dist = [0, 0.33, 0.67, 1.0]
    pub precip_eq:        f32,  // mm/yr ITCZ                     (default 2400)
    pub precip_subtropic: f32,  // mm/yr 30° dry belt             (default 300)
    pub precip_midlat:    f32,  // mm/yr 50° wet belt             (default 900)
    pub precip_polar:     f32,  // mm/yr 90° dry pole             (default 150)
    // Continentality
    pub continentality_reach:        f32,  // px (default ~200, scales w/ map size in §10.7)
    pub continentality_precip_atten: f32,  // 0..1 (default 0.55)
    // ElevLapse (pixel)
    pub sea_level:              f32,  // default = `flatworld::BASE_LEVEL + zonegen::SHORE_LEVEL_OFFSET`
                                       // (compile-time link — no magic value)
    pub lapse_per_elev_unit:    f32,  // °C / elev-unit (default 50.0 — at +0.45 mountain → −22°C)
    pub ice_temp:               f32,  // pixel-temp < → Ice    (default −10.0)
    pub tundra_temp:            f32,  // pixel-temp < → Tundra (default 0.0)
    pub peak_lapse_min_delta:   f32,  // delta below which lapse override is suppressed
                                       // (default 0.05 — above plains noise ±0.026, below
                                       // hills +0.13 and mountain peaks +0.48). Stops sub-peak
                                       // noise on polar plains from flipping to Ice.
}

pub struct ZoneClimate {              // computed per L1 zone, cached per render
    pub temp_mean:     f32,
    pub precip_annual: f32,
    pub biome:         Biome,         // zone-default (pre-lapse)
}

pub enum Biome {                      // 8 Whittaker biomes
    Ice, Tundra, BorealForest,
    TemperateForest, TemperateGrassland,
    HotDesert, Savanna, TropicalRainforest,
}
```

### 10.3 Layer pipeline (function composition)

```rust
pub fn compute_zone_climate(
    world: &FlatWorld,
    params: &WorldClimateParams,
    plate_id: usize,
    zone_id: usize,
    edge_dist_sea: &[u32],   // precomputed once over `is_sea` (§10.5)
) -> ZoneClimate {
    let (sx, sy) = world.plates[plate_id].zone_sites[zone_id];
    let h = world.height as f32;

    // 1. Insolation (World layer, sampled at zone lat — sea-level temp).
    let lat_dist = params.hemisphere_layout.lat_dist(sy, h);
    let temp_sea = lerp(params.t_eq, params.t_pole, lat_dist);

    // 1b. Zone-level elevation lapse: a zone above `sea_level` cools by
    //     `lapse_per_elev_unit * (zone_elev - sea_level)`. This makes
    //     elevated plateaus (Tibet-style) classify colder at zone level —
    //     so `pixel_biome` only needs to handle the *additional* drop from
    //     the zone base up to a peak (true snow caps).
    let zone_elev = world.elevation_at(sx, sy);
    let zone_lapse = params.lapse_per_elev_unit * (zone_elev - params.sea_level).max(0.0);
    let temp = temp_sea - zone_lapse;

    // 2. Circulation (World layer, sampled at zone lat).
    let mut precip = circulation_curve(lat_dist, params);

    // 3. (Plate layer reserved — pass-through in v2; v3 OceanCurrent slots here.)

    // 4. Continentality (Zone layer, from zone-site coast distance).
    let coast_d = sample_edge_dist(edge_dist_sea, sx, sy, world.width);
    let cont = (coast_d / params.continentality_reach).clamp(0.0, 1.0);
    precip *= 1.0 - params.continentality_precip_atten * cont;

    // 5. (ZoneRefinement — implicit by using zone-site coords throughout.)

    let biome = whittaker(temp, precip);
    ZoneClimate { temp_mean: temp, precip_annual: precip, biome }
}

// Piecewise-linear over [0, 0.33, 0.67, 1.0] → [eq, subtropic, midlat, polar].
fn circulation_curve(lat_dist: f32, p: &WorldClimateParams) -> f32 { ... }

// Pixel-level lapse override — only fires for genuine peaks (delta ≥ gate)
// so sub-peak relief noise on a Tundra polar plain doesn't flicker to Ice.
pub fn pixel_biome(zc: &ZoneClimate, elev_pixel: f32, zone_base_elev: f32,
                   params: &WorldClimateParams) -> Biome {
    let delta = elev_pixel - zone_base_elev;
    if delta < params.peak_lapse_min_delta {
        return zc.biome;  // not a peak — zone biome stands
    }
    let temp_pixel = zc.temp_mean - params.lapse_per_elev_unit * delta;
    if temp_pixel < params.ice_temp     { Biome::Ice }
    else if temp_pixel < params.tundra_temp { Biome::Tundra }
    else                                { zc.biome }
}
```

### 10.4 Whittaker classifier (8 biomes)

| Biome | temp (°C) | precip (mm/yr) | Hex colour |
|---|---|---|---|
| **Ice**                | *(pixel-lapse only)* < ice_temp     | any        | `#E8EEF2` |
| **Tundra**             | < tundra_temp (or pixel-lapse)      | any        | `#B8B7AE` |
| **BorealForest**       | 0 .. 7                              | > 250      | `#3B5E3A` |
| **TemperateForest**    | 7 .. 22                             | > 600      | `#4F8B41` |
| **TemperateGrassland** | 7 .. 22                             | 250 .. 600 | `#B8B45A` |
| **HotDesert**          | > 7                                 | < 250      | `#D8B070` |
| **Savanna**            | > 22                                | 250 .. 1500| `#C9C04A` |
| **TropicalRainforest** | > 22                                | > 1500     | `#1E5F2A` |

Order of checks in `whittaker(t, p)`: cold tier (Tundra below 0; BorealForest
0..7 with precip threshold) → dry (HotDesert / TemperateGrassland) → hot
(TropicalRainforest > 1500, Savanna 250..1500) → default TemperateForest.

### 10.5 Sea proxy + edge_dist reuse

Replace the existing `edge_dist_from_void(&is_land, w, h)` call in
[`zonegen::render_all_zones_eroded`] with a sea-aware variant:

```rust
let is_sea: Vec<bool> = (0..n).map(|i| !is_land[i] || elev[i] < shore_level).collect();
let edge_dist = edge_dist_from_sea(&is_sea, w, h);   // same BFS, different start set
```

`shore_level` is already computed at zonegen.rs:647. The coast-taper pass at
zonegen.rs:649 keeps every land pixel ≥ shore_level, so in v2 `is_sea ==
!is_land` exactly. The API is the only thing changing — when hydrology v3 adds
lakes, the lake cells naturally enter `is_sea` and continentality respects them
without refactor.

### 10.6 Render hook (replaces hypso colour pass)

In [`zonegen::render_all_zones_eroded`] at line 716+ (colour pass), replace the
`hypso_color(t)` branch with a biome-colour branch:

```rust
// after `subattrs` precompute (line 586) — compute zone climates once per render
let zone_climates: Vec<Vec<ZoneClimate>> = world.plates.iter().map(|p| {
    (0..p.zone_sites.len())
        .map(|zi| compute_zone_climate(world, params, p.id, zi, &edge_dist))
        .collect()
}).collect();

// (zone base_elev cache, parallel shape, for the lapse delta)
let zone_base: Vec<Vec<f32>> = world.plates.iter().map(|p| {
    p.zone_sites.iter().map(|&(sx, sy)| world.elevation_at(sx, sy)).collect()
}).collect();

// colour pass — replace line 727 (`hypso_color`) with:
let (plate_id, l1) = nearest_l1_zone_at(world, x, y);
let zc   = &zone_climates[plate_id][l1];
let base = zone_base[plate_id][l1];
let biome = pixel_biome(zc, elev[i], base, params);
biome_color(biome)
```

The beach band (line 719) + river stamps (line 744) run *after* and override
biome-coloured pixels — coast band stays sand, rivers stay blue.

### 10.7 Resolution-aware tuning

`continentality_reach` is in pixels. The current 1024×640 reference has plates
~250 px across; reach = 200 gives "saturated continentality at the centre of a
medium plate." For a 10× area map (3240×2024), plates are ~√10× wider
(~790 px); reach should scale: `effective_reach = params.continentality_reach
× (short_side / 640).max(1.0)` (mirrors the existing river-brush scale at
zonegen.rs:765).

### 10.8 Test plan

Each layer is independently testable. Acceptance scenarios:

1. **Insolation alone** (precip clamped to mid-band): equator zones return
   Tropical-class temp (~28°C); pole zones return Arctic temp (~−25°C).
2. **Circulation alone** (temp clamped to mid): lat_dist = 0 → max precip;
   lat_dist = 0.33 → minimum subtropic precip; lat_dist = 0.67 → mid-lat
   bump; lat_dist = 1.0 → min polar.
3. **Continentality alone**: coast zone (coast_d = 0) → full precip; interior
   zone (coast_d ≥ reach) → reduced precip by `(1 − atten)` factor.
4. **Lapse override**: high-elev pixel in a TropicalRainforest zone → Ice
   above ice_temp threshold regardless of zone biome (snow cap on Andes-type
   peak in the tropics).
5. **HemisphereLayout** flips: Equatorial gives two cold caps; NorthOnly gives
   one cold cap at y=h; SouthOnly mirrors.
6. **Determinism**: render the same world twice → byte-identical RGB.
7. **Visual smoke** (manual): seed 7 + Gigaplanet-equivalent flatworld;
   confirm latitudinal bands visible; coastal-vs-interior precip drop visible;
   snow caps on mountain zones at low lat.

### 10.9 Files to touch

| File | Action | Why |
|---|---|---|
| `crates/world-gen/src/flat_climate.rs` | **NEW** | the module |
| `crates/world-gen/src/lib.rs` | MOD | `pub mod flat_climate;` export |
| `crates/world-gen/src/zonegen.rs` | MOD | render-hook in `render_all_zones_eroded`; new signature takes `&WorldClimateParams` |
| `crates/world-gen/examples/flatworld.rs` | MOD | CLI flags for the climate params (`--hemisphere`, `--t-eq`, `--lapse`, …); output biome-coloured PNG |
| `docs/plans/2026-05-23-climate-simulation-research.md` | DONE (this file) | locked plan |

### 10.10b As-built deltas from spec (SHIPPED 2026-05-23)

Two intentional deltas surfaced during visual smoke + /review-impl. Both are
*tightenings* over the original spec; neither changes scope:

- **D1 — `peak_lapse_min_delta` field added** (in `WorldClimateParams`, default
  `0.05`). The original spec had `pixel_biome` use any positive elevation
  delta to trigger the lapse override. Visual smoke showed this caused polar
  plains (where zone temp is already below `ice_temp`) to flip to Ice on
  every pixel with positive relief noise (±0.026 amplitude) — turning whole
  polar plates uniformly white. The gate suppresses the override for sub-peak
  relief so only true peaks (Hills, Mountains) earn the override.

- **D2 — Zone-level lapse added** (in `compute_zone_climate`, step 1b).
  Without it, the zone-level classifier received `temp_mean` derived purely
  from latitude — a high-elevation plateau zone at low lat would classify as
  Temperate when it should classify as Boreal/Tundra (Tibetan plateau is at
  Italian latitude but is sub-arctic). The 1b lapse `temp_mean -=
  lapse_per_elev_unit × max(0, zone_elev - sea_level)` corrects this. The
  pixel-level lapse in [`pixel_biome`] then contributes only the
  *additional* drop from zone base up to a peak (true snow caps on top of
  an already-cool mountain zone).

Both fixes were caught by `/review-impl` and folded inline before COMMIT.

### 10.10 Scope guard — what v2 explicitly does NOT do

- No ocean currents (v3).
- No orographic / wind routing (v4).
- No seasonality / Köppen subtypes (v5).
- No per-pixel noise on top of zone biome (PO call — "keep zones flat").
- No biome blending across zone seams (pixel takes the L1 zone's biome
  directly; lapse is the only pixel-level effect).
- No lake / inland-sea handling — `is_sea` is structurally ready but in v2
  has no inland water to mark.
- No CLI re-styling of `--class-demo`, `--eroded-out` — those still output the
  pre-climate hypsometric. A NEW flag e.g. `--biome-out` is the biome render.
