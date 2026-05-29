# Chunk A — Biome-Theme Types + Registry (TMP-Q2)

**Spec:** [`docs/specs/2026-05-29-biome-theme-painter.md`](../specs/2026-05-29-biome-theme-painter.md)
**Size:** L (9 files / 5 logic / 1 side-effect = Cargo.toml dep add)
**Goal:** Land all type + registry plumbing. Placer NOT added (chunk B).
V2 byte-identical golden preserved.

## File list (9 files)

| # | File | Action | Lines | Purpose |
|---|---|---|---|---|
| 1 | `services/tilemap-service/Cargo.toml` | MOD | +1 | `noise = "0.9"` exact pin |
| 2 | `services/tilemap-service/src/types/biome_theme.rs` | NEW | ~120 | `BiomeThemeDef`, `BiomeMixEntry`, `BiomeThemeError`, `validate()` |
| 3 | `services/tilemap-service/src/types/mod.rs` | MOD | +1 | `pub mod biome_theme;` |
| 4 | `services/tilemap-service/src/registry.rs` | MOD | ~80 | `biome_by_id: BTreeMap<String, BiomeThemeDef>` + load + validation + getter + `RegistryFile.biome` |
| 5 | `services/tilemap-service/src/types/template.rs` | MOD | +6 | `TilemapTemplate.background_biome`, `ZoneSpec.biome_theme` (both `Option<String>` opt-in) |
| 6 | `services/tilemap-service/registry/default.toml` | MOD | +60 | 7 `[[biome]]` entries (forest_temperate, forest_dense_pine, mountain_alpine, swamp_mangrove, desert_dune, grassland_meadow, tundra_frost) |
| 7 | `services/tilemap-service/registry/xianxia_sample.toml` | MOD | +60 | parallel 7 `xianxia:biome.*` entries |
| 8 | `services/tilemap-service/tests/biome_theme_v2_preservation.rs` | NEW | ~100 | AC-BIOME-1 V2 byte-identical assertion |
| 9 | `services/tilemap-service/src/types/template.rs` (tests block) | MOD | +50 | ZoneSpec + Template round-trip tests for new fields (within existing file) |

**Migration script:** None. Adding `Option<>` field is serde-default `None`;
no fixture rewrites required (V2 discipline already proven by
DecorationPlacer chunk A).

## Invariants (V2 preservation)

1. **Default-None serializes invisibly** — assert
   `!serde_json::to_string(&template).contains("background_biome")` when None
2. **Default-None deserializes from missing field** — assert
   `serde_json::from_str(pre_chunk_json).unwrap().background_biome.is_none()`
3. **Registry-load with empty `[[biome]]` array works** — backwards-compat
   for the default registry until chunk B adds entries (will land in
   same commit so this is bare-min compile, but the safety net stays)
4. **Per-book registries with NO biome section still load** — `RegistryFile.biome` is `#[serde(default)]`

## Validation (chunk-A scope)

`BiomeThemeDef::validate()` runs at `Registry::from_file` time, rejects:

| Failure | Error variant | Reason |
|---|---|---|
| `mix.is_empty()` | `EmptyMix` | placer cannot sample from empty pool |
| `weight.is_finite() == false` | `NonFiniteWeight { idx, value }` | CDF arithmetic would propagate NaN/Inf |
| `weight <= 0.0` | `NonPositiveWeight { idx, value }` | zero-weight entry can never be picked silently; treat as author error |
| unknown `TerrainKind` tag | `UnknownTerrain { idx, tag }` | reuse `is_valid_biome_key` from registry.rs |
| duplicate `terrain` key | `DuplicateTerrain { tag }` | silent dedup would change weights |

`id` format validation reuses existing `is_valid_id` from registry.rs.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `biome_theme_def_validates_well_formed` | biome_theme.rs (unit) | All `lw:biome.*` entries from default.toml pass validate() |
| `biome_theme_def_rejects_empty_mix` | biome_theme.rs (unit) | `EmptyMix` error |
| `biome_theme_def_rejects_non_finite_weight` | biome_theme.rs (unit) | NaN/Inf/-Inf all rejected |
| `biome_theme_def_rejects_non_positive_weight` | biome_theme.rs (unit) | 0.0 and -1.0 rejected |
| `biome_theme_def_rejects_unknown_terrain` | biome_theme.rs (unit) | "atmosphere" rejected |
| `biome_theme_def_rejects_duplicate_terrain` | biome_theme.rs (unit) | two entries with `terrain = "grass"` rejected |
| `biome_theme_def_round_trips` | biome_theme.rs (unit) | serde round-trip |
| `registry_loads_default_toml_with_biomes` | registry.rs (existing test mod) | `Registry::load_default().biome_count() == 7` |
| `registry_rejects_unknown_biome_id_format` | registry.rs | `id = "INVALID"` rejected via `is_valid_id` |
| `registry_rejects_duplicate_biome_id` | registry.rs | two `[[biome]]` with same id rejected |
| `tilemap_template_deserializes_without_background_biome` | template.rs (existing test mod) | AC-BIOME-1: None default |
| `tilemap_template_round_trips_with_background_biome_some` | template.rs | round-trip non-None |
| `zone_spec_deserializes_without_biome_theme` | template.rs | None default |
| `zone_spec_round_trips_with_biome_theme_some` | template.rs | round-trip non-None |
| `v2_template_terrain_layer_byte_identical_pre_chunk` | tests/biome_theme_v2_preservation.rs (NEW) | AC-BIOME-1: full `place_tilemap` over a representative template (no biome_theme fields) produces same `terrain_layer` bytes pre/post chunk A |

## Pipeline non-effect (chunk A only)

- No `BiomeThemePainter` modificator added.
- `Registry.biome_by_id` exists but is unused by any placer.
- `TilemapTemplate.background_biome` / `ZoneSpec.biome_theme` exist but
  no placer consumes them yet.
- This means chunk A produces ZERO behavior change for any input. V2
  golden tests pass trivially.

## Risk register (chunk-A-specific)

| Risk | Mitigation |
|---|---|
| `noise` crate's transitive deps balloon binary size | Verified `noise 0.9` deps are pure-Rust, ~30KB; spot-check `cargo tree -p tilemap-service` after add |
| TOML `[[biome]]` parsing collides with other `biome` key (no such key today, future-proofing) | Audit registry: no top-level `biome` key exists; `[biome_selection_rules]` is nested inside `[[zones]]` of templates, not registry |
| Lockfile churn in workspace's `Cargo.lock` if `noise` pulls upstream version bumps | Use exact pin `noise = "=0.9.0"` (not `^0.9`) to freeze |
| `xianxia_sample.toml` 60-line addition trips a typo on a single TerrainKind tag, breaking xianxia_sample registry-load test | All terrain tags constrained to closed set; copy default.toml entries, change only ids + labels |

## Out of scope (later chunks)

- Placer logic (chunk B)
- `noise::Perlin` actual use (chunk B)
- Frontend MetadataPanel biome count (chunk C)
- minimal.json demo opt-in (chunk C)
