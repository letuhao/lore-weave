# GEO_001 — World Geometry

> **Conversational name:** "World Geometry" (GEO). The procedural geographic substrate beneath MAP_001's visual layer. Voronoi cell partition (~10k cells per continent) + heightmap + climate + biome + (V1+ schema-reserved) political layer + settlement layer + route network + culture distribution + resource slots. Per-continent ChannelScoped T2 aggregate. Generated from `(seed, creative_seed)` reproducibly; edited via delta-overlay (admin canonization adds named ordered deltas); inherited by snapshot fork via reference + per-reality local deltas. V1 populates geometry/climate/biome layers; V1+ layers schema-reserved.
>
> **Category:** GEO — Geography Foundation (foundation tier; sibling of EF_001 + PF_001 + MAP_001 + CSC_001 + RES_001 + PROG_001)
> **Status:** **DRAFT 2026-05-13** (single-cycle: boundary lock claim + catalog + folder + main doc + boundary registration + lock release)
> **Catalog refs:** [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — owns `GEO-*` namespace (`GEO-A*` axioms · `GEO-D*` deferrals · `GEO-Q*` open questions)
> **Builds on:** [`06_data_plane/12_channel_primitives.md`](../../06_data_plane/12_channel_primitives.md) DP-Ch1..Ch10 (channel hierarchy provides per-continent scope) · [`03_multiverse/01_four_layer_canon.md`](../../03_multiverse/01_four_layer_canon.md) (L1/L2/L3 cascade — seed at L2, deltas at L3) · [`03_multiverse/03_fork_and_cascading.md`](../../03_multiverse/03_fork_and_cascading.md) MV6 (snapshot fork; deltas-at-fork-point copied) · [`07_event_model/`](../../07_event_model/) Option C taxonomy · [`MAP_001`](../00_map/MAP_001_map_foundation.md) (visual layer; positions derive from GEO V1+) · [`PF_001`](../00_place/PF_001_place_foundation.md) (cell-tier place semantic; PF-D7 procedural generation V1+ consumes GEO)
> **Resolves:** Strategy substrate gap (provinces / adjacency / terrain / settlements / routes / resources have no existing queryable SSOT — future STRAT_001 V2+ blocker) · LLM-context grounding gap (no per-region biome/culture/climate query for prompt assembly; LLM has to guess "where in the world is Lý Minh") · Procedural world bootstrap gap (RealityManifest declares `geography_seed + creative_seed`; GEO pipeline materializes; admin canonization edits via delta overlay) · Image-rendering input gap (MAP_002 V2+ LlmGenerated pipeline needs a structured world description; GEO's biome + climate + culture fields ARE that input)
> **Defers to:** future **STRAT_001 V2+** (strategy gameplay; consumes GEO political/settlement/route/resource layers) · future **TVL_001 V1+** (travel mechanics; consumes route distance + RouteKind) · future **EXPL_001 V2+** (exploration + fog-of-war; consumes cells + per-PC discovered set) · future **GEO_002 POL_001 V1+** (political layer generator) · future **GEO_003 SET_001 V1+** (settlement generator) · future **GEO_004 ROUTE_001 V1+** (route network generator) · future **GEO_005 V2+** (resource distribution generator) · **MAP_002 V1+** (orthogonal; renders GEO via fantasy-map LoRA image pipeline)

---

## §1 Why this exists

Three concrete gaps in the V1+ design surface that GEO_001 closes.

**Gap 1 — Strategy substrate has no queryable SSOT.** Strategy gameplay (Paradox / Civ / Total War class — sieges, supply lines, province ownership, trade routes, naval invasions, diplomatic axes) needs deterministic, queryable, regeneration-stable data: province graph with adjacency, terrain enum driving movement + combat modifiers, settlement nodes with strategic role, route edges with weights, sea zones with separate naval adjacency, chokepoints, resource distribution, culture/religion tags. No existing feature owns this. MAP_001 owns the *visual UI graph* (per-channel position + asset slots + navigable edges for player drill-down rendering); MAP_001 does NOT own the underlying geographic substrate. PF_001 owns *cell-tier semantic identity* (10 PlaceType variants per cell) without continent-scale geometry. The 2024–2025 survey of world-map generators concluded that **Red Blob Games' dual-mesh + Azgaar's algorithm pipeline (Voronoi → heightmap → climate → erosion → biomes → political growth → settlements → routes)** is still state-of-the-art for *structured* fantasy world geometry; LLM-image-to-map approaches fail strategy gameplay's regeneration-stability and adjacency-correctness requirements. GEO_001 is the schema lock for that substrate.

**Gap 2 — LLM-context grounding has no per-region query.** When prompt-assembly per S9 §12Y `[ACTOR_CONTEXT]` section says "Lý Minh is in cell `yen_vu_lau`", the LLM has to *guess* whether Yên Vũ Lâu is by the coast, in the mountains, in a tropical city, in a temperate village — guesses drift the canon. SPIKE_01 turn 5 surfaced this gap (PC location grounding required the LLM to invent geographic context). With GEO_001, the prompt-assembly path can join `cell_channel.metadata.cell_id → PF_001 place → district_channel → ... → continent_channel.world_geometry` and fetch the cell's `BiomeKind + ClimateZone + nearest_settlement_role + culture_tag` deterministically. This is plumbing not gameplay — but it is V1-blocking for canon-faithful prompt grounding once worlds extend beyond a single hand-authored cell.

**Gap 3 — World bootstrap has no procedural pipeline.** RealityManifest currently requires authors to enumerate every channel from continent through cell with `MapLayoutDecl` (MAP_001 §9) and `PlaceDecl` (PF_001 §9). For a single-cell starter world this is fine. For a Thần Điêu Đại Hiệp setting (multiple cities + traveling segments + canon geography across thousands of miles) it is impossible — the author can't hand-author 10k cells. GEO_001 introduces `geography_seed + creative_seed → world_geometry` procedural generation: author supplies seed + creative direction; pipeline produces ~10k Voronoi cells with biome/climate/heightmap; PF_001 procedural place generation (PF-D7, V1+) selects PlaceType per cell from biome; MAP_001 auto-positions (V1+) settlements as map_layout nodes. Admin canonization edits live as `GeographyDelta` entries layered on top — base map regenerates reproducibly from seed; edits don't jitter the world.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **WorldGeometry** | Aggregate `world_geometry` (T2 / Channel scope at continent channel) | One row per continent channel. Single aggregate with internal layered structure (geometry / climate / biome V1 populated + political / settlement / route / culture / resource V1 schema-reserved). |
| **CellGrid** | `Vec<GeoCell>` — ~10k Voronoi cells per continent (V1 cap 16k) | Each cell carries center coordinate + neighbor adjacency list + heightmap value + climate zone + biome. Generated deterministically from `(seed, creative_seed)` via Voronoi partition over Poisson-disk sample (per Patel dual-mesh). NOT a DP channel — cells are rows under the world_geometry aggregate; the DP `cell` channel level (where gameplay sessions live) is a separate concept and maps to ONE GeoCell via `cell_channel.metadata.geo_cell_id` FK. |
| **GeoCellId** | Newtype `pub struct GeoCellId(pub(crate) u32)` (per-continent dense u32; module-private constructor) | Dense small integers (0..16384) make adjacency lists compact. Distinct from `ChannelId` (which is per-reality UUID) — these are internal handles within the continent's geometry. |
| **HeightmapValue** | `u16` (0..65535) per cell | Sea level threshold at deterministic value (default 32768); below = water cell. Plates + thermal/hydraulic erosion shape values during generation (§5). |
| **ClimateZone** | Closed enum 8 variants (§4) | Per-cell climate band derived from latitude (continent-relative) + altitude (heightmap-derived) + ocean-distance. Latitude convention: continent y-axis 0=north pole, MAX=south pole; northern-hemisphere realities flip via `creative_seed.hemisphere_orientation`. |
| **BiomeKind** | Closed enum 14 variants (§4) | Per-cell biome derived from `(climate, heightmap, river_flux)`. The deterministic-function mapping (climate × elevation × moisture → biome) is part of the V1 generator contract — same inputs ALWAYS produce same biome. |
| **RiverFlux** | `f32` per cell (V1 minimum) | Hydraulic-erosion-derived water flow accumulator. Cells with `river_flux > river_threshold` materialize as Biome::River; coast cells (water-adjacent land) get `is_coast=true` regardless of biome. |
| **Province** | Named cell-cluster (V1 schema-reserved; V1+ POL_001 populates) | Logical strategic unit. V1: aggregate has `provinces: Vec<Province>` declared but empty. V1+ POL_001 populates via priority-queue flood-fill from capital seeds. Each Province has ProvinceId + name + member GeoCellIds + capital_settlement_id + state_id. |
| **Settlement** | Burg with strategic role (V1 schema-reserved; V1+ SET_001 populates) | V1: aggregate has `settlements: Vec<Settlement>` declared but empty (or minimal — only what `creative_seed.named_settlements` declares). V1+ SET_001 weighted placement. SettlementRole closed enum reserved (Hamlet / Village / Town / City / Capital / Fortress). |
| **Route** | Typed edge over GeoCell adjacency (V1 schema-reserved; V1+ ROUTE_001 populates) | V1: aggregate has `routes: Vec<Route>` declared but empty. V1+ ROUTE_001 Dijkstra over terrain cost. RouteKind closed enum reserved (Road / Trail / RiverNavigation / SeaLane / MountainPass). |
| **CultureRegion** | Cell-set tagged with CultureTag (V1 schema-reserved) | V1: aggregate has `culture_regions: Vec<CultureRegion>` declared but empty. V1+ feature populates via culture-spread sim (priority-queue flood-fill from cultural-hearth cells defined by `creative_seed.culture_hints`). |
| **ResourceTag** | Reserved slot per Province (V2+ populated) | V1: aggregate has `province.resources: Vec<ResourceTag>` declared but empty. V2+ GEO_005 resource distribution generator populates via climate × biome conditioned Poisson-disk. Each ResourceTag references RES_001 ResourceKind for downstream production-base derivation. |
| **GeographySeed** | `pub struct GeographySeed { master_seed: u64, voronoi_seed: u64, climate_seed: u64, erosion_seed: u64, political_seed: u64, settlement_seed: u64 }` (sub-seeds derived from `master_seed` via blake3) | Sub-seed split enables stage-independent regeneration (e.g., re-run political layer with different `political_seed` while keeping geometry stable). Authoring contract: author declares `master_seed`; sub-seeds derive deterministically. |
| **CreativeSeed** | LLM-supplied creative direction (§6) | Pre-generation constraints feeding the procgen pipeline — region archetypes, naming styles per culture, lore hooks per region, ideological flavor, hemisphere orientation, biome preferences. NOT post-hoc decoration. |
| **GeographyDelta** | Named ordered edit applied on top of base map (§7) | Admin canonization (Forge:EditGeographyDelta). DeltaKind closed enum 6 V1: AddNamedSettlement / RenameRegion / SetBiomeOverride / AddRoute / RemoveRoute / SetResourceOverride. Replay = base + deltas in order. Atomic per-event. |
| **WaterCellTag** | Per-cell flag derived from heightmap < sea_level OR biome ∈ {Ocean, Lake, River} | Single Voronoi mesh; water cells tagged. Naval adjacency derived by clustering connected water cells; navigable_river adjacency derived from `river_flux > navigable_threshold`. Per §8 (sea zone model — single mesh, NOT separate Paradox-style land/sea graphs V1; V2+ migration tracked GEO-D6). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

GEO_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| GEO event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Geometry birth at RealityManifest bootstrap | **EVT-T4 System** | `GeographyBorn { channel_id, continent, seed, creative_seed_hash, voronoi_cell_count, generator_pipeline_version }` | DP-Internal RealityBootstrapper (Synthetic actor) | Emitted at reality bootstrap alongside PF_001 PlaceBorn (cell tier) + MAP_001 LayoutBorn. One per continent channel. The `creative_seed_hash` and `generator_pipeline_version` fields enable replay-determinism CI: same hash + same pipeline version = same world (per EVT-A9 probabilistic generation determinism). |
| Geometry state delta (delta append, base regen, layer activation) | **EVT-T3 Derived** | `aggregate_type=world_geometry` (field delta) | Aggregate-Owner role (world-service post-validate) | Causal-ref to triggering EVT-T8 Administrative (Forge geography edit) OR EVT-T4 GeographyBorn (initial materialization). |
| Author-edit geography delta via Forge | **EVT-T8 Administrative** | `Forge:EditGeographyDelta { continent_channel_id, delta_kind, delta_payload, prev_delta_id }` | WA_003 Forge | Audit-grade. DeltaKind enum V1: AddNamedSettlement / RenameRegion / SetBiomeOverride / AddRoute / RemoveRoute / SetResourceOverride. `prev_delta_id` enforces ordered append (idempotent retry-safe). |
| Snapshot fork: copy deltas at fork-point | **EVT-T4 System** | `GeographyForkInherited { child_reality_id, parent_continent_channel_id, fork_point_event_id, copied_delta_count }` | DP-Internal SnapshotForker (Synthetic actor) | One per forked continent. Copies parent's `geography_deltas[..fork_point]` as child's initial delta list. New child deltas append on top; parent's post-fork deltas do NOT cascade. **(MED-2 fix)** Reclassified EVT-T8 Administrative → EVT-T4 System: producer is DP-Internal not Forge admin; `Forge:` prefix dropped; lives in EVT-T4 sub-type registry NOT §4 EVT-T8 sub-shapes table. |
| LLM-derived narrative geography hook (V1+) | **EVT-T6 Proposal** | `GEO:CreativeSeedExtension` (V1+ reservation) | future LLM CreativeSeed-extender Generator | V1: scope-out — `creative_seed` is fixed at reality creation. V1+ extension: LLM proposes additional cultures/regions narratively (Forge admin reviews + materializes via T8). Reservation only V1. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. EVT-T4 System sub-types row gains `GeographyBorn` AND `GeographyForkInherited` (GEO_001-owned alongside EF_001 EntityBorn / PF_001 PlaceBorn / MAP_001 LayoutBorn / others); EVT-T3 Derived sub-types row gains `aggregate_type=world_geometry`; EVT-T8 Administrative sub-shapes registry (`_boundaries/02_extension_contracts.md` §4) gains `Forge:EditGeographyDelta` ONLY (`GeographyForkInherited` is EVT-T4 System, NOT §4-listed per MED-2 fix).

---

## §3 Aggregate inventory

One aggregate owned by GEO_001:

### 3.1 `world_geometry` (T2 / Channel-continent) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "world_geometry", tier = "T2", scope = "channel")]
pub struct WorldGeometry {
    pub channel_id: ChannelId,                              // primary key — MUST be continent-tier per MAP-2 ChannelTier (HIGH-2 fix)
    pub continent_index: u8,                                // 0..=N within the reality; reality with one continent = 0
    pub schema_version: u32,                                // (MED-5 fix) aggregate field-shape version per I14 additive evolution; V1 = 1
    pub generator_pipeline_version: u32,                    // (MED-4 fix) algorithm version; pinned at GeographyBorn; mid-life upgrades FORBIDDEN
    pub seed: GeographySeed,                                // immutable per continent; sub-seeds derived from master_seed
    pub creative_seed: CreativeSeed,                        // immutable per continent post-bootstrap; V1+ extension via Forge T8
    pub geography_deltas: Vec<GeographyDelta>,              // append-only ordered edits; replay = base + deltas; idempotency via delta_id
    pub last_delta_event_id: Option<EventId>,               // causal-ref pointer for ordered append validation

    // ─── Geometry layer (V1 populated) ───
    pub cells: Vec<GeoCell>,                                // ~10k Voronoi cells; dense GeoCellId index = position in Vec
    pub neighbors: Vec<Vec<GeoCellId>>,                     // neighbors[cell_id] = adjacent cells; symmetric (no directed edges V1)
    pub sea_level_threshold: u16,                           // heightmap value below = water; default 32768; tunable per creative_seed

    // ─── Climate layer (V1 populated) ───
    pub climate_zones: Vec<ClimateZone>,                    // climate_zones[cell_id] = ClimateZone (parallel array to cells)

    // ─── Biome layer (V1 populated) ───
    pub biomes: Vec<BiomeKind>,                             // biomes[cell_id] = BiomeKind
    pub river_flux: Vec<f32>,                               // river_flux[cell_id] = hydraulic flux f32
    pub river_threshold: f32,                               // flux > threshold = navigable river; default 1000.0; tunable
    pub is_coast: Vec<bool>,                                // is_coast[cell_id] = land cell adjacent to water cell

    // ─── Political layer (V1 schema-reserved; V1+ POL_001 populates) ───
    pub provinces: Vec<Province>,                           // V1: empty Vec OR canonical author-declared only
    pub states: Vec<State>,                                 // V1: empty Vec OR canonical author-declared only

    // ─── Settlement layer (V1 schema-reserved; V1+ SET_001 populates) ───
    pub settlements: Vec<Settlement>,                       // V1: empty Vec OR creative_seed.named_settlements materialized

    // ─── Route layer (V1 schema-reserved; V1+ ROUTE_001 populates) ───
    pub routes: Vec<Route>,                                 // V1: empty Vec OR canonical author-declared only

    // ─── Culture layer (V1 schema-reserved) ───
    pub culture_regions: Vec<CultureRegion>,                // V1: empty Vec OR creative_seed.culture_hints seeded

    // ─── Resource layer (V2+ schema-reserved) ───
    // (resources live on Province.resources; root aggregate doesn't carry a separate Vec)
}

pub struct GeoCell {
    pub id: GeoCellId,                                      // dense u32; equals index in cells[]
    pub center: (f32, f32),                                 // normalized 0.0..=1.0 within continent viewport
    pub heightmap: u16,                                     // 0..65535; below sea_level_threshold = water cell
    pub vertex_polygon: Vec<(f32, f32)>,                    // Voronoi cell vertex polygon for rendering (4-12 points typically)
    pub area_normalized: f32,                               // cell area as fraction of continent (~1/N average)
}

pub struct GeographySeed {
    pub master_seed: u64,                                   // author-declared at reality creation
    pub voronoi_seed: u64,                                  // derived via blake3(master_seed, b"voronoi")
    pub climate_seed: u64,                                  // derived via blake3(master_seed, b"climate")
    pub erosion_seed: u64,                                  // derived via blake3(master_seed, b"erosion")
    pub political_seed: u64,                                // derived via blake3(master_seed, b"political") [V1+ used]
    pub settlement_seed: u64,                               // derived via blake3(master_seed, b"settlement") [V1+ used]
}

pub struct Province {
    pub id: ProvinceId,                                     // opaque newtype
    pub name: LocalizedName,                                // shared with PF_001 / MAP_001
    pub member_cells: Vec<GeoCellId>,                       // cell-cluster member set
    pub capital_settlement_id: Option<SettlementId>,        // V1: None; V1+ POL/SET populate
    pub state_id: Option<StateId>,                          // V1: None; V1+ POL populates
    pub resources: Vec<ResourceTag>,                        // V1: empty; V2+ resource generator populates
}

pub struct State {
    pub id: StateId,
    pub name: LocalizedName,
    pub capital_province_id: ProvinceId,
    pub member_provinces: Vec<ProvinceId>,
    pub culture_tag: Option<CultureTag>,
    pub ideology_ref: Option<IdeologyId>,                   // references IDF_005 (Ideology Foundation)
}

pub struct Settlement {
    pub id: SettlementId,
    pub name: LocalizedName,
    pub cell_id: GeoCellId,                                 // which cell this settlement sits in
    pub role: SettlementRole,                               // closed enum §4
    pub population_tier: u8,                                // 0..6 abstract; canonical-declared OR generator-derived
    pub canon_ref: Option<BookCanonRef>,                    // (LOW-3 fix) preserves CanonicalSettlementDecl.canon_ref on materialization
    pub channel_id: Option<ChannelId>,                      // V1+ when town-tier channel exists for this settlement
}

pub struct Route {
    pub id: RouteId,
    pub kind: RouteKind,                                    // closed enum §4
    pub from_cell: GeoCellId,
    pub to_cell: GeoCellId,
    pub distance_units: u32,                                // canonical abstract leagues (matches MAP_001 distance_units)
    pub default_fiction_duration: FictionDuration,          // OnFoot baseline (matches MAP_001 §8 pattern)
    pub is_bidirectional: bool,
}

pub struct CultureRegion {
    pub id: CultureRegionId,
    pub tag: CultureTag,                                    // opaque V1; V1+ structured
    pub member_cells: Vec<GeoCellId>,
    pub hearth_cell: GeoCellId,                             // origin cell from creative_seed.culture_hints
}

pub struct GeographyDelta {
    pub id: GeographyDeltaId,                               // monotonic u64 per aggregate row (HIGH-3 fix; per-(reality_id, continent_channel_id))
    pub kind: GeographyDeltaKind,                           // closed enum 5 V1 §4.5 (MED-6 fix; was 6 V1)
    pub authored_by_actor_id: ActorId,                      // Forge author per WA_003 audit
    pub reason: I18nBundle,                                 // human-readable canonization rationale (50+ char per S5 Tier 2 discipline)
    // (LOW-2 fix) applied_at_fiction_time DROPPED — not needed for replay determinism; the triggering
    // EVT-T8 event already carries wall-time via S4 MetaWrite audit + continent fiction_clock at event_id.
}
```

**Rules:**

- One row per continent `channel_id`. Primary key conflict rejects `geography.duplicate_world_geometry`.
- `channel_id` MUST resolve to a channel whose `MAP-2 ChannelTier == Continent` (mapped from `DP-Ch1 level_name` per MAP_001 §3 enum). Non-continent channels reject `geography.invalid_channel_tier`. (HIGH-2 fix: explicit dependency on MAP-2 closed-enum prevents validator ambiguity across `level_name` string conventions.)
- `cells.len()` MUST be in `[1024, 16384]` V1; outside range rejects `geography.cell_count_out_of_bounds`. (Lower bound prevents degenerate worlds; upper bound caps memory.)
- `neighbors[i].len()` MUST be in `[3, 12]` for every cell (Voronoi cells have 3-12 neighbors); outside rejects `geography.invalid_neighbor_degree`.
- `climate_zones.len() == biomes.len() == river_flux.len() == is_coast.len() == cells.len()` — all parallel arrays MUST match length; mismatch rejects `geography.parallel_array_length_mismatch`.
- `sea_level_threshold` MUST be in `[8192, 57344]` (avoid degenerate all-water or all-land worlds); outside rejects `geography.sea_level_out_of_bounds`.
- `geography_deltas` ordered append-only; out-of-order delta_id or rewriting past deltas rejects `geography.delta_order_violation` (parallel to TDIL-A8 past-clock-edit-forbidden).
- **(HIGH-3 fix)** `GeographyDelta.id` is monotonic **per `world_geometry` aggregate row** — i.e., per `(reality_id, continent_channel_id)` tuple. Forks start fresh sequences from the post-`GeographyForkInherited` `last_delta_event_id`; sibling realities' delta_id values may collide across rows without interaction (they live in separate aggregates). Cross-aggregate `delta_id` comparison is meaningless.
- **(MED-4 fix)** Once a `world_geometry` row is materialized at `generator_pipeline_version=N`, that row stays at N for its lifetime. Mid-life pipeline upgrades are **FORBIDDEN**. New realities adopt the latest `pipeline_version` at bootstrap. R3 upcasters apply only to additive schema-shape evolution (`schema_version` bumps), never to generator algorithm versions. Upgrade attempts reject `geography.pipeline_version_mismatch`.
- **(LOW-1 fix)** `GeoCellId == index` invariant: for all `i in 0..cells.len()`, `cells[i].id == GeoCellId(i as u32)`. Out-of-order or sparse cell vectors reject `geography.cell_id_index_violation`. (Enforced at GeographyBorn + at every delta apply that touches cells.)
- `creative_seed` immutable post-bootstrap V1. Forge edit attempts on the CreativeSeed struct itself (vs. appending deltas) reject `geography.creative_seed_immutable_v1`. V1+ extension via T6 LLM proposal → T8 Forge approval (GEO-D5).
- V1 schema-reserved layers (provinces / states / settlements / routes / culture_regions): MAY be empty OR populated only by canonical author declaration in `creative_seed.canonical_*`. Runtime generator population is V1+ via dedicated generator features (POL_001 / SET_001 / ROUTE_001 — schema-stable, activation-deferred discipline). Writes to these layers outside the canonical-declaration path V1 reject `geography.layer_activation_deferred_v1`.

---

## §4 Closed enums

### 4.1 ClimateZone (8 V1)

```rust
pub enum ClimateZone {                                      // closed; derived deterministically from (latitude, altitude, ocean_distance)
    Polar,                                                  // ice cap; supports Glacier/Tundra biomes
    Boreal,                                                 // cold continental; supports Tundra/Forest
    Temperate,                                              // four-season moderate; supports Forest/Plain/Hill
    Mediterranean,                                          // dry-summer; supports Plain/Forest (Mediterranean)
    Subtropical,                                            // warm humid; supports Forest/Plain/Marsh
    Tropical,                                               // hot humid; supports Jungle/Marsh/Coast
    Arid,                                                   // hot dry; supports Desert/Plain
    Highland,                                               // high-altitude regardless of latitude; supports Mountain/Hill
}
```

V1+ extensions (closed-enum bump per R3 additive): MagicalAnomaly (cultivation-realm settings; Tây Du Ký / Thần Điêu specific climate cells) — tracked GEO-D7.

### 4.2 BiomeKind (14 V1)

```rust
pub enum BiomeKind {                                        // closed; derived from (climate, heightmap, river_flux) deterministically
    Ocean,                                                  // water cell deep
    Lake,                                                   // water cell isolated (no ocean connection)
    River,                                                  // land cell with river_flux > threshold
    Coast,                                                  // land cell adjacent to ocean (is_coast=true)
    Beach,                                                  // low elevation coastal sand/rock
    Plain,                                                  // flat low-elevation; Temperate/Mediterranean/Subtropical/Arid
    Forest,                                                 // tree-cover; Boreal/Temperate/Subtropical
    Jungle,                                                 // tropical dense; Tropical only
    Marsh,                                                  // wetland; Tropical/Subtropical low + high flux
    Mountain,                                               // high elevation; Highland or Tropical-Highland
    Hill,                                                   // mid elevation; Temperate/Mediterranean
    Desert,                                                 // arid low; Arid only
    Tundra,                                                 // cold low; Polar/Boreal
    Glacier,                                                // perpetual ice; Polar high
}
```

The deterministic mapping function `(climate, heightmap, river_flux) → BiomeKind` is part of the V1 generator contract and is fixed by `generator_pipeline_version`. Bumping the pipeline version requires an upcaster row per R3 (V2+ if biome semantics change).

### 4.3 SettlementRole (6 reserved; V1 schema, V1+ SET_001 populates)

```rust
pub enum SettlementRole {                                   // closed; V1+ SET_001 weighted placement
    Hamlet,                                                 // population_tier 0-1; rural; no walls
    Village,                                                // population_tier 1-2; rural; defensive palisade
    Town,                                                   // population_tier 2-3; market + walls
    City,                                                   // population_tier 3-4; multi-quarter + walls
    Capital,                                                // state_id != None capital_province seat; max population_tier per state
    Fortress,                                               // military; chokepoint terrain; population_tier 1-2 (small but defensive)
}
```

### 4.4 RouteKind (5 reserved; V1 schema, V1+ ROUTE_001 populates)

```rust
pub enum RouteKind {                                        // closed; V1+ ROUTE_001 Dijkstra over terrain cost
    Road,                                                   // built; high-traffic; settlement-to-settlement
    Trail,                                                  // unimproved path; low-traffic; chokepoint or wilderness
    RiverNavigation,                                        // river_flux > navigable_threshold; movement via boat
    SeaLane,                                                // ocean cells; coastal city pairs; movement via ship
    MountainPass,                                           // chokepoint over Highland; strategic value
}
```

### 4.5 GeographyDeltaKind (5 V1; MED-6 fix — dropped from 6 V1, SetResourceOverride moved to V1+ reservation)

```rust
pub enum GeographyDeltaKind {                               // closed; admin canonization via Forge:EditGeographyDelta T8
    AddNamedSettlement { cell_id: GeoCellId, name: LocalizedName, role: SettlementRole, population_tier: u8 },
    RenameRegion { cell_ids: Vec<GeoCellId>, new_name: LocalizedName, scope: RenameScope }, // RenameScope = Settlement | Province | Region | CulturalArea
    SetBiomeOverride { cell_id: GeoCellId, biome_override: BiomeKind, reason: I18nBundle }, // V1 LAND-↔-LAND only per HIGH-1; water transitions reject geography.biome_override_water_transition_v1
    AddRoute { from_cell: GeoCellId, to_cell: GeoCellId, kind: RouteKind, distance_units: u32, default_fiction_duration: FictionDuration }, // V1 schema-reserved layer per §3
    RemoveRoute { route_id: RouteId },                      // V1 schema-reserved layer per §3
}
```

**V1+ DeltaKind extensions** (closed-enum bump per R3 additive): `SetResourceOverride { province_id, resources, reason }` (V2+ when resource generator GEO-D10 lands) · `MergeProvinces` · `SplitProvince` · `TransferProvinceToState` · `SetCultureRegion`. All tracked under GEO-D8.

---

## §5 Generation pipeline (eight-stage overview)

Procedural generation pipeline implemented in `world-service`'s `geography-generator` module. V1 implements stages 1-4 substantively; stages 5-8 are V1+ activation slots (schema declared, generator deferred). Pipeline is deterministic: same `(seed, creative_seed, pipeline_version)` always produces the same `world_geometry` aggregate.

| # | Stage | V1 status | Algorithm | Sub-seed |
|---|---|---|---|---|
| 1 | **Voronoi partition** | ✅ V1 | Poisson-disk sample (cell count from `creative_seed.world_scale`) → Voronoi mesh via Fortune's algorithm; neighbor adjacency from Delaunay dual (per Red Blob Games dual-mesh, Apache 2.0 reference) | `voronoi_seed` |
| 2 | **Heightmap** | ✅ V1 | Tectonic-plates approximation (Perlin noise + radial falloff per `creative_seed.coastline_profile`) → thermal erosion smoothing | `erosion_seed` |
| 3 | **Climate** | ✅ V1 | Latitude × altitude × ocean-distance model (Köppen-Geiger-inspired); 8 ClimateZone bands; per-cell deterministic | `climate_seed` |
| 4 | **Biome + river + water network** | ✅ V1 | Three sub-stages (MED-3 fix — Lake-vs-Ocean discrimination needs global topology): **(4a)** hydraulic erosion → river_flux per cell. **(4b)** water-network connected-components flood-fill from any border water cell → tag connected water as `is_in_ocean_component=true`; isolated water cells stay false. **(4c)** BiomeKind via `(climate, heightmap, river_flux, is_in_ocean_component, is_coast)` mapping function — water with `is_in_ocean_component=true` → Ocean; water with false → Lake; land with `river_flux > threshold` → River; land adjacent to Ocean → Coast (sets `is_coast=true`); otherwise climate × elevation. | `erosion_seed` |
| 5 | **Political growth** | 📦 V1+ POL_001 | Priority-queue flood-fill from capital seeds (cell distance + terrain cost); state borders emerge from capital influence radii | `political_seed` |
| 6 | **Settlement placement** | 📦 V1+ SET_001 | Burg score = `f(population_potential, water_proximity, terrain_passability)` → Poisson-disk weighted placement → SettlementRole by terrain heuristic (mountain pass → Fortress; coast + flux → Capital candidate; etc.) | `settlement_seed` |
| 7 | **Route network** | 📦 V1+ ROUTE_001 | Dijkstra over terrain-cost graph between settlement pairs (Road for City-City; Trail elsewhere); sea-lane derivation between coastal cities via water cells; MountainPass chokepoint detection via graph edge-betweenness | derived |
| 8 | **Culture spread** | 📦 V1+ | Priority-queue flood-fill from cultural-hearth cells (declared in `creative_seed.culture_hints`); CultureRegion membership emerges; influence falls off with terrain barrier (mountains, oceans block spread) | `political_seed` (shared) |

**Pipeline determinism (EVT-A9 compliance):**

- Same `(master_seed, creative_seed, generator_pipeline_version)` → bitwise-identical `world_geometry` aggregate (modulo HashMap iteration order, which the generator MUST normalize via deterministic sort — V1 implementation discipline: sort HashMap keys to BTreeMap at serialize time; SPIKE_04 GAP-S2.A CI snapshot test enforces).
- `dp::deterministic_rng` per `_boundaries/02_extension_contracts.md` §1 used for ALL non-deterministic choices within the pipeline.
- **(D-S04-3)** Floating-point operations (`river_flux: f32` accumulation in stage 4a + Voronoi cell area in stage 1) compiled with **strict-IEEE mode** (`-ffp-contract=off` for C/C++ deps; Rust's default IEEE-754 + explicit `#[deny(clippy::float_arithmetic)]` outside the generator module). NO `f64` truncation paths; NO SIMD-vectorized reductions (which reassociate operands non-deterministically). Fixed-point representation deferred V1+ if drift surfaces in CI snapshot tests (SPIKE_04 GAP-S2.B).
- Replay CI gate verifies: same seed → same aggregate bytes after stages 1-4. V1+ activation of stages 5-8 extends the CI gate.
- Pipeline version bumps require an upcaster path per R3 (V2+ if mapping function changes).

**Cost envelope (V1 target):**

- 10k cells continent: ~50ms generation wall-clock V1 (single-threaded Rust; per-stage sub-100ms budget).
- Materialization to `world_geometry` aggregate: ~1MB on-disk per continent (compressed; binary serialized via existing 02_storage compression).
- One-shot at bootstrap; not re-run on routine operation (regeneration happens only on `creative_seed` extension Forge action, V1+).

---

## §6 CreativeSeed (LLM-supplied creative direction)

```rust
pub struct CreativeSeed {                                   // immutable post-bootstrap V1; V1+ extension via T6 LLM proposal + T8 Forge approval
    pub schema_version: u32,                                // V1 = 1; bump on additive extension
    pub archetype: WorldArchetype,                          // closed enum 12 V1 — wuxia / cyberpunk / high_fantasy / etc.
    pub world_scale: WorldScale,                            // closed enum 5 V1 — Pocket(1024) / Region(2048) / Continent(8192) / SuperContinent(12288) / Megaplanet(16384) cells
    pub hemisphere_orientation: HemisphereOrientation,      // Northern / Southern / Equatorial (latitude convention)
    pub coastline_profile: CoastlineProfile,                // Island / Peninsula / Coastal / Inland / Archipelago — drives radial falloff in stage 2
    pub climate_bias: Option<ClimateZone>,                  // None = balanced; Some(ClimateZone) = bias toward this zone (e.g., Arid for Dune-style)
    pub culture_hints: Vec<CultureHint>,                    // ≤16; each Hint = (hearth_position_normalized, naming_style, value_tags); fed into stage 8 culture spread
    pub canonical_settlements: Vec<CanonicalSettlementDecl>, // author-pinned settlements that MUST exist post-generation (e.g., "Tương Dương" at specified position); placed before stage 6 weighted generation; ~5-50 typical
    pub canonical_provinces: Vec<CanonicalProvinceDecl>,    // V1+ stage 5 — author-pinned states (e.g., "Tống triều" must exist with capital at Khai Phong)
    pub lore_hooks_per_region: Vec<RegionalLoreHook>,       // freeform; consumed by LLM at prompt-assembly time, NOT by generator
    pub naming_styles: HashMap<CultureTag, NamingStyleDecl>, // Markov-chain corpus or LLM-prompt per culture; used by stage 6 + 8 for settlement/region names
}

pub enum WorldArchetype {                                   // closed 12 V1; V1+ closed-enum bump
    Wuxia,                                                  // Tang/Song dynasty grounded; cultivation realms
    HighFantasy,                                            // Tolkien-derived
    LowFantasy,                                             // historical Earth + small magic
    Cyberpunk,                                              // urban dystopian
    SteamPunk,
    Postapocalyptic,
    ScienceFiction,
    Historical,                                             // earth-history adapted
    Mythological,                                           // Greek/Norse/etc. pantheon-driven
    Romance,                                                // contemporary urban; minimal procgen geography
    Mystery,                                                // contemporary investigation; minimal procgen geography
    Custom,                                                 // author declares everything; generator falls back to neutral defaults
}

pub enum WorldScale {                                       // closed 5 V1; determines cells.len() target
    Pocket,                                                 // ~1024 cells; single-city tabletop
    Region,                                                 // ~2048 cells; country-scale wuxia
    Continent,                                              // ~8192 cells; default V1
    SuperContinent,                                         // ~12288 cells; epic fantasy
    Megaplanet,                                             // ~16384 cells; sci-fi planet
}

pub struct CultureHint {
    pub hearth_position_normalized: (f32, f32),             // 0.0..=1.0; where this culture originates on the continent
    pub naming_style_ref: CultureTag,                       // FK into creative_seed.naming_styles
    pub value_tags: Vec<String>,                            // e.g., ["honor", "hierarchy", "ancestor_worship"]; fed to LLM context only V1
}

// (LOW-3 fix) Struct shapes that CreativeSeed references — explicitly declared:

pub struct CanonicalSettlementDecl {                        // consumed by §11 RealityManifest + §5 stage 4c materialization
    pub name: LocalizedName,
    pub position_normalized: (f32, f32),                    // 0.0..=1.0; placed before V1+ SET_001 weighted generation
    pub role: SettlementRole,
    pub population_tier: u8,
    pub canon_ref: Option<BookCanonRef>,                    // book-grounded; materialized onto Settlement.canon_ref
}

pub struct RegionalLoreHook {                               // freeform; consumed by LLM prompt-assembly at §6 grounding contract, NOT by generator
    pub scope: HookScope,                                   // PRE-materialization identifiers only — see HookScope below
    pub content: I18nBundle,
}

pub enum HookScope {                                        // (Option C bug fix 2026-05-13) — uses identifiers that exist at CreativeSeed-creation time
    SettlementByName(LocalizedName),                        // resolves post-stage-6 to SettlementId by name match against canonical_settlements
    PositionRegion { center: (f32, f32), radius_normalized: f32 }, // resolves post-stage-1 to Vec<GeoCellId> covering the disc
    Archetype,                                              // applies globally to this archetype's world; no resolution needed
    // V1+ extension when knowledge-service ships: KnowledgeEntityRef(EntityRef) to bind hooks to canonical book entities
}

pub struct NamingStyleDecl {                                // V1: Markov-chain corpus ref OR LLM-prompt template; at least one Some required
    pub markov_corpus_ref: Option<String>,                  // V1 Markov chain corpus identifier (in glossary-service)
    pub llm_prompt_template: Option<String>,                // V1+ LLM-prompt template for generative naming
}
```

**Why CreativeSeed is the LLM's actual job (not naming/decoration):**

The LLM produces the `CreativeSeed` value at world-creation time as **structured creative direction** (archetype + scale + culture hints + canonical settlements + naming styles). The procgen pipeline consumes this as **constraints**, then runs deterministically. The LLM does NOT run the pipeline; it does NOT produce the Voronoi cells or the heightmap; it does NOT post-decorate the output. It pre-directs the procgen with the same kind of input a human world-author would write.

This factors LLM strength (creative narrative direction, cultural nuance, name generation) from LLM weakness (geometric reasoning, spatial consistency, deterministic replay). Per the 2024-2025 survey, this hybrid is the only approach that satisfies both creative richness AND strategy gameplay's regeneration-stability.

**Write-side authoring contract → see [GEO_001b](GEO_001b_authoring_flow.md).** The schema HERE is the *materialized data shape*. The flow that PRODUCES this schema (LLM authoring template per S9, schema-constrained generation, multi-turn iteration, validation+retry, cost cap per S6, knowledge-service grounding, producer abstraction LLM/Manual/Imported/KnowledgeExtracted) lives in the sibling doc. GEO_001b also introduces `SpatialPreference` (closed enum of named spatial intents like Northern/Coastal/Highland/NearBiome/etc.) as the V1+ LLM-friendlier alternative to `(f32, f32)` position fields — additive per I14 (CreativeSeed.schema_version 1 → 2 when GEO_001b lands at LOCK; V1=1 keeps required `position_normalized`, V1+=2 adds optional `spatial_preference` with validator "at least one Some").

**LLM-context grounding contract (consumed by S9 prompt assembly):**

When `[ACTOR_CONTEXT]` includes a PC location, prompt-assembly joins:
`cell_channel.metadata.geo_cell_id → world_geometry.biomes[geo_cell_id], climate_zones[geo_cell_id], culture_regions where cell_id ∈ member_cells, nearest_settlement, nearest_route, lore_hooks_per_region`

and renders a compact `[GEOGRAPHIC_CONTEXT]` sub-section. This is mechanism-level — no new prompt section needed; existing S9 §12Y.L3 8-section structure absorbs the join inside `[ACTOR_CONTEXT]`. The LLM gets canonical geographic facts, not invented ones.

---

## §7 Delta overlay editability model

The base map regenerates reproducibly from `(seed, creative_seed, pipeline_version)`. Admin canonization edits live as `GeographyDelta` entries appended to `geography_deltas` in order. **Replay = base + deltas in order.** No destructive regeneration; small edits don't jitter the world.

### Append protocol

```
Forge actor (per WA_003 RBAC + S5 Tier 2 ImpactClass=Griefing for additive; Tier 1 ImpactClass=Destructive for SetBiomeOverride+RemoveRoute)
    ↓ emits EVT-T8 Administrative `Forge:EditGeographyDelta { kind, payload, prev_delta_id }`
07_event_model EVT-V* validator pipeline:
    1. AuthorizationGate (capability JWT: can_edit_geography for the continent)
    2. SchemaGate (DeltaKind variant valid; payload typecheck)
    3. ReferentialIntegrityGate (cell_id ∈ cells; route_id ∈ routes if RemoveRoute; etc.)
    4. OrderingGate (prev_delta_id == world_geometry.last_delta_event_id)
    5. ContentSafetyGate (LocalizedName + reason scrubbed via §12X.L7 — D-S04-4: scrub regardless of in-fiction context, matching existing §12X.L7 admin discipline; named in-fiction characters like "Tiểu Long Nữ" go through the same regex scrubber as personal data — defense in depth)
    ↓ if all pass:
EVT-T3 Derived `aggregate_type=world_geometry` field delta:
    geography_deltas.push(GeographyDelta { id, kind, fiction_time, author, reason })
    last_delta_event_id = this_event_id
```

**Idempotency:** retry with same `prev_delta_id` is safe (ordering gate filters duplicates); retry after success rejects `geography.delta_order_violation`.

**Read protocol:**

```rust
fn materialize_world_geometry(seed: &GeographySeed, creative_seed: &CreativeSeed, deltas: &[GeographyDelta]) -> WorldGeometry {
    let mut wg = run_pipeline(seed, creative_seed);          // stages 1-4 V1 (5-8 V1+ when activated)
    for delta in deltas {                                    // ordered application
        apply_delta(&mut wg, delta);
    }
    wg
}
```

`apply_delta` is total per V1 DeltaKind closed-enum:

- `AddNamedSettlement`: push to `settlements`; settle on cell.
- `RenameRegion`: find region by scope match; replace LocalizedName.
- `SetBiomeOverride`: V1 admits only **land-↔-land** transitions (HIGH-1 fix). Set `biomes[cell_id] = override`; recompute `is_coast[cell_id]` + `is_coast[n]` for every `n ∈ neighbors[cell_id]` (scope-bounded ≤12 cells); river_flux recomputed via stage 4b scope-bounded re-run over the same neighborhood. **Water-↔-land transitions reject `geography.biome_override_water_transition_v1`** (V1+ when biome+water-network re-derivation lands — tracked GEO-D13). Coherence guarantee: post-delta `(biomes, river_flux, is_coast)` triple satisfies the same invariants as a freshly-generated world for the affected neighborhood.
- `AddRoute`: V1 schema-reserved — see §3 layer-activation rule; route adjacency contract owned by V1+ ROUTE_001.
- `RemoveRoute`: V1 schema-reserved per §3 layer-activation rule.

**Why delta-overlay vs. destructive regeneration:**

Azgaar and similar tools regenerate destructively (re-run the whole pipeline with new params; results jitter). For an MMO RPG where (a) saves reference cell positions, (b) admin canonizations accumulate over months, (c) players form attachment to specific settlements — destructive regeneration is catastrophic. Delta-overlay is genuinely novel work (no Azgaar-style tool does this V1) but the schema is straightforward; the heavy lift is the `apply_delta` total-function discipline + CI gate that proves "base + deltas at fork-point = child's initial state."

---

## §8 Sea zone adjacency (single mesh with water-cell tags)

V1 single Voronoi mesh; water cells tagged via `biome ∈ {Ocean, Lake, River}` OR `heightmap < sea_level_threshold`. Naval adjacency derived by clustering connected water cells; navigable-river adjacency derived from `river_flux > navigable_threshold` (default 1000.0 V1).

```rust
impl WorldGeometry {
    pub fn naval_neighbors(&self, cell_id: GeoCellId) -> Vec<GeoCellId> {
        // Only water cells have naval neighbors; land cells return empty.
        if !self.is_water_cell(cell_id) { return vec![]; }
        // Walk neighbors; include water neighbors and coastal land cells (for embark/disembark).
        self.neighbors[cell_id.0 as usize].iter()
            .filter(|&&n| self.is_water_cell(n) || self.is_coast[n.0 as usize])
            .copied().collect()
    }

    pub fn is_water_cell(&self, cell_id: GeoCellId) -> bool {
        let i = cell_id.0 as usize;
        matches!(self.biomes[i], BiomeKind::Ocean | BiomeKind::Lake | BiomeKind::River)
    }
}
```

**Tradeoff vs. Paradox-style separate land/sea graphs:**

- ✅ Single mesh: simpler maintenance, LLM creative-seeding consistent (one CultureRegion can span coast + interior), V1 naval gameplay (V1+ TVL_001 SeaLane Travel) implementable from derived adjacency.
- ❌ Single mesh: explicit "strait" modeling (Bosporus, Dardanelles — narrow water passing land both sides) is awkward; strategic naval invasions across narrow seas need V1+ explicit strait detection.

**V2+ migration path (GEO-D6):** if strategy gameplay needs Paradox-grade naval, GEO_001 V2+ schema extension adds `sea_zones: Vec<SeaZone>` derived layer (clusters of water cells) + `straits: Vec<StraitDecl>` explicit author-declared chokepoint edges. Single-mesh stays as primary; sea_zones+straits is derived projection. Tracked GEO-D6 V2+.

---

## §9 Multiverse inheritance

Per `03_multiverse/03_fork_and_cascading.md` MV6 snapshot-fork semantics: child reality inherits parent's events up to and including `fork_point_event_id`; child's events are not visible to parent; no merging.

**GEO inheritance contract:**

At snapshot fork, DP-internal SnapshotForker emits `Forge:ForkGeographyInherit { child_reality_id, parent_continent_channel_id, fork_point_event_id, copied_delta_count }` per continent. Child's initial `world_geometry` aggregate:

- `seed`: copied from parent (identical Voronoi mesh, climate, biome — bit-exact reproducibility).
- `creative_seed`: copied from parent.
- `geography_deltas`: copied as `parent.geography_deltas[.. fork_point_index]` where `fork_point_index` = max delta whose generating event ≤ fork_point_event_id.
- `last_delta_event_id`: set to child's first event (the ForkGeographyInherit itself).

Post-fork:

- Child appends new deltas locally; parent does NOT see them.
- Parent appends new deltas locally; child does NOT see them.
- **L1 axioms (canon layer) DO cascade** per §6 read-through to book — if author edits a canon-anchored CreativeSeed extension at L2, both parent and child see the new L2 value on next read UNLESS child has an L3 override (i.e., a child-local GeographyDelta on the same cell/region).

This matches the existing 4-layer canon cascading-read rule (L3 > L2 > L1). GeographyDelta is L3-scoped (reality-local) by construction; CreativeSeed lives at L2 (per-reality but author-declared at creation).

**Determinism guarantee:** because Voronoi + heightmap + climate + biome are deterministic functions of the seed (stages 1-4 reproducible), and deltas are append-only with explicit ordering, replay of `(seed, creative_seed, deltas)` produces bit-identical `world_geometry` aggregates across both parent and child up to their respective delta append points. This is the foundation for strategy gameplay save-stability across forks.

---

## §10 Composition with foundation siblings

GEO_001 composes with the existing foundation tier without overlap. Composition contracts:

| Sibling | Composition |
|---|---|
| **MAP_001 Map Foundation** | V1: MAP_001 owns `map_layout.position` (per-channel author-positioned visual node placement). V1+ GEO-D5: `map_layout.position` derives from `world_geometry.settlements[settlement_id].cell_id → cells[id].center` (auto-positioned from GEO settlement coordinates). MAP_001 stays the visual SSOT; GEO is the geometric SSOT. MAP_001 light reopen at LOCK adds "V1+ position derivation row" tracking GEO-D5 activation. |
| **PF_001 Place Foundation** | V1: PF_001 owns `place` aggregate (cell-tier semantic identity, PlaceType per cell). PF-D7 procedural place generation V1+ consumes `world_geometry.biomes[geo_cell_id]` + `climate_zones[geo_cell_id]` → PlaceType heuristic (Biome::Forest + Temperate climate → Village/Inn likely; Biome::Mountain → Cave/Pass; Biome::Ocean → no cell). Cell channels carry `cell_channel.metadata.geo_cell_id` FK back into world_geometry — bridges DP channel hierarchy and procedural geometry. |
| **CSC_001 Cell Scene Composition** | V1+ CSC_001 consumes `world_geometry.biomes[geo_cell_id]` for skeleton selection (Biome::Forest → forest_clearing skeleton; Biome::Mountain → cave skeleton; etc.). V1 CSC_001 is biome-agnostic (author selects skeleton); V1+ activation via PF-D7 cascade. |
| **EF_001 Entity Foundation** | No direct composition. Entities live in cells (EF_001 `entity_binding`); cells live in the channel hierarchy; geometry data is per-continent. Entity queries don't traverse GEO. LLM prompt-assembly does (per §6 grounding contract). |
| **RES_001 Resource Foundation** | V2+ GEO-D10: resource distribution generator (`GEO_005`) consumes `world_geometry.biomes × climate_zones` to seed per-province `resource_inventory` production base (e.g., Biome::Plain + Temperate → grain production; Biome::Mountain + Highland → ore; Biome::Coast → fish). V1 schema-only — Province.resources is declared empty. RES_001 V2+ NPCAutoCollect (RES-D19 lazy migration) reads this for resource production rates. |
| **PROG_001 Progression Foundation** | No direct composition V1. V2+ if cultivation-realm world archetype (Wuxia) declares Highland cells as "spirit-vein" cells with bonus cultivation rate, PROG_001 could read `world_geometry.biomes[geo_cell_id] + creative_seed.archetype` to apply per-cell training modifiers. Tracked GEO-D7 alongside MagicalAnomaly climate extension. |
| **DP-Ch1..Ch10** | World_geometry is ChannelScoped at continent tier (DP-Ch4 marker). `cell_channel.metadata.geo_cell_id` FK is the bridge from DP channel hierarchy to procedural geometry rows. ChannelTier::Continent in MAP_001's enum aligns. |

**Six foundation features compose without overlap:** EF (WHO) + PF (WHERE-semantic) + MAP (WHERE-graph-visual) + CSC (WHAT-inside-cell) + RES (WHAT-flows-through-entity) + PROG (HOW-actors-grow) + **GEO** (WHERE-geometric-substrate). GEO completes the spatial-substrate triangle (semantic / visual / geometric) and serves as the foundation for V1+ POL/SET/ROUTE features and V2+ STRAT/EXPL features.

---

## §11 RealityManifest extension

Per `_boundaries/02_extension_contracts.md` §2 RealityManifest envelope: GEO_001 declares three OPTIONAL fields per continent channel. OPTIONAL because realities with single hand-authored cell (current SPIKE_01 scope) don't need procedural geography — V1 default is "no procgen, no GEO row." Realities that DECLARE `geography_seed` MUST also declare `creative_seed`; absence rejects `geography.creative_seed_required_when_seeded`.

```rust
// Extension to existing RealityManifest envelope per `_boundaries/02_extension_contracts.md` §2
pub struct RealityManifestGeographyExtension {              // OPTIONAL — author opt-in V1
    pub continent_geometries: Vec<ContinentGeometryDecl>,   // one per continent channel; empty Vec = no procgen
}

pub struct ContinentGeometryDecl {
    pub continent_channel_id: ChannelId,                    // MUST be continent-tier per DP-Ch1
    pub geography_seed: GeographySeed,                      // REQUIRED per continent
    pub creative_seed: CreativeSeed,                        // REQUIRED per continent
    pub geography_deltas: Vec<GeographyDelta>,              // OPTIONAL initial deltas (canon-seeded edits at bootstrap)
}
```

**Bootstrap order at reality creation (extends existing RealityBootstrapper sequence):**

```
1. DP create_channel for reality root + continent channels (DP-Ch8)
2. For each continent in RealityManifest.continent_geometries:
   a. RealityBootstrapper emits EVT-T4 GeographyBorn{continent_channel_id, seed, creative_seed_hash, ...}
   b. world-service materializes WorldGeometry via run_pipeline(seed, creative_seed)
   c. Apply initial geography_deltas in order
   d. Persist as T2/Channel-continent aggregate
3. DP create_channel for country/district/town channels (per RealityManifest.places + map_layout)
4. EF_001 entity_binding bootstrap (PCs + canonical NPCs + items)
5. PF_001 PlaceBorn at cell channels (per existing PF_001 bootstrap; V1+ procedural seeding consumes GEO)
6. MAP_001 LayoutBorn (per existing MAP_001 bootstrap; V1+ position derivation consumes GEO)
```

V1 default if `continent_geometries` empty: no GEO rows; LLM prompt-assembly geographic-context falls back to `creative_seed.archetype` text-only hints; existing MAP_001 + PF_001 single-cell bootstrap unchanged.

---

## §12 Failure UX — `geography.*` RejectReason namespace

Owned by GEO_001. Registered in `_boundaries/02_extension_contracts.md` §1.4. **V1 rule_ids: 13** (3 added in fix cycle: HIGH-1 `biome_override_water_transition_v1` · MED-4 `pipeline_version_mismatch` activated · LOW-1 `cell_id_index_violation`) + V1+ reservations: 3.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1) | English fallback |
|---|---|---|---|---|
| `geography.duplicate_world_geometry` | schema | RealityBootstrapper | "Lục địa này đã có dữ liệu địa lý." | "This continent already has geography data." |
| `geography.invalid_channel_tier` | schema | RealityBootstrapper | "Chỉ kênh lục địa mới có dữ liệu địa lý." | "Only continent channels can have geography data." |
| `geography.cell_count_out_of_bounds` | schema | Generator pipeline | "Số ô không hợp lệ (cần 1024..16384)." | "Cell count out of bounds (must be 1024..16384)." |
| `geography.invalid_neighbor_degree` | schema | Generator pipeline | "Sơ đồ ô bị lỗi cấu trúc." | "Cell graph structural error." |
| `geography.parallel_array_length_mismatch` | schema | Generator pipeline / Forge | "Dữ liệu địa lý không nhất quán." | "Geography data inconsistent." |
| `geography.sea_level_out_of_bounds` | schema | Generator pipeline / Forge | "Mức biển nằm ngoài khoảng cho phép." | "Sea level out of allowed range." |
| `geography.delta_order_violation` | user | Forge:EditGeographyDelta | "Thứ tự chỉnh sửa địa lý sai. Tải lại và thử lại." | "Geography edit order violation. Refresh and retry." |
| `geography.creative_seed_immutable_v1` | user | Forge | "Cấu hình sáng tạo của lục địa không thể chỉnh sửa trực tiếp. Hãy dùng chức năng 'Thêm Hậu Cảnh' (V1+)." | "Continent creative seed is immutable. Use 'Add Lore' (V1+) instead." |
| `geography.layer_activation_deferred_v1` | user | Forge | "Lớp dữ liệu này sẽ kích hoạt ở phiên bản sau (V1+)." | "This layer activates in V1+; not yet available." |
| `geography.creative_seed_required_when_seeded` | schema | RealityBootstrapper | "Thiết lập địa lý cần cả seed và creative_seed." | "Geography setup requires both seed and creative_seed." |
| **`geography.biome_override_water_transition_v1`** *(HIGH-1)* | user | Forge:EditGeographyDelta | "V1: chỉ cho phép chuyển biome trên đất liền. Chuyển đổi nước↔đất sẽ có ở phiên bản sau." | "V1: only land-↔-land biome transitions allowed. Water↔land transitions arrive in V1+." |
| **`geography.pipeline_version_mismatch`** *(MED-4 active)* | schema | RealityBootstrapper / read path | "Phiên bản pipeline không khớp; thế giới này khóa ở phiên bản cũ." | "Pipeline version mismatch; this world is pinned to an older version." |
| **`geography.cell_id_index_violation`** *(LOW-1)* | schema | Generator pipeline / Forge | "Sơ đồ ô bị lỗi định danh." | "Cell ID/index invariant violated." |

**V1+ reservations:**

- `geography.cross_reality_reference` (V2+ Heresy axis) · `geography.delta_kind_v1plus_inactive` (V1+ DeltaKind extensions: SetResourceOverride V2+ per MED-6 + MergeProvinces/SplitProvince/etc.) · `geography.resource_layer_activation_pending` (V2+ generator placeholder).

i18n: V1 ships `user_message: I18nBundle` per RES_001 §2 cross-cutting contract from day 1.

---

## §13 Cross-service handoff

| Service | Role | V1 status |
|---|---|---|
| **world-service** | Authoritative owner — runs pipeline at bootstrap; applies Forge T8 deltas; persists aggregate | V1 |
| **glossary-service** | Stores canonical names referenced by creative_seed (canonical_settlements, lore_hooks); GEO holds `LocalizedName + BookCanonRef` per existing PF/MAP pattern | V1 |
| **chat-service** (S9 prompt-assembly) | Read-only consumer for `[ACTOR_CONTEXT]` geographic grounding per §6 contract | V1 |
| **api-gateway-bff** | Routes Forge UI POSTs → world-service; player map UI GETs → `/world/geometry/{continent_channel_id}` | V1 read; V1+ Forge UI |
| **knowledge-service** | Reads biomes + culture_regions to enrich entity/place knowledge graph (planned per CLAUDE.md two-layer pattern) | Not V1 |
| **video-gen-service** | V2+ consumes rendered slice for fantasy-map LoRA image generation (MAP_002 LlmGenerated pipeline); GEO output is the input description | V2+ |

No new service introduced. All work fits inside `world-service` extension + read-only consumers.

---

## §14 Sequences

### 14.1 Bootstrap with geography (Yên Vũ Lâu wuxia setting)

```
Author RealityManifest.continent_geometries[0] = ContinentGeometryDecl {
  continent_channel_id: <continent:southern_song>,
  geography_seed: { master_seed: 0xA1B2C3D4, ... },
  creative_seed: { archetype: Wuxia, world_scale: Region (~2048 cells), hemisphere: Northern,
                   coastline: Coastal, culture_hints: [han_jiangnan@(0.3,0.4), mongol_steppe@(0.8,0.2)],
                   canonical_settlements: [Tương Dương@(0.4,0.5)=Capital, Khai Phong@(0.5,0.3)=City,
                                           Yên Vũ Lâu@(0.45,0.55)=Town], ... },
  geography_deltas: [],
}
  ↓ RealityBootstrapper emits EVT-T4 GeographyBorn { continent, seed, creative_seed_hash, cells=2048, pipeline_version=1 }
  ↓ world-service generator: Stage 1 Voronoi (2048 cells + adjacency); Stage 2 Heightmap with Coastal falloff
    (~30% water); Stage 3 Climate (Subtropical south / Temperate north / Boreal far north); Stage 4 Biome +
    river_flux + connected-components water-network → Ocean (connected) vs Lake (isolated); canonical
    settlements pinned to nearest valid cells (GEO-Q2 fallback to nearest land within radius 5 if water).
  ↓ WorldGeometry aggregate persisted (~1MB); LLM prompt-assembly for cell:yen_vu_lau joins biomes[id]=Plain +
    climate_zones[id]=Subtropical + culture_regions(han_jiangnan) + nearest_settlement(Yên Vũ Lâu Town) →
    renders [GEOGRAPHIC_CONTEXT] = "thị trấn, văn hóa Hán-Giang Nam, đồng bằng cận nhiệt đới". LLM grounded.
```

### 14.2 Forge admin canonization adds a new city via delta

```
Author uses Forge:EditGeographyDelta — kind: AddNamedSettlement{cell_id: 1247 (Mountain biome), name:
"Cold Pool Academy", role: Hamlet, population_tier: 1}; prev_delta_id: world_geometry.last_delta_event_id;
reason: I18nBundle{vi: "Tiểu Long Nữ thành lập học viện ẩn cư..." 50+ char}.
  ↓ EVT-T8 Administrative emitted → 07_event_model validator pipeline: AuthorizationGate (capability
    can_edit_geography) → SchemaGate (DeltaKind payload valid) → ReferentialIntegrityGate (cell_id ∈ cells;
    Mountain biome valid for Hamlet) → OrderingGate (prev_delta_id matches) → ContentSafetyGate (reason
    scrubbed §12X.L7) → all pass.
  ↓ EVT-T3 Derived emitted → WorldGeometry mutation: geography_deltas.push(GeographyDelta{id, kind, ...});
    settlements.push(Settlement{id, name="Cold Pool Academy", cell_id=1247, role=Hamlet, canon_ref=None});
    last_delta_event_id = this_event_id.
  ↓ Subsequent prompt-assembly for cells near 1247 sees nearest_settlement="Cold Pool Academy"; fork
    inheriting this delta if fork_point ≥ delta_event_id.
```

### 14.3 Snapshot fork inherits geography deltas at fork-point

```
Parent R_alpha at event_id 5000 has world_geometry.geography_deltas = [d1, d2, d3] (d3 at event_id 4800).
Player creates fork at event_id 5000 → child R_beta.
  ↓ DP SnapshotForker (Synthetic actor; EVT-T4 System NOT EVT-T8 Admin) emits per continent:
    GeographyForkInherited { child_reality_id: R_beta, parent_continent_channel_id, fork_point_event_id:
    5000, copied_delta_count: 3 }.
  ↓ Child world_geometry materialized: new ChannelId per DP-Ch3; seed/creative_seed identical to parent;
    geography_deltas=[d1,d2,d3] copied; last_delta_event_id = ForkGeographyInherited event in R_beta;
    cells identical (deterministic from seed); delta_id sequence resumes from 4 (per-aggregate namespace).
  ↓ R_beta appends d4 locally; R_alpha continues with d4_alpha unrelated. R_beta.deltas=[d1,d2,d3,d4],
    R_alpha.deltas=[d1,d2,d3,d4_alpha]. No cross-pollination. Save state stable across both forks.
```

---

## §15 Acceptance criteria

11 V1-testable acceptance scenarios for GEO_001 schema + V1-stages-1-4 pipeline (AC-GEO-11 added 2026-05-13 in write-side cycle to verify HookScope post-materialization resolution per Option C bug-fix). Acceptance scoped to V1 layers (geometry / climate / biome); V1+ political/settlement/route/culture/resource layer acceptance lands with those generators.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-GEO-1** | Bootstrap continent with `seed=0xA1B2C3D4, creative_seed=<Wuxia,Region,Coastal>` → world_geometry has 2048 cells, all parallel arrays match length, biomes follow climate-elevation mapping function, no rule rejected. | — |
| **AC-GEO-2** | Bootstrap second continent with SAME `(seed, creative_seed, pipeline_version)` → byte-identical `cells + heightmap + climate_zones + biomes + river_flux` aggregate. (Replay determinism per EVT-A9.) | — |
| **AC-GEO-3** | Bootstrap continent with `cell_count < 1024` via creative_seed.world_scale tampering attempt → rejected with `geography.cell_count_out_of_bounds`. | `geography.cell_count_out_of_bounds` |
| **AC-GEO-4** | Forge admin emits `AddNamedSettlement{cell_id: 1247, name: "Cold Pool Academy", role: Hamlet}` → delta appended, settlements list grows by 1, last_delta_event_id updated. | — |
| **AC-GEO-5** | Forge admin emits same `AddNamedSettlement` with stale `prev_delta_id` (off by 1) → rejected with `geography.delta_order_violation`; settlement NOT added. | `geography.delta_order_violation` |
| **AC-GEO-6** | Forge admin attempts to mutate `creative_seed.archetype` post-bootstrap (not via T6 LLM proposal) → rejected with `geography.creative_seed_immutable_v1`. | `geography.creative_seed_immutable_v1` |
| **AC-GEO-7** | LLM prompt-assembly join `cell_channel<yen_vu_lau>.metadata.geo_cell_id → biomes[id]` returns BiomeKind::Plain; `climate_zones[id]` returns ClimateZone::Subtropical; rendered `[GEOGRAPHIC_CONTEXT]` matches canonical Vietnamese fixture string per S9 prompt-assembly contract. | — |
| **AC-GEO-8** | Snapshot fork at event_id E where parent has 3 deltas all with event_id < E → child world_geometry has identical seed + creative_seed + all 3 deltas; child appends d4; parent appends d4_alpha; readback shows both diverge correctly with no cross-pollination. | — |
| **AC-GEO-9** | RealityManifest declares `geography_seed` but omits `creative_seed` → rejected at bootstrap with `geography.creative_seed_required_when_seeded`. | `geography.creative_seed_required_when_seeded` |
| **AC-GEO-10** | RealityManifest omits `continent_geometries` entirely (single-cell SPIKE_01-style reality) → bootstrap succeeds with no GEO rows; existing PF_001 + MAP_001 + EF_001 + RES_001 bootstrap unchanged; LLM prompt-assembly falls back to creative-archetype text-only hints. | — |
| **AC-GEO-11** | *(Option C bug-fix coverage)* CreativeSeed contains `lore_hooks_per_region: [{scope: SettlementByName("Yên Vũ Lâu"), content: ...}, {scope: PositionRegion{center: (0.45, 0.55), radius: 0.05}, content: ...}, {scope: Archetype, content: ...}]` → post-stage-6 resolution: SettlementByName binds to materialized SettlementId for "Yên Vũ Lâu"; PositionRegion binds to Vec<GeoCellId> covering the 0.05-radius disc around (0.45, 0.55); Archetype scope applies globally. LLM prompt-assembly correctly fetches all 3 hook types for cells in their resolved scopes. (Verifies pre-materialization HookScope contract is synthesizable end-to-end.) | — |

LOCK granted when 10 scenarios pass integration tests against a `geography-generator` reference implementation in `world-service`. CANDIDATE-LOCK on commit landing all schema + acceptance scenarios documented (this commit).

---

## §16 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **GEO-D1** | Hand-authored geometry mode (skip procgen; author uploads explicit Voronoi mesh + biome tags for canon-faithful historical worlds like Tang/Song dynasty maps) | V2+ | Useful for serious wuxia authors; not V1-blocking. |
| **GEO-D2** | POL_001 Political Layer Generator (V1+ feature; provinces + states via priority-queue flood-fill from capital seeds; activates GEO_001 political layer fields) | V1+30d | Unblocks strategy gameplay design. |
| **GEO-D3** | SET_001 Settlement Generator (V1+ feature; burg placement weighted by population + climate + water; SettlementRole assignment) | V1+30d | Pair with GEO-D2. |
| **GEO-D4** | ROUTE_001 Route Network Generator (V1+ feature; Dijkstra over terrain cost; sea-lane derivation; MountainPass chokepoint detection) | V1+30d | Unblocks TVL_001. |
| **GEO-D5** | MAP_001 position auto-derivation from GEO settlement centroids (MAP_001 V1: author manually positions; V1+: positions derive from `world_geometry.settlements[id].cell_id.center`) | V1+ | MAP_001 light reopen at LOCK pending. |
| **GEO-D6** | Paradox-style separate sea-zone graph (V1: single Voronoi mesh with water-cell tags; V2+: derived `sea_zones: Vec<SeaZone>` + `straits: Vec<StraitDecl>` if strategy gameplay needs explicit naval chokepoints) | V2+ | Conditional on strategy gameplay requirements. |
| **GEO-D7** | MagicalAnomaly ClimateZone extension for cultivation/magic settings (V1+ closed-enum bump per R3 additive) | V1+ | Triggered by Wuxia / HighFantasy archetype Bandai validation. |
| **GEO-D8** | GeographyDeltaKind V1+ extensions (MergeProvinces / SplitProvince / TransferProvinceToState / SetCultureRegion) | V1+ | Closed-enum bump per R3 when POL_001 ships. |
| **GEO-D9** | EXPL_001 Exploration + Fog-of-War (per-PC `discovered_cells` set; cell-level exploration mechanics) | V2+ | Pair with V1+ TVL_001. |
| **GEO-D10** | V2+ resource distribution algorithm (climate × biome conditioned Poisson-disk; populates GEO-11 reserved slot) | V2+ | Strategy phase. |
| **GEO-D11** | Multi-continent world (multiple continent channels per reality with explicit ocean-crossing routes between them; V1 default single-continent) | V2+ | Tracked alongside GEO-D6 naval. |
| **GEO-D12** | T6 LLM CreativeSeed extension proposal (V1+ Generator: LLM proposes additional cultures/regions; Forge admin reviews and materializes via T8) | V1+ | Unblocks generative world-extension UX. |

---

## §17 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **GEO-Q1** | Should `generator_pipeline_version` be exposed in prompt-assembly `[GEOGRAPHIC_CONTEXT]`? Pro: versioned narrative debugging. Con: prompt bloat. | Defer to S9 closure pass. |
| **GEO-Q2** | Fallback when authored `CanonicalSettlementDecl.position` lands in water post-stage-2? | V1: snap to nearest land within radius 5; revisit if author UX complains. |
| **GEO-Q3** | Sub-seed split: share `political_seed` with culture (per §5 stage 8) or separate? | V1: shared (matches Azgaar pattern); split V1+ if independent re-roll demanded. |
| **GEO-Q4** | `world_geometry.cells` storage: monolithic Vec serialized blob OR per-cell SQL table for spatial filtering? | V1: monolithic (matches MAP/PF aggregate pattern; 1MB per continent fine). V2+ denormalize if cell-SQL queries needed. |
| **GEO-Q5** | Resource generator V2+ (GEO-D10) owner: GEO_005 vs. RES_001 extension vs. new category? | Defer to V2+ design. |

---

## §18 Cross-references

- [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — catalog entry; owns `GEO-*` namespace
- [`_index.md`](_index.md) — folder index with kernel touchpoints + composition discipline
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `world_geometry` aggregate owned by GEO_001 (row added 2026-05-13)
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — `geography.*` RejectReason namespace (§1.4) + RealityManifest `continent_geometries` extension (§2) added 2026-05-13
- [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) — DRAFT 2026-05-13 entry
- [`06_data_plane/12_channel_primitives.md`](../../06_data_plane/12_channel_primitives.md) — DP-Ch1..Ch10; ChannelScoped at continent tier; `cell_channel.metadata.geo_cell_id` FK pattern
- [`03_multiverse/01_four_layer_canon.md`](../../03_multiverse/01_four_layer_canon.md) — L1/L2/L3 cascade (creative_seed at L2, deltas at L3)
- [`03_multiverse/03_fork_and_cascading.md`](../../03_multiverse/03_fork_and_cascading.md) — MV6 snapshot-fork semantics
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T3 / T4 / T8 sub-shapes added per §2.5
- [`features/00_map/MAP_001_map_foundation.md`](../00_map/MAP_001_map_foundation.md) — visual layer composition (§10); V1+ position auto-derivation GEO-D5
- [`features/00_place/PF_001_place_foundation.md`](../00_place/PF_001_place_foundation.md) — cell-tier composition; PF-D7 procedural generation V1+ consumes GEO
- [`features/00_resource/RES_001_resource_foundation.md`](../00_resource/RES_001_resource_foundation.md) — V2+ resource generator composition (GEO-D10)
- World-map landscape survey 2026-05-13 (research report; Patel dual-mesh + O'Leary erosion + Azgaar pipeline references; archived in conversation log) — algorithmic baseline for §5 stages 1-4

---

## §19 Implementation readiness

**Design layer (this commit):** ✅ aggregate schema + closed enums + 8-stage pipeline + CreativeSeed + delta overlay + sea-zone single-mesh + fork inheritance + composition contracts + RealityManifest extension + `geography.*` namespace + EVT-T3/T4/T8 mapping + 10 acceptance scenarios — all declared.

**Implementation phase (V1):** 📦 generator reference in `world-service` · replay-determinism CI gate (seed → byte-identical aggregate) · `apply_delta` total-function CI gate.

**Downstream consumer integration (V1+):** 📦 MAP_001 light reopen (position auto-derivation row per GEO-D5) · PF_001 procedural place generation activating PF-D7 consuming GEO biome.

**Status:** DRAFT. CANDIDATE-LOCK upon §15 acceptance scenarios passing integration tests against the reference `geography-generator` implementation. LOCK upon downstream consumers (MAP_001 position derivation V1+ / PF_001 procedural seeding V1+ / S9 prompt-assembly geographic-context grounding V1) integrating successfully.
