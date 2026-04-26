# CSC_001 — Cell Scene Composition

> **Conversational name:** "Cell Scene" (CSC). The 4-layer composition pipeline that turns a cell-tier place into a renderable in-scene UI: hand-authored skeleton template (Layer 1) + seed-driven procedural fixture placement (Layer 2) + LLM categorical zone-assignment for occupants (Layer 3, optional with canonical fallback) + LLM creative narration (Layer 4, optional). Replaces the architecturally-flawed "LLM-as-grid-generator" approach with bounded layers matching LLM strengths to creative-decision-only and LLM weaknesses (spatial coordinate manipulation) confined to deterministic engine code.
>
> **Category:** CSC — Cell Scene Composition (foundation tier; sibling of EF_001 + PF_001 + MAP_001; 4th foundation feature covering the in-scene rendering layer)
> **Status:** **DRAFT 2026-04-26** (Option C max scope per user direction "design now"; v3→v4 demo evidence in `_ui_drafts/CELL_SCENE_v1..v4` validates 4-layer architecture)
> **Catalog refs:** [`cat_00_CSC_cell_scene_composition.md`](../../catalog/cat_00_CSC_cell_scene_composition.md) — owns `CSC-*` namespace (`CSC-A*` axioms · `CSC-D*` deferrals · `CSC-Q*` open questions)
> **Builds on:** [PF_001 Place Foundation](../00_place/PF_001_place_foundation.md) (reads `place.place_type` to pick skeleton; `place.fixture_seed` informs Layer 1 template), [EF_001 Entity Foundation](../00_entity/EF_001_entity_foundation.md) (reads `entity_binding WHERE cell_id` for Layer 3 occupant list), [MAP_001 Map Foundation](../00_map/MAP_001_map_foundation.md) (cell-tier visual layer; `map_layout.background_asset` V1+ renders under cell scene), [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §3.2 scene_state (runtime ambient feeds Layer 4 narration), [PL_005 Interaction](../04_play_loop/PL_005_interaction.md) (cell scene UI consumer; click entity → 5 V1 InteractionKinds), [07_event_model](../../07_event_model/) Option C taxonomy (T4 SceneLayoutBorn; T3 Derived for cell_scene_layout deltas; T8 Administrative for Forge edits)
> **Resolves:** Cell scene rendering gap (EF + PF + MAP cover semantic substrate; CSC owns the visual composition layer that turns these into pixels) · Architectural pivot from v3 LLM-as-grid (32K reasoning tokens, 0 successful renders on Qwen 3.6 35B-A3B) to v4 LLM-as-zone-classifier (2.5K total tokens, 6/6 entities placed correctly) — **12.7× cost reduction with higher reliability**, captured as core architectural axiom CSC-A1
> **Defers to:** future TVL_001 Travel Mechanics for V1+ within-cell PC movement · future MAP_002 Asset Pipeline for V1+ skeleton sprite art · future Forge V2 for visual skeleton editor UI · WA_003 for V1+ author-uploaded skeleton templates

---

## §1 Why this exists

Three concrete gaps in the V1 design surface that CSC_001 closes:

**Gap 1 — Cell scene rendering had no schema-level home.** Foundation tier so far covered: WHO (EF entity addressability), WHERE-semantic (PF place identity), WHERE-visual-graph (MAP world map). But "click into a cell, see what's there" — the in-scene gameplay layer where PC/NPC/Item interaction actually happens — had no feature owning the composition pipeline. PCS_001 spawn assumes a renderable scene exists; PL_005 Interaction targeting assumes click-able entities at known positions. Without CSC_001, downstream features can't ground their UI behavior.

**Gap 2 — Naive "LLM generates grid" approach is architecturally flawed.** Demo evidence captured at `_ui_drafts/CELL_SCENE_v1..v4`:

| Demo | Approach | Qwen 3.6 35B-A3B result | Total tokens |
|---|---|---|---|
| v1 | Hand-crafted (no LLM) | works (visual only) | 0 |
| v2 | LLM generates 16×16 ASCII grid | multi-char alphabet confusion (Co/Wn parsed as separate chars) | varied; failures |
| v3 | Single-char alphabet + few-shot + retry | 30,000 reasoning tokens; hit 4K limit; no output | 31,448 (failed) |
| **v4** | **4-layer (skeleton + procedural + LLM-zones + narration)** | **all 6 entities correctly placed** | **2,471 (success)** |

LLMs are bad at spatial coordinate manipulation at scale (256-cell grid mental tracking, multi-row character-level accuracy, plan-execution decoupling) and good at categorical decisions + creative prose. The v3→v4 pivot maps LLM jobs to LLM strengths.

**Gap 3 — Per-cell handcrafting is impossible at scale.** Realities will have hundreds-thousands of cells. Author handcrafts of every layout don't scale. Pure handcraft only fits canonical landmark cells (throne rooms, key narrative locations). CSC_001 provides the procedural-with-LLM-flavor pipeline that fills the long tail.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **CellSceneLayout** | Aggregate `cell_scene_layout` (T2 / Channel-cell scope) — per-cell-id | Single row per cell; covers all 4 layers' state. See §3. |
| **SkeletonId** | Newtype `pub struct SkeletonId(String)` — identifier for hand-authored template | V1: `tavern_compact` / `tavern_long_hall` / `tavern_open_plan` / `default_generic_room`. V1+ libraries grow per-PlaceType. |
| **SkeletonTemplate** | Layer 1 hand-authored template — `tiles: [[char; 16]; 16]` + `zones: HashMap<String, ZoneBounds>` | Static config (Rust const or JSON file shipped with binary V1). Author override per-cell V1+ via Forge. |
| **ZoneBounds** | Declarative bounding box `Rect { rows: (u32, u32), cols: (u32, u32) }` OR `TileList(Vec<TileCoord>)` | Skeleton declares zone NAMES + bounds; Layer 2 resolves to actual tile coords (subtracting walls/fixtures). |
| **ProceduralSeed** | u64 — derived from `blake3(reality_id, cell_id, structural_state, fiction_time_bucket)` | Replay-deterministic per EVT-A9. Same inputs → same fixture placement. |
| **FixturePosition** | Layer 2 output — `{ kind: FixtureKind, position: TileCoord, size: u32, group_id: Option<u32> }` | One per fixture placed (counter, table, chairs, fireplace, window). `group_id` ties tables to their adjacent chairs. |
| **FixtureKind** | Closed enum 5 V1 — `Counter \| Table \| Chair \| Fireplace \| Window` | Maps to single-char tile alphabet B / T / H / P / N respectively. |
| **ZoneCatalog** | Layer 2 output — `HashMap<String, Vec<TileCoord>>` mapping zone-name → resolved tile coords | Examples: `counter:on` → tile list of B-typed counter tiles; `table_3:seated` → adjacent H chair tiles; `south_entry:just_inside` → F floor tile inside door. |
| **EntityZoneAssignment** | Layer 3 output (optional) — `HashMap<EntityId, String>` mapping entity → zone-name | LLM-generated OR canonical-default. None → use canonical fallback algorithm. |
| **Layer3Source** | Closed enum — `CanonicalDefault \| LlmGenerated { model, attempts, generated_at }` | Audit + cache invalidation. |
| **NarrationText** | Layer 4 output — `Option<String>` (Vietnamese prose V1; en V1+ per CSC-Q3) | Free-form; no schema validation. Cached per (cell, scene_state, occupant_set). |
| **TileCoord** | `(u32, u32)` — (x, y) within 16×16 grid | x = column 0..15, y = row 0..15. Same convention as MAP_001 §5 but at cell-internal scale (not parent-viewport). |
| **PlaceMetadata** | Read-projection from PF_001 — `{ place_type, canon_ref, structural_state, narrative_drift, display_name }` | Layer 3+4 LLM input context. |
| **AmbientState** | Read-projection from PL_001 scene_state — `{ weather, time_of_day_qualifier, crowd_density }` | Layer 4 LLM input context. |
| **OccupantSummary** | Per-entity input to Layer 3+4 — `{ entity_id, kind, display_name, mood?, status_effects? }` | Read-projection from EF_001 entity_binding + per-feature aggregates (NPC_001 mood; PL_006 status). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

CSC_001 introduces no new EVT-T* category. Maps onto existing mechanism-level taxonomy:

| CSC event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Scene layout birth (first PC entry to cell triggers compute; or RealityManifest bootstrap with eager option) | **EVT-T4 System** | `SceneLayoutBorn { channel_id, skeleton_id, procedural_seed }` | DP-Internal RealityBootstrapper OR world-service on first cell load | Layer 1+2 deterministic; one event per cell-tier channel V1. Cached forever until structural change. |
| Layer 3 LLM zone-assignment commit (when LLM call returns valid placement) | **EVT-T3 Derived** | `aggregate_type=cell_scene_layout` (entity_zone_assignments + layer3_source field deltas) | Aggregate-Owner role (world-service post-validate) | Causal-ref to triggering EVT-T1 Submitted (PC entry) or EVT-T8 Administrative (Forge refresh). |
| Layer 4 narration cache write (V1+; deferred caching aggregate) | **EVT-T3 Derived** (V1+) | `aggregate_type=cell_scene_narration_cache` | Future feature | Out of CSC_001 V1 scope; deferred to CSC-D11 reservation. |
| Author-edit cell scene via Forge (change skeleton / reroll seed / refresh LLM zones) | **EVT-T8 Administrative** | `Forge:EditCellScene { channel_id, edit_kind, before, after }` | WA_003 Forge | Edit kinds V1: ChangeSkeleton / RerollSeed / ForceLayer3Refresh / ForceLayer4Refresh / ResetToCanonicalDefaults. |
| Layer 3 LLM proposal (V1+ pre-commit review queue) | **EVT-T6 Proposal** (V1+) | `csc:Layer3Proposal` | Future feature | V1+ if author-review pipeline needed for LLM-generated layouts. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. EVT-T4 System sub-types row gains `SceneLayoutBorn` (CSC_001-owned alongside EF EntityBorn / PF PlaceBorn / MAP LayoutBorn); EVT-T3 Derived sub-types row gains `aggregate_type=cell_scene_layout`; EVT-T8 Administrative sub-shapes registry gains `Forge:EditCellScene`.

---

## §3 Aggregate inventory

One aggregate owned by CSC_001 V1:

### 3.1 `cell_scene_layout` (T2 / Channel-cell scope) — PRIMARY

```rust
#[derive(Aggregate)]
#[dp(type_name = "cell_scene_layout", tier = "T2", scope = "channel")]
pub struct CellSceneLayout {
    pub channel_id: ChannelId,                            // primary key (cell-tier only V1; mirrors PF_001 §3.1)
    pub skeleton_id: SkeletonId,                          // Layer 1 selected template
    pub procedural_seed: u64,                             // Layer 2 input (deterministic per blake3 hash); see §14 cross-service for JSON string-serialization
    pub procedural_params: ProceduralParams,              // Layer 2 input (table_count, density, fireplace_side)
    pub fixture_positions: Vec<FixturePosition>,          // Layer 2 output; cached
    pub zone_catalog: HashMap<String, Vec<TileCoord>>,    // Layer 2 output (Phase 3 S1.1 — was untyped serde_json::Value; now strongly-typed)
    pub entity_zone_assignments: Option<EntityZoneAssignmentMap>,  // Layer 3 output (None = use canonical fallback)
    pub layer3_source: Layer3Source,                      // CanonicalDefault | LlmGenerated{...}
    pub prompt_template_version: u32,                     // Phase 3 S2.8 — cache invalidator on prompt schema upgrades; V1 = 1
    pub last_layout_change_fiction_time: FictionTime,
}

pub struct SkeletonId(pub String);                        // canonical id; V1: tavern_compact/long_hall/open_plan/default_generic_room

pub struct ProceduralParams {
    pub table_count: u32,                                 // 2..=6 V1
    pub density: f32,                                     // 0.1..=1.0 V1 (drives counter_size + decoration intensity)
    pub fireplace_side: FireplaceSide,                    // east | west | north (interior wall placement)
}

// V1 defaults applied at first row creation (Phase 3 S2.7 — was undocumented).
// Author can override via Forge:EditCellScene; per-PlaceType per-skeleton tuning V1+ (CSC-Q5).
impl Default for ProceduralParams {
    fn default() -> Self {
        Self { table_count: 4, density: 0.6, fireplace_side: FireplaceSide::East }
    }
}

pub enum FireplaceSide {
    East, West, North,
}

pub struct FixturePosition {
    pub kind: FixtureKind,                                // Counter | Table | Chair | Fireplace | Window
    pub position: TileCoord,                              // (x, y) within 16×16
    pub size: u32,                                        // tiles occupied (counter=3..5; table=1; etc.)
    pub group_id: Option<u32>,                            // tables 1, 2, 3 ... for chair association
}

pub enum FixtureKind {                                    // closed 5 V1 — maps to single-char alphabet
    Counter,                                              // → B
    Table,                                                // → T
    Chair,                                                // → H
    Fireplace,                                            // → P
    Window,                                               // → N
}

pub struct EntityZoneAssignmentMap {
    pub assignments: HashMap<EntityId, String>,           // entity_id → zone_name (e.g., "counter:behind")
    pub generated_at_fiction_time: FictionTime,
}

pub enum Layer3Source {
    CanonicalDefault,                                     // engine-computed fallback (no LLM); fast + deterministic
    LlmGenerated {                                        // LLM-supplied; cached until invalidation
        model: String,                                    // "qwen/qwen3.6-35b-a3b" etc.
        attempts: u32,                                    // 1..=3 (retry count used)
        generated_at_fiction_time: FictionTime,
    },
}

pub struct TileCoord {
    pub x: u32,                                           // 0..=15
    pub y: u32,                                           // 0..=15
}
```

**Rules:**
- One row per `channel_id` (cell-tier only V1; non-cell channels have no `cell_scene_layout`). PF_001 1:1 cell invariant inherited.
- `skeleton_id` MUST resolve to a registered skeleton template OR fall back to `default_generic_room`. Unknown id → engine logs `csc.skeleton_not_found` and uses fallback at runtime (NOT a user-facing reject; see §10.2 Phase 3 S3.3 framing tightening).
- `procedural_seed` is computed at row-creation time as `blake3(b"csc-procedural-seed", reality_id, channel_id, structural_state, fiction_time_bucket).truncate_to_u64()`. Authors may override via `Forge:EditCellScene.RerollSeed { new_seed }`. Cross-service serialized as **string** (Phase 3 S1.5 — JS Number precision loss prevention; see §14).
- `procedural_params`: defaults to `ProceduralParams::default()` at first row creation (Phase 3 S2.7); author override via Forge.
- `fixture_positions` + `zone_catalog` are computed by Layer 2 at row creation; cached. Recomputed only on (skeleton_id, procedural_seed, procedural_params) change.
- `entity_zone_assignments`: None means engine uses canonical default at read-time (always succeeds; deterministic). Some(...) means LLM-generated assignment cached; invalidated when occupant set changes (entity entry/exit at cell) OR `prompt_template_version` mismatches current.
- `layer3_source`: tracks provenance for audit + cache invalidation.
- `prompt_template_version`: V1 = 1; bumped on Layer 3 / Layer 4 prompt schema changes that may invalidate cached LLM outputs (Phase 3 S2.8). Cache miss on version mismatch triggers re-call.

---

## §4 Layer 1 — Skeleton template registry

Hand-authored 16×16 templates per PlaceType. **V1 only Tavern + default_generic_room** (per Q6-a sub-decision); V1+ libraries grow per-PlaceType.

### 4.1 V1 skeleton templates

| SkeletonId | PlaceType compatibility | Shape | Zones declared |
|---|---|---|---|
| `tavern_compact` | Tavern | square 16×16 with counter NW + open center + door S | counter / center_floor / east_wall / west_wall / north_wall / south_entry / door / threshold |
| `tavern_long_hall` | Tavern | E-W rectangular hall with internal wall row 4 | counter / center_floor / east_wall / west_wall / north_wall / south_entry / door / threshold |
| `tavern_open_plan` | Tavern | sparse perimeter with multiple south doors + carpet borders | counter / center_floor / east_wall / west_wall / north_wall / south_entry / door / threshold |
| `default_generic_room` | All non-Tavern V1 (Residence/Marketplace/Temple/Workshop/OfficialHall/Road/Crossroads/Wilderness/Cave) | 16×16 with single south door + open floor + 1 wall fixture slot | center_floor / south_entry / door / threshold (no counter / no fireplace) |

### 4.2 SkeletonTemplate Rust shape

```rust
pub struct SkeletonTemplate {
    pub id: SkeletonId,                                   // canonical id
    pub display_name: String,                             // human-readable name
    pub place_type_compat: Vec<PlaceType>,                // which PF_001 PlaceTypes accept this
    pub tiles: [[char; 16]; 16],                          // single-char alphabet, 16×16
    pub zones_decl: HashMap<String, ZoneBounds>,          // declarative zone bounds
}

pub enum ZoneBounds {
    Rect { rows: (u32, u32), cols: (u32, u32) },          // inclusive bounding box
    TileList(Vec<TileCoord>),                             // explicit tile set (for irregular zones)
}
```

### 4.3 Skeleton selection algorithm

When a cell's `cell_scene_layout` is being created (lazy at first PC entry, OR eager at RealityManifest bootstrap if `eager_scene_compute` flag):

```rust
fn select_skeleton(cell_id: ChannelId, place_type: PlaceType, manifest_overrides: &HashMap<ChannelId, SkeletonId>) -> SkeletonId {
    // 1. Author-declared override takes priority
    if let Some(override_id) = manifest_overrides.get(&cell_id) {
        return override_id.clone();
    }
    // 2. Filter templates by PlaceType compatibility
    let compatible: Vec<&SkeletonTemplate> = SKELETON_REGISTRY.iter()
        .filter(|t| t.place_type_compat.contains(&place_type))
        .collect();
    // 3. If no compatible templates, fall back to default_generic_room
    //    (V1+ S3.4: when V1+ adds new PlaceTypes that no template claims compat for,
    //    default_generic_room MUST be updated to include them; default_generic_room is
    //    the universal fallback contract.)
    if compatible.is_empty() {
        return SkeletonId("default_generic_room".to_string());
    }
    // 4. Pick deterministically (Phase 3 S1.3 — explicit blake3 for replay-determinism)
    let hash_input = format!("csc-skeleton-select:{}", cell_id.as_str());
    let hash_bytes = blake3::hash(hash_input.as_bytes());
    let hash_u64 = u64::from_le_bytes(hash_bytes.as_bytes()[0..8].try_into().unwrap());
    let idx = (hash_u64 % (compatible.len() as u64)) as usize;
    compatible[idx].id.clone()
}
```

V1+ extensions tracked at CSC-D1 (per-PlaceType libraries) + CSC-D5 (author skeleton uploads via Forge V2). **V1+ PlaceType extension semantics (Phase 3 S3.4):** when EF-D1 adds new EntityId variants AND new PlaceType variants land, `default_generic_room.place_type_compat` MUST be updated to include the new variants in the same boundary review. Treat `default_generic_room` as the open-ended fallback that absorbs new PlaceTypes by default.

---

## §5 Layer 2 — Procedural fixture placer

Engine code; no LLM. Deterministic given `(skeleton, procedural_seed, procedural_params)`.

### 5.1 Algorithm

```rust
use rand_chacha::ChaCha8Rng;       // Phase 3 S1.4 — explicit RNG for replay-determinism
use rand::SeedableRng;

fn run_layer_2(
    skeleton: &SkeletonTemplate,
    seed: u64,
    params: &ProceduralParams,
) -> Layer2Output {
    let mut grid = skeleton.tiles.clone();
    let mut rng = ChaCha8Rng::seed_from_u64(seed);  // ChaCha8 — deterministic, NOT thread-local random
    let mut fixtures = Vec::new();
    let mut zones = resolve_zone_decls(&skeleton.zones_decl);  // decl → tile lists

    // 5.1.a Counter: place 3..=5 contiguous B tiles in counter zone
    // Phase 3 S1.2 — Rust idiomatic clamp: value.clamp(min, max)
    let counter_size = ((3.0 + params.density * 2.0).round() as u32).clamp(3, 5);
    let counter_tiles = place_counter(&mut grid, &zones["counter"], counter_size, &mut rng);
    for t in &counter_tiles { fixtures.push(FixturePosition { kind: Counter, position: *t, size: 1, group_id: None }); }
    zones.insert("counter:on".into(), counter_tiles.clone());
    zones.insert("counter:behind".into(), counter_tiles.iter().filter_map(|t| floor_below(&grid, *t)).collect());

    // 5.1.b Fireplace: 1-2 P tiles on selected wall
    let fp_zone = match params.fireplace_side {
        East => &zones["east_wall"],
        West => &zones["west_wall"],
        North => &zones["north_wall"],
    };
    let fp_tiles = place_fireplace(&mut grid, fp_zone, &mut rng);
    for t in &fp_tiles { fixtures.push(FixturePosition { kind: Fireplace, position: *t, size: 1, group_id: None }); }
    zones.insert("fireplace".into(), fp_tiles);

    // 5.1.c Tables + adjacent chairs (params.table_count, with 2x2 spacing constraint)
    for table_idx in 0..params.table_count {
        let table_pos = pick_table_position(&grid, &zones["center_floor"], &mut rng);
        if let Some(pos) = table_pos {
            grid[pos.y][pos.x] = 'T';
            fixtures.push(FixturePosition { kind: Table, position: pos, size: 1, group_id: Some(table_idx) });

            // Adjacent chairs (1-2 per table)
            let chair_count = if rng.next_f32() > 0.5 { 2 } else { 1 };
            let chair_positions = place_adjacent_chairs(&mut grid, pos, chair_count, &mut rng);
            for cp in &chair_positions { fixtures.push(FixturePosition { kind: Chair, position: *cp, size: 1, group_id: Some(table_idx) }); }

            zones.insert(format!("table_{}:on", table_idx + 1), vec![pos]);
            zones.insert(format!("table_{}:seated", table_idx + 1), chair_positions.clone());
            zones.insert(format!("table_{}:near", table_idx + 1), adjacent_floors(&grid, pos));
        }
    }

    // 5.1.d Windows: at least 1 N tile already in skeleton; Layer 2 may add more if density high
    if params.density > 0.7 {
        // Add 1 more window on outer wall opposite existing
        ...
    }

    // 5.1.e Door + threshold zones from skeleton (already declared)
    zones.insert("door".into(), find_tiles(&grid, 'D'));
    zones.insert("threshold".into(), find_tiles(&grid, 'R'));
    zones.insert("south_entry:just_inside".into(), zones["door"].iter()
        .filter_map(|d| floor_above(&grid, *d)).collect());
    zones.insert("center_floor:open".into(), find_open_floor(&grid, &zones["center_floor"]));

    Layer2Output { grid, fixtures, zone_catalog: zones }
}
```

### 5.2 Determinism guarantees

- Same `(skeleton, seed, params)` → byte-identical Layer 2 output (replay-safe per EVT-A9)
- **RNG: `ChaCha8Rng` from `rand_chacha` crate** (Phase 3 S1.4 — explicit choice; NOT thread-local random; cross-implementation reproducible)
- Insertion order in Vec preserved; `HashMap` iteration NOT used in critical path (any HashMap-derived output sorted by key before canonicalization)
- No floating-point arithmetic in critical path (use integer math; `f32` only for `params.density` which is converted to integer thresholds via `((3.0 + density * 2.0).round() as u32).clamp(3, 5)` pattern)

### 5.3 Failure modes

Layer 2 cannot fail in the traditional sense — algorithm always produces some output. Edge cases:
- Counter zone too small (< 3 tiles available F) → place fewer counter tiles (down to 0) without erroring
- Center_floor too small for `params.table_count` tables → place as many as fit, log warning
- All paths blocked by skeleton walls → degenerate but valid Layer 2 output (just floors + skeleton; no fixtures). This is an authoring problem (bad skeleton); not a runtime failure.

No `csc.*` rule_id for Layer 2 (always succeeds).

---

## §6 Layer 3 — LLM zone assignment

Optional. Engine has canonical-default fallback that always works.

### 6.1 LLM input contract

```rust
pub struct Layer3Request {
    pub channel_id: ChannelId,
    pub place_metadata: PlaceMetadata,                    // PF_001 read
    pub fixtures_summary: Vec<String>,                    // human-readable (from Layer 2 output)
    pub zones_available: Vec<String>,                     // names from zone_catalog
    pub entities_to_place: Vec<EntityPlacementSpec>,      // EF_001 + per-feature
    pub locale: Locale,                                   // "vi" V1
}

pub struct EntityPlacementSpec {
    pub entity_id: EntityId,
    pub kind: EntityType,                                 // Pc | Npc | Item | EnvObject (cell-internal)
    pub display_name: String,
    pub canonical_default_zone_hint: String,              // engine's recommendation if LLM fails
    pub placement_constraint: PlacementConstraint,        // Walkable | Placeable
}

pub enum PlacementConstraint {
    Walkable,                                             // F/C/H/D/R only (actors)
    Placeable,                                            // F/C/H/D/R + B + T (items can sit on furniture)
}
```

### 6.2 LLM prompt template (V1)

System message: `You are a scene populator. Output strict JSON only.`

User message structure (formalized from v4 demo prompt):

```
TAVERN SCENE: {place_metadata.display_name} ({place_metadata.canon_ref})
Ambient: {ambient_summary}

FIXTURES PLACED:
- Counter ({counter_size} tiles)
- table_1 (with {n} chairs)
- table_2 (with {n} chairs)
- ...
- Fireplace, window already in place

AVAILABLE ZONES (engine-resolved tile lists):
- {zone_name_1}
- {zone_name_2}
...

ASSIGN each entity to ONE zone name from list above:
- {entity_1.id} — {entity_1.placement_hint}
- {entity_2.id} — {entity_2.placement_hint}
...

Output JSON ONLY (no markdown, no commentary):
{"<entity_id>":"<zone_name>", ...}
```

### 6.3 LLM output validators

Validators run on parsed JSON output (mirrors v4 demo validators):

| # | Check | rule_id on fail |
|---|---|---|
| 1 | All required entity ids present in assignments | `csc.entity_missing_from_assignment` |
| 2 | All zone_name values exist in `zones_available` | `csc.invalid_zone_assignment` |
| 3 | Resolved coords (engine maps zone → first available tile in zone) pass placement constraint per entity (Walkable for actors / Placeable for items) | `csc.actor_on_non_walkable` OR `csc.item_on_non_placeable` |
| 4 | No two entities resolve to same TileCoord | `csc.zone_overlap` |

### 6.4 Retry loop (max 3 attempts V1)

```rust
fn run_layer_3_with_retry(request: Layer3Request, max_attempts: u32) -> Layer3Output {
    let mut history: Vec<ChatMessage> = vec![system_message(), user_message(&request)];

    // Phase 3 S2.2 — capture occupant snapshot at call start; verify unchanged at write
    let occupant_snapshot_hash = hash_occupant_set(&request.entities_to_place);

    for attempt in 1..=max_attempts {
        let response = llm_call(&history)?;
        let parsed = parse_json(&response)?;
        let validators = run_layer3_validators(&parsed, &request);
        if validators.all_pass() {
            // Phase 3 S2.2 — PC race check: re-fetch current occupant set; if changed mid-call, abort write
            let current_hash = hash_current_occupants(&request.channel_id);
            if current_hash != occupant_snapshot_hash {
                log::info!("csc.layer3_occupant_set_changed: aborting write; will re-trigger on next entry");
                // V1: abort + skip write; canonical fallback already in place from §15.1 lazy-create
                return Layer3Output::AbortedRaceCondition;
            }
            return Layer3Output::Success {
                assignments: parsed.assignments,
                source: Layer3Source::LlmGenerated { model: ..., attempts: attempt, generated_at: now() },
            };
        }
        // Build feedback and append to history for retry
        history.push(assistant_message(&response));
        history.push(user_feedback_message(&validators.failures));
    }
    // All retries exhausted; fall back to canonical default
    Layer3Output::Fallback {
        assignments: canonical_default_assignment(&request, &request.zone_catalog),
        source: Layer3Source::CanonicalDefault,
        last_error: Some("layer3_retry_exhausted".to_string()),
    }
}
```

**PC race condition policy V1 (Phase 3 S2.2):** Layer 3 LLM calls are async (typically 2-30s); occupants may change mid-call (PC leaves cell, another PC enters, NPC moves). Policy:
- **Capture occupant snapshot** at LLM call start (`hash_occupant_set` over sorted entity_id list)
- **At write commit**, re-fetch current occupant set; compare hash to snapshot
- **If unchanged**: write LLM result to aggregate
- **If changed**: abort + skip write (canonical fallback already populated by §15.1 lazy-create flow); log `csc.layer3_occupant_set_changed` (V1+ rule_id reservation; V1 logged only for ops observability); next cell entry re-triggers Layer 3 invocation against fresh occupants

Trade-off: occasional re-LLM cost on race vs guaranteed consistency. Single-PC realities rarely race; multi-PC tavern scenarios may re-trigger frequently — V1+30d profiling decides if a different policy (last-write-wins, merge, etc.) is preferable.

### 6.5 Canonical default assignment (no LLM; fallback)

```rust
fn canonical_default_assignment(
    request: &Layer3Request,
    zone_catalog: &HashMap<String, Vec<TileCoord>>,
) -> HashMap<EntityId, String> {
    let mut out = HashMap::new();
    for spec in &request.entities_to_place {
        // Phase 3 S2.1 — empty-zone fallback chain
        // If hinted zone is empty (Layer 2 produced 0 tiles for it), walk fallback list
        // to find first non-empty zone matching entity's placement constraint.
        let resolved_zone = resolve_with_fallback(
            &spec.canonical_default_zone_hint,
            zone_catalog,
            &spec.placement_constraint,
            &fallback_chain_for(&spec.entity_id, &spec.kind),
        );
        out.insert(spec.entity_id.clone(), resolved_zone);
    }
    out
}

fn fallback_chain_for(entity_id: &EntityId, kind: &EntityType) -> Vec<&'static str> {
    // Per-entity fallback chain (priority list; first non-empty zone wins)
    match (entity_id.id_str(), kind) {
        // PC: door/threshold area → any walkable
        (id, _) if id.starts_with("pc:") =>
            vec!["south_entry:just_inside", "threshold", "door", "center_floor:open"],

        // NPC tavern keeper: behind counter → near table → open floor
        (id, _) if id.contains("lao_ngu") =>
            vec!["counter:behind", "table_1:near", "center_floor:open"],

        // NPC waitress: near table → open floor
        (id, _) if id.contains("tieu_thuy") =>
            vec!["table_1:near", "table_2:near", "center_floor:open"],

        // NPC scholar: seated at far table → near far table → open floor
        (id, _) if id.contains("du_si") =>
            vec!["table_N:seated", "table_N:near", "table_1:seated", "center_floor:open"],

        // Item tea_pot: on counter → on table → open floor (last resort)
        (id, _) if id.contains("tea_pot") =>
            vec!["counter:on", "table_1:on", "center_floor:open"],

        // Item scroll: on far table → on counter → open floor
        (id, _) if id.contains("scroll") =>
            vec!["table_N:on", "counter:on", "table_1:on", "center_floor:open"],

        // Generic NPC default
        (_, EntityType::Npc) => vec!["center_floor:open", "south_entry:just_inside"],

        // Generic item default
        (_, EntityType::Item) => vec!["counter:on", "table_1:on", "center_floor:open"],

        _ => vec!["center_floor:open"],
    }
}

fn resolve_with_fallback(
    primary: &str,
    catalog: &HashMap<String, Vec<TileCoord>>,
    constraint: &PlacementConstraint,
    chain: &[&str],
) -> String {
    // Try primary first
    if zone_has_valid_tile(primary, catalog, constraint) {
        return primary.to_string();
    }
    // Walk fallback chain
    for zone_name in chain {
        if zone_has_valid_tile(zone_name, catalog, constraint) {
            // Phase 3 S2.1 — log csc.zone_empty_fallback_used (defensive ops signal)
            log::warn!("csc.zone_empty_fallback_used: primary={} fallback={}", primary, zone_name);
            return zone_name.to_string();
        }
    }
    // Last resort: any walkable/placeable tile in catalog
    log::error!("csc.zone_empty_fallback_used: no zone in fallback chain has tiles; using catalog scan");
    "center_floor:open".to_string()  // engine guarantees this zone always has at least 1 tile
}
```

**Engine's default hint per entity** (V1 baseline; per-entity chain in `fallback_chain_for`):
- pc → `south_entry:just_inside` (then door/threshold/center_floor as fallbacks)
- npc tavern_keeper → `counter:behind` (then table_1:near/center_floor:open)
- npc waitress → `table_1:near` (then table_2:near/center_floor:open)
- npc scholar → `table_N:seated` for last-table N (then table_N:near/table_1:seated/center_floor:open)
- item tea_pot → `counter:on` (then table_1:on/center_floor:open)
- item scroll → `table_N:on` (then counter:on/table_1:on/center_floor:open)

These defaults guarantee the canonical fallback NEVER fails — `center_floor:open` is the universal last-resort which Layer 2 invariantly populates with at least 1 tile (per §5.3 algorithm: even degenerate skeletons produce some F floor tile in the center zone).

---

## §7 Layer 4 — LLM narration

Optional. UI shows fixture-list summary if narration absent (non-blocking).

### 7.1 LLM input contract

```rust
pub struct Layer4Request {
    pub place_metadata: PlaceMetadata,                    // PF_001 read
    pub ambient: AmbientState,                            // PL_001 scene_state read
    pub fixtures_summary: Vec<String>,                    // Layer 2 output
    pub occupants: Vec<OccupantSummary>,                  // EF + NPC + PCS reads
    pub locale: Locale,                                   // "vi" V1
}
```

### 7.2 Prompt template (V1)

System message: `You are a scene narrator for an LLM-driven RPG. You write Vietnamese prose only.`

User message:
```
Scene: {display_name} ({place_metadata.canon_ref})
Ambient: {ambient_summary in Vietnamese}
Skeleton: {skeleton_display_name}
Occupants: {npc_list with positions in Vietnamese}
Items visible: {item_list in Vietnamese}
PC just arrived: {pc_display_name} qua cửa nam.

Viết 2-3 câu mô tả khung cảnh bằng tiếng Việt, theo phong cách {genre}.
Output prose only, không markdown:
```

### 7.3 No structured validation

Layer 4 output is creative free-form. Accepted as-is. UI displays text in narration panel.

Length guideline (NOT enforced): 2-3 sentences (V1); V1+ may add length controls.

### 7.4 Cache strategy

```rust
// Phase 3 S3.1 — explicit canonical hash algorithms
fn cache_key_layer_4(
    channel_id: &ChannelId,
    place_metadata: &PlaceMetadata,
    ambient: &AmbientState,
    occupants: &[OccupantSummary],
    prompt_template_version: u32,        // Phase 3 S2.8 — invalidates cache on prompt schema change
) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(b"csc-layer4-narration-cache");
    hasher.update(channel_id.as_bytes());
    // Canonicalize place_metadata + ambient via serde_json with sort_keys=true for stability
    hasher.update(canonical_json_bytes(place_metadata).as_bytes());
    hasher.update(canonical_json_bytes(ambient).as_bytes());
    // Phase 3 S3.1 — occupant_set_hash: canonical sort by entity_id, then blake3
    hasher.update(&occupant_set_hash(occupants));
    hasher.update(&prompt_template_version.to_le_bytes());
    hasher.finalize().into()
}

fn occupant_set_hash(occupants: &[OccupantSummary]) -> [u8; 32] {
    // Sort by entity_id lexicographically (canonical order)
    let mut sorted: Vec<&OccupantSummary> = occupants.iter().collect();
    sorted.sort_by(|a, b| a.entity_id.as_str().cmp(b.entity_id.as_str()));
    let mut hasher = blake3::Hasher::new();
    for occ in sorted {
        hasher.update(occ.entity_id.as_bytes());
        hasher.update(canonical_json_bytes(occ).as_bytes());
    }
    hasher.finalize().into()
}
```

Cached value: `NarrationText` + `generated_at_fiction_time`.

Invalidation triggers:
- Structural state change (PF_001 place.structural_state delta)
- Occupant set change (entity entry/exit at cell)
- Forge:EditCellScene.ForceLayer4Refresh
- `prompt_template_version` bump (Phase 3 S2.8 — global invalidation on prompt schema upgrade)

**V1 storage + replay-determinism caveat (Phase 3 S2.4):** cache stored in-memory at world-service (LRU eviction; not persisted aggregate). **Replay-determinism for Layer 4 is BEST-EFFORT V1** — across world-service restarts OR LRU eviction, cache loss triggers re-LLM call which may produce different prose at temperature > 0. Document V1 limitation:
- Same session window → same cache key → same narration ✓
- Cross-session OR cross-restart → cache miss → LLM re-call (different output if temp > 0) ✗

V1+ persistent cache aggregate `cell_scene_narration_cache` (CSC-D11 reservation) closes this gap. V1 acceptable since Layer 4 narration is creative-flavor, not structural; subtle prose variation across sessions doesn't break gameplay.

---

## §8 Replay-determinism

Per EVT-A9 + CSC-A1 (architectural axiom: layered determinism):

| Layer | Input determinism | Output determinism |
|---|---|---|
| L1 Skeleton | `(cell_id, place_type, manifest_overrides)` | `skeleton_id` (deterministic select) |
| L2 Procedural | `(skeleton, seed = blake3(reality_id, cell_id, structural_state, fiction_time_bucket), params)` | `(grid, fixtures, zone_catalog)` byte-identical |
| L3 LLM zones | `(zone_catalog, occupant_set, place_metadata)` | `assignments` cached per cache_key; replay reads cached value |
| L3 Canonical fallback | `(zone_catalog, occupant_set)` | deterministic algorithm |
| L4 Narration | `(place_metadata, ambient, occupants)` | `text` cached per cache_key; replay reads cached value |

**Replay semantics:**
- Same reality + same fiction_time → same `cell_scene_layout` aggregate state (Layers 1+2 + cached Layer 3 in aggregate; Layer 4 cached in memory)
- Different replay session → same Layer 1+2 output (deterministic); Layer 3+4 may re-call LLM if cache lost (rare; treated as cache miss)
- LLM model upgrades (different model id) invalidate cache (cache key includes model id)
- **Layer 4 cross-session replay-determinism is BEST-EFFORT V1 (Phase 3 S2.4):** V1 in-memory LRU cache means world-service restart OR LRU eviction loses Layer 4 narration → re-LLM call may produce different prose at temperature > 0. Acceptable V1 since narration is creative flavor (not structural); persistent cache via CSC-D11 V1+ closes the gap. Layer 1+2 strict replay-determinism + Layer 3 aggregate-cached replay-determinism are NOT affected.
- **Prompt template version (Phase 3 S2.8):** Layer 3 cache key + Layer 4 cache key both include `prompt_template_version: u32`. Bumped on Layer 3 / Layer 4 prompt schema changes that invalidate cached LLM outputs. V1 = 1; V1+ versions monotonic per I14 additive evolution.

---

## §9 Failure modes per layer + fallback chains

Each layer has bounded failure with deterministic fallback. Cell scene **always renders** V1 — no failure mode blocks UI.

| Layer | Failure | Fallback | Rule_id (if any) |
|---|---|---|---|
| L1 | skeleton_id not in registry | use `default_generic_room` template | `csc.skeleton_not_found` (logged, not returned to user) |
| L1 | PlaceType has no V1 skeleton (Wilderness/Cave/etc.) | use `default_generic_room` | `csc.placetype_no_skeleton_v1` (logged) |
| L2 | (never; algorithm always produces output — see §5.3) | n/a | — |
| L3 | LLM unreachable (network / 5xx / timeout) | canonical default assignment | (no rule_id; non-blocking) |
| L3 | LLM JSON parse fail (3 retries exhausted) | canonical default assignment | `csc.layer3_retry_exhausted` |
| L3 | LLM validator fail (3 retries exhausted) | canonical default assignment | `csc.layer3_retry_exhausted` (with last attempt's specific failure: `csc.invalid_zone_assignment` / `csc.actor_on_non_walkable` / etc.) |
| L4 | LLM unreachable / fail | no narration; UI shows fixture-list summary | (no rule_id; non-blocking) |

**Critical invariant:** if Layer 1+2 succeed (which they always do given valid skeleton registry), the cell scene renders. Layer 3+4 are quality enhancers, not blockers.

---

## §10 RealityManifest extension + `csc.*` RejectReason namespace

### 10.1 Extension to RealityManifest

```rust
pub struct RealityManifest {
    // ... existing fields ...

    // ─── CSC_001 Cell Scene Composition extension (added 2026-04-26) ───
    pub scene_skeleton_overrides: HashMap<ChannelId, SkeletonId>,  // OPTIONAL V1; per-cell author override
                                                                   // empty default → engine selects via §4.3 algorithm
}
```

### 10.2 `csc.*` RejectReason namespace V1

**Phase 3 S3.3 framing tightened:** rule_ids in this namespace fall into 2 categories — (1) **engine-internal** rule_ids (logged for ops observability; never returned to user-facing reject path; engine handles via fallback), and (2) **write-time-validator** rule_ids (rejected at LLM Layer 3 commit; trigger retry loop). The "Soft-override eligible" column is replaced with "Visibility" column for clearer intent.

| rule_id | Trigger | Vietnamese reject copy V1 | Visibility |
|---|---|---|---|
| `csc.skeleton_not_found` | `skeleton_id` not in SKELETON_REGISTRY (manifest override or runtime read) | "Mẫu khung cảnh không tồn tại." | **Engine-internal** (logged; UI falls back to default_generic_room; never returned to user) |
| `csc.invalid_zone_assignment` | Layer 3 LLM output zone_name not in catalog | "Phân vùng không hợp lệ trong gán LLM." | **Write-time validator** (retry trigger; never user-facing) |
| `csc.zone_overlap` | Two entities resolve to same TileCoord after zone resolution | "Hai đối tượng được gán cùng vị trí." | **Write-time validator** (retry trigger; never user-facing) |
| `csc.actor_on_non_walkable` | Layer 3 placement violates walkable invariant for actor entity | "Nhân vật được đặt trên ô không đi được." | **Write-time validator** (retry trigger; never user-facing) |
| `csc.item_on_non_placeable` | Layer 3 placement violates placeable invariant for item entity (item on W/P/N) | "Vật phẩm được đặt trên ô không cho phép." | **Write-time validator** (retry trigger; never user-facing) |
| `csc.entity_missing_from_assignment` | Layer 3 LLM output omits required entity_id | "Thiếu phân vùng cho đối tượng yêu cầu." | **Write-time validator** (retry trigger; never user-facing) |
| `csc.layer3_retry_exhausted` | All 3 LLM retry attempts failed; canonical fallback applied | "Tất cả lần thử LLM đều thất bại; dùng mặc định." | **Engine-internal** (logged; canonical fallback applied) |
| `csc.placetype_no_skeleton_v1` | (Phase 3 S2.3 clarified: defensive ceiling) PlaceType has no compatible skeleton AND default_generic_room compat doesn't cover the requested PlaceType. **V1: should never fire** since default_generic_room.place_type_compat covers all non-Tavern V1 PlaceTypes per §4.1; rule kept as defensive ceiling for V1+ when default_generic_room compat may shrink. | "Loại nơi này chưa có thư viện khung cảnh V1." | **Engine-internal** (logged; falls back regardless) |
| **`csc.zone_empty_fallback_used`** (Phase 3 S2.1 NEW) | Canonical default fallback chain triggered because primary hint zone is empty (Layer 2 produced 0 tiles for it); engine walks per-entity fallback chain to find non-empty alternative | "Phân vùng mặc định chuyển hướng do thiếu ô khả dụng." | **Engine-internal** (logged for ops observability; resolution still succeeds via fallback chain) |

**V1+ rule_id reservations:**
- `csc.skeleton_invalid` — V1+ author-uploaded skeleton fails template validators (uploaded via Forge V2)
- `csc.procedural_density_too_high` — V1+ ceiling check for fixture density
- `csc.narration_unsafe_content` — V1+ content moderation gate on Layer 4 output
- **`csc.layer3_occupant_set_changed`** (Phase 3 S2.2 NEW) — V1 logged-only race-detection signal; V1+ may promote to user-facing reject if author wants to surface "scene refresh deferred due to mid-call PC movement"

---

## §11 DP primitives consumed

CSC_001 implements one aggregate; no new DP-K* primitives needed.

| DP primitive | Used for | Pattern |
|---|---|---|
| `t2_read(cell_scene_layout, key=channel_id)` | UI render: get fixtures + zone_catalog + entity_zone_assignments | Hot-path on cell entry; cached per DP-K6 subscribe |
| `t2_write(cell_scene_layout, ...)` | Layer 1+2 lazy create on first cell entry; Layer 3 commit; Forge edits | Aggregate-Owner role per DP-K5 |
| `subscribe(cell_scene_layout, filter)` | UI invalidation on Layer 3 LLM completion; Forge admin live preview | DP-K6 durable subscribe |

**No new DP-K* primitives requested.** CSC_001 fits within existing kernel surface.

---

## §12 Capability JWT claims

CSC_001 declares no new top-level capability claim. Reuses existing claims:
- `produce: ["AggregateMutation", "AdminAction"]` — required for cell_scene_layout writes + Forge admin
- Per-aggregate write capability under `capabilities[]` per DP-K9 — needs `cell_scene_layout:write`

**Provider-registry routing (Phase 3 S3.2 — JWT contract specified):** Layer 3+4 LLM invocations routed through provider-registry-service per CLAUDE.md provider-gateway invariant. JWT claims required for LLM call routing:

```json
{
  "produce": [..., "LlmCall"],            // V1+ added; world-service must declare LlmCall
  "llm_call_kind": "csc.layer3_zones",     // OR "csc.layer4_narration"
  "llm_call_budget": {                     // V1+30d cost gating per CSC-D3
    "tokens_max": 8000,
    "cost_max_usd": 0.05,
    "model_allowlist": ["qwen/qwen3.6-35b-a3b", "claude-3-5-haiku", ...]
  }
}
```

V1: `LlmCall` claim + `llm_call_kind` discriminator only; budget gating reserved V1+30d (CSC-D3). Provider-registry-service validates the call, routes to user's BYOK provider per their registered config, returns response. Direct provider SDK calls from world-service are forbidden per CLAUDE.md.

**Service binding:** world-service is the canonical writer for `cell_scene_layout`.

---

## §13 Subscribe pattern

| Subscriber | Filter | Purpose |
|---|---|---|
| Frontend (player UI) | `cell_scene_layout WHERE channel_id = current_cell` | render scene; auto-update on Layer 3 completion |
| WA_003 Forge author UI | `cell_scene_layout WHERE reality_id = current` | author scene editor live preview |
| LLM AssemblePrompt (PL_005 Interaction context) | `cell_scene_layout WHERE channel_id = current_cell` | `[CELL_SCENE_CONTEXT]` section for interaction-routing prompts |
| Future MAP_002 Asset Pipeline | `cell_scene_layout WHERE skeleton_id ∈ uploaded_skeletons` | V1+ refresh after author skeleton upload |

**Validator slot considerations:** EVT-V_cell_scene runs as part of write-validator pipeline for layout mutations (Layer 3 LLM commit). Slot ordering deferred to alignment review (extends EF-Q3 + PF-Q1 + MAP-Q1; tracked as **CSC-Q2**).

---

## §14 Cross-service handoff

ChannelId is the natural identifier; cross-service serialization reuses channel-id JSON shape:

```json
{
  "channel_id": "cell:yen_vu_lau",
  "skeleton_id": "tavern_compact",
  "procedural_seed": "12345678901234567890",
  "_seed_serialization_note": "u64 procedural_seed serialized as STRING at JSON boundary per Phase 3 S1.5 — JS Number.MAX_SAFE_INTEGER ~9e15 < u64 max ~1.8e19 → integer JSON would lose precision; backend deserializes from string back to u64. Same convention applies anywhere u64 crosses to JS frontend.",
  "fixture_positions": [
    {"kind": "Counter", "position": {"x": 1, "y": 1}, "size": 1, "group_id": null},
    {"kind": "Table", "position": {"x": 4, "y": 4}, "size": 1, "group_id": 0},
    ...
  ],
  "zone_catalog": {
    "counter:on": [{"x": 1, "y": 1}, {"x": 2, "y": 1}, ...],
    "counter:behind": [{"x": 1, "y": 2}, ...],
    "table_1:seated": [{"x": 3, "y": 4}, ...],
    "...": "..."
  },
  "entity_zone_assignments": {
    "assignments": {"pc:ly_minh": "south_entry:just_inside", "npc:lao_ngu": "counter:behind", "...": "..."},
    "generated_at_fiction_time": {"...": "..."}
  },
  "layer3_source": {"LlmGenerated": {"model": "qwen/qwen3.6-35b-a3b", "attempts": 1, "...": "..."}},
  "prompt_template_version": 1,
  "last_layout_change_fiction_time": {"...": "..."}
}
```

Causality token chain: `cell_scene_layout` mutations include CausalityToken referencing the triggering EVT-T1 Submitted (PC entry) or EVT-T8 Administrative (Forge edit). Replay-determinism preserved per EVT-A9 + §8.

---

## §15 Sequences (5 V1 representative flows)

### 15.1 First PC entry to cell (lazy compute; canonical Layer 3 default)

**Phase 3 S2.6 — explicit ordering: layout creation tied to PC entry, NOT subscribe.** Subscribe is read-only per DP convention; world-service `ensure_cell_scene_layout(cell_id)` RPC fires during PL_001 §13 travel sequence (BEFORE MemberJoined emit), guaranteeing layout exists by the time frontend subscribes.

```
PC issues /travel destination=cell:yen_vu_lau (PL_002 Grammar)
  ↓ EVT-T1 Submitted PCTurn { kind: Travel } commits per PL_001 §13
  ↓ PL_001 §13 step ④: entity_binding updated per EF_001 §13
  ↓ PL_001 §13 step ⑤ (NEW per Phase 3 S2.6): ensure_cell_scene_layout(cell:yen_vu_lau)
       → world-service checks if cell_scene_layout row exists for channel_id
       → if NOT exists, lazy-create:
         L1: select_skeleton(cell:yen_vu_lau, Tavern, manifest_overrides) → "tavern_compact"
         L2: run_layer_2(tavern_compact, seed=blake3(...), ProceduralParams::default()) → grid + fixtures + zones
         L3 (canonical default): canonical_default_assignment(zone_catalog, occupants) → assignments
         L4: skipped (lazy; on-demand only V1)
       → t2_write cell_scene_layout { skeleton_id, seed, params, fixtures, zone_catalog, entity_zone_assignments=Some(canonical), layer3_source=CanonicalDefault, prompt_template_version=1 }
       → emit EVT-T4 System SceneLayoutBorn { channel_id, skeleton_id, procedural_seed }
  ↓ PL_001 §13 step ⑥: DP emits MemberJoined for cell channel
  ↓ Frontend subscribes cell_scene_layout WHERE channel_id=cell:yen_vu_lau
  ↓ row already exists (created in step ⑤); subscribe responds with full data
  ↓ Frontend renders scene with canonical entity placement
```

This eager-create-on-PC-entry pattern eliminates the subscribe-trigger ambiguity from prior draft. See §15.6 below for the corresponding lazy-cell-flow update at PL_001b §16.3 (Phase 3 S2.5).

### 15.2 LLM-augmented Layer 3 (after canonical default)

```
[Continuing 15.1 — scene rendered with canonical defaults]
  ↓ Frontend (or world-service background) issues Layer 3 LLM call:
    L3 LLM: build_prompt(zone_catalog, occupants, place_metadata) → Qwen 3.6 35B-A3B
    L3 retry loop: max 3 attempts; each attempt validators
    On success (typically attempt 1):
      ↓ t2_write cell_scene_layout { entity_zone_assignments=Some(llm_output), layer3_source=LlmGenerated{...} }
      ↓ emit EVT-T3 Derived { aggregate_type: cell_scene_layout, delta: { entity_zone_assignments, layer3_source } }
    On all-retries-fail:
      ↓ canonical fallback already in place (from 15.1); no write needed
      ↓ log csc.layer3_retry_exhausted
  ↓ Frontend re-renders if assignments changed (subscribers receive delta)
```

### 15.3 Layer 4 narration on demand

```
PC issues "describe scene" command (PL_002 /describe or implicit on cell entry)
  ↓ world-service Layer 4 LLM call:
    build_layer_4_prompt(place_metadata, ambient, occupants) → Qwen 3.6 35B-A3B
    On success: NarrationText cached at world-service in-memory LRU
    On fail: no narration; UI shows fixture-list summary fallback
  ↓ Frontend receives narration text in scene description panel
```

### 15.4 Author-edit cell scene via Forge

```
Author issues Forge:EditCellScene { channel_id: cell:yen_vu_lau, edit_kind: RerollSeed, before: { seed: 12345 }, after: { seed: 67890 } }
  ↓ EVT-T8 Administrative Forge:EditCellScene commits
  ↓ WA_003 Forge atomic transaction:
    - re-run L2 with new seed → new fixtures + zones
    - invalidate Layer 3 cache (re-canonical-default; LLM re-call deferred to next read)
    - invalidate Layer 4 cache
    - t2_write cell_scene_layout { procedural_seed=67890, fixture_positions=new, zone_catalog=new, entity_zone_assignments=canonical-default, layer3_source=CanonicalDefault }
    - emit EVT-T3 Derived
    - emit ForgeEdit audit log (forge_audit_log per WA_003)
  ↓ Frontend subscribers receive update; scene re-renders
```

### 15.5 Replay determinism — same reality clone produces identical layout

```
Reality clone: r_tien_nghich_001 → r_tien_nghich_002 (snapshot fork per MV12)
  ↓ both realities query cell_scene_layout for cell:yen_vu_lau at same fiction_time:
    L1 selects skeleton: same hash(cell_id) → same skeleton_id ✓
    L2 procedural: same seed = blake3(reality_id ?, cell_id, structural_state, fiction_time_bucket)
      ┃ NOTE: seed includes reality_id → DIFFERENT realities have DIFFERENT seeds intentionally
      ┃ For replay-within-same-reality: same seed → same fixtures ✓
      ┃ For clone-comparison: different reality_id → different layouts (intentional; per-reality variety)
    L3 canonical default: deterministic algorithm; same occupants → same assignments
    L4 narration: cached per (channel_id, place_metadata, ambient, occupants); LLM re-called on cache miss only
```

---

## §16 Acceptance criteria

10 V1-testable scenarios (AC-CSC-1..10):

1. **AC-CSC-1 — Skeleton fallback on unknown id:** writing `cell_scene_layout { skeleton_id: "nonexistent_template" }` runtime → engine logs `csc.skeleton_not_found` and returns `default_generic_room` rendering. Cell still renders; no user-facing error. Tests §4.3 + §9.

2. **AC-CSC-2 — Layer 2 deterministic:** running `run_layer_2(skeleton=tavern_compact, seed=12345, params=defaults)` twice produces byte-identical `(grid, fixtures, zone_catalog)`. Tests §5.2 + §8 replay invariant.

3. **AC-CSC-3 — Canonical Layer 3 default always succeeds (incl. degenerate empty-zone case per Phase 3 S2.1):** for any (skeleton, fixtures) pair INCLUDING degenerate cases where Layer 2 produces empty `counter:on` / `table_X:on` zones (e.g., counter zone too small in skeleton design), `canonical_default_assignment(request, zone_catalog)` walks the per-entity fallback chain (§6.5 `fallback_chain_for`) and returns assignments where every entity resolves to a tile passing its `placement_constraint` (Walkable for actors / Placeable for items). No overlap. **Test variants:** (a) normal Tavern with all zones populated → primary hints used; (b) degenerate skeleton with counter_zone_too_small → tea_pot falls through to table_1:on; (c) extreme degenerate where ALL fixture zones empty → all entities resolve to center_floor:open (last-resort guarantee). Tests §6.5 + Phase 3 S2.1 fallback chain.

4. **AC-CSC-4 — Layer 3 LLM success path:** LLM (Qwen 3.6 35B-A3B per v4 demo evidence) returns valid JSON in attempt 1; all 4 validators pass; assignments commit to aggregate. Tests §6.1-§6.3 + §6.4 happy path.

5. **AC-CSC-5 — Layer 3 retry recovery:** LLM attempt 1 produces invalid_zone_assignment (zone not in catalog); attempt 2 with feedback message produces valid assignment. Cell renders with attempt-2 result. `layer3_source.attempts = 2`. Tests §6.4 retry loop.

6. **AC-CSC-6 — Layer 3 retry exhaustion → fallback:** LLM 3 retries all fail (e.g., persistent JSON parse failure); engine applies canonical default; logs `csc.layer3_retry_exhausted`; cell renders with canonical placement. Tests §9 fallback chain.

7. **AC-CSC-7 — Layer 4 narration cache + occupant invalidation (Phase 3 S3.5 expanded):** **(a)** first Layer 4 LLM call returns text; subsequent reads with same `(cell, scene_state, occupants, prompt_template_version)` return cached value (no LLM call) — observable via call counter at provider-registry-service. **(b)** entity entry/exit at cell → occupant_set_hash changes → cache miss → next read triggers re-LLM. **(c)** prompt_template_version bump (V1+ schema upgrade) → all caches invalidated globally. **(d)** in-memory LRU eviction → cache miss → re-LLM (acceptable per §7.4 V1 limitation). Tests §7.4 cache_key_layer_4 + Phase 3 S2.4 + S2.8.

8. **AC-CSC-8 — Replay-determinism per EVT-A9:** same `(reality_id, cell_id, structural_state, fiction_time_bucket)` inputs produce identical Layer 2 output across separate sessions. Replay reads cached Layer 3 + Layer 4 verbatim. Tests §8.

9. **AC-CSC-9 — Forge:EditCellScene atomic transaction:** Forge:EditCellScene executes 3 writes in a single Postgres transaction: (a) update cell_scene_layout row, (b) emit EVT-T8 Administrative, (c) append to forge_audit_log. Mid-transaction failure → all 3 rollback. Tests §15.4 + WA_003 integration (mirror EF/PF/MAP atomicity ACs).

10. **AC-CSC-10 — Non-Tavern PlaceType renders via default_generic_room:** PlaceType `Wilderness` cell attempts to load → engine selects `default_generic_room` template (no Tavern-compatible templates fit Wilderness V1; default_generic_room.place_type_compat covers all non-Tavern V1 PlaceTypes per Phase 3 S3.4). Cell renders with door + open floor + canonical entity placements. **Phase 3 S2.3:** `csc.placetype_no_skeleton_v1` rule does NOT fire here (default_generic_room compat covers Wilderness); rule remains for defensive ceiling V1+. Tests §4.3 + §3.4 V1+ PlaceType extension semantics + §9.

11. **AC-CSC-11 — PC race condition during async Layer 3 call (Phase 3 S2.2 — NEW):** PC enters cell → ensure_cell_scene_layout creates row with canonical defaults; Layer 3 LLM call invoked async with occupant_snapshot_hash captured. **(a)** Mid-LLM-call, PC `/travel` to different cell → entity_binding updated; original cell occupant set hash changes. **(b)** LLM completes, world-service compares current occupant_set_hash to snapshot → mismatch detected → write aborted, log `csc.layer3_occupant_set_changed` (V1 logged-only). **(c)** Original cell renders with canonical default Layer 3 (from initial lazy-create). **(d)** When some other PC re-enters original cell, Layer 3 re-invoked with fresh occupants. Tests §6.4 race policy + Phase 3 S2.2.

---

## §17 Deferrals

| ID | What | Why deferred | Target phase |
|---|---|---|---|
| **CSC-D1** | V1+ skeleton libraries for non-Tavern PlaceTypes (Residence/Marketplace/Temple/Workshop/OfficialHall/etc.) | V1 Tavern only (3 templates) + default_generic_room fallback covers structural V1 needs | V1+30d per-PlaceType libraries (~3-5 templates each) |
| **CSC-D2** | V1+ procedural decorations (carpets, candles, ambient props beyond fixtures) | V1 fixtures-only suffices for SPIKE_01 grounding | V1+ ambient enhancement feature |
| **CSC-D3** | V1+30d Layer 3 LLM cost gating per usage-billing-service | V1 LLM calls free-of-cost-gating (assumes self-hosted LM Studio); V1+ cost tracking when production billing lands | V1+30d billing integration |
| **CSC-D4** | V1+ Layer 4 narration freshness refresh (per-turn or scheduled regenerate) | V1 narration cached forever per cache_key; V1+ scheduled freshness for ambient drift over fiction-time | V1+30d scheduler + narration feature |
| **CSC-D5** | V1+ author skeleton uploads via Forge V2 (custom templates) | V1 hand-authored static registry only; V1+ Forge V2 visual skeleton editor + S3 storage | V1+ MAP_002 asset pipeline + Forge V2 |
| **CSC-D6** | V1+ multi-cell layout (apartment building cells share structure) | V1 each cell independent; V1+ if author content needs apartment-style hierarchy | V1+ multi-place-per-cell (PF-D4 dependency) |
| **CSC-D7** | V1+ animated entity transitions (visual smoothness) | V1 instant-snap rendering; V1+ frontend animation feature | V1+ frontend rendering V2 |
| **CSC-D8** | V1+ tactical features (line-of-sight, cover, range modifiers for Strike) | V1 no spatial gameplay V1; V1+ if combat / stealth features designed | V1+ tactical-combat feature |
| **CSC-D9** | V1+ Forge skeleton editor UI (visual editor for hand-authoring templates) | V1 templates in code/JSON config; V1+ Forge UI for non-programmer authors | V1+ Forge V2 |
| **CSC-D10** | V2+ procedural narration (LLM generates per-turn ambient updates beyond initial scene description) | V1 single narration per scene-state; V2+ live ambient narration feed | V2+ narration feature |
| **CSC-D11** | V1+ persistent `cell_scene_narration_cache` aggregate | V1 in-memory LRU at world-service; V1+ persistent cache for cross-session reuse + audit | V1+30d if narration cost profiling shows benefit |
| **CSC-D12** | V1+ TVL_001 Travel Mechanics within-cell PC movement | V1 PC at fixed position post-arrival; V1+ if click-to-move within cell needed | V1+ TVL_001 design (CSC-Q1 watchpoint) |
| **CSC-D13** | V2+ multi-locale narration (en V1+; ja/zh V2+) | V1 vi only; LocalizedName framework V1+ unified at 00_foundation | V1+ when more shared schemas adopt LocalizedName |

---

## §18 Cross-references

- **PF_001 Place Foundation** — reads `place.place_type` for skeleton selection (§4.3); reads `place.fixture_seed` for skeleton compatibility hints (V1+ alignment); cell-tier composition flow per PF_001 §3.1 (entity_binding location.InCell{cell_id} = CSC channel_id).
- **EF_001 Entity Foundation** — reads `entity_binding WHERE cell_id` for occupant list (Layer 3+4 input); writes do not modify entity positions (CSC owns visual placement at cell-internal grid; entity_binding owns location.InCell at logical level).
- **MAP_001 Map Foundation** — cell-tier composition: MAP_001 owns visual position within parent town viewport; CSC_001 owns within-cell 16×16 layout. CSC reads `map_layout.background_asset` if set (V1+ render under cell scene).
- **PL_001 Continuum** — reads `scene_state.ambient` for Layer 4 narration input; lazy-cell creation flow per PL_001b §16.3 must also create `cell_scene_layout` row (mirrors PF_001 + MAP_001 lazy-cell pattern). **PL_001b §16.3 needs minor reopen to add CSC lazy creation** (folded into this commit).
- **PL_002 Grammar** — `/describe` command (V1+ optional) triggers Layer 4 narration call.
- **PL_005 Interaction** — cell scene UI is the consumer; click entity → action menu → InteractionKind. CSC provides entity positions; PL_005 owns interaction logic.
- **PL_006 Status Effects** — actor_status displayed in cell scene UI sidebar (PC stats panel); CSC reads `actor_status WHERE actor_id IN cell_occupants`.
- **NPC_001 Cast** — reads `npc.mood` + persona for Layer 3+4 occupant context.
- **NPC_002 Chorus** — V1+ multi-NPC reaction scenes consume cell scene state.
- **PCS_001** (when designed) — PC spawn cell triggers `cell_scene_layout` lazy creation; PC body description feeds Layer 4 narration.
- **WA_001 Lex** — V1+ Lex axioms may inform Layer 3 placement (e.g., "scholars must be near books"); V1 Layer 3 prompt agnostic.
- **WA_002 Heresy** — V1+ if per-place contamination affects scene appearance; V1 not.
- **WA_003 Forge** — `Forge:EditCellScene` AdminAction sub-shape registered (§2.5 + §15.4).
- **07_event_model** — EVT-T4 SceneLayoutBorn + EVT-T3 `aggregate_type=cell_scene_layout` + EVT-T8 Forge:EditCellScene registered.
- **06_data_plane** — `cell_scene_layout` aggregate sits in T2/Channel-cell scope per existing DP contract. No new primitives.
- **provider-registry-service** (existing service per CLAUDE.md) — Layer 3+4 LLM calls routed through provider gateway invariant (BYOK; no direct provider SDK calls).

---

## §19 Readiness checklist

- [x] Domain concepts table covers SkeletonId / SkeletonTemplate / ZoneBounds / ProceduralSeed / FixturePosition / FixtureKind / ZoneCatalog / EntityZoneAssignment / Layer3Source / NarrationText / TileCoord / PlaceMetadata / AmbientState / OccupantSummary
- [x] Aggregate inventory: 1 aggregate (`cell_scene_layout` primary; T2/Channel-cell scope)
- [x] 4-layer architecture documented §4-§7 (skeleton + procedural + LLM-zones + narration); each layer's contract + failure mode
- [x] V1 skeleton registry: 3 Tavern templates + 1 default_generic_room fallback
- [x] V1 procedural placer: 5 fixture kinds (Counter / Table / Chair / Fireplace / Window); deterministic per blake3 seed
- [x] LLM Layer 3: JSON contract + 4 validators + 3-attempt retry loop + canonical fallback
- [x] LLM Layer 4: free-form Vietnamese prose + cache strategy + non-blocking failure
- [x] Replay-determinism §8: layered seed + cache key strategy
- [x] Failure modes §9: 4 layers × bounded fallback chains; cell scene always renders
- [x] RealityManifest extension `scene_skeleton_overrides` (optional V1; per-cell override)
- [x] Reference safety policy: **9 V1 rule_ids** in `csc.*` namespace (Phase 3 cleanup added `zone_empty_fallback_used` per S2.1) + 4 V1+ reservations (added `layer3_occupant_set_changed` per S2.2)
- [x] Event-model mapping: EVT-T4 SceneLayoutBorn + EVT-T3 aggregate_type=cell_scene_layout + EVT-T8 Forge:EditCellScene; no new EVT-T*
- [x] DP primitives: existing surface only (no new DP-K*)
- [x] Capability JWT: existing claims (no new top-level)
- [x] Subscribe pattern: 4 subscribers V1
- [x] Cross-service handoff: ChannelId JSON shape
- [x] 5 representative sequences (lazy first entry / LLM-augmented Layer 3 / Layer 4 on demand / Forge edit / replay-determinism)
- [x] **11 V1-testable acceptance scenarios** (AC-CSC-1..11; Phase 3 cleanup added AC-CSC-11 for PC race condition; AC-CSC-3 + AC-CSC-7 expanded with multi-variant tests for empty-zone fallback + cache invalidation)
- [x] 13 deferrals (CSC-D1..D13) with target phases
- [x] Cross-references to all 14 affected features + foundation docs
- [x] v3→v4 demo evidence cited as design grounding (token economy, architectural pivot rationale)
- [x] Phase 3 review cleanup applied 2026-04-26 (Severity 1+2+3 — 13 fixes — typed zone_catalog · clamp arg order · blake3 explicit · ChaCha8Rng explicit · u64 JSON string-serialize · empty-zone fallback chain + new csc.zone_empty_fallback_used · PC race condition policy + csc.layer3_occupant_set_changed reservation · placetype_no_skeleton_v1 defensive clarification · Layer 4 best-effort replay-determinism · PL_001b §16.3 lazy cell_scene_layout creation · ensure_cell_scene_layout RPC ordering · ProceduralParams V1 defaults · prompt_template_version cache key · occupant_set_hash canonical algorithm · provider-registry JWT contract · RejectReason visibility framing · V1+ PlaceType extension fallback · 3 AC additions/expansions)
- [ ] CANDIDATE-LOCK pending closure pass + downstream updates

---

## §20 Open questions (post-DRAFT)

| ID | Question | Resolution path |
|---|---|---|
| **CSC-Q1** | V1+ TVL_001 integration — does PC move within cell after arrival? If so, position update mechanic + Layer 3 invalidation rules | TVL_001 design + V1+ within-cell movement feature; CSC-D12 reservation tracks |
| **CSC-Q2** | Validator slot ordering: EVT-V_cell_scene relative to EVT-V_map_layout / EVT-V_place_structural / EVT-V_entity_affordance / EVT-V_lex (extends EF-Q3 + PF-Q1 + MAP-Q1) | `_boundaries/03_validator_pipeline_slots.md` alignment review (single pass for all 4 watchpoints) |
| **CSC-Q3** | Layer 4 narration multi-locale — V1 vi only; how do en/ja/zh layers compose? Per-locale LLM call or single call multi-locale output? | V1+ LocalizedName cleanup pass + per-locale narration feature |
| **CSC-Q4** | Layer 3 fallback caching — should canonical default be cached or recomputed each read? | V1: recompute (fast deterministic algorithm); V1+ cache if profiling shows pain |
| **CSC-Q5** | Per-PlaceType fixture density tuning — Tavern busy vs Wilderness sparse should have different default `procedural_params.density` | V1+ per-PlaceType default param sets; V1 single global default applies |
