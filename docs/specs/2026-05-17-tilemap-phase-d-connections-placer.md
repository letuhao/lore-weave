# Spec — tilemap-service Phase D: ConnectionsPlacer

> **Status:** CLARIFY (awaiting PO sign-off) · **Size:** XL · **Mode:** default v2.2 human-in-loop (no AMAW)
> **Roadmap:** [`docs/plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md`](../plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md) §4 Phase D
> **Source spec:** [TMP_007 — Connections & Guards](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_007_connections_and_guards.md) (§2–§13, CANDIDATE-LOCK 2026-05-13).
> Builds on Phase A (`place_and_connect_object`, `choose_guard`, `search_path`, `would_seal_a_gap`, the `TileState` build grid), Phase B (ObstaclePlacer), Phase C (TreasurePlacer).
> **Scope decision (PO, 2026-05-17 CLARIFY):** water routes (§7) + coast sealing (§9) are **in scope** for Phase D.

## §1 Context & goal

Phases A–C built the engine's terrain + obstacle + treasure placers. Phase D adds the **fourth placer — `ConnectionsPlacer` (TMP_007)** — the zone-graph *edge realization* layer.

Every `ZoneSpec` carries author-declared `connections: Vec<TemplateConnection>` — abstract edges ("zone 1 connects to zone 6, `Threshold`, guard strength 5000"). Today nothing realizes them: the generated tilemap's zones are geometrically placed but not *physically joined*. Phase D renders each edge as a real tile-level passage:

- a **guarded corridor** between bordering zones (`Threshold`),
- a **free open border** (`Open`),
- a **monolith teleport pair** (`Portal`, or any non-bordering fallback),
- a **water-route ferry crossing** (non-bordering zones with a Sea between them),
- or **nothing physical** (`Hint` / `Adversarial` — author-intent edges that only influenced zone placement).

After Phase D a generated tilemap is **fully connected** — every connection is realized, guards stand at guarded passages, and each zone's `free_paths` walkable skeleton is joined to its neighbours' so a player can traverse the map. This is the **third phase to change `place_tilemap` output**, so the AC-11 golden is rebaselined.

## §2 Scope

### In scope (V1+30d)

1. **`ConnectionsPlacer` modificator** — the TMP_007 §3 three-pass algorithm, registered in `place_tilemap`.
2. **Pass 1 — Portal connections** (§3 Pass 1) — every `Portal`-kind connection places a monolith pair (`place_monolith_pair`, §8): one `Monolith` object in each zone's open interior, sharing a `pair_id`.
3. **Pass 2 — Direct passages** (§3 Pass 2) — for a non-`Portal` connection whose two zones share a border: collect neighbour-border tiles, score candidate passage points (§3 — 3-way-junction avoidance, distance-from-objects, safety gap, prefer-zone-centre), place the monster guard when `guard_strength > 0`, and pathfind each zone's `free_paths` to the passage, attaching the routes as new `Walkable` path.
4. **Pass 3 — Indirect passages** (§3 Pass 3) — for a connection that failed Pass 2: a **water route** (§7) if a Sea zone lies between the two zones, else a **monolith-pair fallback** (§8). The monolith fallback always succeeds, so every connection is realized.
5. **§6 terrain-prohibits-transition** — an engine prohibition table (V1+30d: Snow↔Lava, Subterranean↔Surface); a connection between prohibited-terrain zones skips Pass 2 and falls to Pass 3.
6. **§7 water routes (V1+30d simplified ferry)** — shore-tile detection, a water-tile path through the Sea zone, and a **ferry-crossing object** at each shore (click → instant transit; no V2 ship mechanic).
7. **§3.1 border separation** — a thin blocked border around each zone after Pass 2 (PCG hygiene — keeps objects off zone boundaries).
8. **§9 coast sealing** — a zone with no water-route connection has its water-adjacent border sealed with shore obstacles.
9. **§4.1 mutual-completion dedup** — a connection realized by one zone's pass is marked completed on **both** zones, so the other zone does not re-place it. (This is dedup logic, not concurrency — see Out of scope.)
10. **`RoadOption` honoring** — Phase D records the road anchors (connection-guard positions of connections whose `road != False`) for Phase E's `RoadPlacer`; Phase D does **not** lay road segments.
11. **Determinism (TMP-A4)** — `ConnectionsPlacer` is RNG-free: every choice is a deterministic score-or-sort with a flat-index tie-break (see D11 — no sub-seed is taken), single-threaded fixed zone order; the golden is rebaselined.
12. **Additive schema (TMP-A8)** — a home for the monolith `pair_id`, the ferry-crossing object, and any realized-connection records. Exact shape settled at DESIGN; all `#[serde(default)]`.

### Out of scope

| Item | Why |
|---|---|
| §4 cross-zone dining-philosopher locking | The engine is single-threaded — the mutex is a structural no-op (roadmap §6). The §4.1 mutual-completion *dedup* is kept (item 9). |
| Real ship mechanics (§7 V2+) | V1+30d ships the "ferry crossing, click → instant transit" only; the player-ship / sail / sea-combat system is V2 (TVL_001). |
| Road segments (`RoadPlacer`) | Phase E. Phase D only records road anchors (item 10). |
| §11 reject events (`tilemap.zone_not_connected`, `tilemap.monolith_placement_failed`) | Need the Phase-2+ progress-event channel (cf. DEFERRED #015/#017, and Phase C's TMP-TR-Q4). V1+30d: the monolith fallback always succeeds, so a genuinely unconnected zone is a rare degenerate case handled deterministically without an event. |
| TMP-CONN-Q1..Q4 V2+ reservations — `gate_kind`, multi-PC party travel, guard `respawn`, `multi_edge_id` | §13 marks all four V2+ / schema-reserved / defer-to-PL_001. |
| §13 TMP-CONN-Q5 Forge-editor dashed-line rendering of Hint/Adversarial | FE / authoring-tool concern, not the generation engine. |
| TownPlacer / MinePlacer anchors | No towns V1+30d (roadmap §6.5) — RoadPlacer (Phase E) degrades gracefully when no town anchors exist. |

All work is **pure-engine** — no LLM, no gateway, no network.

## §3 Open design questions (resolved at the DESIGN phase)

These are flagged now so the PO sees the surface area; the Lead settles them at DESIGN, and the design self-review checks them.

- **D-Q1 — monolith `pair_id` home.** `TilemapObjectKind::Monolith` is a unit variant; a monolith placement needs to carry its teleport-pair id. Candidate homes: reuse the Phase-C `TilemapObjectPlacement.value` field, or add a dedicated additive field. (TMP_007 §3/§8 write `Monolith { pair_id }`.)
- **D-Q2 — ferry-crossing object representation.** `TilemapObjectKind` has no `Ferry`/`Shipyard` variant. Options: add a closed-enum variant, or reuse an existing kind. Affects the schema.
- **D-Q3 — realized-connection records.** Does `TilemapView` gain an explicit list of realized connections (a runtime `ZoneEdge`-style record per edge — kind, endpoints, guard, road flag), or is a connection fully implicit in the placed objects + the grown `free_paths`? (`types/zone.rs` already has a `ZoneEdge` type.) The roadmap calls this a Phase-D DESIGN decision (`ZoneRuntime` vs `TilemapView`).
- **D-Q4 — road-anchor handoff to Phase E.** Phase D records connection-guard anchors for `RoadPlacer`. Mechanism: an explicit road-node list in the build state, or Phase E re-derives anchors by scanning `object_placements`.
- **D-Q5 — connection guard placement.** Pass 2 picks an exact `guard_pos` by its own scoring. Phase A's `place_and_connect_object` *re-chooses* an anchor by distance scoring — so a connection guard is likely placed more directly (mark the chosen tile, push a `MonsterLair` record) rather than through `place_and_connect_object`. The guard still must not seal a gap (`would_seal_a_gap`).
- **D-Q6 — the §5 "curved" path-search cost function.** `search_path` takes a pluggable cost; the cost that makes passage paths curve near the border (not bisect the zone) is a DESIGN detail.

## §4 Acceptance criteria

Final ACs are pinned at DESIGN; this is the CLARIFY sketch the PO signs off on.

- **AC-1** — a `Portal` connection places a monolith pair: one `Monolith` object in each zone's interior, sharing a `pair_id`; the connection is marked completed on both zones.
- **AC-2** — an `Open` connection between two bordering zones places a direct passage and **no** guard; both zones' `free_paths` are joined.
- **AC-3** — a `Threshold` connection between two bordering zones places a guarded passage — a `MonsterLair` 4-adjacent to the passage when `guard_strength > 0` (guard strength carried on the record), with both zones' `free_paths` joined to it. The guard is **best-effort**: it takes a gap-safe `Open` tile, and if none exists 4-adjacent to the passage the crossing is realized unguarded (connectivity wins over the guard — D10).
- **AC-4** — passage-point scoring avoids 3-way junctions: a placed passage never sits where it would touch a third zone.
- **AC-5** — `Hint` and `Adversarial` connections place **no** physical passage, no guard, no monolith.
- **AC-6** — a connection between terrain-prohibited zones — V1+30d: a `Subterranean` zone bordering a surface-terrain zone (TMP_007 §6's "Snow↔Lava" is moot — `Lava` is not a V1+30d `TerrainKind`) — skips Pass 2 direct and is realized by Pass 3 (water route or monolith). A `Threshold`'s `guard_strength` is **not** carried to the Pass-3 fallback — a monolith pair / ferry is an unguarded crossing by design.
- **AC-7** — a non-bordering connection is realized by a **water-route ferry** when a Sea zone lies between the two zones, and by a **monolith pair** when no Sea is available; both shores/zones get the corresponding objects.
- **AC-8** — **every** author connection is realized — after `ConnectionsPlacer` runs, no `Threshold`/`Open`/`Portal` connection is left un-completed (the monolith fallback guarantees this).
- **AC-9** — §4.1 mutual completion: a connection shared by zones A and B is realized exactly **once**, not re-placed by the second zone's pass.
- **AC-10** — connectivity: `ConnectionsPlacer` never seals a gap — every zone's passable region (`Walkable ∪ Open`) stays connected (independent flood-fill), and the attached cross-zone paths join the zones into one traversable region. *Carve-out:* a degenerate zone in which **every** `Open` tile is a cut-vertex (e.g. a 1-wide zone — unreachable from `place_zones` geometry) may have its monolith seal a gap; D4 chooses AC-8 (realize the connection) over AC-10 there.
- **AC-11** — determinism (TMP-A4): same `(template, seed, grid)` ⇒ byte-identical `TilemapView`; the golden is rebaselined to the Phase-D engine and `golden_baseline_byte_identical` reproduces it.
- **AC-12** — additive schema round-trips (TMP-A8): the monolith `pair_id`, the ferry object, and any realized-connection record serialize/deserialize with the new fields defaulting; pre-Phase-D JSON still loads.
- **AC-13** — `cargo test --workspace` green; `cargo clippy --workspace --all-targets` clean.

## §5 Module design (DESIGN phase)

### Resolved design questions

- **D-Q1 — monolith `pair_id` home → reuse `TilemapObjectPlacement.value`.** A `Monolith` placement carries `value: Some(pair_id)`. `value` is already the "kind-specific magnitude" (Phase-C D10: Treasure = gold, MonsterLair = strength); Monolith = pair_id is the same pattern. No new field.
- **D-Q2 — ferry object → add `TilemapObjectKind::Ferry`.** A closed-enum extension (the established pattern — Phase B added `Obstacle`). A ferry-crossing renders as `Ferry`; serialises `"ferry"`. Pre-Phase-D JSON never carries it, so deserialisation stays compatible.
- **D-Q3 — realized-connection records → NOT surfaced on `TilemapView`.** A connection is fully observable from the placed objects (`Monolith` / `MonsterLair` / `Ferry`) plus the grown `free_paths`; no V1+30d post-pipeline consumer needs an explicit edge list, so none is added (additive-conservative — the Phase-C discipline of not adding a field without a consumer). Phase-D-internal realized state lives on the build state (D-Q4), not the view.
- **D-Q4 — road handoff → `TilemapBuildState.road_nodes: Vec<TileCoord>`.** Phase D appends a connection guard's tile to `road_nodes` when the connection has `road != False` and got a physical passage. Phase E's `RoadPlacer` consumes `road_nodes`. (How Phase E also sources treasure-pile-guard anchors is Phase E's DESIGN — out of Phase D scope.)
- **D-Q5 — connection guard placement → adjacent to the passage corridor.** The passage corridor (`our_path ∪ their_path`, all transitioned `Open → Walkable`) is the unobstructed link that joins the two zones (AC-10). The guard `MonsterLair` is placed on an `Open` tile 4-adjacent to the passage point, gap-checked with `would_seal_a_gap` — mirroring the Phase-C treasure-guard-beside-the-pile pattern and TMP_007 §12's "monster sprite + 1-tile open road tile". The guard never sits *on* the corridor, so it cannot break the connection.
- **D-Q6 — path-search cost → uniform cost for V1+30d.** `search_path` is driven with a uniform `cost = 1.0`; the passage corridor is the shortest route. TMP_007 §5's "curved cost" (paths bowing away from the border) is a visual-polish refinement with no correctness role — deferred (a Deferred-item candidate), not built in Phase D.

### Algorithm decisions

**D1 — `ConnectionsPlacer` modificator (`engine/modificators/connections_placer.rs`, NEW).** A `Modificator`; `name()` = `"connections_placer"`; `dependencies()` = `["terrain_painter"]` (terrain is needed for `choose_guard` and the §6 transition check). `TreasurePlacer` and `ObstaclePlacer` already declare `"connections_placer"` in their own `dependencies()` (Phase B/C), so registering `ConnectionsPlacer` slots it **first** among the placers via the Kahn topo-sort (TMP_006 §7: Connections → Treasure → … → Obstacles).

**D2 — global 3-pass `process`.** `process` runs three ordered passes over **all** zones' connections (TMP_007 §3 + §10 priority), not zone-by-zone-then-passes. A connection joins two zones and appears on both endpoints' `connections` lists; a `HashSet` of canonicalised zone-pairs (the two `ZoneId`s sorted) is the **§4.1 mutual-completion dedup** — a connection realised in any pass is recorded in the set, and the second endpoint's entry is skipped. The §4 dining-philosopher mutex is **not** built (single-threaded — roadmap §6); the dedup set replaces it.

**D3 — `PassageKind` dispatch.** `Portal` → Pass 1. `Hint` / `Adversarial` → **no physical realisation** (they only influenced TMP_002 force-directed placement); skipped, not added to the dedup set as "passages" — they are simply not connections to realise. `Open` / `Threshold` → Pass 2 (direct), falling to Pass 3 on failure.

**D4 — Pass 1, `place_monolith_pair`.** For each `Portal` connection: take a deterministic interior tile of each zone's `zone_area_open` — a non-edge tile maximising `nearest_object_distance` (uncrowded — TMP_007 §3 Pass 1 "not on edge, not near other objects"), flat-index tie-break. Assign the next `pair_id` from a monotonic engine counter, place a `Monolith` object (`value: Some(pair_id)`) at each, mark both tiles `Occupied`, record the pair in the dedup set. Always succeeds (if a zone has no non-edge `Open` tile — a degenerate zone — fall back to any `Open` tile; only a fully-blocked zone fails, which Pass 3's caller already excludes).

**D5 — Pass 2, direct passages.** Build a neighbour-border map (per zone, which zones its border tiles touch — TMP_007 §3 `collect_neighbour_zones`). For each unrealised non-`Portal` connection whose two zones share a border and whose terrains are **not** §6-prohibited: evaluate each candidate **passage point** `P` — a `self`-zone border tile 4-adjacent to `other`, the single bridge tile both zones' path searches reach. Reject `P` if it 4-touches a *third* zone (no 3-way junction — AC-4), if `nearest_object_distance[P] ≤ 3` (too crowded — TMP_007 §3), or if it fails the **safety check** — `P` must have ≥ 1 passable 4-neighbour inside `self` **and** ≥ 1 inside `other`, so a corridor can route through it. Score the survivors with the **pinned V1+30d formula** `score(P) = nearest_object_distance[P] − (dist(P, self.center) + dist(P, other.center))` — prefer uncrowded and near both zone centres; max wins, flat-index tie-break. (TMP_007 §3's `imbalance_penalty` / `compute_safety_gap` are left under-specified by the source — lesson 4b229319; this pinned score + safety check is the deliberate, fully-defined V1+30d resolution.) If `guard_strength > 0`, place the guard (D10). Then `search_path` from `P` to each zone's `free_paths` mask, over `{P} ∪ that-zone's-passable-area`, uniform cost; if **both** paths return `Some`, attach them (`Open → Walkable`) so the corridor `our_path ∪ their_path` — meeting at `P` — joins the two zones' `free_paths`; record the pair completed; and if `road != False`, push `P` to `road_nodes`. On any failure (no surviving candidate, or either path returns `None`) the connection is left for Pass 3.

**D6 — Pass 3, indirect passages.** For each still-unrealised `Open` / `Threshold` connection: **(a)** if the map has a `Sea` zone and both zones have a tile adjacent to that Sea's water, run the §7 water route; **(b)** else `place_monolith_pair` (D4) — the always-succeeds fallback, guaranteeing AC-8.

**D7 — §6 terrain-prohibits-transition.** A pure `terrain_prohibits_transition(a, b) -> bool` over an engine table. V1+30d table: `Subterranean` may not directly border a surface land terrain (TMP_007 §6 — "Subterranean ↔ Surface"). The §6 "Snow ↔ Lava" example is **moot** — `Lava` is not a V1+30d `TerrainKind` — and is noted as such, not encoded. A prohibited pair skips Pass 2 → Pass 3.

**D8 — §7 water routes.** When a `Sea` zone exists: a zone's **shore tiles** are its `zone_area_open` tiles 4-adjacent to a Sea-zone tile. If both endpoint zones have shore tiles, `search_path` a route over the Sea zone's water tiles between the two shores; on success place a `Ferry` object at each shore tile, mark both tiles `Occupied`, record completed. On failure → monolith fallback (D6b).

**D9 — §3.1 border separation + §9 coast sealing.** After Pass 2, a thin one-tile border is sealed around each zone's outer edge where it abuts another zone — **only `Open` border tiles** are set to `Obstacle`, so a realised passage corridor (which is `Walkable`) is preserved by construction; each tile is `would_seal_a_gap`-checked so the sealing never disconnects a zone (PCG hygiene). §9: a zone with **no** realised water-route connection has its water-adjacent `Open` border tiles set to `Obstacle` (same `Open`-only, gap-checked rule), preventing an unintended shore passage.

**D10 — guards.** A connection guard is `choose_guard(passage_terrain, guard_strength)` → a `MonsterLair` placement (`value: Some(guard_strength)`) on a gap-safe `Open` tile 4-adjacent to the passage point (D-Q5). `guard_strength == 0` ⇒ no guard (an `Open`-feel passage even on a `Threshold` edge).

**D11 — determinism (TMP-A4).** `ConnectionsPlacer` is **RNG-free** — every choice (monolith tile, passage point, water/path route) is a deterministic score-or-sort with a flat-index tie-break; the monolith `pair_id` counter is monotonic. No sub-seed is needed; determinism holds by construction on the fixed single-threaded zone order. The golden is **rebaselined** to the Phase-D engine.

**D12 — schema (additive, TMP-A8).** `TilemapObjectKind` gains `Ferry`. `TilemapBuildState` gains `road_nodes: Vec<TileCoord>` (init `Vec::new()` in `from_zones`). `Monolith` / `MonsterLair` / `Ferry` placements reuse the existing `value` field. No `TilemapView` field is added (D-Q3).

### Module / file census

```
src/
  engine/modificators/connections_placer.rs   NEW  ConnectionsPlacer — 3-pass algorithm,
                                                   place_monolith_pair, Pass-2 scoring,
                                                   water routes, border/coast sealing,
                                                   terrain_prohibits_transition
  engine/modificators/mod.rs                  MOD  re-export ConnectionsPlacer
  engine/mod.rs                                MOD  register ConnectionsPlacer (first placer)
  engine/build_state.rs                        MOD  +road_nodes: Vec<TileCoord>
  types/object.rs                              MOD  +TilemapObjectKind::Ferry
  tests/determinism.rs                         MOD  golden rebaselined; AC coverage
  tests/golden/tilemap_baseline.json           MOD  rebaselined (D11)
```

Pure helpers (`terrain_prohibits_transition`, neighbour-border map, passage scoring, monolith-tile pick) are unit-testable; `ConnectionsPlacer::process` is integration-tested with hand-built multi-zone build states. `cargo test --workspace` + `cargo clippy --all-targets` are the VERIFY gate (AC-13).
