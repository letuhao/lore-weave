# Spec — River barrier-strength: split ObstaclePlacer, carve river pre-erosion (DEFERRED #026)

> **Status:** CLARIFY → DESIGN.
> **Track:** `LLM_MMO_RPG` (tilemap-service).
> **Size:** XL (pipeline-topology change + heavy golden churn + determinism-
> critical). Default v2.2 human-in-loop; `/review-impl` mandatory at
> POST-REVIEW (this changes the connectivity-bearing pipeline order).
> **Clears:** DEFERRED #026 (river ford-heavy / weak barrier).

---

## 1. Problem & refined diagnosis

DEFERRED #026: the golden river is ford-heavy (75 crossings / 98 tiles). The
deferred hypothesised "route rivers before obstacle **fill**". Investigation
refined this:

- **`erode_zone`** (Open→Obstacle) is what fragments the passable region — it
  peels each zone toward its `free_paths` skeleton, leaving narrow passable
  channels. **`fill_zone`** (Obstacle→Occupied) does **not** change
  passability.
- `RiverPlacer` runs last, so it carves the *post-erosion* narrow channels.
  Carving any narrow-channel tile would seal a gap ⇒ it fords ⇒ near-continuous
  fording.
- In a **wide-open** zone, a bisecting river produces only a *few* fords (just
  where its carved line finally spans wall-to-wall) — the desired barrier.
- The river's sources/sinks **are** the `Mountain`/`Lake` obstacle objects,
  currently placed *into the eroded obstacle region*. So they require erosion
  first ⇒ the river is structurally stuck behind erosion.

**Fix (PO-confirmed):** place the `Mountain`/`Lake` source/sink obstacles
**pre-erosion** on the zone's **Open** area, carve the river into the
wide-open zone, then erode + fill the rest **around** the river. Obstacle
semantics shift edge→interior (PO-accepted); golden rebaselines.

## 2. Goal

The continent river drops from ~76 % forded to a small, well-placed crossing
count (target: < 25 % of river tiles forded). Connectivity invariant
**unchanged** — the strict dual `would_seal_a_gap` gate stays; rivers simply
carve a wider region so fewer tiles are forced fords. `place_tilemap` stays
deterministic (TMP-A4); golden rebaselined deliberately.

### Non-goals
- **Do not** change `RiverPlacer`'s carve/ford logic — it is correct; it just
  now runs against a wider passable region.
- **Do not** change `would_seal_a_gap` or the simple-point erosion pre-filter.
- **Do not** add new biome types or change `select_biomes`.

## 3. Approach — split `ObstaclePlacer` into two pipeline passes

Replace the single `ObstaclePlacer` with two modificators around `RiverPlacer`:

### 3.1 `ObstacleSourcePlacer` (NEW — runs after `road_placer`, before river)

Per non-Forbidden zone:
1. `select_biomes(zone_id, terrain, rules, library, seed)` → selection
   (deterministic — same call as today).
2. Place **only** the `Mountain` + `Lake` objects of the selection, on the
   zone's **`zone_area_open()`** region (not the eroded obstacle region),
   largest-first among the mountain/lake templates. These become the river
   sources (Mountain anchors) + sinks (Lake anchors).
3. **No erosion** in this pass.

### 3.2 `RiverPlacer` (UNCHANGED logic — dependency retarget only)

`dependencies()` changes from `["obstacle_placer", "road_placer"]` to
`["obstacle_source_placer", "road_placer"]`. Carve/ford logic untouched.

### 3.3 `ObstacleFillPlacer` (the renamed/retargeted `ObstaclePlacer` — after river)

Per non-Forbidden zone:
1. `erode_zone(zone_idx)` — **now skips Water-terrain tiles** (a river ford is
   passable + Water; erosion must not eat it). River carved tiles are already
   `Obstacle`, so erosion's existing `Open`-only guard skips them; the new
   Water guard additionally protects forded (passable-Water) tiles.
2. `select_biomes(...)` (re-derived, deterministic — same selection as 3.1).
3. Place the **non-Mountain/Lake** objects on `zone_obstacle()`, **skipping
   Water-terrain tiles** (don't drop a tree onto a river).

### 3.4 Pipeline order (engine/mod.rs)

```
TerrainPainter → ConnectionsPlacer → TreasurePlacer → RoadPlacer
  → ObstacleSourcePlacer → RiverPlacer → ObstacleFillPlacer
```

Wired by the existing Kahn topo-sort via `dependencies()` edges:
- `obstacle_source_placer` deps: `terrain_painter`, `road_placer` (+ the
  unregistered `treasure_placer`/`connections_placer` tolerated as today).
- `river_placer` deps: `obstacle_source_placer`, `road_placer`.
- `obstacle_fill_placer` deps: `river_placer`.

## 4. Determinism / correctness contract

- **Connectivity invariant preserved.** Both `erode_zone` (simple-point gate)
  and `RiverPlacer` (dual `would_seal_a_gap`) keep their strict gates. The
  river carving a wider region produces *fewer* forced fords, but never
  strands a region (the gate is unchanged). `erosion_never_seals_a_gap` +
  the river connectivity tests still hold.
- **Erosion-skips-Water is connectivity-safe.** Skipping a tile from erosion
  can only *keep more passable*, never strand — strictly safer for
  connectivity.
- **Fill-skips-Water** only changes *where* decorative obstacles land (never a
  connectivity concern — fill places on already-`Obstacle` tiles).
- **Determinism (TMP-A4):** `select_biomes` is seeded + pure; both passes
  re-derive the same selection. Largest-first ordering within each pass is
  deterministic (area desc, biome-id, name). Placement walks
  `iter_set` (flat order). The whole pipeline stays reproducible.
- **Golden rebaselined deliberately** via `regenerate_golden_baseline` — the
  output legitimately changes (mountains/lakes move interior; river becomes a
  real barrier). This is the one task where the golden *should* change.

## 5. Test strategy

### 5.1 Existing tests
- `river_placer::tests::*` — UNCHANGED (they call `place_rivers` directly with
  hand-built fixtures; the pipeline reorder doesn't touch them). Must stay
  green.
- `obstacle_placer::tests::*` — the erode/fill/simple-point tests; adjust for
  the split (erode tests move to the fill placer; the AC-1/2/3 simple-point
  tests are unaffected — they test `local_seal_verdict`/`erode_zone` directly).
- The pipeline/determinism tests in `engine/mod.rs` + `tests/determinism.rs`
  — update the registry registration to the two new modificators; rebaseline
  the golden.

### 5.2 New tests
- **AC-1** `obstacle_source_placer_places_mountains_and_lakes_in_open_area` —
  after the source pass, Mountain/Lake objects exist on tiles that were Open;
  no other obstacle types placed; no erosion happened (zone still mostly Open).
- **AC-2** `river_in_a_wide_zone_fords_far_less_than_pre_reorder` — a wide
  single-zone fixture with a Mountain source + Sea sink; assert the river's
  ford ratio is low (e.g. fords / river-tiles < 0.4) — the barrier-strength
  win. (The pre-reorder ratio on the same fixture would be high.)
- **AC-3** `fill_placer_skips_river_water_tiles` — after the full pipeline, no
  `Occupied` obstacle sits on a Water-terrain river tile.
- **AC-4** `erosion_does_not_eat_a_river_ford` — a forded (passable-Water) tile
  survives the post-river erosion pass.
- **AC-5** `place_tilemap_is_deterministic_after_reorder` — same seed ⇒
  byte-identical `TilemapView` (the AC-4 determinism test, still green).

### 5.3 Measurement (AC-6 — informational)
Re-run `tilemap-service measure`; record the continent river ford ratio
before (75/98 ≈ 0.77) vs after, in the SESSION. Confirm `place_tilemap` still
fast (≤ ~7 s) and the river barrier is meaningfully stronger.

## 6. Acceptance criteria
- **AC-1..AC-5** pass (§5.2).
- **AC-6** continent river ford ratio drops materially (target < 0.25);
  recorded in the SESSION.
- **AC-7** `cargo test --workspace` green; `cargo clippy` 0 warnings.
- **AC-8** golden deliberately rebaselined; `golden_baseline_byte_identical`
  green against the new baseline; `regenerate_golden_baseline` documented in
  the SESSION as intentionally re-run.
- **AC-9** DEFERRED #026 moved to "Recently cleared".

## 7. Files touched (estimate)
| Path | Change |
|---|---|
| `src/engine/modificators/obstacle_placer.rs` | split into `ObstacleSourcePlacer` + `ObstacleFillPlacer`; `fill_region` generalised (target mask + type filter + skip-water); `erode_zone` skips Water tiles; tests adjusted + AC-1/3/4 |
| `src/engine/modificators/river_placer.rs` | `dependencies()` retarget `obstacle_placer`→`obstacle_source_placer`; AC-2 ford-ratio test |
| `src/engine/modificators/mod.rs` | export the two new modificators |
| `src/engine/mod.rs` | register both + reorder; update pipeline tests + comments |
| `tests/determinism.rs` + `tests/golden/tilemap_baseline.json` | rebaseline golden |
| `docs/specs/2026-05-22-tilemap-river-barrier-reorder.md` | THIS FILE |
| `docs/plans/2026-05-22-tilemap-river-barrier-reorder.md` | PLAN |
| `docs/deferred/DEFERRED.md` | clear #026 |
| `docs/measurements/2026-05-18-continent.md` | ford-ratio before/after |
| `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | session entry |

## 8. Risks
| Risk | Mitigation |
|---|---|
| Golden churn hides an unintended regression | AC-1..AC-5 pin the *intended* changes; `/review-impl` scrutinises; the river/erosion connectivity tests are the invariant guard |
| Mountains/lakes on Open area break a downstream assumption (e.g. fill expecting them in obstacle region) | AC-1 + the full-pipeline tests; mountains/lakes are `Occupied` either way (impassable) |
| `select_biomes` not pure ⇒ two passes diverge | verify in DESIGN by reading `select_biomes`; if impure, compute once + thread the selection through |
| Erosion-skips-Water misses a carved (Obstacle) tile | carved tiles are `Obstacle` (already skipped by the Open-only guard); only forded (passable-Water) tiles need the new guard |
| Two mountains/lakes per zone change river source/sink selection | river uses lowest-flat Mountain per zone — unchanged; AC-2 + determinism cover it |

## 9. Open question for PO
- **Q1** (recommended: **yes**) — re-run `measure` for the ford-ratio
  before/after (AC-6)? ~5 min. Yes per measurement-first discipline.
