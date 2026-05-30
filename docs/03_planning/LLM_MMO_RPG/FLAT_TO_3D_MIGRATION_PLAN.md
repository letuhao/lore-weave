# Flat → 3D Substrate Migration Plan

> **Session 98 (2026-05-30) — DISCUSSION + PLAN, no code shipped.**
> Audit of the flat-world experiment vs the production sphere pipeline, and a
> decision on how to reconcile them before the "elevation map applied at the
> end" retrofit the PO feared becomes expensive.
>
> Reading order before this doc: [`GEO_GENERATOR_PLAN.md`](GEO_GENERATOR_PLAN.md)
> (phase board + handoff), [`GEO_WORLD_TIER_REDESIGN.md`](GEO_WORLD_TIER_REDESIGN.md)
> (§5b Köppen, §6c fantasy split).

---

## 0 — The one finding that reframes the whole session

Apply ContextHub lesson **1fbf8d34** ("doubt the substrate before the
implementation"): before assuming the civ features are trapped on the flat map,
check *which substrate they actually run on*.

**The civilization layer is shared, not flat-bound.** `political`, `settlement`,
`routes`, `culture`, `feature`, `naming`, `hydrology` are **mesh-agnostic
modules**. The sphere `generate()` calls `political::build`, `settlement::build`,
`routes::build`, `culture::build`, `feature::extract`
([`lib.rs:100-124`](../../../crates/world-gen/src/lib.rs#L100-L124)) — the *same
functions* `civ_adapter.rs` calls
([`civ_adapter.rs:47-51`](../../../crates/world-gen/src/civ_adapter.rs#L47-L51)).
The adapter's own docstring states it plainly:

> *"The downstream code is 100% mesh-agnostic — it doesn't care whether centers
> come from a Fibonacci sphere or a flat rectangle — so a single adapter unlocks
> all those layers for the flatworld track."*

**Consequence:** the PO's fear — *"we bolted a pile of civ features onto the flat
map and skipped the elevation map; it'll be painful to retrofit 3D later"* — is
**largely already resolved**, because:

1. The civ stack is not flat-bound; it already runs on the 3D sphere.
2. The sphere substrate **already has** a real elevation map: plate tectonics +
   Earth-like signed hypsometry + altitude-driven ruggedness + hydraulic
   erosion (Phases 1-2 + coherence pass, all shipped). There is no "apply
   elevation at the end" step pending on the production substrate — it's been
   the foundation since Phase 1.

The flat track is an **experiment** that developed *terrain/climate algorithms*,
not a parallel production civilization that now needs lifting wholesale.

---

## 1 — Honest current state: what is actually on each substrate

### Sphere pipeline (`world_gen::generate`) — PRODUCTION

| Stage | Module | Status |
|---|---|---|
| Mesh | `mesh` | Fibonacci lattice + 3D Quickhull + spherical Voronoi (no seam, no pole degeneracy) |
| Terrain | `terrain` + `plates` | Plate tectonics (6-way boundary classify, orogeny uplift) **or** legacy Profile; 3D Perlin; altitude-driven ruggedness; Earth-like signed hypsometry |
| Erosion | `erosion` | Two-phase stream-power carve/settle (Path B v2) |
| Climate | `climate` | **8-zone** Köppen-*inspired*; orographic moisture march + continentality. **No full Hadley/Ferrel circulation yet** ([`climate.rs:192`](../../../crates/world-gen/src/climate.rs#L192)) |
| Hydrology | `hydrology` | Barnes priority-flood → flow accumulation → river_flux; ocean/lake network |
| Biome | `biome` | **14-cell** BiomeKind |
| Political | `political` | Province flood-fill + state clustering |
| Settlement | `settlement` | Burg-score Poisson-disk + role assignment |
| Routes | `routes` | Road MST / Trail / SeaLane / MountainPass / RiverNavigation |
| Culture | `culture` | Barrier flood-fill regions |
| Features | `feature` | MountainRange / River / WaterBody extraction |
| Naming | `naming` + `author` | LLM naming via **`loreweave_llm` SDK gateway** (PR #13) |
| Render | `render` + `relief` | Hypsometric relief, hillshade, Orthographic globe, SVG political |

**Real 3D elevation: YES.** Full civ stack on the real 3D world: **YES**
(Phase 3, PR #5).

### Flat pipeline (`flatworld` + `zonegen` + `flat_climate` + `civ_adapter`) — EXPERIMENT

| Concern | Module | Status / Notes |
|---|---|---|
| Macro layout | `flatworld` | Plates as 2D polygons on a rectangle; 2-level Voronoi zone tree (plate → zone → subzone); collision-uplift elevation |
| Shape vocabulary | `shape` (dispatcher) | Bézier / Polar / Boolean / Slime-Physarum / archipelago / coastline-fractalize — **operates on 2D polygons** |
| Local terrain | `zonegen` | Per-zone LOCAL relief (no world frame, no sea/ocean) |
| Climate | `flat_climate` | **21-cell** Whittaker Biome; 5-layer pipeline (Insolation + Circulation + Continentality + ZoneRefinement + ElevLapse) — **richer than sphere's 8-zone** |
| Civ bridge | `civ_adapter` | `CivView` reshapes FlatWorld → the shared civ-stack interface |

**Real 3D elevation: NO** — `z=0`, collision-uplift on a flat rectangle, fixed
`sea_level=0.5`. This is the gap the PO worried about — but it is an
**experiment-only** gap, not a production one.

---

## 2 — Q&A summary

**Q1 — What does the sphere pipeline produce?** See §1 table. Full
plate-tectonic 3D planet + complete civ stack + LLM naming + render.

**Q2 — Which civ-layer-amaw features have sphere analogues already?**
**All of the civ stack:** political, settlement, routes, culture, feature,
naming. They are literally the same modules — there is nothing to "port,"
it already runs on the sphere. `civ-layer-amaw`'s only structural delta vs the
current branch is cosmetic (civ_adapter refactored into 5 submodules) plus 3
now-deleted hardcoded LLM provider files (`shape/{anthropic,ollama,openai}.rs`),
superseded by PR #13's SDK gateway.

**Q3 — What is genuinely NEW on flat (no sphere equivalent)?**
1. **`flat_climate` 5-layer Köppen/Whittaker** (21-cell biome) — more
   sophisticated than sphere's 8-zone climate. *This is the one real win.*
2. **Hierarchical zone tree** (plate → zone → subzone) — a prototype of the
   "world → realms → nations → provinces" hierarchy the architectural
   realisation ([`GEO_GENERATOR_PLAN.md:128-138`](GEO_GENERATOR_PLAN.md#L128))
   says a real world needs. Sphere has only flat province/state today.
3. **2D shape dispatcher** (Bézier/Polar/Boolean/Slime/fractalize) — genuinely
   new *vocabulary*, but **coupled to 2D polygon geometry**; does not transfer
   to the sphere without reimplementation.
4. **`civ_adapter` / `zonegen`** — pure flat plumbing, no sphere meaning.

**Q4 — What should be lifted vs stay flat-only?**

| Feature | Decision | Rationale |
|---|---|---|
| `flat_climate` 5-layer climate sophistication | **LIFT to sphere** | Directly becomes the documented Phase 3 Köppen work; flat already de-risked the layered approach |
| Hierarchical zone tree (plate→zone→subzone) | **LIFT concept later** (Phase 4+) | Validated prototype of the political hierarchy the sphere will need; not urgent |
| 2D shape dispatcher | **STAY flat-only** | Coupled to 2D polygons; sphere terrain comes from plate uplift + 3D Perlin, not polygon shapes. Reimplementing on sphere = separate large effort, low payoff now |
| `civ_adapter`, `zonegen`, `flatworld` | **STAY flat-only / freeze** | Pure flat experiment scaffolding |

**Q5 — Migration strategy (cheap-now vs expensive-later).** See §3.

**Q6 — Next ship.** See §4.

---

## 3 — Migration decision (the cheap-now path)

The expensive-later trap the PO sensed is real, but it is **not** "elevation on
the flat map." It is: *continuing to evolve two parallel substrates and trying
to unify them at the end.* The cheap-now move is to stop that now.

**Decisions:**

1. **Sphere is the production substrate.** It already has real 3D elevation +
   the full civ stack. Declare this explicitly so no future session re-invests
   civ features into the flat track.
2. **Flat track = experiment, status "harvested then frozen."** Its one genuine
   win (layered Köppen/Whittaker climate) gets lifted; the rest is kept as a
   reference, not extended.
3. **No civ feature is exempt from running on the sphere.** Apply lesson
   **b720b779**: if a future "let's just add it on flat first, it's faster"
   urge appears, that is the rationalization to challenge — flat civ work does
   not transfer to 3D for free *except* through the mesh-agnostic shared
   modules, which already run on the sphere anyway.
4. **The hierarchical zone tree is the one deferred genuine prototype.** Track
   it (DEFERRED row) as input to the future sphere political-hierarchy work, not
   as something the flat track keeps developing.

This avoids the painful retrofit by **deleting the second substrate from the
production roadmap now**, while preserving its harvested algorithms.

---

## 4 — Next-ship proposal (PO picks one)

| # | Candidate | Effort | Why |
|---|---|---|---|
| **A** | **Phase 3 Köppen climate on sphere**, using `flat_climate`'s 5-layer design as the validated blueprint | **M–L** | Documented next step *and* harvests the flat track's only genuine win in one move. Adds the desert/forest/tundra colour diversity still missing vs real Earth. De-risked (layered approach already prototyped) |
| **B** | **Visual quality audit: sphere world vs real Earth** | **S** | Cheap; produces an evidence-based punch-list (climate monotony, hypsometry, coastline realism) that *informs* what to ship after. Good if PO wants direction before committing to A |
| **C** | **Lift hierarchical zone tree → sphere political hierarchy** | **L** | Genuine structural advance toward "world → realms → nations", but larger and less visually impactful than A; better after A |

**Recommendation: A, with a thin B up front.** Do a 1-hour visual audit (B) to
confirm climate monotony is the top visible defect (it is, per the handoff's
"remaining all-green colour monotony is climate"), then ship A. This sequences
the flat track's harvested climate work straight into the production substrate
and lets us formally close the flat experiment in the same arc.

### 4.1 — PO DECISION (session 98): **candidate C chosen**

The PO chose **C — lift the hierarchical zone tree to the sphere**, over the
quicker climate win (A). Consistent with the long-horizon MMO ambition: a deep,
multi-tier world structure is worth more now than colour diversity. R3 is
therefore promoted from "open risk" to **the active next-ship**.

But **C is under-specified, and the ambiguity is a substrate-doubt trap** —
"lift the zone tree as a political hierarchy" silently merges two *different*
kinds of hierarchy:

| | Flat's zone tree | Sphere's province/state |
|---|---|---|
| Nature | **Geometric / tectonic** — Voronoi subdivision of plate polygons | **Political** — terrain-cost flood-fill + state clustering |
| Driven by | Pure geometry (seeded Voronoi) | Civ algorithms (habitability, cost) |
| Layer | A *terrain* region hierarchy | A *civilization* hierarchy |

The architectural realisation
([`GEO_GENERATOR_PLAN.md:128-138`](GEO_GENERATOR_PLAN.md#L128)) actually names
**two separate** missing things: *(i)* "a world frame with multiple continents +
ocean basins" (geometric) and *(ii)* "hierarchical political (world → realms →
nations → provinces)" (political). The flat zone tree is *(i)*-shaped; "political
hierarchy" is *(ii)*. They are not the same lift.

**The fork to resolve before BUILD:**

- **C1 — Geometric region hierarchy.** Subdivide the *sphere itself* into nested
  geographic regions (continents → subcontinents → regions → localities),
  independent of politics. This is the literal analogue of flat's plate→zone→
  subzone tree. Civ layers then anchor onto it. Closest to "lift the zone tree."
- **C2 — Deeper political hierarchy.** Keep terrain as-is; extend the *political*
  stack from province→state to world→realm→nation→province→county — more tiers
  of the civ algorithms, not a geometric subdivision. This is the "world →
  realms → nations" reading.
- **C3 — Both, geometric first.** C1 provides the geographic frame; C2's
  political tiers then nest inside it. Largest scope; most faithful to the MMO
  end-state but a multi-session arc.

The flat experiment only validated the **geometric** subdivision (C1). C2 is
new design on the sphere. Picking the wrong one means session 99 builds a
geometric tree when the PO wanted political tiers, or vice-versa.

---

### 4.2 — LOCKED DIRECTION (session 98): **C3 — both, geometric first**

The PO chose **C3**: build the geometric region frame first, then nest the
political tiers inside it. This is a **multi-session XL arc** toward the MMO
end-state (deep, multi-tier world structure), not a single ship.

**Arc breakdown:**

| Sub-phase | Builds | Size | Session |
|---|---|---|---|
| **C-1** | Geometric region hierarchy on the sphere: continents → subcontinents → regions | **L** | 99 (start) |
| **C-2** | Political tiers nesting inside the frame: world → realm → nation → province → county | **L–XL** | later |

**Honest framing (lesson b720b779 — no free transfer).** "Lift the flat zone
tree" does **not** mean porting `flatworld.rs` code — that code is 2D
Voronoi-within-polygon and will not transfer to the sphere. What lifts is the
**validated *structure*** (recursive subdivision: macro-plate → mid-zone →
sub-zone). C-1 re-implements that structure with sphere-native primitives.

**C-1 scope for session 99 (the geometric frame):**

The sphere already owns most of the primitives — C-1 assembles them into a
nested hierarchy rather than inventing partitions from scratch:

1. **Continents** = connected components of land cells (flood-fill the land mask
   over `neighbors`, the same machinery `feature::extract` uses for water
   bodies). NOT a fresh Voronoi — continents are an *emergent* connectivity
   fact, and the existing `plates` layer already marks continental vs oceanic.
2. **Subcontinents / regions** = recursive **great-circle Voronoi** seeded inside
   each parent (3D centroid Voronoi on the unit sphere — **do NOT** copy flat's
   2D pixel-grid Voronoi; same trap as R6).
3. **Parent links + stable IDs** designed now so C-2's political tiers anchor
   cleanly onto the frame.
4. **Determinism**: the new layer feeds `content_hash`; pin the new hash as the
   regression lock in the C-1 ship (precedent: every terrain change re-bases).

**C-1 design decisions to resolve in session 99 CLARIFY/DESIGN (XL → needs a
spec + plan file):**

- **D1** — Are continents derived purely from land connectivity, or from
  clustering *continental plates* (the `plates` layer already exists)? Doubt the
  substrate: prefer reusing `plates` over a parallel partition unless they
  genuinely diverge.
- **D2** — Subdivision count per level: fixed, scale-driven, or knob-driven
  (`CreativeSeed`)? Flat used per-parent random counts in a range.
- **D3** — Does the frame replace or wrap the existing flat province/state, and
  how do `feature`/`political` re-anchor? (This is the C-1↔C-2 seam.)
- **D4** — Great-circle Voronoi implementation: reuse `mesh.rs` spherical
  Voronoi machinery, or a lighter seed-nearest assignment over existing cells?

**Session 99 is an XL sub-phase → it owns a dedicated spec + plan file**
(`docs/specs/` + `docs/plans/`), per the task-size protocol. This migration doc
is the parent rationale; it does not replace the C-1 spec.

---

## 5 — Risk register (PO concerns still open after this plan)

| ID | Risk | Status after this plan | Mitigation |
|---|---|---|---|
| R1 | "Elevation applied at end will be a painful retrofit" | **Resolved** for production — sphere has had real elevation since Phase 1; flat's missing elevation is experiment-only | Declare sphere production (§3.1) |
| R2 | Two substrates drift further apart | **Resolved by decision** — flat frozen after climate harvest | §3.2 |
| R3 | Flat's hierarchical zone tree is a real capability sphere lacks (nested region hierarchy) | **NOW THE ACTIVE SHIP** — promoted to candidate C3 (§4.2) | Build geometric frame (C-1) then political tiers (C-2) on the sphere |
| R7 | C-1 builds a geometric partition that duplicates the existing `plates` layer instead of reusing it | **OPEN — D1 in §4.2** | Resolve in session 99 DESIGN: derive continents from `plates`/land-connectivity, not a parallel Voronoi |
| R4 | 2D shape vocabulary (archipelago, fractalized coastlines) won't reach the sphere | **OPEN / accepted** — coupled to 2D geometry | Accept as flat-only; revisit only if sphere coastline realism becomes the top defect |
| R5 | Köppen lift (A) re-bases `content_hash` again | **Known cost** — every terrain/climate change re-bases the determinism hash | Acceptable per prior precedent; pin the new hash as the regression lock in the same ship |
| R6 | Köppen on flat used 2D continentality (edge-dist grid); sphere needs great-circle distance-to-ocean | **OPEN design detail for A** | The 5-layer *design* lifts; the distance metric must be re-derived on the sphere (do not copy the flat 2D grid — that was HIGH-1 in the civ-layer review) |

R6 is the concrete "doubt the substrate" trap for candidate A: the flat
continentality term is a 2D pixel-grid BFS; on the sphere it must be a
great-circle distance-to-ocean. Lift the **layer architecture**, re-implement
the **distance metric**.

---

## 7 — C-1 DESIGN (session 98 CLARIFY/DESIGN, no code) — grounded in the actual substrate

Investigated the real code to resolve D1-D4. **Key discovery: the connectivity +
top-tier partition machinery already exists** — C-1 is mostly *assembly of
existing primitives*, not new partitioning. This makes C-1 lower-risk than the
"L" estimate suggested.

### 7.1 — Existing primitives C-1 reuses (verified)

| Primitive | Where | What it gives C-1 |
|---|---|---|
| `pathfind::land_components(&is_land, neighbors)` | used by [`political.rs:29`](../../../crates/world-gen/src/political.rs#L29) | **Continents** = connected land masses. Already deterministic, already in the pipeline |
| `feature::components(biome, neighbors, kind)` | [`feature.rs:66`](../../../crates/world-gen/src/feature.rs#L66) | **Ocean basins** = connected ocean components (already extracted as `water_bodies`) |
| `plates.plate_of` + `Plate{kind}` | [`plates.rs:64-76`](../../../crates/world-gen/src/plates.rs#L64) | **Subcontinents** = continent ∩ plate (cratonic/tectonic subdivision) — reuse, no new partition |
| warped nearest-seed dot-product | [`plates.rs:99-114`](../../../crates/world-gen/src/plates.rs#L99) | **Regions** = great-circle Voronoi pattern to copy (lighter than `mesh.rs` full Voronoi) |

### 7.2 — The geometric hierarchy (3 levels)

```
L0  Continent     = pathfind::land_components (land cells)        [REUSE]
                    Ocean basin = feature::components(Ocean)       [REUSE]
L1  Subcontinent  = Continent ∩ plate_of                          [REUSE plate layer]
                    (a continent over K continental plates → K subcontinents;
                     geologically = cratons. Single-plate large continents:
                     optional great-circle Voronoi split — see open Q)
L2  Region        = great-circle Voronoi within each subcontinent  [NEW, lightweight]
                    (seed-nearest dot test, plates.rs pattern; count scale/knob)
```

### 7.3 — Design decisions resolved

- **D1 / R7 — RESOLVED: reuse, don't re-partition.** L0 = `land_components`,
  L1 = `continent ∩ plate_of`. Only L2 introduces new geometry. This avoids the
  "parallel partition duplicating `plates`" trap (R7) by construction.
- **D4 — RESOLVED: copy the `plates.rs` warped nearest-seed pattern** for L2,
  not `mesh.rs` full spherical Voronoi. Lighter, proven, deterministic. **R6
  trap avoided** — this is great-circle (3D dot product), never flat's 2D grid.
- **D3 — RESOLVED: WRAP, do not replace.** C-1 emits a NEW hierarchy layer on
  `WorldMap` (parent links + per-cell `region_of`/`subcontinent_of`/
  `continent_of`); `political` province/state stay untouched. C-2 later
  re-anchors province under region. The C-1↔C-2 seam = the parent-link IDs,
  designed now.
- **D2 — PARTIAL.** L0/L1 counts are emergent (no param). L2 region count is the
  one knob — recommend a `CreativeSeed` field (scale-aware default), mirroring
  how `plate_count` works.

### 7.4 — Data model (proposed, for session 99 spec)

New `WorldMap` fields (all feed `content_hash`; pin the re-base):
- `continent_of: Vec<u32>`, `subcontinent_of: Vec<u32>`, `region_of: Vec<u32>`
  (per-cell, parallel to `cells`)
- `regions: Vec<Region>` where `Region { id, subcontinent, seed_cell }`,
  `subcontinents: Vec<Subcontinent { id, continent, plate }>`,
  `continents: Vec<Continent { id, kind: Land|Ocean, seed_cell }>`
- Mirror the `Province`/`State` shape (id + parent + `#[serde(default)] name`
  excluded from hash) so naming + C-2 anchoring compose the same way.

### 7.5 — Determinism

Index-ordered flood-fills + ascending-id tie-breaks (same discipline as
`feature.rs` / `plates.rs`). `content_hash` re-bases once (new fields); pin the
new hash as the regression lock in the C-1 commit — standard precedent.

### 7.6 — PO sign-off (session 98) — RESOLVED

1. **Single-plate continent at L1** — **ACCEPTED**: one subcontinent is fine;
   defer any size-threshold Voronoi split to a later tuning pass.
2. **L2 region count source** — **ACCEPTED**: a `CreativeSeed` knob (scale-aware
   default), mirroring `plate_count`.
3. **Render in C-1** — **PO chose model-first**: split C-1 into
   - **C-1a (session 99)** — data model + hierarchy + tests + pinned hash.
     **No render.** VERIFY via JSON round-trip + structural tests (every cell
     has a valid continent/subcontinent/region id; parent links consistent;
     determinism). **Caveat (lesson — fixed-shape mocks/tests can mask bugs):**
     model-only VERIFY can't *see* a mis-partition, so the structural tests must
     be strong — assert partition invariants (no orphan cells, region ⊆
     subcontinent ⊆ continent, counts > 0 per level), not just "it serializes."
   - **C-1b (later)** — `--region-png` 3-tier choropleth for visual verification.

### 7.7 — Revised size + staging

- **C-1a** — **M**: L0/L1 are reuse, L2 + data model + tests are the new work.
  One cycle. *Session 99.*
- **C-1b** — **S**: render only. Later.
- **C-2** (political tiers world→realm→nation→province→county) — **L–XL**, the
  larger later sub-phase; re-anchors `province` under `region`.

---

## 8 — What this plan does NOT do

- No code shipped this session (per session 98 directive).
- Does not delete the flat track — it is frozen + harvested, kept as reference.
- Does not write the C-1 spec — that is session 99's CLARIFY/DESIGN output
  (XL → dedicated spec + plan file). This doc is the parent rationale only.
- **Direction is LOCKED (§4.2): C3 — geometric frame first (C-1, session 99),
  then political tiers (C-2, later).** Candidates A (Köppen) and B (visual audit)
  are not dropped — they remain available later; the flat climate harvest (A)
  is still the cheapest standalone win whenever colour monotony becomes the top
  defect.
