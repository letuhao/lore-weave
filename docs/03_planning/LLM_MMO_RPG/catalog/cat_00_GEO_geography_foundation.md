<!-- CHUNK-META
source: design-track manual seed 2026-05-13
chunk: cat_00_GEO_geography_foundation.md
namespace: GEO-*
generated_by: hand-authored (foundation-tier catalog seed)
-->

## GEO — Geography Foundation (foundation tier; sibling of EF + PF + MAP + CSC + RES + PROG; procedural geographic substrate)

> Foundation-level catalog. Owns `GEO-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `GEO-A*` | Axioms (locked invariants) |
> | `GEO-D*` | Per-feature deferrals |
> | `GEO-Q*` | Open questions |

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| GEO-1 | `world_geometry` aggregate (T2 / Channel scope at continent channel; single aggregate with internal layered structure — geometry / climate / biome / political / settlement / route / culture / resource) | ✅ | V1 schema | DP-Ch1..Ch10, MAP-1, PF-1 | [GEO_001 §3.1](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-2 | Voronoi cell partition (~10k cells per continent) with neighbor adjacency graph; deterministic from `(seed, creative_seed)` | ✅ | V1 | GEO-1 | [GEO_001 §5 stage 1](../features/00_geography/GEO_001_world_geometry.md#5-generation-pipeline-eight-stage-overview) |
| GEO-3 | Heightmap layer (per-cell elevation u16; coast/water tagged via height threshold + climate) | ✅ | V1 | GEO-1, GEO-2 | [GEO_001 §5 stage 2](../features/00_geography/GEO_001_world_geometry.md#5-generation-pipeline-eight-stage-overview) |
| GEO-4 | Climate layer (per-cell ClimateZone closed enum 8 V1: Polar / Boreal / Temperate / Mediterranean / Subtropical / Tropical / Arid / Highland; latitude + altitude + ocean-distance model) | ✅ | V1 | GEO-1, GEO-3 | [GEO_001 §4](../features/00_geography/GEO_001_world_geometry.md#4-closed-enums) |
| GEO-5 | Biome layer (per-cell BiomeKind closed enum 14 V1: Ocean / Lake / River / Coast / Beach / Plain / Forest / Jungle / Marsh / Mountain / Hill / Desert / Tundra / Glacier; derived from climate × heightmap) | ✅ | V1 | GEO-1, GEO-4 | [GEO_001 §4](../features/00_geography/GEO_001_world_geometry.md#4-closed-enums) |
| GEO-6 | Hydraulic erosion + river network (per-cell river_flux f32; flux > threshold = navigable river); single-mesh sea zone tagging (Biome::Ocean / Lake / River = water cells; naval adjacency derived) | ✅ | V1 | GEO-1, GEO-3, GEO-5 | [GEO_001 §5 stage 3 + §8](../features/00_geography/GEO_001_world_geometry.md#8-sea-zone-adjacency-single-mesh-with-water-cell-tags) |
| GEO-7 | Province layer (named cell clusters with strategic role; ProvinceId opaque newtype; V1 schema-reserved; V1+ POL_001 populates) | 📦 | V1 schema | GEO-1 | [GEO_001 §3.1 political layer](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-8 | Settlement layer (per-province burg list with SettlementRole closed enum 6 reserved: Hamlet / Village / Town / City / Capital / Fortress; V1 schema-reserved; V1+ SET_001 populates) | 📦 | V1 schema | GEO-1, GEO-7 | [GEO_001 §3.1 settlement layer](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-9 | Route layer (typed edge graph over Voronoi neighbors; RouteKind closed enum 5 reserved: Road / Trail / RiverNavigation / SeaLane / MountainPass; V1 schema-reserved; V1+ ROUTE_001 populates) | 📦 | V1 schema | GEO-1, GEO-6 | [GEO_001 §3.1 route layer](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-10 | Culture layer (per-cell CultureTag opaque; V1 schema-reserved; V1+ CULT_001 or similar populates) | 📦 | V1 schema | GEO-1 | [GEO_001 §3.1 culture layer](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-11 | Resource layer slot (`Vec<ResourceTag>` per province; references RES_001 ResourceKind taxonomy; V1 schema-reserved; V2+ resource distribution generator populates) | 📦 | V2+ | GEO-1, GEO-7, RES-1 | [GEO_001 §3.1 resource layer](../features/00_geography/GEO_001_world_geometry.md#31-world_geometry-t2--channel-continent--primary) |
| GEO-12 | CreativeSeed (LLM-supplied creative direction input: archetype, culture hints, lore hooks, naming styles; consumed by procgen pipeline as constraints — NOT post-hoc decoration) | ✅ | V1 | GEO-1 | [GEO_001 §6](../features/00_geography/GEO_001_world_geometry.md#6-creativeseed-llm-supplied-creative-direction) |
| GEO-13 | Deterministic-base + delta-overlay editability model (base map regenerates from `(seed, creative_seed)`; admin canonizations live as named ordered `GeographyDelta` entries; replay = base + deltas in order) | ✅ | V1 | GEO-1 | [GEO_001 §7](../features/00_geography/GEO_001_world_geometry.md#7-delta-overlay-editability-model) |
| GEO-14 | RealityManifest `geography_seed: GeographySeedDecl + creative_seed: CreativeSeedDecl + geography_deltas: Vec<GeographyDeltaDecl>` (REQUIRED V1 per-continent-channel) | ✅ | V1 | GEO-1, GEO-12, GEO-13 | [GEO_001 §11](../features/00_geography/GEO_001_world_geometry.md#11-realitymanifest-extension) + [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| GEO-15 | `geography.*` RejectReason namespace (10 V1 rule_ids + 4 V1+ reservations) | ✅ | V1 | GEO-1 | [GEO_001 §12](../features/00_geography/GEO_001_world_geometry.md#12-failure-ux-geography-rejectreason-namespace) + [`_boundaries/02_extension_contracts.md` §1.4](../_boundaries/02_extension_contracts.md) |
| GEO-16 | EVT-T4 GeographyBorn sub-type + EVT-T3 aggregate_type=world_geometry + EVT-T8 Forge:EditGeographyDelta (admin canonization delta authoring) | ✅ | V1 | GEO-1, EVT-A11 | [GEO_001 §2.5](../features/00_geography/GEO_001_world_geometry.md#25-event-model-mapping-per-07_event_model-option-c-taxonomy) |
| GEO-17 | Multiverse fork inheritance (snapshot fork copies `(seed, creative_seed, deltas_at_fork_point)`; new child deltas stay local per MV6 snapshot-fork semantic + 4-layer canon cascading-read) | ✅ | V1 | GEO-1, GEO-13 | [GEO_001 §9](../features/00_geography/GEO_001_world_geometry.md#9-multiverse-inheritance) |
| GEO-18 | Composition with MAP_001 (V1+ map_layout positions derive from GEO settlement/province centroids; V1 author still positions manually; V1+ auto-derivation activation) | 📦 | V1+ | GEO-1, MAP-1 | [GEO_001 §10](../features/00_geography/GEO_001_world_geometry.md#10-composition-with-foundation-siblings) |
| GEO-19 | Composition with PF_001 (cell-tier place generation V1+ procedural place seeding consumes GEO biome/terrain for PlaceType selection; PF-D7 procedural place generation deferral activates) | 📦 | V1+ | GEO-1, PF-1 | [GEO_001 §10](../features/00_geography/GEO_001_world_geometry.md#10-composition-with-foundation-siblings) |
| GEO-20 | Composition with RES_001 (V2+ resource distribution generator consumes GEO biome × climate to seed resource_inventory production base) | 📦 | V2+ | GEO-1, RES-1 | [GEO_001 §10](../features/00_geography/GEO_001_world_geometry.md#10-composition-with-foundation-siblings) |
| GEO-21 | V1+30d POL_001 Political Layer Generator (states + boundaries via priority-queue flood-fill from capitals; activates GEO_001 political layer fields) | 📦 | V1+ | GEO-1, GEO-7 | [GEO_001 §16 GEO-D2](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-22 | V1+30d SET_001 Settlement Generator (burg placement weighted by population + climate + water proximity; capital/port/fortress role assignment via terrain heuristics) | 📦 | V1+ | GEO-1, GEO-8 | [GEO_001 §16 GEO-D3](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-23 | V1+30d ROUTE_001 Route Network Generator (Dijkstra over terrain-cost graph; sea lane derivation from coastal water cells; mountain-pass chokepoint detection) | 📦 | V1+ | GEO-1, GEO-9 | [GEO_001 §16 GEO-D4](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-24 | V2+ STRAT_001 Strategy Substrate (province ownership state + armies + supply lines + sieges; consumes locked GEO political/settlement/route/resource layers as read-only inputs) | 📦 | V2+ | GEO-7, GEO-8, GEO-9, GEO-11 | [GEO_001 §16 GEO-D8](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-25 | V2+ EXPL_001 Exploration + Fog-of-War (per-PC `discovered_cells` set; cell-level exploration mechanics; activates GEO cell-detail consumption beyond LLM-context) | 📦 | V2+ | GEO-1 | [GEO_001 §16 GEO-D9](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-26 | V2+ resource distribution algorithm (climate × biome conditioned Poisson-disk for strategic resources; populates GEO-11 reserved slot) | 📦 | V2+ | GEO-11, RES-1 | [GEO_001 §16 GEO-D10](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-27 | V2+ multi-continent world (multiple continent channels per reality with explicit ocean-crossing routes between them; V1 default single-continent) | 📦 | V2+ | GEO-1, DP-Ch1 | [GEO_001 §16 GEO-D11](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
| GEO-28 | V2+ author-supplied geometry mode (skip procgen; author uploads explicit Voronoi mesh + biome tags; useful for canon-faithful book worlds like Tang dynasty maps) | 📦 | V2+ | GEO-1 | [GEO_001 §16 GEO-D12](../features/00_geography/GEO_001_world_geometry.md#16-deferrals) |
