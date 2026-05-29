# Biome-Theme Painter — Quality-Push Theme #2 (TMP-Q2)

**Status:** DRAFT
**Author:** Claude (Opus 4.7) + letuhao1994 (PO)
**Created:** 2026-05-29
**Branch:** `mmo-rpg/zone-map-decoration-placer` (4-chunk arc continuation)
**Driver:** HoMM3 RMG comparison (`D:\Works\source\vcmi/lib/rmg/`) revealed
  single-tile zone fills produce flat, uniform terrain — no patches, no
  visual variety. Tale-of-Immortal aesthetic target needs correlated
  biome patches (forest with sparse meadow clearings, mountain with rock
  + dirt blend, swamp with water-marsh-grass mix).

---

## 1. Goal

Replace V2's "one `TerrainKind` per zone, every assigned tile painted same
kind" model with an opt-in **biome theme** system:

- **BiomeTheme** = weighted `Vec<(TerrainKind, weight)>` registry entry
  keyed by id (e.g. `lw:biome.forest_temperate`).
- **Zone override:** `ZoneSpec.biome_theme: Option<String>` references a
  registry id. When `Some(_)`, the placer samples per-tile via Perlin
  noise + threshold CDF. When `None`, V2 single-fill path runs unchanged.
- **Background fill:** `TilemapTemplate.background_biome: Option<String>`
  paints all non-zone tiles (currently `u8 = 0` void). When `None`,
  open-space stays void (V2 path).

V2 byte-identical golden tests stay green via additive `Option<>` +
`skip_serializing_if = "Option::is_none"` discipline.

## 2. Non-Goals

- Per-tile sprite blending / tile transitions (frontend renderer concern,
  separate ticket).
- Voronoi-based biome boundaries (Perlin patches are simpler + good
  enough for V3.0; V3.1 may swap).
- Climate-driven biome selection (world-inheritance already covers
  template-level biome hints; this is purely visual density).
- Subterranean biomes (V3 underground separate work).

## 3. Acceptance Criteria

| ID | Criterion | Verifier |
|---|---|---|
| **AC-BIOME-1** | V2 templates (`biome_theme = None` everywhere) produce byte-identical `terrain_layer` to pre-chunk baseline | Cargo test `biome_theme_v2_preservation` — hashes pre/post terrain_layer |
| **AC-BIOME-2** | `BiomeTheme.mix` registry-load rejects: empty `mix`, non-finite weight, weight ≤ 0, unknown `TerrainKind` tag, duplicate kind | Cargo unit tests on `BiomeTheme::validate` |
| **AC-BIOME-3** | `BiomeThemeDef` deserializes from TOML with `[[biome]]` array (mirrors `[[terrain]]` / `[[object]]` pattern) | Cargo unit test on `Registry::from_toml_str` |
| **AC-BIOME-4** | Zone with `biome_theme = Some("lw:biome.forest_temperate")` produces ≥ 2 distinct `TerrainKind` values across its assigned tiles (Perlin patches present) | Integration test counting distinct kinds in zone tiles |
| **AC-BIOME-5** | Template with `background_biome = Some("lw:biome.grassland_meadow")` produces 0 tiles with `u8 = 0` in the final `terrain_layer` | Integration test asserting no void tiles outside zones |
| **AC-BIOME-6** | Same `(template, seed)` → byte-identical `terrain_layer` across 100 runs (determinism axiom) | Cargo test running placer 100× over the same input |
| **AC-BIOME-7** | Per-zone Perlin pattern uncorrelated with neighbor zones (different sub-seeds) | Integration test asserting two zones with same theme have ≠ kind distributions modulo same fixed seed |
| **AC-BIOME-8** | Frontend `MetadataPanel` shows "biomes: N" count (number of zone tiles assigned via a biome theme) | Playwright e2e test (chunk C) |

## 4. Wire Shape (additive — V2 preserved)

### `TilemapTemplate` (template.rs)

```rust
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TilemapTemplate {
    // ... existing fields ...
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub background_biome: Option<String>,  // id into registry biome index
}
```

### `ZoneSpec` (template.rs)

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneSpec {
    // ... existing fields ...
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub biome_theme: Option<String>,  // id into registry biome index
}
```

### `BiomeThemeDef` (NEW — registry.rs)

```rust
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BiomeThemeDef {
    pub id: String,           // "lw:biome.forest_temperate"
    pub label: String,        // "Temperate Forest"
    pub mix: Vec<BiomeMixEntry>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BiomeMixEntry {
    pub terrain: String,      // TerrainKind::tag() value (snake_case)
    pub weight: f32,          // > 0, finite; relative density
}
```

### `RegistryFile` (registry.rs)

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegistryFile {
    pub registry: RegistryRef,
    #[serde(default)] pub terrain: Vec<TerrainKindDef>,
    #[serde(default)] pub object: Vec<ObjectKindDef>,
    #[serde(default)] pub biome: Vec<BiomeThemeDef>,  // NEW
}
```

### `Registry` index (registry.rs)

```rust
biome_by_id: BTreeMap<String, BiomeThemeDef>,
```

`BTreeMap` (not `HashMap`) for the same determinism reason as
`decoration_by_biome` — placer iteration order must be stable.

## 5. Algorithm (chunk B — placer)

Run **after** `TerrainPainter`, **before** `ConnectionsPlacer`. Pipeline
position locks in chunk B; chunk A only adds types + registry.

```
for each tile (x, y) in grid:
    if tile ∈ any zone with biome_theme = Some(id):
        theme = registry.biome_by_id[id]
        u_perlin = perlin(x, y, sub_seed("biome_theme:{zone_id}:perlin"))
        kind = sample_by_cdf(theme.mix, u_perlin)
        terrain_layer[i] = kind as u8
    else if tile ∉ any zone and template.background_biome = Some(id):
        theme = registry.biome_by_id[id]
        u_perlin = perlin(x, y, sub_seed("background_biome:perlin"))
        kind = sample_by_cdf(theme.mix, u_perlin)
        terrain_layer[i] = kind as u8
    // else: leave terrain_layer[i] as TerrainPainter wrote it
```

`sample_by_cdf` maps Perlin output `u ∈ [-1, 1]` → `[0, 1]` → picks the
mix entry whose cumulative weight ≥ u. Patches emerge because Perlin
output is spatially correlated (~3-8 tile patches at default frequency).

## 6. Registry Themes (chunk A — 5-8 themes per registry)

### Default (`lw:` prefix)

1. `lw:biome.forest_temperate` — 70% Forest / 20% Grass / 10% Rough (clearings)
2. `lw:biome.forest_dense_pine` — 85% Forest / 10% Snow / 5% Mountain
3. `lw:biome.mountain_alpine` — 70% Mountain / 20% Rough / 10% Snow
4. `lw:biome.swamp_mangrove` — 60% Swamp / 25% Water / 15% Grass
5. `lw:biome.desert_dune` — 80% Sand / 15% Rough / 5% Grass (oasis)
6. `lw:biome.grassland_meadow` — 75% Grass / 15% Forest / 10% Rough
7. `lw:biome.tundra_frost` — 70% Snow / 20% Rough / 10% Mountain

### Xianxia (`xianxia:` prefix)

Parallel xianxia: themes (`xianxia:biome.qi_forest_jade`, etc.) — same
TerrainKind primitives, xianxia label semantics.

## 7. Ground-Truth Verification Table (anti-hallucination)

Lesson `feedback_verify_api_against_code_before_specifying_algorithm`:
every referenced field/function MUST exist NOW.

| Algorithm reference | File:line | Verified exists? |
|---|---|---|
| `TilemapTemplate.background_biome` | template.rs:96 (struct) | NEW — adding |
| `ZoneSpec.biome_theme` | template.rs:23 (struct) | NEW — adding |
| `Registry.biome_by_id` | registry.rs:117 | NEW — adding |
| `RegistryFile.biome` | registry.rs:102 | NEW — adding |
| `BiomeThemeDef.validate()` | NEW | — |
| `TerrainKind::tag()` | types/tile.rs:48 | YES (used by decoration `is_valid_biome_key`) |
| `is_valid_biome_key` | registry.rs:83 | YES — reuse for terrain string → enum |
| `ChaCha8Rng + sub_seed` | seed.rs (used in terrain_painter.rs:85) | YES |
| `state.terrain_layer.len() == grid.area()` | build_state.rs:36 + 111 | YES |
| `assigned_tiles.iter_set()` | terrain_painter.rs:61 | YES |
| `noise::Perlin` | NOT ADDED | NEW — `noise = "0.9"` to Cargo.toml |

## 8. Chunk Plan

| Chunk | Size | Files | Scope |
|---|---|---|---|
| **A — types + registry** | L (~9 files) | This chunk: types/biome_theme.rs (NEW), Cargo.toml (+noise), registry.rs (BiomeThemeDef + biome_by_id + validation), template.rs (background_biome + ZoneSpec.biome_theme), default.toml + xianxia.toml (7 themes each), V2-preservation tests, ZoneSpec + Template round-trip tests | Skeleton + opt-in fields. V2 path byte-identical. Placer NOT added yet. |
| **B — placer logic** | L | biome_theme_painter.rs (NEW), engine/mod.rs (register at 5 sites), modificators/mod.rs (export), integration tests + AC-BIOME-1..7, snapshot pin | Perlin sampler + threshold CDF + background pass + zone override |
| **C — frontend + smoke** | M | minimal.json (opt-in demo), MetadataPanel (biome count Row), smoke.spec.ts (AC-BIOME-8) | Demo + browser smoke |

## 9. Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Perlin determinism cross-platform — `noise` crate uses `permutation_table_size(0)` seed; different OS may produce different bytes | Pin to `noise = "0.9"` exact version; integration test asserts byte-identical output on CI's Linux + my Windows; add cross-OS verification job if drift detected |
| `BTreeMap<String, BiomeThemeDef>` clone-on-lookup if `BiomeThemeDef.mix` grows large | `mix` is small (3-5 entries); `&BiomeThemeDef` returned by getter, no clone |
| Open-space painting interacts with `RoadPlacer` (roads override terrain in-place) | RoadPlacer runs AFTER terrain layers in the pipeline; roads will overwrite biome-painted tiles correctly (existing pattern preserved) |
| `terrain_layer[i] = 0` after biome paint for non-TerrainKind values | All BiomeMixEntry.terrain MUST be a valid TerrainKind::tag() value; registry-load rejects unknown |
| Frontend renderer breaks on patched terrain | Renderer already handles per-tile distinct TerrainKind (V2 supports it via `terrain_vocabulary`); biome paints just produce more variety |

## 10. Open Questions

None — all PO decisions locked inline this session (see commit message
referencing this spec).
