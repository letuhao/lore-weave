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

## 6 — Open design decisions (need PO confirmation)

| Question | Options | Default proposed |
|---|---|---|
| Annual-mean only vs seasonal | (a) annual only → Whittaker; (b) seasonal → Köppen subtypes | **(a) v1, (b) v3+** |
| Hemisphere layout | (a) equator at frame centre (symmetric); (b) at one edge (one hemisphere only) | **(a) centre** |
| Wind direction model | (a) constant west→east; (b) latitude-banded; (c) full circulation cells | **(b) banded, v2** |
| Ocean current model | (a) skip; (b) east/west bias on coastal plates; (c) full gyre routing | **(a) v1, (b) v3** |
| Number of biomes v1 | 8 (Whittaker-lite) vs 12 (with subtypes) | **8 in v1, refine in v3+** |
| Local noise on top | None vs small perlin variation | **None** — keep zones flat; if too uniform we add noise after |

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

1. Define the layer trait + `ClimateField` struct (in a new `flat_climate`
   module or a section of `zonegen`).
2. Implement v1 layers: Insolation, Circulation, Continentality,
   ZoneRefinement, ElevationLapse, Whittaker classification.
3. Hook into `render_all_zones_eroded`: precompute `ZoneClimate` per zone via
   the pipeline (replaces the current scattered per-pixel formula). Pixel
   only modifies temp via lapse → flip biome if cold enough (snow caps).
4. Verification: render seeds with deliberately mountainous + coastal +
   inland zones, assert visible:
   - Latitudinal bands (tropics/subtropics/mid-lat/polar).
   - Coastal vs inland distinction within same lat.
   - Snow caps on high mountains regardless of latitude.
5. Defer v3+ (ocean currents, orographic, seasonal Köppen) to later phases.

This unlocks `Hydrology extras` (lakes need water balance = precip −
evaporation, which needs proper climate) and richer terrain colouring.
