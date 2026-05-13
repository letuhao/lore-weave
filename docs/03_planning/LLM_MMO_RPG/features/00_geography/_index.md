# 00_geography — Index

> **Category:** GEO — Geography Foundation (foundation tier; sibling of EF_001 + PF_001 + MAP_001 + CSC_001 + RES_001 + PROG_001; procedural geographic substrate)
> **Catalog reference:** [`catalog/cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) (owns `GEO-*` stable-ID namespace)
> **Purpose:** Defines the procedural geographic substrate beneath MAP_001's visual layer. Owns the `world_geometry` aggregate (T2/Channel-continent) with internal layered structure — Voronoi cell partition + heightmap + climate + biome + (V1+ schema-reserved) political layer + settlement layer + route network + culture distribution + resource slots. Generated deterministically from `(seed, creative_seed)` reproducibly; edited via delta-overlay (admin canonization adds named ordered deltas); inherited by snapshot fork via reference + per-reality local deltas. V1 populates geometry/climate/biome layers; V1+ POL_001/SET_001/ROUTE_001 activate political/settlement/route layers; V2+ STRAT_001 consumes locked layers for strategy gameplay.

**Active:** main session (GEO_001 fix cycle complete + GEO_001b DRAFT 2026-05-13 — write-side cycle; boundary lock claimed)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| GEO_001 | **World Geometry** (GEO) | Procedural geographic substrate: `world_geometry` aggregate (T2/Channel-continent; one row per continent channel) + internal layered structure (geometry / climate / biome V1 populated + political / settlement / route / culture / resource V1 schema-reserved) + ~10k Voronoi cells per continent with neighbor adjacency + heightmap u16 + ClimateZone closed enum 8 V1 + BiomeKind closed enum 14 V1 + river network via hydraulic erosion + single-mesh sea zone tagging (water cells via Biome::Ocean/Lake/River) + deterministic-base + delta-overlay editability + CreativeSeed LLM input as procgen constraint + RealityManifest `geography_seed + creative_seed + geography_deltas` REQUIRED V1 per continent + multiverse snapshot-fork inheritance (deltas-at-fork-point copied; new child deltas stay local). Owns `geography.*` RejectReason namespace (13 V1 rule_ids + 3 V1+ reservations). **11 V1-testable acceptance scenarios** AC-GEO-1..11 (AC-GEO-11 added 2026-05-13 write-side cycle verifying HookScope post-materialization resolution per Option C bug-fix). | **DRAFT 2026-05-13** (DRAFT + fix cycle + write-side cycle 2026-05-13) | [`GEO_001_world_geometry.md`](GEO_001_world_geometry.md) | committed → fix cycle → write-side cycle |
| GEO_001b | **CreativeSeed Authoring Flow** (AUTHOR) | Write-side sibling of GEO_001: specifies HOW the CreativeSeed that GEO_001 consumes gets produced. AuthoringProducer 5-variant enum (LlmGenerated V1 / AuthorManual V1 / Imported V1+ / KnowledgeServiceExtracted V1+ / Hybrid V1) + SpatialPreference 14-variant closed enum (Northern/Southern/Equatorial/Coastal/Inland/Insular/Highland/Lowland/RiverValley/NearBiome/NearClimate/NearCulture/NearSettlement/FarFromSettlement/ExplicitPosition/Any) as LLM-friendly alternative to raw (f32, f32) (CreativeSeed.schema_version 1→2 additive per I14) + S9-registered prompt template `world_authoring/v1.tmpl` per §12Y 8-section structure + schema-constrained generation REQUIRED + multi-turn iteration loop (V1 cap N=10 iterations / N=3 retry per iteration / S6 cost cap inherited from S6-D2) + validation pipeline 5 steps + producer abstraction (5 producers; 3 V1 active + 2 V1+ schema-reserved) + knowledge-service grounding contract V1+ when knowledge-service ships per CLAUDE.md. Owns `authoring.*` RejectReason namespace (8 V1 rule_ids + 4 V1+ reservations). 10 V1-testable acceptance scenarios AC-AUTHOR-1..10. **No new aggregate** (AuthoringSession is BFF-held UX state; durable record is `AuthoringMetadata` embedded in RealityManifest + GeographyBorn payload). | **DRAFT 2026-05-13** | [`GEO_001b_authoring_flow.md`](GEO_001b_authoring_flow.md) | (write-side cycle this commit) |

---

## Kernel touchpoints (shared with GEO features)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on T2/Channel-continent aggregates; DP-Ch1..Ch10 channel hierarchy provides per-continent scope
- `06_data_plane/12_channel_primitives.md` — ChannelId binding; ChannelScoped marker trait at continent channel
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=world_geometry`; EVT-T4 System `GeographyBorn` sub-type; EVT-T8 Administrative `Forge:EditGeographyDelta` sub-shape
- `03_multiverse/01_four_layer_canon.md` — L1/L2/L3/L4 canon cascading-read; geography seed lives at L2, deltas live at L3
- `03_multiverse/03_fork_and_cascading.md` — snapshot fork semantics; deltas-at-fork-point inheritance
- `_boundaries/01_feature_ownership_matrix.md` — `world_geometry` owned by GEO_001 (added 2026-05-13)
- `_boundaries/02_extension_contracts.md` §1.4 — `geography.*` RejectReason namespace prefix added 2026-05-13
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension `geography_seed + creative_seed + geography_deltas` (REQUIRED V1 per continent) added 2026-05-13
- `00_map/MAP_001_map_foundation.md` — composes; V1 author-positions map_layout manually; V1+ positions derive from GEO settlement/province centroids
- `00_place/PF_001_place_foundation.md` — composes; V1+ procedural place generation (PF-D7) consumes GEO biome/terrain for PlaceType selection
- `00_resource/RES_001_resource_foundation.md` — composes; V2+ resource distribution generator consumes GEO biome × climate to seed resource_inventory base

---

## Naming convention

`GEO_<NNN>_<short_name>.md`. Sequence per-category. GEO_001 is the foundation; future GEO_NNN candidates (each V1+ or V2+):

- `GEO_002` Political Layer Generator (POL — provinces, states, cultures via priority-queue flood-fill)
- `GEO_003` Settlement Generator (SET — burg placement + role assignment via terrain heuristics)
- `GEO_004` Route Network Generator (ROUTE — Dijkstra over terrain cost; sea lanes; chokepoint detection)
- `GEO_005` Resource Distribution Generator (V2+ — climate × biome conditioned strategic resources)
- `GEO_006` Multi-Continent World (V2+ — multiple continent channels per reality with ocean-crossing routes)
- `GEO_007` Author-Supplied Geometry Mode (V2+ — skip procgen; author uploads explicit mesh for canon-faithful book worlds)

Whether these become separate GEO_NNN files or sub-sections of GEO_001 depends on size at design time. Per foundation-tier discipline, one aggregate per feature file unless internal-layered (the chosen pattern for GEO_001 per user direction).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

GEO_001 is foundational substrate — every domain feature that queries terrain, biome, region identity, or spatial geometry depends on GEO_001 contracts. Boundary discipline:

| Concern | Owner |
|---|---|
| Procedural geometric substrate (Voronoi cells, heightmap, biome) | **GEO_001** |
| Visual UI layer (per-channel positions, image assets, navigable graph) | **MAP_001** |
| Cell semantic identity (PlaceType, ConnectionDecl) | **PF_001** |
| Cell interior scene composition (zones, fixtures, occupants) | **CSC_001** |
| Entity locations (where is X) | **EF_001** |
| Resource production base (V2+ derived from GEO biome × climate) | **RES_001** + future GEO_005 |
| Province ownership + armies + sieges | future **STRAT_001 V2+** |
| Travel mechanics (speed/method matrix) | future **TVL_001 V1+** |
| Per-PC exploration / fog-of-war | future **EXPL_001 V2+** |

Six foundation features (EF + PF + MAP + CSC + RES + PROG + GEO) compose without overlap. GEO is the procedural-geometric SSOT; MAP is the visual SSOT; PF is the cell-semantic SSOT; CSC is the cell-scene-composition SSOT. They reference each other, never redefine.

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) may need a light update post-GEO_001 LOCK to add §4.4g GEO_001 reading for "where does PC spawn relative to biome/region" reference (PC spawn cell still references valid PlaceId per PF_001; GEO provides the biome context for prompt-assembly LLM grounding). Update scheduled at GEO_001 CANDIDATE-LOCK promotion (not in this DRAFT commit).

MAP_001 §15 (cross-references) currently lists "Travel mechanics defers to TVL_001" — light reopen at MAP_001 LOCK should add a row "Visual positions V1+ derive from GEO settlement centroids per GEO_001 §10" tracking the GEO-D5 deferral activation.
