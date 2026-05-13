# TMP_007 — Connections & Guards

> **Conversational name:** "Connections" (TMP-CONN). The zone-graph edge realization layer. Takes abstract zone-graph edges and renders them as actual tile-level passages: guarded corridors, free borders, water routes, or teleport portals.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **DRAFT 2026-05-13** (revised 2026-05-13 for license-hygiene framing)
> **Owns:** TMP-4 + TMP-14 catalog entries + ConnectionsPlacer modificator detail

---

## §1 Why connections are hard

The template declares "zone 1 connects to zone 6 with guard strength 5000". Realizing this:

- Find a passage point: a tile where both zones touch (border-adjacency)
- Pick a passage that doesn't accidentally touch a third zone (no 3-way junctions)
- Place a monster guard at the passage point
- Build paths from both zones' interior `free_paths` to the guard tile
- Add a road if `road != False`
- Handle the case where zones don't touch (use water route or monolith portal)
- Don't deadlock when 2 modificators on different zones try to place a connection simultaneously

Standard solution patterns from the genre prior art (§9) handle all of this. We synthesize the pattern below.

---

## §2 PassageKind enum (5 variants — TMP-A3)

Per TMP_001 §2.2:

| Variant | Algorithm | Visual feel |
|---|---|---|
| `Threshold` | Direct passage (if adjacent) → fall back to water route → fall back to monolith pair. Place monster guard at passage. | Standard "guarded crossing" |
| `Open` | Direct passage only. No guard. Multi-tile open border. | Free open passage |
| `Hint` | No physical passage. Only influences zone placement (zones with hint edges are placed closer in force-directed phase). | None — author-intent only |
| `Adversarial` | No physical passage. Zones with adversarial edges are pushed apart in force-directed phase. | None — author-intent only |
| `Portal` | Always place monolith pair. Never direct passage, even if zones share border. | Portal-only travel |

### 2.1 When each kind is appropriate

- `Threshold` (default) — most edges. Adventure feel: cross from one region to another via a guarded passage.
- `Open` — for "open border" zones. Two adjacent kingdoms with free trade. No monster combat between them.
- `Hint` — narrative connections that don't physically realize. E.g., "Zone A's lore is tied to Zone B (sister city across the sea)" but you can't walk between them; only narrative cross-references.
- `Adversarial` — for rival zones that must be far apart. E.g., "two rival sects in same continent" — author wants them spaced.
- `Portal` — for forbidden / dimensional travel. E.g., zone with no overland route, only reachable via teleport.

### 2.2 RoadOption per connection

```rust
pub enum RoadOption { True, False, Random }
```

- `True` — always build road if connection has physical passage
- `False` — never build road (e.g., wilderness path through forest)
- `Random` — pre-resolved during finalization; random subset becomes roaded

Open connections never have roads; open implies "raw open border", which doesn't need a single road.

---

## §3 3-pass algorithm

### Pass 1: Portal passages

```
FOR each Portal-kind passage of this zone:
    place_monolith_pair(connection)
    Mark connection.completed = true on BOTH zones
```

`place_monolith_pair`:
1. Pick a tile in zone A's `area_open` (not on edge, not near other objects)
2. Pick a tile in zone B's `area_open` (same)
3. Get next monolith index from engine's monolith pool (engine maintains pool of teleport-pair IDs)
4. Place a `TilemapObjectKind::Monolith { pair_id }` at each tile
5. Mark tiles `Occupied`

This is the simplest case; always succeeds.

### Pass 2: Direct passages (zones share border)

For each non-Portal connection:

```
collect_neighbour_zones(zone):
    # Walk zone's border tiles; record adjacent zones
    border = zone.area.get_border()
    FOR each border_tile in border:
        FOR each adjacent_tile of border_tile:
            adj_zone_id = tilemap_view.zone_id_at(adjacent_tile)
            IF adj_zone_id != zone.id:
                neighbour_border_map[adj_zone_id].push(border_tile)

FOR each connection C of this zone:
    other_zone = zones[C.other_zone(self.id)]

    # Acquire locks on both zones (dining-philosopher pattern; Dijkstra 1965)
    lock = lock_zones(self, other_zone)

    # Check terrain prohibits direct transition
    IF terrain_prohibits_transition(self.terrain, other_zone.terrain):
        # e.g., Snow ↔ Lava direct transition prohibited
        continue (will try indirect in Pass 3)

    IF other_zone NOT in neighbour_border_map:
        continue  # zones don't share border; will try indirect in Pass 3

    # Find best passage point
    candidates = neighbour_border_map[other_zone.id]
    best_score = -infinity
    best_passage = None

    FOR each border_pos in candidates:
        potential = self.area_open.nearest(border_pos)

        # Avoid 3-way junctions (don't touch a 3rd zone)
        adjacent_zones = set of zone_ids at neighbors of potential
        IF adjacent_zones contains any zone other than self and other_zone:
            continue

        # Distance to other objects (don't crowd existing objects)
        dist = min(potential.nearest_object_distance, border_pos.nearest_object_distance)
        IF dist <= 3: continue  # too close to existing objects

        # Safety gap: passage point shouldn't be enclosed
        safety_gap = compute_safety_gap(potential, self, other_zone)
        IF safety_gap is invalid: continue

        # Score: prefer close to zone centers (passage in middle of border looks better)
        distance_to_center = self.center.dist(potential) * other_zone.center.dist(potential)
        local_dist = (dist - distance_to_center) * imbalance_penalty
        IF local_dist > best_score:
            best_score = local_dist
            best_passage = (border_pos, potential)

    IF best_passage is None:
        continue  # try indirect

    (road_node, guard_pos) = best_passage

    IF C.guard_strength > 0:
        guard_monster = ObjectManager.choose_guard(C.guard_strength)
        # Place guard at guard_pos
        ObjectManager.place_object(MonsterPlacement { monster: guard_monster, position: guard_pos })

    # Connect both zones' free_paths to the passage (A* search; Hart, Nilsson & Raphael 1968)
    our_path = pathfind(self.free_paths, guard_pos, in self.area_for_roads)
    their_path = pathfind(other_zone.free_paths, guard_pos, in other_zone.area_for_roads)

    IF our_path valid AND their_path valid:
        self.attach_walkable_path(our_path)
        other_zone.attach_walkable_path(their_path)

        IF C.road != False:
            RoadPlacer.add_road_node(self.id, guard_pos)
            RoadPlacer.add_road_node(other_zone.id, road_node)

        other_zone.modificator<ConnectionsPlacer>().mark_passage_completed_from_neighbour(C)
        Mark connection.completed = true
```

### Pass 3: Indirect passages (zones don't share border)

For connections that failed Pass 2:

```
FOR each remaining connection C:
    # Option A: Water route (if Sea zone exists between them)
    IF map has Sea zone:
        IF water_proxy.water_keep_connection(C):
            # Water route succeeded
            Mark connection.completed on BOTH zones
            continue

    # Option B: Monolith fallback
    place_monolith_pair(C)
    Mark connection.completed on BOTH zones
```

### 3.1 Border separation between zones

After Pass 2, create a thin "border" of blocked tiles around each zone (`create_border` step). Prevents random objects from sitting exactly on zone boundaries (visually muddy). Standard PCG hygiene.

---

## §4 Cross-zone locking (dining-philosopher pattern)

When ConnectionsPlacer for zone 1 wants to place a guard at the zone 1 / zone 2 boundary:
1. It needs to read zone 2's `area_open` (where can the passage tile go on the other side?)
2. It needs to write to zone 2's state (place guard waypoint; add road node)
3. Meanwhile ConnectionsPlacer for zone 2 might be doing the same with zone 3

Without coordination: deadlock. Dining-philosopher try_lock pattern (Dijkstra 1965): spin until both locks are available. Both released on placement complete.

```rust
fn lock_zones(z1: &Zone, z2: &Zone) -> (ZoneWriteGuard, ZoneWriteGuard) {
    if z1.id == z2.id { return (z1.write(), DummyGuard); }
    loop {
        let l1 = z1.area_mutex.try_lock();
        let l2 = z2.area_mutex.try_lock();
        if l1.is_some() && l2.is_some() {
            return (l1.unwrap(), l2.unwrap());
        }
        // Both released on drop; spin
        std::thread::yield_now();
    }
}
```

A per-modificator `externalAccessMutex` is also held for cross-modificator coordination.

### 4.1 Mutual completion check

When connection C between zone A and zone B is placed by zone A's ConnectionsPlacer:
- zone A marks `C.completed` in its `completed_passages` list
- zone A calls `other_zone.ConnectionsPlacer.mark_passage_completed_from_neighbour(C)` which adds C to zone B's `completed_passages` too

This prevents zone B's ConnectionsPlacer from trying to re-place C:
```rust
fn mark_passage_completed_from_neighbour(&mut self, c: ZoneConnection) {
    let lock = self.external_access_mutex.lock();
    self.completed_passages.push(c);
}
```

---

## §5 Path search for connection routing

After finding `guard_pos`, we need a path from `self.free_paths` to `guard_pos` (so the player can actually walk to the passage). Algorithm: A* (Hart, Nilsson & Raphael 1968) or Dijkstra over `self.area_for_roads` (`Open` + `Walkable` tiles, excluding blocked).

```rust
pub fn search_path(
    area: &TileMask,                                      // search space (where path can go)
    target: TileCoord,
    cost_fn: impl Fn(TileCoord, TileCoord) -> f32,
) -> Option<Path> {
    // Dijkstra / A* from `target` outward through `area`
    // cost_fn: scoring per edge; lower = preferred
    // For connections: prefer curved paths near zone border (avoid bisecting zone)
}
```

A "curved cost function" prefers tiles farther from border. Result: passage paths curve naturally; don't slice zones straight through middle.

After search, the path tiles are added to `zone.free_paths` via `zone.attach_walkable_path(path)`. Path tiles transition from `Open` → `Walkable`.

---

## §6 Terrain prohibits transition

Engine config has `prohibit_transitions: Vec<TerrainKind>` per TerrainKind — terrains that can't directly border each other:

```
Snow ↔ Lava : prohibited (visual jarring)
Subterranean ↔ Surface : prohibited (impossible)
```

When connection is between zones of prohibited terrains, Pass 2 direct fails — fall back to Pass 3 indirect (water or portal).

LoreWeave V1+30d default prohibitions (engine config):
- Snow ↔ Lava : prohibited
- Subterranean ↔ Surface : prohibited (V3+ underground)
- (none else V1+30d — most terrains can border)

Author can extend via `tilemap_template.banned_terrain_transitions: BTreeSet<(TerrainKind, TerrainKind)>` (V2+; schema-reserved per TMP-A8).

---

## §7 Water routes

If two zones can't connect directly but the map has a Sea zone in between:

```
1. Find tiles in self.area_open adjacent to water (shore)
2. Find tiles in other_zone.area_open adjacent to water (shore)
3. Build path through Sea zone from shore-self to shore-other:
   - Run Dijkstra over water tiles
   - Mark water-path tiles Occupied (so they don't get filled with sea monsters)
4. Place shipyard at each shore (engine config: shipyard cost)
5. Player needs ship to traverse: must enter shipyard, board, sail
```

V1+30d simplification: just place "ferry crossing" objects at both shores; player clicks → instant transit. No real ship mechanic V1+30d (ship system is V2+ TVL_001 travel mechanics).

V2+: full ship mechanics (player has ship object, sails water tiles, fights sea creatures).

---

## §8 Monolith fallback

When neither direct nor water route succeeds, place monolith pair (same as Portal kind):

```rust
fn place_monolith_pair(c: ZoneEdgeSpec) {
    let monolith_index = generator.next_monolith_index();
    // Get template for this monolith type (must be placeable on both zones' terrains)
    let template_a = get_monolith_template_for_terrain(zone_a.terrain);
    let template_b = get_monolith_template_for_terrain(zone_b.terrain);

    // Place in each zone (interior, not edge)
    let pos_a = zone_a.area_open.farthest_from(zone_a.center, in safe_radius);
    let pos_b = zone_b.area_open.farthest_from(zone_b.center, in safe_radius);

    zone_a.place_object(TilemapObject::Monolith { pair_id: monolith_index, template: template_a, position: pos_a });
    zone_b.place_object(TilemapObject::Monolith { pair_id: monolith_index, template: template_b, position: pos_b });
}
```

V1+30d: monolith renders as a portal sprite at each tile. Click → teleport to paired position. No combat; no cost.

V2+: monolith might have guard, cooldown, faction-restricted access, etc.

---

## §9 Coast sealing

If zone A has no water-route connection to zone B (even though both are near water), seal zone A's coast (zone A's water-adjacent border tiles) with shore obstacles. Prevents unintended water route via shore-side passage. Standard PCG hygiene.

V1+30d adopt. V2+ might add explicit "no coast seal" override for specific zone pairs.

---

## §10 Connection priority ordering

Connections processed in this order:
1. Portal (Pass 1)
2. Direct (Pass 2)
3. Indirect via water (Pass 3 Option A)
4. Indirect via monolith (Pass 3 Option B)

Within each pass, connection-by-connection in `zone.connections` order (template-author-declared).

Author can hint priority via `ZoneEdgeSpec.priority: Option<u16>` (V2+; schema-reserved per TMP-A8).

---

## §11 Failure modes

| Failure | Cause | Behavior |
|---|---|---|
| Direct + indirect both fail | Zones too isolated, no water, monolith fallback fails (rare) | Emit `tilemap.zone_not_connected` reject; UI shows error + suggests Forge:EditTemplate to add explicit Portal connection |
| Passage point can't be found | All border tiles too close to other zones OR objects too dense | Try next-best border tile; if all fail → fall to indirect |
| Monolith pair fails (no valid tile in either zone) | Zone area_open too constrained | Emit `tilemap.monolith_placement_failed`; suggest reducing zone density |
| Lock contention (rare) | Multiple agents claim same zone-pair | Spin until released; bounded by other modificator runtimes; eventually succeeds |

---

## §12 Visual rendering

V1+30d FE rendering for connections:
- `Threshold` — monster sprite + 1-tile open road tile leading from zone to zone
- `Open` — multi-tile open border (no monster, no road tile)
- `Hint` — invisible (no render)
- `Adversarial` — invisible (no render)
- `Portal` — purple swirl sprite at each end (mirror sprite shows pair_id)

Click-interactions:
- Click `Monolith` → travel UI ("Travel to other portal?")
- Click `MonsterLair` guard → encounter UI (V2 combat)
- Click into Open passage → seamless zone transition (PL_001 §13 Travel)

---

## §13 Open questions

| ID | Question | Default proposal |
|---|---|---|
| TMP-CONN-Q1 | Should connections support per-PC permission gates (e.g., faction-only)? | V2+ via `gate_kind: Option<GateKind>` on ZoneEdgeSpec (consume PF_001 PlaceConnection gating pattern); V1+30d ungated |
| TMP-CONN-Q2 | How to handle multi-PC parties traveling together via connection? | Same as PL_001 §13 — all party PCs move together as one travel action; no per-PC fork |
| TMP-CONN-Q3 | Should guards re-spawn after combat (V2)? | V2 author config per ZoneEdgeSpec: `respawn: NeverIRL | WeeklyFictional | ConditionalNarrative`; V1+30d no combat so moot |
| TMP-CONN-Q4 | Can a single zone-pair have multiple connections (e.g., 2 different passages)? | NO V1+30d (one edge per pair); V2+ multi-edge if author needs |
| TMP-CONN-Q5 | Should `Hint` connections be visible in author Forge UI (preview)? | YES — dashed line in editor; non-render in player UI |

---

## §14 Prior Art

### Algorithm foundations

- **Dijkstra, E. W. (1965).** "Cooperating sequential processes." Technical Report EWD-123. — §4 dining-philosophers pattern.
- **Dijkstra, E. W. (1959).** "A note on two problems in connexion with graphs." *Numerische Mathematik* 1, 269–271. — §5 path search.
- **Hart, P. E., Nilsson, N. J. & Raphael, B. (1968).** "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Trans. on Systems Science and Cybernetics* 4(2), 100–107. — §5 A* for connection routing.
- **Herlihy, M. & Shavit, N. (2008).** *The Art of Multiprocessor Programming.* Morgan Kaufmann. — Modern read-write locking patterns.

### Genre prior art (zone connections in similar games)

- **Heroes of Might and Magic III** (1999, New World Computing). Genre prior art for guarded zone connections + monolith portal pairs + water-route fallback.
- **VCMI** (2007+, GPL v2+). Open-source HoMM3 engine reimplementation. Documented connections placer at <https://github.com/vcmi/vcmi/blob/develop/lib/rmg/modificators/ConnectionsPlacer.cpp>. Cited as one well-documented open-source reference implementation of the 3-pass placement pattern.
- **Civilization V / VI** (Firaxis). Choke-point + strategic-resource placement on procedurally generated maps.
- **Roguelikes (Brogue, DCSS)**. Connectivity-preserving level connections.

### Concurrent-programming pedagogy

- **Lea, D. (2000).** *Concurrent Programming in Java* (2nd ed.). Addison-Wesley. — Reader-writer locks, try-lock patterns.

### LoreWeave internal references

- [TMP_001 §2.2](TMP_001_tilemap_foundation.md) — PassageKind enum.
- [TMP_002 §3](TMP_002_zone_placement.md) — force-directed phase consumes Adversarial + Hint passage kinds for placement.
- [TMP_003 §3.3](TMP_003_pipeline_modificators.md) — ConnectionsPlacer modificator wiring.
