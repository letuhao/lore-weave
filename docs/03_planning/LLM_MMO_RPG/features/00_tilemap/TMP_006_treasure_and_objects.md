# TMP_006 — Treasure & Objects

> **Conversational name:** "Treasure" (TMP-TR). The tiered value-density-based treasure-pile generator and the connectivity-preserving object placer.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **DRAFT 2026-05-13** (revised 2026-05-13 for license-hygiene framing)
> **Owns:** TMP-11 + TMP-12 catalog entries + TreasurePlacer + ObjectManager modificator detail

---

## §1 Why treasure tiers + density

Naive treasure placement ("scatter N piles randomly across zone") fails because:

- High-value piles too close to player start = trivializes early game
- Low-value piles too sparse = empty zones feel boring
- Random piles don't reflect author intent ("this zone is dangerous, expect strong rewards")
- Random placement risks **sealing gaps** — placing a pile between two free regions makes them disconnected (no path)

Standard PCG solution: **tiered value-density spec per zone**. Author declares 1-3 tiers like `[{min:100, max:800, density:4}, {min:1500, max:3000, density:6}, {min:8000, max:12000, density:3}]`. Generator places high tier first (large piles farther apart), then medium (denser), then low (densest). Each placement preserves zone connectivity.

The result: zones feel **tuned to author intent**. Low-tier zones near player start. High-tier zones in guarded wilderness. Cap on `treasure_value_limit` (engine default 20,000) — anything above becomes a "Pandora Box" / special-gold-pile variant.

This pattern (tiered values + density + scaling guards) is genre-standard. See §9 Prior Art.

---

## §2 TreasureTierSpec schema

```rust
pub struct TreasureTierSpec {
    pub min: u32,                                         // min pile value
    pub max: u32,                                         // max pile value
    pub density: u16,                                     // piles per zone-tile-thousand
}
```

Per zone, the author declares `treasure_tiers: Vec<TreasureTierSpec>` (typically 1-3 tiers). Order doesn't matter (generator sorts by `max` value descending).

`density` interpretation: target pile count = `density * zone.assigned_tiles.len() / 1000`. So `density: 4` on a 1500-tile zone = ~6 piles in that tier. Density is a soft target — actual count may be less if placement fails.

Author can specify a tier with `min == max == 0, density == 1` to add a filler "empty" tier (rarely used).

`max_treasure_value` is computed at finalization as the max over all tiers' `max` field. Used by generator to prune object pool (skip objects with value above max).

---

## §3 TreasurePlacer modificator

(Detail of TMP_003 §3.7.)

### 3.1 Object pool construction

```
Object pool sources:
  1. Common objects: scan all known TilemapObjectKinds; filter:
     - object has rmg_info (rarity, value, zone_limit, map_limit)
     - value <= zone.max_treasure_value
     - rmg_info.map_limit not yet exceeded
  2. Dwellings: creature-generators tagged for this terrain (V2; V1+30d skipped)
  3. Pandora Boxes: for high-value piles exceeding treasure_value_limit (gold-pandora variant)
  4. Seer Huts: quest-givers (V2)
  5. Prisons: hero-prison objects (V2)
  6. Spell Scrolls: tiered values (engine default: [500, 2000, 3000, 4000, 5000])

V1+30d pool keeps small: generic treasure chest + scattered gold + landmark + decorative cache.
Each TilemapObjectKind has rmg_info { value, rarity, zone_limit }:
  - value: gold-equivalent worth
  - rarity: weighting for random pick (high rarity = picked often)
  - zone_limit: max occurrences per zone (e.g., "only 1 Grail per map")
```

`ObjectInfo` struct:
```rust
pub struct ObjectInfo {
    pub primary_id: MapObjectId,
    pub secondary_id: MapObjectSubId,
    pub templates: Vec<TilemapObjectTemplate>,            // visual placements (rotations, variants)
    pub value: u32,                                       // gold-equivalent worth
    pub probability: u16,                                 // rarity weight
    pub max_per_zone: u16,                                // hard cap per zone
    pub generate_object: Box<dyn Fn(&Context) -> TilemapObject>,  // factory
}
```

### 3.2 Apply zone-config overrides

Author can:
- Ban categories: `zone.banned_object_categories: BTreeSet<ObjectCategory>` (e.g., ban Dwellings, Resources)
- Ban specific objects: `zone.banned_objects: BTreeSet<CompoundMapObjectId>`
- Require specific objects: `zone.required_objects: BTreeMap<CompoundMapObjectId, RequiredCount>`
- Inherit from another zone: `inherit_custom_objects_from: Some(ZoneId)` (TMP_004 §3)

After filtering, the pool is per-zone-customized.

### 3.3 Treasure pile generation (per tier, high-first)

```
treasures_remaining = []

FOR each tier T (sorted by max descending):
    target_count = (T.density as f32 * zone.assigned_tiles.len() as f32 / 1000.0) as u32

    pile_count = 0
    emergency_loop_counter = 0
    WHILE pile_count < target_count AND emergency_loop_counter < target_count:
        # Build a pile by sampling objects until value falls in [T.min, T.max]
        pile = []
        pile_value = 0
        attempts = 0
        WHILE pile_value < T.min AND attempts < 100:
            obj = sample_weighted_by_rarity(pool, max_value: T.max - pile_value)
            IF obj is None: BREAK
            pile.push(obj)
            pile_value += obj.value
            attempts += 1

        IF pile_value < T.min OR pile_value > T.max:
            # Failed to compose valid pile
            emergency_loop_counter += 1
            CONTINUE

        # Place pile (described in §3.4)
        IF needs_guard(pile_value):
            guard = pick_monster_guard(pile_value)
            pile.guard = Some(guard)

        treasures_remaining.push(pile)
        pile_count += 1

# Now place all generated piles in the zone (deferred to allow batched optimization)
FOR each pile in treasures_remaining:
    place_pile_in_zone(pile)
```

`emergency_loop_counter` prevents infinite loops when pool can't compose tier value range (e.g., all remaining objects too cheap for high tier).

`needs_guard(value)`: engine default `min_guard_value = 2000`. Piles with value ≥ 2000 get a monster guard. Engine config `tilemap_defaults.min_guard_value: u32` overrides.

### 3.4 Placement via ObjectManager

For each pile, call `ObjectManager.place_and_connect_object`:

```
search_area = zone.area_open (Open tiles)
search_area = search_area - roads (no treasures on roads)
search_area = search_area - other_object_placements

# Score each candidate tile in search_area:
FOR each candidate tile in search_area:
    distance_to_nearest_object = nearest_object_distance_grid[tile]
    IF distance < min_distance(pile_value):
        score = -inf (reject)
    ELSE:
        score = distance_to_nearest_object

        # Penalty for sealing road
        IF pile.access_tiles overlap road_segments:
            score /= 10

        # "Never seal a gap" check
        IF would_seal_a_gap(pile, zone.free_paths):
            score = -inf (reject)

# Pick best-scoring tile; place pile; update nearest_object_distance grid
```

`min_distance(value)`: scales with pile value. Approximate formula: `min_dist = sqrt(value / 100) + 5`. Lower-value piles can cluster; higher-value piles spread out.

### 3.5 Guards

```
IF pile.value >= min_guard_value:
    guard_monster = pick_monster_native_to_terrain(zone.terrain, strength = pile.value / 10)
    guard_position = zone.area_open.find_adjacent_tile(pile.access_point)
    pile.guard = Some(MonsterPlacement { monster: guard_monster, position: guard_position })
```

Guard position adjacent to pile's access tile. Monster strength scales with pile value. V2+ NPC_002 integration: guard "behaves" (taunts player approaching) via NPC roleplay.

V1+30d simplified: guard is a `TilemapObjectKind::MonsterLair { strength }` placement at adjacent tile. Combat resolution is V2.

---

## §4 The "Never seal a gap" connectivity invariant (TMP-A7)

The most important invariant in the whole pipeline.

### 4.1 The hazard

Naive object placement can create unreachable regions:
```
.....X.....         .....X.....
.....X.....         .....X..M..   ← place mountain (M) here
.....X.....   →     .....X..M..
.....F.....         .....F..M..
.....F.....         .....F.....
                    Free area split into 2 disconnected halves!
```

Player can't reach the right half. Pathfinding breaks. Quest objectives become unreachable. Catastrophic UX failure.

### 4.2 The check

Standard graph-connectivity check, using Tarjan's connected-components algorithm (Tarjan 1976):

```rust
fn would_seal_a_gap(object_footprint: &TileMask, free_paths: &TileMask) -> bool {
    // Imagine placing the object: which Walkable tiles get newly blocked?
    let blocked_after = free_paths.subtract(object_footprint);
    // Count connected components of remaining Walkable tiles
    let components = connected_components(&blocked_after);
    // Compare to before-object component count
    let before_components = connected_components(free_paths);
    components.len() > before_components.len()
}
```

If placing the object increases the number of connected components in the Walkable area, it sealed a gap. Reject placement.

The check is O(W × H) per placement (flood-fill twice). For 256×256 with ~100 placements, that's ~6.5M ops per zone = milliseconds. Cheap enough to run on every candidate placement.

This is a **standard PCG invariant**. Every level generator in the genre prior art (§9) enforces a similar invariant; without it, you get unreachable rooms.

### 4.3 Optimization: pre-filter

For large objects, pre-filter candidate tiles whose adjacent-free-tile count is low. Tiles adjacent to only 1 free region can't seal a gap (no second region to disconnect from). Tiles adjacent to 2+ free regions are risky candidates — run full check.

Border-inside / border-outside helpers can do this efficiently with O(footprint_perimeter) ops per candidate.

### 4.4 Implications

- **Placement failures are normal:** generator may try 10-20 positions before finding one that fits. Density is a target, not a guarantee.
- **High-value piles place first:** if they fail, ok; their constraints are stricter. Low-value piles fit in remaining space.
- **Obstacle placement (TMP_005) has same invariant.** ObstaclePlacer.process does iterative blocking + connectivity check.

---

## §5 ObjectManager modificator (service layer)

(Detail of TMP_003 §3.6.)

ObjectManager is a **service** modificator used by TreasurePlacer + ConnectionsPlacer + TownPlacer + MinePlacer. Doesn't generate objects itself; provides placement primitives + nearest-object-distance maintenance.

### 5.1 nearest_object_distance grid

Per-zone Vec<Vec<f32>> initialized to large value. On each object placement, update tiles in object's "influence radius" (e.g., 20-tile radius) with min(current_distance, distance_to_object).

This gives O(1) "how far from nearest object is tile X" query. Critical for treasure-pile placement scoring + monster guard placement.

### 5.2 placeAndConnectObject API

```rust
pub fn place_and_connect_object(
    search_area: TileMask,
    object: &TilemapObject,
    min_distance: f32,                                    // min distance from other objects
    needs_guard: bool,
    is_treasure: bool,
    optimize_type: OptimizeType,
) -> Result<PlacementResult, PlacementError> {
    // 1. Score all candidate tiles in search_area
    // 2. Pick best-scoring tile (per optimize_type policy)
    // 3. Verify: object fits (footprint in search_area); doesn't seal gap; path exists from free_paths to access_point
    // 4. Place: mark tiles Occupied; insert into tilemap_view.object_placements; update nearest_object_distance grid
    // 5. Return placement (with path to access from free_paths — used for road generation)
}

pub enum OptimizeType {
    Distance,                  // maximize distance from existing objects
    BothDistanceAndCenter,     // balance distance + closeness to zone center
    Center,                    // minimize distance from zone center
}
```

`OptimizeType::BothDistanceAndCenter` is the default for treasures (you want them scattered but not all on map edge). `Center` for towns. `Distance` for special objects.

### 5.3 chooseGuard helper

```rust
pub fn choose_guard(strength: u32, allow_creature_swap: bool) -> Option<MonsterTemplate>;
```

Picks a creature template native to zone terrain at desired strength. V1+30d: simple lookup table by `terrain → MonsterTemplate`. V2: full creature pool from `creature_handler` + faction-weighted selection.

Returns `None` if no creature available at this strength — guard is skipped, placement is unguarded (piles below min_guard_value can be unguarded by design).

---

## §6 Grail-equivalent special placement

Genre prior art often has a "final reward" object placed at end of generation (e.g., HoMM3's Grail, Diablo's unique items at deepest dungeon level). LoreWeave V1+30d: **no Grail equivalent**. V2: optional "canonical mythical item" placement per template (e.g., wuxia template might have "Sword of the Heavens" placed at random treasure-zone-of-tier-3 — narrative anchors).

---

## §7 Object placement order (pipeline order)

Within the modificator pipeline, objects get placed in this order (dependency-driven):

1. **Towns** (TownPlacer; V2 active) — main town at zone center; secondary towns offset
2. **Mines** (MinePlacer; V2 active) — placed in zone with sufficient distance from town
3. **Monoliths** (ConnectionsPlacer for Portal-kind passages) — placed at zone boundary
4. **Connection guards** (ConnectionsPlacer for Threshold-kind passages) — monster + passage tile
5. **Treasure piles** (TreasurePlacer) — high-value first, low-value last, all distance-scaled
6. **Roads** (RoadPlacer) — minimum spanning tree over above anchors
7. **Rivers** (RiverPlacer) — flow paths from mountains to lakes
8. **Obstacles** (ObstaclePlacer) — biome obstacle-set fill, largest-first

The order matters: roads connect existing anchors (towns + treasure-pile guards). Rivers route around existing roads. Obstacles fill remaining `Obstacle` tiles without sealing anything.

Each step's placement honors the "never seal a gap" invariant.

---

## §8 Special object kinds taxonomy

LoreWeave V1+30d simplifies to 7 `TilemapObjectKind` variants:

| Variant | V1+30d role | V2+ extension |
|---|---|---|
| `Treasure` | Generic loot pile | Tiered loot tables; rarity by zone monster strength |
| `MonsterLair` | Encounter trigger (connection guard or wild) | NPC roleplay integration (NPC_002); LLM-narrated encounters |
| `Landmark` | Visual + lore anchor (waterfall, statue, ruin) | Forge-author canonical book-canon refs |
| `Mine` | Resource node (V2 RES_001) | Per-resource type; production rate |
| `Town` | Major settlement | V2 TownPlacer; faction-owned; sub-tier drill-in to CSC_001 |
| `Monolith` | Teleport pair (Portal-kind passage) | V3 multi-tier portals |
| `Decoration` | Visual only | Author-uploadable decorations V3 |

This taxonomy is intentionally minimal V1+30d — extensible via TMP-A8 schema-additive.

---

## §9 Prior Art

### Procedural-content-generation foundations

- **Tarjan, R. E. (1976).** "Edge-disjoint spanning trees and depth-first search." *Acta Informatica* 6, 171–185. — §4 connected-components for "never seal a gap" invariant.
- **Yannakakis, G. N. & Togelius, J. (2018).** *Artificial Intelligence and Games.* Springer. Chapter 5: Procedural Content Generation. — Tiered loot + density patterns.
- **Smith, G. (2014).** "Understanding procedural content generation." *Proceedings of CHI* — Density tuning + author constraint.

### Tiered-loot patterns in game prior art

- **Diablo / Diablo II / Diablo III** (Blizzard). Tiered-rarity loot drop tables (white/blue/yellow/orange) influenced the genre's value-tier vocabulary.
- **Heroes of Might and Magic III** (1999, New World Computing). Tiered treasure values + density per zone in the Random Map Generator. Genre prior art for the specific shape of `{min, max, density}` per tier.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented treasure tier system + object pool at <https://github.com/vcmi/vcmi/blob/develop/lib/rmg/modificators/TreasurePlacer.cpp> and `randomMap.json` config. Cited as one well-documented open-source reference.
- **Roguelikes** (NetHack, Brogue, Dungeon Crawl Stone Soup). Per-level depth-scaled loot distribution.
- **Path of Exile / Borderlands** modern action-RPGs. Continuous-tier loot scaling.

### Connectivity-preserving placement

- **Bob Nystrom (2014).** "Rooms and Mazes: A Procedural Dungeon Generator." Blog post. — Connectivity-preserving room placement.
- **Žára, O. (2014).** "Procedural map generation in roguelikes." *RogueDev online talks.* — Connectivity invariants tutorial.

### LoreWeave internal references

- [TMP_001 §3.1](TMP_001_tilemap_foundation.md) — `tilemap_view` aggregate.
- [TMP_002 §5](TMP_002_zone_placement.md) — fractalize provides `free_paths` consumed by connectivity check.
- [TMP_004 §3](TMP_004_template_authoring.md) — `inherit_treasure_from` field.
