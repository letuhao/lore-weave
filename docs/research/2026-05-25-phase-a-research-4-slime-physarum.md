# Research 4 — Multi-Agent Slime Mold / Physarum / DLA Algorithms for Plate Shape

**Date:** 2026-05-25 (session 59) · **Context:** After Research 3 + commit of research knowledge base, PO proposed a novel algorithm idea — multi-agent random walks with energy decay, then connect nodes and trace boundary. Asked if it exists and if it's more diverse than research'd algorithms.

## §0 — PO's Algorithm Proposal (verbatim, preserved)

> "dùng thuật toán vết dầu loang hay dùng thuật toán vẽ câu nhiều nhanh ngẫu tiên từ 1 hoặc n xuất phát điểm, sau khi di chuyển ngẫu nhiên tới các node cố định gồm n node thì chúng ta nối ngẫu nhiên các node này lại với nhau rồi vẽ edge đi qua các node thì sao?
>
> giống kiểu giả lập nấm slime hay tia chớp di chuyển ấy?
> hình dạng của mảng kiến tạo sẽ random hơn và hình dáng tạo ra chúng ta không biết trước
>
> kiểu dữ bỏ vào đó n seed chưa biết, mỗi seed có thể lực khác nhau, cho chúng di chuyển dò đường random cho tới khi hết thể lức và dừng lại
> sau đó chúng ta lại cho các seed khác đi tìm đường đi ngẫu nhiên đễ vẽ biên cho các seed rồi loại bỏ các đường giao dư thừa, cuối cùng chúng ta có 1 polygon phức tạp nhưng trông thực hơn?
>
> với thuật toán này của tôi thì sao, có đa dạng hơn mấy cái vừa research ở trên không?
> có thuật toán nào như vậy không? có game nào áp dụng không?"

**Translation summary:**
- Use "spreading oil stain" (vết dầu loang) or **multi-branch random walk from 1 or N starting points**
- Walks reach N fixed nodes, then **randomly connect** nodes to each other, **draw edges through nodes**
- Like **slime mold simulation or moving lightning**
- Each seed has different **stamina/energy**, walks randomly until energy depleted
- Then second pass with new seeds **traces the boundary**, removes overlapping/redundant edges
- Result: **complex polygon, looks more realistic**
- Questions: Is this more diverse than current research? Does this algorithm exist? Do any games use it?

## §1 — YES — This IS a Real Algorithm Family

PO's proposal is essentially **a 5-stage hybrid** of well-known algorithms. Each stage has a canonical name in literature:

### Stage breakdown

| PO's stage | Algorithm name | Canonical reference |
|---|---|---|
| **1. N seeds with random energy, random walk** | **Multi-agent biased random walk with energy decay** | Jones 2010 — [Characteristics of Pattern Formation in Physarum (Artificial Life 16:2)](https://uwe-repository.worktribe.com/output/980579) |
| **2. "Oil spreading" / branching** | **Diffusion-Limited Aggregation (DLA)** | Witten & Sander 1981 — [PRL 47:1400 DOI](https://doi.org/10.1103/PhysRevLett.47.1400) — produces dendritic fractal D≈1.71 |
| **3. "Lightning movement"** | **Dielectric Breakdown Model (DBM)** | Niemeyer-Pietronero-Wiesmann 1984 — [PRL DOI](https://doi.org/10.1103/PhysRevLett.52.1033) — adapts DLA for lightning |
| **4. Connect random pairs of stopped nodes** | **Random Geometric Graph** + **Minimum Spanning Tree** OR **Delaunay subset** | Penrose 2003 "Random Geometric Graphs" (Oxford UP) |
| **5. Trace boundary through node cloud** | **Concave hull (α-shape)** | Edelsbrunner-Kirkpatrick-Seidel 1983 — [IEEE TIT DOI](https://doi.org/10.1109/TIT.1983.1056714); Moreira-Santos 2007 — [k-nearest concave hull](https://repositorium.sdum.uminho.pt/bitstream/1822/6429/1/ConcaveHull_ACM_MYS.pdf) |
| **6. "Remove redundant intersecting edges"** | **Bentley-Ottmann sweep line** + **Douglas-Peucker simplification** | Bentley-Ottmann 1979 [IEEE TC](https://doi.org/10.1109/TC.1979.1675432); Douglas-Peucker 1973 |

### What "slime mold simulation" actually is

**Physarum polycephalum** is a single-celled organism that forms branching networks to find food. When digitized as a simulator (Jeff Jones 2010), it works as:

1. **N agents** scattered on a grid, each with position + heading
2. Each agent has 3 sensors (left/forward/right) sampling a **trail field**
3. Agent moves forward, drops trail, rotates toward strongest sensor reading
4. Trail field decays + diffuses (like ink spreading)
5. After N timesteps → emergent transport network

This is exactly what Sebastian Lague reproduced in his famous YouTube video **["Coding Adventure: Ant and Slime Simulation"](https://www.youtube.com/watch?v=X-iSQQgOd1A)** and what Sage Jenson visualized in his Physarum experiments. The output: **organic dendritic networks** that look like slime molds, ant trails, neural networks, or — when filled in — **organic continent shapes**.

### What "lightning movement" / DBM is

**Dielectric Breakdown Model**: same as DLA but particles preferentially walk along electric-potential gradients. Produces:
- Lightning bolts in air (Niemeyer-Pietronero 1984)
- Crystal growth patterns
- River networks (Rinaldo et al. 1992)
- Branching coastlines if used for terrain

Reed & Wyvill 1994 ["Physically-based modeling of lightning"](https://dl.acm.org/doi/10.1145/192161.192193) is the canonical computer graphics application.

## §2 — Real-World References & Implementations

### Academic papers
1. **Jones 2010 — Physarum transport network** ([repository](https://uwe-repository.worktribe.com/output/980579)) — the multi-agent slime simulation paper
2. **Adamatzky 2010 — Physarum Machines** (book, World Scientific) — Physarum as nature's computer
3. **Witten-Sander 1981 — DLA** ([PRL DOI](https://doi.org/10.1103/PhysRevLett.47.1400)) — foundational paper
4. **Niemeyer-Pietronero-Wiesmann 1984 — DBM lightning** ([PRL DOI](https://doi.org/10.1103/PhysRevLett.52.1033))
5. **Rinaldo et al. 1992 — Self-organized fractal river networks** ([PRL DOI](https://doi.org/10.1103/PhysRevLett.70.822)) — DBM applied to rivers
6. **Edelsbrunner-Kirkpatrick-Seidel 1983 — α-shapes** ([IEEE TIT](https://doi.org/10.1109/TIT.1983.1056714)) — generalized concave hull
7. **Moreira-Santos 2007 — k-nearest concave hull** ([PDF](https://repositorium.sdum.uminho.pt/bitstream/1822/6429/1/ConcaveHull_ACM_MYS.pdf)) — practical algorithm for point-cloud boundary
8. **Reed-Wyvill 1994 — Physically-based lightning** ([ACM DOI](https://dl.acm.org/doi/10.1145/192161.192193))
9. **Penrose 2003 — Random Geometric Graphs** (Oxford UP) — node connection theory

### Tools & visualizations
- **[Sebastian Lague — Coding Adventure: Ant and Slime Simulation](https://www.youtube.com/watch?v=X-iSQQgOd1A)** — definitive educational implementation; ~30k agents real-time on GPU
- **[Sage Jenson — Physarum experiments](https://cargocollective.com/sagejenson/physarum)** — generative art series, beautiful visualizations
- **[Andy Lomas — Computational Forms / Cellular Forms](https://www.andylomas.com/cellularForms.html)** — agent-aggregate sculpture
- **[Karl Sims — Reaction-Diffusion](http://www.karlsims.com/rd.html)** — related (Turing patterns)
- **[WBLut Physarum repo](https://github.com/wblut/HE_Mesh)** — Java Physarum + mesh integration

### Game examples (LIMITED — this is a research gap industry hasn't filled)

| Game / project | What's used | How close to PO's algo |
|---|---|---|
| **Dwarf Fortress** — river generation | D8 drainage from random sources (single-agent walk) | ⚠ Partial (single-agent, no concave hull) |
| **Brogue** — cave generation | Random walks with brush, then accretion | ⚠ Similar (uses CA after, not concave hull) |
| **Sebastian Lague slime simulation** | Multi-agent + trail field + sensor | ✓ **CLOSEST** but for visual sim, not game gen |
| **Sage Jenson Physarum** | Same as Lague | ✓ Same — art, not game |
| **Plague Inc.** | Stochastic disease spread across countries | ⚠ Similar agent walk, no shape generation |
| **Townscaper** | Wave Function Collapse on relaxed grid | ✗ Different paradigm (constraint-driven) |
| **Cellular Forms (Andy Lomas)** | Cell agglomeration with diffusion | ✓ Similar emergent-shape approach |
| **No Man's Sky** asteroid fields | Voronoi-cluster (rumored) | ✗ Different |

**Verdict on game industry usage**: Multi-agent random walk + boundary trace for **continent generation specifically** is **a near-empty white space** in game industry. Most games stick to noise+threshold (Civ V/VI), tectonic sim (PlaTec), or WFC (Townscaper). PO's idea would be **genuinely novel** as a published game algorithm. Academic and art-installation literature is rich, but game-published is sparse.

## §3 — Algorithm Implementation Sketch (for our Rust system)

### Step 1 — Multi-Agent Walk Phase (~80 LOC)

```rust
struct WalkAgent {
    pos: (f32, f32),
    heading: f32,
    energy: f32,       // depleted by 1 per step
    salt: u32,
}

fn agent_walk(
    agents: &mut [WalkAgent],
    bounds: (f32, f32, f32, f32),
    persistence: f32,      // 0.0 = pure brownian; 1.0 = straight line
    rng: &mut Rng,
) -> Vec<(f32, f32)> {  // returns all visited points
    let mut visited = Vec::new();
    while agents.iter().any(|a| a.energy > 0.0) {
        for agent in agents.iter_mut() {
            if agent.energy <= 0.0 { continue; }
            // Random direction change biased toward current heading
            let dtheta = (rng.next_f32() - 0.5) * (1.0 - persistence) * TAU;
            agent.heading += dtheta;
            agent.pos.0 += agent.heading.cos();
            agent.pos.1 += agent.heading.sin();
            agent.pos.0 = agent.pos.0.clamp(bounds.0, bounds.2);
            agent.pos.1 = agent.pos.1.clamp(bounds.1, bounds.3);
            visited.push(agent.pos);
            agent.energy -= 1.0;
        }
    }
    visited
}
```

### Step 2 — Connect Random Nodes (~50 LOC)

```rust
// Pick K "anchor nodes" from visited points (e.g., every 10th, or random subset)
// Build Delaunay triangulation (use existing Mesh.rs Delaunay code)
// OR: random graph (each node connects to K nearest neighbors)
fn connect_anchors(anchors: &[(f32, f32)], k: usize) -> Vec<(usize, usize)> {
    let mut edges = Vec::new();
    for (i, &a) in anchors.iter().enumerate() {
        let mut nearest: Vec<(f32, usize)> = anchors
            .iter()
            .enumerate()
            .filter(|(j, _)| *j != i)
            .map(|(j, &b)| (dist_sq(a, b), j))
            .collect();
        nearest.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
        for &(_, j) in nearest.iter().take(k) {
            if i < j { edges.push((i, j)); }
        }
    }
    edges
}
```

### Step 3 — Trace Boundary (Concave Hull / α-shape) (~150 LOC)

```rust
// Moreira-Santos k-nearest concave hull algorithm
fn concave_hull(points: &[(f32, f32)], k: usize) -> Polygon {
    // 1. Start with rightmost point
    // 2. From current point, find K nearest neighbors
    // 3. Pick the one that makes the largest right turn (clockwise sweep)
    // 4. If picked point creates self-intersection, pick next-best
    // 5. Repeat until back to start
    // (full impl ~100 LOC + Bentley-Ottmann self-intersection check ~50 LOC)
    todo!()
}

// Alternative: α-shape via Delaunay edge filtering
fn alpha_shape(points: &[(f32, f32)], alpha: f32) -> Polygon {
    // 1. Compute Delaunay triangulation
    // 2. For each triangle, check circumradius < alpha
    // 3. Boundary = edges of accepted triangles that aren't shared
}
```

### Step 4 — Polygon Simplification (~30 LOC)

Standard Douglas-Peucker or Visvalingam-Whyatt. Already in many Rust crates (`geo` crate has it).

### Putting it together — per-plate pipeline

```rust
fn slime_plate_generate(
    seed: u32,
    plate_center: (f32, f32),
    energy: f32,           // ~plate_radius × 50
    n_agents: usize,       // 3-8
    persistence: f32,      // 0.7 = curvy walks
    k_neighbors: usize,    // 4-6 for connection step
    alpha: f32,            // concave hull tightness
) -> Polygon {
    let mut rng = Rng::seeded(seed);
    let mut agents = (0..n_agents).map(|i| WalkAgent {
        pos: plate_center,
        heading: rng.next_f32() * TAU,
        energy: energy * (0.5 + rng.next_f32()),  // varied per agent
        salt: seed.wrapping_add(i as u32),
    }).collect::<Vec<_>>();
    let bounds = (
        plate_center.0 - energy * 0.5, plate_center.1 - energy * 0.5,
        plate_center.0 + energy * 0.5, plate_center.1 + energy * 0.5,
    );
    let visited = agent_walk(&mut agents, bounds, persistence, &mut rng);
    let hull = concave_hull(&visited, 8);   // tighter k = more concave
    simplify_polygon(&hull, tolerance=2.0)
}
```

**Total estimated LOC**: ~310 (80 + 50 + 150 + 30). One new module `crates/world-gen/src/shape/slime.rs`.

## §4 — Diversity Verdict: vs Templates (Research 3 Rec #1)

| Aspect | Templates (Bézier spine, A1) | **PO's Slime/Physarum** |
|---|---|---|
| **Topology variety** | 5-8 fixed shapes (S, hook, ring...) | **Unlimited** — any topology (branching, ring, blob, peninsula, scattered cluster, all in one plate) |
| **Predictability** | High (template → shape category guaranteed) | **Low** — emergent, can't say "give me Italy" |
| **Visual surprise** | Limited (predicted S-curve etc.) | **High** — each seed = surprise |
| **Per-seed quality variance** | Low (template guarantees) | **HIGH** — some seeds beautiful, some seeds look like sad worms |
| **Determinism** | ✓ (seeded RNG) | ✓ (seeded RNG) |
| **Hash pin stability** | Stable across small code changes | **FRAGILE** — any change in walk RNG order = totally different shape |
| **CPU cost per plate** | ~1ms (one polygon pass) | **~10-100ms** (10k-100k agent steps + concave hull + simplification) |
| **Eval composite stability** | Predictable | **Wild swings** ±20pt likely |
| **Code complexity** | Low (~120 LOC per template) | **High** (~310 LOC + dependencies) |
| **"Real-Earth feel"** | Looks designed | **Looks organic OR alien OR weird** depending on params |
| **Authoring workflow** | Designer-friendly (tune templates) | **Researcher-friendly** (tune emergence) |

### When slime wins
- Worlds where **maximum variety + surprise** is the goal (e.g., procedural sandbox without authored expectations)
- Plates where **scattered cluster + multi-component** is desired naturally (no schema complexity)
- Art-installation visuals over game UX

### When templates win
- Worlds where **predictable shape categories** matter (climate eval expects certain biome distributions)
- **QA** is feasible (each template has known acceptance criteria)
- Designer **needs to author specific shapes** (Italy/Korea/Norway analogs)

## §5 — Recommended Hybrid Architecture

Best of both worlds: **hybrid by SizeRank**.

```
Giant + Large plates  → Bézier spine templates (Research 3 Rec #1)
                        Predictable, designer-controllable, visual stability matters
                        These are the "Eurasia/Africa" of the world

Medium plates         → Choice of templates (Cratonic / Peninsular / FjordCoast)
                        Mix of authored topology with variety

Small + Micro plates  → SLIME ALGORITHM (PO's idea)
                        Wild variety is OK / desirable
                        Each tiny island = surprise
                        These are the "Galapagos/Indonesia/random islands"
```

This way:
- Big plates dominating world visual are predictable + stable
- Tiny plates that fill in the rest are wildly varied
- Eval impact is bounded (Giants control most of land area)
- PO's algorithmic intuition gets used where it shines most

## §6 — Algorithm Variants to Consider

If we pursue PO's algorithm, several parameters control emergence:

### Walk variants
| Variant | Behavior | Best for |
|---|---|---|
| **Pure Brownian** (persistence=0) | Cloud expansion | Blob plates |
| **High persistence** (0.95) | Straight tendrils | Peninsular plates |
| **Trail-following** (Physarum) | Reinforced paths | Branching networks |
| **Levy flight** (heavy-tail step size) | Occasional jumps | Multi-component scatter |
| **Constrained walk** (avoid prior cells) | Self-avoiding spread | Compact filled |

### Boundary variants
| Variant | Pros | Cons |
|---|---|---|
| **Convex hull** | Always works, fast | Loses concavities (back to blobs) |
| **Concave hull (Moreira-Santos)** | Tight wrap on shape | Can produce holes/self-intersections |
| **α-shape** | Smooth tightness control | Requires Delaunay first |
| **Marching squares on density** | Naturally smooth | Need to rasterize visited density |

### Energy variants
| Variant | Behavior |
|---|---|
| **Uniform** | All seeds same stamina → balanced shapes |
| **Pareto** | Few big seeds + many small → fractal-like |
| **By SizeRank** | Energy = size_rank_radius × 50 → matches plate target size |

## §7 — Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Concave hull produces self-intersecting polygon | High | Bentley-Ottmann post-pass to detect, retry with different k_neighbors |
| Walks escape plate bounds | Medium | Hard clamp to bounding circle; OR repulsive force at boundary |
| Some seeds produce degenerate shapes (thin worm, scattered dots) | High | Quality filter: reject + re-seed if `area < min_threshold` OR `compactness < 0.05` |
| Eval composite swings wildly | High | Restrict to Small + Micro plates (less area = less eval impact) |
| Performance regression (slow per-plate) | Medium | Limit to small plates (smaller energy → fewer steps); parallelize via rayon |
| Hash pin fragility kills CI | High | Re-pin every commit OR exclude slime plates from hash pin (use shape-property hash instead) |

## §8 — Comparison Summary vs Research 1-3

| Algorithm | Variety | Control | Speed | Determinism | Production-ready |
|---|---|---|---|---|---|
| Research 1: Multi-tier noise + midpoint disp | ★★★ | ★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| Research 2: 7-template taxonomy | ★★★★ | ★★★★★ | ★★★★ | ★★★★★ | ★★★★ |
| Research 3 Rec #1: Bézier spine + thickness | ★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| Research 3 Rec #2: SDF capsule chain + smin | ★★★★★ | ★★★★ | ★★★ | ★★★★★ | ★★★ |
| **Research 4: PO Slime / Physarum** | ★★★★★ | ★ | ★★ | ★★★ | ★★ |
| Research 4: Hybrid (Templates Giant+Large, Slime Micro) | ★★★★★ | ★★★★ | ★★★★ | ★★★★ | ★★★★ |

**Slime algorithm scores highest on RAW VARIETY but lowest on production-readiness.**

The **hybrid approach** combines the best of both: production-grade for big plates + wild variety for small plates.

## §9 — Recommendation

**For v3.1 implementation**: defer slime algorithm in favor of **Bézier spine** (Research 3 Rec #1) as the primary template engine. Templates provide the controllability needed for climate-eval stability.

**For v3.2 or v3.3**: layer in **PO's slime algorithm specifically for SizeRank::Small and SizeRank::Micro plates**. The hybrid pattern gives the best variety/stability tradeoff and uses each algorithm where it shines.

**For "exploration mode" or "wild seed" worlds** (future feature): expose slime algorithm as opt-in for users who want maximum surprise.

## §10 — Sources

### Academic
1. Jones J., 2010 — Characteristics of pattern formation and evolution in approximations of Physarum transport networks, *Artificial Life* 16(2): [Repository](https://uwe-repository.worktribe.com/output/980579)
2. Adamatzky A., 2010 — *Physarum Machines: Computers from Slime Mould*, World Scientific
3. Witten T.A., Sander L.M., 1981 — *Phys. Rev. Lett.* 47:1400, Diffusion-limited aggregation: [DOI](https://doi.org/10.1103/PhysRevLett.47.1400)
4. Niemeyer L., Pietronero L., Wiesmann H.J., 1984 — *Phys. Rev. Lett.* 52:1033, Fractal dimension of dielectric breakdown: [DOI](https://doi.org/10.1103/PhysRevLett.52.1033)
5. Rinaldo A. et al., 1992 — *Phys. Rev. Lett.* 70:822, Self-organized fractal river networks: [DOI](https://doi.org/10.1103/PhysRevLett.70.822)
6. Edelsbrunner H., Kirkpatrick D.G., Seidel R., 1983 — *IEEE TIT* 29:551, On the shape of a set of points in the plane: [DOI](https://doi.org/10.1109/TIT.1983.1056714)
7. Moreira A., Santos M.Y., 2007 — k-nearest concave hull algorithm: [PDF](https://repositorium.sdum.uminho.pt/bitstream/1822/6429/1/ConcaveHull_ACM_MYS.pdf)
8. Reed T., Wyvill B., 1994 — Physically-based modeling of lightning: [ACM DOI](https://dl.acm.org/doi/10.1145/192161.192193)
9. Penrose M., 2003 — *Random Geometric Graphs*, Oxford UP
10. Bentley J.L., Ottmann T.A., 1979 — Algorithms for reporting and counting geometric intersections: [IEEE TC](https://doi.org/10.1109/TC.1979.1675432)
11. Douglas D.H., Peucker T.K., 1973 — Algorithms for the reduction of points in a digitized line: *Canadian Cartographer* 10:112-122

### Game / art / tools
12. [Sebastian Lague — Coding Adventure: Ant and Slime Simulation (YouTube)](https://www.youtube.com/watch?v=X-iSQQgOd1A)
13. [Sage Jenson — Physarum experiments](https://cargocollective.com/sagejenson/physarum)
14. [Andy Lomas — Computational / Cellular Forms](https://www.andylomas.com/cellularForms.html)
15. [Karl Sims — Reaction-Diffusion Computer Sculpture](http://www.karlsims.com/rd.html)
16. [WBLut HE_Mesh Physarum library (Java)](https://github.com/wblut/HE_Mesh)
17. [Coding Train — Random Walks](https://thecodingtrain.com/challenges/c2-random-walker)
18. [Dwarf Fortress Wiki — Rivers in world gen](https://dwarffortresswiki.org/index.php/DF2014:River)

### Comp-geom libraries (Rust)
19. [`geo` crate](https://crates.io/crates/geo) — has Douglas-Peucker simplification
20. [`spade` crate](https://crates.io/crates/spade) — Delaunay triangulation (for α-shape)
21. [`concave_hull` ad-hoc impl in geo-types](https://docs.rs/geo/latest/geo/algorithm/concave_hull/)

## §11 — Verdict

**TL;DR for PO**: 
- ✅ YES this algorithm exists — it's a hybrid of **Physarum simulation + concave hull + polygon simplification**
- ✅ Sebastian Lague, Sage Jenson, Jeff Jones (2010), DLA literature all use related approaches
- ✅ Game industry rarely uses this for continents (mostly used in art/sim/education)
- ✅ **MORE topologically diverse** than our researched algorithms (any shape possible)
- ⚠️ But: lower predictability, harder QA, fragile hash pins, slower CPU
- 💡 **Best use: hybrid** — slime for Small/Micro plates, templates for Giant/Large
- 📋 Estimated impl: ~310 LOC + Delaunay/concave hull deps; 6-8h work; could be v3.2 or v3.3 addition
