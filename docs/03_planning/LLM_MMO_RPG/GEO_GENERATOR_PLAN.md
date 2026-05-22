# GEO World-Map Generator — Build Plan

> **Purpose:** a **standalone procedural world-map generator** — `generate(seed, CreativeSeed) → WorldMap`. A Rust **library crate + thin CLI**. Decoupled from the LLM MMO RPG engine: **no DP-kernel, no event sourcing, no aggregates, no foundation tier.**
>
> **Why this exists:** the goal is a *map generator*, not the MMO. The `V1_30D_IMPLEMENTATION_PLAN.md` + the foundation program were scoped to the full event-sourced engine — **superseded** for this goal. The GEO design docs remain the *algorithm spec*; the engine machinery around them is dropped (§1).

---

## Current status & next session (handoff)

**As of 2026-05-21 — branch `geo-generator-amaw`, pushed.** The 4-phase
generator is built, the post-build human-in-loop review is done, seven
enhancements + the **world-tier sphere migration (Phase 1 stages A + B-1)**
have shipped — each via the full default 12-phase v2.2 workflow
(`/review-impl` on enhancements 3–6):

| Work | Commit |
|---|---|
| Path A — relief render (hillshade · fBm detail · realistic/atlas styles) | `be6047fe` |
| Path B — ridged-noise heightmap (killed the bullseye terrain) | `1bfa54e0` |
| Orographic climate — wind-driven rain shadow (`--wind` knob) | `13ea0999` |
| Feature naming — extraction + LLM `name` step + SVG labels | `d0e608e3` |
| Hydraulic erosion (Path B v2) — two-phase stream-power carve/settle (`--erosion`) | `addd9f16` |
| Render polish — supersample 2× · complementary detail · concavity occlusion | `46a32e1c` |
| Huge-scale benchmark — `WorldScale::Gigaplanet` (~501k cells) + criterion bench | `a156be69` |
| World-tier redesign Phase 1 stage A — sphere mesh + 3D Perlin terrain (kills the rectangle) | `1433f045` |
| World-tier redesign Phase 1 stage B-1 — `Projection` enum + native-3D consumer migration (climate / hydrology / political / settlement / routes / culture; great-circle distances; `(u,v)` adapter dropped) | `0a5387b1` |
| World-tier redesign Phase 1 stage B-2 — `Projection` threaded through render+relief; Orthographic globe view actually renders; relief sampler rewritten (per-pixel back-project → nearest cell); 3D detail/warp fBm; `delaunator` dropped; CLI `--projection`/`--camera` | `4f10b557` |
| World-tier redesign Phase 2 — plate tectonics: NEW `plates.rs` (seed → spherical Voronoi → continental/oceanic kind → tangent motion → 6-way boundary classify → orogeny-uplift BFS); `TerrainMode` enum (Tectonic default / Profile legacy); `plate_count`+`continental_fraction` knobs; plate layer on `WorldMap`; `plate_image` render + `--plate-png` | `2bb5436f` |
| Phase 2 quality pass — fast hull (O(N²) Quickhull → O(N log N) stereographic+Delaunay, gigaplanet 620s→25s); auto-sized output (aspect-correct, cell-count-driven, `--detail`/`--height`); Earth-like signed hypsometry; plate-boundary warp (irregular continents); fixed-sea percentile-stretch quantization (distinct plains/uplands/peaks) | `ce87bdcb` |
| **Terrain-coherence pass — altitude-driven ruggedness field (Musgrave "statistics by altitude") gating relief detail + erosion incision (flat plains, jagged mountains); ocean depth-by-coast-distance curve (shelf→abyssal flat, replaces lumpy fBm); coast-distance arc gate (offshore island arcs, no continent-welding); fixed-scale quantize (flat worlds stay green). Removed boundary-proximity ruggedness — it ringed every coast with a thin high "pen-stroke" ridge.** | HEAD of `geo-generator-amaw` |

**Phase 1 + 2 COMPLETE + a quality pass.** The quality pass was driven by PO
visual review against a real Earth relief map. Key wins: the generator now
affords gigaplanet (501k cells) in ~25s; output dimensions scale with cell
count + projection aspect (no more fixed-square "compression"); and terrain
has **Earth-like hypsometry** (sea pinned at 0.40 of the range, land
percentile-stretched to fill 0.40→1.0 → green plains / brown uplands / white
peaks / deep ocean, all *distinct*). The min-max normalize that squeezed all
land into the top 20% of the range (the "flattened terrain" bug) is fixed.
`content_hash` rebased again (mesh + terrain algorithm changes).

> **✅ RESOLVED (2026-05-22) — terrain-coherence pass.** The "noisy / no flat
> plains" blocker is fixed. Implemented per
> [`docs/plans/2026-05-22-geo-terrain-coherence-spec.md`](../../plans/2026-05-22-geo-terrain-coherence-spec.md):
> an **altitude-driven ruggedness field** (Musgrave "statistics by altitude")
> gates relief detail + erosion incision → macro-flat plains, jagged mountains;
> ocean depth follows a **coast-distance curve** (shelf → abyssal flat) instead
> of uniform fBm; a **coast-distance arc gate** keeps island arcs offshore so
> shelf+uplift no longer welds continents. Verified at gigaplanet (501k cells):
> plains local slope 71–73 vs mountains 5944–6735 (**84–92× contrast**), ocean
> smooth, continents separated, seeds 7 & 555 distinct. 158 tests + clippy
> clean. **Note:** ruggedness was *not* derived from plate-boundary proximity
> (the spec's first idea) — that rings every continent/ocean coast with a thin
> high "pen-stroke" ridge (a coast *is* a plate boundary); altitude-driven is
> geologically correct. Tradeoff: hypsometry is now ~98% lowland (flatter than
> Earth's 62/23/6) — deliberate, per PO's "everything too bumpy" steer; the
> mid-band rolling-uplands is a one-knob tweak if wanted later. **Next: PO will
> intervene directly in the algorithm; then Phase 3 Köppen climate** (the
> remaining all-green colour monotony is climate, not relief).

> **⚠ Architectural realisation (2026-05-18).** The Gigaplanet benchmark made
> it clear: **cell count is resolution, not scope.** A 501k-cell map still
> "feels like a province," because the generator is structurally a
> *region* generator — one `CoastlineProfile` = one landmass, one hemisphere
> climate slice, ~80 provinces / 12 states. `WorldScale` only ever changed how
> finely that *one region* is subdivided. A real world needs a **tier above**:
> a world frame with multiple continents + ocean basins, a global climate
> model (full latitude banding, multiple wind cells), hierarchical political
> (world → realms → nations → provinces), and a far wider terrain vocabulary —
> the **geo-type redesign** (Earth terrain + fantasy: great rift, lava world,
> shattered world). This is the next major work.

**Spec locked + Phase 1 stage A done (2026-05-20).** PO reviewed
[`GEO_WORLD_TIER_REDESIGN.md`](GEO_WORLD_TIER_REDESIGN.md) and chose **true
sphere** over cylinder (§3), two-level fantasy split (§6c), default §8 phase
order, and spec-default scale targets — 4 of 5 §9 open questions resolved;
Q3 (tier-2 persistence) deferred to Phase 5. Phase 1 stage A then landed
the sphere foundation:

- `mesh.rs` rewritten: **Fibonacci-lattice sample + 3D Quickhull + spherical
  Voronoi polygons**. No edges, no E-W seam, no pole degeneracy — wrap is
  automatic.
- `Cell.center` migrated from `(f32, f32)` 2D plane to `[f32; 3]` 3D unit
  sphere; `Cell::lat()` / `Cell::lon()` derived; `compute_hash` reshaped.
- `noise.rs` gained `gradient_noise_3d` + `fbm_3d` + `ridged_fbm_3d` (Marsaglia
  uniform-on-sphere gradients; trilinear blend with smootherstep fade).
- `terrain.rs` rewritten: **3D Perlin heightmap**, sampled at unit-sphere
  points — naturally seamless across the antimeridian (proven by the new
  `height_at_is_continuous_across_the_antimeridian` test). `CoastlineProfile`
  heuristics reframed with great-circle distance + sphere-distributed
  Archipelago discs.
- `climate.rs` `effective_latitude` swap — Northern/Southern logic flipped to
  match the new equirectangular (u, v) convention (v=0 at north pole).
- `lib.rs` (u, v) adapter scaffold lets `climate` / `hydrology` / `political`
  / `settlement` / `routes` / `culture` keep their legacy 2D signatures —
  migrated to native 3D in stage B alongside the `Projection` enum work.
- 98 lib unit tests pass; 7 determinism + 5 serde integration tests pass —
  `content_hash` re-baselined intentionally (sphere geometry ⇒ different
  bytes).

**Phases 1 + 2 are COMPLETE.** The generator is a genuine sphere (Fibonacci
mesh + 3D Quickhull + 3D-Perlin terrain + Equirectangular/Orthographic
projections) **and** a plate-tectonic planet: NEW `plates.rs` seeds N plates,
assigns cells by spherical Voronoi, marks each continental or oceanic, gives
each a motion vector, classifies every adjacent-plate boundary (fold mountain /
subduction / island arc / ridge / rift / fault), and builds a per-cell orogeny
uplift field that raises belts + carves trenches/rifts. `terrain.rs` branches
on `TerrainMode` (Tectonic default = plate base + uplift + dampened fBm
texture, no radial mask, no `enforce_coherence`; Profile = the legacy
single-continent path). The plate layer is exposed on `WorldMap` and rendered
by `plate_image` (`--plate-png`). Knobs: `--terrain-mode`, `--plate-count`,
`--continental-fraction`. Plan: [`docs/plans/2026-05-21-geo-phase2-plate-tectonics.md`](../../plans/2026-05-21-geo-phase2-plate-tectonics.md).
Try it: `world-gen generate --seed 7 --scale super-continent --out m.json
--relief-png globe.png --plate-png plates.png --projection orthographic
--camera 1,0.3,0.2`.

**Next session — TOP PRIORITY: fix the "noisy terrain / no flat plains"
quality blocker** (PO 2026-05-22). Before Phase 3, research + rework the noise
spectrum so the terrain has genuinely **flat plains** with relief
*concentrated* in mountain belts, instead of uniform per-cell jitter
everywhere (ocean floor included).

- **Research first:** how do games / DEM generators produce coherent flat
  plains + localized mountains? Reference points: ARK: Survival Evolved
  (sculpted + heightmap), Azgaar/MFCG, World Machine / Gaea (erosion +
  *ruggedness masks*), real DEM hypsometry. The common technique: a
  **ruggedness / amplitude field** that gates high-frequency detail — high
  near tectonic belts & coasts, ≈0 on cratonic plains & abyssal floor — so
  flat regions stay flat.
- **Likely rework:** in `terrain::tectonic_relief`, multiply the hills +
  ridged-detail terms by a low-frequency *ruggedness* mask derived from the
  plate-boundary distance (the `plates.uplift` BFS already has this) + a
  large-scale fBm, so cratonic interiors and abyssal plains are macro-flat
  while belts are rugged. Also damp the continental base variation on plains.
- Then proceed to **Phase 3 — global Köppen climate**
  ([`GEO_WORLD_TIER_REDESIGN.md`](GEO_WORLD_TIER_REDESIGN.md) §5b): insolation
  bands + elevation lapse + continentality (distance-to-ocean, plate cratons)
  + orographic shadow + wind cells + ocean currents → Köppen type per cell;
  biome widens to WWF/Whittaker (§6b). This adds the desert/forest/tundra
  *colour* diversity still missing vs a real Earth map.

Benchmark (release, post fast-hull): gigaplanet (501k cells) generate +
orthographic relief render ≈ **25 s** total (was 620 s+ with the O(N²) hull).

**Other open GEO enhancements** (surveyed, lower priority than the redesign):
16-bit heightmap export; deposition / sediment-fan refinement; archetype-
conditioned generation (`world_archetype` still inert — the redesign §6c gives
it meaning).

---

## Phase status board

| Phase | Title | Status |
|---|---|---|
| 0 | Scaffold (re-purpose the Cycle-0 `world-service` crate) | **DONE** (superseded — Phase 1 created `crates/world-gen` fresh; `services/world-service` + `services/travel-service` left orphaned for human cleanup) |
| 1 | Crate structure + core types + Voronoi mesh + heightmap | **DONE** (2026-05-17) |
| 2 | Climate + biomes + rivers | **DONE** (2026-05-17) |
| 3 | Political + settlement + route + culture | **DONE** (2026-05-17) |
| 4 | Serialization + image export + CLI + LLM CreativeSeed authoring | **DONE** (2026-05-17) |

**All 4 phases complete — the GEO world-map generator is built.** Phases were executed under **AMAW** per the project owner's call — the full 12-phase workflow with cold-start sub-agent reviews + `/review-impl` on each phase.

**Post-build review (2026-05-17):** a human-in-loop review — code + generated-map quality + design fidelity — followed. 20 findings (3 HIGH/MED route-network defects + coverage / fidelity / doc gaps), all fixed across 3 commits. See [`docs/audit/geo-review-2026-05-17.md`](../../audit/geo-review-2026-05-17.md).

**Render quality — Path A (2026-05-17):** a render-only quality overhaul of the PNG export, after a low-fidelity-output review. The renderer is *not* part of `WorldMap` / `content_hash`, so the model is untouched (content hash byte-identical before/after). NEW `noise.rs` (hand-rolled Perlin gradient noise + fBm) + `relief.rs` (a `ReliefField` engine: render-time re-triangulation, barycentric elevation rasterization, box-blur de-faceting, domain warp, fBm detail, NW hillshade). `render.rs` gained a hypsometric `relief_image` and composites the hillshade over the biome / political / culture maps; `land_sea_image` removed. CLI: `--style realistic|atlas` + `--relief-png`. +15 tests (83 green, 1 ignored), clippy clean. Plan: [`docs/plans/2026-05-17-geo-relief-render.md`](../../plans/2026-05-17-geo-relief-render.md). Path A fixes the flat-mosaic + no-relief *render* defects; the blob-bullseye *model* defect (`terrain::grow_blob`'s radial heightmap) is **Path B**.

**Heightmap rework — Path B (2026-05-17):** the model-side fix. `terrain::grow_blob` (radial blob seeds → concentric "bullseye" mountains) is replaced by `height_at(x,y)` — a global continuous heightmap function sampled at each cell centre: a low-frequency fBm continent base, ridged-multifractal mountain ranges (sharp linear ridgelines, not radial cones) gated by a belt mask + a landness gate, mid-frequency hills, all domain-warped, plus the optional Inland dome. `noise.rs` gained `ridged_fbm` and now joins the deterministic model; `grow_blob` / `nearest_cell` / `erode` removed. The coastline-profile masks, connectivity-aware sea level, and land-coherence enforcement are unchanged. `content_hash` changes (intentional algorithm change) — the determinism invariant holds. 88 tests green (+5), clippy clean. Plan: [`docs/plans/2026-05-17-geo-path-b-heightmap.md`](../../plans/2026-05-17-geo-path-b-heightmap.md). Hydraulic erosion (carved valleys / dendritic drainage) is **Path B v2**, deferred.

**Orographic climate (2026-05-17):** the first GEO enhancement after the Path A/B render + heightmap work. A new `PrevailingWind` knob on `CreativeSeed` (8 compass directions; CLI `--wind`, LLM-author-settable, `#[serde(default)] = West`). `climate.rs` replaced its pure ocean-distance `dry` input with a wind-driven moisture march (`moisture_field`): air enters moist from the windward sea, recharges over water, and bleeds away over land — a small overland leak (continentality) plus a strong orographic loss wherever terrain climbs — so the lee of a mountain range falls into a dry rain shadow. `dry = 1 − moisture` feeds the existing classifier; biomes and rivers improve downstream for free. `ocean_distance` removed. `content_hash` changes (intentional). 92 tests green, clippy clean; `/review-impl` raised 6 findings (no HIGH) — all fixed. Plan: [`docs/plans/2026-05-17-geo-orographic-climate.md`](../../plans/2026-05-17-geo-orographic-climate.md).

**Feature naming (2026-05-17):** the second GEO enhancement — turns the anonymous heightmap into a *named world*. Two stages: (1) deterministic **feature extraction** (`feature.rs`) — `generate` now flood-fills the biome field into discrete `MountainRange` / `River` / `WaterBody` entities (their geometry feeds `content_hash`); (2) a separate non-deterministic **LLM naming step** (`naming.rs`) — `name_world` makes one json-schema-constrained call and applies names by `zip`. `Settlement` / `Province` / `State` / `CultureRegion` + the 3 new types gained `name: String`; the `name` fields are **excluded from `content_hash`** (a documented carve-out, double-tested) so `generate` stays pure and a named map verifies the same hash as the unnamed one. New `name` CLI subcommand; `political_svg` gained XML-escaped `<text>` labels; `author.rs` factored a shared `llm_json_request`. 103 tests green, clippy clean; `/review-impl` raised 7 findings (no HIGH) — all fixed. Plan: [`docs/plans/2026-05-17-geo-feature-naming.md`](../../plans/2026-05-17-geo-feature-naming.md). PNG text labels (glyph rasterisation) deferred.

**Hydraulic erosion — Path B v2 (2026-05-18):** the third GEO enhancement — carves the raw Path B heightmap. NEW `erosion.rs`: a two-phase stream-power landscape-evolution pass run inside `terrain::build` on the f32 elevation field (after `apply_falloff`, before u16-normalization — quantized steps would round to zero). Each iteration runs its own `f32` priority-flood (Barnes depression-fill, `total_cmp`-ordered heap), adopts the *filled* field (a raw heightmap is pit-riddled — incising it directly is a near no-op), accumulates uniform-rain drainage area, then incises `K·area^m·slope` (clamped to the receiver drop). The **carve phase** is pure incision (cuts dendritic valley networks); the **settle phase** then adds transport-capacity deposition — `settle_rate` of the load above `Kc·area^m·slope` is dropped (valley-floor fill / mountain-front fans). The two-phase split is load-bearing: deposition during the violent carve refills valleys faster than they cut. Hillslope diffusion rounds ridge crests. A NEW `ErosionStrength` knob (None/Light/Moderate/Heavy, default Moderate, `#[serde(default)]`) on `CreativeSeed` — `--erosion` CLI flag + LLM-author schema. Incision is clamped to never carve land below the provisional waterline (no sub-sea speckle); **Archipelago is skipped** (`terrain::build` gate — incision carving a strait would dissect its fixed 5-disc invariant, mirroring `enforce_coherence`/`choose_sea_level`). `content_hash` changes for the 4 non-Archipelago profiles (intentional). 112 tests green (+9), clippy clean. Default v2.2 workflow, human-in-loop; the deposition model was redesigned mid-VERIFY (Davy-Lague `G/area` → two-phase transport-capacity) on a PO call after the first model refilled valleys. Plan: [`docs/plans/2026-05-18-geo-hydraulic-erosion.md`](../../plans/2026-05-18-geo-hydraulic-erosion.md). Sharper sediment fans (finer mesh / multi-flow routing) and 16-bit heightmap export deferred.

**Render polish (2026-05-18):** the fourth GEO enhancement — render-only, no `WorldMap`/`content_hash` change. The relief renderer was masking model-scale detail (erosion valleys, Path B ridges, orographic relief): it blurred the barycentric base by ~½ cell to de-facet it, then overlaid fBm detail of *larger* amplitude than the model signal, modulated *up* on highlands. Three fixes. (1) **Supersampling 2×** — every `*_image` renders at `SS×` then box-`downsample`s; anti-aliases coastlines, hillshade and Voronoi edges (route lines stamped `SS`-thick, dots `SS`-scaled, the Atlas ink coastline `SS`-thick — the last caught by `/review-impl`). (2) **Complementary detail** — `relief.rs build` is now two-pass: warp→`base`, then a `base − blur(base)` high-pass measures local model relief; detail fBm *fills* flat ground and *recedes* over carved structure (`detail_fill`), and `detail_amp` is lowered. (3) **Concavity occlusion** — valley floors (negative high-pass) are darkened, an ambient-occlusion proxy that makes carved drainage read. The de-facet blur was cut to ⅓ cell; the hypsometric palette + coastal shallows retuned. 114 tests green (+2), clippy clean; `/review-impl` raised 1 MED (Atlas coastline) + 5 LOW/COSMETIC — MED fixed, rest accepted. Plan: [`docs/plans/2026-05-18-geo-render-polish.md`](../../plans/2026-05-18-geo-render-polish.md). The "renderer masks model detail" limiting factor flagged after erosion is resolved.

**Huge-scale benchmark (2026-05-18):** the fifth GEO enhancement — a NEW `WorldScale::Gigaplanet` (708² grid = 501,264 cells, `tag` 5, ~30× `Megaplanet`) + a criterion benchmark (`benches/generate.rs`, `cargo bench`, `criterion` dev-dep) timing `generate` across all six scales + a `relief_image` render. CLI `--scale gigaplanet`, LLM-author schema synced. The five existing scales' `grid_side`/`tag` are untouched → no `content_hash` shift. `structure.rs` gained a dedicated `gigaplanet_generates_a_coherent_map` test (`#[ignore]` — two 501k-cell generates run minutes in a debug build; run with `--release -- --ignored`); the slow `SCALES` sweep stays at five scales. **Benchmark (release):** generate 6.2/12.6/45/56/91 ms for Pocket–Megaplanet, **8.5 s** at Gigaplanet; relief render ~14 s — super-linear (O(n log n) stages + erosion's iterative priority-flood) but not O(n²). 114 tests green (+0 run, +1 ignored), clippy clean. Plan: [`docs/plans/2026-05-18-geo-huge-scale-benchmark.md`](../../plans/2026-05-18-geo-huge-scale-benchmark.md). **The showcase render is what triggered the architectural realisation above** — a 501k-cell map still reads as one province, because the generator's scope is one region regardless of cell count.

### Phase 1 — build log (2026-05-17)

`crates/world-gen/` — library `world_gen` + CLI bin `world-gen`. 9 source files + 2 integration tests, 19 tests green, `cargo clippy --all-targets` clean. Voronoi dual-mesh (perimeter ring + jittered interior → `delaunator` Delaunay → degree-repaired adjacency); Azgaar blob+radial-falloff heightmap; blake3+ChaCha8 determinism with a `content_hash` gate. AMAW: 3 design-review rounds (r1/r2 REJECTED → r3 APPROVED_WITH_WARNINGS), 2 code-review rounds (r1 REJECTED — land-coherence held on only some seeds → r2 APPROVED_WITH_WARNINGS), `/review-impl` (1 MED + 4 LOW), Scope Guard CLEAR. Phase 4 LLM authoring will use `ibm/granite-4-h-tiny` via LM Studio. One deferred item: `DEFERRED.md` #013 (land-fraction precision → Phase 2). Phase 4's optional LLM authoring is **in scope** for this run.

### Phase 2 — build log (2026-05-17)

Stages 3–4: `climate.rs` (latitude×elevation×ocean-distance → 8 `ClimateZone`), `hydrology.rs` (Barnes priority-flood depression fill → flow accumulation → `river_flux`; ocean/lake water network), `biome.rs` (14-`BiomeKind` matrix). `CreativeSeed` gained `hemisphere_orientation` + `climate_bias`; `WorldMap` gained `climate`/`biome`/`river_flux`/`is_coast`; CLI `--png` now renders biomes. 40 tests green, clippy clean. **DEFERRED #013 cleared** — connectivity-aware sea-level binary search + a continental base dome for the high-land `Inland` profile. AMAW: 2 design rounds (r1 REJECTED 2 BLOCK → r2 APPROVED_WITH_WARNINGS), 2 code rounds (r1/r2 APPROVED_WITH_WARNINGS — a code-review WARN fix surfaced + fixed a real `Inland` land-fragmentation BLOCK), `/review-impl` (1 MED + 3 LOW), Scope Guard CLEAR.

### Phase 3 — build log (2026-05-17)

Stages 5–8 (task size **XL**), pure-procedural: `pathfind.rs` (deterministic integer-cost multi/single-source Dijkstra, BFS, largest-remainder apportionment, union-find), `political.rs` (province terrain-cost flood-fill + nearest-state-seed clustering), `settlement.rs` (burg-score Poisson-disk + role assignment), `routes.rs` (Road MST+augmentation, Trail, SeaLane, MountainPass, RiverNavigation), `culture.rs` (barrier flood-fill). `CreativeSeed` gained `settlement_density` + `culture_count`; `WorldMap` gained `province_of`/`provinces`/`states`/`settlements`/`routes`/`culture_of`/`culture_regions`; CLI gained `--political-png`. 50 tests green, clippy clean. AMAW: 3 design rounds (r1/r2 REJECTED — archipelago multi-component + quota apportionment → r3 APPROVED_WITH_WARNINGS), 2 code rounds (both APPROVED_WITH_WARNINGS), `/review-impl` (1 MED + 3 LOW). A union-find-on-distance state-clustering bug (degenerate to 1 state) was caught at VERIFY by the political-map render and fixed with nearest-state-seed assignment. Scope Guard CLEAR.

### Phase 4 — build log (2026-05-17)

`WorldMap` ⇄ JSON round-trip with `compute_hash`/`verify_hash` (a loaded map is verified, not trusted — a hand-edited JSON fails the check); `render::political_svg` vector export; CLI restructured into `generate` / `author` clap subcommands with `--config` (load a `CreativeSeed` JSON) + `--svg`; `author.rs` — LLM CreativeSeed authoring via a `reqwest::blocking` call to an OpenAI-compatible endpoint with a `json_schema` response constraint, default `ibm/granite-4-h-tiny` at LM Studio. 65 tests + 1 `#[ignore]` LLM integration test (passes against LM Studio), clippy clean. AMAW: 3 design rounds (r1/r2 REJECTED — hash not re-derived after load, hash-move under-specified → r3 APPROVED_WITH_WARNINGS), 2 code rounds (r1 REJECTED — missing acceptance-criteria tests → r2 APPROVED_WITH_WARNINGS), `/review-impl` (3 LOW), Scope Guard CLEAR. The `author`→`generate --config` chain was verified end-to-end: a prose brief produced a schema-valid `CreativeSeed` that generated a valid map.

---

## §1 — Scope: kept vs dropped

**KEPT** — from GEO_001 / GEO_001b / POL_001 / SET_001 / ROUTE_001, the *algorithms and data*:
- The 8-stage generation pipeline (Voronoi → heightmap → climate → biome+rivers → political → settlement → route → culture).
- The closed enums: `ClimateZone` (8), `BiomeKind` (14), `WorldArchetype` (12), `WorldScale` (5), `RouteKind` (5), `SettlementRole`.
- The `CreativeSeed` creative-direction input model.
- The algorithmic baseline: Patel dual-mesh, Azgaar pipeline, O'Leary erosion (§5).

**DROPPED** — the MMO-engine coupling (the reason the foundation program was ever needed):
- The event-sourced `world_geometry` *aggregate* (T2/Channel) → replaced by a plain `WorldMap` value.
- `GeographyDelta` / delta-overlay editing, `geography.*` reject namespace, the validator pipeline, `schema_version`, snapshot-fork / multiverse, RealityManifest coupling, capability claims.
- The `world-service` *network service* framing → a **library crate + CLI** instead.

**The one invariant carried over:** **regeneration-determinism** — `generate(seed, creative_seed)` is a pure function; same inputs → byte-identical `WorldMap`. This is the core CI gate of every phase.

---

## §2 — Architecture

A library crate **`world_gen`** + a thin CLI bin **`world-gen`**. Re-purpose the Cycle-0 `services/world-service/` scaffold; Phase 1 may move it to `crates/world-gen/` (it is a library, not a service — recommended) or keep it in place — a Phase 1 call. *(The Cycle-0 `travel-service` scaffold is unrelated to this generator — leave it or delete it; orthogonal.)*

```
world_gen (lib)
  creative_seed   — the CreativeSeed input model (grows per phase)
  world_map       — the WorldMap output value + Cell + the closed enums
  mesh            — Voronoi dual-mesh partition + adjacency
  terrain         — heightmap · climate · biome · rivers
  political       — provinces · states
  settlement      — burg placement · role assignment
  routes          — road/trail/sealane/mountainpass/river network
  culture         — culture-region spread
  serde           — WorldMap (de)serialization
world-gen (bin)   — CLI: generate a map from a seed + config, dump JSON / image
```

One seeded RNG (`blake3`-derived per the design docs' determinism note) threaded through every stage. `WorldMap` carries a stable content hash for the determinism test.

---

## §3 — The 4 build phases

### Phase 1 — Crate structure + core types + mesh + heightmap
- **Builds:** the `world_gen` lib + `world-gen` CLI skeleton; `CreativeSeed` (geometry-relevant fields) + `WorldMap` + `Cell` + `WorldScale`/`WorldArchetype` enums; **Voronoi dual-mesh** partition (~1k–16k cells per `WorldScale`) + cell adjacency; **heightmap** (u16 elevation, Azgaar-style blob seeds + falloff) + land/sea threshold.
- **Design ref:** GEO_001 §5 stages 1–2.
- **Verify:** determinism (same seed → byte-identical mesh + heightmap); cell count within `WorldScale` bounds; neighbour degree 3–12; the CLI dumps a land/sea image showing a coherent continent.

### Phase 2 — Climate + biomes + rivers
- **Builds:** `ClimateZone` (8) from latitude (hemisphere) × elevation; rainfall → downhill flow accumulation → **rivers**; `BiomeKind` (14) from (climate × heightmap × river_flux) per the GEO_001 §5 derivation matrix.
- **Design ref:** GEO_001 §5 stages 3–4.
- **Verify:** determinism; biome derivation matches the matrix; rivers descend monotonically to sea/lake; no incoherent biome adjacency (GEO_001's HIGH-1 coherence concern); CLI dumps a biome-coloured map.

### Phase 3 — Political + settlement + route + culture
- **Builds:** stage 5 **provinces** (flood-fill from seeds) + **states**; stage 6 **settlements** (burg-score Poisson-disk weighted by habitability + role assignment Hamlet→Capital); stage 7 **routes** (Road via Dijkstra · Trail · SeaLane · MountainPass · RiverNavigation); stage 8 **culture-region** spread. `CreativeSeed` gains its political/culture fields.
- **Design ref:** GEO_002 POL_001 · GEO_003 SET_001 · GEO_004 ROUTE_001 (algorithm sections only).
- **Verify:** determinism; provinces partition the land totally; every state has exactly one capital; one-route-per-pair; roads connect settlements; CLI dumps a full political/road map.

### Phase 4 — Serialization + export + CLI + (optional) LLM authoring
- **Builds:** `WorldMap` ⇄ JSON (round-trip stable); image/SVG export; the full CLI (`world-gen --seed S --config creative_seed.json --out map.json [--png]`); **optional** GEO_001b authoring — `loreweave_llm` turns a prose brief into a schema-valid `CreativeSeed` JSON.
- **Design ref:** GEO_001 §6 (CreativeSeed) · GEO_001b.
- **Verify:** JSON round-trip identity; CLI end-to-end on a fixture seed; (optional) LLM authoring yields a `CreativeSeed` that re-generates a valid map.

---

## §4 — Per-phase workflow

Each phase runs the default 12-phase v2.2 workflow. The non-negotiables per `CLAUDE.md`:
- **Phase 6 VERIFY** — run the determinism test + the structural checks above with fresh evidence.
- **Phase 7 REVIEW** — 2-stage (spec compliance + code quality).
- **`/review-impl`** after BUILD — adversarial pass (the prior arc's discipline).
- **Phase 11 COMMIT** — set the phase `Status=DONE` on the board in the same commit.

Determinism is the load-bearing CI gate: a test that asserts `generate(seed, cfg)` is byte-identical across two runs, for every fixture seed, every phase.

---

## §5 — Algorithm references (all permissively licensed — per the GEO_001 2026-05-13 survey)

- **Patel dual-mesh** (Apache 2.0) — Voronoi/Delaunay mesh; Rust crates: `delaunator` / `spade`.
- **Azgaar Fantasy Map Generator pipeline** (MIT) — the heightmap → climate → biome → burg → route stage structure.
- **O'Leary hydraulic erosion** (MIT) — optional heightmap refinement.
- LLM-image-to-map approaches were **rejected** at design time (no regeneration-stability / adjacency-correctness) — the generator is structured-procedural, not generative-image.

---

## §6 — Relationship to the design track

- The GEO_001 / GEO_001b / POL / SET / ROUTE design docs stay as the **algorithm spec**; their event/aggregate/delta sections are simply not implemented here.
- `V1_30D_IMPLEMENTATION_PLAN.md` + `V1_30D_CYCLE_LOG.md` are **superseded for this goal** — retained only as a record, relevant only if the full event-sourced MMO is ever built.
- If the MMO is later built, this `world_gen` library is reusable as-is — the engine's `world_geometry` aggregate would *wrap* it (call `generate()` for the base, layer deltas on top). Building the standalone generator first is the right order regardless.
