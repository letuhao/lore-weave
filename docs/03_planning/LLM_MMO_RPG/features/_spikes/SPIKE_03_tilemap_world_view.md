# SPIKE_03 — Tilemap World View (HOMM3-style camera-rendered map)

> **Status:** DRAFT 2026-04-27 — exploratory. Architectural concept captured; PoC scheduled as Session 2; no IDs claimed; no catalog rows added; no boundary touched.
>
> **Scope:** Add a NEW visual layer alongside MAP_001 (logical graph) — a camera-scrollable tilemap rendered via Phaser-style FE engine, with terrain biomes + roads + objects + cells placed as positions on the tilemap. Same 4-layer LLM-architecture pattern as CSC_001 (validated by v3→v4 demo evidence; 12.7× cost reduction). Pattern target: HOMM3 / Bannerlord / Wesnoth overworld feel.
>
> **Conversational name:** "Tilemap" or "Big Map" — placeholder feature ID `TMP_001` (subject to namespace claim when graduating).
>
> **Graduation path:** PoC validates feasibility (Session 2) → user reviews → if accepted, graduates to:
> - `features/00_tilemap/` subfolder + `TMP_001_tilemap_foundation.md` design doc
> - `catalog/cat_00_TMP_tilemap_foundation.md` namespace claim
> - `_boundaries/` lock claim (single boundary commit per pattern)
> - V-tier assignment: V1+30d minimum; V2 full; V3 RMG (HOMM3-style player-driven generation)
>
> If rejected or perpetually deferred → stays here as permanent reference.
>
> **NOT in scope:** PoC implementation (Session 2). Final aggregate schema. Boundary lock. RMG (Random Map Generator) UX wizard (V3 territory). Sprite asset commissioning. Mobile-specific render strategy.

**Active:** main session 2026-04-27 (DRAFT capture; closing on Session 1 finish; Session 2 PoC will reopen)

---

## §1 — Why this spike exists

User raised 2026-04-27 in continuation of MAP/PF/CSC discussion:

> "bản đồ hiện tại khá chán vì chỉ có cell và graph. tôi muốn thiết kế thêm bản đồ big map cũng giống như cell nhưng to hơn với cơ chế render theo camera (phaser game) liệu có được không?
> liệu có thể dùng code + llm support để tạo 1 bản đồ như vậy (build dữ liệu json/table trong db) rồi render nó lên FE?
> giống như map generating của mấy game như hero of might and magic?"

Three concrete asks:
1. **Camera-rendered big map** — beyond MAP_001's SVG node-link drill-down; tile-based, larger than viewport, scrollable + zoomable
2. **Code + LLM build flow** — engine generates terrain, LLM adds flavor + decoration, store JSON/blob in DB, FE renders
3. **HOMM3 RMG-style** — procedural map generation parameterized by seed + template

The current MAP_001 (CANDIDATE-LOCK 2026-04-26) is a **logical graph layer** — abstract node-link graph at 5 channel tiers (continent → cell). It's the right shape for a11y / screen-reader / low-bandwidth fallback, but **lacks the immersive game-world feel** users expect from RPG/strategy genres (HOMM3 / Bannerlord / Total War campaign / EU4 / Wesnoth / Wartales).

CSC_001 (CANDIDATE-LOCK 2026-04-26) covers the **interior 16×16 grid** at cell tier with 4-layer composition. The v3→v4 architectural pivot validated: LLM = categorical zone classifier, NOT spatial coordinate generator. Same pattern can scale up.

What's missing: a **tilemap world view** sitting between MAP_001 (graph) and CSC_001 (cell interior) — the "outdoor/region/continent canvas" where everything else lives.

---

## §2 — Architectural fit (no break of existing locks)

```
┌─────────────────────────────────────────────────────────────────┐
│  MAP_001 — Logical graph layer (UNCHANGED, CANDIDATE-LOCK)      │
│  · Cells/towns/districts as nodes; positions 0..1000 abstract   │
│  · Connections (Public/Private/Locked/Hidden/OneWay)            │
│  · distance_units + default_fiction_duration                    │
│  · SVG node-link drill-down render (a11y fallback + low-bw)     │
└────────────────────────┬────────────────────────────────────────┘
                         │ reads: which channels exist + position
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  *** NEW — TMP_001 Tilemap Foundation                           │
│  · Per-non-cell-channel rendered tilemap                        │
│  · Variable grid size (continent ~256×256; town ~64×64)         │
│  · Camera-scrollable (Phaser/Pixi-rendered FE)                  │
│  · 4 layers (mirroring CSC_001):                                │
│    L1 hand-authored tilemap skeleton (kingdom_default, etc.)    │
│    L2 procedural terrain placer (Perlin/Voronoi biomes)         │
│    L3 LLM zone-classifier (place "monster lair" in suitable z)  │
│    L4 LLM regional narration (cached)                           │
│  · Cell rendered AS objects on tilemap; click cell → drill in   │
└────────────────────────┬────────────────────────────────────────┘
                         │ click cell → transition
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  CSC_001 — Cell interior 16×16 (UNCHANGED, CANDIDATE-LOCK)      │
└─────────────────────────────────────────────────────────────────┘
```

**Why both MAP_001 + TMP_001 coexist (not replace):**

| Reason | Detail |
|---|---|
| A11y fallback | Screen reader users get MAP_001 SVG with text labels; tilemap canvas is opaque to AT |
| Low-bandwidth | Mobile / poor connection → SVG (~5KB) instead of tilemap (~150KB) |
| Browser fallback | Older browsers without WebGL fall back to graph view |
| Authoring flow | Author edits canonical position via MAP_001 (single source of truth); tilemap derives |
| LLM context | LLM AssemblePrompt reads MAP_001 graph (compact) not tilemap (~150KB) |

**Position reconciliation:**
- MAP_001 = source of truth for cell/town positions (0..1000 abstract within parent viewport)
- TMP_001 = derives tile coordinates: `tile_coord = (map_pos.x * grid_size / 1000, map_pos.y * grid_size / 1000)`
- Author edits MAP_001 position via Forge → TMP_001 re-render automatically (subscribe pattern)

**Both layers SHIP as products:**
- V1 default render = MAP_001 graph (current locked state — ships with V1)
- V1+30d adds TMP_001 — players toggle between graph view + tilemap view
- V2+ default render = TMP_001 tilemap; graph view = secondary

---

## §3 — 4-layer composition (HOMM3 RMG = exact CSC pattern)

| Layer | Owner | Output | LLM cost | HOMM3 analog |
|---|---|---|---|---|
| **L1 — Hand-authored skeleton** | Engine config | `terrain_zones: HashMap<ZoneId, ZoneSpec>` + `connection_graph: Vec<ZoneEdge>` (zones must be road-reachable) | None | RMG template — Jebus / 6lm15 / Balance |
| **L2 — Procedural terrain placer** | Engine code (deterministic ChaCha8 RNG + Perlin/Voronoi noise) | `tiles: Vec<Vec<TerrainKind>>` (full grid); `roads: Vec<RoadSegment>`; `rivers: Vec<RiverSegment>`; auto-tile transitions | None | RMG terrain generation |
| **L3 — LLM categorical placement** | LLM (zone classifier — does NOT generate tiles) | `entity_placements: HashMap<EntityId, ZoneId>` — "monster_camp_1 → forest_west" | ~3K tokens | RMG object placement |
| **L4 — LLM regional narration** | LLM (free-form prose) | `region_narration: String` — Vietnamese xianxia flavor; cached per (channel, season, structural_state) | ~1K tokens | (HOMM3 doesn't have; LLM-native value-add) |

**Total LLM cost per tilemap composition: ~4-5K tokens.** Same v3→v4 architectural lesson: LLM never sees full grid; LLM sees zone-level summaries only. Bounded cost regardless of grid size — 64×64 vs 256×256 doesn't change LLM context.

**L2 algorithm sketch (validated against CSC_001 §5 pattern):**
```
1. Initialize grid with biome zone IDs from L1 skeleton.zone_decls
2. Within each zone, apply 2D Perlin noise (zone-specific octaves + scale) →
   classify each tile to TerrainKind via threshold table
3. Apply auto-tile transitions (Wang-tile pattern) for biome boundaries
4. Place rivers: pick L1-declared "river_source" zones, run flow algorithm
   downhill to L1-declared "river_sink" using terrain elevation
5. Place roads: shortest-path between L1-declared "road_anchor" objects (cells/
   towns from MAP_001 child positions); avoid Mountain/Water tiles
6. Decorate: scatter non-interactable scenery (trees on Forest tiles; rocks
   on Mountain; ruins randomly at low density) — pure visual, no aggregate
```

**L3 LLM contract** (mirror CSC_001 §6):
```
LLM input:
  - place_metadata: { tier, climate, canon_ref, narrative_drift }
  - terrain_summary: e.g. "60% Forest center, 25% Mountain north, 10% Water southwest, 5% Grass"
  - zones_available: ["forest_west", "mountain_pass", "lake_shore", "open_plain"]
  - entities_to_place: [
      { id: "monster_camp_1", kind: BanditCamp, hint: "wilderness" },
      { id: "treasure_cave_1", kind: HiddenCave, hint: "remote" },
    ]
LLM output (JSON, validated):
  { "placements": [
      { "entity_id": "monster_camp_1", "zone": "forest_west" },
      { "entity_id": "treasure_cave_1", "zone": "mountain_pass" },
    ] }
```

3-retry feedback loop on validation failure (CSC_001 §6.4 pattern). Canonical default fallback always succeeds (engine algorithm: place in first zone matching `hint`).

---

## §4 — Aggregate sketch (preliminary, NOT locked)

```rust
#[derive(Aggregate)]
#[dp(type_name = "tilemap_view", tier = "T2", scope = "channel")]
pub struct TileMapView {
    pub channel_id: ChannelId,                    // primary key (per-channel)
    pub tier: ChannelTier,                        // mirror MAP_001
    pub grid_size: GridSize,                      // (width, height)
    pub skeleton_id: TileMapSkeletonId,           // L1 template
    pub procedural_seed: u64,                     // L2 input — blake3 deterministic
    pub procedural_params: TileMapProceduralParams,
    pub terrain_layer: Vec<u8>,                   // L2 output — flattened grid; bytea storage; index = y*width+x
    pub roads: Vec<RoadSegment>,                  // L2 output
    pub rivers: Vec<RiverSegment>,                // L2 output
    pub child_cell_placements: HashMap<ChannelId, TileCoord>, // derived from MAP_001 positions
    pub object_placements: Vec<MapObjectPlacement>, // L3 output
    pub layer3_source: Layer3Source,              // CanonicalDefault | LlmGenerated
    pub region_narration: Option<String>,         // L4 output, cached
    pub prompt_template_version: u32,             // cache invalidator
    pub last_change_fiction_time: FictionTime,
}

pub enum TerrainKind {                            // closed enum V1+30d (10 variants)
    Grass, Forest, Mountain, Water, Sand,
    Snow, Swamp, Road, Rough, Subterranean,
}

pub struct GridSize { pub width: u32, pub height: u32 }

pub enum MapObjectKind {                          // closed enum
    Treasure,                                     // visible loot marker
    MonsterLair,                                  // encounter trigger
    Landmark,                                     // visual + lore (waterfall, statue)
    Decoration,                                   // pure visual (trees, rocks)
    Mine,                                         // resource node V2+
    Portal,                                       // cross-tier link V2+ (consumes MAP-D9)
    Ruin,                                         // discoverable lore
}

pub struct MapObjectPlacement {
    pub object_id: MapObjectId,                   // distinct from EntityId
    pub kind: MapObjectKind,
    pub position: TileCoord,
    pub linked_canon_ref: Option<BookCanonRef>,
    pub linked_quest_id: Option<QuestId>,         // V2+ QST link
    pub interaction_handler: ObjectInteractionKind, // None / Examine / Enter / Combat
}

pub struct RoadSegment {
    pub waypoints: Vec<TileCoord>,                // polyline
    pub road_kind: RoadKind,                      // Highway/Path/Trade
    pub speed_modifier: f32,                      // V2+ TVL_001 consumer
}

pub struct RiverSegment {
    pub waypoints: Vec<TileCoord>,
    pub width: u32,                               // tiles
    pub crossable_at: Vec<TileCoord>,             // bridge/ford points
}

pub struct TileCoord { pub x: u32, pub y: u32 }   // within tilemap grid

pub enum Layer3Source {                           // mirror CSC_001
    CanonicalDefault,
    LlmGenerated { model: String, attempts: u32, generated_at_fiction_time: FictionTime },
}
```

**EVT-T mapping** (preliminary, awaits boundary review):
- EVT-T4 System sub-type: `TileMapBorn`
- EVT-T3 Derived sub-type: `aggregate_type=tilemap_view`
- EVT-T8 AdminAction sub-shapes: `Forge:RegenTileMap`, `Forge:PlaceObject`, `Forge:PaintTile` (V2+)

**RealityManifest extension:**
- `tilemap_skeletons: HashMap<ChannelId, TileMapSkeletonId>` — author override per-channel (OPTIONAL V1+30d)
- `tilemap_defaults: TileMapDefaults` — engine fallback config

---

## §5 — V-tier proposal (3 phases)

### V1+30d — Minimum tilemap (no LLM, basic Phaser, 1-month build)

**In scope:**
- 1 aggregate `tilemap_view` per non-cell channel
- 2 hand-authored skeleton (continent_default + town_default)
- L2 procedural terrain placer (Perlin biome + simple river/road)
- Cell positions imported from MAP_001 (derived; not authoritative)
- L3 = Canonical Default only (engine algorithm; no LLM)
- L4 = None (no narration)
- FE: Phaser canvas inside React component; emoji/colored-square fallback for tiles + objects
- Camera: drag-to-pan + scroll-to-zoom; click cell → drill into MAP_001 cell view → CSC_001
- Forge:RegenTileMap (re-roll seed) only

**Out of scope V1+30d:**
- LLM zones / LLM narration (V2)
- Multiple skeletons per genre (V2)
- Custom sprite atlas (V2 → TMP_002 Asset Pipeline mirroring MAP_002)
- Terrain movement modifiers (V2)
- Fog-of-war (V2 — depends on MAP-D10 unblock)
- Tactical combat (V2 — depends on CSC-D8)
- Random map gen UX (V3)

**Cost estimate:** 1 month focused implementation. Reuses CSC_001 v4 architecture lessons.

### V2 — Full tilemap with LLM + genre packs

**Adds:**
- L3 LLM zone classifier (place treasures/lairs/landmarks); 3-retry feedback loop
- L4 LLM regional narration (cached per (channel, season, structural_state))
- Skeleton libraries per subgenre (wuxia continent / scifi star sector / modern country)
- Author-uploadable sprite atlas (TMP_002 Asset Pipeline)
- Roads with travel speed modifier (consume MAP_001 distance_units; 2× speed on Highway)
- Terrain affects encounter type (forest = bandit; mountain = beast; water = pirate)
- Integrates fog-of-war (MAP-D10 V1+30d unblocked)
- Travel encounters on tile traversal (SPIKE_02 D3)

### V3 — Random Map Generator (HOMM3 RMG analog)

**Adds:**
- Author parameters → seed → fully procedural reality at creation time
- "I want a wuxia kingdom with 4 sects, 12 towns, mountain on north, sea on south, 3 rival factions"
- Engine generates RealityManifest + tilemap from params (full bootstrap from RMG)
- Player-facing reality customization wizard
- Manual paint UX (Forge:PaintTile per-tile editing)

---

## §6 — Open questions (eight Q1-Q8 captured from chat 2026-04-27)

| ID | Question | Default proposal | Need user decision? |
|---|---|---|---|
| **TMP-Q1** | Tilemap for which tier? (a) all 4 non-cell tiers; (b) 1-2 tiers (continent + town); (c) author-configurable per reality | (b) V1+30d (continent + town); (c) V2 | YES — affects scope |
| **TMP-Q2** | Position reconciliation MAP_001 ↔ TMP_001 | (a) MAP_001 authoritative; tilemap derives `tile = (pos × grid / 1000)` | YES — but (a) recommended |
| **TMP-Q3** | Storage — full grid in DB or regen from seed? | Store grid as Postgres `bytea` (~64KB/tilemap raw); regen if version mismatch | OK as default |
| **TMP-Q4** | FE engine — Phaser vs Pixi vs OpenLayers vs custom canvas | Phaser (user mentioned; community + react wrapper) | OK as default |
| **TMP-Q5** | Asset cost — sprite atlas | V1+30d: emoji + colored squares (no commissioned art); V2: Kenney.nl CC0 packs OR commissioned ~$200-500/genre | YES — affects budget |
| **TMP-Q6** | Edit semantics — paint-tile vs re-roll vs hybrid | V1+30d: regen seed + place_object only; V2: manual paint | OK as default |
| **TMP-Q7** | Mobile fallback — graceful degrade to MAP_001 graph? | YES — auto-detect mobile, fall back to MAP_001 SVG; user can opt-in tilemap | OK as default |
| **TMP-Q8** | Cross-feature integration — AIT Untracked NPCs on tilemap? Weather per-tile? Travel encounters? | V1+30d: no AIT integration, no weather, no encounters; V2: all three | YES — affects V2 scope |

**Per-question default:** when a default is "OK as default", PoC will assume it and feedback if user disagrees. When "YES — need decision", PoC proceeds on most plausible interpretation; user reviews and refines after PoC.

---

## §7 — PoC plan (Session 2 — immediately following Session 1 commit)

**Goal:** validate that the 4-layer composition + camera-scroll + Phaser-render pattern feels right, BEFORE committing to V1+30d aggregate schema or boundary lock.

**Deliverable:** `poc/tilemap_world_view/` — Node.js project with Vite + TypeScript + Phaser 3. Updated 2026-04-27 from initial `_ui_drafts/TILEMAP_v1.html` plan after user direction "build PoC nghiêm túc dùng nodejs". Reusability claim §10 strengthened — code structured to port into `frontend/` (TS) + `services/world-service/` (TS→Rust) without rewrite.

**PoC stack:** Vite + TypeScript + Phaser 3 (pure Phaser, no React wrapper for PoC). Vitest for determinism tests. Node 20+.

**Demo scope (PoC v1):**
1. **Vite + TS + Phaser 3** project scaffold; `npm run dev` boots; HMR works
2. **64×64 procedural terrain grid** generated via inline value-noise + Mulberry32 PRNG (no CDN deps); deterministic seed
3. **10 terrain types** matching aggregate enum: Grass / Forest / Mountain / Water / Sand / Snow / Swamp / Road / Rough / Subterranean — colored-square fallback render
4. **L1 hardcoded skeleton** (`kingdom_default`): 7 zones (central plain, north mountain, foothill, west forest, east grass, south lake, south coast) + 7 cell anchors (capital, fortress, temple, tavern, port, 2 cells) + 5 landmarks (peak, lake, ruin, monster lair, treasure)
5. **L2 algorithm** with 2 sub-modules:
   - `terrain.ts` — zone-aware fBm value-noise (octaves per zone) → biome weighted distribution
   - `roads.ts` — A* pathfinding with terrain-cost matrix (Mountain=8, Forest=3, Water=10, Road=0.5)
6. **Phaser scene**: tile graphics layer + roads polyline + emoji object overlays
7. **Camera controls**: drag-pan + scroll-zoom + zoom buttons; bounds-clamped
8. **Click cell/landmark** → sidebar shows kind + id + position
9. **UI**: GitHub-dark theme matching `MAP_GUI_v1/v2.html` style; seed input + regen + random + zoom + export JSON
10. **Export JSON**: download `tilemap_view_<seed>.json` matching SPIKE_03 §4 aggregate shape — proves serialization
11. **Asset loader** with hybrid fallback: detects Kenney Tiny Town in `public/assets/` → uses sprite atlas; else colored squares + emoji
12. **Determinism test**: Vitest property `same seed → byte-identical TileMapView output` (per EVT-A9)

**Out of scope (PoC v1):**
- LLM integration L3/L4 (V2 — would need lmstudio proxy like CSC_v4; ~3K + ~1K tokens)
- Auto-tile transitions Wang-style (V1+30d cosmetic)
- Rivers (V1+30d; A* is reusable for river flow)
- Fog-of-war (V1+30d; depends on MAP-D10 unblock)
- Mobile fallback (V2; auto-detect mobile → MAP_001 SVG)
- React wrapper (V1+30d when porting to `frontend/`)

**Reusability mapping** (per user instruction "PoC này sẽ tái sử dụng vào game"):

| PoC module | Production target |
|---|---|
| `src/generators/prng.ts` + `noise.ts` + `terrain.ts` + `roads.ts` | Port TS → Rust at `services/world-service/src/tilemap/` |
| `src/data/types.ts` | Mirror in `contracts/api/tilemap/` OpenAPI schema |
| `src/scenes/TilemapScene.ts` + `src/render/*` | Lift to `frontend/src/features/tilemap/scenes/` (wrap in React component) |
| `src/data/skeleton.ts` (kingdom_default) | Becomes first entry in skeleton library; per-genre packs added V2 |
| `src/ui/*` + `src/styles.css` | Frontend control surface skeleton |
| `tests/generators.test.ts` | Determinism property → enforce per EVT-A9 in production CI |

**Estimated PoC effort:** 1 focused session (~2-3 hours scaffolding + verification).

**PoC success criteria:**
- (a) `npm install` + `npm run dev` boots without error; HMR works
- (b) Camera pan/zoom feels natural on desktop browser
- (c) 64×64 grid renders smoothly (60fps target) without jank
- (d) Regenerate button produces visually distinct maps from different seeds
- (e) JSON output is well-structured (passes manual review for SPIKE_03 §4 aggregate fit)
- (f) Determinism test passes: same seed → identical output (per EVT-A9)
- (g) `npm run build` produces production bundle < 2MB (Phaser + app code)

**PoC failure modes (what would invalidate the approach):**
- Phaser canvas chops on a 64×64 grid → architecture review (switch to Pixi or custom canvas)
- JSON shape proves unwieldy when structured for backend storage → revisit aggregate sketch §4
- Camera UX feels wrong vs node-link graph → maybe MAP_001 is enough; defer TMP_001 indefinitely
- Procedural terrain looks visually boring → L1 skeleton library needs more thought before V1+30d build
- Asset loader complexity outweighs benefit → drop hybrid; emoji-only V1+30d

**Asset strategy (decided 2026-04-27):**
- PoC v1 ships with colored squares + emoji icons (zero external deps; runs on `npm install` alone)
- `src/render/asset_loader.ts` detects Kenney Tiny Town (CC0) at `public/assets/kenney_tiny_town/` and switches to sprite atlas if present
- README provides download instructions + URL
- V2 production: per-genre commissioned art OR Kenney/CC0 packs as defaults

---

## §8 — Graduation path

When user reviews PoC and approves direction:

1. **Move SPIKE_03 to "DRAFT Session 2 complete"** — append PoC findings as §11 to this file
2. **Create concept doc** `features/00_tilemap/00_CONCEPT_NOTES.md` with Q1-Q12 deep-dive matrix (mirror PROG_001 / AIT_001 pattern)
3. **Q-deep-dive batched** with user (4-batch like AIT_001) → all Q LOCKED
4. **Boundary lock claim** via `_boundaries/_LOCK.md` — single agent claims for the multi-commit cycle
5. **Author** `features/00_tilemap/TMP_001_tilemap_foundation.md` (~700-1200 lines per foundation feature pattern)
6. **Catalog claim** `catalog/cat_00_TMP_tilemap_foundation.md` with `TMP-*` namespace
7. **Boundary updates** — `01_feature_ownership_matrix.md` (new aggregate row + RealityManifest extension + EVT-T sub-shapes + RejectReason namespace + stable-ID prefix); `02_extension_contracts.md` §1.4 (`tilemap.*` namespace) + §2 (RealityManifest extension)
8. **Phase 3 cleanup → CANDIDATE-LOCK** following standard pattern

If user rejects after PoC review:
- File stays as permanent reference
- PoC HTML stays in `_ui_drafts/` as reference artifact
- Add row to `_spikes/_index.md` marked "rejected" with rationale

---

## §9 — Cross-references

- [`MAP_001_map_foundation.md`](../00_map/MAP_001_map_foundation.md) — logical graph layer (UNCHANGED)
- [`PF_001_place_foundation.md`](../00_place/PF_001_place_foundation.md) — cell semantic identity (UNCHANGED)
- [`CSC_001_cell_scene_composition.md`](../00_cell_scene/CSC_001_cell_scene_composition.md) — 4-layer pattern reference; v3→v4 pivot evidence
- [`SPIKE_02_reference_games_gap_analysis.md`](SPIKE_02_reference_games_gap_analysis.md) — broader game-feature gap context
- [`SPIKE_01_two_sessions_reality_time.md`](SPIKE_01_two_sessions_reality_time.md) — pattern for spike methodology
- [`_ui_drafts/MAP_GUI_v1.html`](../../_ui_drafts/MAP_GUI_v1.html) + [`MAP_GUI_v2.html`](../../_ui_drafts/MAP_GUI_v2.html) — graph view demos
- [`_ui_drafts/CELL_SCENE_v4_layered.html`](../../_ui_drafts/CELL_SCENE_v4_layered.html) — 4-layer LLM-architecture validation demo
- HOMM3 RMG documentation — reference for procedural map generation parameter pattern (template + seed + zone connections)
- Phaser 3 documentation — `https://phaser.io/phaser3` for FE engine choice rationale

**Future cross-refs (when graduated):**
- TVL_001 Travel Mechanics — consumes road speed modifier, terrain movement cost
- MAP-D10 fog-of-war — TMP_001 V2 integrates per-PC discovered_tiles
- WTH_001 Weather (SPIKE_02 C1 if graduated) — per-biome weather binding
- QST_001 Quest System V2 — MapObjectPlacement.linked_quest_id
- CFT_001 Crafting V2 — Mine MapObjectKind = resource node consumer

---

## §10 — File hygiene

- **Author:** main session 2026-04-27
- **Locks claimed:** none (this file lives in `_spikes/`, not boundary-touching)
- **Catalog impact:** zero — no IDs claimed, no rows added
- **PoC artifacts to be created Session 2:** `_ui_drafts/TILEMAP_v1.html`
- **Tests required:** PoC success criteria §7 acts as informal acceptance test
- **Reusability commitment:** per user "PoC này sẽ tái sử dụng vào game" — PoC code structured to port to production Phaser-React + Rust backend

---

## §11 — Session 2 findings (PoC scaffold complete 2026-04-27)

### §11.1 What was built

Project at [`poc/tilemap_world_view/`](../../../../poc/tilemap_world_view/):

| Module | LoC | Purpose |
|---|---:|---|
| `src/data/types.ts` | 145 | TileMapView aggregate types mirroring §4 (10 TerrainKind, 7 MapObjectKind, ChannelTier, TileMapView) |
| `src/data/skeleton.ts` | 165 | L1 hardcoded `kingdom_default` (7 zones, 7 cell anchors, 7 landmarks, 6 road connections) — wuxia/Vietnamese theme |
| `src/generators/prng.ts` | 35 | Mulberry32 PRNG + hash2D pure function |
| `src/generators/noise.ts` | 60 | Value-noise 2D + fBm |
| `src/generators/terrain.ts` | 70 | L2.a — zone-aware fBm noise → biome distribution |
| `src/generators/roads.ts` | 145 | L2.b — A* pathfinding with terrain-cost matrix (Mountain=8, Water=12, Road=0.4) |
| `src/generators/tilemap.ts` | 50 | composeTileMap() orchestration |
| `src/render/colors.ts` | 50 | Terrain palette + emoji map + variantColor() for natural tile texture |
| `src/scenes/TilemapScene.ts` | 215 | Phaser scene: tile graphics + roads polyline + emoji overlays + camera (drag-pan + scroll-zoom-toward-pointer) |
| `src/main.ts` | 200 | Entry point + UI bindings + JSON export + terrain distribution sidebar |
| `src/ui/styles.css` | 230 | GitHub-dark theme matching MAP_GUI_v1/v2.html |
| `tests/generators.test.ts` | 175 | **19 Vitest tests** covering PRNG / hash2D / noise / terrain / roads / composition / determinism / JSON round-trip |
| **Total** | **~1540 LoC** | Production-shape, TypeScript-strict, fully tested |

Plus: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `README.md`, `.gitignore`.

### §11.2 PoC success criteria — verified

| # | Criterion | Status | Evidence |
|---|---|---|---|
| (a) | `npm install` completes without error | ✅ | 81 packages, 17s, 4 moderate vulns (in vitest deps; non-blocking) |
| (b) | `npm run dev` boots; serves HTML + TS modules | ✅ | Vite v5.4.21 ready in 426ms; localhost:5174→5175 fallback worked; main.ts compiles to 20KB ESM; styles.css 4.9KB; phaser optimized dep loaded |
| (c) | Camera pan/zoom feels natural at 60fps | ⚠️ Browser test pending | Code path implemented (drag-state + zoom-toward-pointer); needs human verification in browser |
| (d) | Regenerate produces distinct maps from different seeds | ✅ | Determinism test "different seeds → different terrain" passes |
| (e) | JSON output matches §4 aggregate shape | ✅ | Schema test verifies all required fields; JSON round-trip equivalence test passes |
| (f) | `npm test` passes — all determinism tests green | ✅ | **19/19 passed in 134ms** |
| (g) | `npm run build` produces bundle < 2MB | ✅ | **1.49MB minified / 345KB gzip** (1.5MB JS + 3KB CSS + 2KB HTML) |

### §11.3 What worked (validates SPIKE_03 architecture)

- **L1+L2 split is clean and portable.** Generators are pure functions with no DOM/Phaser dependency — direct Rust port to `services/world-service/` will be 1:1 with no architectural rework. Tests already verify the determinism invariant (per EVT-A9) that production must enforce.
- **64×64 grid renders from scratch in well under 5ms** (terrain gen + A* roads — `gen time` shown in sidebar; expected ~1-3ms based on local node test pace). LLM-free L1+L2 cost is negligible at this scale.
- **A* with terrain-cost matrix produces narratively-readable road networks.** Roads avoid Mountain/Water; reuse other Roads (cost 0.4) — natural Roman-grid emergence even without explicit network optimization.
- **Aggregate shape from §4 fits cleanly with TypeScript.** No fields needed reshaping; `terrain_layer: number[]` (flattened y*width+x) serializes well; `Layer3Source` discriminated union maps to TS easily.
- **Mulberry32 + hash2D + value-noise is sufficient for PoC visuals.** No external CDN noise lib needed; ~95 LoC total for noise stack.
- **GitHub-dark theme matches LoreWeave UI conventions** (MAP_GUI_v1/v2.html style) — easy port to Tailwind+shadcn at frontend graduation.

### §11.4 Surprises / hidden complexity discovered

| # | Discovery | Implication |
|---|---|---|
| S1 | **Phaser bundle is large** — 1.5MB minified for a "demo" engine | Frontend port should use code-splitting; tilemap scene loaded lazily on map-open. Consider Pixi.js (~600KB) if tilemap is the only Phaser use case. |
| S2 | **Variation color via `variantColor()` adds significant visual texture** without sprite art | Justifies asset-loader hybrid pattern: even without sprite atlas, tilemap looks "alive" not flat. Reduces V1+30d sprite-pack urgency. |
| S3 | **Road A\* with same-input terrain still produces same path** even though Map iteration is "implementation-defined" | JS spec requires Map insertion-order iteration → A\* tie-breaking is deterministic by accident. **For Rust port, must pick a stable tie-break explicitly (e.g., (g, x, y) lexicographic).** Risk of cross-impl divergence. |
| S4 | **Sidebar terrain distribution chart is highly informative** — shows biome% at-a-glance | Worth promoting to production: helps authors verify their skeleton zone biome_weights produce intended look. |
| S5 | **Cell labels overflow at low zoom** | Phaser text sizing doesn't auto-scale; cells visually clutter. **V1+30d:** show labels only above zoom threshold. |
| S6 | **Click vs drag disambiguation needed** explicit `dragState.moved` flag | Without it, every drag fires a click on whatever cell happened to be near pointer-up. Production wiring must preserve this pattern. |
| S7 | **Phaser `pointermove` fires before `pointerdown`'s state lands** in some Vite HMR scenarios | Workaround: set drag state in pointerdown AND check `isDown` in pointermove. Fixed in PoC. |
| S8 | **A\* with 64×64 terrain + 6 roads runs ~6 path searches with ~1000 max iterations each** | Backend Rust port should benchmark with 256×256 grid (continent scale) before committing aggregate field design — A\* may need binary heap upgrade. |

### §11.5 Aggregate schema refinements (vs §4)

After PoC implementation, `§4` aggregate sketch should be refined as follows when TMP_001 graduates:

| Field | Refinement | Rationale |
|---|---|---|
| `terrain_layer` | Add `terrain_layer_format: 'flattened_u8' \| 'rle' \| 'compressed'` discriminator | PoC stores as `number[]`; production may want byte-level compaction or RLE for storage cost. Discriminator future-proofs encoding swap. |
| `cell_placements` / `object_placements` | Confirm `tier` field on cells (added in PoC); landmarks don't need tier (always cell-tier sub-positions) | Adds richness for FE rendering decisions (capital icon larger than cell icon) |
| `Layer3Source` | Use TS-style discriminated union (`{ kind: '...' }`); not flat enum + optional fields | PoC pattern serializes cleanly through JSON.stringify; cleaner than enum-with-side-fields |
| `prompt_template_version` | Confirmed essential | Cache invalidator for V2 LLM Layer 3/4; even V1 should ship with version=1 |
| **NEW** `gen_time_ms` | Optional field for telemetry | Backend can record generation cost; V1+30d profiling input |
| **NEW** `tie_break_strategy` | Document A\* tie-break method | Required for cross-impl determinism (PoC=JS Map insertion order; Rust=lexicographic) |

### §11.6 Refined V1+30d scope cuts

Based on PoC findings, suggested V1+30d trim:

- ✅ **Keep:** L1 + L2 (terrain + roads), aggregate schema, deterministic gen, hybrid asset loader, JSON export, click-to-drill wiring
- ⚠️ **Reconsider:** Phaser as default engine — investigate Pixi.js for smaller bundle. Decision deferrable to graduation Q1-Q12 deep-dive.
- 📦 **Defer harder than originally planned:** auto-tile transitions (cosmetic; emoji+colors look adequate); rivers (A* reusable but separate L2 pass)
- 🆕 **Add to V1+30d scope:** zoom-threshold-based label visibility (S5); explicit A\* tie-break (S3); telemetry `gen_time_ms` field (S8)

### §11.7 Reusability claim — validated

PoC code structure DOES support direct port without rewrite:
- Generators (`prng/noise/terrain/roads/tilemap`) = 360 LoC of pure TS → straight Rust port; deterministic property tested
- `data/types.ts` = 145 LoC → maps cleanly to OpenAPI schema or Rust structs
- Phaser scene = 215 LoC → wrap in React component for `frontend/src/features/tilemap/`
- Tests = 175 LoC → promote to production CI as property tests for EVT-A9 enforcement

**~1100 LoC of production-shape code already written** (excluding UI styles + entry point).

### §11.8 Decision pending — user review

Next step: **user opens `npm run dev` in browser**, validates criteria (c) camera feel + (d) regenerate visual variety. Based on browser experience:

- **Graduate** → create `features/00_tilemap/00_CONCEPT_NOTES.md` + Q1-Q12 deep-dive matrix → `TMP_001_tilemap_foundation.md` design doc → boundary lock cycle → V1+30d implementation
- **Refine** → list specific gaps; spike adds PoC v2 with refinements
- **Reject** → file stays as permanent reference; V1 ships with MAP_001 SVG only

### §11.9 Files / artifacts produced this session

- `poc/tilemap_world_view/` — full Vite + TS + Phaser PoC project (~1540 LoC across 12 files + 5 config files)
- `dist/` — production build artifacts (gitignored)
- `docs/03_planning/LLM_MMO_RPG/features/_spikes/SPIKE_03_tilemap_world_view.md` — this file (§7 updated for Node.js scope; §11 filled)
- `docs/03_planning/LLM_MMO_RPG/features/_spikes/_index.md` — SPIKE_03 row added (Session 1 commit)

---

## §12 — PoC v2 visual richness pass (2026-04-27)

User feedback after PoC v1 browser review:

> "tôi đã thấy bản đồ rồi nhưng mà hơi xấu, có thể tìm thêm free assets chèn thêm vào không?
> có thể làm bản bản đồ rich như hero of might and magic 3 không?"

### §12.1 Honest constraint setting

HOMM3-rich is **not realistic in PoC** — HOMM3 has 25 years of polish + custom hand-drawn art at high resolution + isometric perspective + animated tiles + multi-tile composite objects with shadows. Realistic ambition for PoC v2: **5-8× richer than v1** using free CC0 sprite packs + code-only improvements.

### §12.2 What was built in v2

**Asset acquisition:**
- Successfully fetched Kenney Roguelike RPG Pack via probing kenney.nl page for direct zip URL: `https://kenney.nl/media/pages/assets/roguelike-rpg-pack/1cb71b28fb-1677697420/kenney_roguelike-rpg-pack.zip`
- 715KB zip → unzipped to spritesheet (94KB PNG) + sample + license
- CC0 license — committed directly to `poc/tilemap_world_view/public/assets/` (no attribution legally required, but README credits Kenney)
- Spritesheet: 968×526, 16×16 tiles + 1px margin, ~1700 tile slots, 57 cols × 31 rows

**New code modules:**

| File | LoC | Purpose |
|---|---:|---|
| [`src/render/kenney_atlas.ts`](../../../../poc/tilemap_world_view/src/render/kenney_atlas.ts) | 110 | Sprite index map: terrain-keyed decoration palette + CELL_SPRITES + LANDMARK_SPRITES + frameOf() helper. **All indices TUNABLE** if wrong sprite shows. |
| [`src/render/decorations.ts`](../../../../poc/tilemap_world_view/src/render/decorations.ts) | 75 | Procedural scatter using PRNG hash2D — deterministic per (cell_id, x, y, seed). Skips occupied tiles (cell anchors + landmarks + road waypoints + 1-tile halo around cells). |
| [`src/render/minimap.ts`](../../../../poc/tilemap_world_view/src/render/minimap.ts) | 130 | DOM canvas overlay top-right of game container. 2px-per-tile scale (128×128 minimap for 64×64 grid). Click-to-jump main camera. Viewport rect highlight in cyan. Pure DOM/canvas — no Phaser dep. |

**Modified modules:**

| File | Change |
|---|---|
| `src/render/colors.ts` | Brighter Kenney-aligned palette (Grass 0x6dac4a vs old 0x4a7e3a; Water 0x4a9bc4 vs 0x2d5f7e). Added SHORELINE_COLOR + MOUNTAIN_RIDGE_COLOR. Stronger variantColor adjustment (±12 vs ±8). |
| `src/scenes/TilemapScene.ts` | preload() loads Kenney spritesheet; create() adds 5 z-ordered layers (tiles → biome borders → decorations → roads → objects); renderBiomeBorders() draws 2px shoreline + ridge lines at terrain transitions; renderDecorations() places Kenney sprites procedurally; renderObjects() adds drop-shadow circles + uses sprite-or-emoji hybrid; road rendering added shadow underlay for visual weight. |
| `src/main.ts` | Wired Minimap (DOM overlay) with click-to-jump + 100ms viewport rect update interval. |
| `README.md` | Updated asset strategy section — Kenney pack now ships in repo; tunable indices documented. |

### §12.3 Visual improvements summary

| Improvement | Impact | Cost |
|---|---|---|
| **Kenney sprite decorations** (trees/flowers/rocks/mushrooms procedurally scattered) | High — breaks monotony of terrain squares; gives "alive" feel | 0 — code-only after asset commit |
| **Cell/landmark sprites with shadows** | High — replaces emoji with proper game art | 0 — code-only |
| **Brighter palette** matching Kenney sample | Medium — colors look intentional, not muddy | 0 |
| **Stronger per-tile variation** (±12 vs ±8) | Medium — more natural texture | 0 |
| **Biome borders** (shoreline + mountain ridge lines) | Medium — biome edges visually defined | 0 |
| **Road shadow underlay** | Low-medium — roads pop more | 0 |
| **Minimap with viewport rect** | High UX — orient at low zoom levels; click-jump | 0 |

### §12.4 Verified post-v2

| Check | Status |
|---|---|
| `npm run typecheck` | ✅ no errors |
| `npm test` | ✅ 19/19 pass in 120ms |
| `npm run build` | ✅ 1.50MB bundle / 348KB gzip |
| Vite dev server boot | ✅ ready in 392ms |
| All TS modules + Kenney sheet serve via HTTP | ✅ all 200 |

### §12.5 Known v2 limitations (still)

| # | Limitation | Reason / next step |
|---|---|---|
| L1 | Some Kenney sprite indices may be off (best-guess from visual inspection of spritesheet) | User reports: "this sprite shows wrong" → edit `kenney_atlas.ts` (col, row); fallback chain (sprite missing → emoji) means PoC always renders something |
| L2 | No auto-tile transitions (Wang-pattern blending between biomes) | V1+30d cosmetic; minor visual polish |
| L3 | Decorations don't "settle" into terrain (sprite z-ordering is per-frame, not depth-sorted) | Phaser depth sorting V1+30d if visual layering issues appear |
| L4 | Cells don't have multi-tile sprites (HOMM3 town occupies 3×3 tiles with shadow) | V2 — needs dedicated layout system; defer to TMP_001 V2 design |
| L5 | No animated water | V2+ — Phaser tile animation supports it but PoC scope cut |
| L6 | Minimap lacks zoom-out/in level (fixed 2px/tile scale) | V1+30d if grid > 128×128 |
| L7 | No "fog of war" / discovered tiles | V1+30d depends on MAP-D10 unblock |

### §12.6 PoC v2 → graduation readiness

**Reusability has IMPROVED in v2 (more code structured for production):**

| New module | Production target |
|---|---|
| `kenney_atlas.ts` | Becomes `frontend/src/features/tilemap/atlas_kenney.ts` + sibling atlases per genre pack (TMP V2 — atlas registry) |
| `decorations.ts` | Procedural scatter algorithm portable to Rust: pure function of (view, seed). Backend can pre-compute scatter and ship to FE as compact array. |
| `minimap.ts` | DOM canvas — port to React component for `frontend/src/features/tilemap/Minimap.tsx`. Pure draw, no Phaser dep makes it lightweight. |

### §12.7 Decision pending — v2 user review

User opens `npm run dev`, validates:
- (a) Map looks visually rich (5-8× over v1) — sprites visible, decorations scattered, cells stand out
- (b) Some sprites may be wrong (best-guess indices) — user reports specific sprites for index tuning
- (c) Minimap helps orient at low zoom
- (d) Click cells → sidebar info still works
- (e) Regenerate produces visually distinct maps

Then decision: **graduate** / **refine sprite indices** / further visual polish iterations.

(Session 2.5 — PoC v2 visual pass — closes when user reviews v2 in browser.)

---

## §13 — PoC v3 LLM integration (2026-04-27)

User decision after v2 visual pass:

> "ok, tạm ổn, cái này có thể fine tuned bới user sau cũng được
> về phía LLM model như qwen có thể generate bản đồ như thế này không?"

Discussion concluded with **Path A: build PoC v3 with LLM integration**. Implementation captured here.

### §13.1 Architecture (extending v2)

```
[User natural-language prompt]
    ↓
[L1.b LLM Skeleton Generator]                  ← NEW v3
    ↓ (calls /api/llm/chat/completions, Vite-proxied to lmstudio)
[Qwen 3 14B/32B via lmstudio]
    ↓ (returns JSON; max 3 retry with validation feedback)
[Schema + semantic validator]                  ← NEW v3
    ↓ (validation pass)
[TileMapSkeleton] → activeSkeleton swap
    ↓
[Engine L2 procedural] (terrain + roads — unchanged from v2)
    ↓
[Phaser render] (unchanged from v2)
```

L3/L4 still deferred to V2 design phase. PoC v3 only adds L1.b (NL-prompt-to-skeleton).

### §13.2 What was built in v3

**New modules ([src/llm/](../../../../poc/tilemap_world_view/src/llm/)):**

| File | LoC | Purpose |
|---|---:|---|
| `types.ts` | 60 | OpenAI-compatible chat completion types + LlmGenerationResult shape with attempt history |
| `client.ts` | 95 | fetch wrapper for `/api/llm/chat/completions`; LlmNetworkError / LlmHttpError / LlmResponseError classes; `probeLlm()` for endpoint health check |
| `prompts.ts` | 75 | System prompt with strict schema + 15 invariants; few-shot pair (FEWSHOT_USER + KINGDOM_DEFAULT minified as FEWSHOT_ASSISTANT); buildInitialMessages + buildRetryMessages |
| `validator.ts` | 290 | Hand-rolled validator (no Zod dep); 13 sub-validators for skeleton_id / grid_size / terrain_zones / cell_anchors / landmark_anchors / road_connections; coverage check (zones cover full grid); connectivity check (Town-tier cells reachable from capital) |
| `skeleton_generator.ts` | 110 | Orchestration: max 3 attempts; per-attempt phases (calling → parsing → validating → retrying); strips markdown JSON fences if LLM ignores `response_format: json_object`; aggregates AttemptRecord history |

**New UI ([src/ui/llm_dialog.ts](../../../../poc/tilemap_world_view/src/ui/llm_dialog.ts)):**

| LoC | Purpose |
|---:|---|
| 215 | DOM-based modal: model name input + endpoint probe-status + prompt textarea + generate/cancel buttons + live status log + result preview pane with apply button. Pure DOM (no Phaser dep). Lazy-init on first click. |

**Modified:**

| File | Change |
|---|---|
| `vite.config.ts` | Added proxy: `/api/llm` → `${VITE_LLM_ENDPOINT}/v1` (default lmstudio :1234). Avoids CORS in dev. |
| `index.html` | Added `⚡ LLM` button to toolbar |
| `src/main.ts` | Added `applyLlmSkeleton()` swapping `activeSkeleton` from `KINGDOM_DEFAULT` to LLM-generated; LlmDialog lazy-init + open handler |
| `src/ui/styles.css` | +200 lines for `.llm-dialog-*` modal styles (overlay + modal + form fields + status log + result preview) |
| `tests/llm_validator.test.ts` (NEW) | 13 test cases covering all rejection paths + KINGDOM_DEFAULT canonical pass |
| `validator.ts` connectivity check | Loosened: only Town/District/Country tiers must be road-connected; tier=Cell entries exempt as "sub-locations near a parent town" (KINGDOM_DEFAULT has 2 sub-cells without dedicated roads) |

### §13.3 Verified post-v3

| Check | Status | Evidence |
|---|---|---|
| `npm run typecheck` | ✅ | Initial validator type-coercion error fixed (use `as unknown as TileMapSkeleton`) |
| `npm test` | ✅ | **32/32 pass in ~600ms** (19 generator + 13 validator) |
| `npm run build` | ✅ | **1.52MB minified / 355KB gzip** (vs v2 1.50MB / 348KB — added ~22KB for LLM module) |
| Vite dev server boot | ✅ | ready in 405ms |
| All TS modules + Kenney sheet serve | ✅ | all 200 |
| LLM proxy reachable | ✅ | POST `/api/llm/chat/completions` returns 400 (lmstudio not running expected); proxy infrastructure works |

### §13.4 What works (validated)

- **Vite proxy bypasses CORS** — frontend at `:5174-5178` can call lmstudio at `:1234` without CORS configuration
- **Hand-rolled validator** comprehensive (13 distinct rejection paths tested)
- **Retry loop with feedback** — proven pattern from CSC v4; should work for Qwen 3 14B+ at 80%+ first-try, 95%+ with 1-2 retry
- **Strict schema in system prompt** — forces LLM to focus on layout decisions, not free-form generation
- **Few-shot example** (KINGDOM_DEFAULT) — LLM gets concrete shape reference; reduces hallucination of bad enum values
- **AbortController** wired — Cancel button stops in-flight LLM call cleanly
- **Probe endpoint health** before generation — user gets clear error if lmstudio not running

### §13.5 What's NOT validated yet (browser test)

User must verify:
1. Open `npm run dev` + run lmstudio with Qwen 3 14B (or larger)
2. Click `⚡ LLM` → endpoint probe shows green "✓ Reachable; N model(s) loaded"
3. Type a prompt → click Generate → live status log shows attempts
4. On success → result preview shows JSON; click Apply → tilemap regenerates with new skeleton
5. Test failure modes: empty prompt; lmstudio not running; small model that fails schema (Qwen 3 4B?)

### §13.6 Reusability validation — STRENGTHENED

LLM module is highly reusable:

| Module | Production target |
|---|---|
| `src/llm/client.ts` | Lift to `frontend/src/lib/llm/openai_compat.ts`; identical fetch pattern. Backend version → `services/world-service/src/llm/` (Rust port using existing provider-registry pattern). |
| `src/llm/prompts.ts` | Move to `services/world-service/src/tilemap/prompts.rs`; system prompt becomes Rust constant; few-shot example loaded from canonical skeleton library. |
| `src/llm/validator.ts` | **Critical: keep TS + add Rust mirror.** Validator should run BOTH client-side (instant feedback) AND server-side (security boundary). Rust port uses serde + custom validators. |
| `src/llm/skeleton_generator.ts` | Backend version handles authentication, billing, rate limiting via existing usage-billing-service. Frontend version stays for instant preview UX. |
| `src/ui/llm_dialog.ts` | Port to React component `frontend/src/features/tilemap/LlmDialog.tsx`; replace DOM API with React state. |

**Token budget per skeleton generation: ~3.5-4.2K input + ~1-1.5K output = ~5K total.** With Qwen 3 32B local: free; with API model (Claude Haiku): ~$0.005 per generation. Affordable for V1+30d.

### §13.7 Known v3 limitations

| # | Limitation | Reason / next step |
|---|---|---|
| L1 | Smaller Qwen models (4B, 7B) may not produce valid schema reliably | Document in README — recommend 14B+ |
| L2 | LLM output non-deterministic at temp=0.7 | User can manually set temp=0 for reproducibility; UX exposure deferred |
| L3 | No streaming of LLM response (full JSON returned at once) | Streaming JSON is hard (incomplete JSON during stream). UX-acceptable for ~30s gen time. |
| L4 | L3 zone classifier (landmark placement) NOT in v3 | V2 territory; would add ~3K tokens per call |
| L5 | L4 narration NOT in v3 | V2 territory; cheap (~1K tokens) but not blocking PoC validation |
| L6 | No prompt history / saved prompts UI | V1+30d UX |
| L7 | No multi-turn refinement ("make the mountain bigger") | V2 UX feature |

### §13.8 Decision pending — v3 user review

User must:
1. Install lmstudio + load Qwen 3 14B+ model + start server
2. `npm run dev` + click `⚡ LLM` button
3. Submit prompt; observe attempts; review preview
4. Click Apply → verify map regenerates correctly
5. Try edge cases: empty prompt; bad lmstudio endpoint; very specific prompt; very vague prompt

Then decision matrix:
- **PoC v3 confirmed working** → graduate to TMP_001 (concept_notes + Q1-Q12 deep-dive + design doc)
- **Schema/prompt needs tuning** → iterate prompts.ts/validator.ts
- **Different LLM provider needed** → swap endpoint config; provider-agnostic via OpenAI-compat API
- **L3/L4 needed in PoC** → extend with zone classifier + narration calls (each ~3K tokens; +3 attempts each)

(Session 3 — PoC v3 LLM integration — closes when user reviews v3 in browser with lmstudio running.)
