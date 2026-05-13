# TMP_004 — Template Authoring

> **Conversational name:** "Templates" (TMP-TPL). The schema authors use to describe what kind of tilemap they want generated.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **CANDIDATE-LOCK 2026-05-13** (DRAFT 2026-05-13 → revised 2026-05-13 for license-hygiene framing → CANDIDATE-LOCK closure pass: TMP-TPL-Q1..Q5 RESOLVED at §10)
> **Owns:** TMP-2 + TMP-15 + TMP-16 + TMP-17 + TMP-30 catalog entries

---

## §1 What a template is

A `TilemapTemplate` aggregate is **author intent for a procedurally-generated tilemap**. It declares:

- Which **zones** exist (size, role, terrain, treasure tiers, monster strength, town hints)
- How zones **connect** (Threshold passage, Open passage, Portal pair, etc.)
- Global **constraints** (banned monsters, banned artifacts, banned terrains, water content)
- Inheritance shortcuts (`inherit_*_from` fields) so symmetric templates don't bloat
- Biome selection rules (per template; engine defaults override-able by author)

One reality can have multiple templates (e.g., a different template per `ChannelTier`, or genre-specific templates like "wuxia continent" vs "steampunk country"). RealityManifest specifies which template applies to which tier.

The template pattern is genre-standard. Most procedural map generators in the prior art (HoMM3, Caves of Qud, Wesnoth, Dwarf Fortress, Civ V/VI) accept some form of author template declaring zones + constraints + density tuning. See §10 Prior Art for specific references.

---

## §2 Schema

Full `TilemapTemplate` schema. This is the authoritative shape — RealityManifest references templates by `template_id`; `tilemap_view` consumes templates at generation time.

```rust
#[derive(Aggregate, Serialize, Deserialize)]
#[dp(type_name = "tilemap_template", tier = "T2", scope = "reality")]
pub struct TilemapTemplate {
    pub template_id: TilemapTemplateId,
    pub name: String,                                     // e.g. "Wuxia Continent V1"
    pub description: String,                              // freeform author notes
    pub author_canon_ref: Option<BookCanonRef>,           // optional book-canon hint
    pub applicable_tiers: BTreeSet<ChannelTier>,          // which tiers this template applies to
    pub default_grid_size: GridSize,                      // when applied to a channel
    pub min_zones: u32,                                   // hard lower bound
    pub max_zones: u32,                                   // hard upper bound
    pub players_range: Option<(u32, u32)>,                // (min, max) — V2+ multiplayer; V1+30d ignored
    pub humans_range: Option<(u32, u32)>,                 // V2+

    pub zones: BTreeMap<ZoneId, ZoneSpec>,                // zone-by-zone specs
    pub connections: Vec<ZoneEdgeSpec>,                   // edges between zones
    pub biome_selection_rules: BiomeSelectionRules,       // author-tunable obstacle-set composition; see TMP_005 §2

    pub allowed_water_content: BTreeSet<WaterContent>,    // None | Normal | Islands
    pub banned_terrain_kinds: BTreeSet<TerrainKind>,
    pub banned_monsters: BTreeSet<FactionId>,             // V2 monster faction ban
    pub banned_artifacts: BTreeSet<ArtifactId>,           // V2 — RES_001 integration
    pub banned_spells: BTreeSet<SpellId>,                 // V2 — magic system
    pub enabled_heroes: BTreeSet<HeroId>,                 // V2 — explicit allow-list

    pub schema_version: u32,                              // for V1+30d additive-only evolution (TMP-A8)
    pub last_change_fiction_time: FictionTime,
}

pub struct ZoneSpec {
    pub zone_id: ZoneId,
    pub zone_role: ZoneRole,                              // see §2.1 — Wilderness/Hub/Forbidden/Sea (V1+30d)
    pub size: u32,                                        // relative weight (typical range 4-12)

    pub owner: Option<PlayerId>,                          // V2+ multiplayer (player faction); V1+30d: None
    pub forced_level: ForcedLevel,                        // Automatic | Surface | Underground (V3+ Underground)

    pub player_towns: TownInfo,                           // # castles + # towns + densities
    pub neutral_towns: TownInfo,
    pub match_terrain_to_town: bool,                      // pick terrain matching town's native faction
    pub towns_are_same_type: bool,                        // all towns in zone = same faction
    pub town_hints: Vec<TownHint>,                        // per-town hints

    pub terrain_types: BTreeSet<TerrainKind>,             // allowed terrains; empty = all
    pub banned_terrains: BTreeSet<TerrainKind>,           // override-ban on top of template-level ban

    pub allowed_monsters: BTreeSet<FactionId>,            // V2 monster faction allow-list
    pub banned_monsters: BTreeSet<FactionId>,
    pub allowed_towns: BTreeSet<FactionId>,
    pub banned_towns: BTreeSet<FactionId>,
    pub monster_strength: MonsterStrength,                // Weak | Normal | Strong | None

    pub mines: BTreeMap<ResourceKind, u16>,               // obligatory mines (e.g. {wood: 1, ore: 1, ...})
    pub treasure_tiers: Vec<TreasureTierSpec>,            // {min, max, density} per tier
    pub max_treasure_value: u32,                          // computed cap

    pub custom_objects: ObjectConfig,                     // V2 custom required/banned objects
    pub connected_zone_ids: Vec<ZoneId>,                  // denormalized from connections[]

    pub visible_position: (f32, f32),                     // V3+ Forge editor preview position
    pub visible_size: f32,                                // V3+ Forge editor preview size

    pub narrative_hint: Option<String>,                   // optional author-supplied narrative seed for L4 LLM narration

    // INHERITANCE SHORTCUTS — see §3 below
    pub inherit_towns_from: Option<ZoneId>,
    pub inherit_mines_from: Option<ZoneId>,
    pub inherit_terrain_from: Option<ZoneId>,
    pub inherit_treasure_from: Option<ZoneId>,
    pub inherit_custom_objects_from: Option<ZoneId>,
}

pub struct ZoneEdgeSpec {
    pub edge_id: u32,                                     // unique within template
    pub zone_a: ZoneId,
    pub zone_b: ZoneId,
    pub kind: PassageKind,                                // see §2.2 — Threshold/Open/Hint/Adversarial/Portal
    pub guard_strength: u32,                              // monster guard strength (0 = no guard)
    pub road: RoadOption,                                 // True | False | Random
}

pub enum WaterContent { None, Normal, Islands }           // 3 variants
pub enum ForcedLevel { Automatic, Surface, Underground }  // V1+30d active: Automatic + Surface; V3 adds Underground
pub enum MonsterStrength { Weak, Normal, Strong, None }   // None = no monsters in zone

pub struct TreasureTierSpec {
    pub min: u32,                                         // min pile value
    pub max: u32,                                         // max pile value
    pub density: u16,                                     // piles per zone-tile-thousand
}

pub struct TownInfo {
    pub town_count: u32,
    pub castle_count: u32,                                // castle = main town with fort; town = secondary
    pub town_density: u32,                                // 1-10 spacing factor
    pub castle_density: u32,
}

pub struct TownHint {
    pub like_zone: Option<ZoneId>,                        // copy town faction from another zone
    pub not_like_zone: Vec<ZoneId>,                       // exclude another zone's faction
    pub related_to_zone_terrain: Option<ZoneId>,          // pick faction whose native terrain matches another zone
}

pub enum RoadOption { True, False, Random }               // "Random" pre-resolved during finalization
```

### 2.1 ZoneRole enum

Per TMP_001 §2.1. V1+30d 4 variants:

| Variant | Meaning |
|---|---|
| `Wilderness` | Exploration zone; treasure piles + monster guards; no main town. The default zone role. |
| `Hub` | Crossroads zone; not fractalized; single straight path through. Connects multiple regions. |
| `Forbidden` | Completely blocked; only enterable via Portal-kind passage. For dimensional / locked regions. |
| `Sea` | Water zone; one per tilemap maximum. |

V2+ adds `AllyHome` + `RivalHome` (TMP-D12 reservation) for multiplayer scenarios with player factions.

### 2.2 PassageKind enum

Per TMP_001 §2.2:

| Variant | Behavior |
|---|---|
| `Threshold` | Default; monster guard at passage + road connecting zones |
| `Open` | Free passage; no guard; zones share a wide border |
| `Hint` | Placement hint only (no physical passage; zones are "logically connected" but not traversable; influences placement spatial reasoning) |
| `Adversarial` | Push zones apart (negative attraction); for "rival kingdoms" feel |
| `Portal` | Always monolith pair, even if zones share border |

---

## §3 Inheritance fields

ZoneSpec inheritance keeps templates DRY:

- `inherit_towns_from: Option<ZoneId>` — use same town faction + count as referenced zone
- `inherit_mines_from: Option<ZoneId>` — same mines config
- `inherit_terrain_from: Option<ZoneId>` — same allowed terrain types
- `inherit_treasure_from: Option<ZoneId>` — same treasure tiers
- `inherit_custom_objects_from: Option<ZoneId>` — same banned/required objects

Example template fragment (symmetric 2-player setup):
```json
{
  "zones": {
    "1": {
      "zone_role": "wilderness",
      "size": 8,
      "owner": 1,
      "player_towns": { "castles": 1 },
      "neutral_towns": { "towns": 1 },
      "mines": { "wood": 1, "mercury": 1, "ore": 1 },
      "treasure_tiers": [
        { "min": 1000, "max": 2100, "density": 4 },
        { "min": 3500, "max": 4900, "density": 7 }
      ]
    },
    "2": {
      "zone_role": "wilderness",
      "size": 8,
      "owner": 2,
      "player_towns": { "castles": 1 },
      "neutral_towns": { "towns": 1 },
      "inherit_mines_from": 1,
      "inherit_treasure_from": 1
    }
  }
}
```

Zone 2 inherits mines + treasure from zone 1. Author writes the full spec once.

### 3.1 Inheritance resolution

```
After template is loaded but before generation starts:

1. Detect cycles in inheritance graph (e.g., zone 1 → inherit_treasure_from → zone 2 → inherit_treasure_from → zone 1):
   - emit `tilemap.inherit_cycle` if found; reject template

2. Resolve inheritance via fixpoint iteration (depth-first, memoized):
   FOR each zone X:
     FOR each inheritance field (towns / mines / terrain / treasure / custom_objects):
       IF X.inherit_X_from is Some(Y):
         resolve Y first (recurse), then copy Y's resolved value into X

3. Verify resolved values are valid:
   - mines: every resource_kind is recognized
   - terrain: every terrain_kind is valid for level
   - treasure: density > 0; min <= max
```

Cycle detection uses standard graph algorithm (Tarjan 1972 strongly-connected components, or simple recursion with visited-set).

### 3.2 Inheritance is NOT prototype chaining at runtime

Once resolved, inheritance is **frozen into the template**. Generation reads resolved values. This means:
- Author edits zone 1's treasure tiers via Forge → zone 2's treasure stays unchanged
- Forge UI can show "this zone's mines inherited from zone 1" as a UI hint (non-destructive resolve preview)

V2+ might add live-inheritance (zone 2 always tracks zone 1; edits propagate). V1+30d: static-resolve.

### 3.3 Town hints (more nuanced inheritance)

`TownHint` is per-town within a zone (not whole-zone-level):

```rust
pub struct TownHint {
    pub like_zone: Option<ZoneId>,            // this town has same faction as town in zone Y
    pub not_like_zone: Vec<ZoneId>,           // this town faction != any town faction in zones X..Z
    pub related_to_zone_terrain: Option<ZoneId>, // pick faction whose native terrain matches zone Y's terrain
}
```

Example: zone 5 has 2 towns; town 1 like_zone=3 (matches faction of zone 3's town), town 2 not_like_zone=[1,2,3] (different from player zones).

Used by TownPlacer modificator (V2 active). V1+30d: TownPlacer is no-op (MAP_001 supplies positions); town hints are schema-reserved.

---

## §4 Connection schema

```rust
pub struct ZoneEdgeSpec {
    pub edge_id: u32,
    pub zone_a: ZoneId,
    pub zone_b: ZoneId,
    pub kind: PassageKind,
    pub guard_strength: u32,                              // 0 = no guard; >0 = monster strength
    pub road: RoadOption,                                 // True | False | Random
}
```

JSON example:
```json
"connections": [
  { "edge_id": 1, "zone_a": "1", "zone_b": "6", "guard_strength": 5000, "kind": "threshold", "road": "true" },
  { "edge_id": 2, "zone_a": "1", "zone_b": "7", "guard_strength": 5000, "kind": "threshold", "road": "true" },
  { "edge_id": 3, "zone_a": "3", "zone_b": "4", "guard_strength": 0, "kind": "open", "road": "false" },
  { "edge_id": 4, "zone_a": "5", "zone_b": "10", "guard_strength": 14000, "kind": "portal", "road": "false" }
]
```

`road: "random"` is **pre-resolved** at finalization. A random subset of `road: random` connections become roaded; remainder become unroaded. Done deterministically from seed. Reason: keep zones from being over-connected by roads (visual clutter).

`kind: "open"` connections never have roads (open border doesn't need a single road).

---

## §5 Schema-additive evolution (TMP-A8)

V1+30d → V2 → V3 must respect: **no field removal; no field type change; only additive**.

Allowed:
- Add new optional field to ZoneSpec (e.g., V2 add `narrative_hint: Option<String>` ← already present V1+30d for L4 reservation)
- Add new variant to enum (e.g., V2 add `RoadKind::Trade` to existing 2 variants)
- Increase max value of existing field (e.g., grid_size cap 1024×1024 → V2 4096×4096)

Forbidden (without schema migration):
- Remove field
- Change field type (e.g., `size: u32` → `size: f32`)
- Rename field
- Remove enum variant (mark `_withdrawn` instead)

Breaking changes require new `template_kind`. V1+30d ships `TilemapTemplateV1`; V3 RMG wizard might introduce `TilemapTemplateV3` with different shape — both coexist; per-template choice.

`schema_version` field auto-increments on Forge:EditTemplate; clients verify schema compatibility on read.

---

## §6 Engine defaults (`tilemap_defaults`)

When RealityManifest doesn't specify a `tilemap_template` for a tier, engine uses defaults. Pseudo-config:

```rust
pub struct TilemapDefaults {
    pub grid_size_per_tier: HashMap<ChannelTier, GridSize>,
    pub default_template_per_tier: HashMap<ChannelTier, TilemapTemplateRef>,
    pub default_water_content: WaterContent,
    pub default_monster_strength: MonsterStrength,
    pub llm_enabled: bool,
    pub single_thread: bool,
    pub skip_tier: BTreeSet<ChannelTier>,
    pub generation_timeout_seconds: u32,                  // default 30
    pub force_directed_max_iterations: u32,               // default 1000
    pub force_directed_max_wall_clock_seconds: u32,       // default 5
}

impl Default for TilemapDefaults {
    fn default() -> Self {
        let mut grid_size_per_tier = HashMap::new();
        grid_size_per_tier.insert(ChannelTier::Continent, GridSize { width: 256, height: 256 });
        grid_size_per_tier.insert(ChannelTier::Country,   GridSize { width: 192, height: 192 });
        grid_size_per_tier.insert(ChannelTier::District,  GridSize { width: 128, height: 128 });
        grid_size_per_tier.insert(ChannelTier::Town,      GridSize { width: 64,  height: 64  });

        Self {
            grid_size_per_tier,
            default_template_per_tier: HashMap::new(),     // empty = use engine canonical defaults per tier
            default_water_content: WaterContent::None,
            default_monster_strength: MonsterStrength::Normal,
            llm_enabled: false,                            // V1+30d default OFF; V2 ON
            single_thread: false,                          // V1+30d default parallel
            skip_tier: BTreeSet::new(),
            generation_timeout_seconds: 30,
            force_directed_max_iterations: 1000,
            force_directed_max_wall_clock_seconds: 5,
        }
    }
}
```

Engine ships with canonical default templates (1 per tier) bundled in code. Authors can override via Forge:EditTemplate.

---

## §7 Example template (LoreWeave-styled wuxia continent)

```json
{
  "template_id": "wuxia_continent_v1",
  "name": "Wuxia Continent (V1)",
  "description": "Standard wuxia continent: 1 central hub + 4 neighboring kingdoms + 4 wilderness zones + 1 sealed forbidden land + 1 water lake",
  "applicable_tiers": ["continent"],
  "default_grid_size": { "width": 256, "height": 256 },
  "min_zones": 8,
  "max_zones": 8,
  "zones": {
    "1": {
      "zone_id": 1,
      "zone_role": "wilderness",
      "size": 12,
      "match_terrain_to_town": false,
      "terrain_types": ["grass", "forest"],
      "monster_strength": "normal",
      "treasure_tiers": [
        { "min": 100, "max": 800,  "density": 4 },
        { "min": 1500, "max": 3000, "density": 6 }
      ],
      "mines": { "wood": 2, "ore": 1 },
      "narrative_hint": "ancestral homeland of Lotus Sect lay disciples"
    },
    "2": {
      "zone_id": 2,
      "zone_role": "wilderness",
      "size": 10,
      "terrain_types": ["mountain", "snow"],
      "monster_strength": "strong",
      "treasure_tiers": [
        { "min": 3000, "max": 5000, "density": 3 },
        { "min": 8000, "max": 12000, "density": 5 }
      ],
      "mines": { "gem": 1, "mercury": 1 },
      "narrative_hint": "lost cultivation grounds of Diamond Sect"
    },
    "3": {
      "zone_id": 3,
      "zone_role": "wilderness",
      "size": 8,
      "terrain_types": ["sand", "rough"],
      "monster_strength": "normal",
      "inherit_treasure_from": 1,
      "inherit_mines_from": 1
    },
    "4": {
      "zone_id": 4,
      "zone_role": "wilderness",
      "size": 8,
      "inherit_terrain_from": 1,
      "inherit_treasure_from": 1
    },
    "5": {
      "zone_id": 5,
      "zone_role": "wilderness",
      "size": 6,
      "terrain_types": ["forest", "swamp"],
      "monster_strength": "strong",
      "treasure_tiers": [
        { "min": 5000, "max": 8000, "density": 8 }
      ]
    },
    "6": {
      "zone_id": 6,
      "zone_role": "forbidden",
      "size": 4,
      "terrain_types": ["rough"]
    },
    "7": {
      "zone_id": 7,
      "zone_role": "hub",
      "size": 3,
      "terrain_types": ["grass"]
    },
    "8": {
      "zone_id": 8,
      "zone_role": "sea",
      "size": 5
    }
  },
  "connections": [
    { "edge_id": 1, "zone_a": 1, "zone_b": 7, "kind": "open", "guard_strength": 0, "road": "true" },
    { "edge_id": 2, "zone_a": 2, "zone_b": 7, "kind": "threshold", "guard_strength": 8000, "road": "random" },
    { "edge_id": 3, "zone_a": 3, "zone_b": 7, "kind": "open", "guard_strength": 0, "road": "true" },
    { "edge_id": 4, "zone_a": 4, "zone_b": 7, "kind": "open", "guard_strength": 0, "road": "true" },
    { "edge_id": 5, "zone_a": 5, "zone_b": 7, "kind": "threshold", "guard_strength": 5000, "road": "random" },
    { "edge_id": 6, "zone_a": 6, "zone_b": 1, "kind": "portal", "guard_strength": 0, "road": "false" },
    { "edge_id": 7, "zone_a": 6, "zone_b": 2, "kind": "portal", "guard_strength": 0, "road": "false" },
    { "edge_id": 8, "zone_a": 8, "zone_b": 1, "kind": "hint", "guard_strength": 0, "road": "false" },
    { "edge_id": 9, "zone_a": 8, "zone_b": 2, "kind": "hint", "guard_strength": 0, "road": "false" }
  ],
  "biome_selection_rules": {
    "use_engine_default": true
  },
  "allowed_water_content": ["normal", "islands"],
  "banned_terrain_kinds": [],
  "banned_monsters": [],
  "schema_version": 1
}
```

Author intent reading: central hub (zone 7) connects 4 surrounding zones (1, 3, 4, 5) all open-border. Mountain wilderness (2) is threshold-guarded-with-road. Forbidden zone (6) has portal pairs from sect zones (1, 2) — players reach it via teleport, never overland. Sea (8) is logically connected to zones 1 + 2 (hint) so placement is influenced but no real route.

---

## §8 Forge UI for template editing

V3 vision (Forge):
- **Template library** — list of templates in reality; clone / edit / delete
- **Zone canvas** — visual drag-and-drop zone editor (size, position, connections)
- **ZoneSpec form** — per-zone field editor (treasure tiers, terrain, monster strength)
- **Inheritance preview** — when author sets `inherit_treasure_from: 1`, UI shows resolved values inline
- **Validate button** — emits `Forge:ValidateTemplate` (dry-run with same seed; reports any reject_reason violations)
- **Generate preview** — runs full pipeline against this template; shows resulting `tilemap_view` in viewer

V1+30d: Forge UI ships **read-only** template viewer (template authored via direct DP write or admin tool). V2 adds Forge edit UX.

V3 RMG wizard (TMP-D1) builds on top: parameter capture ("wuxia kingdom, 4 sects, 12 towns, mountain north, sea south") → engine synthesizes template → opens Forge editor.

---

## §9 Validation rules (cross-ref `tilemap.*` namespace)

| Validation | rule_id (cross-ref TMP_001 §9) |
|---|---|
| Template not found by ref | `tilemap.template_not_found` |
| Template applied to wrong tier | `tilemap.template_tier_mismatch` |
| Two zones share zone_id | `tilemap.zone_id_collision` |
| Connection refs non-existent zone | `tilemap.connection_zone_not_found` |
| Connection self-loop (non-Portal) | `tilemap.connection_self_loop` |
| `inherit_*_from` cycle | `tilemap.inherit_cycle` |
| `inherit_*_from` ref not found | `tilemap.inherit_not_found` |
| Schema version drift (post-edit) | `tilemap.template_schema_version_mismatch` |
| Grid size out of bounds | `tilemap.grid_size_out_of_bounds` |
| TreasureTierSpec invalid (max < min, density = 0) | `tilemap.treasure_tier_invalid` |
| `applicable_tiers` empty | `tilemap.applicable_tiers_empty` |

Validations run at `Forge:EditTemplate` commit time AND at template finalization (just before generation). Both gates fail-loud; UI shows specific reject_reason.

---

## §10 Resolved questions (closure pass 2026-05-13)

| ID | Question | Locked decision | How resolved |
|---|---|---|---|
| TMP-TPL-Q1 | ZoneSpec.size: relative-weight or absolute-tiles? | **Relative-weight V1+30d** — engine auto-scales to fill grid; V2+ author can override with optional `absolute_tile_count: Some(u32)` field on ZoneSpec (schema-additive per TMP-A8) | ✅ ACCEPT default |
| TMP-TPL-Q2 | Connection guard-strength: range or single value? | **Single value V1+30d** — `guard_strength: u32` (deterministic); V2+ optional `guard_strength_range: Option<(u32, u32)>` for variability with per-seed sampling | ✅ ACCEPT default |
| TMP-TPL-Q3 | Template inheritance (template A extends template B)? | **NO V1+30d** — adds complexity without clear V1+30d use case; author can clone+modify in Forge UI. V2+ if author demand emerges (TMP-D16 reservation) | ✅ ACCEPT (defer V2+) |
| TMP-TPL-Q4 | Conflicting `banned_terrain_kinds` between template-level + zone-level | **UNION** — template-level UNION zone-level for ban (more restrictive of two wins); both bans apply additively. Implements "defense in depth" — author can broadly ban at template, narrowly add zone-level bans without losing global protection | ✅ ACCEPT default |
| TMP-TPL-Q5 | Per-template `seed_offset` override | **Author can set `seed_offset: u32`** — engine derives seed from `blake3(reality_id || channel_id || template_id || seed_offset)`; same offset across realities → same procedural map. Useful for "I want exact same continent as Reality X" workflow + cross-reality comparison testing | ✅ ACCEPT default |

---

## §11 Prior Art

### Template-system pedagogy

- **Yannakakis, G. N. & Togelius, J. (2018).** *Artificial Intelligence and Games.* Springer. Chapter 5: Procedural Content Generation. — Survey of template-based PCG.
- **Smith, G. (2014).** "Understanding procedural content generation: A design-centric analysis of the role of PCG in games." *Proceedings of CHI* — Author intent vs procedural fidelity.

### Template formats in genre prior art

- **Heroes of Might and Magic III** (1999, New World Computing). The original Random Map Generator template format defined the zones-plus-connections-plus-inheritance pattern that influenced this genre. Closed-source.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented template JSON schema at <https://github.com/vcmi/vcmi/blob/develop/config/schemas/template.json>; example templates at `Mods/vcmi/Content/config/rmg/`. Cited as one well-documented open-source reference template format.
- **Battle for Wesnoth** (2003+, GPL v2+). WML (Wesnoth Markup Language) map templates.
- **Caves of Qud** (Freehold Games). Author-extensible XML zone descriptions.
- **Stellaris / EU4** (Paradox). Map mod format for procedural galaxy / region generation.

### LoreWeave internal references

- [TMP_001 §2](TMP_001_tilemap_foundation.md) — TilemapTemplate aggregate (T2/Reality scope).
- [TMP_005](TMP_005_biome_and_obstacles.md) — BiomeSelectionRules detail.
- [WA_003 Forge](../02_world_authoring/) — V2 template-editor UI.
