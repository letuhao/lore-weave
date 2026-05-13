# TMP_001 — Tilemap Foundation

> **Conversational name:** "Tilemap Foundation" (TMP). The procedural-generation visual layer for the world map. **MAP_001** owns the author-positioned logical graph; **TMP_001** owns the procedurally-generated tilemap rendered on top. Both ship; both are canonical at their layer; TMP_001 derives positions from MAP_001 (subscribe pattern).
>
> **Category:** TMP — Tilemap Foundation (foundation tier; sibling of MAP_001 + CSC_001 + EF_001 + PF_001)
> **Status:** **DRAFT 2026-05-13** (initial authoring; graduated from SPIKE_03; revised 2026-05-13 for license-hygiene framing); Phase 3 review + §15 acceptance walk pending
> **Catalog refs:** [`cat_00_TMP_tilemap_foundation.md`](../../catalog/cat_00_TMP_tilemap_foundation.md) — owns `TMP-*` namespace (`TMP-A*` axioms · `TMP-D*` deferrals · `TMP-Q*` open questions)
> **Builds on:** [MAP_001 Map Foundation](../00_map/MAP_001_map_foundation.md) §5 author-positioned (x, y) source-of-truth (extends with derived tile_coord), [CSC_001 Cell Scene Composition](../00_cell_scene/CSC_001_cell_scene_composition.md) v3→v4 4-layer architecture pattern (mirrored here), [PF_001 Place Foundation](../00_place/PF_001_place_foundation.md) cell-tier integration (cells appear as objects on parent-tier tilemap), [AIT_001 AI Tier](../16_ai_tier/AIT_001_ai_tier_foundation.md) AIT-A4 hybrid 2-stage pattern (cheap + lazy-LLM; reused at TMP_008), [TDIL_001 Time Dilation](../17_time_dilation/TDIL_001_time_dilation_foundation.md) TDIL-A9 replay-determinism (TMP-A4 seeded generation), [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §16 RealityManifest extension (`tilemap_templates` + `tilemap_defaults`), [DP-Ch1..Ch53](../../06_data_plane/) channel hierarchy (every non-cell channel may have a `tilemap_view`), [07_event_model](../../07_event_model/) Option C taxonomy (T4 System TilemapBorn/ZonesPlaced; T3 Derived for state deltas; T8 Administrative for Forge edits; T5/T6 V2 for LLM layers)
> **Genre prior art:** see §1.1 below; multi-game survey of zone-based procedural-map techniques (HoMM3, Wesnoth, Civilization, Dwarf Fortress, Caves of Qud, Paradox titles). Specific implementations referenced in §17 Prior Art bibliography.
> **Defers to:** future `TMP_009` V2 sprite atlas (TMP-D6) · `TMP_010` V2 procedural settlements (TMP-D8) · `TMP_011` V3 RMG wizard (TMP-D1 + TMP-D2) · `TMP_012` V2+ tactical combat (TMP-D7) · MAP_002 V1+ asset pipeline (shared image-asset architecture)

---

## §1 Why this exists

Three concrete user-experience gaps that MAP_001's logical graph cannot close:

**Gap 1 — Immersion gap.** Node-link graphs feel abstract. Players who come from genre prior art (Heroes of Might and Magic, Civilization, Dwarf Fortress, Wesnoth, Bannerlord, Caves of Qud) expect a continuous explorable canvas with terrain, rivers, roads, biomes. SPIKE_03 user explicit ask: "bản đồ hiện tại khá chán vì chỉ có cell và graph. tôi muốn thiết kế thêm bản đồ big map ... giống như map generating của mấy game như hero of might and magic?" Without a tilemap layer, the MMO-RPG genre feel is dampened.

**Gap 2 — Spatial-reasoning gap for authors.** When designing book canon ("the bandit camp is in the forest north of the river crossing"), authors need a visual canvas to position narrative elements. MAP_001 graph nodes don't carry biome / terrain context that anchors the prose. TMP_001 procedural terrain provides the spatial scaffold that authors edit + LLM grounds against.

**Gap 3 — LLM-grounding gap.** LLM-driven NPCs need to "know" the world they live in. A MAP_001 edge `Forest → Mountain` gives less context than "you see oak trees thinning into pine; ahead the path climbs toward snow-capped peaks where the bandits keep their fortress." TMP_008 L4 regional narration closes this.

### 1.1 Genre prior art survey

Procedural map generation for zone-based exploration games has ~25 years of design lineage. We surveyed the design space across genres to identify which patterns are universally-converged-on and which are project-specific. Pattern convergence increases confidence; project-specific choices stay open.

| Title | Era | Pattern relevance |
|---|---|---|
| **Heroes of Might and Magic III** | 1999, New World Computing | Original "Random Map Generator" UX — author picks template, engine produces playable map. Zone-graph paradigm + tiered treasure + biome obstacles + monster-guarded passages. Genre-defining for our shape. (Reimplemented as open source via VCMI — see §17 Prior Art.) |
| **Civilization V / VI** | 2010 / 2016, Firaxis | Climate-band procedural generation (latitude-based terrain). Resource placement balanced per-civilization start. Influences our zone-balance discipline. |
| **Battle for Wesnoth** | 2003+, open source | Tile-based fantasy TBS with author-extensible map generators. Demonstrates open-source viability + community templates. |
| **Dwarf Fortress** | 2002+, Bay 12 Games | Multi-pass world generation with deterministic seed: terrain → erosion → biomes → civilizations → history. Influences our pipeline ordering. |
| **Caves of Qud** | 2015+, Freehold Games | Procedural biome composition with hand-authored "set pieces" interleaved. Demonstrates the L1 hand-authored + L2 procedural mix that informs our 4-layer model. |
| **Europa Universalis IV / Crusader Kings III** | Paradox | Large-scale region graphs (~5000+ provinces). Demonstrates that authored hierarchical maps scale to grand-strategy density. Influences our 4-tier (Continent → Country → District → Town) hierarchy. |
| **Bannerlord / Total War campaign maps** | Modern | Camera-scrollable tilemap canvas with cells as drill-in points. Demonstrates the "tilemap canvas + click-into-region" UX our SPIKE_03 user requested. |
| **Roguelike literature** (Brogue, DCSS, NetHack) | 1980s+ | Tile state machines + connectivity invariants + level generators with "no unreachable rooms" guarantees. Established the "never seal a gap" pathfinding invariant we use. |

Cross-cutting patterns we adopt (because they're universally-converged across the survey, not project-specific):

- **Zone-graph paradigm** — every game above models its world as zones-with-connections, not raw tile grid. Anchors our MAP_001 + TMP_001 split.
- **Tile state machine** — every roguelike + every CRPG procedural-level system uses a `walkable / placeable / obstacle / occupied` 4-state model (or similar 3-5 state variant). Standard CS pathfinding pattern.
- **Tiered treasure value system** — every loot-based game (Diablo, HoMM, roguelikes) uses value-tier × placement-density. Standard procedural loot pattern.
- **"Never seal a gap" connectivity invariant** — every level-gen system enforces this (else you get unreachable areas). Standard procedural-content-generation axiom.
- **Modificator / pass pipeline with dependencies** — Dwarf Fortress (4-pass world gen), Caves of Qud (similar), HoMM3-RMG-derivatives all use this. Maps to the visitor/strategy + topological-sort pattern (Gamma et al. 1994; Kahn 1962).

### 1.2 LoreWeave-specific design choices

Beyond the survey-convergent patterns, TMP_001 makes specific design choices distinct to LoreWeave:

| Choice | Why |
|---|---|
| **4-layer LLM-augmented composition (L1 + L2 + L3 + L4)** | OUR pattern, derived from CSC_001 v3→v4 lessons (cell-interior composition). L3 LLM zone classifier + L4 regional narration are LoreWeave-specific because the surveyed games don't have LLM-driven NPCs. Bounds LLM cost by keeping LLM categorical (TMP-A9). |
| **MAP_001 author-positioned source-of-truth, TMP_001 derived** | Specific to our two-layer split (logical graph + rendered tilemap). Surveyed games either have only-grid (no separate graph layer) or only-graph (no tile rendering). Our split enables a11y/low-bandwidth fallback (TMP-A6). |
| **Cell tier has NO `tilemap_view`** (CSC_001 16×16 interior authoritative) | LoreWeave-specific because we have CSC_001 as a separate cell-interior composition system. Surveyed games either render cells as part of the same tilemap or have no cell-interior layer at all. (TMP-A1) |
| **Schema-additive evolution + V-tier ramp (V1+30d L1+L2 → V2 LLM → V3 RMG wizard)** | LoreWeave's broader I14 + foundation evolution discipline. (TMP-A8) |
| **Deterministic seed = Blake3(reality_id || channel_id || template_id || seed_offset)** | LoreWeave-specific because TDIL_001 requires replay-deterministic generation (TDIL-A9). Surveyed games use various seed strategies. (TMP-A4) |
| **5-variant `PassageKind` enum** (Threshold / Open / Hint / Adversarial / Portal) | Our naming + semantics. Functional equivalents exist in genre prior art under various names. See §2.2. |
| **4-variant `ZoneRole` enum V1+30d** (Wilderness / Hub / Forbidden / Sea) | Our naming + V-tier scoping. V2+ multiplayer adds AllyHome / RivalHome. See §2.1. |

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **TilemapView** | Aggregate `tilemap_view` (T2 / Channel scope) | Per non-cell channel. For cell tier: CSC_001 16×16 interior is authoritative (no `tilemap_view`). Per TMP-A1. |
| **TilemapTemplate** | Aggregate `tilemap_template` (T2 / Reality scope) | Author-declared template document. Multiple templates per reality (one per tier or per genre). RealityManifest references via `TilemapTemplateRef`. |
| **GridSize** | `(width: u32, height: u32)` | V1+30d defaults: Continent 256×256 / Country 192×192 / District 128×128 / Town 64×64. Author-configurable. |
| **TerrainKind** | Closed enum 10 V1+30d | `Grass / Forest / Mountain / Water / Sand / Snow / Swamp / Road / Rough / Subterranean`. Stored as u8 index. (Generic game-dev terrain enum; appears in roughly identical form across the entire genre prior art surveyed in §1.1.) |
| **TileState** | Closed enum 4 (standard pathfinding pattern) | `Walkable` (passable + no object — was `Free`) / `Open` (passable + can fit object — was `Possible`) / `Obstacle` (blocked) / `Occupied` (object placed). Standard procedural-level-gen state machine; see Žára 2014 RogueDev talks for pedagogical introduction. Internal pipeline state; not exposed to player UI. |
| **ZoneSpec** | Author intent for a zone (TilemapTemplate inner type) | Authoring shape — see TMP_004 §2 for full schema. Includes zone_id + zone_role + size + treasure_tiers + mines + town_hints + terrain_types + monster_strength + connections. |
| **ZoneRole** | Closed enum 4 V1+30d (LoreWeave-distinct partitioning) | See §2.1. |
| **ZoneEdge** | Connection between two zones | `{zone_a, zone_b, kind: PassageKind, guard_strength, road: RoadOption}`. |
| **PassageKind** | Closed enum 5 (LoreWeave-distinct naming) | See §2.2. |
| **TilemapObject** | Object placed on tilemap (creature dwelling, treasure pile, town, mine, landmark, monolith) | Generic kind enum 7 V1+30d (Treasure / MonsterLair / Town / Mine / Landmark / Monolith / Decoration). Most are V2+ deferred per scope. |
| **BiomeSet** | Per-zone obstacle-set selection at runtime | Configurable selection rule (`BiomeSelectionRules`) on the template, not engine-baked. Default rules engine-shipped (sensible mix of mountain + tree + lake/crater + plant/rock objects); author overrides per template. See TMP_005 §2-§4. |
| **TreasureTierSpec** | `{min, max, density}` per zone | Standard tiered-loot pattern; appears across the genre prior art. Multiple tiers per zone (e.g., 3 tiers: cheap/medium/expensive). |
| **TilemapSeed** | u64 deterministic seed (Blake3 hash of reality_id + channel_id + template_id) | Per TMP-A4 — replay-deterministic via TDIL-A9. Re-roll for variety creates new seed via Forge:RegenTilemap. |
| **GenerationSource** | Closed enum 2 (mirror CSC_001 `Layer3Source`) | `EngineGenerated` (V1+30d L1+L2 only; deterministic) / `LlmAugmented { model: String, attempts: u32, generated_at_fiction_time: FictionTime }` (V2 L3+L4 layered on top). |
| **MapLayoutDerivedRef** | Back-pointer to MAP_001 `map_layout` row | Tilemap derives child-cell positions from MAP_001. See §7. |

### 2.1 `ZoneRole` enum (4 V1+30d variants; V2+ adds 2 more)

```rust
pub enum ZoneRole {                    // V1+30d 4 variants
    Wilderness,                        // exploration zone; treasure + monster guards; no main town
    Hub,                               // crossroads zone; not fractalized; single straight path through
    Forbidden,                         // completely blocked; only enterable via Portal-kind passage
    Sea,                               // water zone (one per tilemap maximum)

    // V2+ multiplayer (TMP-D12 reserved):
    // AllyHome,                       // friendly player's start zone
    // RivalHome,                      // hostile player's start zone
}
```

V1+30d uses 4 variants; V2+ multiplayer scenarios may activate AllyHome / RivalHome (currently TMP-D12 reservation). Hub and Forbidden roles cover crossroads and locked-region narrative needs. Sea is a singleton per tilemap.

### 2.2 `PassageKind` enum (5 V1+30d variants)

```rust
pub enum PassageKind {
    Threshold,    // monster-guarded passage + road; default for most authored edges
    Open,         // free passage; zones share a wide border; no guard, no road
    Hint,         // narrative-only edge; no physical passage; influences placement spatial reasoning
    Adversarial,  // pushes zones apart (negative attraction); for rival-faction zones
    Portal,       // teleport pair; always materialized as a monolith pair regardless of border
}
```

| Variant | When appropriate |
|---|---|
| `Threshold` (default) | Most authored edges. Adventure feel: cross from one region to another via a guarded passage. |
| `Open` | "Open border" zones. Two adjacent kingdoms with free trade. No monster combat between them. |
| `Hint` | Narrative connections that don't physically realize. E.g., "Zone A's lore is tied to Zone B (sister city across the sea)" — author intent only. |
| `Adversarial` | Rival zones that must be far apart. E.g., "two rival sects in same continent" — author wants spatial separation. |
| `Portal` | Forbidden / dimensional travel. Zone with no overland route, only reachable via teleport. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

TMP_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| TMP event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Tilemap birth at RealityManifest bootstrap | **EVT-T4 System** | `TilemapBorn { channel_id, tier, grid_size, template_id, seed }` | DP-Internal RealityBootstrapper (Synthetic actor) | One per non-cell channel from `root_channel_tree`. Cell channels skipped (CSC_001 authoritative). |
| Zone-placement-complete (after force-directed converges) | **EVT-T4 System** | `ZonesPlaced { channel_id, zone_count, total_iterations }` | tilemap-service zone-placer | Audit + perf-debug; precondition for modificator pipeline kickoff. |
| Tilemap state delta (terrain repaint, object add/remove, connection update) | **EVT-T3 Derived** | `aggregate_type=tilemap_view` (field delta) | Aggregate-Owner role (tilemap-service post-validate) | Causal-ref to triggering EVT-T8 Administrative (Forge edit) or EVT-T1 Submitted (V2+ in-fiction trigger). |
| Template schema delta | **EVT-T3 Derived** | `aggregate_type=tilemap_template` | Same | Author edits ZoneSpec via Forge → template delta → cascade to `tilemap_view` re-generation. |
| Re-roll tilemap (re-seed; full re-generate) | **EVT-T8 Administrative** | `Forge:RegenTilemap { channel_id, mode: CosmeticOnly \| FullRebootstrap, new_seed: u64 }` | WA_003 Forge | Audit-grade. CosmeticOnly preserves objects, re-paints terrain. FullRebootstrap re-runs entire pipeline. |
| Author edits template | **EVT-T8 Administrative** | `Forge:EditTemplate { template_id, edit_kind, before, after }` | WA_003 Forge | edit kinds V1+30d: AddZone / RemoveZone / EditZoneSpec / AddConnection / RemoveConnection / EditConnection / EditTreasureTier. |
| Author manually overrides placement (V3 paint UX preview) | **EVT-T8 Administrative** | `Forge:OverridePlacement { channel_id, tile_coords[], override_kind }` | WA_003 Forge | V1+30d: schema-reserved; V3 active. override_kind V3: PaintTerrain / PlaceObject / RemoveObject. |
| L3 LLM zone classifier output (V2) | **EVT-T6 Proposal** + **EVT-T5 Generated** | `aggregate_type=tilemap_view` (L3 payload) | LLM via tilemap-service zone-classifier (Synthetic role) | Validated by L3 guardrails; falls back to engine canonical-default on rejection. V1+30d: reserved only. |
| L4 LLM regional narration (V2) | **EVT-T5 Generated** | `aggregate_type=tilemap_view` (L4 narration cache delta) | LLM via tilemap-service narration (Synthetic role) | Cached per `(channel_id, season, structural_state, prompt_template_version)`. V1+30d: reserved only. |

Boundary registry additions (`_boundaries/01_feature_ownership_matrix.md`):
- EVT-T4 System sub-types row gains `TilemapBorn` + `ZonesPlaced` (TMP_001-owned alongside EF_001 EntityBorn + PF_001 PlaceBorn + MAP_001 LayoutBorn)
- EVT-T3 Derived sub-types row gains `aggregate_type=tilemap_view` + `aggregate_type=tilemap_template`
- EVT-T8 Administrative sub-shapes registry gains `Forge:RegenTilemap` + `Forge:EditTemplate` + `Forge:OverridePlacement`
- EVT-T5 + EVT-T6 sub-types row gets V2-reserved entries for L3/L4 (no V1+30d activation)

---

## §3 Aggregate inventory

Two aggregates owned by TMP_001:

### 3.1 `tilemap_view` (T2 / Channel scope) — PRIMARY

Per-non-cell-channel runtime tilemap state. Created at RealityManifest bootstrap; mutated via Forge actions.

```rust
#[derive(Aggregate)]
#[dp(type_name = "tilemap_view", tier = "T2", scope = "channel")]
pub struct TilemapView {
    pub channel_id: ChannelId,                              // primary key (per non-cell channel)
    pub tier: ChannelTier,                                  // denormalized: Continent | Country | District | Town (NOT Cell — TMP-A1)
    pub grid_size: GridSize,                                // (width, height) — from tilemap_defaults or per-channel override
    pub template_id: TilemapTemplateId,                     // ref to tilemap_template aggregate (per-reality)
    pub seed: u64,                                          // deterministic Blake3 hash — per TMP-A4
    pub zones: Vec<ZoneRuntime>,                            // runtime zone state (positions + assigned tiles + objects); see §3.1.1
    pub terrain_layer: Vec<u8>,                             // flat grid; index = y*width + x; value = TerrainKind u8 index
    pub object_placements: Vec<TilemapObjectPlacement>,     // all placed objects (V1+30d: treasures + landmarks + decorations; V2+ extends)
    pub road_segments: Vec<RoadSegment>,                    // polylines of road tiles (post-RoadPlacer)
    pub river_segments: Vec<RiverSegment>,                  // polylines + crossable_at tiles (post-RiverPlacer)
    pub child_cell_anchors: HashMap<ChannelId, TileCoord>,  // derived from MAP_001 positions per TMP-A6; updated via subscribe
    pub generation_source: GenerationSource,                // EngineGenerated V1+30d / LlmAugmented V2
    pub regional_narration: Option<String>,                 // L4 narration; V1+30d: None; V2: cached prose
    pub prompt_template_version: u32,                       // L4 cache invalidator
    pub generation_metadata: GenerationMetadata,            // generation_started_at, generation_completed_at, modificator_durations
    pub last_state_change_fiction_time: FictionTime,        // last Forge edit or LLM augmentation
}

pub struct ZoneRuntime {
    pub zone_id: ZoneId,                                    // matches ZoneSpec.zone_id from template
    pub center_position: (u32, u32),                        // tile coords (final position after force-directed converge)
    pub assigned_tiles: TileMask,                           // bitmask of which tiles belong to this zone (vertex-tiling-assigned)
    pub terrain_type: TerrainKind,                          // post-TerrainPainter
    pub biome_set: BiomeSelection,                          // chosen at runtime per template rules
    pub free_paths: TileMask,                               // post-fractalize core path skeleton
    pub guard_positions: Vec<TileCoord>,                    // where monster-guards stand for Threshold passages
    pub treasure_summary: TreasureSummary,                  // count + total_value per tier (post-TreasurePlacer)
}

pub enum TerrainKind {                                      // closed enum V1+30d (10 variants); stored u8 1-10
    Grass = 1,
    Forest = 2,
    Mountain = 3,
    Water = 4,
    Sand = 5,
    Snow = 6,
    Swamp = 7,
    Road = 8,                                               // overlay; auto-tile transitions to underlying terrain
    Rough = 9,                                              // rocky / barren
    Subterranean = 10,                                      // V2+ reserved (underground)
}

pub struct GridSize { pub width: u32, pub height: u32 }

pub struct TileCoord { pub x: u32, pub y: u32 }

pub struct TileMask {                                       // efficient bitmask over grid; ~32KB for 256×256
    pub width: u32,                                         // grid width (denormalized for self-contained mask)
    pub height: u32,
    pub bits: Vec<u64>,                                     // packed bits row-major
}

pub enum TilemapObjectKind {                                // closed enum V1+30d (7 variants)
    Treasure { tier_index: u8, value: u32 },                // visible loot pile
    MonsterLair { strength: u32 },                          // encounter trigger
    Landmark { canon_ref: Option<BookCanonRef> },           // visual + lore (waterfall, statue, ruin)
    Mine { resource_kind: ResourceKind },                   // V2 RES_001 integration
    Town { faction_id: FactionId, canon_ref: Option<BookCanonRef> },  // V2 — TownPlacer integration
    Monolith { pair_id: MonolithPairId },                   // teleport pair (Portal-kind passage)
    Decoration { kind: DecorationKind },                    // pure visual (trees, rocks, flowers); no aggregate
}

pub struct TilemapObjectPlacement {
    pub object_id: TilemapObjectId,                         // distinct from EntityId
    pub kind: TilemapObjectKind,
    pub position: TileCoord,
    pub guard_position: Option<TileCoord>,                  // if guarded — separate tile adjacent
    pub interaction_kind: ObjectInteractionKind,            // None / Examine / Enter / Combat
    pub blocked_tiles: TileMask,                            // tiles blocked by this object's footprint
}

pub struct RoadSegment {
    pub waypoints: Vec<TileCoord>,                          // polyline (auto-tile transitions applied at render)
    pub road_kind: RoadKind,                                // Highway (cobblestone primary) / DirtPath (secondary)
    pub speed_modifier: f32,                                // V2+ TVL_001 consumer
}

pub enum RoadKind { Highway, DirtPath }                     // V1+30d 2 variants; V2 adds Trade / Smuggler / Holy

pub struct RiverSegment {
    pub waypoints: Vec<TileCoord>,
    pub width: u32,                                         // 1-3 tiles
    pub crossable_at: Vec<TileCoord>,                       // bridge or ford points
}

pub enum GenerationSource {
    EngineGenerated,                                        // V1+30d default; L1+L2 only; deterministic
    LlmAugmented {                                          // V2 active
        model: String,
        attempts: u32,
        generated_at_fiction_time: FictionTime,
    },
}

pub struct GenerationMetadata {
    pub generation_started_at: WallClockTime,
    pub generation_completed_at: Option<WallClockTime>,
    pub modificator_durations: HashMap<String, std::time::Duration>,  // per-modificator timing
    pub iteration_count: u32,                               // force-directed convergence iterations
}
```

**Storage estimate per `tilemap_view`:**
- Header + zones: ~5KB (per-zone metadata × ~10 zones average)
- `terrain_layer` 256×256: 64KB (1 byte per tile) — Postgres `bytea`
- `object_placements`: ~10KB (≤ 200 objects × 50 bytes average)
- `road_segments` + `river_segments`: ~5KB
- Total: ~85KB per tilemap. Continent + 4 country + 16 district + 64 town ≈ 85 tilemaps × 85KB ≈ 7MB per typical reality. Acceptable.

### 3.2 `tilemap_template` (T2 / Reality scope) — SECONDARY

Author-declared template document. Multiple templates per reality (e.g., one per ChannelTier, or per genre subzone). Referenced by `tilemap_view.template_id`.

```rust
#[derive(Aggregate)]
#[dp(type_name = "tilemap_template", tier = "T2", scope = "reality")]
pub struct TilemapTemplate {
    pub template_id: TilemapTemplateId,                     // primary key (per-reality)
    pub name: String,                                       // author-supplied, e.g. "Wuxia Continent V1"
    pub description: String,                                // freeform
    pub applicable_tiers: BTreeSet<ChannelTier>,            // which tiers this template applies to
    pub default_grid_size: GridSize,                        // when applied
    pub zones: HashMap<ZoneId, ZoneSpec>,                   // zone-by-zone specs
    pub connections: Vec<ZoneEdgeSpec>,                     // edges between zones
    pub biome_selection_rules: BiomeSelectionRules,         // author-tunable obstacle-set selection; engine default = sensible mix
    pub allowed_water_content: BTreeSet<WaterContent>,      // None | Normal | Islands
    pub banned_terrain_kinds: BTreeSet<TerrainKind>,        // global ban for this template
    pub banned_monsters: BTreeSet<FactionId>,               // template-wide monster ban
    pub banned_artifacts: BTreeSet<ArtifactId>,             // V2 — RES_001 integration
    pub schema_version: u32,                                // for V1+30d additive-only evolution per TMP-A8
    pub last_change_fiction_time: FictionTime,
}

// Full schema in TMP_004 §2 — too long to inline here
```

---

## §3.5 Cross-aggregate consistency rules

TMP_001 introduces 4 cross-aggregate consistency rules `TMP-C1..C4` (mapped to global C-rule registry in `_boundaries/03_validator_pipeline_slots.md`):

| Rule | Description |
|---|---|
| **TMP-C1** | `tilemap_view.template_id` MUST reference a `tilemap_template` in the same reality (cross-aggregate FK). |
| **TMP-C2** | `tilemap_view.child_cell_anchors` keys MUST be children of `tilemap_view.channel_id` in DP channel hierarchy (no orphans). |
| **TMP-C3** | `tilemap_view.zones[].zone_id` MUST be a subset of `tilemap_template.zones` keys (no zones in runtime that weren't templated). |
| **TMP-C4** | `tilemap_view.object_placements[].position` MUST be within `tilemap_view.grid_size` bounds (no off-grid objects). |

---

## §4 4-layer composition architecture

Mirrors CSC_001 v3→v4 pattern. Per TMP-A2.

| Layer | Owner | Output | Cost | V-tier active |
|---|---|---|---|---|
| **L1 — Hand-authored skeleton** | TilemapTemplate (author Forge edits) | `zones: HashMap<ZoneId, ZoneSpec>` + `connections: Vec<ZoneEdgeSpec>` | None (one-time author cost) | V1+30d |
| **L2 — Procedural terrain + objects** | Engine code (deterministic from `seed`) | `terrain_layer` + `object_placements` + `road_segments` + `river_segments` | None (deterministic compute) | V1+30d |
| **L3 — LLM zone classifier** | LLM (zone-summary input → entity-zone assignment output) | Refines `object_placements[].position` (LLM picks which zone an entity goes to; engine still picks the tile) | ~3K tokens per tilemap | V2 |
| **L4 — LLM regional narration** | LLM (free-form prose per zone) | `regional_narration: String` — cached per (channel_id, season, structural_state) | ~1K tokens per zone × ~10 zones per tilemap = ~10K tokens; **cached** so amortizes to ~0 over time | V2 |

Total V2 LLM cost per tilemap composition: ~4-5K tokens initial + ~10K narration (cached). After cache warm-up, ~0 ongoing cost. See TMP_008 §5 for cost model details.

**Key lesson from CSC_001 v3→v4** that informs TMP_001:
- LLM is **categorical classifier**, NOT spatial coordinate generator. LLM picks "this monster goes in forest_west zone", not "monster goes at tile (47, 89)". Engine picks the tile. This bounds LLM context regardless of grid size — 64×64 vs 256×256 doesn't change LLM cost.
- 3-retry feedback loop on validation failure. Canonical-default fallback always succeeds (engine deterministic algorithm).

---

## §5 Tile state machine

Standard procedural-level-generation state model. The 4-variant `TileState` enum encodes pipeline progress per tile.

```
                           (Open means "can fit object here")
       ┌──────────────────────────────────────────────────────────┐
       ▼                                                          │
   ┌────────┐  init    ┌──────────┐  place obj  ┌──────────┐  ╲╲  │
   │Walkable│ ───────► │   Open   │ ──────────► │ Occupied │   ╲╲ │
   │ (path) │ ◄─────── │ (empty)  │             │(objstd)  │    ╲╲│
   └────────┘ fractalize└──────────┘             └──────────┘     │
       ▲                  │                                       │
       │                  │ obstacle fill                         │
       │                  ▼                                       │
       │           ┌──────────┐                                   │
       │           │ Obstacle │ ──────────────────────────────────┘
       │           │ (blocked)│   (Obstacle can transition to Occupied if
       └───────────┴──────────┘    a guard tile is placed there)
         after fractalize
```

| State | Meaning | Pipeline phase that introduces it |
|---|---|---|
| **Walkable** | Passable; part of zone's free-path skeleton; cannot host objects (would block paths). | Fractalize (TMP_002 §5) |
| **Open** | Passable; can host objects. Modificator candidate area. | Zone assignment (TMP_002 §3.2) — initial state for all assigned tiles before fractalize |
| **Obstacle** | Impassable barrier. | ObstaclePlacer (TMP_005 §4) |
| **Occupied** | Object placed on this tile (object_placement). Treated as Obstacle for pathing but distinguished for object queries. | TreasurePlacer + ObjectManager + ConnectionsPlacer guards |

**Invariants:**
- Every tile in `tilemap_view.zones[].assigned_tiles` is exactly one of {Walkable, Open, Obstacle, Occupied} at end of pipeline
- `Walkable` tiles form a connected subgraph within each zone (post-fractalize)
- `Walkable` tiles + accessible `Occupied` tiles together form the player-walkable area
- Cross-zone passage: `Walkable` tile in zone A adjacent to `Walkable` tile in zone B → unguarded direct connection. Guarded connection: an `Occupied` guard-tile sits between them.

`TileState` is **internal** to the generation pipeline — NOT stored in `tilemap_view` directly (would be redundant with `assigned_tiles` + `terrain_layer` + `object_placements`). Reconstructible on demand for downstream pathfinding queries.

---

## §6 Determinism + seeding

Per TMP-A4. Aligned with TDIL-A9 replay-determinism free V1.

Seed derivation (Blake3):
```
seed = blake3(
  reality_id.to_bytes() ||
  channel_id.to_bytes() ||
  template_id.to_bytes() ||
  seed_offset.to_le_bytes()
).first_u64()
```

- `seed_offset` defaults to 0; incremented on `Forge:RegenTilemap { mode: FullRebootstrap }` (new seed → new generation)
- `CosmeticOnly` re-roll preserves `seed` but re-rolls biome obstacle-set selection only (seed-derived sub-RNG) — keeps zone graph + tile geometry stable, just re-skins
- All generation RNGs derived deterministically from `seed` via ChaCha8Rng (seeded by Blake3-chained sub-seeds). Choice of ChaCha8 is a standard cryptographic-quality RNG selection.
- LLM augmentation (L3+L4) is V2 NON-deterministic — but cached outputs ARE deterministic in replay (replay reads cache, doesn't re-call LLM). Same pattern as CSC_001 v4 LLM cache.

**Replay-determinism contract:**
- Given `(reality_id, channel_id, template_id, seed_offset)` + same `tilemap_template` schema version, generation produces identical `tilemap_view` state. Tested via deterministic-replay test harness at TDIL-A9.
- LLM cache miss in replay → fall back to canonical-default L3 output (no LLM call); narration remains None until cache populated by live play.

---

## §7 MAP_001 position reconciliation

Per TMP-A6. MAP_001 is **canonical** source of truth for cell + town + non-cell-channel positions; TMP_001 is **derived** render layer.

Mechanism:
- MAP_001 stores per-channel `(x, y)` in normalized 0..1000 within parent viewport (MAP-3)
- TMP_001 derives `tile_coord` per child:
  ```
  tile_coord.x = (map_pos.x as u32 * grid_size.width) / 1000
  tile_coord.y = (map_pos.y as u32 * grid_size.height) / 1000
  ```
- Child cells / towns appear as `TilemapObjectPlacement` of kind `TilemapObjectKind::Town` or as cell-anchor markers (V1+30d: cell appears as 1×1 tile marker; click → drill into CSC_001)
- Author edits MAP_001 position via Forge:EditMapLayout → cascade emits EVT-T3 Derived on `map_layout`
- TMP_001 subscribes to `map_layout` deltas via DP-Ch24 channel publish/subscribe; on delta, re-derives `child_cell_anchors`. NOT a full regenerate — only the anchor map updates.

**Subscribe contract:**
- TMP modificator pipeline produces `tilemap_view` once at bootstrap; subsequent MAP_001 position edits trigger a partial update (just `child_cell_anchors` map). Terrain/objects/roads unchanged.
- If author wants full re-generation after MAP_001 edit (e.g., re-route roads to new town positions): Forge:RegenTilemap with `mode: CosmeticOnly` does road + biome re-roll; `mode: FullRebootstrap` does full pipeline re-run from scratch.

---

## §8 Cell-tier integration

Per TMP-A1. **Cell tier has NO `tilemap_view`.** CSC_001 (16×16 interior) is authoritative for cell rendering.

Cells appear ON the parent-tier tilemap as either:
- **Town tier cells:** rendered as `TilemapObjectKind::Town` with `Faction` + `canon_ref` — click → drill into the cell's CSC_001 view
- **Wilderness cells:** rendered as `TilemapObjectKind::Landmark` with `canon_ref` — click → drill into CSC_001 (might be a forest clearing, mountain pass, etc.)
- **Special cells:** TimePortal / DilationChamber — V2+ via MAP-D9 + TDIL-D20

Position on parent tilemap derived from MAP_001 per §7.

---

## §9 RealityManifest extension + `tilemap.*` RejectReason namespace

### 9.1 RealityManifest extension (OPTIONAL V1+30d)

Two fields, both engine-defaulted:

```rust
pub struct RealityManifest {
    // ... existing fields ...

    pub tilemap_templates: Option<HashMap<ChannelTier, TilemapTemplateRef>>,
    // V1+30d: None (engine uses `tilemap_defaults.default_template_per_tier`)
    // If Some: per-tier template selection. Falls back to defaults for any tier not specified.

    pub tilemap_defaults: Option<TilemapDefaults>,
    // V1+30d: None (engine uses hardcoded sensible defaults)
    // If Some: author overrides grid sizes, default templates, LLM enablement, etc.
}

pub struct TilemapDefaults {
    pub grid_size_per_tier: HashMap<ChannelTier, GridSize>,
    pub default_template_per_tier: HashMap<ChannelTier, TilemapTemplateRef>,
    pub default_water_content: WaterContent,                // None | Normal | Islands
    pub default_monster_strength: MonsterStrength,          // Weak | Normal | Strong
    pub llm_enabled: bool,                                  // V1+30d default false; V2 default true
    pub single_thread: bool,                                // V1+30d default false (parallel); for deterministic-debug builds
    pub skip_tier: BTreeSet<ChannelTier>,                   // tiers to NOT generate tilemaps for; UI falls back to MAP_001 graph view
}
```

### 9.2 `tilemap.*` RejectReason namespace (16 V1+30d + 6 V1+)

V1+30d active rule_ids:

| rule_id | When emitted |
|---|---|
| `tilemap.template_not_found` | `tilemap_template_id` ref does not resolve in reality |
| `tilemap.template_tier_mismatch` | Author applies template to a tier outside `applicable_tiers` |
| `tilemap.zone_id_collision` | Two zones in same template share `zone_id` |
| `tilemap.connection_zone_not_found` | `ZoneEdgeSpec.zone_a` or `zone_b` doesn't exist in zones map |
| `tilemap.connection_self_loop` | `zone_a == zone_b` for non-Portal-kind passage (self-connection only allowed for Portal kind, which materializes as monolith pair) |
| `tilemap.inherit_cycle` | `inherit_treasure_from` / `inherit_terrain_from` / etc. create a cycle in inheritance graph |
| `tilemap.inherit_not_found` | Inheritance ref doesn't resolve |
| `tilemap.template_schema_version_mismatch` | RealityManifest references a `template_id` whose `schema_version` post-edit drifted beyond V1+30d additive bounds |
| `tilemap.grid_size_out_of_bounds` | Author override exceeds engine limits (V1+30d max 1024×1024 per tier) |
| `tilemap.generation_failed` | Zone-placement force-directed convergence failed after `max_iterations` (rare; configurable) |
| `tilemap.generation_timeout` | Generation exceeded `tilemap_defaults.generation_timeout_seconds` (V1+30d default 30s) |
| `tilemap.empty_zone` | Vertex-tiling assignment produced empty zone — likely template misconfiguration (zone size + grid size mismatch) |
| `tilemap.zone_not_connected` | Final pipeline state has disconnected zones (post-ConnectionsPlacer; should not happen but defended) |
| `tilemap.object_off_grid` | TilemapObjectPlacement.position outside grid bounds (TMP-C4 violation) |
| `tilemap.regen_mode_incompatible` | Forge:RegenTilemap CosmeticOnly attempted on a tilemap whose template changed since last generation (must use FullRebootstrap) |
| `tilemap.llm_layer_disabled` | V2 LLM augmentation requested but `tilemap_defaults.llm_enabled == false` |

V1+ reservations:
| rule_id | When activates |
|---|---|
| `tilemap.paint_override_forbidden_in_v1plus30d` | V3 manual paint UX gated to V3 (TMP-D2) |
| `tilemap.sprite_atlas_not_uploaded` | V2 sprite pipeline (TMP-D6) |
| `tilemap.travel_encounter_blocked_v1plus30d` | V2 tile-traversal encounter (TMP-D4) |
| `tilemap.movement_modifier_disabled_v1plus30d` | V2 terrain speed (TMP-D5) |
| `tilemap.combat_overlay_disabled` | V2+ tactical combat (TMP-D7) |
| `tilemap.fog_of_war_disabled` | V2+ per-PC discovery (TMP-D3) |

---

## §10 Storage + grid sizing

| Tier | V1+30d default grid size | Storage `terrain_layer` | Total per `tilemap_view` |
|---|---|---|---|
| Continent | 256×256 = 65,536 tiles | 64KB | ~85KB |
| Country | 192×192 = 36,864 tiles | 36KB | ~50KB |
| District | 128×128 = 16,384 tiles | 16KB | ~25KB |
| Town | 64×64 = 4,096 tiles | 4KB | ~10KB |

Typical reality (1 continent + 4 country + 16 district + 64 town):
- 1 × 85KB + 4 × 50KB + 16 × 25KB + 64 × 10KB ≈ 1325KB ≈ 1.3MB per reality of tilemap data

PostgreSQL `bytea` for `terrain_layer`; JSON for other fields. V2+ consideration: if storage becomes a problem, drop `terrain_layer` and regen-on-demand from seed (some procedural games take this approach — no persisted tile grid, only template + seed).

V1+30d choice: **persist** `terrain_layer` — author Forge edits via TMP-D2 V3 paint UX (deferred but schema-prepared) require persisted grid. Cost is small (~1.3MB per reality).

---

## §11 Bootstrap sequence

When a reality is created (RealityManifest bootstrap), per non-cell channel that has a `tilemap_template` reference (or falls back to default):

```
1. Engine reads RealityManifest.tilemap_templates[tier] → resolves TilemapTemplateRef → loads tilemap_template aggregate
2. Engine derives seed = blake3(reality_id || channel_id || template_id || 0)
3. Engine instantiates tilemap_view aggregate with header (channel_id, tier, grid_size, template_id, seed)
4. Engine emits EVT-T4 System TilemapBorn { channel_id, tier, grid_size, template_id, seed }
5. Engine runs the modificator pipeline (TMP_003):
   5a. Zone placement (force-directed convergence) → emits EVT-T4 ZonesPlaced
   5b. Zone assignment (vertex-based irregular tiling assigns tiles to zones)
   5c. Fractalize (per zone, in parallel; produces free_paths + areaOpen)
   5d. Modificator pipeline:
       - TerrainPainter (per zone) → terrain_layer
       - ConnectionsPlacer (per zone, with cross-zone locking) → guards + roads' anchor tiles
       - TreasurePlacer (per zone) → object_placements
       - RoadPlacer (per zone) → road_segments
       - RiverPlacer (per zone) → river_segments
       - ObstaclePlacer (per zone) → terrain_layer obstacle marks + object_placements for large decorations
6. Engine writes final tilemap_view state to DP via DP-K5 write primitive
7. Engine emits EVT-T3 Derived (aggregate_type=tilemap_view, kind=GenerationCompleted)
8. (V2 only) Engine emits EVT-T6 Proposal for L3 zone classifier → LLM call → L3 output applied
9. (V2 only) Engine emits EVT-T6 Proposal for L4 narration → LLM call → regional_narration field populated (cached)
```

Cell-tier channels are skipped (CSC_001 owns cell rendering).

**Performance budget V1+30d (engine-only, no LLM):**
- Continent tilemap 256×256: target < 5 seconds wall-clock (parallel modificators)
- Country tilemap 192×192: target < 3 seconds
- District tilemap 128×128: target < 1 second
- Town tilemap 64×64: target < 500ms

Typical bootstrap budget for full reality (1 continent + 4 country + 16 district + 64 town): ~20-30 seconds. Long-running; show progress bar in UI. Defer to user-action ("Generate world" button at reality creation; can be re-rolled later).

---

## §12 Open questions

| ID | Question | Default proposal | Need user decision? |
|---|---|---|---|
| **TMP-Q1** | Storage strategy: persist `terrain_layer` or regenerate from seed? | Persist V1+30d (~1.3MB per reality is cheap; enables V3 paint UX schema-prepared) | OK as default |
| **TMP-Q2** | Should `tilemap_view` exist for District + Town tiers, or only Continent + Country? | All 4 non-cell tiers V1+30d (with skip_tier engine config for opt-out) | OK as default |
| **TMP-Q3** | LLM enablement default V2 | V2 default ON; V1+30d ships with LLM off (cost validation) | YES at V2 launch |
| **TMP-Q4** | FE rendering engine — Phaser vs Pixi vs custom canvas? | Phaser (community + React wrapper; SPIKE_03 recommendation) | YES at impl |
| **TMP-Q5** | Force-directed convergence: needs a wall-clock budget (vs annealing-until-stable). | Cap at 1000 iterations OR 5 seconds; whichever first. Emit `tilemap.generation_timeout` if cap hit. | OK as default |
| **TMP-Q6** | Should LLM L3 zone classifier accept author-narrative-hints from tilemap_template, or use only zone summaries? | Both: accept optional `narrative_hint: Option<String>` per zone; merge with engine-computed terrain summary in prompt | OK as default |
| **TMP-Q7** | V2+: Should cells (cell tier) appear on parent tilemap as 1×1 marker or as multi-tile region matching CSC_001 16×16 footprint? | 1×1 marker V1+30d (simpler, no scale conflict); V2+ multi-tile when zooming (TMP-D11 reserve) | OK as default |
| **TMP-Q8** | Multi-PC parallel generation: if 2 players create realities concurrently, does the engine process them serially or parallel? | Parallel (tilemap-service is stateless; uses per-(reality, channel) lock) | OK as default |

---

## §13 Axioms (TMP-A1..A10)

| Axiom | Statement |
|---|---|
| **TMP-A1** | Cell tier has no `tilemap_view`; CSC_001 16×16 interior is authoritative for cell rendering. Cells appear as objects on parent-tier tilemap. |
| **TMP-A2** | TMP follows 4-layer composition mirror of CSC_001 v3→v4: L1 hand-authored + L2 procedural + L3 LLM classifier + L4 LLM narration. L1+L2 V1+30d active; L3+L4 V2. |
| **TMP-A3** | Zone-graph paradigm with 5-variant `PassageKind` (Threshold / Open / Hint / Adversarial / Portal) — LoreWeave-distinct naming for functional categories observed across the genre prior art (§1.1). |
| **TMP-A4** | Generation is deterministic: seed = Blake3(reality_id || channel_id || template_id || seed_offset). Same inputs → same `tilemap_view`. Replay-deterministic per TDIL-A9. |
| **TMP-A5** | Tile state machine: every tile is exactly one of {Walkable, Open, Obstacle, Occupied} at end of pipeline. Walkable tiles form connected subgraph per zone. (Standard pathfinding state model.) |
| **TMP-A6** | MAP_001 is canonical source of truth for child-channel positions; TMP_001 derives `tile_coord` via linear scale. Author edits MAP_001 → TMP subscribes → re-derives anchors. |
| **TMP-A7** | "Never seal a gap" connectivity invariant: every object placement preserves zone path-connectivity. Modificators check before commit; reject placement that would disconnect Walkable regions. Standard procedural-content-generation axiom. |
| **TMP-A8** | Schema-additive evolution V1+30d → V2: new fields are added, never removed or repurposed. Schema-breaking changes require new `template_kind`. Aligned with foundation I14. |
| **TMP-A9** | LLM never sees raw tiles; LLM operates on zone summaries. LLM cost is independent of grid size. Bounds V2+ LLM cost. |
| **TMP-A10** | Modificator pipeline runs with explicit dependency graph; parallel execution within constraints. Single-thread mode available for deterministic-debug. (Standard visitor/strategy + topological-sort pattern.) |

---

## §14 Cross-feature integration

| Feature | Integration |
|---|---|
| **MAP_001** | TMP_001 derives child-cell anchor positions from MAP_001 author-positioned (x, y) — subscribe pattern (§7). MAP_001 stays canonical; TMP_001 stays derived. |
| **CSC_001** | Cell tier uses CSC_001; non-cell tiers use TMP_001. Cells appear as objects on parent tilemap; click cell → drill into CSC_001 16×16 interior. |
| **PF_001** | Non-cell-tier `place` rows are V1+ (PF_001 V1 restricts to cell only); TMP_001 V1+30d coexists by reading from `tilemap_template` directly. V1+ PF_001 reopen for non-cell `place` rows can co-exist with TMP_001. |
| **AIT_001** | TMP_008 V2 L3+L4 reuses AIT-A4 hybrid 2-stage pattern: Stage 1 (engine cheap) always runs; Stage 2 (LLM lazy) opt-in. |
| **TDIL_001** | TMP-A4 seed determinism satisfies TDIL-A9 replay-free V1. Cross-realm time dilation doesn't affect tilemap (purely spatial). |
| **PL_001** | §16 RealityManifest extends with `tilemap_templates` + `tilemap_defaults`. PL_001 §13 Travel V2+ consumes terrain speed modifier (TMP-D5) for non-cell-tier travel cost calc. |
| **PCS_001** | V2+ per-PC `discovered_tiles` fog-of-war (TMP-D3) consumes PCS_001 vision range + PC position. |
| **RES_001** | V2 mines on tilemap (TMP-D10) integrate with `resource_inventory` + cell-production. |
| **NPC_001** | NPC routing on tilemap V2+ consumes `tilemap_view.road_segments` + free-path connectivity. |
| **WA_003 Forge** | 3 new AdminAction sub-shapes: `Forge:RegenTilemap` + `Forge:EditTemplate` + `Forge:OverridePlacement` (latter V3 active; V1+30d schema-reserved). |
| **05_llm_safety** | V2 L3+L4 LLM calls go through 3-intent classifier + injection defense + World Oracle. |
| **06_data_plane** | Two new T2 aggregates (`tilemap_view` per channel; `tilemap_template` per reality). Standard DP-K1..K12 access. Subscribe channel for MAP_001 deltas (DP-Ch24). |
| **07_event_model** | 2 EVT-T4 sub-types + 2 EVT-T3 aggregate types + 3 EVT-T8 sub-shapes (active V1+30d) + 2 V2 EVT-T5/T6 reservations. See §2.5. |

---

## §15 Acceptance criteria (placeholder — closure-pass walk pending)

10 V1+30d-testable scenarios `AC-TMP-1..10` to be walked at CANDIDATE-LOCK promotion. Sketches:

| ID | Scenario |
|---|---|
| AC-TMP-1 | Reality bootstrap with default templates: every non-cell channel gets a `tilemap_view`; cells skipped. Verify `TilemapBorn` events emitted for all non-cell channels. |
| AC-TMP-2 | Re-bootstrap with same seed: produces identical `tilemap_view` state (TMP-A4 replay determinism). |
| AC-TMP-3 | Author edits MAP_001 position via Forge:EditMapLayout → TMP_001 subscribes → `child_cell_anchors` updates without full regen (TMP-A6 derived). |
| AC-TMP-4 | Forge:RegenTilemap CosmeticOnly: same zones + same connections + new biome obstacle-set; objects + roads preserved. |
| AC-TMP-5 | Forge:RegenTilemap FullRebootstrap with new seed_offset: completely new geometry; emits new `TilemapBorn` + `ZonesPlaced`. |
| AC-TMP-6 | Template with `inherit_treasure_from` / `inherit_terrain_from` / etc. cycle: rejected with `tilemap.inherit_cycle` at template save. |
| AC-TMP-7 | Template applied to wrong tier: rejected with `tilemap.template_tier_mismatch`. |
| AC-TMP-8 | Generation timeout (force-directed cannot converge in 5s): emit `tilemap.generation_timeout`; UI falls back to MAP_001 graph view for this channel. |
| AC-TMP-9 | "Never seal a gap" test: place obstacle that would disconnect Walkable zone → modificator rejects placement; tries another spot. |
| AC-TMP-10 | V2 LLM augmentation off (tilemap_defaults.llm_enabled = false): L3+L4 layers skipped; `generation_source: EngineGenerated`; `regional_narration: None`. |

Full criteria walk + Phase 3 review pending.

---

## §16 Deferrals (TMP-D1..D12)

| ID | Item | V-tier |
|---|---|---|
| **TMP-D1** | V3 RMG wizard (author parameters → seed → full reality bootstrap) | V3 |
| **TMP-D2** | V3 manual paint UX (Forge:PaintTile per-tile editor) | V3 |
| **TMP-D3** | V2+ per-PC discovered_tiles fog-of-war (consumes MAP-D10 + PCS_001) | V2+ |
| **TMP-D4** | V2 tile-traversal travel encounters | V2 |
| **TMP-D5** | V2 terrain movement modifiers (speed_modifier per TerrainKind) | V2 |
| **TMP-D6** | V2 sprite atlas pipeline (TMP_009 — mirror of MAP_002) | V2 |
| **TMP-D7** | V2+ tactical-combat tilemap derivative (consumes CSC-D8 + battlefield mode) | V2+ |
| **TMP-D8** | V2+ procedural settlement layouts (TMP_010 — town-tier zoom into building grid) | V2+ |
| **TMP-D9** | V3 multi-level verticality (PocketDimension / TimePortal / underground) | V3 |
| **TMP-D10** | V2 mines + dwellings on tilemap (RES_001 integration) | V2 |
| **TMP-D11** | V2+ multi-tile cell rendering on parent tilemap (TMP-Q7 deferred resolution) | V2+ |
| **TMP-D12** | V2+ multiplayer ZoneRole variants (AllyHome / RivalHome) for competitive scenarios | V2+ |

---

## §17 Prior Art

### Academic foundations

- **Fruchterman, T. M. J. & Reingold, E. M. (1991).** "Graph Drawing by Force-Directed Placement." *Software—Practice and Experience* 21(11), 1129–1164. — Basis for zone placement algorithm (TMP_002 §3).
- **Penrose, R. (1974).** "Role of aesthetics in pure and applied mathematical research." *Bulletin of the IMA* 10, 266–271. — Aperiodic tiling used for irregular zone shapes (TMP_002 §4).
- **Kahn, A. B. (1962).** "Topological sorting of large networks." *Communications of the ACM* 5(11), 558–562. — Modificator pipeline ordering (TMP_003 §4).
- **Tarjan, R. E. (1976).** "Edge-disjoint spanning trees and depth-first search." *Acta Informatica* 6, 171–185. — Connected-components for connectivity invariant (TMP_006 §4).
- **Dijkstra, E. W. (1965).** "Cooperating sequential processes." Technical Report EWD-123. — Dining philosophers pattern for cross-zone locking (TMP_007 §4).
- **Hart, P. E., Nilsson, N. J. & Raphael, B. (1968).** "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Trans. on Systems Science and Cybernetics* 4(2), 100–107. — A* pathfinding for road generation (TMP_003 §3.4).
- **Gamma, E., Helm, R., Johnson, R. & Vlissides, J. (1994).** *Design Patterns: Elements of Reusable Object-Oriented Software.* Addison-Wesley. — Strategy + Visitor patterns underlying modificator design.

### Genre prior art

- **Heroes of Might and Magic III** (1999). New World Computing. Random Map Generator UX + zone-graph paradigm + tiered treasure + biome obstacles + monster-guarded passages. Genre-defining for this shape.
- **VCMI** (2007+, GPL v2 or later). Open-source reimplementation of HoMM3 engine, including a well-documented RMG (`lib/rmg/`). Surveyed as one mature open-source implementation of the genre patterns. See <https://github.com/vcmi/vcmi/tree/develop/lib/rmg> and developer documentation at <https://github.com/vcmi/vcmi/blob/develop/docs/developers/RMG_Description.md>. *Note: TMP_001..TMP_008 documents the LoreWeave design independently; vcmi is one of several implementations cited for the genre patterns documented here.*
- **Battle for Wesnoth** (2003+, GPL v2+). Open-source tile-based fantasy TBS with author-extensible map generators.
- **Civilization V / VI** (2010 / 2016). Firaxis Games. Climate-band procedural generation; resource-placement balancing.
- **Dwarf Fortress** (2002+). Bay 12 Games. Multi-pass deterministic-seed world generation (terrain → erosion → biomes → civilizations → history).
- **Caves of Qud** (2015+). Freehold Games. Procedural biome composition with hand-authored set pieces interleaved.
- **Europa Universalis IV / Crusader Kings III**. Paradox Interactive. Large-scale region graphs at grand-strategy density.

### LoreWeave-internal cross-references

- [CSC_001 Cell Scene Composition](../00_cell_scene/CSC_001_cell_scene_composition.md) — v3→v4 4-layer architectural pattern (mirrored at TMP §4).
- [MAP_001 Map Foundation](../00_map/MAP_001_map_foundation.md) — author-positioned logical graph (canonical source of truth at TMP §7).
- [AIT_001 AI Tier](../16_ai_tier/AIT_001_ai_tier_foundation.md) — AIT-A4 hybrid 2-stage pattern (reused at TMP_008 L3 + L4).
- [TDIL_001 Time Dilation](../17_time_dilation/TDIL_001_time_dilation_foundation.md) — TDIL-A9 replay-determinism (satisfied by TMP-A4).
- [SPIKE_03 Tilemap World View](../_spikes/SPIKE_03_tilemap_world_view.md) — original exploratory spike from which TMP folder graduated.
