<!-- CHUNK-META
source: design-track manual seed 2026-05-13 (revised 2026-05-13 for license-hygiene framing)
chunk: cat_00_TMP_tilemap_foundation.md
namespace: TMP-*
generated_by: hand-authored (SPIKE_03 graduation; genre prior art surveyed)
-->

## TMP — Tilemap Foundation (foundation tier; sibling of MAP + CSC; procedural-generation visual layer)

> Foundation-level catalog. Owns `TMP-*` stable-ID namespace.
>
> | Sub-prefix | What |
> |---|---|
> | `TMP-A*` | Axioms (locked invariants) |
> | `TMP-D*` | Per-feature deferrals |
> | `TMP-Q*` | Open questions |

**Graduated from:** [`features/_spikes/SPIKE_03_tilemap_world_view.md`](../features/_spikes/SPIKE_03_tilemap_world_view.md) (DRAFT 2026-04-27) — concept validated; this catalog row claims namespace + V-tier commitment.

**Genre prior art surveyed:**
- Heroes of Might and Magic III (1999, New World Computing) — pioneered the zone-graph procedural map generator
- Battle for Wesnoth (2003+, GPL v2+) — open-source tile-based fantasy TBS
- Civilization V / VI (Firaxis) — climate-band procedural map generation
- Dwarf Fortress (2002+, Bay 12 Games) — multi-pass deterministic-seed world generation
- Caves of Qud (2015+, Freehold Games) — biome composition with set-piece interleaving
- VCMI (2007+, GPL v2 or later) — open-source HoMM3 engine reimplementation; well-documented procedural map generator at `lib/rmg/`; cited as one open-source reference for the genre patterns surveyed here
- Roguelike literature (Brogue, DCSS, NetHack) — tile state machines, connectivity invariants

**Algorithm foundations (cited per-doc Prior Art sections):**
- Fruchterman & Reingold (1991) — force-directed graph drawing
- Penrose (1974) — aperiodic tiling
- Kahn (1962) / Tarjan (1976) — topological sort, connected components
- Dijkstra (1965) — dining philosophers (cross-zone locking)
- Hart, Nilsson & Raphael (1968) — A* pathfinding
- Gamma et al. (1994) — Strategy + Visitor patterns

### Catalog entries

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| TMP-1 | `tilemap_view` aggregate (T2 / Channel scope; per-non-cell-channel; cell tier uses CSC_001 16×16 interior — TMP-A1) | 📋 | V1+30d | MAP-1, PF-1, CSC-1, DP-Ch* | [TMP_001 §3.1](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-2 | `tilemap_template` aggregate (T2 / Reality scope; author-declared template document) | 📋 | V1+30d | TMP-1 | [TMP_001 §3.2](../features/00_tilemap/TMP_001_tilemap_foundation.md) + [TMP_004](../features/00_tilemap/TMP_004_template_authoring.md) |
| TMP-3 | 4-layer composition architecture (L1 hand-authored skeleton + L2 procedural terrain + L3 LLM zone classifier + L4 LLM regional narration) — LoreWeave-internal pattern derived from CSC_001 v3→v4 | 📋 | V1+30d L1+L2 / V2 L3+L4 | TMP-1, TMP-2, AIT-1 | [TMP_001 §4](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-4 | Zone-graph paradigm: `Vec<ZoneSpec>` + `Vec<ZoneEdgeSpec>` with 5-variant `PassageKind` (Threshold / Open / Hint / Adversarial / Portal) | 📋 | V1+30d | TMP-2, MAP-5 | [TMP_002 §2](../features/00_tilemap/TMP_002_zone_placement.md) + [TMP_007](../features/00_tilemap/TMP_007_connections_and_guards.md) |
| TMP-5 | Force-directed zone placement using Fruchterman-Reingold (1991) with simulated annealing | 📋 | V1+30d | TMP-4 | [TMP_002 §3](../features/00_tilemap/TMP_002_zone_placement.md) |
| TMP-6 | Penrose-tiling-based zone shape generator (irregular zone polygons via aperiodic vertex subdivision per Penrose 1974) | 📋 | V1+30d | TMP-5 | [TMP_002 §4](../features/00_tilemap/TMP_002_zone_placement.md) |
| TMP-7 | 4-variant `TileState` enum (Walkable / Open / Obstacle / Occupied) — standard procedural-level-gen state machine | 📋 | V1+30d | TMP-1 | [TMP_001 §5](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-8 | Fractalize algorithm (random-distant-tile path-extension to build free-path skeleton inside zones) — standard roguelike level-gen pattern | 📋 | V1+30d | TMP-7 | [TMP_002 §5](../features/00_tilemap/TMP_002_zone_placement.md) |
| TMP-9 | Pipeline modificator pattern with explicit dependency graph + parallel execution (Strategy/Visitor patterns per Gamma et al. 1994; topological sort per Kahn 1962) | 📋 | V1+30d | TMP-3, EVT-G* | [TMP_003 §2](../features/00_tilemap/TMP_003_pipeline_modificators.md) |
| TMP-10 | Modificator catalog V1+30d: TerrainPainter / ObstaclePlacer / ConnectionsPlacer / RoadPlacer / RiverPlacer / ObjectManager / TreasurePlacer — 7 V1+30d modificators | 📋 | V1+30d | TMP-9 | [TMP_003 §3](../features/00_tilemap/TMP_003_pipeline_modificators.md) |
| TMP-11 | Tiered treasure value system: `Vec<{min, max, density}>` per zone — standard tiered-loot pattern with per-tier value range + placement density | 📋 | V1+30d | TMP-2 | [TMP_006 §2](../features/00_tilemap/TMP_006_treasure_and_objects.md) |
| TMP-12 | "Never seal a gap" connectivity invariant: every object placement preserves zone path-connectivity via connected-components check (Tarjan 1976) | 📋 | V1+30d | TMP-11, TMP-8 | [TMP_006 §4](../features/00_tilemap/TMP_006_treasure_and_objects.md) |
| TMP-13 | Biome obstacle-set architecture: `BiomeSelectionRules` author-tunable composition (engine default = sensible mix of mountain/tree/lake-or-crater/plant/rock/structure/animal/other) | 📋 | V1+30d | TMP-10 | [TMP_005 §2](../features/00_tilemap/TMP_005_biome_and_obstacles.md) |
| TMP-14 | `PassageKind` V1+30d (5 variants — Threshold/Open/Hint/Adversarial/Portal): Threshold (default; monster-guard + road) / Open (free passage) / Hint (placement-influence-only) / Adversarial (push apart) / Portal (always teleport pair) | 📋 | V1+30d | TMP-4 | [TMP_007 §2](../features/00_tilemap/TMP_007_connections_and_guards.md) |
| TMP-15 | `inherit_*_from` inheritance fields on ZoneSpec (inherit_treasure_from / inherit_terrain_from / inherit_mines_from / inherit_towns_from / inherit_custom_objects_from) — DRY template authoring | 📋 | V1+30d | TMP-2 | [TMP_004 §3](../features/00_tilemap/TMP_004_template_authoring.md) |
| TMP-16 | `ZoneRole` enum V1+30d (4 variants — Wilderness / Hub / Forbidden / Sea); V2+ adds AllyHome / RivalHome for multiplayer | 📋 | V1+30d | TMP-2 | [TMP_004 §2](../features/00_tilemap/TMP_004_template_authoring.md) |
| TMP-17 | Author-template inheritance + finalization (resolves `inherit_*_from` references before generation begins; cycle detection via Tarjan 1972 SCC) | 📋 | V1+30d | TMP-15 | [TMP_004 §3.1](../features/00_tilemap/TMP_004_template_authoring.md) |
| TMP-18 | RealityManifest extension: `tilemap_templates: HashMap<ChannelTier, TilemapTemplateRef>` (OPTIONAL V1+30d; engine-defaulted) + `tilemap_defaults: TilemapDefaults` | 📋 | V1+30d | TMP-2 | [`_boundaries/02_extension_contracts.md` §2](../_boundaries/02_extension_contracts.md) |
| TMP-19 | `tilemap.*` RejectReason namespace (16 V1+30d rule_ids + 6 V1+ reservations — see TMP_001 §9) | 📋 | V1+30d | TMP-1 | [TMP_001 §9](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-20 | EVT-T4 System sub-types: `TilemapBorn` (per-channel at RealityManifest bootstrap) + `ZonesPlaced` (after zone placement) | 📋 | V1+30d | TMP-1, EVT-A11 | [TMP_001 §2.5](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-21 | EVT-T3 Derived: `aggregate_type=tilemap_view` field deltas + `aggregate_type=tilemap_template` schema deltas | 📋 | V1+30d | TMP-20 | [TMP_001 §2.5](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-22 | EVT-T8 Administrative sub-shapes V1+30d: `Forge:RegenTilemap` (re-roll seed; CosmeticOnly OR FullRebootstrap variants) + `Forge:EditTemplate` + `Forge:OverridePlacement` | 📋 | V1+30d | TMP-20 | [TMP_001 §2.5](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-23 | EVT-T5 Generated for L3 zone classifier (LLM-proposed entity → zone mapping; V2 active) + L4 narration (cached prose per zone × season × structural_state) | 📋 | V2 | TMP-20, EVT-G* | [TMP_008 §3-4](../features/00_tilemap/TMP_008_llm_integration.md) |
| TMP-24 | Deterministic seed (Blake3 hash of reality_id + channel_id + template_id + seed_offset) — replay-deterministic per TDIL-A9 | 📋 | V1+30d | TMP-1 | [TMP_001 §6](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-25 | MAP_001 position reconciliation: tilemap derives tile_coord from MAP_001 author-positioned (x, y) — MAP_001 is source of truth; tilemap is derived render layer | 📋 | V1+30d | TMP-1, MAP-3 | [TMP_001 §7](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-26 | Cell-tier integration: cells appear as TileMapObjects on parent-tier tilemap; click cell → drill into CSC_001 16×16 interior. Cell tier itself has NO tilemap_view (CSC_001 is authoritative) | 📋 | V1+30d | TMP-1, CSC-1 | [TMP_001 §8](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-27 | Tile compact encoding: terrain layer stored as `Vec<u8>` (bytea) — 1 byte per tile; `terrain_kind: u8` enum index | 📋 | V1+30d | TMP-1 | [TMP_001 §10](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-28 | Grid sizes per tier V1+30d: Continent 256×256 / Country 192×192 / District 128×128 / Town 64×64 — author-configurable via `tilemap_defaults` | 📋 | V1+30d | TMP-1 | [TMP_001 §10](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-29 | Single-thread mode flag (deterministic order, slower) + multi-thread default (relies on dependency-graph correctness) | 📋 | V1+30d | TMP-9 | [TMP_003 §4](../features/00_tilemap/TMP_003_pipeline_modificators.md) |
| TMP-30 | Author-template versioning + upgradability: V1+30d schema-additive only per TMP-A8 (aligned with foundation I14) | 📋 | V1+30d | TMP-2 | [TMP_004 §5](../features/00_tilemap/TMP_004_template_authoring.md) |
| TMP-31 | L3 LLM zone-classifier contract: input = zone summary + entities-to-place; output = `Vec<{entity_id, zone_id}>`; 3-retry feedback loop + canonical-default fallback (CSC_001 v3→v4 pattern reuse) | 📋 | V2 | TMP-20, EVT-G* | [TMP_008 §3](../features/00_tilemap/TMP_008_llm_integration.md) |
| TMP-32 | L4 LLM regional narration: per-zone prose (1-2 paragraphs); cached per `(channel_id, season, structural_state, prompt_template_version)`; bypass cache only on Forge:RegenTilemap or template change | 📋 | V2 | TMP-31 | [TMP_008 §4](../features/00_tilemap/TMP_008_llm_integration.md) |
| TMP-33 | LLM cost bound: ~4-5K tokens per full tilemap composition (L3 + L4); independent of grid size (LLM never sees raw tiles, only zone summaries) | 📋 | V2 | TMP-31, TMP-32 | [TMP_008 §5](../features/00_tilemap/TMP_008_llm_integration.md) |
| TMP-34 | V3 RMG wizard: author parameters → seed → fully procedural reality at creation time. Player-facing parameter capture ("wuxia kingdom, 4 sects, mountain north, sea south"). Out of V2 scope. | 📦 | V3 | TMP-1..TMP-33 | [TMP_001 §16 TMP-D1](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-35 | V3 manual paint UX (`Forge:PaintTile` per-tile editor) — for author refinement after RMG | 📦 | V3 | TMP-34 | [TMP_001 §16 TMP-D2](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-36 | V2+ fog-of-war integration: per-PC `discovered_tiles` overlay (consumes MAP-D10 + PCS_001) | 📦 | V2+ | TMP-1, PCS-* | [TMP_001 §16 TMP-D3](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-37 | V2 travel encounters: tile traversal triggers encounter checks (e.g., forest = bandit; mountain = beast); consumes SPIKE_02 D3 | 📦 | V2 | TMP-1, EVT-G* | [TMP_001 §16 TMP-D4](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-38 | V2 terrain movement modifiers: speed_modifier per TerrainKind consumed by TVL_001 + MAP-6 distance_units | 📦 | V2 | TMP-1, MAP-6 | [TMP_001 §16 TMP-D5](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-39 | V2 sprite atlas pipeline (TMP_009 — mirror of MAP_002 asset pipeline pattern) | 📦 | V2 | TMP-1 | [TMP_001 §16 TMP-D6](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-40 | V2 tactical-combat tilemap derivative (consumes CSC-D8 + battlefield mode) | 📦 | V2 | TMP-1, CSC-* | [TMP_001 §16 TMP-D7](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-41 | V2+ procedural settlement layouts (zoom-in on Town tier: streets + buildings) | 📦 | V2+ | TMP-1 | [TMP_001 §16 TMP-D8](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-42 | V3 multi-level (sub-tier) verticality: PocketDimension / TimePortal (consume MAP-D9 + MAP-D2) | 📦 | V3 | TMP-1, MAP-5 | [TMP_001 §16 TMP-D9](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-43 | V2 dwellings + mines as `tilemap_view` objects (RES_001 integration; standard creature-generator + resource-node pattern from genre prior art) | 📦 | V2 | TMP-1, RES-1 | [TMP_001 §16 TMP-D10](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
| TMP-44 | V2+ multiplayer ZoneRole variants (AllyHome / RivalHome) for competitive scenarios | 📦 | V2+ | TMP-2 | [TMP_001 §16 TMP-D12](../features/00_tilemap/TMP_001_tilemap_foundation.md) |
