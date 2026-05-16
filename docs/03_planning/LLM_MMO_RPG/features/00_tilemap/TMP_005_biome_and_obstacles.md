# TMP_005 — Biome & Obstacles

> **Conversational name:** "Biome & Obstacles" (TMP-BIOME). The visual-consistency layer. Each zone selects a coherent set of obstacle objects (mountains, trees, lakes, plants, rocks) that look like they belong together.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **CANDIDATE-LOCK 2026-05-13** (DRAFT 2026-05-13 → revised 2026-05-13 for license-hygiene framing → CANDIDATE-LOCK closure pass: TMP-BIOME-Q1..Q4 RESOLVED at §9)
> **Owns:** TMP-13 catalog entry + TerrainPainter + ObstaclePlacer modificator detail

---

## §1 Why biomes matter

Two problems naive obstacle filling can't solve:

**Problem 1 — visual inconsistency.** Random obstacles look chaotic. A grass zone with pine trees + cacti + coral reefs feels broken. Players (and LLMs writing narrative) need consistent visual + thematic style per zone.

**Problem 2 — LLM grounding.** TMP_008 L4 regional narration ("you see oak trees thinning into pine; ahead the path climbs toward snow-capped peaks") only works if the visual layout is internally consistent. A "forest zone" must look like a forest; a "mountain pass" must have mountains. Biomes give the LLM something to ground prose against.

**Solution:** **biome obstacle-sets** — per-zone, the engine selects a coherent mix of obstacle types (1 mountain set + 1-2 tree sets + lake-xor-crater + 1-2 plant sets + 1-2 rock sets + maybe-1 structure + maybe-1 animal). All chosen sets must match the zone's terrain + level + faction + alignment. Each set contains 4-10 visually-consistent object templates.

The selection algorithm is **parameterized by `BiomeSelectionRules`** on the template — engine defaults provide a sensible mix, but authors can override per template. This is a standard PCG pattern; see §9 Prior Art for similar approaches in other procedural-map games.

---

## §2 Biome obstacle-set schema

### 2.1 What's a biome

A `BiomeSet` is a group of obstacle templates that share visual style. Authors (or the engine, with defaults) declare biomes. The generator picks biomes per zone at runtime according to `BiomeSelectionRules`.

```rust
pub struct BiomeSet {
    pub biome_id: BiomeId,
    pub terrain_types: BTreeSet<TerrainKind>,             // which terrains this biome can spawn on
    pub level: BiomeLevel,                                // Surface | Underground | Both
    pub factions: BTreeSet<FactionId>,                    // optional — only spawn in zones owned by faction
    pub alignments: BTreeSet<Alignment>,                  // optional — Good | Evil | Neutral
    pub object_type: BiomeObjectType,                     // see §2.2
    pub templates: Vec<TilemapObjectTemplate>,            // 4-10 object templates
}

pub enum BiomeObjectType {                                // 9 object kinds
    Mountain,                                             // large (3-9 tiles)
    Tree,                                                 // large (3-7 tiles)
    Lake,                                                 // large (4-12 tiles)
    Crater,                                               // large (4-9 tiles); xor with Lake
    Rock,                                                 // small (1-3 tiles)
    Plant,                                                // small (1-2 tiles); includes mushrooms
    Structure,                                            // small (1-4 tiles); ruins, statues
    Animal,                                               // small (1-2 tiles); bones, lairs
    Other,                                                // small (1 tile); flowers, debris; picked last + rare
}

pub enum BiomeLevel { Surface, Underground, Both }
pub enum Alignment { Good, Neutral, Evil }
```

Templates are tilemap-object descriptors with footprint (which tiles the object occupies + which are blocking).

### 2.2 BiomeSelectionRules (author-tunable)

The rule for "how many of each biome object type to pick per zone" is **explicit on the template**, with sensible engine defaults:

```rust
pub struct BiomeSelectionRules {
    pub use_engine_default: bool,                         // if true, ignore `rules`; use engine default rules
    pub rules: Vec<BiomeSelectionRule>,                   // ordered selection rules
}

pub struct BiomeSelectionRule {
    pub object_type: BiomeObjectType,
    pub count_min: u8,                                    // minimum sets of this type to pick (e.g. 1)
    pub count_max: u8,                                    // maximum sets (e.g. 2)
    pub xor_with: Option<BiomeObjectType>,                // pick this XOR another type (e.g. Lake xor Crater)
    pub priority: BiomePriority,                          // First | Normal | Last
}

pub enum BiomePriority {
    First,                                                // pick before others (used for "frame" categories like mountains)
    Normal,
    Last,                                                 // pick after everything (e.g. "other" rare types)
}
```

### 2.3 Engine default rules

When `use_engine_default: true`, engine ships these defaults:

```rust
fn engine_default_biome_selection_rules() -> Vec<BiomeSelectionRule> {
    vec![
        // Large frame objects, picked first
        BiomeSelectionRule { object_type: Mountain, count_min: 1, count_max: 1, xor_with: None, priority: First },
        BiomeSelectionRule { object_type: Tree, count_min: 1, count_max: 2, xor_with: None, priority: First },
        BiomeSelectionRule { object_type: Lake, count_min: 0, count_max: 1, xor_with: Some(Crater), priority: First },
        BiomeSelectionRule { object_type: Crater, count_min: 0, count_max: 1, xor_with: Some(Lake), priority: First },
        // Small filler
        BiomeSelectionRule { object_type: Plant, count_min: 1, count_max: 2, xor_with: None, priority: Normal },
        BiomeSelectionRule { object_type: Rock, count_min: 1, count_max: 2, xor_with: None, priority: Normal },
        // Optional ambient
        BiomeSelectionRule { object_type: Structure, count_min: 0, count_max: 1, xor_with: None, priority: Normal },
        BiomeSelectionRule { object_type: Animal, count_min: 0, count_max: 1, xor_with: None, priority: Normal },
        // Rare last-pick
        BiomeSelectionRule { object_type: Other, count_min: 0, count_max: 1, xor_with: None, priority: Last },
    ]
}
```

These defaults give the "frame + fill" pattern common across procedural-map generators (mountains + trees as large landmarks; rocks + plants as filler; structures/animals as ambient detail). Authors override per-template if they want a different feel (e.g., a sci-fi sector might have NO mountains/trees, only Structure + Other ambient debris).

### 2.4 Example biomes (LoreWeave-flavored)

```json
{
  "biome_id": "grassland_pines",
  "terrain_types": ["grass"],
  "level": "surface",
  "object_type": "tree",
  "templates": [
    { "name": "pine_tree_small", "footprint": "1x1 blocked" },
    { "name": "pine_tree_medium", "footprint": "1x2 blocked" },
    { "name": "pine_tree_large", "footprint": "2x2 blocked" },
    { "name": "oak_tree_medium", "footprint": "1x2 blocked" }
  ]
}

{
  "biome_id": "alpine_peaks",
  "terrain_types": ["mountain", "snow"],
  "level": "surface",
  "object_type": "mountain",
  "templates": [
    { "name": "snowy_peak_3x3", "footprint": "3x3 blocked" },
    { "name": "rocky_peak_2x3", "footprint": "2x3 blocked" },
    { "name": "tall_peak_3x4", "footprint": "3x4 blocked" }
  ]
}

{
  "biome_id": "wuxia_bamboo_grove",
  "terrain_types": ["grass", "forest"],
  "level": "surface",
  "factions": ["wuxia_sect_lotus"],
  "object_type": "tree",
  "templates": [
    { "name": "bamboo_clump_small", "footprint": "1x1 blocked" },
    { "name": "bamboo_clump_medium", "footprint": "1x2 blocked" }
  ]
}
```

The faction-scoped biome (last example) is the key: when a zone is owned by `wuxia_sect_lotus`, the engine prefers `wuxia_bamboo_grove` over generic `grassland_pines` for tree spawns. Visual + narrative consistency falls out for free.

---

## §3 TerrainPainter modificator

(Detail of TMP_003 §3.1.)

### 3.1 Terrain selection

```
1. IF zone.zone_role == Sea:
   - terrain_kind = random from [Water] (V1+30d single water terrain; V2+ adds Marsh, Coastline, etc.)

2. ELIF zone.spec.match_terrain_to_town AND zone.town_type != Neutral:
   - terrain_kind = LIBRARY.faction[town_type].native_terrain
   - faction_native_terrain map V1+30d default:
     wuxia_sect_lotus → Grass
     wuxia_sect_diamond → Mountain
     wuxia_sect_void → Snow
     scifi_solar → Sand
     modern_civic → Grass
     (engine-configurable; per-reality override via faction config)

3. ELSE:
   - terrain_kind = random from zone.spec.terrain_types (or all-surface-passable if empty)

4. Level validation:
   - IF zone.is_underground AND !terrain.is_underground:
       fall back to Subterranean
   - IF zone.is_surface AND !terrain.is_surface:
       fall back to Dirt
```

### 3.2 Paint terrain on all zone tiles

```
FOR each tile in zone.assigned_tiles:
    tilemap_view.terrain_layer[y*width + x] = terrain_kind as u8

FOR 15% of tiles (random subset; engine decoration percentage):
    tilemap_view.terrain_layer[y*width + x] = decoration_variant(terrain_kind)
    # variants are visual-only (grass-with-flowers, dirt-with-rocks); same passability
```

### 3.3 Terrain transition tiles (V2+)

V1+30d: hard terrain boundaries between zones (grass tile next to sand tile = visible seam). Visually acceptable for V1+30d.

V2+: **auto-tile transitions** — at zone borders, paint transition variant (e.g., grass-to-sand fade). Adapted via map-edit blending. Schema-reserved at TMP-A8 (additive — `transition_variants` field on TerrainKind).

---

## §4 ObstaclePlacer modificator

(Detail of TMP_003 §3.2.)

### 4.1 Biome selection per zone

```
Inputs to filter biomes:
  - zone.terrain_kind
  - zone.level (Surface V1+30d)
  - zone.town_faction (if zone has town)
  - zone.alignment (V2+; V1+30d no alignment, so all alignments pass)

Filter all biomes BY:
  - terrain_types contains zone.terrain_kind
  - level is Both OR matches zone.level
  - factions is empty OR contains zone.town_faction
  - alignments is empty OR contains zone.alignment

Group filtered biomes by object_type.

Apply BiomeSelectionRules from template (or engine defaults):
  FOR each rule (in priority order — First, Normal, Last):
    count = random.range(rule.count_min..=rule.count_max)
    IF rule.xor_with is Some(other_type):
      # XOR: pick THIS type OR the other type with 50/50; not both
      IF biome_selection already has other_type entries: skip this rule
      IF random_bool(): skip this rule
    FOR i in 0..count:
      pick random biome from filtered[rule.object_type]
      add to biome_selection
```

If insufficient biomes match (e.g., 0 mountain sets for this terrain): fall back to using all templates of that object_type (with a logged warning).

Selection persisted as `tilemap_view.zones[].biome_selection: BiomeSelection`:

```rust
pub struct BiomeSelection {
    pub mountain: Vec<BiomeId>,                           // 0-N depending on rules
    pub trees: Vec<BiomeId>,
    pub lake_or_crater: Vec<BiomeId>,                     // either kind goes here
    pub plants: Vec<BiomeId>,
    pub rocks: Vec<BiomeId>,
    pub structures: Vec<BiomeId>,
    pub animals: Vec<BiomeId>,
    pub other: Vec<BiomeId>,
}
```

### 4.2 Identify blocked area

After zone fractalize (TMP_002 §5):
- `zone.free_paths` is the connected free-path skeleton (`Walkable`; cannot be blocked)
- `zone.area_used` is the placed-object footprint (already `Occupied`)
- `zone.area_open` is the remaining tiles (`Open` state — candidates for obstacles)

ObstaclePlacer's job: mark a subset of `area_open` as `Obstacle` + fill with obstacle objects.

### 4.3 Strip loose appendages

Standard procedural-level-generation cleanup: iterative blocking that "absorbs" tiles adjacent to walls / off-map / blocked areas. Grows the obstacle region inward from zone borders + objects:

```
LOOP:
  to_block = empty
  FOR each tile in area_open:
    neighbors_outside = tiles adjacent to tile that are off-map OR shouldBeBlocked
    IF neighbors_outside is non-empty AND neighbors_outside is connected (not diagonal):
      # tile is adjacent to a "wall" of off-map/blocked tiles
      # block it (no harm — doesn't create new dead-end)
      to_block.add(tile)
  IF to_block is empty: BREAK
  area_open.subtract(to_block)
  FOR each tile in to_block: tile_state.set(tile, TileState::Obstacle)
END LOOP
```

This produces smooth interior + zone-boundary fade. Loose tiles that stick out get absorbed. Standard "erode + smooth" pattern in PCG literature.

### 4.4 Fill `Obstacle` tiles with obstacle objects

Largest-first algorithm:
```
1. Collect all object templates from selected biomes
2. Sort by footprint area descending (largest first)
3. FOR each template (largest first):
   FOR each candidate tile in blocked_area:
     IF object footprint fits (all object-tiles are in blocked_area):
       IF placement doesn't seal a gap (connectivity invariant — see TMP_006 §4):
         Place object; mark tiles Occupied instead of Obstacle
         Update nearest-object-distance grid
         BREAK
4. Remaining blocked tiles get small filler obstacles (1×1) OR remain pure Obstacle tile (no object — engine renders generic "rocky impassable terrain")
```

Largest-first matters: a 3×3 mountain needs all 9 tiles free; if smaller objects placed first, large objects might not fit. Common PCG pattern.

### 4.5 Special object placement: rivers source/sink

After obstacle placement, identify mountain + lake objects and register them with RiverPlacer:

```
ObstaclePlacer.process():
  ... place all obstacles ...

FOR each placed object:
  IF object.type == "mountain":
    river_placer.add_river_source(object.area)
  ELIF object.type == "lake":
    river_placer.add_river_sink(object.area)
```

Then RiverPlacer (TMP_003 §3.5) runs after, flowing water from mountains to lakes.

Author can also explicitly flag a zone as river_source / river_sink via ZoneSpec field (TMP_004 §2 schema-reserved V2+).

---

## §5 Cosmetic re-roll vs full re-bootstrap

(Cross-ref TMP_001 §2.5 EVT-T8 sub-types.)

### 5.1 CosmeticOnly

`Forge:RegenTilemap { mode: CosmeticOnly, new_seed: u64 }`:

- Preserves: zones[], free_paths, object_placements (treasures + landmarks), road_segments, river_segments
- Re-rolls: biome_selection (new obstacle sets) + biome obstacle filling
- Use case: author likes the layout but doesn't like the visual style ("less alpine, more bamboo")

Cost: ~1s wall-clock (only ObstaclePlacer re-runs).

### 5.2 FullRebootstrap

`Forge:RegenTilemap { mode: FullRebootstrap, new_seed: u64 }`:

- Discards: entire `tilemap_view`
- Re-runs: full pipeline from §11 of TMP_001 (zone placement → Penrose → fractalize → all modificators)
- Use case: author wants different layout entirely

Cost: ~5-30s wall-clock depending on grid size.

---

## §6 Pre-seeded biome library (engine defaults)

V1+30d ships with ~30 default biome sets covering common terrain × object-type combinations:

| Terrain | Mountain | Tree | Lake/Crater | Rock | Plant | Other |
|---|---|---|---|---|---|---|
| Grass | rolling_hills | oak_pine / bamboo_grove | clear_pond / mossy_crater | granite_boulder | wildflower / clover | scattered_log |
| Forest | overgrown_ridge | oak_pine / dense_birch / bamboo_grove | hidden_pond / forest_crater | mossy_rock | fern / mushroom_cluster | fallen_tree |
| Mountain | alpine_peak / volcanic_peak | sparse_pine | high_lake / volcanic_crater | granite_boulder / obsidian_chunk | hardy_lichen | bone_pile |
| Water | underwater_ridge | (none) | reef_lake / underwater_crater | coral_reef | seaweed_cluster | shipwreck |
| Sand | dune_ridge | palm / cactus_cluster | oasis / sun_crater | red_rock | scrub_grass / cactus_flower | bleached_bones |
| Snow | snowy_peak | snow_pine / frozen_birch | ice_lake / ice_crater | ice_boulder | frozen_lichen | frozen_corpse |
| Swamp | bog_ridge | mangrove / cypress | murky_pond / sinkhole_crater | mossy_rock | swamp_reed / mushroom_cluster | ancient_log |
| Rough | rocky_outcrop | dead_tree | dry_lakebed / impact_crater | broken_stone | scrub_grass | rusty_debris |

(Plus 5-8 more for V2+ Subterranean, faction-specific overrides.)

Authors override via Forge:EditBiome (V2+; V1+30d defaults locked).

---

## §7 Decoration vs blocking objects

Two categories on tilemap:

| Category | Examples | TileState | Aggregate? |
|---|---|---|---|
| **Blocking obstacle** | Mountain, tree, large rock, lake, crater | Obstacle → Occupied | YES (TilemapObjectPlacement) |
| **Decoration** | Wildflowers, fallen log, single bush, scattered debris | terrain_layer variant | NO (purely visual; no aggregate row) |

Decorations are part of the `terrain_layer` 15% decoration percentage (§3.2). No collision; player walks through. Renders at FE based on terrain_layer byte value.

Blocking obstacles are aggregate rows on `tilemap_view.object_placements`. Player path-finding treats them as walls.

---

## §8 Decoration density tuning

V1+30d default: 15% of tiles get a decoration variant. V2+ tunable per zone via `ZoneSpec.decoration_percentage: Option<u8>` (schema-reserved per TMP-A8).

Higher decoration % → busier-looking zone, more visual clutter, harder to read at high zoom. Lower → cleaner, more austere (e.g., desert wilderness).

---

## §9 Resolved questions (closure pass 2026-05-13)

| ID | Question | Locked decision | How resolved |
|---|---|---|---|
| TMP-BIOME-Q1 | Seasonal biome variants (winter pine vs summer pine) | **V2+ via TDIL-A2 season clock** — biome gains `seasonal_variants: HashMap<Season, Vec<ObjectTemplate>>` (schema-reserved V1+30d); engine swaps templates at season boundary; L4 narration cache invalidates on season change (per TMP_008b §8.2 cache key includes `season`) | ✅ ACCEPT (defer V2+ TMP-D17) |
| TMP-BIOME-Q2 | LLM-generated biome templates | **V3 opt-in** via `Forge:GenerateBiome` AdminAction — LLM emits `Vec<ObjectTemplate>` with footprint + visual hints; reviewed by author Forge approval queue (mirrors L3 canon_kind approval flow per TMP-LLM-Q2); rejected by default; author can promote to engine biome library | ✅ ACCEPT (defer V3 TMP-D18) |
| TMP-BIOME-Q3 | Zone terrain not covered by any biome | **Fall back to all-templates-of-this-type** — engine uses any object_template matching zone.terrain regardless of biome grouping; log `tilemap.biome_fallback_used` INFO event with terrain_kind + zone_id; visual coherence reduced but zone remains generated; author sees ops dashboard alert + can author new biome | ✅ ACCEPT default |
| TMP-BIOME-Q4 | Per-region biome rarity | **V2+ rarity tag** per `(biome_id, terrain_kind)` cell on biome registry — V1+30d uniform (all biomes equally likely if filter matches); V2+ `biome.rarity_per_terrain: HashMap<TerrainKind, BiomeRarity>` (Common/Uncommon/Rare/Legendary) for variety control | ✅ ACCEPT (defer V2+ TMP-D19) |

---

## §10 Prior Art

### Procedural-content-generation foundations

- **Yannakakis, G. N. & Togelius, J. (2018).** *Artificial Intelligence and Games.* Springer. Chapter 5: Procedural Content Generation. — Survey including biome / terrain composition.
- **Hendrikx, M., Meijer, S., Van Der Velden, J. & Iosup, A. (2013).** "Procedural content generation for games: A survey." *ACM Trans. on Multimedia Computing, Communications, and Applications* 9(1). — Taxonomy of PCG approaches incl. biome composition.
- **Smith, G., Whitehead, J., Mateas, M. (2011).** "Tanagra: Reactive planning and constraint solving for mixed-initiative level design." *IEEE Trans. Computational Intelligence and AI in Games* 3(3), 201–215. — Author-constrained PCG.

### Genre prior art (biome composition in similar games)

- **Heroes of Might and Magic III** (1999, New World Computing). Genre prior art for biome obstacle composition.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented biome format at <https://github.com/vcmi/vcmi/blob/develop/docs/modders/Entities_Format/Biome_Format.md> (introduced in vcmi v1.5.0). Cited as one well-documented open-source reference implementation of biome composition.
- **Dwarf Fortress** (2002+, Bay 12 Games). Biome generation with climate + elevation + drainage layers.
- **Caves of Qud** (Freehold Games). Layered biome composition with set-piece interleaving.
- **Civilization V / VI** (Firaxis Games). Climate-band biome painting.

### Roguelike biome generation pedagogy

- **Bob Nystrom (2014).** "Rooms and Mazes: A Procedural Dungeon Generator." Blog post. — Connectivity-preserving placement.
- **Žára, O. (2014).** "Procedural map generation in roguelikes." *RogueDev online talks.* — Biome layering tutorial.
- **Brogue source code** (open source). Reference biome composition in a polished roguelike.
