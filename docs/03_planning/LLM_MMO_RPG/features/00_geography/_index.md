# 00_geography — Index

> **Category:** GEO — Geography Foundation (foundation tier; sibling of EF_001 + PF_001 + MAP_001 + CSC_001 + RES_001 + PROG_001; procedural geographic substrate)
> **Catalog reference:** [`catalog/cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) (owns `GEO-*` stable-ID namespace)
> **Purpose:** Defines the procedural geographic substrate beneath MAP_001's visual layer. Owns the `world_geometry` aggregate (T2/Channel-continent) with internal layered structure — Voronoi cell partition + heightmap + climate + biome + (V1+ schema-reserved) political layer + settlement layer + route network + culture distribution + resource slots. Generated deterministically from `(seed, creative_seed)` reproducibly; edited via delta-overlay (admin canonization adds named ordered deltas); inherited by snapshot fork via reference + per-reality local deltas. V1 populates geometry/climate/biome layers; V1+ POL_001/SET_001/ROUTE_001 activate political/settlement/route layers; V2+ STRAT_001 consumes locked layers for strategy gameplay.

**Active:** none. _Last released 2026-05-14_ by main session (GEO_003 SET_001 Settlement Generator DRAFT + /review-impl 1-pass fix cycle — 4 HIGH + 4 MED + LOW-3 resolved in single combined `[boundaries-lock-claim+release]` continuation; lock released; tree clean).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| GEO_001 | **World Geometry** (GEO) | Procedural geographic substrate: `world_geometry` aggregate (T2/Channel-continent; one row per continent channel) + internal layered structure (geometry / climate / biome V1 populated + political / settlement / route / culture / resource V1 schema-reserved) + ~10k Voronoi cells per continent with neighbor adjacency + heightmap u16 + ClimateZone closed enum 8 V1 + BiomeKind closed enum 14 V1 + river network via hydraulic erosion + single-mesh sea zone tagging (water cells via Biome::Ocean/Lake/River) + deterministic-base + delta-overlay editability + CreativeSeed LLM input as procgen constraint + RealityManifest `geography_seed + creative_seed + geography_deltas` REQUIRED V1 per continent + multiverse snapshot-fork inheritance (deltas-at-fork-point copied; new child deltas stay local). Owns `geography.*` RejectReason namespace (13 V1 rule_ids + 3 V1+ reservations). **11 V1-testable acceptance scenarios** AC-GEO-1..11 (AC-GEO-11 added 2026-05-13 write-side cycle verifying HookScope post-materialization resolution per Option C bug-fix). | **DRAFT 2026-05-13** (DRAFT + fix cycle + write-side cycle 2026-05-13) | [`GEO_001_world_geometry.md`](GEO_001_world_geometry.md) | committed → fix cycle → write-side cycle |
| GEO_003 | **Settlement Generator** (SET_001) | V1+30d sibling of GEO_002 POL_001 beneath GEO_001 schema-reserved settlement layer (GEO-8 + GEO-D3). Activates pipeline **stage 6** (Settlement placement — burg-score weighted Poisson-disk; hybrid political-first-then-terrain role assignment; hybrid canonical+procedural population_tier derivation). **POL coordination locked**: POL_001 stage 5 → SET_001 stage 6 → POL_001 stage 8 ordering. Stage 6 STEP D1 populates POL_001's Province.capital_settlement_id (closes POL V1+30d-standalone None field; strategy-substrate Province+State+Settlement triangle complete). Hybrid seed source per SET-D2 (SettlementSeedMode 3-variant Canonical/Procedural/Hybrid default closed enum). Activates 3 V1+30d `GeographyDeltaKind` variants via R3 closed-enum bump (RelocateSettlement / PromoteSettlement / RemoveSettlement; mixed tier — RemoveSettlement Tier 1 ImpactClass=Destructive per S5, Relocate/Promote Tier 2 ImpactClass=Griefing). Adds capability `can_edit_settlement_geography` JWT claim (one-shot migration auto-grants to existing `can_edit_geography` holders at SET ship mirroring POL_001 MED-6). Extends `geography.*` namespace with 14 V1+30d rule_ids (shared per SET-D7; total namespace 47 V1+30d when SET ships). `geography.layer_activation_deferred_v1` lifted for settlement layer at SET ship. **CreativeSeed schema_version bumps 3 → 4** (1 additive field-set settlement_seed_mode + settlement_density_hint; mirrors POL_001 2→3 precedent); LLM authoring template bump v2.tmpl → v3.tmpl. SettlementDensityHint 3-variant default Medium (Sparse 800 cells/settlement / Medium 400 / Dense 200). **No new aggregate** (populates GEO_001's existing `world_geometry.settlements` Vec + Province.capital_settlement_id linkage). **15 V1+30d-testable acceptance scenarios** AC-SET-1..15. 12 deferrals SET-D1..D12 + 5 open questions SET-Q1..Q5; 15 SET-V* validators. **Phase 0 SET-D1..D7 LOCKED via single deep-dive 2026-05-14** with user approval option 1. Owns SET-* sub-prefix in catalog (26 entries SET-1..SET-26 under existing `GEO-*` namespace). | **DRAFT 2026-05-14** | [`GEO_003_settlement_generator.md`](GEO_003_settlement_generator.md) | (this commit) |
| GEO_002 | **Political Layer Generator** (POL_001) | V1+30d activation feature beneath GEO_001 schema-reserved political/state/culture fields (GEO-7 + GEO-10 + GEO-D2 + GEO-D8). Activates pipeline **stage 5** (Political growth — multi-source Dijkstra flood-fill from capital seeds with TerrainCost; province + state assignment per HIGH-3 algorithm pin: deterministic graph-connected-component clustering on orphan provinces with geometric-distance pre-filter per MED-10) + **stage 8** (Culture spread — flood-fill from cultural hearths with CultureBarrier; CultureRegion population; State.culture_tag derivation via mode-over-cells with CultureTag.as_canonical_str() tiebreaker per MED-7). Hybrid seed source per POL-D2 (canonical author declarations take priority + procedural fallback fills remainder; PoliticalSeedMode 3-variant Canonical/Procedural/Hybrid default closed enum; HIGH-2 fix aligned Canonical semantic: NO procedural seeds, canonical flood-fill across entire continent). Activates 4 V1+30d `GeographyDeltaKind` variants via R3 closed-enum bump (MergeProvinces / SplitProvince / TransferProvinceToState / SetCultureRegion — all Tier 1 ImpactClass=Destructive per S5); 2 V2+ reservations new per POL-D14 (CreateState / DestroyState — civil-war state creation V2+). Adds capability `can_edit_political_geography` JWT claim (one-shot migration auto-grants to existing `can_edit_geography` holders at POL ship per MED-6). Extends `geography.*` namespace with **20 V1+30d rule_ids** (shared per POL-D7; /review-impl 2nd-pass added 5 MED-driven rule_ids). `geography.layer_activation_deferred_v1` lifted for political layer at POL ship. **CreativeSeed schema_version bumps 2 → 3** per HIGH-1 fix (3 additive fields mirror GEO_001b 1→2 precedent); LLM authoring template bump v1.tmpl → v2.tmpl. **No new aggregate** (populates GEO_001's existing `world_geometry` fields). **21 V1+30d-testable acceptance scenarios** AC-POL-1..21 (15 original + 6 /review-impl coverage); 14 deferrals POL-D1..D14 + 5 open questions POL-Q1..Q5; 20 POL-V* validators. **Phase 0 D1-D7 LOCKED via single deep-dive 2026-05-14** with user approval option 1. **/review-impl 2-pass fix cycle 2026-05-14**: 1st pass caught HIGH-1+2+3; 2nd pass caught HIGH-4 (fix-introduced regression from HIGH-3) + 12 MED + 3 LOW. All 16 findings batch-applied in this commit. Owns POL-* sub-prefix in catalog (24 entries POL-1..POL-24 under existing `GEO-*` namespace). | **DRAFT 2026-05-14** (DRAFT + /review-impl 2-pass fix cycle) | [`GEO_002_political_layer.md`](GEO_002_political_layer.md) | (this commit) |
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

- ~~`GEO_002` Political Layer Generator (POL — provinces, states, cultures via priority-queue flood-fill)~~ — **DRAFT 2026-05-14** (file: [`GEO_002_political_layer.md`](GEO_002_political_layer.md))
- ~~`GEO_003` Settlement Generator (SET — burg placement + role assignment via terrain heuristics)~~ — **DRAFT 2026-05-14** (file: [`GEO_003_settlement_generator.md`](GEO_003_settlement_generator.md))
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
