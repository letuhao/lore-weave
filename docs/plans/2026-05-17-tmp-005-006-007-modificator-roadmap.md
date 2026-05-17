# TMP_005/006/007 — Modificator-Pipeline Build Roadmap

> **Status:** PLAN — awaiting operator `go` (2026-05-17)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Scope:** the unbuilt half of the TMP_003 modificator pipeline — TMP_005 (Biome
> & Obstacles), TMP_006 (Treasure & Objects), TMP_007 (Connections & Guards),
> plus RoadPlacer + RiverPlacer (TMP_003 §3.5).
> **This is a roadmap, not a spec.** Each phase below produces its own
> `docs/specs/` + `docs/plans/` pair at its `/amaw` CLARIFY/DESIGN/PLAN.

---

## 1. Goal

The engine today (`place_tilemap`) runs zone placement + a modificator pipeline
containing **only `TerrainPainter`**; `tilemap_view.object_placements` is always
empty. This roadmap takes the engine from "terrain only" to a **complete
V1+30d generation pipeline**: terrain → obstacles → treasure → connections →
roads → rivers, every step honouring the TMP-A4 determinism axiom and the
"never seal a gap" connectivity invariant.

When it lands, the L3/L4 LLM bootstrap can classify **engine-placed** objects
instead of the current fixture set — a genuine engine→L3→L4 flow.

## 2. Scope

### In scope (V1+30d cut)

- 5 new modificators: `ObstaclePlacer`, `TreasurePlacer`, `ConnectionsPlacer`,
  `RoadPlacer`, `RiverPlacer` — plus the `ObjectManager` service modificator.
- The shared foundation: a per-tile `TileState` grid, an extended
  `ModificatorContext`, the connectivity check, A\* path search,
  `TilemapObjectTemplate` footprints.
- The ~30-set engine biome library (TMP_005 §6) + `BiomeSelectionRules`.
- Additive (TMP-A8) template-schema extensions: connection `guard_strength` +
  `road`, zone `treasure_tiers`, optional `biome_selection_rules`,
  banned/required objects.

### Out of scope

| Item | Why | Where it lives |
|---|---|---|
| `TownPlacer` / `MinePlacer` | TMP_006 §7 marks both **V2-active**; V1+30d skips them | V2 |
| Combat / guard kill → tile re-walkable | TMP_006 §8.5 TMP-TR-Q2/Q6 are **V2** | V2 |
| Cross-zone dining-philosopher locking (TMP_007 §4) | engine is **single-threaded** — the lock is a no-op; see §6 | — (cut) |
| Real ship mechanics (TMP_007 §7) | V1+30d ships the simplified "ferry crossing" only | V2 (TVL_001) |
| Seasonal / LLM-generated biomes (TMP_005 §9 Q1/Q2) | explicitly V2+/V3 | V2/V3 |
| HTTP service surface, Postgres, Forge AdminActions | DESIGN.md §9 "Phase 4+" | later |

All work is **pure-engine** — no LLM, no gateway, no network.

## 3. Current state

| Component | State |
|---|---|
| `place_zones` (TMP_002) | ✅ done — FR placer + Penrose + fractalize |
| Modificator framework (registry + Kahn topo-sort) | ✅ done |
| `TerrainPainter` | ✅ done (Phase-1 cut; 15% decoration variant still out) |
| `ModificatorContext` | ⚠ thin — carries only `terrain_layer` + `zone_terrain` |
| `TileState` enum | exists in `types/tile.rs`; **no grid is materialized** |
| `object_placements` | always empty |
| `TilemapObjectTemplate` (footprint type) | does not exist |

## 4. The five phases

Foundation-first. Phase A builds the shared core that the docs do **not**
decompose cleanly per-doc (`ObjectManager` + the connectivity check + path
search are used across all three). Phases B–E are one placer-family each.

| Phase | Owns | Doc | Size | New / changed files (indicative) |
|---|---|---|---|---|
| **A — Foundation** | extended `ModificatorContext`, `TileState` build-grid, per-zone area model, `TilemapObjectTemplate`, connectivity check, A\* search, `ObjectManager`, template-schema extensions | TMP_006 §4/§5, TMP_007 §5 | XL | ~8–10 |
| **B — Obstacles** | `BiomeSet` schema, ~30-set biome library, `BiomeSelectionRules`, `ObstaclePlacer` | TMP_005 | XL | ~5 |
| **C — Treasure** | `TreasureTierSpec`, `ObjectInfo` pool, `TreasurePlacer` | TMP_006 | L | ~5 |
| **D — Connections** | `ConnectionsPlacer` 3-pass algorithm, monolith pairs, water routes, coast sealing | TMP_007 | XL | ~5 |
| **E — Roads & Rivers** | `RoadPlacer` (MST over anchors), `RiverPlacer` (mountain→lake flow) | TMP_003 §3.5 | L | ~4 |

Sizes are indicative — each phase re-classifies at its own `/amaw` CLARIFY.

### Phase A — Pipeline foundation

The load-bearing phase. No new *visible* output (object_placements stays empty,
terrain unchanged → `tests/determinism.rs` is a free regression gate), but it is
the largest correctness surface.

- **A.1** Extend `ModificatorContext` to the TMP_003 §2.2 model — introduce a
  build-state owning a mutable per-tile `TileState` grid, mutable
  `object_placements`, and per-zone runtime areas (`area_open` / `area_used` /
  `free_paths`, per TMP_005 §4.2). Exact struct shape settled at Phase A DESIGN.
- **A.2** `TilemapObjectTemplate` — object footprint descriptor (occupied tiles
  relative to an anchor + which are blocking) + fits/place helpers.
- **A.3** `would_seal_a_gap` — connected-components (flood-fill / Tarjan) over a
  `TileMask`; TMP_006 §4.2 + the §4.3 pre-filter. **The single most
  correctness-critical primitive in the pipeline** — gets property-style tests.
- **A.4** `search_path` — A\* / Dijkstra over a `TileMask` search area with a
  pluggable cost function (TMP_007 §5). Consumed by Phases D + E.
- **A.5** `ObjectManager` service — `nearest_object_distance` grid (§5.1),
  `place_and_connect_object` + `OptimizeType` (§5.2), `choose_guard` with the
  V1+30d terrain→monster lookup table (§5.3).
- **A.6** Template-schema additive extensions (all `#[serde(default)]`):
  `TemplateConnection.guard_strength` + `.road: RoadOption`,
  `ZoneSpec.treasure_tiers`, optional `ZoneSpec.biome_selection_rules`,
  `banned_object_*` / `required_objects`.

### Phase B — ObstaclePlacer + biomes (TMP_005)

- `BiomeSet` + §2 types (`BiomeObjectType` 9-variant, `BiomeLevel`, `Alignment`,
  `BiomeSelectionRules` / `BiomeSelectionRule` / `BiomePriority`,
  `BiomeSelection`).
- The ~30-set engine biome library (§6 — the 8-terrain × object-type table) +
  the §2.3 engine-default selection rules.
- `ObstaclePlacer`: §4.1 biome selection (priority order + XOR), §4.2 identify
  blocked area, §4.3 strip-loose-appendages erosion, §4.4 largest-first fill
  (every placement runs the §A.3 connectivity check), §4.5 register
  mountain/lake objects as river source/sink for Phase E.
- Folds in the deferred TerrainPainter 15% decoration variant (§3.2).

### Phase C — TreasurePlacer (TMP_006)

- `TreasureTierSpec` (§2), `ObjectInfo` (§3.1), V1+30d small object pool
  (treasure chest, scattered gold, landmark, cache, spell scrolls).
- §3.2 zone-config overrides (banned / required / inherit).
- §3.3 tiered high-tier-first pile generation with the emergency-loop guard;
  §3.4 placement via `ObjectManager`; §3.5 guards (`needs_guard`,
  `min_guard_value`).
- §8.5 TMP-TR-Q4 — placement-failure fallback: reduce density 50% + log INFO.

### Phase D — ConnectionsPlacer (TMP_007)

- The 3-pass algorithm: Pass 1 portals, Pass 2 direct passages (passage-point
  scoring, 3-way-junction avoidance), Pass 3 indirect (water route → monolith).
- §3.1 border separation, §6 terrain-prohibits-transition, §7 water routes
  (V1+30d simplified ferry), §8 monolith fallback, §9 coast sealing.
- **Single-threaded cut:** §4's dining-philosopher mutex is moot — modificators
  run sequentially. The §4.1 mutual-completion dedup (mark a passage completed
  on *both* zones so it is not re-placed) is **kept** — that is dedup logic, not
  concurrency.
- Adds runtime connection/road records to the view (schema extension — exact
  home, `ZoneRuntime` vs `TilemapView`, settled at Phase D DESIGN).

### Phase E — RoadPlacer + RiverPlacer (TMP_003 §3.5)

- `RoadPlacer`: minimum-spanning-tree over the placed anchors (connection
  guards + treasure-pile guards — no towns V1+30d), road segments routed with
  the §A.4 path search. TMP_006 §7 step 6.
- `RiverPlacer`: flow water from mountain sources to lake sinks registered by
  ObstaclePlacer §4.5. TMP_006 §7 step 7.
- Phase E CLARIFY reads TMP_003 §3.5 for the full RoadPlacer/RiverPlacer detail.

## 5. Dependency / build order

```
A (foundation)
├─ B  ObstaclePlacer ── needs: connectivity check, TilemapObjectTemplate
├─ C  TreasurePlacer ── needs: ObjectManager, connectivity check
├─ D  ConnectionsPlacer ─ needs: ObjectManager, path search
└─ E  Road + River ───── needs: path search; anchors from C+D; river src/sink from B
```

Build order **A → B → C → D → E**. The *runtime* pipeline order is fixed by the
registry's topological sort (TMP_006 §7: Connections → Treasure → Roads →
Rivers → Obstacles) and is independent of the build order — each placer is
tested against fixtures in its own phase.

## 6. Cross-cutting decisions (decided — not re-opened per phase)

1. **V1+30d cut everywhere.** The docs mark V1+30d vs V2+/V3 throughout; we
   build V1+30d. V2+ items listed in §2 are out.
2. **Single-threaded, no locking.** TMP_007 §4 dining-philosopher locking is a
   no-op in a single-threaded engine — not built. Mutual-completion dedup kept.
3. **Determinism (TMP-A4).** Every placer sub-seeds via
   `blake3(seed ‖ zone_id ‖ modificator_label)` — the established
   `seed::sub_seed` pattern. Same `(template, seed, grid)` ⇒ byte-identical
   output.
4. **Schema extensions are additive (TMP-A8)** — `#[serde(default)]`, no
   breaking change to existing fixtures.
5. **TownPlacer / MinePlacer absent** — ConnectionsPlacer/RoadPlacer's anchor
   logic must degrade gracefully when no town anchors exist.

## 7. Determinism & test strategy

- `tests/determinism.rs` extends every phase — same seed ⇒ identical
  `object_placements`, `terrain_layer`, road/river segments. It is the **hard
  inter-phase regression gate**.
- Phase A's connectivity check + path search get **property-style tests**
  (random masks, invariant assertions) — a bug there compounds into B–E.
- Per-modificator unit tests against small fixture templates (the `8×8`/`48×48`
  grid fixtures already used in `terrain_painter.rs` / `placement/mod.rs`).
- `cargo test` green at the **workspace root** is the gate to start the next
  phase.

## 8. Autonomy & gating plan

Operator choice (2026-05-17): **straight-through, no inter-phase checkpoints.**

- Each phase = one `/amaw` task → the full 12-phase AMAW workflow → cold-start
  Adversary review at design + code REVIEW, Scope Guard at QC/POST-REVIEW.
- **No per-chunk stops within a phase**; **no human checkpoint between phases.**
- **Hard stop — not optional:** a phase that ends with red `cargo test` or a
  failed VERIFY gate **halts the run**. Autonomous ≠ paper over a failure; a red
  phase stops and surfaces for the operator. The determinism test is the
  tripwire.
- `docs/audit/AUDIT_LOG.jsonl` + per-phase findings docs accumulate across all
  five phases so the **single end-of-run review** has a complete trail.
- Each phase COMMITs to `mmo-rpg/zone-map-amaw`; nothing is pushed (push needs
  explicit operator approval — CLAUDE.md Phase 11 guardrail).

> **Risk acknowledged:** SESSION_HANDOFF flags map-gen as correctness-critical
> and recommends a checkpoint between phases; on all 3 prior phases an
> independent human review caught real bugs the capped AMAW Adversary missed.
> Straight-through is the operator's override. The mitigation is §7's hard test
> gate + the heaviest rigor on Phase A.

## 9. Risks

| Risk | Mitigation |
|---|---|
| A Phase-A foundation bug (esp. connectivity check) compounds into B–E silently | Property-style tests on `would_seal_a_gap` + `search_path`; determinism test as tripwire |
| `ModificatorContext` extension is the riskiest design — gets the shape wrong and B–E inherit it | Phase A DESIGN settles it explicitly; Adversary cold-start reviews it |
| Connectivity check O(W·H) per candidate × many candidates → slow on 256² continent grids | TMP_006 §4.3 pre-filter; perf is a Deferred-item candidate, not a phase blocker |
| TMP_003 §3.5 (Road/River) is thinner than TMP_005/006/007 — less spec to lean on | Phase E CLARIFY reads TMP_003 §3.5 in full; flag gaps as findings |
| "Straight-through" lets an early defect ride into 4 later phases | §8 hard test gate; §7 Phase-A rigor |

## 10. Acceptance spine

Per-phase acceptance criteria are written at each `/amaw` CLARIFY. The
roadmap-level done-definition:

- All 6 modificators (`ObjectManager` + 5 placers) registered; `place_tilemap`
  produces non-empty `object_placements` with treasures, connection guards,
  monoliths, roads, rivers, obstacles.
- No placement violates the "never seal a gap" invariant (asserted in tests).
- `tests/determinism.rs` green — byte-identical output for a fixed seed.
- `cargo test` green at the workspace root.
- TMP_005/006/007 §-level requirements traced in each phase's spec.

---

## Operator start

On `go`: Phase A runs first as one `/amaw` task. Recommended pre-flight —
`cargo build` + `cargo test` clean at the workspace root, ContextHub up for the
`/amaw` Adversary/Scope-Guard calls.
