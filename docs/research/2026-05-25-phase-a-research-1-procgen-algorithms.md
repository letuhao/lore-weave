# Research 1 — Procgen Continent Algorithms (Phase A v2 baseline research)

**Date:** 2026-05-25 (session 59) · **Author:** general-purpose research agent · **Context:** PO feedback after Phase A v1 calibration — "polygons look better but still toy-blob, real Earth has Indonesia/Japan/Norway-style complexity"

## §1 — Why real coastlines are complex

### Mandelbrot 1967 fractal coastline result

Lewis Fry Richardson noticed border-length estimates between countries disagreed wildly depending on the ruler used. Mandelbrot's 1967 *Science* paper "How Long Is the Coast of Britain? Statistical Self-Similarity and Fractional Dimension" formalised this as the **Richardson–Mandelbrot law**:

```
L(ε) ≈ F · ε^(1 − D)
```

where `ε` is the ruler length, `L` is the measured length, and `D ∈ [1, 2]` is the **fractal dimension** of the coast.

Measured values:

| Coast | D | Character |
|---|---|---|
| South African | ~1.02 | Smooth, near-straight |
| Britain (west coast) | ~1.25 | Moderately crinkled |
| Norway (with fjords) | ~1.52 | Deep-fjord, near-2D |

**Britain at 100 km ruler ≈ 2,800 km; at 50 km ≈ 3,400 km; at 1 km ≈ 8,000 km+.**

### Five physical processes act at decoupled scales

Coastline complexity is the **superposition of several processes that all act over a range of scales**:

1. **Tectonic boundary geometry (≥1000 km)** — plate rifts and convergences set the macro-shape
2. **Isostatic rebound and sea-level change (100–1000 km, geologic time)** — same heightmap intersects sea at different contour
3. **Fluvial / glacial erosion (1–100 km)** — rivers carve valleys → rias when flooded; glaciers carve U-valleys → fjords (Norway's D=1.52 is almost entirely glacial)
4. **Wave / longshore drift (10 m – 10 km)** — smooths headlands, builds spits, encloses lagoons
5. **Karst / lithology contrast (any scale)** — limestone vs basalt erode at different rates

Crucial insight: **all five act simultaneously at different scales**. Procedural generation must inject complexity at **multiple decoupled scales**.

### Implication for our 12-plate model

At 1024×640 px and 12 plates we average ~55k px² per plate — each plate ~230 px across. To recover Earth-like complexity we need detail bands at roughly **230 px → 80 px → 25 px → 8 px** (plate macro → peninsula → bay → islet), i.e. roughly four octaves of structure.

## §2 — Algorithm Catalog (10 techniques)

Each entry: **Idea · Pros · Cons · Complexity (1–5) · Implementation sketch.**

### 2.1 Domain Warping (Iñigo Quilez)

**Idea.** Replace `f(p)` with `f(p + k·g(p))` where `g` is itself fbm. Quilez's classic recipe is two-level: `q = fbm(p)`, `r = fbm(p + 4·q + offsets)`, final = `fbm(p + 4·r)`. Straight isolines bend, lobes get stretched, recesses get carved.

**Pros.** Cheap (3× fbm cost), purely deterministic, no extra data structures, plugs directly into a noise-threshold continent mask.
**Cons.** Doesn't add NEW scales of detail — it warps existing ones. The warp strength `k≈4.0` is a sweet spot.
**Complexity:** 1.

Reference: [Iñigo Quilez — Domain Warping](https://iquilezles.org/articles/warp/)

### 2.2 Plate-Tectonic Simulation with Rigid Body Motion (Gainey / Viitanen)

**Idea.** Treat each plate as a polygon with a velocity vector (or rotation axis on a sphere). Step time; where plates converge, raise crust; where they diverge, sink it; transform faults cut straight gashes.

**Pros.** Produces realistic mountain belts, island arcs, rifts naturally. Boundaries are non-circular because plate edges interlock after stepping.
**Cons.** Heavy. Requires plate motion integration, collision detection, crust transfer, erosion to be tuned.
**Complexity:** 4–5.

References:
- [Andy Gainey — Experilous](http://experilous.com/1/blog/post/procedural-planet-generation)
- [Lauri Viitanen — PlaTec thesis (2012)](https://www.theseus.fi/bitstream/handle/10024/40422/Viitanen_Lauri_2012_03_30.pdf)

### 2.3 Voronoi Sub-Plates ("Recursive Lloyd")

**Idea.** Inside each macro-plate, generate N sub-Voronoi cells; give each a small drift vector; let cells "drift apart" by inflating the parent polygon then subtracting narrow strait-shaped gaps.

**Pros.** Reuses existing Voronoi-zone code; produces archipelago-like clusters where sub-cells separate.
**Cons.** "Strait" geometry must be parameterised carefully to avoid pixel artefacts.
**Complexity:** 3.

### 2.4 Diffusion-Limited Aggregation (DLA)

**Idea.** Plant a seed pixel. Release random walkers from boundary; when one bumps the cluster, it sticks. Repeat N times. Cluster grows as branchy fractal of dimension **D ≈ 1.71**.

**Pros.** Mathematically guaranteed fractal; gorgeous branching/peninsular structure for free.
**Cons.** Slow (Monte Carlo per pixel); needs a bias to favour landward growth; hard to compose with tectonic plate seeds.
**Complexity:** 3.

Reference: [Diffusion-Limited Aggregation — Wikipedia](https://en.wikipedia.org/wiki/Diffusion-limited_aggregation)

### 2.5 Reaction-Diffusion (Gray-Scott)

**Idea.** Two species U, V diffusing at different rates with non-linear reaction; depending on (F, k) parameters you get stripes, spots, fingerprints, worm-like growth. The "spots → coral" regime produces continent/ocean masks resembling real geography.

**Pros.** Self-organising, no manual seed placement, natural multi-scale appearance.
**Cons.** Hard to control specific outcomes (it's chaotic); slow to converge (~10k iterations); doesn't honour tectonic plate seeds.
**Complexity:** 4.

### 2.6 Hydraulic Erosion as Post-Process

**Idea.** Start with a simple heightmap; run thousands of "droplets" that flow down-gradient, picking up sediment on steep slopes and depositing on flat. Drainage carves valleys; when the heightmap is intersected by a sea contour, those valleys become rias, fjords, and dendritic estuaries — **exactly the "Chesapeake Bay" pattern**.

**Pros.** Produces realistic dendritic coast geometry from any starting heightmap.
**Cons.** Computational cost (100k+ droplets); requires a heightmap, not a mask; tuning depth/rate is tedious.
**Complexity:** 3.

Reference: [Job Talle — Simulating Hydraulic Erosion](https://jobtalle.com/simulating_hydraulic_erosion.html)

### 2.7 Marching Squares on Multi-Octave Noise Threshold

**Idea.** Build a per-pixel scalar field `h(x,y) = base_shape(x,y) + Σ aᵢ·fbm(fᵢ·x, fᵢ·y)` (e.g. 6 octaves at f = 1, 2, 4, 16, 32, 64). Threshold at `h > 0` to get a land mask, then run marching squares to extract a smooth polygon outline.

Bras&Plucky's island series (Sept 2025) does this with a coastal-boost factor `(1 − e⁴)` that injects extra high-freq noise *only* near the shore.

**Pros.** Single unified pipeline; coastline fractality is dialled in by octave count.
**Cons.** Abandons the "polygon vertex perturbation" abstraction — you now think in heightmaps.
**Complexity:** 2–3.

Reference: [Bras&Plucky — Procedural Island Generation III](https://brashandplucky.com/2025/09/17/procedural-island-generation-iii.html)

### 2.8 Falloff Maps + Noise (Sebastian Lague)

**Idea.** Multiply (or subtract) a noise heightmap by a smooth island-falloff map. Lague's classic remap is `f(x) = x^a / (x^a + (b − b·x)^a)` with `a = 3, b = 2.2` — an S-curve.

**Pros.** Dead simple; trivially controls "island vs mainland"; widely understood.
**Cons.** Produces single-blob islands; no archipelago.
**Complexity:** 1.

### 2.9 Polygon Map Generation with Centroidal Voronoi (Amit Patel / Red Blob)

**Idea.** Cover plane with Poisson-disc points; Voronoi-tessellate; Lloyd-relax 2 iterations; classify each polygon as land/ocean by a *radial-sine island function* + flood-fill from map edges to find ocean.

**Pros.** Beautiful low-poly aesthetic; integrates with rivers/biomes naturally; the classification step is robust.
**Cons.** Coastline complexity is bounded by polygon count (1000 polygons ≈ Britain-resolution at best); not designed for *fractal* edges.
**Complexity:** 3.

Reference: [Amit Patel — Polygonal Map Generation](http://www-cs-students.stanford.edu/~amitp/game-programming/polygon-map-generation/)

### 2.10 Recursive Midpoint Displacement on Polygon Boundary

**Idea.** Classic fractal terrain trick applied to closed polygon outline. For each edge, split at a point between 1/4 and 3/4 of its length, displace perpendicularly by `±A · iteration_scale^k`, recurse.

**Pros.** O(N log N), deterministic with seeded RNG, produces target-able fractal dimension (H exponent: `D = 2 − H`; `H = 0.5` → `D ≈ 1.5`, Norway-like).
**Cons.** Self-intersection at high iteration counts requires repair. Doesn't create separate islands — just crinkles the existing boundary.
**Complexity:** 2.

Reference: [Fractal Coastlines (thingonitsown)](http://thingonitsown.blogspot.com/2018/12/fractal-coastlines.html)

## §3 — Sub-Plate / Archipelago Techniques

The PO's "rounded blobs" complaint is fundamentally about **boundary topology**, not just curviness. A circle with fbm noise on its boundary is still topologically a disk. Real continents have peninsulas (deep concavities) and satellite islands (separate connected components).

### 3.1 Recursive Voronoi Sub-Plates That Drift Apart

Generate 3–7 sub-plates within each macro-plate. Then **shrink each sub-cell by factor `s ∈ [0.80, 0.92]` about its centroid**. The shrunk sub-cells become land; residual inter-cell gaps become water straits.

### 3.2 Boolean Subtract Noise Channels (Fjord Carving)

After the plate polygon is rasterised to a mask, generate a low-frequency ridged-noise field. Where `ridged(x,y) > 0.78`, subtract from the mask. Ridged noise's natural curvilinear ridges become curvilinear straits that look like fjords or sounds.

### 3.3 Micro-Plate Spawning at Boundaries

Where two macro-plate boundaries meet at an angle resembling a subduction zone, spawn 2–5 micro-plates as small isolated islands offset 20–60 px on the overriding-plate side, **curved into an arc**. This is the genuine geological mechanism for the Aleutians, Japan, Indonesia, Marianas, Tonga.

### 3.4 Multi-Tier Boundary Noise (Decoupled Frequency Bands)

Add three frequency bands:
- **Lobe band** at `freq=0.6, amp=0.50`: forces 2–4 large lobes (peninsulas)
- **Base band** (current) at mid-scale
- **Cove band** at `freq=8.0, amp=0.06`: Norwegian-fjord-scale wiggles

### 3.5 Pinch-Off Subdivision (Topology-Changing)

After polygon boundary is generated, run self-intersection test: where width drops below threshold, **split the polygon into two connected components**.

## §4 — Annotated References

1. **Mandelbrot 1967, *Science* 156:636–638** — [DOI](https://www.science.org/doi/10.1126/science.156.3775.636) — foundational fractal coastline paper
2. **Iñigo Quilez — Domain Warping** — [iquilezles.org/articles/warp/](https://iquilezles.org/articles/warp/) — `q=fbm(p), r=fbm(p+4q), final=fbm(p+4r)`. Warp 4.0 sweet spot
3. **Iñigo Quilez — fbm** — [iquilezles.org/articles/fbm/](https://iquilezles.org/articles/fbm/) — H exponent and gain theory
4. **Amit Patel — Polygonal Map Generation** — [stanford.edu](http://www-cs-students.stanford.edu/~amitp/game-programming/polygon-map-generation/) — Voronoi + Lloyd + radial-sine + flood-fill
5. **Amit Patel — Making maps with noise** — [redblobgames.com/maps/terrain-from-noise](https://www.redblobgames.com/maps/terrain-from-noise/) — Square bump, octave amplitude, ridged noise
6. **Martin O'Leary — Generating Fantasy Maps** — [mewo2.com/notes/terrain/](https://mewo2.com/notes/terrain/) + [GitHub](https://github.com/mewo2/terrain)
7. **Andy Gainey — Procedural Planet Generation** — [experilous.com](http://experilous.com/1/blog/post/procedural-planet-generation) — full plate-tectonic flood-fill on geodesic sphere
8. **Lauri Viitanen — PlaTec thesis (2012)** — [theseus.fi](https://www.theseus.fi/bitstream/handle/10024/40422/Viitanen_Lauri_2012_03_30.pdf)
9. **Job Talle — Simulating Hydraulic Erosion** — [jobtalle.com](https://jobtalle.com/simulating_hydraulic_erosion.html)
10. **Fractal Coastlines (thingonitsown)** — [blogspot.com](http://thingonitsown.blogspot.com/2018/12/fractal-coastlines.html) — 131k vertices in 230 ms via recursive midpoint
11. **Azgaar — Coastline** — [azgaar.wordpress.com](https://azgaar.wordpress.com/2017/04/03/coastline/) + [Templates](https://azgaar.wordpress.com/2017/10/05/templates/)
12. **Bras&Plucky — Procedural Island Generation III** — [brashandplucky.com](https://brashandplucky.com/2025/09/17/procedural-island-generation-iii.html)
13. **Coastline paradox** — [Wikipedia](https://en.wikipedia.org/wiki/Coastline_paradox)

## §5 — Three Concrete Recommendations for Phase A v2

### Rec #1 (highest impact-per-hour): Multi-tier boundary noise + recursive midpoint displacement

**Hours:** ~1.0. **Impact:** very high.

**Sketch:** Keep current polygon abstraction. Replace single 3-octave fbm vertex perturbation with three explicit frequency bands applied as separate passes:
- **Lobe band** (peninsula creator): for each vertex at angle θ from centroid, displace radially by `0.45 · plate_radius · fbm(cos(2θ), sin(2θ), seed_lobe)`. **This single addition is what visually breaks "rounded blob" → "peninsular continent."**
- **Base band** (current behaviour): `0.20 · plate_radius · fbm₃octaves(...)`
- **Cove band**: after polygon is generated, run §2.10 midpoint displacement with 4 passes, amplitudes `[5, 3, 2, 1] px`. Vertex count rises from ~36 to ~36·2⁴ = 576; fractal dimension ≈ 1.4.

**Why this is #1.** Additive change. No new data structures. Directly attacks "boundary not curvy/lobed enough". ~80 lines diff in `flatworld.rs`.

### Rec #2 (highest topological impact): Sub-plate fragmentation + island arcs

**Hours:** ~1.5. **Impact:** very high (changes topology).

**Sketch:** Two parts.
- **(a) Sub-plate strait gaps.** Mark zones whose centroid lies in outer 35% of plate as fragmentation candidates. Shrink by `s ∈ [0.78, 0.90]`. Pick largest connected component as main plate; rest tagged `IslandFragment(plate_id)`.
- **(b) Micro-plate island arcs.** For each plate-plate boundary edge, if drift vectors converge (`v₁·n − v₂·n > 0.3`), spawn 3–5 micro-plates along a circular arc.

**Why this is #2.** Only recommendation that actually changes topology — adds disconnected islands. Slightly more invasive (needs `Plate` struct to hold optional satellite polygons).

### Rec #3 (highest realism, biggest break): Heightmap + multi-octave noise field + marching squares

**Hours:** ~2.5. **Impact:** very high but disruptive.

**Sketch:** Abandon "12 polygons" rendering abstraction. Build per-pixel `h(x, y)` scalar field at 1024×640 with domain warping + 6-octave noise + coastal boost. Then marching squares.

**Why this is #3 despite being most realistic.** Highest disruption: changes world-data type from `Vec<Polygon>` to `Mask + PlateField`. Likely breaks Voronoi zone, drainage, climate pipelines.

## §6 — Stacking strategy

- **#1 alone (~1 h)** is minimum viable visual fix — boundaries get lobes + Norwegian-fjord-scale cove detail
- **#1 + #2 (~2.5 h)** is recommended Phase A v2 deliverable — peninsulas + archipelagic fragmentation + Aleutian island arcs
- **#3** is Track 2 / Phase A v3 — file under "tracked deferral"

## §7 — Result (what actually happened next)

PO chose Rec #1 only (multi-tier noise without midpoint displacement initially).

Spike test of lobe band amp=0.80 freq=1.2 → produced visible peninsular plates (3-5 lobes each, Korea/Mediterranean-like shapes). But eval crashed -1.07 with 2 single-seed regressions of -5pt+.

PO then asked for next-level direction → Research 2 (size diversity + template approach).
