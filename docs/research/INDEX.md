# Research Index — Phase A Plate Shape Generation

> **Purpose:** Preserve all research findings on procedural plate-shape generation across multiple sessions so knowledge doesn't get lost in conversation context. Each research file is self-contained with full citations.

## Reading Order

The four research files were produced in sequence during session 59 (2026-05-25), each in response to PO feedback after the prior iteration:

1. **[Research 1 — Procgen Continent Algorithms](2026-05-25-phase-a-research-1-procgen-algorithms.md)** — Original 10-algorithm catalog after PO feedback "polygons still toy-blob". Recommended Rec #1 (multi-tier noise + midpoint displacement). Result: spike test showed peninsular plates but with eval regression on 2 seeds.

2. **[Research 2 — Shape Templates + Size Diversity + Azgaar FMG Pattern](2026-05-25-phase-a-research-2-shape-templates-sizing.md)** — After PO feedback "still circles same size, need TEMPLATES + multi-algo". 17-algorithm catalog + Pareto/log-normal sizing + Azgaar FMG analysis + 7-template taxonomy + 4-phase v3 roadmap. **Result: v3.0 shipped (commit f022cf82)** — schema refactor + Pareto sizing + anisotropy.

3. **[Research 3 — Topology-Specific Algorithms + Game Industry References](2026-05-25-phase-a-research-3-topology-game-algos.md)** — After PO feedback "still ovals, need S-shape/sock/hook/ring, what algos do games use?". 12 topology-specific algorithms + 20 game industry references (Civ V/VI, DF, NMS, Stellaris, Minecraft, Bad North, Townscaper, Caves of Qud, Brogue, Spelunky, Spore, Diablo II, etc.) + 8-template taxonomy + 3 ranked recs. **Result: PO requested research saved before v3.1 impl.**

4. **[Research 4 — Multi-Agent Slime Mold / Physarum / DLA Algorithms](2026-05-25-phase-a-research-4-slime-physarum.md)** — PO proposed novel algorithm: multi-agent random walks with energy decay → connect nodes → trace boundary. Verified the algorithm exists (Physarum/Jones 2010 + DLA + concave hull). Catalogued game examples (Sebastian Lague slime sim, Sage Jenson Physarum art, DF rivers, Brogue caves). Verdict: **most topologically diverse** of all researched algorithms but lowest production-readiness. Recommended **hybrid use**: templates for Giant/Large plates + slime for Small/Micro plates.

## Quick Reference Tables

### What algorithm produces what topology?

| Topology | Best algorithm | Why | Earth analog | LOC |
|---|---|---|---|---|
| Oval/blob | Anisotropic ellipse + fbm | what v3.0 has | Australia | 0 |
| **S-curve** | Bézier spine + thickness (A1) | 3 ctrl pts | S. America, Norway | 120 |
| **Sock/L/boot** | Bézier with sharp interior angle | 1 spine bent 110° | Italy | 120 (shared) |
| **Hook** | Bézier with 1 bend, asymmetric taper | 3 ctrl, taper r(t) | Florida, Korea | 120 (shared) |
| **Y/T branching** | Skeleton + capsule SDF + smin | 3-node graph | Africa with horn | 250 |
| **Crescent/Arc** | Parametric circular arc + thickness | circle arc spine | Aleutians, Java, Cuba | 80 |
| **Ring/atoll** | Boolean: disk − inner disk | geo-clipper crate | Atoll | 50 + dep |
| **Cross/+** | Skeleton 4-arm radial OR rose r=cos(2θ) | hub+arms | rare | 150 |
| **Crab/spider** | Skeleton 4-6 limbs | multi-capsule SDF | Sulawesi | 200 |
| **Archipelago** | Multi-component marching squares | already in schema | Indonesia | 100 |

**Key insight: Bézier spine + thickness (A1) alone covers 5 topologies (S/hook/sock/L/arc) with ONE module.**

### Real games' algorithms

| Pattern | Games | Pros | Cons |
|---|---|---|---|
| **Fractal noise + rejection** | Civ V/VI, SimCity | Simple, fast | Always blob-y |
| **Tectonic simulation** | PlaTec (academic), No Man's Sky planet gen | Realistic | Heavy CPU |
| **Wave Function Collapse** | Bad North, Townscaper, Caves of Qud (partial) | Industry-proven, expressive | Tile-aligned, costly |
| **Hand-authored stamps** | Diablo II (95 presets), Spelunky (templates), Songs of Conquest | Maximum control, authored-feel | 1h+ per stamp authoring |
| **Skeleton + thickness** | **Spore creatures** | Most topology variety per LOC | Cusp handling |
| **Multi-layer noise** | Dwarf Fortress, Minecraft 1.18+ | Realistic erosion-like | Many tunables |
| **Polygon Voronoi + Lloyd** | mewo2 terrain, Red Blob mapgen2 | Beautiful low-poly | Bounded by polygon count |

### v3.0 (shipped) status

- **Commit:** f022cf82
- **Schema:** Plate.components: Vec<Polygon> with primary()/bounding_box()/multi-component contains()
- **Sizing:** SizeRank enum (Giant/Large/Medium/Small/Micro), deterministic 12-plate distribution 1+2+3+4+2
- **Anisotropy:** (rx, ry, theta_rot) ellipsoidal, aspect Pareto-sampled
- **Eval:** new v5.2 baseline 85.24 (was 89.30 pre-v3.0)
- **PNG renders:** eval/compare-phase-a/v3.0/{plates,biome}_s{7,13,42}.png

### v3.1+ candidates (NOT YET IMPLEMENTED)

| Rec | Algorithm | Hours | Risk | Visual impact | Topologies unlocked |
|---|---|---|---|---|---|
| **#1 (recommended first)** | Bézier spine + variable thickness | 10 | 2/5 | ★★★★☆ | S, hook, sock, L, arc (5 from 1 algo) |
| **#2 (broader)** | SDF capsule chain + smooth-min + marching squares | 14 | 3/5 | ★★★★★ | ALL incl. Y/T branching, archipelago |
| **#3 (production-grade hybrid)** | Spine (A1) + superformula (A7) + boolean (A6 w/ geo-clipper) | 18 | 3/5 | ★★★★★ | 7/8 topologies, deferred Y/T branching |
| **#4 (authored-feel)** | Hand-authored stamps (Diablo II school) | 1h/stamp × N | 1/5 | ★★★★ | whatever you author |
| **#5 (most emergent — PO's idea)** | **Multi-agent slime/Physarum + concave hull** (Research 4) | 6-8 | 4/5 (fragile) | ★★★★★ | **UNLIMITED** but unpredictable per-seed |
| **#6 (hybrid w/ slime)** | Templates for Giant/Large + slime for Small/Micro | 10 + 8 | 3/5 | ★★★★★ | Predictable bigs + wild smalls |

## Roadmap (locked)

See [`docs/plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md) for the v3.0 → v3.3 phased plan:

| Phase | Status | Scope |
|---|---|---|
| **v3.0** | ✅ SHIPPED (f022cf82) | Schema refactor + Pareto + anisotropy |
| **v3.1** | NEXT | Template dispatcher (Bézier spine likely) |
| **v3.2** | future | Full 7-template taxonomy |
| **v3.3** | future | Multi-component (true archipelagos) |

The plan doc will be updated once v3.1 algorithm is chosen.

## Critical PO Feedback Quotes (verbatim)

Preserving exact PO direction in original language so future agents read intent correctly:

### After Phase A v1 spike (Research 1 → 2 trigger)
> "có cải thiện nhưng các mảng lục địa thường có hình tròn, kích thước bằng nhau, trong thực tế các mảng lục địa có rất nhiều kích thước đa dạng hơn, cần thên edge và làm ra các hình dạng phức tạp hơn, nên dùng các template khác nhau để tạo chứ không dùng duy nhất 1 công thức, hiện tại chỉ có thể tạo ra hình tròn bằng nhau rồi bóp méo các cạnh, cần dùng nhiều loại thuật toán tạo hình khác nhau để phối hợp, cần research về thuật toán tạo hình"

**Translation:** Improvement but plates still rounded, same size. Real continents have very diverse sizes. Need more edges and complex shapes. Should use different TEMPLATES, not one formula. Need multiple shape-generation algorithms combined. Research shape algorithms.

### After Phase A v3.0 shipped (Research 2 → 3 trigger)
> "có cải thiện nhưng vẫn là hình oval, không hình học phức tạp nào hơn trong template hả? ví dụ hình chữ S, hình cái tất, vân vân"
> "các game khác họ dùng thuật toán hình học như thế nào vậy?"

**Translation:** Improvement but still ovals — no more complex geometric forms in templates? Example: S-shape, sock shape, etc. What geometric algorithms do other games use?

### After Research 3 presented
> "lưu tất cả kiến thức chúng ta research nảy giờ, bao gồm mấy research ở trên vào file để không bị trôi kiến thức"
> "các kiến thức này sẽ dánh để research phase sau, trước tiên lưu kiên thức lại"

**Translation:** Save all research knowledge into files so it doesn't drift away. This knowledge will be used in next research phase — first save knowledge.

(This INDEX + the 3 research files satisfy that request.)

### After Research 3 saved — PO proposed novel algorithm (Research 4 trigger)
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

**Translation:** Use "spreading oil stain" / multi-branch random walk from N starting points with energy-decay; reach fixed nodes; connect nodes; trace boundary; remove redundant edges. Like slime mold / lightning simulation. More diverse than the research'd algorithms? Does this exist? Any games?

(Answered in Research 4: yes exists as Physarum + DLA + concave hull hybrid; rarely in games; most diverse of all but least production-ready; recommended hybrid use with templates.)

## Visual Evidence (eval/compare-phase-a/)

Permanent visual artifacts committed in repo:

- `target_real_earth.png` — Real-Earth landmass silhouettes (Japan/Indonesia/Britain/Norway/India/Greece) at 1024×640 scale as reference target
- `before-phase-a/{plates,biome}_s{7,13,42}.png` — HEAD baseline (smooth octagons)
- `after-phase-a/{plates,biome}_s{7,13,42}.png` — Phase A v1 calibrated (rounded blobs)
- `spike-rec1/{plates,biome}_s{7,13,42}.png` — Spike of lobe band (peninsular but eval regression)
- `v3.0/{plates,biome}_s{7,13,42}.png` — v3.0 shipped (size-diverse + anisotropic)

## Key References (universal canonical sources)

The 5 most important reference URLs across all 3 research reports:

1. **[Azgaar Fantasy Map Generator (Github)](https://github.com/Azgaar/Fantasy-Map-Generator)** — Canonical template-based plate generator (since 2017). 5 templates × Hill/Pit/Range/Trough/Strait primitives.
2. **[Iñigo Quilez 2D SDFs](https://iquilezles.org/articles/distfunctions2d/)** + **[smin](https://iquilezles.org/articles/smin/)** — Definitive SDF primitive library + smooth-min math.
3. **[Spore Procedural Generation PDF (CMU)](https://press.etc.cmu.edu/file/download/835/9a5bceac-2665-4da1-821c-556947c9e3f3)** — Spore's spine+segment+thickness algorithm (the trick we should adapt for plates).
4. **[Red Blob Games Polygon Map](http://www-cs-students.stanford.edu/~amitp/game-programming/polygon-map-generation/)** — Foundational Voronoi+Lloyd+island-function approach.
5. **[Mandelbrot 1967 Coastline Paradox](https://doi.org/10.1126/science.156.3775.636)** — Why coastlines are fractal; foundational paper for procedural fractal terrain.
