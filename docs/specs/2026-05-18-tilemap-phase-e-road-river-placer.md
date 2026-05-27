# Phase E — RoadPlacer + RiverPlacer — Spec

> **Track:** `LLM_MMO_RPG` tilemap-service · TMP_005/006/007 modificator-pipeline build
> **Roadmap:** [`docs/plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md`](../plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md) §4 Phase E
> **Branch:** `mmo-rpg/zone-map-amaw` · **Workflow:** default v2.2 human-in-loop
> **Size:** XL (9 files · 2 new modificators + a `TilemapView` schema extension + golden rebaseline)
> **Source docs:** TMP_003 §3.4/§3.5 (Road/River), TMP_005 §4.5 (river source/sink tags), TMP_006 §7 (pipeline order)

---

## §1 Context

The engine's modificator pipeline today runs **TerrainPainter → ConnectionsPlacer
→ TreasurePlacer → ObstaclePlacer**. Phase E adds the **last two placers** —
`RoadPlacer` and `RiverPlacer` — completing the TMP_003 §3 V1+30d catalog.

When Phase E lands, `place_tilemap` produces a fully-realized map: terrain,
obstacles, treasure, connections, **roads**, and **rivers**. This is the final
placer phase of the TMP_005/006/007 roadmap.

Inputs Phase E consumes from prior phases:
- `state.road_nodes: Vec<TileCoord>` — connection-passage tiles recorded by
  Phase-D `ConnectionsPlacer` (already pre-filtered to connections with
  `road != RoadOption::False`).
- `state.object_placements` — `MonsterLair` anchors (guards) and `Obstacle`
  placements tagged `biome_object_type` (`Mountain` / `Lake`) from Phase B.
- `state.zones[i].center` — per-zone centre.

## §2 Scope

### In scope

- **`RoadPlacer`** (TMP_003 §3.4): a minimum-spanning-tree over road anchors,
  each MST edge routed with the existing `search_path` (Dijkstra) and realised
  as a `RoadSegment` of `TerrainKind::Road`-painted tiles.
- **`RiverPlacer`** (TMP_003 §3.5): water flow from mountain-obstacle sources to
  lake/sea sinks, realised as a `RiverSegment`. **Rivers are functional
  barriers** (PO decision 2026-05-18) — carved river tiles become impassable,
  with **bridges** (road crossings) and **fords** (connectivity-gated + every-Nth)
  as passable crossing points.
- Additive (TMP-A8) `TilemapView` schema extension: `road_segments`,
  `river_segments`, and their record types.
- Pipeline registration so the Kahn topo-sort runs
  **… → TreasurePlacer → RoadPlacer → ObstaclePlacer → RiverPlacer**.
- Golden rebaseline to the Phase-E engine.

### PO decisions (CLARIFY checkpoint 2026-05-18)

| # | Decision | Rationale |
|---|---|---|
| PO-1 | **Road anchor set = all three:** zone centres (non-Forbidden) ∪ `road_nodes` (connection passages) ∪ `MonsterLair` anchors (guards). | A coherent road network reaching every zone, its gateways, and its guards. |
| PO-2 | **Rivers are functional barriers.** Carved river tiles are impassable; the carve is `would_seal_a_gap`-gated; bridges + fords keep the map connected. | Rivers are real terrain, not decoration — actors must cross at bridges/fords. |

### Out of scope

| Item | Why | Where |
|---|---|---|
| `TownPlacer` / `MinePlacer` anchors (town/mine entrances) | V2-active per TMP_006 §7 — V1+30d has neither | V2 |
| Author `river_source` / `river_sink` `ZoneSpec` flags | TMP_004 §2 marks them schema-reserved V2+ | V2 |
| Major rivers (width 2-3, author-flagged) | width flag is V2+ | V2 |
| `RoadKind` Highway/DirtPath distinction | V1+30d has no town/mine edges — every edge is zone-backbone; one road kind | V2 |
| HTTP service surface, Postgres | DESIGN.md §9 "Phase 4+" | later |

All work is **pure-engine** — no LLM, no gateway, no network.

## §3 Resolved doc conflicts (CLARIFY findings)

- **F-1 — pipeline order River vs Obstacle.** TMP_006 §7 numbers Rivers(7)
  *before* Obstacles(8), but TMP_005 §4.5 ("After obstacle placement, identify
  mountain + lake objects … Then RiverPlacer runs after") and TMP_003 §3.5
  (`DEPENDENCY(ObstaclePlacer)`) both require **River after Obstacle** — River
  consumes the `biome_object_type` tags ObstaclePlacer writes. **Resolved:**
  River runs last; TMP_006 §7's numbering is an authoring-doc error.
- **F-2 — road tile state.** TMP_003 §3.4 step 5 says "Set TileState to Occupied
  for road tiles". `TileState::Occupied` is **not passable** — a road of
  Occupied tiles would break traversal and could split a zone. **Resolved:**
  road tiles keep their passable `TileState` (`Walkable`/`Open`); roads are
  realised by painting `terrain_layer → TerrainKind::Road`. No object placer
  runs after RoadPlacer that targets passable tiles (ObstaclePlacer fills only
  `Obstacle` tiles), so "roads can't host objects" holds without an Occupied
  mark.
- **F-3 — river routing algorithm.** TMP_003 §3.5 describes "steepest-descent"
  flow, which can stall in a local minimum. **Resolved:** route the river with
  the existing deterministic `search_path` (Dijkstra) from source to the nearest
  sink, using an elevation-weighted cost so the path still prefers low terrain —
  same intent, robust + deterministic.

## §4 Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | `RoadPlacer` registered; the Kahn topo-sort runs it **after** `TreasurePlacer` and **before** `ObstaclePlacer`. |
| AC-2 | `RiverPlacer` registered; the topo-sort runs it **last** — after `ObstaclePlacer`. |
| AC-3 | Road MST anchors = zone centres of non-Forbidden zones ∪ `state.road_nodes` ∪ `MonsterLair` anchors, deduplicated; non-passable anchors handled (DESIGN settles snap-vs-drop). |
| AC-4 | Each realised MST edge yields a `RoadSegment`; every waypoint tile is painted `TerrainKind::Road`; road tiles remain passable (TileState unchanged). |
| AC-5 | An MST edge whose endpoints have no passable route is skipped — best-effort, no panic, the rest of the network still builds. |
| AC-6 | River sources = `Obstacle` placements tagged `Mountain`; sinks = `Obstacle` placements tagged `Lake` ∪ `Sea`-role zone tiles. |
| AC-7 | A river tile is carved to `TileState::Obstacle` + `Water` terrain **unless** it is a **bridge** (coincides with a road tile) or a **ford** (carving it would seal a gap, or it is the every-Nth crossing) — bridges/fords stay passable. |
| AC-8 | The river carve never splits any non-Forbidden zone's passable region (`Walkable ∪ Open`) **nor the map-wide passable region** — every carve is `would_seal_a_gap`-gated against both (refinement R1); verified end-to-end with an **independent** flood-fill oracle (the AC-7/AC-10 pattern). |
| AC-9 | A bridge is recorded wherever a river tile crosses a road tile; that tile stays passable and keeps `Road` terrain. |
| AC-10 | Determinism (TMP-A4): same `(template, channel, tier, grid, seed)` ⇒ byte-identical `TilemapView` incl. `road_segments` + `river_segments`. |
| AC-11 | The golden baseline is rebaselined to the Phase-E engine; `golden_baseline_byte_identical` reproduces it. |
| AC-12 | Schema is additive (TMP-A8): a pre-Phase-E `TilemapView` JSON without `road_segments` / `river_segments` still deserializes (fields default empty). |
| AC-13 | A template with no roaded connections places no roads, and one with no mountains places no rivers — both no-op gracefully. |

## §5 Module design

### §5.1 Pipeline registration & order

`place_tilemap` registers two new modificators. The Kahn topo-sort orders the
pipeline by `dependencies()` edges, independent of `add` order:

```
terrain_painter → connections_placer → treasure_placer → road_placer → obstacle_placer → river_placer
```

- `RoadPlacer::dependencies() = ["terrain_painter", "connections_placer", "treasure_placer"]`
  — runs after Treasure (TMP_006 §7 step 6); needs the terrain layer (road cost
  reads `Road` tiles), the `road_nodes` from Connections, and the guard lairs
  from Treasure.
- `ObstaclePlacer` **already** declares `"road_placer"` in its dependencies — so
  Obstacle now sorts *after* Road with no change to `obstacle_placer.rs`.
- `RiverPlacer::dependencies() = ["obstacle_placer", "road_placer"]` — runs last;
  needs ObstaclePlacer's `Mountain`/`Lake` `biome_object_type` tags (sources +
  sinks) and the road tiles (bridge detection). Resolves finding **F-1**.

Both placers are **RNG-free — determinism by construction** (the
`ConnectionsPlacer` precedent): MST + Dijkstra + fixed flat-index iteration
order. No `seed::sub_seed` (D10).

### §5.2 Schema extension (`types/tilemap.rs`) — additive (TMP-A8)

```rust
pub struct RoadSegment { pub waypoints: Vec<TileCoord> }          // ordered src→dst

pub enum CrossingKind { Bridge, Ford }                            // #[serde rename_all snake_case]

pub struct RiverCrossing { pub at: TileCoord, pub kind: CrossingKind }

pub struct RiverSegment {
    pub tiles: Vec<TileCoord>,        // ordered source-edge → sink, every river tile
    pub crossings: Vec<RiverCrossing>,// the passable subset (bridges + fords)
}
```

`TilemapView` gains `#[serde(default)] road_segments: Vec<RoadSegment>` and
`river_segments: Vec<RiverSegment>` (D9). `TilemapView::empty` + the
`place_tilemap` literal initialise them. `TilemapBuildState` gains mutable
`road_segments` / `river_segments` Vecs (init empty in `from_zones`), moved into
the view by `place_tilemap`.

### §5.3 `RoadPlacer` (TMP_003 §3.4)

**Anchors (PO-1).** Collect, then dedup by `TileCoord`:
1. `state.zones[i].center` for every non-`Forbidden` zone (a Forbidden zone is
   all-`Obstacle` — unroutable).
2. every tile in `state.road_nodes` (connection passages, Phase D).
3. every `MonsterLair` anchor in `state.object_placements` (connection guards +
   treasure guards).

**D-Q1 — routing proxy.** `search_path` needs start/goal inside the passable
search area, but a `MonsterLair` anchor tile is `Occupied` and a zone centre may
be `Occupied`. For each anchor derive a *proxy*: the anchor tile itself if
passable, else its lowest-flat-index passable 4-neighbour, else **drop** the
anchor. MST distance + path search both use the proxy.

**D-Q2 — MST.** Prim's algorithm (`engine/geometry/mst.rs`) over the deduped
proxy list sorted by flat index; start node = lowest flat index; edge weight =
Manhattan distance; ties broken by the candidate node's flat index. Returns
`Vec<(usize, usize)>` node-index edges — deterministic.

**D-Q3 / D-Q4 — road realisation.** Road search area = the map-wide passable
mask (`Walkable ∪ Open`) **minus all `Sea`-role zone tiles** (roads do not cross
open sea — that is the ferry's job). For each MST edge run `search_path` over
that area, proxy→proxy, cost by the *destination* tile: already-`Road` terrain
→ `0.5` (later edges reuse earlier roads), `Walkable` → `1.0`, `Open` → `2.0`.
`None` (no route — e.g. endpoints split by sea) ⇒ skip the edge (AC-5,
best-effort). Each routed path → a `RoadSegment { waypoints }`; every waypoint
`terrain_layer[idx] = TerrainKind::Road`. `TileState` is **left unchanged** —
roads stay passable (finding **F-2**). No `RoadKind`, no path smoothing
(out of scope / Deferred #025).

### §5.4 `RiverPlacer` (TMP_003 §3.5)

**D-Q5 — sources (one river per mountain-bearing zone).** A `Mountain` obstacle
per zone would spawn hundreds of rivers; instead, for each zone owning ≥1
`Obstacle` placement tagged `BiomeObjectType::Mountain`, the source is that
zone's lowest-flat-index mountain anchor. Sources processed in flat-index order.

**D-Q6 — sinks.** A `TileMask` of every `Lake`-tagged obstacle anchor ∪ every
tile of every `Sea`-role zone. A source with an empty sink mask, or whose
routed path exceeds `MAX_RIVER_LEN = grid.width + grid.height` (a sanity bound
on the "Manhattan range" of TMP_003 §3.5), places no river.

**D-Q7 — flow routing (finding F-3).** River search area = every tile that is
**not** `TileState::Obstacle`, plus the source tile and the sink tiles (so
start/goal are in-area). `search_path` (Dijkstra) source→nearest-sink, cost by
the destination tile's terrain elevation proxy: `Mountain` 10, `Snow`/`Rough` 4,
`Grass`/`Forest`/`Sand`/`Swamp`/`Subterranean`/`Road` 2, `Water` 0.5 — the river
prefers to descend toward water. Deterministic; robust where steepest-descent
would stall in a local minimum.

**D-Q8 — carve, with bridges + fords.** Walk the routed path; the source tile
and any sink tile are recorded in `tiles` but **not** carved (never carve the
mountain or the lake). For each remaining tile `t`, in path order:

1. `t`'s terrain is `Road` ⇒ **Bridge** — record `RiverCrossing{at:t,Bridge}`;
   keep `TileState` + `Road` terrain.
2. else `t`'s owning zone is `Forbidden` ⇒ carve freely (no passable region) —
   but the map-wide check of step 3 still applies. *(Review note: this branch
   is in practice unreachable — Forbidden-zone tiles are all-`Obstacle`, hence
   excluded from `river_search_area`, and can never be a source/sink since
   ObstaclePlacer skips Forbidden zones. The empty-`zone_passable` ⇒ `false`
   behaviour handles it correctly regardless, with no special case.)*
3. else if carving `t` would **split a connected region** — checked against
   **both** `t`'s owning zone's passable mask **and** the *map-wide* passable
   mask (`would_seal_a_gap` against each) ⇒ **Ford** — record
   `RiverCrossing{at:t,Ford}`; keep `TileState`; paint `Water`.
4. else `t` is the `FORD_INTERVAL = 12`-th tile since the last crossing ⇒
   **Ford** (a guaranteed crossing on long rivers); keep `TileState`; paint
   `Water`.
5. else **carve** — paint `Water`; if `t` was passable drop it to
   `TileState::Obstacle` (a non-passable `Occupied` tile keeps its state — both
   block traversal, and `would_seal_a_gap` already proved it strands nothing).

> **REVIEW-DESIGN refinement R1 — the map-wide check.** A per-zone gap-check
> alone is **wrong for a river**: a river crossing the single Phase-D corridor
> that links zone A to zone B severs A↔B reachability while splitting *neither*
> zone internally. The map-wide `would_seal_a_gap` catches exactly that — the
> true invariant for a functional barrier is "the river never splits the map's
> global passable region". The per-zone check is *also* kept (strictly more
> connected; keeps the existing `ac10`-style per-zone end-to-end test valid).
> The two checks are independent — neither implies the other.

Every carve is gated against the **live** masks (derived from `tile_state`
after prior carves) — incremental, the obstacle/treasure-placer precedent. This
makes **AC-8** true by construction. The path → a `RiverSegment{tiles,
crossings}`.

### §5.5 File census

| File | Change |
|---|---|
| `src/engine/geometry/mst.rs` | **NEW** — Prim's MST over a coord list (pure, property-tested) |
| `src/engine/modificators/road_placer.rs` | **NEW** — `RoadPlacer` (§5.3) |
| `src/engine/modificators/river_placer.rs` | **NEW** — `RiverPlacer` (§5.4) |
| `src/engine/geometry/mod.rs` | MOD — `pub mod mst; pub use mst::minimum_spanning_tree` |
| `src/engine/modificators/mod.rs` | MOD — register both modules + re-export |
| `src/engine/mod.rs` | MOD — `registry.add` both placers; move `road_segments`/`river_segments` into the view |
| `src/engine/build_state.rs` | MOD — `road_segments` + `river_segments` fields, init empty in `from_zones` |
| `src/types/tilemap.rs` | MOD — `RoadSegment`/`RiverSegment`/`RiverCrossing`/`CrossingKind` + 2 view fields + `empty()` init |
| `tests/determinism.rs` | MOD — give a fixture zone `Mountain` terrain so the golden carries a river; AC-1/2/10/13 assertions |
| `tests/golden/tilemap_baseline.json` | MOD — rebaseline to the Phase-E engine |

### §5.6 Determinism & test strategy

- `mst.rs` gets **property-style tests** (random coord sets — tree has n−1
  edges, spans every node, total weight ≤ a trivial chain).
- `RoadPlacer` / `RiverPlacer` unit-tested against hand-built fixtures with
  pinned tile counts (the `ac7` precedent — geometry that *forces* a road / a
  river / a bridge / a connectivity-driven ford, so the `≥1` assertions are
  real no-op detectors).
- **AC-8** gets the end-to-end independent-flood-fill test (`flood`/`components`
  in `engine/mod.rs` tests) extended through `RiverPlacer`.
- `tests/determinism.rs` `ac4` + `golden_baseline_byte_identical` are the
  inter-phase regression gate.

### §5.7 Known limitations (V1+30d — documented, not bugs)

- **No river confluence.** Each source routes its own river to a sink; rivers do
  not merge. River N's search area excludes river <N's carved (`Obstacle`)
  tiles, so a later river routes *around* an earlier one. Deterministic via
  flat-index source order. Real-river merging is V2.
- **`would_seal_a_gap` per river tile is O(W·H).** A continent-scale (256²) map
  with many rivers pays O((W+H)·W·H) per river. Acceptable at V1+30d test scale;
  flagged as a Deferred-perf candidate (roadmap §9 already lists the
  connectivity-check cost as a perf-deferred item).
- **No path smoothing / `RoadKind`.** Roads are raw Dijkstra paths, single kind
  (Deferred #025).

