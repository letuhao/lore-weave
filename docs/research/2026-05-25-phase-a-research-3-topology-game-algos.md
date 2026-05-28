# Research 3 — Topology-Specific Algorithms + Game Industry References

**Date:** 2026-05-25 (session 59) · **Author:** general-purpose research agent · **Context:** After Phase A v3.0 shipped (Pareto sizing + anisotropy), PO feedback was: "still oval shapes — what about S-shapes, sock shapes, hooks, rings? How do other games use geometric algorithms?"

## §1 — Shape Algorithms Producing Specific Topology

Twelve algorithms, ranked by topological expressiveness. Each grounded in a real-game or seminal-paper reference.

### A1. Bézier / Catmull-Rom **spine + uniform thickness** (offset curve)

**Idea.** Author 1-D parametric curve C(t) via 3–5 control points; sweep disk of radius r along C(t) (Minkowski sum) to obtain 2-D polygon. Tiller-Hanson polygon-offset method or Gabriel Suchowolski's selective-subdivision quadratic offset are canonical numerical approaches.

**Topology.** S-curves (3-point), hooks (1 bent control), boots/L-shapes (sharp corner), U-shapes — depending solely on control polygon. Earth analog: Norwegian coast (S), Florida (hook), Italy minus heel (boot core).

**Pros.** Single primitive yields entire family `S | U | C | hook | L`; easy to bend with one parameter (interior angle); deterministic.
**Cons.** Constant thickness looks artificial unless tapered r along t. Cusps when curvature radius < r.
**Complexity.** 2–3.

References: [Aurimas Gasiulis cubic Bézier offsetting](https://gasiulis.name/cubic-curve-offsetting/), [Hoschek 1993 variable-radius offset](https://www.sciencedirect.com/science/article/abs/pii/001044859390010L)

### A2. **SDF capsule chain + smooth-min** (Iñigo Quilez)

**Idea.** Define plate as `sdf(p) = smin_k( capsule(p, A0, A1, r0), capsule(p, A1, A2, r1), ... )`. Quilez's quadratic-polynomial smin produces clay-like smooth unions. Rasterize to grid then marching-squares the 0-isoline.

**Topology.** Chain of 3 capsules at 120° = Y branch (Africa). 4 capsules in zigzag = S/Z (S. America). 4 capsules in closed loop = ring (atoll). Earth analog: Sulawesi (4-arm spider), Aleutian arc.

**Pros.** Single SDF expression yields ANY topology; smooth blending hides joints.
**Cons.** Requires raster→polygon step; higher CPU than direct polygon generation.
**Complexity.** 3.

References: [Quilez smin](https://iquilezles.org/articles/smin/), [Quilez 2D SDFs](https://iquilezles.org/articles/distfunctions2d/)

### A3. **Skeleton / medial-axis inverse** with per-arm thickness

**Idea.** Define plate as graph G (nodes + edges) of skeletal segments. Each edge is thick line segment. Union them all.

**Topology.** Choose graph topology = choose plate topology. 3-node star = Y. 4-node cross = +. 5-node = pentagonal hub.

**Pros.** Topology authored as tiny adjacency list — extremely controllable.
**Cons.** Polygon union requires polygon clipping; junctions can produce artifacts at acute angles.
**Complexity.** 4 (union math) or 2 if rendered via SDF.

References: [CGAL Straight Skeleton Extrusion](https://doc.cgal.org/latest/Straight_skeleton_2/group__PkgStraightSkeleton2Extrusion.html)

### A4. **Persistent random walk + brush** (correlated brownian)

**Idea.** Start at origin, take N steps; each step direction = previous + small angular jitter (persistence p ∈ [0.8, 0.99]). Paint disk at every visited cell, then marching-squares.

**Topology.** High persistence → elongated worm. Low persistence → blob. Self-intersecting walk → ring or figure-8.
**Pros.** Stochastically generates highly varied shapes; one knob.
**Cons.** Topology emergent (not directly controlled).
**Complexity.** 2.

### A5. **L-system grammar producing letter-like shapes**

**Idea.** Lindenmayer rewrite rules: `F → F[+F][-F]` (binary branching). Run for depth d, then thicken each segment.

**Topology.** Depth-1 = single line, depth-2 = Y, depth-3 = bushy. Earth analog: trees, river basins (Amazon delta), highly-branched coastlines (Norway).
**Pros.** Recursive branching emerges naturally.
**Cons.** Rarely produces compact-blob shapes (always tree-like).
**Complexity.** 3.

### A6. **Boolean polygon operations** (constructive solid geometry, 2-D)

**Idea.** `plate = ellipse_A UNION ellipse_B DIFFERENCE ellipse_C`. Use `geo-clipper` or `i_overlay` Rust crates for CSG on polygons.

**Topology.** Boot = ellipse minus wedge. Crescent = circle minus offset circle. Ring = circle minus inner circle.
**Pros.** Extremely intuitive ("Italy = leg ∪ heel ∪ toe"); composes well with stamp libraries.
**Cons.** Requires polygon-clipping dep; can produce holes — our current SSOT `components: Vec<Polygon>` actually supports this.
**Complexity.** 3 (with crate) / 5 (rolling your own).

References: [Chazelle convex decomposition](https://dl.acm.org/doi/pdf/10.1145/357346.357348)

### A7. **Polar function r(θ) — superformula / rose curve / cardioid**

**Idea.** Define boundary in polar form `r(θ) = f(θ)`. Gielis (2003) superformula unifies superellipses/circles/triangles/stars/flowers in 6-parameter equation:

```
r(θ) = ( |cos(mθ/4)/a|^n2 + |sin(mθ/4)/b|^n3 )^(-1/n1)
```

**Topology.** m=3, n=high → triangle. m=5 → pentagon-star. m=2, n1≠n2 → oval. Cardioid `r = a(1+cos θ)` → heart. Rose `r = cos(nθ)` → n-petal flower.
**Pros.** ONE formula generates 5+ topologies; deterministic; fast.
**Cons.** All produce ROTATIONALLY symmetric — cannot make Italy or S-curve. Strictly star-shaped.
**Complexity.** 1.

References: [Superformula Wikipedia](https://en.wikipedia.org/wiki/Superformula)

### A8. **Variable-radius offset along spine** (extension of A1)

**Idea.** Same as A1 but `r(t)` is function of arc-length: `r(t) = r0·(1 - β·t²)` tapers the end into a peninsula.

**Topology.** Same as A1 plus tapering tips (Italy's toe, Florida's tip).
**Complexity.** 3.

References: [Hoschek 1993 PDF](https://www.sciencedirect.com/science/article/abs/pii/001044859390010L)

### A9. **Parametric arc + thickness** (special case of A1 with circular spine)

**Idea.** Spine is arc of a circle: `C(t) = center + R·(cos(θ0+t·Δθ), sin(θ0+t·Δθ))`, thickness r.

**Topology.** Crescent (Cuba, Aleutian arc, Japan, Sumatra-Java).
**Complexity.** 1.

### A10. **Stamp composition** (Diablo II / Spelunky / Caves of Qud school)

**Idea.** Pre-author ~20 shape "stamps" (sock, S, hook, boot…), each stored as base polygon. At gen time, select stamp by template tag, apply random rotation/mirror/scale/noise.

Diablo II builds caves from 95 pre-authored "presets". Spelunky uses 10×8 character grid templates with randomization chunks.

**Topology.** Whatever you authored.
**Pros.** Maximum visual control, predictable output.
**Cons.** Requires authoring effort (~1 hr per stamp).
**Complexity.** 2.

References: [Reverse Design: Diablo 2 — Randomness](http://thegamedesignforum.com/features/RD_D2_5.html), [Spelunky room templates](https://ems.andrew.cmu.edu/2014_60210a/maj/08/27/technological-artdesign-spelunky/index.html)

### A11. **Diffusion-Limited Aggregation (DLA)** with seed-shape constraint

**Idea.** Brownian particles random-walk until they touch existing aggregate; sticks. Witten-Sander 1981. Produces branching dendritic fractals (D ≈ 1.71).

**Topology.** Fractal branching coastlines (extreme fjords/Norway-like).
**Complexity.** 4.

### A12. **Wave Function Collapse on coarse tile grid** (Townscaper / Bad North)

**Idea.** Author ~16 tile types with adjacency rules. WFC fills n×n grid such that all neighbor constraints hold.

**Topology.** Whatever the tile-set encodes — extremely flexible but tile-design-bound.
**Pros.** Industry-proven (Townscaper, Bad North, Caves of Qud).
**Cons.** Highest implementation cost; produces tile-aligned shapes unless post-smoothed.
**Complexity.** 5.

References: [Bad North WFC talk — Stalberg EPC2018](https://www.youtube.com/watch?v=0bcZb-SsnrA), [Townscaper](https://www.gamedeveloper.com/game-platforms/how-townscaper-works-a-story-four-games-in-the-making), [WFC repo](https://github.com/mxgmn/WaveFunctionCollapse)

## §2 — Games & Their Algorithms (20 references)

| # | Game | Algorithm | Topology output | Source |
|---|------|-----------|-----------------|--------|
| 1 | **Civilization V/VI Continents** | Fractal noise + rejection (largest ≤64%) | Compact blobs with rifts | [CivFanatics blend script](https://forums.civfanatics.com/threads/map-script-request-blend-of-continents-and-fractal.654286/) |
| 2 | **Civilization V Pangaea** | Same fractal + rejection (largest ≥84%) | One giant blob | [Map (Civ5) wiki](https://civilization.fandom.com/wiki/Map_(Civ5)) |
| 3 | **Civilization VII** (2024) | Rebuilt map gen pipeline | Multi-pass shaping | [Civ VII From Devs](https://civilization.2k.com/civ-vii/from-the-devs/map-generation/) |
| 4 | **Dwarf Fortress** | Midpoint displacement on elev/rain/temp/drainage/volcanism/wildness grids → smoothing → simulated rivers → rain-shadow pass → biome classification → rejection sampling | Realistic continents w/ mountain ridges, rivers, biomes | [DF wiki](https://dwarffortresswiki.org/index.php/DF2014:World_generation), [GDC 2016 Tarn Adams](https://www.gdcvault.com/play/1023372/Practices-in-Procedural) |
| 5 | **No Man's Sky** | Voxel-based terrain on sphere → polygonization → biome passes | Spherical planet w/ infinite variety | [GDC NMS Continuous World](https://www.gdcvault.com/play/1024265/Continuous_World_Generation_in__No_Man_s_Sky_), [GDC Building Worlds Math](https://www.gdcvault.com/play/1024514/Building-Worlds-Using) |
| 6 | **Stellaris** | Parametric: spiral arms / ellipse / annulus. Star count 200–1000 | Galaxy shapes | [Paradox Dev Diary #3](https://forum.paradoxplaza.com/forum/threads/stellaris-dev-diary-3-galaxy-generation.885267/) |
| 7 | **Minecraft 1.18+** | 6-param 3D climate noise (continentalness, erosion, weirdness, humidity, temperature, depth); quarter-chunks classified by nearest-biome | Biome regions from noise-space partitioning | [Minecraft Wiki](https://minecraft.wiki/w/World_generation), [Henrik Kniberg talk](https://www.youtube.com/watch?v=ob3VwY4JyzE) |
| 8 | **Caves of Qud** | Hybrid: pre-made towns + WFC + procedural wilderness; layered "brush" passes | Mixed authored + procedural | [GDC 2019 Grinblat](https://www.gdcvault.com/play/1026313/Math-for-Game-Developers-End), [Roguelike Celebration Bucklew WFC](https://www.youtube.com/watch?v=jV-DZqdKlnE) |
| 9 | **Brogue** | Room accretion: 4 room generators (rect overlap, CA blob, single circle, multi-circle); "machines" re-run on existing room | Tree-rooted dungeons | [Anderoonies generation pt 1](http://anderoonies.github.io/2020/03/17/brogue-generation.html), [pt 2](http://anderoonies.github.io/2020/04/07/brogue-generation-2.html) |
| 10 | **Spelunky** | 4×4 grid → solution path → templates per cell + wildcard chunks | Authored-feel platformer | [Derek Yu Spelunky book](https://bossfightbooks.com/products/spelunky-by-derek-yu), [CMU EMS analysis](https://ems.andrew.cmu.edu/2014_60210a/maj/08/27/technological-artdesign-spelunky/index.html) |
| 11 | **Townscaper** | Irregular relaxed quad grid (hex→quad split + relaxation) + WFC + marching cubes | Organic city blocks on islands | [Stalberg IndieCade 2019](https://www.youtube.com/watch?v=1hqt8JkYRdI) |
| 12 | **Bad North** | WFC on triangle+quad island grid, custom observation heuristic | Crescent/curved-beach islands | [EPC2018 Stalberg](https://www.youtube.com/watch?v=0bcZb-SsnrA) |
| 13 | **Diablo II** | "Presets" — pre-made room/chunk library (95 cave presets in Act I), assembled by deck-draw | Random dungeons feeling authored | [Game Design Forum RD D2](http://thegamedesignforum.com/features/RD_D2_5.html) |
| 14 | **Songs of Conquest** | JSON-authored "layouts" telling generator which regions to spawn and connect; configurable region size/difficulty | Adventure maps | [SoC RMG modding](https://www.songsofconquest.com/modding/rmg) |
| 15 | **Endless Legend / Humankind** | Tile-based with regions; resource-spawn iterates regions and biases by listing order | Region-bound continents | [Amplitude World Gen Custom](https://community.amplitude-studios.com/amplitude-studios/endless-legend/blogs/708-community-spotlight-5-world-generator-full-customization-by-enchanteur) |
| 16 | **RimWorld** | Hex tiles with 12 pentagons (icosahedron-derived sphere); per-tile biome/elevation noise | Per-tile climate | [RimWorld Wiki](https://rimworldwiki.com/wiki/World_generation) |
| 17 | **Spore** | **Spine-and-segment creature gen: variable spine length, per-segment thickness, drag-drop parts — EXACTLY §1.A1 spine approach applied to creatures** | Arbitrary creature topology | [ETC CMU PDF](https://press.etc.cmu.edu/file/download/835/9a5bceac-2665-4da1-821c-556947c9e3f3), [MIT Tech Review on Spore](https://www.technologyreview.com/2008/06/17/127401/creating-creatures/) |
| 18 | **Red Blob Games map gen** (reference) | Voronoi+Lloyd relaxation; shape-from-distance + reshape functions (Square Bump + Smooth) | Continental-scale | [Amit Patel polygon](http://www-cs-students.stanford.edu/~amitp/game-programming/polygon-map-generation/), [Island shaping 2022](https://simblob.blogspot.com/2022/04/improving-island-shaping-for-map.html) |
| 19 | **PlaTec / Procedural Tectonic Planets** (academic) | Plate tectonics simulation: split fractal into Voronoi plates → simulate drift/collision → erode | Realistic continents w/ mountain belts | [Viitanen 2012 PlaTec PDF](https://www.theseus.fi/bitstream/handle/10024/40422/Viitanen_Lauri_2012_03_30.pdf), [Cortial et al. 2019](https://hal.science/hal-02136820/file/2019-Procedural-Tectonic-Planets.pdf) |
| 20 | **Cauliflower Labs Geology Simulator** (indie ref) | Educational plate-tectonics implementation | Continent drift | [Geology Simulator blog](http://cauliflowerlabs.blogspot.com/2014/10/geology-simulator-plate-tectonics.html) |

### Key Finding: Even Civ V/VI use the same algorithm we did (noise + rejection)

Going beyond requires either:
- **Wave Function Collapse** (Bad North/Townscaper/Qud) — tile-based, smoothed
- **Tectonic simulation** (PlaTec, Cortial 2019) — physical model
- **Authored stamps** (Diablo II/Spelunky/Songs of Conquest school) — hybrid hand+procedural

## §3 — Best Algorithm Per Topology (PO's Examples)

| Topology | Best algo | Why | Rust sketch | LOC | SSOT? |
|----------|-----------|-----|-------------|-----|-------|
| **Oval/blob** (Australia) | A7 superformula OR current ellipse+fbm | Closed-form, already shipped | `r(θ) = ellipse·perturb(fbm)` | 0 (have it) | yes |
| **S-curve** (S. America, Norway) | **A1 Bézier spine + thickness** | One curve, two control bends; tapered radius | spine = 4 ctrl pts in S; offset by r(t)=r0·(1-0.3·t²); fbm-perturb ring | ~120 | yes |
| **Sock/L/boot** (Italy) | **A1 with one sharp control angle** OR A6 boolean (ellipse ∪ ellipse) | Italy = 1 spine bent 110° + offset; OR leg ∪ heel ∪ toe | A1 with 3 ctrl pts; thicken with `r(t)=lerp(big,small,t²)` | ~120 | yes |
| **Hook** (Korea, Florida, Cape Cod) | **A1 with 1 control bend, asymmetric taper** | Single-curve hook; tip tapers | 3 ctrl pts (root, elbow, tip); `r(t)=lerp(r0,0.2·r0,t)` | ~120 | yes |
| **Y/T-branching** (Africa horn) | **A3 skeleton** (3 nodes) OR **A2 capsule chain w/ branch** | True branching is multi-arm | skeleton with 3 edges meeting at hub; per-arm radius; render via A2 SDF or polygon union | ~250 | yes (1 component) |
| **Crescent/Arc** (Cuba, Aleutians, Java) | **A9 parametric arc + thickness** OR A1 with arc spine | Closed-form crescent | spine = circle arc R, θ0→θ1, thickness r; cap ends; fbm | ~80 | yes |
| **Ring/atoll** | **A6 annulus** = disk − inner disk | One subtraction call | `outer_circle.difference(inner_circle)` via geo-clipper | ~50 | needs `components: Vec<Polygon>` outer ring (yes — have it) |
| **Cross/+** (rare Indonesian) | **A3 skeleton** (4 nodes radial) OR A7 rose `r=cos(2θ)` | Skeleton = full control; rose = quick approximation | 4 capsules from center | ~150 | yes |
| **Crab/spider** (Sulawesi) | **A3 skeleton** with 4–6 limbs OR **A2 capsule chain** | Multi-limb = multi-arm skeleton | center hub + 4–6 random-angle arms; per-arm length+taper | ~200 | yes |
| **Archipelago** (Indonesia) | **A11 DLA** or current **multi-component marching-squares** | Multi-component is built into our schema | seed N centers; for each, A1 small spine | ~100 | yes — already `Vec<Polygon> components` |

**Key insight: A1 (Bézier spine + thickness) alone covers 5 of 10 topologies. That's the highest-leverage primitive.**

## §4 — Unified 8-Template Taxonomy for v3.1+

Refined from PO list. Each template uses single dominant primitive plus shared post-passes (fbm boundary noise, size-rank scaling).

| # | Name | Algorithm | Topology | Earth analog | Complexity | Est. hours |
|---|------|-----------|----------|--------------|------------|-----------|
| 1 | **CompactCore** | current ellipse+fbm | oval blob | Australia | 1 | 0 (shipped) |
| 2 | **CurvedContinent** | A1 Bézier spine + thickness (3 ctrl, gentle S) | S-curve | S.America, Norway coast | 3 | 6h |
| 3 | **PeninsularBoot** | A1 with sharp interior angle + tapered tip | sock/L/boot | Italy, Korea | 3 | shared w/ #2 (param sweep) |
| 4 | **HookedPeninsula** | A1 with single bend, asymmetric taper | hook | Florida, Cape Cod | 2 | shared w/ #2 |
| 5 | **IslandArc** | A9 parametric arc + thickness (or A1 w/ circular spine) | crescent | Aleutians, Java, Cuba | 2 | 3h |
| 6 | **RingAtoll** | A6 annulus (geo-clipper) | ring | Atoll, Bikini | 2 | 3h + crate dep |
| 7 | **BranchedContinent** | A3 skeleton, 3–4 arms, render via A2 capsule SDF + smin + marching-squares | Y/T/+ branching | Africa with horn, Sulawesi | 4 | 10h |
| 8 | **Archipelago** | Multi-component: 5–9 small A1 or A7 shapes scattered | multi-component | Indonesia, Philippines | 3 | 4h |

**Total new work:** ~26 hours (single dev, full TDD).

Templates 2–4 are all **the same A1 spine+thickness algorithm** with different (control-point count, interior angle, taper) parameter triplets. So really 5 distinct algorithms + parameter variation.

## §5 — Top 3 Recommendations for Phase A v3.1

### Rec #1 — Best for SHAPE VARIETY: **Bézier spine + variable-thickness offset** (§1.A1 + A8)

Spine-and-thickness is the swiss-army knife. Spore uses it for creatures (spine + per-segment radius); we use it for plates. One algorithm gives S/U/C/hook/boot/L just by changing control polygon.

**Architectural sketch.** New `crates/world-gen/src/shape/spine.rs` exposing `fn plate_from_spine(spine: &[Vec2], radius_fn: impl Fn(f32)->f32, samples: usize, rng: &mut R) -> Polygon`. Sample spine via Catmull-Rom centripetal; compute per-sample tangent → normal; emit left/right offset vertices. Cap endpoints with semi-circle fan. Run existing fbm vertex perturb. Templates 2–4 become 1 generator with 3 preset parameter sets. Hook into `Plate.components[0]` SSOT — no schema break.

**Hours.** 10h (6 generator, 2 tests, 2 viz parity check)
**Risk.** Cusp at high curvature (mitigate: keep `r ≤ 0.3 × min_curvature_radius`).
**Files.** `flatworld.rs` (template dispatch), new `shape/spine.rs`, new `shape/offset.rs`, `tests/spine_offset_test.rs`.

### Rec #2 — Best for SPECIFIC SHAPE CONTROL: **SDF capsule chain + smooth-min + marching-squares** (§1.A2 + A3)

Pure SDF approach: every plate is `smin(capsule(A,B,r1), capsule(B,C,r2), ...)`. Iñigo Quilez's quadratic smin gives clay-like blending. Output via marching-squares. ONE algorithm for ALL templates including current ellipse (= single capsule with r1=r2=rx and length=0).

**Architectural sketch.** New `shape/sdf.rs` with `fn sdf_chain(p: Vec2, joints: &[Vec2], radii: &[f32], k: f32) -> f32`. Each `PlateTemplate` definition becomes `Vec<(joint_pos, radius)>` + `smin_k`. Rasterize per-plate to local 256×256 grid, march iso=0 with existing MS code, vertex-perturb with fbm. Plate.components retains `Vec<Polygon>` because single SDF can produce multiple disconnected pieces → free archipelago support.

**Hours.** 14h. **Risk.** Rasterization cost (256² × 12 = 786k SDF evals per world). **Files.** `flatworld.rs`, new `shape/sdf.rs`, `shape/raster.rs`, `tests/sdf_chain_test.rs`.

### Rec #3 — Best for PRODUCTION USE: **Hybrid — A1 spine + A7 superformula + A6 boolean**

Pragmatic: pick cheapest right tool per topology. A1 handles 5 elongated templates. A7 superformula (one closed-form polar function) handles oval/star/rounded-square in 30 LOC. A6 boolean (geo-clipper crate) gives ring/atoll + arbitrary CSG composition.

**Architectural sketch.** Three small modules:
- `shape/spine.rs` — A1, ~120 LOC
- `shape/polar.rs` — A7 superformula, ~30 LOC
- `shape/csg.rs` — A6 thin wrapper around `geo-clipper`, ~80 LOC

`PlateTemplate::generate(rng) -> Vec<Polygon>` dispatches to right module per `kind`. SSOT preserved. No marching-squares plumbing needed.

**Hours.** 18h total. **Risk.** `geo-clipper` crate adds 1 dep. **Files.** `Cargo.toml` (add `geo-clipper = "0.8"`), `flatworld.rs`, 3 new modules in `shape/`, parallel tests.

## §6 — Recommendation Summary

If forced to pick one: **#1 Bézier spine + variable thickness**. It alone unlocks 5 of 8 topologies PO mentioned with single small generator (~120 LOC). Templates 6 (ring) and 7 (branching) can be deferred to v3.2.

For final v3.2 push: layer in **#3's hybrid** (A7 polar for symmetric/rose-curve plates, A6 boolean for rings). Save **#2 SDF capsule chain** for hypothetical v4 if multi-arm branching plates become critical.

## §7 — All Sources (deduplicated)

### Algorithm references
1. [Iñigo Quilez — Smooth min](https://iquilezles.org/articles/smin/)
2. [Iñigo Quilez — 2D Distance Functions](https://iquilezles.org/articles/distfunctions2d/)
3. [Iñigo Quilez — 3D Distance Functions](https://iquilezles.org/articles/distfunctions/)
4. [Aurimas Gasiulis — Bézier offsetting](https://gasiulis.name/cubic-curve-offsetting/)
5. [Hoschek 1993 — Variable-radius offset](https://www.sciencedirect.com/science/article/abs/pii/001044859390010L)
6. [Catmull-Rom centripetal](https://en.wikipedia.org/wiki/Centripetal_Catmull%E2%80%93Rom_spline)
7. [Catmull-Rom in game dev](https://andrewhungblog.wordpress.com/2017/03/03/catmull-rom-splines-in-plain-english/)
8. [CGAL Straight Skeleton](https://doc.cgal.org/latest/Straight_skeleton_2/index.html)
9. [CGAL Skeleton Extrusion](https://doc.cgal.org/latest/Straight_skeleton_2/group__PkgStraightSkeleton2Extrusion.html)
10. [Chazelle convex decomposition](https://dl.acm.org/doi/pdf/10.1145/357346.357348)
11. [Gielis Superformula](https://en.wikipedia.org/wiki/Superformula)
12. [Polar Curves Brilliant](https://brilliant.org/wiki/polar-curves/)
13. [Epicycloid Wolfram](https://mathworld.wolfram.com/Epicycloid.html)
14. [Wave Function Collapse mxgmn](https://github.com/mxgmn/WaveFunctionCollapse)
15. [WFC tips Boris the Brave](https://www.boristhebrave.com/2020/02/08/wave-function-collapse-tips-and-tricks/)
16. [Witten-Sander DLA](https://en.wikipedia.org/wiki/Diffusion-limited_aggregation)
17. [Ryan Geiss Metaballs](http://www.geisswerks.com/ryan/BLOBS/blobs.html)
18. [Ronja 2D SDF Combination](https://www.ronja-tutorials.com/post/035-2d-sdf-combination/)
19. [L-system game dev medium](https://medium.com/@wiltchamberian777/l-system-in-game-cc2b79c2a17f)

### Game references
20. [Civ V Map](https://civilization.fandom.com/wiki/Map_(Civ5))
21. [CivFanatics blend script](https://forums.civfanatics.com/threads/map-script-request-blend-of-continents-and-fractal.654286/)
22. [CivFanatics Continental Drift](https://forums.civfanatics.com/threads/continental-drift-map-script.698809/)
23. [Civ VII Map Generation](https://civilization.2k.com/civ-vii/from-the-devs/map-generation/)
24. [DF World Generation](https://dwarffortresswiki.org/index.php/DF2014:World_generation)
25. [DF World Rejection](https://dwarffortresswiki.org/index.php/v0.34:World_rejection)
26. [DF Advanced World Gen](https://dwarffortresswiki.org/index.php/Advanced_world_generation)
27. [GDC Tarn Adams Procedural](https://www.gdcvault.com/play/1023372/Practices-in-Procedural)
28. [GDC NMS Continuous World](https://www.gdcvault.com/play/1024265/Continuous_World_Generation_in__No_Man_s_Sky_)
29. [GDC NMS Building Worlds Math](https://www.gdcvault.com/play/1024514/Building-Worlds-Using)
30. [Paradox Stellaris Dev Diary 3](https://forum.paradoxplaza.com/forum/threads/stellaris-dev-diary-3-galaxy-generation.885267/)
31. [Minecraft World Generation Wiki](https://minecraft.wiki/w/World_generation)
32. [Alan Zucconi Minecraft](https://www.alanzucconi.com/2022/06/05/minecraft-world-generation/)
33. [Henrik Kniberg Minecraft](https://www.youtube.com/watch?v=ob3VwY4JyzE)
34. [GDC Caves of Qud Grinblat](https://www.gdcvault.com/play/1026313/Math-for-Game-Developers-End)
35. [Caves of Qud Game Developer](https://www.gamedeveloper.com/design/tapping-into-the-potential-of-procedural-generation-in-caves-of-qud)
36. [Brian Walker Brogue talk](https://www.youtube.com/watch?v=Uo9-IcHhq_w)
37. [Anderoonies Brogue pt 1](http://anderoonies.github.io/2020/03/17/brogue-generation.html)
38. [Anderoonies Brogue pt 2](http://anderoonies.github.io/2020/04/07/brogue-generation-2.html)
39. [Brogue Wiki Generation](https://brogue.fandom.com/wiki/Level_Generation)
40. [RD Diablo 2 Randomness](http://thegamedesignforum.com/features/RD_D2_5.html)
41. [Derek Yu Spelunky book](https://bossfightbooks.com/products/spelunky-by-derek-yu)
42. [Spelunky CMU EMS analysis](https://ems.andrew.cmu.edu/2014_60210a/maj/08/27/technological-artdesign-spelunky/index.html)
43. [Spore Playable Procedural Gen PDF](https://press.etc.cmu.edu/file/download/835/9a5bceac-2665-4da1-821c-556947c9e3f3)
44. [Spore Tech Review](https://www.technologyreview.com/2008/06/17/127401/creating-creatures/)
45. [Songs of Conquest RMG](https://www.songsofconquest.com/modding/rmg)
46. [Amplitude Endless Legend World Gen](https://community.amplitude-studios.com/amplitude-studios/endless-legend/blogs/708-community-spotlight-5-world-generator-full-customization-by-enchanteur)
47. [RimWorld Wiki World Gen](https://rimworldwiki.com/wiki/World_generation)
48. [Amit Patel Polygon Map](http://www-cs-students.stanford.edu/~amitp/game-programming/polygon-map-generation/)
49. [Amit Patel Island Shaping 2022](https://simblob.blogspot.com/2022/04/improving-island-shaping-for-map.html)
50. [Red Blob Games Island Shaping](https://www.redblobgames.com/maps/terrain-from-noise/islands.html)
51. [Bad North WFC EPC2018](https://www.youtube.com/watch?v=0bcZb-SsnrA)
52. [Townscaper Game Developer](https://www.gamedeveloper.com/game-platforms/how-townscaper-works-a-story-four-games-in-the-making)
53. [Stalberg Townscaper IndieCade](https://www.youtube.com/watch?v=1hqt8JkYRdI)
54. [Viitanen PlaTec PDF](https://www.theseus.fi/bitstream/handle/10024/40422/Viitanen_Lauri_2012_03_30.pdf)
55. [Cortial Procedural Tectonic Planets](https://hal.science/hal-02136820/file/2019-Procedural-Tectonic-Planets.pdf)
56. [Cauliflower Labs Geology Sim](http://cauliflowerlabs.blogspot.com/2014/10/geology-simulator-plate-tectonics.html)

### Reference papers
57. [Diamond-Square PCG Wiki](http://pcg.wikidot.com/pcg-algorithm:diamond-square-algorithm)
58. [Steve Losh Diamond Square](https://stevelosh.com/blog/2016/06/diamond-square/)
59. [Midpoint Displacement Wikipedia](https://en.wikipedia.org/wiki/Midpoint_displacement_algorithm)
60. [Game AI Pro 3 Random walks](https://www.oreilly.com/library/view/game-ai-pro/9781351647748/xhtml/13_Chapter02.xhtml)
61. [Random Walk Unity Noveltech](https://www.noveltech.dev/procgen-random-walk)
62. [Fractional Brownian motion Game Developer](https://www.gamedeveloper.com/programming/sponsored-feature-procedural-terrain-generation-with-fractional-brownian-motion)
63. [Polynomial PCG terrain arXiv:1610.03525](https://arxiv.org/pdf/1610.03525)
64. [Modern PCG Algorithms CSSESW 2024](https://cssesw.easyscience.education/cssesw2024/CSSESW2024/paper21.pdf)
65. [DLA terrain Voxels.blogspot](http://voxels.blogspot.com/2014/01/procedural-terrain-heightmap-generation.html)
66. [DLA PCG Wiki](http://pcg.wikidot.com/diffusion-limited-aggregation)

## §8 — Result (what happens next)

PO chose: **save research as files before implementing**.

This file + the other 2 research files are the persistent knowledge base. Next session (post-research-save) can pick from the 3 ranked recs for v3.1 implementation.

The leading candidate is **Rec #1 (Bézier spine + thickness)** — single algorithm unlocking S/hook/sock/L/arc topologies. Defer Rec #2 (SDF) until/unless multi-arm branching becomes critical. Use Rec #3 (Hybrid) approach in v3.2+ when adding ring/atoll templates.
