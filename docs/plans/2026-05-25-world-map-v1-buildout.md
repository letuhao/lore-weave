# World Map V1 — Detailed Buildout Spec (6 phases A–F)

> **Status:** DRAFT 2026-05-25 — design only, pre-implementation.
> Companion to:
> - [`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md)
>   (locked top-down baseline §1–§8, deferred §9 items)
> - [`2026-05-23-b5-v2-weakness-analysis.md`](2026-05-23-b5-v2-weakness-analysis.md)
>   (climate batches v2.1a–e + v4 + v5 shipped)
> - [`2026-05-24-v5-koppen-seasonal-design.md`](2026-05-24-v5-koppen-seasonal-design.md)
>   (v5 Köppen-lite SHIPPED)
>
> **PO 2026-05-25 directive:** "phần flatten map hiện tại giống như bức vẻ
> đồ chơi" — current flat map looks toy-like. Climate quality is mature
> (v5.0 mean 89.56) but **rendering + data depth are visually + semantically
> shallow**. This doc captures the V1 buildout plan to ship a "world map
> done" state.

---

## 1 — Context: what we built vs what's missing

### Shipped (session 58 end state, HEAD `55490a5d`)

- **Flatworld 2D pipeline** (`flatworld.rs` + `zonegen.rs` + `flat_climate.rs`):
  - Plates (depth 0) + Zones (depth 1) + Sub-zones (depth 2)
  - 5-layer climate physics (Insolation, Circulation, v3 OceanCurrent,
    Continentality, v4 Orographic) + pixel ElevLapse
  - 19-Köppen subtype classifier with seasonality data
  - Per-pixel biome render with W6 zone-seam blend + W9 amplitude-gated relief
  - Sidecar JSON export (`--climate-out`) for tilemap consumers
- **Eval framework v4.3** ecotone-aware law-based scoring, mean 89.56
- **Sphere pipeline** (`lib.rs::generate` → `WorldMap`) — parallel system,
  Phase 1+2 shipped (Fibonacci sphere, plates, settlements, routes,
  political, culture)

### NOT shipped — the gaps PO flagged

**🎨 Visual gaps ("toy drawing" feel):**

| # | Gap | Symptom | Real-Earth comparison |
|---|---|---|---|
| V1 | Polygon simplicity | Plates: 6–11 vertices, slight jitter → kid-drawing angular | Real continents: thousand-vertex coastlines, fractal-like |
| V2 | Straight coastlines | Voronoi straight edges + edge_jitter=0.35 | Real coasts: bays, peninsulas, inlets, self-similar at all scales |
| V3 | **No elevation in biome render** | biome.png is flat — mountains and plains look identical color-wise | Real biome maps: hillshade overlay → mountain ridges visible |
| V4 | Sharp zone seams | Voronoi straight + W6 1-pixel blend | Organic curved zone boundaries |
| V5 | Pixel-rasterized rivers | stamp_disk per drainage step → blocky | Smooth Bezier centerlines with tapered width |

**📊 Data gaps ("no depth"):**

| # | Gap | Hiện trạng | Real-Earth analog |
|---|---|---|---|
| D1 | **L3 transition features missing** | Beach band = render effect (uniform 22px gradient) | Coastlines have Beach/Cliff/Mangrove/Fjord variations; rivers have Estuary/Delta |
| D2 | L4 Landscape diversity | Sub-zones inherit parent zone's biome verbatim | Within "Amazon Rainforest", lowland vs montane vs floodplain differ visibly |
| D3 | Rivers as graph | Rasterized D8 drainage → pixel array | Named river systems: source → tributaries → mainstream → mouth |
| D4 | Lakes | None | Closed-basin lakes (Caspian, Great Lakes, Baikal) |
| D5 | Wetlands / marshes | None | Pantanal, Sundarbans, Mekong delta |
| D6 | Named mountain ranges | Sphere has `MountainRange`; flatworld doesn't | Andes, Himalayas, Rockies have names + extent |
| D7 | Adjacency records as data | Renderer infers ad-hoc | Per data-arch §5: `Adjacency { other, seam, kind, strength }` |
| D8 | Volcanoes | None | Random spawn at convergent plate seams |

**🏗️ Architecture gaps (explicitly defer past V1):**

| # | Gap | Defer reason |
|---|---|---|
| A1 | N-tier channel hierarchy (continent/country/district/town/cell) | Needs PO decision on flatworld vs sphere canonical |
| A2 | Multi-continent per "planet" | Currently 1 rect = 1 world; sphere already handles this |
| A3 | Sphere ↔ flatworld integration | 2 parallel systems; decision needed |
| A4 | TMP_001 tilemap adapter | Designed but not built; downstream consumer |
| A5 | MAP_001 graph adapter | Designed but not built |
| A6 | Time dynamics (erosion/drift/climate-shift over time) | V2+ feature |
| A7 | Lazy materialization (virtual tree) | Performance optimization, not blocking |
| A8 | Persistence (RegionPath store) | Production deployment, not local dev |

---

## 2 — V1 acceptance criteria

V1 "world map done" ships when:

- ✅ Polygons realistic: plates ≥24 vertices, noise-deformed coastlines
- ✅ Coastlines jagged (bay/peninsula emerge naturally)
- ✅ Elevation visible in biome render (hillshade overlay)
- ✅ L3 features render as data (≥5 types: Beach/Cliff/Mangrove/Estuary/Foothill)
- ✅ L4 landscape diversity (sub-zones produce different biomes within parent zone)
- ✅ Rivers + lakes as graph entities (named, tributary tree, source/mouth)
- ✅ Sidecar JSON exports all the above for tilemap consumers
- ✅ Eval framework adapts (mean composite stable or improves)
- ✅ Visual self-evaluation by PO confirms "no longer toy-like"

**Out of V1 scope** (deferred to V2+):
- A1–A8 (architecture integration)
- D5–D8 (wetlands, named ranges, volcanoes)
- Time dynamics, persistence, lazy mat

---

## 3 — Phase A: Polygon realism (S, ~2–3h)

**Goal**: fix V1 (kid-drawing polygons).

### A.1 — Bump plate vertex count

Current default `FlatParams { min_vertices: 6, max_vertices: 11 }`. Real
Earth coastlines have ~1000s of vertices at intermediate scale. For our
1024×640 map, ~30–60 vertices per plate gives enough detail without
being expensive.

**Change**: defaults to `min_vertices: 24, max_vertices: 48`.

Cost: O(N) per-plate point-in-polygon test. With 12 plates × 48 verts
× 600k pixels = 350M ops; acceptable (current 12 × 11 × 600k = 80M ops).

### A.2 — Multi-octave noise deformation per vertex

Current vertex calc:
```rust
let r = radius * (1.0 - params.edge_jitter * rng.next_f32());
```
Single-octave jitter, isotropic radial perturbation → looks "fuzzy circle".

**Replace** with multi-octave Perlin noise on radial position:
```rust
let r_base = radius;
let theta = base + wobble;
let noise_freq = 2.5;  // 2.5 cycles around perimeter → main lobes
let noise = fbm_2d(theta * noise_freq, plate_salt, 3); // 3 octaves
let r = r_base * (1.0 + EDGE_NOISE_AMP * noise);
let r = r * (1.0 - params.edge_jitter * rng.next_f32() * 0.3); // residual jitter
```

Result: bays + peninsulas emerge at multiple scales (large lobes from
low-freq octave, small bumps from high-freq octave).

### A.3 — Voronoi zone boundary curve-fit

Voronoi cells have straight edges between sites. **Don't** change the
underlying partition (would break neighbor relationships), but **post-
process** the visible boundary in the biome renderer:

Option B (chosen): perturb the LOOKUP function `plate.zone_at(x, y)` by
adding Perlin noise to query position before nearest-site search:
```rust
let warp = fbm_2d(x * 0.02, y * 0.02, zone_salt, 2) * ZONE_WARP_AMP;
let (qx, qy) = (x + warp_x, y + warp_y);
nearest_site(&plate.zone_sites, qx, qy)
```

This makes zone boundaries WAVY without changing site positions or
breaking sub-zone hierarchy. Sample around boundary: 5–8 pixel waviness.

### A.4 — Tests + hash pin rebase

- New tests: vertex count assertion + noise determinism
- Hash pin: biome render bytes shift (polygon shapes change everything
  downstream) — rebase
- Eval expectation: mean composite roughly stable (biome distribution
  shouldn't shift much, just visual geometry)

**Files touched**: `flatworld.rs` (vertex gen + Plate::zone_at warp),
maybe `noise.rs` (add `fbm_2d` if not present), `zonegen.rs` (hash pin).

**Risk**: noise warp on `zone_at` lookup could create thin slivers if
warp_amp too high. Mitigation: cap warp_amp at 0.3 × site spacing.

---

## 4 — Phase B: Hillshade in biome render (S–M, ~3h)

**Goal**: fix V3 (elevation visible in biome.png).

### B.1 — Compute slope per pixel

For each land pixel `i`, compute slope from `state.elev[i]` and 4
neighbors:
```rust
let dx = (state.elev[i+1] - state.elev[i-1]) * 0.5;
let dy = (state.elev[i+w] - state.elev[i-w]) * 0.5;
let normal = normalize([-dx, -dy, 1.0 / SLOPE_SCALE]);
```
`SLOPE_SCALE` = pixel size in world units / elevation unit. Tune so
slopes feel right (~0.02 for 1024px world).

### B.2 — Lambertian shading factor

Sun direction: `[sin(azimuth), cos(azimuth), elevation_angle]`.
Convention: sun from NW (azimuth=315°), elevation 45° (typical
cartographic).
```rust
let sun = normalize([-0.5, -0.5, 0.7]);
let shade = dot(normal, sun).max(0.1); // floor at 10% for shadow detail
```

### B.3 — Modulate biome color L in HSL

To preserve biome identity (don't shift hue), modulate Lightness only:
```rust
let (h, s, l) = rgb_to_hsl(biome_color);
let l_new = (l * (0.5 + 0.5 * shade)).clamp(0.0, 1.0);
hsl_to_rgb(h, s, l_new)
```
Shading range: `[L × 0.5, L × 1.0]` for shadow-to-noon variation.

**Why HSL not RGB**: same lesson as v5 W9 — RGB multiplicative would
shift biome toward different canonical color (Cfb → Csa drift); HSL
L-only preserves the H+S "identity" of the biome.

### B.4 — Orthogonal to W9

v5 W9 (amplitude-gated zone-level shading) operates at ZONE level
(uniform ±15% per zone). Phase B operates at PIXEL level (per-pixel
slope). Both can stack: W9 sets the zone's overall darkness/brightness
based on relief amplitude; Phase B adds per-pixel detail.

Decision: KEEP W9 (zone-level subtle) + ADD Phase B hillshade. Order:
`biome_c → W9_modulate → W6_seam_blend → Phase_B_hillshade → beach_tint`.

### B.5 — Tests + visual compare

- Unit test: slope=0 → shade=full (no modulation)
- Unit test: slope facing sun → bright; facing away → dark
- Visual compare: mountain ridges should "pop" in biome.png — Death
  Valley should look 3D-ish

**Risk**: hillshade darkens overall scene if shadow floor too low.
Mitigation: keep floor ≥0.5 so unshaded areas keep original color.

---

## 5 — Phase C: Coastline detail (M, ~3–4h)

**Goal**: fix V2 (straight coastlines).

### C.1 — Detect plate boundary pixels

Walk all pixels; for each Land pixel, check if any of 4 neighbors is
Void → boundary pixel. Build set of boundary pixel coordinates.

### C.2 — Boundary deformation via domain warp

For each boundary pixel `(x, y)`, perturb the boundary check using
domain warp:
```rust
let wx = fbm_2d(x * COAST_FREQ, y * COAST_FREQ, COAST_SALT, 4);
let wy = fbm_2d((x + 1000.0) * COAST_FREQ, y * COAST_FREQ, COAST_SALT, 4);
let qx = x + wx * COAST_AMP;
let qy = y + wy * COAST_AMP;
// Use (qx, qy) for plate containment query
```
`COAST_FREQ` ≈ 0.025 (40-pixel wavelength), `COAST_AMP` ≈ 6.0 (max 6px
deformation). 4 octaves give multi-scale bays.

### C.3 — Rasterization

Re-rasterize `is_land[i]` using deformed query: `plates_at(qx, qy)`.

Performance: only re-check pixels near current boundary (already
detected in C.1) — saves full-grid scan. Or: integrate into
`compute_render_state` rasterize loop with always-deformed query.

### C.4 — Natural emergence of bays + peninsulas

Side effects:
- Plate boundary now follows fractal coastline
- Beach band auto-conforms to jagged edge
- River mouths land at natural inlets

### C.5 — Tests + visual

- Visual compare: hemi_north / baseline_s7 should show realistic
  bays + peninsulas
- Test: deterministic from COAST_SALT
- Eval: lat_banding shouldn't shift much; biome distribution maybe ±1%
  (a few coastal pixels reclassified)

**Risk**: heavy domain warp can create disconnected islands or land
inside void. Mitigation: cap COAST_AMP small (≤8px), use moderate
COAST_FREQ.

---

## 6 — Phase D: L3 Features (L, ~6–8h) — biggest payoff

**Goal**: fix D1 (transition features as data + render).

### D.1 — FeatureKind catalog

```rust
pub enum FeatureKind {
    // Coast family (Land ↔ Ocean)
    Beach,           // Plains/Grassland ↔ Ocean warm
    BeachTropical,   // TropicalRainforest ↔ Ocean
    Mangrove,        // TropicalRainforest ↔ Ocean shallow
    Cliff,           // Mountains ↔ Ocean
    Fjord,           // Mountains ↔ Ocean cold (≥0.6 lat_dist)
    RockyCoast,      // Boreal/Tundra ↔ Ocean
    // River family
    Estuary,         // River ↔ Ocean
    Delta,           // High-flux River ↔ Ocean
    RiverConfluence, // River ↔ River merge point
    // Mountain family
    Foothill,        // Mountains ↔ Plains (transition zone)
    MountainPass,    // Lowest-elev path through Mountains
    AlpineMeadow,    // Mountains ↔ Forest (treeline)
    // Desert family
    Oasis,           // Desert ↔ Lake/River (point feature)
    DesertEdge,      // Desert ↔ Grassland
    // Ecotone family (gradient transitions)
    ForestEdge,      // Forest ↔ Grassland
    TundraEdge,      // Tundra ↔ Forest (treeline)
}
```

Total: **16 feature types**. Manageable.

### D.2 — Adjacency detection algorithm

Per design doc §5, build per-zone adjacency list:
```rust
pub struct Adjacency {
    pub other: RegionPath,
    pub seam: Vec<Point>,        // polyline along the boundary
    pub kind: AdjacencyKind,
}
pub enum AdjacencyKind {
    SiblingInterior,             // 2 zones, same plate (zone↔zone in plate)
    CrossPlate { tectonic_kind: SeamKind }, // 2 zones, different plates
    LandOcean,                   // Land ↔ Void (coastline)
    ZoneSubzone,                 // L1↔L2 interface (rarely needs feature)
}
```

Algorithm:
1. Walk all pixels — for each pixel, find owning plate + zone + subzone
2. For each pixel, check 4 neighbors; if neighbor has different
   plate/zone/subzone, record adjacency
3. Dedupe + group adjacencies by (other_path) → seam polyline

### D.3 — Feature spawn rules

Per adjacency, classify what feature to spawn:
```rust
fn classify_feature(a: &Adjacency, biome_a: Biome, biome_b: Biome, ...) -> Option<FeatureKind> {
    match a.kind {
        AdjacencyKind::LandOcean => {
            // Determine land-side biome + lat
            match (land_biome, land_terrain_class, lat_dist) {
                (Af, _, _) => Some(Mangrove),
                (_, Mountains, lat) if lat > 0.6 => Some(Fjord),
                (_, Mountains, _) => Some(Cliff),
                (Et | Ef, _, _) => Some(RockyCoast),
                (Dfc | Dfd, _, _) => Some(RockyCoast),
                (_, _, lat) if lat < 0.4 => Some(BeachTropical),
                _ => Some(Beach),
            }
        }
        AdjacencyKind::SiblingInterior => {
            // Within-plate zone↔zone seam
            match (biome_a, biome_b) {
                (Af | Am | Aw, Bsh | Bwh) => Some(DesertEdge),
                (Cfb | Cfa | Dfb, Bsk | Bsh) => Some(ForestEdge),
                (Et, Dfc | Dfb) => Some(TundraEdge),
                _ => None,
            }
        }
        _ => None,
    }
}
```

### D.4 — Render features as colored bands

Instead of current uniform 22px beach gradient, render features as
3–8px bands with feature-specific colors:
- Beach: warm sand `[212, 200, 178]`
- BeachTropical: cooler off-white sand `[225, 215, 195]`
- Mangrove: muddy green-brown `[110, 95, 65]`
- Cliff: dark grey `[90, 88, 85]`
- Fjord: deep blue-grey `[70, 95, 120]`
- RockyCoast: brown-grey `[140, 130, 115]`
- Estuary: silt brown `[150, 130, 95]`
- Delta: fan-shaped tan `[180, 170, 140]`
- Foothill: muted green `[125, 145, 95]`
- Oasis: bright green dot `[80, 160, 90]` (small radius, 5–10px)
- Edges (ForestEdge/TundraEdge/etc.): blended biome colors at seam

### D.5 — Sidecar export

Extend `ZoneClimateExport` with `features: Vec<FeatureExport>`:
```rust
pub struct FeatureExport {
    pub kind: &'static str,       // "Beach", "Cliff", "Estuary", ...
    pub seam: Vec<[f32; 2]>,      // polyline
    pub width: f32,                // perpendicular extent in pixels
}
```

Sidecar JSON now carries feature catalog per zone — tilemap consumers
can use directly without re-implementing adjacency detection.

### D.6 — Eval expectation

Adding features:
- More pixel-color variety → diversity sub-score up
- Features are climatically appropriate (Beach only at warm coasts, etc.)
  → sanity stays stable
- lat_banding might shift slightly because beach pixels are now
  classified as Beach instead of as adjacent biome — need to add to
  PROFILE_LAT_BANDS or accept as "neutral biome"

### D.7 — Tests

- Unit: feature classifier returns correct FeatureKind for each
  (biome_a, biome_b, lat) combo
- Unit: adjacency detection finds all 4-neighbor differences
- Integration: render with features differs from render without; visual
  inspection confirms features at right locations
- Sidecar test: features exported in JSON match in-memory feature list

**Risk**: render cost — adjacency detection + feature rasterization
adds ~10% render time. Acceptable for now (~5s/render vs 4.5s).
Mitigation: cache adjacency per `compute_render_state`.

**Files touched**: NEW `flat_features.rs` module; `flat_climate.rs`
(maybe FeatureExport struct); `zonegen.rs` (renderer wiring); maybe
`climate_eval.py` (recognize new feature colors as neutral biomes).

---

## 7 — Phase E: L4 Landscape diversity (M, ~4h)

**Goal**: fix D2 (sub-zones within same biome look identical).

### E.1 — Per-sub-zone climate delta

Each sub-zone gets a `LandscapeKind` based on its position within the
parent zone:
```rust
pub enum LandscapeKind {
    Lowland,         // closer to sea_level, parent's biome
    Highland,        // higher elev within zone, cooler (-3°C)
    Floodplain,      // near river, wetter (+30% precip)
    Coastal,         // near coast, milder + wetter
    LeewardSlope,    // back side of mountain, drier (-30% precip)
    WindwardSlope,   // front side of mountain, wetter (+30% precip)
}
```

Detect landscape per sub-zone:
- If terrain class == Mountains AND on prevailing-wind side → WindwardSlope
- If Mountains AND opposite → LeewardSlope
- If avg elev > zone median + threshold → Highland
- If within river path → Floodplain
- If within 2 zone-radii of coast → Coastal
- Default → Lowland

### E.2 — Climate delta per landscape

```rust
fn landscape_climate_delta(l: LandscapeKind) -> (f32, f32) {
    match l {
        Lowland => (0.0, 1.0),         // no change
        Highland => (-3.0, 1.0),       // cooler
        Floodplain => (0.0, 1.30),     // wetter
        Coastal => (1.0, 1.15),        // milder + wetter
        LeewardSlope => (0.0, 0.70),   // drier
        WindwardSlope => (0.0, 1.30),  // wetter
    }
}
```

### E.3 — Per-sub-zone Köppen reclassification

In `compute_zone_climate`, currently classify once per L1 zone. Move to
classify per L2 sub-zone with applied landscape delta:
```rust
let (temp_delta, precip_factor) = landscape_climate_delta(subzone.landscape);
let sz_temp = zone_temp + temp_delta;
let sz_precip = zone_precip * precip_factor;
subzone.biome = koppen_classify(sz_t_warm + delta, sz_t_cold + delta, sz_precip, winter_frac);
```

### E.4 — Visible effect

Within a zone "Cfb Oceanic":
- Lowland sub-zone: Cfb (unchanged)
- Highland sub-zone: Dfb (cooler → continental)
- Coastal sub-zone: Cfb (unchanged but maybe Cfa if pushed warmer)
- Floodplain sub-zone: Cfa (wetter → humid subtropical)

→ Multiple Köppen biomes visible WITHIN single Voronoi zone polygon.
Much more variety per render.

### E.5 — Tests

- Unit: per landscape kind, delta is correct
- Unit: detect Highland correctly (within-zone elev > median + 0.05)
- Integration: count Köppen variety per render — should increase
- Eval: diversity sub-score should improve; sanity stable

**Risk**: per-sub-zone reclassification breaks W6 seam blend (seam
between 2 sub-zones in same parent zone now blends 2 different
biomes instead of same color). Actually this is FEATURE not bug —
seam blend now shows real ecotone.

**Files touched**: `flat_climate.rs` (per-sub-zone climate),
`zonegen.rs` (compute landscape per sub-zone in compute_render_state).

---

## 8 — Phase F: Rivers + Lakes as graph (M–L, ~5h)

**Goal**: fix D3 + D4 (rivers as entities, lakes as data).

### F.1 — River graph construction

Refactor existing D8 drainage to produce graph:
```rust
pub struct River {
    pub id: RiverId,
    pub source: (f32, f32),       // headwater point
    pub mouth: (f32, f32),         // ocean confluence
    pub segments: Vec<RiverSegment>,
    pub tributaries: Vec<RiverId>, // upstream rivers that merge in
    pub flux_peak: f32,            // mm/yr × drainage area
}

pub struct RiverSegment {
    pub centerline: Vec<(f32, f32)>, // polyline
    pub width_at_start: f32,
    pub width_at_end: f32,
}
```

Algorithm:
1. Walk D8 drainage from each headwater (pixels with drainage > threshold
   and no incoming drainage)
2. For each headwater, traverse downstream until hit ocean or another
   river → segment
3. Detect confluences (drainage merges) → tributaries

### F.2 — Lake detection

Lakes = closed-basin depressions where drainage doesn't escape to ocean.
Detect via:
1. Compute post-erosion elevation
2. Run pit-filling: find depressions
3. If depression area > threshold AND total drainage > threshold →
   classify as Lake
4. Extract shore polygon (boundary of below-fill-level area)

```rust
pub struct Lake {
    pub id: LakeId,
    pub shore: Vec<(f32, f32)>,
    pub center: (f32, f32),
    pub area: f32,
    pub inflows: Vec<RiverId>,
    pub outflow: Option<RiverId>,
}
```

### F.3 — Rendering polish

Once rivers are graphs:
- Bezier smoothing on centerlines (cubic Bezier through control points)
- Width interpolation along segment (tapered)
- Lake render: blue fill within shore polygon, slight bump for shore line

### F.4 — Features at river-lake-ocean interfaces

Delta, Estuary, Oasis features (from Phase D) now use river graph as
input. Phase F prereq for some Phase D features.

### F.5 — Sidecar export

Add `rivers: Vec<RiverExport>` + `lakes: Vec<LakeExport>` to sidecar.

### F.6 — Tests

- Unit: river graph has correct source/mouth/tributary structure
- Unit: lake detection finds known closed basins
- Integration: render shows smooth rivers + lake shapes
- Determinism: same seed → identical river graph

**Risk**: pit-filling is O(N²) naive; for 600k pixels, may be slow.
Use priority-queue-based watershed algorithm — O(N log N).

**Files touched**: `hydrology.rs` (graph construction); maybe NEW
`lake.rs` module; `flat_climate.rs` (export); `zonegen.rs` (render).

---

## 9 — Effort summary

| Phase | Scope | Estimated hours | Session count |
|---|---|---:|---:|
| A. Polygon realism | Geometry + warp | 2–3 | 1 |
| B. Hillshade in biome | HSL slope modulation | 3 | 1 |
| C. Coastline detail | Domain warp on boundary | 3–4 | 1 |
| D. L3 Features | Adjacency + 16 feature types + render + sidecar | 6–8 | 1–2 |
| E. L4 Landscape | Per-sub-zone climate delta | 4 | 1 |
| F. Rivers + Lakes | Graph construction + pit-filling | 5 | 1 |
| **Total** | **V1 buildout** | **~25h** | **6–7 sessions** |

Per-session pacing: M-task (~4h) per session is sustainable. L-task (Phase
D) might span 2 sessions or 1 long session.

---

## 10 — Risks and mitigations

| Risk | Phase | Mitigation |
|---|---|---|
| Polygon warp creates self-intersecting plates | A | Cap noise amp; reject samples that violate point-in-polygon convexity |
| Hillshade darkens overall scene | B | Floor shading factor at 0.5 to preserve unshaded color |
| Coastline warp creates disconnected islands | C | Cap deformation amp ≤8px; require contiguous boundary post-warp |
| L3 features add too many color variants | D | Eval BIOME_COLORS dict should add features as neutral (skip lat-banding check) |
| L4 landscape per-sub-zone reclassification creates Tetris feel | E | Within-zone biome shifts should be 1 tier max (Cfb→Cfa OK, Cfb→Bwh too far) |
| River graph construction slow for 600k pixels | F | Priority-queue watershed; cache between renders |
| Tilemap consumer needs migration | D+E+F | Sidecar additive; biome names stable; features/landscapes are NEW fields |
| Eval framework can't score new features properly | D | Phase D includes climate_eval.py update for feature recognition |

---

## 11 — Open questions for implementer

1. **Coastline detail noise wavelength**: 40px (`COAST_FREQ=0.025`) reasonable for 1024px world; tune empirically per visual review.
2. **Hillshade sun direction**: NW + 45° elevation is cartographic standard; could be world-property for "sun position" if planet-style worlds desired.
3. **L3 feature catalog**: 16 types proposed; could expand to 25 (add Wadi, Cirque, etc.) or contract to 10 (essentials only). Decision at Phase D start.
4. **L4 landscape detection thresholds**: Highland=elev>median+0.05; tune per visual review.
5. **River segment Bezier smoothing**: cubic Bezier through every 3rd control point reasonable; tune at Phase F render polish.
6. **Lake area threshold**: ≥50px² ≈ small lake; major lakes ≥500px². Tune.
7. **Per-phase eval baseline**: do we lock new baseline after each phase (v5.1, v5.2…) or only at V1 ship?

---

## 12 — Architecture gaps explicitly out of V1 scope

V1 is **rendering + data depth completion** of the flatworld pipeline.
Following gaps are NOT in V1 and need separate planning:

- **A1**: N-tier channel hierarchy (continent/country/district/town/cell) — needs PO decision on flatworld vs sphere as canonical
- **A2**: Multi-continent per world (sphere already handles this)
- **A3**: Sphere ↔ flatworld integration — needs PO decision
- **A4**: TMP_001 tilemap adapter — downstream consumer; can be designed independently
- **A5**: MAP_001 graph adapter — downstream consumer
- **A6**: Time dynamics — V2+ feature
- **A7**: Lazy materialization — performance, not blocking
- **A8**: Persistence — production, not local

These deferrals are deliberate. V1 should ship flatworld at production
quality first, then PO decides integration story.

---

## 13 — Phase ordering rationale

Recommended order: **A → B → C → E → D → F**.

- **A first**: most visible toy-fix. Polygons are upstream of everything.
- **B second**: hillshade is rendering-only, doesn't change data — minimal risk after A.
- **C third**: coastline detail builds on A's polygon geometry.
- **E before D**: L4 landscape diversity changes biome distribution per sub-zone; should land before L3 features which depend on biome pairs. Otherwise feature classification might be tuned for old biome distribution then need re-tune after L4 ships.
- **D after E**: features classify based on biome adjacencies; needs L4 to know real adjacency biomes.
- **F last**: rivers + lakes need feature-aware estuary/delta classification (Phase D) AND landscape-aware floodplain detection (Phase E). Could move earlier if Phase D feature catalog doesn't include river features, but cleaner last.

Alternative orders to consider:
- **D before E**: ship L3 features faster for tilemap consumer to start integrating; L4 landscape diversity later
- **F before D**: build rivers as graph first (foundation), then features can reference rivers for Estuary/Delta detection
- **C before B**: ship coastlines visibly first, hillshade afterward; B is more involved

PO to choose order at session start.

---

## 14 — References

- [`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md) — locked top-down baseline §1–§8; §9 deferred items
- [`2026-05-23-b5-v2-weakness-analysis.md`](2026-05-23-b5-v2-weakness-analysis.md) — climate batch history (v2.1a–e, v4, v5 shipped)
- [`2026-05-24-v5-koppen-seasonal-design.md`](2026-05-24-v5-koppen-seasonal-design.md) — v5 design SHIPPED reference
- Phase A noise inspiration: Worley + Perlin domain warping
- Phase B hillshade reference: USGS standard cartographic shading
- Phase C coastline reference: Mandelbrot fractal coastline (1967, "How long is the coast of Britain?")
- Phase D feature catalog draws from: Beck et al. 2018 Köppen-Geiger + Olson 2001 ecoregions + Whittaker 1975 transitions
- Phase F river graph reference: Strahler stream order; pit-filling Wang & Liu 2006
