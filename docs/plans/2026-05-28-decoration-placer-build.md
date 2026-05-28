# DecorationPlacer — build plan (4 chunks)

> **Spec:** [`docs/specs/2026-05-28-decoration-placer-density-pass.md`](../specs/2026-05-28-decoration-placer-density-pass.md) (ACCEPTED, Q1–Q3 PO-locked)
> **Implementation branch:** `mmo-rpg/zone-map-decoration-placer` off main (NEW; not on `mmo-rpg/zone-map-quality-spec`)
> **Load-bearing invariant across all chunks:** existing 433 tilemap-service tests + 49 frontend-game vitest tests stay green, no rebaseline.
> **Revision history:** 2026-05-28 v2 — /review-impl surfaced 17 findings against v1 (4 HIGH = wrong file paths + non-existent fields + comment-only fallback branch + missing seed access); all fixed in v2 by re-grounding against actual code at engine/mod.rs:64-145, engine/pipeline/modificator.rs:23-39, engine/build_state.rs:20-40, registry.rs:94-225, seed.rs:72-86. Lesson: validate integration-point types against actual code before specifying algorithms (see `feedback_validate_adr_driver_before_drafting` — same anti-pattern, one level deeper).

## Ground-truth verification table

Before chunk A starts, the implementer MUST verify each ASSUMED API point below by reading the cited file. If any check fails, STOP and re-grep before writing code. This table is the v2 fix for v1's HIGH findings.

| Plan assumes | File:line | What to verify |
|---|---|---|
| `ModificatorContext { template, grid, seed: TilemapSeed, state, registry }` | [engine/pipeline/modificator.rs:23-39](services/tilemap-service/src/engine/pipeline/modificator.rs#L23-L39) | `seed` field is on context, not template |
| `sub_seed(seed: TilemapSeed, label: &str) -> u64` exists | [seed.rs:72](services/tilemap-service/src/seed.rs#L72) | Pattern: `format!("decoration_placer:{}", zone_id.0)` |
| Pipeline composition site | [engine/mod.rs:133](services/tilemap-service/src/engine/mod.rs#L133) | `modificators.add(Box::new(...))` — ALL 5 sites at lines 133, 317, 405, 418, 540 must register DecorationPlacer |
| `TilemapBuildState.zone_terrain: Vec<Option<TerrainKind>>` | [build_state.rs:38](services/tilemap-service/src/engine/build_state.rs#L38) | Terrain access is `ctx.state.zone_terrain[idx]`, NOT `zone.terrain_type` |
| `ZoneBuildState.id: ZoneId(String)` | [build_state.rs:21](services/tilemap-service/src/engine/build_state.rs#L21) | NOT u32; use `.0` for `&str` |
| `Registry` lives at `src/registry.rs` (not `src/types/registry.rs`) | [registry.rs:94-225](services/tilemap-service/src/registry.rs#L94) | `terrain_by_tag` + `object_by_tag` HashMap; new field `decoration_by_biome` is BTreeMap |
| `ObjectKindDef` has no `biomes` field today | [types/registry.rs:100](services/tilemap-service/src/types/registry.rs#L100) | Chunk B adds it with `#[serde(default)]` |
| `TileMask::sample_set` does NOT exist | [types/tile_mask.rs](services/tilemap-service/src/types/tile_mask.rs) | Chunk C adds it (collects + indexes) |
| Existing add-placement pattern | [obstacle_placer.rs:451](services/tilemap-service/src/engine/modificators/obstacle_placer.rs#L451) | `state.object_placements.push(TilemapObjectPlacement { ... })` direct — no accessor |

## Chunk A — placer skeleton + template field (XS)

**Files (5 modify, 2 new):**
- NEW `services/tilemap-service/src/engine/modificators/decoration_placer.rs` — `pub struct DecorationPlacer;` + `impl Modificator` with `name() = "decoration_placer"`, `dependencies() = vec!["road_placer", "obstacle_fill_placer", "river_placer"]`, `process()` early-returns when `ctx.template.decoration_density == None`. ~50 LOC.
- NEW `services/tilemap-service/src/types/decoration.rs` — `pub struct DecorationDensity { min_per_zone: u32, max_per_zone: u32, fraction_of_free: f32 }` + `target_for(&self, free_count: u32) -> u32` method that clamps `round(fraction * free_count)` to `[min, max]`. ~30 LOC.
- MODIFY `services/tilemap-service/src/types/template.rs:97` — add `pub decoration_density: Option<DecorationDensity>` field with `#[serde(default, skip_serializing_if = "Option::is_none")]` to `TilemapTemplate`. Matches `world_zone`'s additive-Option pattern at line 111. ~3 LOC.
- MODIFY `services/tilemap-service/src/engine/modificators/mod.rs` — re-export `decoration_placer`. 1 LOC.
- MODIFY `services/tilemap-service/src/types/mod.rs` — re-export `decoration`. 1 LOC.
- MODIFY `services/tilemap-service/src/engine/mod.rs` — register `DecorationPlacer` via `modificators.add(Box::new(DecorationPlacer));` at **all five** composition sites (lines 133, 317, 405, 418, 540 per `grep -nE "ModificatorRegistry::new"`). Lines 405 + 418 are pre-river/river-only test pipelines; lines 317 + 540 are alt-pipeline test paths. **All five must register the new placer for the test surface to stay coherent.** ~5×1 LOC.

**Tests (1 new):**
- `decoration_placer_early_returns_when_density_none` — assert `place_tilemap_with_registry(default_template, seed=1, default_registry)` produces a TilemapView whose `object_placements` is byte-identical to the V2 golden hash. The V2 golden is the existing pinned hash (no rebaseline). This is the V2-preservation check.

**Determinism check (existing tests):**
- All 377 tilemap-service lib tests + 56 integration tests stay green. V2 golden tests run untouched because `decoration_density: None` is the implicit serde default for every existing template fixture (no fixture JSON/TOML needs to add the field).

**ACs satisfied:** AC-DECO-1 (skeleton exists), AC-DECO-2 (V2 golden byte-identical preserved via opt-in).

**Note on dependencies:** `decoration_placer` must run AFTER all the OPEN-region-modifying placers. From the existing pipeline order ([engine/mod.rs:135-141](services/tilemap-service/src/engine/mod.rs#L135-L141)): `TerrainPainter → ConnectionsPlacer → TreasurePlacer → RoadPlacer → ObstacleSourcePlacer → RiverPlacer → ObstacleFillPlacer → DecorationPlacer (NEW)`. The `dependencies()` vec lists the LAST-running upstream placers (RoadPlacer + ObstacleFillPlacer + RiverPlacer); the topological sort ensures full ordering through transitive dependencies.

**PR title:** `feat(tilemap): decoration_placer skeleton + DecorationDensity template field (chunk A)`

---

## Chunk B — default registry decoration tags + ObjectKindDef.biomes field + Registry index (S)

**Schema additions (registry.rs):**
- ADD `biomes: Vec<String>` field to [`ObjectKindDef`](services/tilemap-service/src/types/registry.rs#L100) (current fields: id, primitive, label, footprint, walkability_pattern, min_spacing, properties). Mark `#[serde(default)]` for backward-compat with existing V2 TOML entries that don't list biomes. Empty list means "no biome filter; placer skips" (defensive default for non-decoration kinds).
- ADD `density_weight: f32` field, `#[serde(default = "default_density_weight")]` (default = 1.0). Used by chunk-C weighted sampling.
- These additions touch the OBJECT KIND schema across all tag types (not just decorations) but the additive Option/default discipline means existing 28 V2 entries continue loading unchanged.

**Files (3 modify, 0 new):**
- MODIFY `services/tilemap-service/registry/default.toml` — append ~30 `[[object]]` entries (note: the actual TOML key is `[[object]]` not `[[object_kinds]]` per [registry.rs:80](services/tilemap-service/src/registry.rs#L80) `RegistryFile { object: Vec<ObjectKindDef> }`). Each entry has `primitive = "decoration"`, `walkability_pattern = "all_walkable"`, `biomes = [...]`, `density_weight`, `min_spacing`. Per spec §6 distribution table. ~300 lines of TOML.
- MODIFY `services/tilemap-service/src/registry.rs` — three additions inside `impl Registry`:
  1. New field `decoration_by_biome: BTreeMap<String, Vec<DecorationRef>>` on the `Registry` struct (BTreeMap for deterministic iteration — `terrain_by_tag` and `object_by_tag` use HashMap which is fine for keyed lookup but NOT for iteration; deco placer iterates so BTreeMap is required).
  2. New type `pub struct DecorationRef { pub kind_id: String, pub density_weight: f32, pub min_spacing: u32 }`.
  3. New helper `pub fn decorations_for_terrain(&self, terrain: TerrainKind) -> &[DecorationRef]` that maps `TerrainKind` enum → biome tag string via `terrain.serde_name()` (TerrainKind already has `#[serde(rename_all = "snake_case")]` per V2 ADR, so `Grass → "grass"`, `Mountain → "mountain"`, etc.) then looks up in `decoration_by_biome`. Returns `&[]` for unmapped terrains (defensive).
  4. Index computation in `Registry::from_file` (line 107) — after the existing object_by_tag loop, scan all ObjectKindDefs with `primitive == ObjectPrimitive::Decoration`, bucket by each biome string in their `biomes` field, sorted insert.
  ~60 LOC total.
- MODIFY `services/tilemap-service/registry/xianxia_sample.toml` — append parallel ~30 `xianxia:decoration.*` entries spanning the same 10 biome keys (`grass, forest, water, road, hill, mountain, swamp, desert, snow, subterranean` — these are the snake_case forms of `TerrainKind` enum variants, NOT registry terrain TAG IDs like `lw:grass`). ~300 lines of TOML.

**Important — biome key vocabulary:**
- `ObjectKindDef.biomes` entries are `TerrainKind` enum names in snake_case (e.g. `"grass"`, `"forest"`, `"mountain"`, `"subterranean"`) — NOT registry terrain-tag IDs (`"lw:grass"`).
- This decouples decoration registration from per-book terrain registry namespace. A xianxia book's `xianxia:qi-meadow` terrain that maps to `TerrainKind::Grass` automatically inherits the `grass`-biome decoration pool.
- The 10 valid biome keys correspond exactly to `TerrainKind` variants. Chunk-B registry-load validation enforces this (any `biomes` entry not matching a known variant fails the load).

**Tests (4 new):**
- `default_registry_has_decoration_coverage_for_all_terrain_kinds` — assert for each `TerrainKind` variant `t`, `registry.decorations_for_terrain(t).len() >= 2`. Covers AC-DECO-12.
- `every_decoration_biome_key_is_known_terrain_kind` — for each decoration `ObjectKindDef`, every entry in `biomes` parses as a `TerrainKind` variant via serde (snake_case match). Registry-load fails with `RegistryError::Validation` if any unknown biome key appears.
- `decoration_by_biome_iteration_is_deterministic` — load registry twice from same TOML, iterate `decoration_by_biome`, assert key order is identical. Locks BTreeMap discipline.
- `xianxia_decoration_parallel_loads_clean` — load xianxia_sample.toml, assert `decorations_for_terrain` returns ≥2 results for each TerrainKind variant in the xianxia namespace.

**ACs satisfied:** AC-DECO-3 (≥28 tags), AC-DECO-12 (all 10 biomes covered, validated at load-time).

**PR title:** `feat(tilemap): registry decoration tags (~30 default + ~30 xianxia) + ObjectKindDef.biomes field (chunk B)`

---

## Chunk C — placer logic with per-tag min_spacing + fallback (M, /amaw recommended)

**Files (1 modify, 1 modify-helper, 0 new):**
- MODIFY `services/tilemap-service/src/engine/modificators/decoration_placer.rs` — replace early-return body with real placement logic. ~220 LOC.
- MODIFY `services/tilemap-service/src/types/tile_mask.rs` — add `pub fn sample_set(&self, rng: &mut impl rand::Rng) -> Option<TileCoord>` helper. Internally collects `iter_set()` into a small Vec then indexes — O(n) per call (bounded by zone tile count; acceptable per spec §11 perf budget). Returns `None` on empty mask. ~15 LOC.

**Ground-truth references (verified pre-chunk against actual code):**
- `ModificatorContext { template, grid, seed: TilemapSeed, state, registry }` per [pipeline/modificator.rs:23-39](services/tilemap-service/src/engine/pipeline/modificator.rs#L23-L39). The seed lives on **ctx, not template**.
- `TilemapBuildState.zone_terrain: Vec<Option<TerrainKind>>` per [build_state.rs:38](services/tilemap-service/src/engine/build_state.rs#L38). Zone's terrain is read via `ctx.state.zone_terrain[zone_idx]`, NOT via a `terrain_type` field on `ZoneBuildState`.
- `ZoneBuildState { id: ZoneId(String), role, center, assigned_tiles, free_paths }` per [build_state.rs:20-26](services/tilemap-service/src/engine/build_state.rs#L20-L26). `zone_id` is a `String` newtype, not `u32`.
- Existing placers use `ctx.state.object_placements.push(TilemapObjectPlacement { ... })` directly — no `add_decoration` accessor. Example: [obstacle_placer.rs:451](services/tilemap-service/src/engine/modificators/obstacle_placer.rs#L451).
- Seed derivation pattern: `ChaCha8Rng::seed_from_u64(sub_seed(ctx.seed, &format!("decoration_placer:{}", zone_id.0)))` matches [treasure_placer.rs](services/tilemap-service/src/engine/modificators/treasure_placer.rs)'s `sub_seed(ctx.seed, &format!("treasure_placer:{}", zone_id.0))`. `sub_seed` defined at [seed.rs:72](services/tilemap-service/src/seed.rs#L72).

**Algorithm (corrected — verified against actual API):**
```rust
fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
    let Some(density) = ctx.template.decoration_density else { return Ok(()) };

    for zone_idx in 0..ctx.state.zones.len() {
        // Per-zone setup. Note: zone_id is ZoneId(String), not u32.
        let zone_id = ctx.state.zones[zone_idx].id.clone();

        // V2 lookup: TerrainKind enum → biome key string (snake_case) → pool.
        // Unknown-terrain zones skip silently (defensive; logs warn).
        let Some(terrain) = ctx.state.zone_terrain[zone_idx] else {
            tracing::warn!(zone = ?zone_id, "decoration_placer: zone has no terrain; skipping");
            continue;
        };
        let pool = ctx.registry.decorations_for_terrain(terrain);
        if pool.is_empty() {
            tracing::debug!(zone = ?zone_id, ?terrain, "decoration_placer: empty pool for terrain; skipping");
            continue;
        }

        // Build the "free for decorations" mask.
        // Start: zone's OPEN region (already excludes free_paths via build_state init).
        let mut free = ctx.state.zone_area_open(zone_idx);

        // Subtract every prior placement's FULL FOOTPRINT (not just anchor):
        // Town is 4×4, Mine is 2×2, etc. per V2 ADR.
        for placement in &ctx.state.object_placements {
            let footprint = placement
                .footprint
                .as_ref()
                .copied()
                .unwrap_or(FootprintSize::unit());
            for dy in 0..footprint.height {
                for dx in 0..footprint.width {
                    let t = TileCoord {
                        x: placement.anchor.x.saturating_add(dx),
                        y: placement.anchor.y.saturating_add(dy),
                    };
                    free.clear(t); // TileMask::clear is the existing setter→0 op
                }
            }
        }
        // Subtract road + river polylines (every waypoint, not just endpoints).
        for road in &ctx.state.road_segments {
            for &t in &road.waypoints { free.clear(t); }
        }
        for river in &ctx.state.river_segments {
            for &t in &river.waypoints { free.clear(t); }
        }
        // Zone center is already a treasure-pile anchor in most templates,
        // but defensive subtract:
        free.clear(ctx.state.zones[zone_idx].center);

        let target = density.target_for(free.count_ones() as u32);
        if target == 0 { continue; }

        // Deterministic per-zone RNG sub-stream. ZoneId.0 is the &str inside.
        // sub_seed already composes ctx.seed + label → u64; we add seed_offset
        // implicitly because sub_seed reads ctx.seed which already folds seed_offset
        // at the place_tilemap entry (verify via engine/mod.rs:64).
        let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(
            ctx.seed,
            &format!("decoration_placer:{}", zone_id.0),
        ));

        // Per-tag placed anchors. BTreeMap (NOT HashMap) — iteration is
        // deterministic, locking determinism golden against future code that
        // iterates this map.
        let mut placed_by_tag: BTreeMap<String, Vec<TileCoord>> = BTreeMap::new();

        let mut placed: u32 = 0;
        let max_tries_per_slot = compute_max_tries(free.count_ones());
        // Heuristic: max_tries = max(8, min(64, free_count / 4))
        // Documented bound — prevents starvation on dense zones, prevents
        // CPU blow-up on huge zones.

        'slot: while placed < target {
            // Weighted tag roll (density_weight from DecorationRef).
            let mut current_tag = roll_weighted_tag(pool, &mut rng);
            let mut fallback_attempts = 0u32;
            const MAX_FALLBACK_ATTEMPTS: u32 = 3;

            loop {
                // Try this tag up to max_tries times.
                let mut tries = 0u32;
                let mut placed_here = false;
                while tries < max_tries_per_slot {
                    let Some(candidate) = free.sample_set(&mut rng) else {
                        break 'slot; // free mask exhausted — give up gracefully
                    };
                    let placed_for_tag = placed_by_tag
                        .entry(current_tag.kind_id.clone())
                        .or_default();
                    if chebyshev_min_distance(placed_for_tag, candidate)
                        >= current_tag.min_spacing
                    {
                        ctx.state.object_placements.push(TilemapObjectPlacement {
                            kind: TilemapObjectKind::Decoration,
                            anchor: candidate,
                            canon_ref: None,
                            biome_object_type: None,
                            primitive: Some(ObjectPrimitive::Decoration),
                            tag: Some(current_tag.kind_id.clone()),
                            footprint: Some(FootprintSize::unit()),
                            orientation: None,
                            properties: None,
                            value: None,
                        });
                        placed_for_tag.push(candidate);
                        free.clear(candidate);
                        placed += 1;
                        placed_here = true;
                        break;
                    }
                    tries += 1;
                }
                if placed_here { break; }

                // Fallback: switch to a strictly lower-min_spacing tag from the
                // pool. ACTUALLY ITERATE — not a comment.
                let Some(fallback) = pool.iter()
                    .filter(|t| t.min_spacing < current_tag.min_spacing)
                    .min_by_key(|t| t.min_spacing)
                else {
                    break; // no fallback exists; give up this slot
                };
                fallback_attempts += 1;
                if fallback_attempts >= MAX_FALLBACK_ATTEMPTS { break; }
                current_tag = fallback;
                // Loop continues with the lower-spacing tag, fresh `tries=0`.
            }

            if !placed_here { /* slot failed — accept under-shoot per AC-DECO-11 */ }
        }
    }
    Ok(())
}

fn compute_max_tries(free_count: usize) -> u32 {
    ((free_count / 4) as u32).clamp(8, 64)
}

fn roll_weighted_tag<'a>(pool: &'a [DecorationRef], rng: &mut impl rand::Rng) -> &'a DecorationRef {
    let total: f32 = pool.iter().map(|r| r.density_weight).sum();
    let mut roll = rng.gen_range(0.0..total);
    for r in pool {
        roll -= r.density_weight;
        if roll <= 0.0 { return r; }
    }
    pool.last().expect("non-empty pool checked above")
}

fn chebyshev_min_distance(placed: &[TileCoord], candidate: TileCoord) -> u32 {
    placed.iter()
        .map(|p| {
            let dx = (p.x as i32 - candidate.x as i32).abs() as u32;
            let dy = (p.y as i32 - candidate.y as i32).abs() as u32;
            dx.max(dy)
        })
        .min()
        .unwrap_or(u32::MAX) // empty placed = no constraint
}
```

**Per-zone seed determinism:** `sub_seed(ctx.seed, "decoration_placer:{zone_id}")` is collision-safe with V3 placement engine because `sub_seed`'s blake3 input format is `seed.to_le_bytes() || b"|" || label.as_bytes()` (see [seed.rs:72-86](services/tilemap-service/src/seed.rs#L72-L86)) — the `|` separator + placer name prefix means `treasure_placer:foo` and `decoration_placer:foo` derive to completely different sub-seeds. No collision risk.

**seed_offset composition:** `ctx.seed` already incorporates `template.seed_offset` at the `place_tilemap_with_registry` entry (verify in chunk-A by reading engine/mod.rs:64 → confirm where seed_offset folds in). Decoration placer inherits this composition automatically.

**Tests (7 new) + 1 snapshot pin:**
- `decoration_density_bounds` — for each tier × 5 seeds: `min ≤ count ≤ max`. AC-DECO-4.
- `decoration_walkability_preserved` — for each fixture, A* path from zone center to opposite reachable corner stays valid after placement. AC-DECO-5.
- `decoration_biome_filter_correct` — every placement with `primitive == Decoration`, the tag's `biomes` list contains the zone's terrain's serde_name. AC-DECO-6.
- `decoration_per_tag_spacing_enforced` — for every pair of placements `(a, b)` with same kind_id: Chebyshev distance ≥ that kind's `min_spacing`. AC-DECO-10.
- `decoration_fallback_under_shoot_bounded` — pathological registry (one tag at min_spacing=20, one cluster tag at min_spacing=0) → fallback to cluster tag → final count within 10% of target. AC-DECO-11.
- `decoration_does_not_overlap_existing_footprints` (NEW per MED-2 fix) — assert no decoration anchor lies inside any prior placement's footprint rectangle (e.g. a Town's interior). Locks footprint-aware subtraction.
- `decoration_with_world_zone_snapshot` (NEW per LOW-2) — fixture template with both `world_zone: Some(...)` AND `decoration_density: Some(TOWN_DEFAULT)` — assert all four invariants (bounds, walkability, biome filter, per-tag spacing) still hold.
- `decoration_with_biome_selection_rules` (NEW per LOW-3) — fixture template with `ZoneSpec.biome_selection_rules: Some(non_default)` + decoration_density Some — same invariants.

**Snapshot pin (1 new, with sanity-validation gate):**
- `decoration_v3_default_town_pinned_hash` — fixture template `(default_template + decoration_density = TOWN_DEFAULT (20-40, 0.10), seed=2026, default_registry)` → produce TilemapView → assert `blake3(canonical_bytes) == [pinned 32-byte literal]`. AC-DECO-7.
- **Pin generation discipline (per MED-7):** before committing the literal, run the produced TilemapView through AC-DECO-4 + AC-DECO-5 + AC-DECO-6 assertions IN THE SAME COMMIT'S TEST FILE. The snapshot literal is only committed once the produced view independently passes those three invariant checks. This prevents pinning a buggy output.

**Determinism check:**
- All existing tests still pass byte-identical (every existing template fixture has `decoration_density: None`).

**ACs satisfied:** AC-DECO-4, 5, 6, 7, 10, 11.

**PR title:** `feat(tilemap): decoration_placer placement logic + per-tag spacing + fallback (chunk C) [M, /amaw]`

**/amaw rationale (per LOW-5):** load-bearing — pins V3 quality-path determinism golden permanently (AC-DECO-7). Specific adversarial questions for /amaw to address:
1. Does the fallback loop's `fallback_attempts` bound actually terminate when every pool tag has min_spacing > 0?
2. Is the `max_tries_per_slot` heuristic correctly bounded on extreme zone sizes (1×1 zone test, 256² zone test)?
3. Does `sub_seed(ctx.seed, "decoration_placer:{zone_id}")` have a collision risk with future placers that include `decoration_placer` in a label suffix?
4. Footprint subtraction uses `saturating_add` — does this hide off-by-one bugs at the grid edge (placement at `x=grid.width-1` with footprint width=4 silently truncates to width=1)?
5. The `placed_by_tag` map uses BTreeMap but `pool` (`&[DecorationRef]`) is a slice with insertion order from chunk B's `from_file`. Is that order deterministic across registry-load runs?

---

## Chunk D — demo opt-in + frontend overlay + browser smoke (S)

**Files (4 modify, 0 new):**
- MODIFY the demo template fixture (likely `frontend-game/src/game/scenes/PreloaderScene.ts` or `play.tsx`'s `DEFAULT_*` consts — verify before chunk D) — set `decoration_density: Some(TOWN_DEFAULT)` for the demo template the frontend sends to `/internal/v1/tilemaps/render`. ~3 LOC.
- MODIFY `frontend-game/src/game/render/object-overlay.ts` — add rendering branch for `primitive: Decoration` placements. Use a single placeholder sprite per `TerrainKind` (small gray dot, colored square, or low-res CC0 sprite) initially; real sprites come from a chunk-D follow-on (per spec §13 stop-condition discipline). ~30 LOC.
- MODIFY `frontend-game/src/components/viewer/MetadataPanel.tsx` — add a `decorations: <count>` Row alongside the existing `placements`, `roads / rivers`, `crossings` rows (per [MetadataPanel.tsx:23](frontend-game/src/components/viewer/MetadataPanel.tsx#L23)). The count is `view.object_placements.filter(p => p.primitive === 'decoration').length`. ~5 LOC.
- MODIFY `frontend-game/e2e/smoke.spec.ts` — add `getByText(/decorations: (\d+)/)` assertion in `/play smoke — V1.2 viewer surface` test; parse the digit and assert ≥ 20. ~10 LOC.

**Frontend test pattern (per LOW-4 fix):**
- The smoke test queries `getByText(/decorations: \d+/)` on the MetadataPanel — pure React DOM, no Phaser scene introspection needed. The number is parsed via the matched group and asserted `>= 20`.
- This leverages the existing V1.2 viewer wiring (`MetadataPanel` already renders counts) so the e2e mechanism is consistent with `placements: N`, `roads / rivers: A / B`, `crossings: N` assertions that already work cross-browser.

**Browser smoke (manual + CI):**
- Manual: run `pnpm dev` + `cargo run --bin tilemap-service serve` locally, open `http://localhost:5174/play`, screenshot before-vs-after for PR description. Inspect MetadataPanel's `decorations: N` row + visual canvas density.
- CI: smoke.spec.ts `decorations: ≥ 20` assertion runs in `frontend-game cross-browser e2e (AC-FG-16)` job (already green per merged PR #6 + commit 8b7811f4 firefox-fix).

**ACs satisfied:** AC-DECO-8 (browser smoke ≥ 20 visible), AC-DECO-9 (all 433 + 49 tests green).

**PR title:** `feat(frontend-game + tilemap): decoration overlay rendering + MetadataPanel count + demo opt-in + browser smoke (chunk D)`

---

## Cross-chunk discipline

**Branch:** all 4 chunks ship on `mmo-rpg/zone-map-decoration-placer` (NEW, off main). Single PR per chunk; merge sequentially. Do not bundle.

**Determinism gate (every chunk):** run full test suite locally before opening PR. Look for ANY golden snapshot diff — if found, stop and root-cause; do not rebaseline.

**Spec amendments:** if implementation reveals the spec is wrong (e.g. the per-tag spacing fallback algorithm is too aggressive and under-shoots > 10%), update the spec in the same PR as the fix. Do not silently diverge from spec text.

**Stop condition (post-D):** browser smoke + PO eyeball — if "feels full," stop. Other quality themes deferred. If "still empty in spots," tune Q1 density values in `template.rs` constants (no code re-ship needed) before drafting any new ADR.

**/amaw usage:** chunk C only. Chunks A/B/D are additive scaffold with low risk. Chunk C's /amaw should specifically address the 5 questions listed in chunk C's "/amaw rationale" section (loop termination, max_tries bounds, seed collision, saturating_add edge, pool ordering determinism).

**Pre-chunk-A ground-truth gate (per v2 revision):** read the 9 file:line references in the "Ground-truth verification table" at the top of this plan. Confirm each assumption matches actual code. If any drifts (e.g. someone refactored ModificatorContext between this plan and chunk A's implementation), STOP and revise this plan first — do not silently work around. This gate is a forcing function against the v1 anti-pattern of specifying an algorithm against hypothetical types.

**Estimated session count:** A in <1 session (skeleton + 5 pipeline registrations + 1 V2-preservation test) · B in 1 session (mostly TOML drafting + new ObjectKindDef.biomes/density_weight fields + Registry biome index) · C in 1-2 sessions (load-bearing algorithm + 7 invariant tests + snapshot pin with sanity-validation gate) · D in 1 session (MetadataPanel `decorations:` row + e2e count assertion + manual screenshot). **Total: 4-5 sessions.**
