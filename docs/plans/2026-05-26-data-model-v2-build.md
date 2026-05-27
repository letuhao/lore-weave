# V2 Data Model — BUILD plan

> ADR: [`docs/specs/2026-05-26-data-model-v2-registry-footprint.md`](../specs/2026-05-26-data-model-v2-registry-footprint.md)
> Branch: `mmo-rpg/zone-map-amaw` (continuation; V1 viewer + V2 land 1 PR)
> Size: XL — 4 batches, est. 5–7 days realistic

## Batch 3.0 — Primitive types + Registry foundation (backend, ~2 days)

Goal: closed primitive enums + registry types + default TOML registry +
loader, all behind feature-equivalent backward compat (default-registry
output structurally matches V1 except new shape fields). Existing
TerrainKind/TilemapObjectKind ENUM REPLACED, callers migrated step-by-step.

### Steps

1. **New primitive enums** — `services/tilemap-service/src/types/primitive.rs`
   - `TerrainPrimitive { Land, Water, Wall, Path, Void }`
   - `ObjectPrimitive { Pickup, Habitable, Blocker, Trigger, Decoration }`
   - Helper `is_walkable_default(self) -> bool`
   - Unit tests: serde round-trip, exhaustive coverage

2. **Registry def structs** — `services/tilemap-service/src/types/registry.rs`
   - `TerrainKindDef`, `ObjectKindDef`, `WalkabilityPattern`, `Direction`
   - Derives serde + PartialEq + Clone
   - Validation: `id` matches regex `^[a-z][a-z0-9_:-]*$`
   - Unit tests: TOML round-trip, property bag deserializes

3. **Registry container + loader** — `services/tilemap-service/src/registry/mod.rs`
   - `TerrainRegistry`, `ObjectRegistry` (HashMap-backed)
   - `load_default()` reads embedded TOML via `include_str!`
   - `load_from_yaml(path)` for file-based registries
   - `get`, `primitive`, `all_tags`, `validate` methods
   - Unit tests: missing tag fallback, validation errors

4. **Default registry TOML** — `services/tilemap-service/registry/default.toml`
   - All 10 current terrain kinds (`lw:grass`, `lw:forest`, ..., `lw:subterranean`)
   - All 9 current object kinds (`lw:treasure`, ..., `lw:ferry`)
   - 9 obstacle subtypes (`lw:obstacle.mountain`, `lw:obstacle.tree`, ...)
   - Each entry: primitive + label + footprint + walkability_pattern + properties
   - Schema: version `1.0.0`; namespace `lw:`

5. **`TileMaskCellv2`** — replace `TerrainKind` u8 in `TilemapView`
   - New: `TerrainCell { primitive, tag }` in `types/tile.rs`
   - `TilemapView.terrain_layer: Vec<TerrainCell>` (was `Vec<u8>`)
   - Existing serde `terrain_layer` field name kept — wire shape break is
     only in element type
   - Update tile_mask.rs callers if any (audit)

6. **`TilemapObjectPlacement`** — extend with footprint + primitive + tag
   - Add `primitive: ObjectPrimitive`, `tag: String`, `footprint: GridSize`,
     `orientation: Direction`, `properties: serde_json::Value`
   - Remove `kind: TilemapObjectKind`, `biome_object_type` (subsumed by tag)
   - Test fixtures audit (golden + integration)

7. **`AppState` carries registries** — load at boot
   - `AppState { internal_token, terrain_registry, object_registry }`
   - `main.rs` calls `load_default()` for both
   - Handler reads from `State<AppState>` (existing pattern)

8. **Wire test** — POST to render endpoint with default registry returns
   new shape; integration test asserts presence + types

9. **Unit test backfill** — all new types: serde round-trip, registry
   lookup, TOML parse error paths
   - Target: +20 unit tests

### Out of Batch 3.0
- Placer using registry (still match old kind via shim during this batch — but old kind goes away anyway, so use registry directly from step 1)
- Wait — actually that's wrong; placer must use new types. Move placer
  refactor into Batch 3.0 if practical. Re-check after step 7.

→ **Cleaner ordering: Batch 3.0 ships types + registry + loader + wire shape
ONLY. Batch 3.1 ships placer refactor. In between, placers reference
`UNIMPLEMENTED_TODO` shim — backend doesn't compile until 3.1 is done.
That breaks the "always compilable" rule. Reconsider.**

**Revised approach: Batches 3.0 + 3.1 land together** in a single mega-
commit because they form one indivisible refactor. Split is artificial —
backend can't function with new types but old placer. Plan as 1 commit.

## Batch 3.0+3.1 (combined) — Backend refactor (~3-4 days)

### Steps (continuing from 3.0 above)

10. **Placer refactor** — `engine/object_manager.rs` + modificators
    - `place_and_connect_object` accepts `&ObjectRegistry`
    - Looks up `kind_def` by tag
    - Computes footprint occupancy + walkability map updates
    - Rejection: any footprint tile occupied → reject
    - min_spacing enforcement via Chebyshev distance check

11. **Modificators refactor** — each modificator that creates
    placements switches from `TilemapObjectKind::X` literal to a tag
    string + registry lookup:
    - `treasure_placer.rs`: tag `"lw:treasure"`
    - `obstacle_placer.rs` + `obstacle_source_placer.rs`: tag like
      `"lw:obstacle.mountain"`, `"lw:obstacle.tree"`
    - `connections_placer.rs`: monolith + portal etc.
    - `river_placer.rs`: ferry crossings
    - `road_placer.rs`: bridge tags

12. **Biome library** — `biome_library.rs` rewrite
    - Read terrain affinity from registry properties (not hard-coded)
    - Build biome→[tag with weights] table at registry-load time
    - Per-zone terrain selection unchanged in behavior; data-driven now

13. **L4 prompt harness** — `harness/l4_prompt.rs` uses tag strings
    not enum variants

14. **Golden test rebaseline** — `tests/golden/tilemap_baseline.json`
    re-generated; diff'd to confirm only new-shape fields differ
    (coordinates byte-identical for same seed)

15. **Integration tests** — `tests/http_integration.rs` updated for new
    wire shape; +new tests for registry-driven render

16. **Determinism test** — `tests/determinism.rs` updated; same seed +
    same registry → same view (incl. new fields)

17. **Run all 332+ tests** — fix every failure to use new types/tags

### Backend test target: 350+ tests passing (+18 from baseline)

## Batch 3.2 — Frontend (~1 day)

Frontend consumes new wire shape. Same commit as backend (single PR;
break wire alignment in lock-step).

### Steps

1. TS types mirror — `src/types/tilemap.ts`
   - `TerrainPrimitive` + `ObjectPrimitive` enums
   - `TerrainKindDef` + `ObjectKindDef` interfaces
   - `TerrainCell { primitive, tag }`
   - `TilemapObjectPlacement` updated
   - `RegistryRef { id, version }`

2. Registry fetch — `src/api/registry-client.ts` (NEW)
   - `useDefaultRegistry()` — fetch + cache `/v1/tilemaps/registry/default`
   - (Stub for now; HTTP endpoint added in Batch 3.0 if backend allows)
   - If backend doesn't ship registry endpoint yet → frontend hardcodes
     default-registry mirror as fallback

3. Sprite mapping — `src/game/render/object-overlay.ts`
   - `spriteForPlacement(tag, primitive)` — tag → asset key with
     primitive-based fallback for unknown tags (e.g.
     `primitive=Blocker` → generic-rock placeholder)
   - Sprite size = `footprint.width × TILE_PX` (deterministic, no tier
     guessing; tier table archived in spec for sprite-art selection)

4. WorldScene + foundation — use TerrainCell.tag for sprite key
   - Tileset frame index derived from registry tag → frame mapping
   - Backward-compat: default registry's `lw:grass`..`lw:subterranean`
     map to frames 0..9 (same order)

5. Click-to-walk — InputSystem reads walkability from registry
   - Tile walkability computed: terrain primitive walkability + any
     overlapping object placement's per-tile walkability_pattern
   - Tile marked Blocker → walkTo rejection (drop click)
   - Existing isInBounds check stays

6. TileInspector — shows tag, primitive, footprint, properties
   summary; richer than V1.2

7. parseTilemapView — updated for new shape; BigInt parser still
   needed for `assigned_tiles.bits`

8. Tests — frontend test update
   - object-overlay-mapping: re-test using tag strings instead of
     enum + biome_object_type tuples
   - new world-math + parseTilemapView coverage as needed

9. Bundle size verify — should stay under 700 KB gzip

## Batch 3.3 — Sample registry + verification (~1 day)

1. **Sample xianxia registry** — `services/tilemap-service/registry/
   xianxia-demo.toml`
   - 5 terrain: `xian:qi-meadow`, `xian:spirit-stream`, `xian:demon-blight`,
     `xian:cloud-step-cliff`, `xian:dao-vein-rough`
   - 5 object: `xian:dao-pillar`, `xian:elixir-garden`, `xian:sect-gate`,
     `xian:meridian-stone`, `xian:qi-condensing-tree`
   - Each maps to primitive + footprint + reuses default sprite as
     placeholder (or assigns a "fantasy-flavored" property)

2. **Backend `?registry=` query param** — `/internal/v1/tilemaps/render?registry=xianxia-demo`
   - Falls back to `default` if not provided
   - Returns matching `registry_ref`

3. **Frontend registry switcher** — temporary dev-only dropdown in
   /play sidebar to switch registries (out of scope normal UX, debug
   tool only)

4. **Browser smoke** — default render + xianxia render side-by-side
   verified; screenshot

5. **TMP_001 spec doc rewrite** — §2 (TerrainKind) + §5 (object
   placement) updated to reference V2 ADR + registry format

6. **SESSION_HANDOFF + DEFERRED**
   - Move #041 + #042 from DEFERRED → "Cleared 2026-05-26 V2 commit"
   - Document V2 limitations (LLM gen still #037, asset pipeline still
     #037, orientation field underused)
   - Update SESSION_HANDOFF with full V1.2 + V2 progression entry

7. **Final commit + push** — V2 mega-commit (or several mini-commits
   if natural breaks emerge during impl)

## Verification phase

- `cargo test -p tilemap-service` → ≥350 tests passing
- `pnpm --filter frontend-game test` → tests pass
- `pnpm --filter frontend-game build` → ≤700 KB gzip
- Browser smoke: default registry seed=1 renders ~equivalent to V1.2;
  xianxia registry renders distinct content; layer toggles + tile
  inspector work
- Determinism: same seed + same registry → same view repeatedly

## Definition of done (V2)

- All 21 ACs in ADR §5 pass
- Branch ready to PR `mmo-rpg/zone-map-amaw → main`
- V1.2 viewer + V2 data model land in one PR
- TMP_001 spec doc reflects V2 model
- 2 lessons saved cross-session (data-shape vs semantics; closed-enum
  fails multi-tenant)
