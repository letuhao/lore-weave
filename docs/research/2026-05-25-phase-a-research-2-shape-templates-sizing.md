# Research 2 — Shape Templates + Size Diversity + Azgaar FMG Pattern

**Date:** 2026-05-25 (session 59) · **Author:** general-purpose research agent · **Context:** After Research 1 + Phase A v2 spike (lobe band), PO feedback was "improvement but still circles same size, real Earth has very diverse sizes, need TEMPLATES (multiple algorithms combined), not one formula"

## §1 — Real-Earth Plate & Continent Size Statistics

### Plate area distribution (Bird 2003 catalog)

Bird's standard reference lists **52 tectonic plates** ranging from Pacific (~103.3 M km²) down to microplates of ~0.05 M km².

| Class | Count | Area range (M km²) |
|---|---|---|
| Major (>20) | 7 | 20-103 (Pacific, Africa, N.America, Eurasia, Antarctica, Australia, S.America) |
| Intermediate | ~8 | 1-20 (Nazca, India, Arabia, Philippine, Caribbean, Cocos, Scotia, Juan de Fuca) |
| Microplates | ~38 | 0.05-1 |

**Largest:smallest ratio ≈ 2000×** (Pacific 103 vs Manus microplate ~0.05). Ignoring microplates, Pacific:Juan de Fuca ≈ **413×**.

Cumulative area distribution is **well-fit by Pareto/power law**: $N(>A) \propto A^{-\alpha}$ with $\alpha \approx 0.25\text{–}0.33$ (cumulative count); PDF exponent ≈ 1.25-1.33 — **heavy-tailed, scale-free-ish**.

7 majors hold ~94% of total surface; remaining ~45 plates share last 6%. **Implication for our 12-plate generator: uniform sampling is wrong prior. Pareto / log-normal draw is what produces "one Pacific, several mediums, lots of fragments".**

References:
- Bird 2003 plate catalog: [G3 DOI](https://doi.org/10.1029/2001GC000252)
- Sornette & Pisarenko 2003 power-law fit: [GRL DOI](https://doi.org/10.1029/2002GL015043)
- Mallard et al. 2016 plate fragmentation: [Nature DOI](https://doi.org/10.1038/nature17992)

### Continental landmass distribution

| Landmass | Area (M km²) | Ratio vs largest |
|---|---|---|
| Eurasia | 54.76 | 1.00 |
| Africa | 30.37 | 0.55 |
| N. America | 24.71 | 0.45 |
| S. America | 17.84 | 0.33 |
| Antarctica | 14.20 | 0.26 |
| Australia | 7.69 | 0.14 |
| Greenland | 2.17 | 0.04 |
| New Guinea | 0.79 | 0.014 |
| Borneo | 0.74 | 0.013 |
| Madagascar | 0.59 | 0.011 |
| Baffin Is. | 0.51 | 0.009 |

Source: [Wikipedia — Islands by area](https://en.wikipedia.org/wiki/List_of_islands_by_area). Ratio of largest:12th-largest ≈ **120×**. **This is the size diversity the PO wants — log-spaced, not linearly spaced.**

### Shape factor distribution

**Fractal D** (coastline complexity, per Sapoval 1991; [Husain et al. 2021 Australia](https://doi.org/10.1038/s41598-021-86405-w)):

| Coastline | Fractal D | Class |
|---|---|---|
| South African (smooth) | 1.02 | rounded |
| Australian | 1.13 | rounded |
| Britain | 1.25 | rias |
| Norway (with fjords) | 1.52 | extreme rias |
| Greek mainland + islands | ~1.20 + archipelago | mixed |

**Compactness** (isoperimetric quotient $Q = 4\pi A / P^2$; 1 = circle, 0 = line):
- Australia ≈ 0.55 (compact)
- Africa ≈ 0.45
- Greenland ≈ 0.40
- Britain ≈ 0.15
- Italy ≈ 0.05 (peninsular)
- Indonesia (whole archipelago bbox) ≈ 0.02

**Our pre-v3.0 generator produced every plate at Q ≈ 0.75-0.85** (perturbed disks). This is the geometric fingerprint of the problem.

### Aspect ratios

Real landmasses are anisotropic: Eurasia ≈ 2.3:1 E-W, Italy ≈ 4:1 NW-SE, Chile ≈ 18:1 N-S, Japan ≈ 5:1. Our pre-v3.0 picked single `radius` scalar → isotropic by construction. **Anisotropic radius (rx ≠ ry, plus rotation) is cheapest possible step toward shape variety.**

## §2 — Shape Generation Algorithm Catalog (17 algorithms)

Each: **idea / pros / cons / complexity (1-5) / output character (peninsular/archipelagic/elongated/compact/fragmented) / implementation sketch.**

### A. Marching squares on noise field — complexity 3
Threshold 2D scalar field at $\tau$; extract closed contour polygons. Pros: **truly organic** — any topology including holes, peninsulas, isthmuses, archipelagos. Cons: produces multiple components by default; contour smoothing needed.

### B. Metaball / blob composition with smooth-min — complexity 2
Treat plate as union of N=3-7 soft disks: $f(p) = \sum_i \exp(-k\|p - c_i\|^2)$. Or use Quilez's smooth-min on signed distances: $\text{smin}(a,b,k) = -\frac{1}{k}\ln(e^{-ka} + e^{-kb})$. Produces natural Y/T/L shapes.

### C. L-systems / branching grammar — complexity 4
Stochastic L-system generates branching skeleton; **inflate** by Minkowski sum with disk. Yields **peninsular / fjord-like** shapes neither noise nor blobs can. Reference: [Prusinkiewicz-Lindenmayer ABoP](http://algorithmicbotany.org/papers/abop/abop.pdf).

### D. Signed Distance Field (SDF) operations — complexity 3
General framework. Define each plate as SDF, compose: $\text{union} = \min(a, b)$, $\text{intersect} = \max(a,b)$, $\text{difference} = \max(a,-b)$, $\text{smin}$ for smooth blends. Reference: [Quilez 2D SDFs](https://iquilezles.org/articles/distfunctions2d/).

### E. Voronoi-based blob composition — complexity 3
Drop M points, build Voronoi, take union of K cells nearest plate centre. Produces angular polygonal fragmented shapes. Requires polygon-union code (Vatti / Greiner-Hormann).

### F. Random walk / agent-based growth — complexity 2
Start agents at centre, step in random direction, paint disk at each tick. With branching, produces dendritic shapes.

### G. Diffusion-Limited Aggregation (DLA) — complexity 3
Witten & Sander 1981: place seed, release particles that walk until touching cluster. **D ≈ 1.71** in 2D. Reference: [Witten-Sander 1981 PRL](https://doi.org/10.1103/PhysRevLett.47.1400).

### H. Boids / flocking aggregation — complexity 4
Reynolds 1987 swarm rules; "land" sticks where agents linger. Reference: [Reynolds 1987](https://www.red3d.com/cwr/papers/1987/SIGGRAPH87.pdf).

### I. Convex hull of biased point cloud — complexity 1
Sample N=20-40 points in anisotropic Gaussian; take convex hull (Graham scan, O(N log N)); smooth with Chaikin. Trivial; gives convex irregular shapes. Always convex (no peninsulas/bays).

### J. Heightmap intersection (sea-level threshold) — complexity 2
Same as A but framed as "build elevation pass first, derive land mask second". Identical algorithm in different framings.

### K. Reaction-diffusion / Turing patterns — complexity 4
Gray-Scott equations: spots / stripes / labyrinths depending on (F, k) params. Reference: [Pearson 1993](https://doi.org/10.1126/science.261.5118.189).

### L. Recursive midpoint displacement — complexity 1
Fournier-Fussell-Carpenter 1982 1D fractal. Reference: [CACM DOI](https://dl.acm.org/doi/10.1145/358523.358553). **High-leverage post-process for every template.** Converts any smooth base into fractal coast with tunable D = 2 - H.

### M. Spline outline (Bezier / Catmull-Rom) — complexity 2
Pick K=5-9 control points around centre with biased angular spacing + radial jitter; fit closed Catmull-Rom spline. Smooth controllable curves; "Madagascar" / "Sri Lanka" smooth-blob look.

### N. Cellular automaton growth — complexity 2
Start with seed cell; iterate Conway-like rule. With asymmetric rules, get elongated/peninsular shapes. Reference: [RogueBasin CA](http://www.roguebasin.com/index.php/Cellular_Automata_Method_for_Generating_Random_Cave-Like_Levels).

### O. Voronoi relaxation + drainage carving — complexity 4
Build Voronoi, Lloyd-relax, then **erode** along drainage network (D8 flow accumulation — already in our `hydrology.rs`), removing cells along thalwegs to carve fjord-like inlets.

### P. Stamp composition — complexity 2
Pre-build library of 20-30 hand-designed "stamp" polygons; pick base + composite stamps via polygon union. Mirrors how Azgaar's fmg works. Reference: `geo-booleanop` crate.

### Q. Alpha shapes — complexity 3
Edelsbrunner et al. 1983: generalization of convex hull admitting concavities controlled by α. Reference: [IEEE TIT DOI](https://doi.org/10.1109/TIT.1983.1056714).

## §3 — Template-Based PCG Patterns

### Azgaar Fantasy Map Generator (FMG) — THE canonical reference

[Azgaar/Fantasy-Map-Generator](https://github.com/Azgaar/Fantasy-Map-Generator) — since 2017 — has done *exactly* the template-based approach the PO is asking for.

5 templates × Hill/Pit/Range/Trough/Strait primitives:

| Template | Primitive recipe | Output |
|---|---|---|
| Volcano | Hill ×3 large | Circular high island |
| High Island | Hill ×4 + Pit ×3 + Range + Trough | Mountainous continent |
| Low Island | Hill ×6 + Range ×2 + Pit + Trough ×3 | Low-relief continent |
| Continents | Hill ×30 small + Strait + Range + Pit | Two continents + strait |
| Archipelago | Hill ×35 + Strait ×2 + Pit + Trough ×3 | Scattered islands |
| Atoll | Hill ring + Pit centre | Ring shape |

Each primitive is a Gaussian-soft brush on a heightfield; **threshold at sea level = coast**.

Source: [heightmap-generator.js](https://github.com/Azgaar/Fantasy-Map-Generator/blob/master/modules/heightmap-generator.js).

### Other published taxonomies

- **Red Blob Games** "Polygonal Map Generation" — radial / square / blob / perlin shape modes as starting "island shape" function
- **mewo2 terrain notebook** — Voronoi + erosion, shape control via slope vectors and noise primitives
- **Caves of Qud** GDC talk by Jason Grinblat — composable world-builder steps
- **Spelunky** room templates (Yu, *Spelunky*, Boss Fight Books, 2016)
- **Brogue** dungeon machines (Brogue source code, `Architect.c`)
- **Wave Function Collapse** (Gumin 2016) — constraint-driven tile combinations

### Composition operators

- **SDF smooth-union** (Quilez): $\text{smin}_k(a,b) = -\frac{1}{k}\log(e^{-ka} + e^{-kb})$
- **Alpha blending of masks**: $M = \alpha \cdot A + (1-\alpha) \cdot B$ then threshold
- **Priority Voronoi**: per-pixel assigned to highest-priority overlapping algorithm
- **Hybrid per-plate**: pick template T with weighted probability; optionally blend two templates with weight $w \in [0,1]$

### Conditional / context-aware template selection

Once templates exist, pick them by **location** (climate pipeline gives lat/lon):
- Polar latitudes → "IceShield" template; skip Archipelago
- Equatorial → "Archipelago" or "PeninsularContinent" likelier
- Plates near other large plates → "ContinentalCore"; lone plates over ocean → "VolcanicArc"

## §4 — Size Diversity Techniques

### Pareto draw

```rust
u = rng.next_f32()                        // U(0,1)
r = r_min * (1.0 - u).powf(-1.0/alpha)   // Pareto(α)
r = r.clamp(r_min, r_max)                 // truncate
```

With $\alpha = 1.5$, $r_{\min} = 0.30 \cdot \text{pitch}$, $r_{\max} = 2.5 \cdot \text{pitch}$: ~60% of plates fall in [0.30, 0.50]·pitch (small), ~25% in [0.50, 1.0] (medium), ~15% in [1.0, 2.5] (large).

### Hierarchical assignment (deterministic ranks)

Instead of sampling each radius independently, **pre-assign size ranks**: 1 giant + 2 large + 4 medium + 5 small. More controllable than blind Pareto.

For 12 plates:

| Rank | Count | Radius band (× pitch) | Earth analog |
|---|---|---|---|
| Giant | 1 | [1.6, 2.4] | Eurasia/Pacific |
| Large | 2 | [1.0, 1.4] | Africa, N.America |
| Medium | 4 | [0.6, 0.9] | Australia, Antarctica |
| Small | 5 | [0.3, 0.55] | Greenland, microplates |

### Cluster + offspring (microplate generation)

After placing K main plates, for each "large" plate add 1-3 **microplates** within `0.5·R_parent` to `1.5·R_parent` of its border. These are the Juan de Fuca / Philippine Sea / Caribbean small plates.

### Two-pass tiling

**Pass 1**: place giants/larges with strong min-separation. **Pass 2**: fill remaining voids (Poisson-disc sampler, seeded only in uncovered regions). Cleanest way to get Earth distribution.

## §5 — Composition & Blending Architecture

**Option α: per-plate template only** (simplest, recommended for v3). Each plate independently picks ONE template + parameters.

**Option β: master heightfield + multi-template stamps** (more like Azgaar). Build one 1024×640 heightfield; each plate is recipe of stamps. **Loses per-plate `vertices` SSOT** → major surgery.

**Option γ: per-plate raster → polygon extraction** (sweet spot). Each plate builds own 256×256 mask; marching-squares extracts polygons. `Plate.vertices` becomes `Plate.components: Vec<Polygon>`. **This is what v3.0 architected for.**

## §6 — Proposed 7-Template Taxonomy

| Type | Real-Earth analog | Primary algorithm | Size (× pitch) | Visual signature |
|---|---|---|---|---|
| **CratonicCore** | Africa, Australia, S.America | M (Catmull-Rom spline) + L (midpoint displacement, low H≈0.5) | 1.2 - 2.4 | Smooth compact continent, slightly fractal coast, Q ≈ 0.4-0.5 |
| **RiftedContinent** | Eurasia (E-W), N.America | B (3-blob smooth-min, elongated) + L | 1.0 - 2.0 | Elongated 2:1 to 3:1, multi-lobed |
| **PeninsularBlock** | India, Italy, Scandinavia, Korea | I (convex hull) + C (3-iter L-system finger) + L | 0.6 - 1.2 | Compact body with 1-3 large fingers; Q ≈ 0.15-0.30 |
| **IslandArc** | Japan, Aleutians, Indonesia-Java arc | Arc skeleton + I per node + L | 0.5 - 1.0 | 3-7 elongated components along curved spine |
| **Archipelago** | Indonesia, Philippines, Aegean | A (marching squares on fbm + radial falloff) | 0.8 - 1.6 | 5-30 disjoint components |
| **MicroBlock** | Juan de Fuca, Scotia, Caribbean | I (convex hull, no anisotropy) + L (low) | 0.2 - 0.4 | Tiny compact polygon |
| **FjordCoast** | Norway, Chile, Greenland | M (smooth base) + L (HIGH H≈0.8) D≈1.5 | 0.8 - 1.5 | Compact body but very ragged ria coast |

**Rationale for 7:**
- Covers shape modes PO listed (peninsular, archipelagic, elongated, compact, arc, fragmented, fjord-coast)
- All seven can be implemented with primitives we have or with thin additions
- Default distribution for 12 plates: 1 Cratonic + 1 Rifted + 2 Peninsular + 1 IslandArc + 1 Archipelago + 4 MicroBlock + 2 FjordCoast

## §7 — Top 3 Phase A v3 Recommendations

### Rec #1 — Template Dispatcher v1 (★★★★☆ visual, risk 2/5) — RECOMMENDED FIRST

Extract per-plate polygon code into new module `crates/world-gen/src/plate_shape.rs`. Define `enum PlateTemplate { CratonicCore, RiftedContinent, ... }` and `fn build(template, center, size_radius, rng, salt) -> Vec<(f32,f32)>`. Implement **only 3 templates** in v1: `CratonicCore`, `PeninsularBlock`, `FjordCoast`.

Add `enum SizeRank { Giant, Large, Medium, Small, Micro }` and deterministic rank assignment.

**Hours**: 3-4. **Risk**: 2/5. **Files**: NEW `plate_shape.rs`; MODIFY `flatworld.rs`, `lib.rs`, `examples/flatworld.rs`.

### Rec #2 — Multi-Component Plates via Marching Squares (★★★★★ visual, risk 4/5) — RECOMMENDED SECOND

Extend `Plate` to `pub primary_polygon: Polygon` and `pub satellites: Vec<Polygon>`. Build per-plate raster generation: 128×128 scalar field with $f(u,v) = \text{fbm}(u,v) - \alpha \cdot d(u,v)$. Threshold + marching squares + Chaikin smoothing.

Wire `Archipelago` and `ContinentalShelf` (low $\alpha$, multiple components) templates.

**Hours**: 4-6. **Risk**: 4/5 — touches Plate struct, marching-squares can produce degenerate polygons. **Files**: NEW `marching.rs`; MODIFY `flatworld.rs`, `render.rs`, `world_map.rs`, `flat_climate.rs`, `hydrology.rs`.

### Rec #3 — Pareto Sizing + Anisotropic Disks (★★★☆☆ visual, risk 1/5) — RECOMMENDED ZEROTH

Minimal change. Two edits to `flatworld::generate`:

1. **Replace uniform radius with Pareto**: `let r = r_min * (1.0 - rng.next_f32()).powf(-1.0/alpha);`
2. **Anisotropic radius (rx, ry, rotation θ)**: `rx = r * sqrt(aspect); ry = r / sqrt(aspect); aspect ∈ [1.0, 3.0]`

Gives **size diversity** + breaks **isotropy** in a single afternoon's work, **without** structural change. Buys visual evidence to justify the bigger #1 refactor.

**Hours**: 1-2. **Risk**: 1/5. **Files**: `flatworld.rs` only.

### Suggested phasing

| Phase | What | Hours | Cumulative impact |
|---|---|---|---|
| **A v3.0** | Rec #3 — Pareto + anisotropy | 1-2 | Size diversity ✓, no shape diversity yet |
| **A v3.1** | Rec #1 — 3-template dispatcher | 3-4 | Three visibly different shape modes |
| **A v3.2** | Rec #1 — add remaining 4 templates | 3-4 | Full 7-template taxonomy on `Vec<(f32,f32)>` |
| **A v3.3** | Rec #2 — multi-component archipelagos | 4-6 | True Indonesia/Aegean output; schema change |

Total ~12-16 h spread across 4 iterations.

## §8 — Key Tradeoffs

- **`Vec<(f32,f32)>` SSOT vs raster pipeline**: Recs #1 + #3 keep polygon SSOT. Rec #2 breaks out to raster + marching-squares — "real" path forward but structural change.
- **Determinism + climate-eval stability**: every change should be **calibrated to preserve $\mathbb{E}[\text{land area}]$** within a few percent.
- **Polygon Boolean ops**: if Rec #2 ever wants true polygon union, pull in `geo-booleanop` crate (MIT licensed, Greiner-Hormann). Don't roll your own Vatti.
- **Stamp libraries**: not in top-3 because authoring 20-30 hand-designed stamps is 6-10h investment with marginal payoff over good 7-template dispatcher. Defer until v4+.

## §9 — Result (what actually happened next)

PO chose **full v3.0-v3.3 roadmap + schema refactor in v3.0**.

v3.0 SHIPPED (commit f022cf82):
- Schema: `Plate.vertices` → `Plate.components: Vec<Polygon>` + `primary()` / `bounding_box()` helpers
- `SizeRank` enum with calibrated bands (Giant 1.0-1.2 → Micro 0.15-0.22, ~6× ratio)
- Deterministic 12-plate distribution: 1 Giant + 2 Large + 3 Medium + 4 Small + 2 Micro
- Anisotropic (rx, ry, theta_rot) ellipsoidal vertex generation
- `shape_seed` reserved for v3.1 template dispatcher
- Eval framework: continentality `abs(h_coast - h_int)` + DELTA_TARGET 2.0 → 1.0 (size-diverse worlds produce smaller deltas)
- New v5.2 baseline: 85.24 (was 89.30 pre-v3.0)

PO then asked: "still oval shapes — what about S, sock, hook, ring? What algorithms do other games use?" → Research 3.

## Citations Summary

- Bird 2003 plate catalog: [G3 DOI](https://doi.org/10.1029/2001GC000252)
- Sornette & Pisarenko 2003: [GRL DOI](https://doi.org/10.1029/2002GL015043)
- Mallard et al. 2016: [Nature DOI](https://doi.org/10.1038/nature17992)
- Mandelbrot 1967 coastline: [Science DOI](https://doi.org/10.1126/science.156.3775.636)
- Fournier-Fussell-Carpenter 1982 midpoint displacement: [CACM DOI](https://dl.acm.org/doi/10.1145/358523.358553)
- Quilez SDF / smooth-min: [iquilezles.org](https://iquilezles.org/articles/distfunctions2d/) + [smin](https://iquilezles.org/articles/smin/)
- Lorensen-Cline 1987 marching cubes: [ACM DOI](https://dl.acm.org/doi/10.1145/37402.37422)
- Witten-Sander 1981 DLA: [PRL DOI](https://doi.org/10.1103/PhysRevLett.47.1400)
- Prusinkiewicz-Lindenmayer 1990 L-systems: [ABoP PDF](http://algorithmicbotany.org/papers/abop/abop.pdf)
- Reynolds 1987 boids: [SIGGRAPH PDF](https://www.red3d.com/cwr/papers/1987/SIGGRAPH87.pdf)
- Pearson 1993 Gray-Scott: [Science DOI](https://doi.org/10.1126/science.261.5118.189)
- Gumin 2016 WFC: [GitHub](https://github.com/mxgmn/WaveFunctionCollapse)
- **Azgaar FMG (THE reference for plate templates)**: [GitHub](https://github.com/Azgaar/Fantasy-Map-Generator) + [heightmap blog](https://azgaar.wordpress.com/2017/12/29/heightmap-generator/)
- Red Blob Games polygonal map: [redblobgames.com](https://www.redblobgames.com/maps/mapgen2/)
- mewo2 terrain notes: [mewo2.com](https://mewo2.com/notes/terrain/)
- Caves of Qud GDC: [YouTube](https://www.youtube.com/watch?v=jV-DZqdKlnE)
- Roguebasin CA: [roguebasin.com](http://www.roguebasin.com/index.php/Cellular_Automata_Method_for_Generating_Random_Cave-Like_Levels)
- `geo-booleanop` crate: [crates.io](https://crates.io/crates/geo-booleanop)
