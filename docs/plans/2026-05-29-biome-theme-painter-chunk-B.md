# Chunk B — BiomeThemePainter (Perlin sampler + placer logic)

**Spec:** [`docs/specs/2026-05-29-biome-theme-painter.md`](../specs/2026-05-29-biome-theme-painter.md)
**Chunk A:** committed at `159b7bca` (types + registry + 7 themes + V2 hash pin)
**Size:** L (~4 files / 4+ logic / 1 side-effect = `engine/mod.rs` pipeline registration)
**Goal:** Implement the Perlin-noise CDF-threshold per-tile placer. Run AFTER `TerrainPainter`, BEFORE `ConnectionsPlacer`. V2 byte-identical preserved when both opt-in fields are `None`.

## Algorithm

```
fn process(ctx):
    // Early-return: no biome work at all → trivially V2-identical
    if template.background_biome.is_none() &&
       all zones have biome_theme == None:
        return Ok(())

    // Pass 1 — Zone overrides (OVERWRITE TerrainPainter's single-fill)
    for zone in state.zones:
        let id = zone.biome_theme.as_ref()?  // skip if None
        let theme = ctx.registry.get_biome(id) else continue  // silent no-op
        let perlin = Perlin::new(seed_u32_for("biome_theme:{zone.id}:perlin"))
        for tile in zone.assigned_tiles.iter_set():
            let u = perlin.get([tile.x * SCALE, tile.y * SCALE])  // [-1, 1]
            let kind = sample_by_cdf(&theme.mix, u)
            terrain_layer[tile.flat_index(width)] = kind as u8

    // Pass 2 — Background fill (only TILES NOT in any zone, i.e. u8 == 0)
    if let Some(id) = &template.background_biome:
        let theme = ctx.registry.get_biome(id) else return Ok(())
        let perlin = Perlin::new(seed_u32_for("background_biome:perlin"))
        for i in 0..terrain_layer.len():
            if terrain_layer[i] != 0:
                continue   // already painted by TerrainPainter or Pass 1
            let (x, y) = (i % width, i / width)
            let u = perlin.get([x * SCALE, y * SCALE])
            let kind = sample_by_cdf(&theme.mix, u)
            terrain_layer[i] = kind as u8

    Ok(())
```

### `seed_u32_for(label)` — sub_seed → u32

`sub_seed(seed, label)` returns `u64`. `noise::Perlin::new(u32)` needs `u32`.
XOR-fold the upper + lower halves to preserve all bits:

```rust
fn seed_u32_for(seed: TilemapSeed, label: &str) -> u32 {
    let s64 = sub_seed(seed, label);
    ((s64 >> 32) as u32) ^ (s64 as u32)
}
```

### `sample_by_cdf(mix, u_perlin)` — CDF threshold

```rust
fn sample_by_cdf(mix: &[BiomeMixEntry], u: f64) -> TerrainKind {
    // Perlin u ∈ ~[-1, 1] → [0, 1) (clamped, then half-open)
    let normalized = ((u + 1.0) * 0.5).clamp(0.0, 0.999_999_99);
    let total: f64 = mix.iter().map(|e| e.weight as f64).sum();
    let threshold = normalized * total;
    let mut cum = 0.0;
    for entry in mix {
        cum += entry.weight as f64;
        if cum > threshold {
            return TerrainKind::from_tag(&entry.terrain)
                .expect("validated at registry-load");
        }
    }
    // Defensive: float roundoff at u ≈ 1.0 might bypass the loop;
    // return the last entry's kind.
    TerrainKind::from_tag(&mix.last().unwrap().terrain)
        .expect("validated at registry-load")
}
```

### `SCALE` — Perlin frequency

Perlin's coherence length is ~1 unit. To get ~8-tile patches, sample
spaced 0.125 units apart in noise space:

```rust
const BIOME_PERLIN_SCALE: f64 = 0.125;
```

Tunable later via per-theme override (V3.1 if needed).

## File list (4 files)

| # | File | Action | Lines | Purpose |
|---|---|---|---|---|
| 1 | `services/tilemap-service/src/types/tile.rs` | MOD | +30 | NEW `TerrainKind::from_tag(&str) -> Option<Self>` + unit test |
| 2 | `services/tilemap-service/src/engine/modificators/biome_theme_painter.rs` | NEW | ~200 | The placer (Modificator impl + helpers + unit tests) |
| 3 | `services/tilemap-service/src/engine/modificators/mod.rs` | MOD | +1 | `pub use biome_theme_painter::BiomeThemePainter;` |
| 4 | `services/tilemap-service/src/engine/mod.rs` | MOD | +10 | Import + register at 5 ModificatorRegistry sites (lines 133, 321, 410, 426, 552) AFTER `TerrainPainter`, BEFORE `ConnectionsPlacer` |
| 5 | `services/tilemap-service/tests/biome_theme_painter.rs` | NEW | ~250 | AC-BIOME-2..7 integration tests + chunk-B snapshot pin |

(Plan v1: 4 files. Actual: 5 because tile.rs gets the `from_tag` helper. Reclassified file count.)

## Pipeline ordering

```
TerrainPainter (paints each zone with single TerrainKind)
    ↓
BiomeThemePainter (NEW — overwrites per-tile via Perlin where opt-in)
    ↓
ConnectionsPlacer
    ↓
TreasurePlacer
    ↓
RoadPlacer       (Road tiles win over biome — carved last)
    ↓
ObstacleSourcePlacer
    ↓
RiverPlacer      (Water tiles win over biome via carve)
    ↓
ObstacleFillPlacer
    ↓
DecorationPlacer
```

`dependencies()` declares: `["terrain_painter"]`. Kahn sort places it
before any other modificator that depends on terrain_layer state.

## Invariants

1. **V2 byte-identical** — when `template.background_biome == None` AND
   every `zone.biome_theme == None`, `process()` returns `Ok(())` after
   the early-return check. `terrain_layer` UNCHANGED. Chunk-A blake3
   pin `64d8d1b25edd...` continues to pass.
2. **Determinism** — `(template, seed, registry)` ⇒ byte-identical
   `terrain_layer`. Per-zone Perlin instances seeded via `sub_seed` of
   `zone_id`; background Perlin seeded via a distinct label.
3. **Unknown biome id = silent no-op** — `registry.get_biome(id)`
   returning `None` skips that zone or the background pass, matching
   the LOW-5 contract documented in chunk A.
4. **Per-zone Perlin streams are uncorrelated** — same fixture with
   two zones referencing the SAME `biome_theme` id produces TWO
   independent Perlin patterns (proves sub_seed diversification).

## Test plan (AC-BIOME-2..7 + safety)

| # | Test | File | Verifies |
|---|---|---|---|
| 1 | `v2_path_unchanged_when_both_opt_ins_are_none` | tests/biome_theme_painter.rs | AC-BIOME-1 (re-check): same blake3 hash pin as chunk A |
| 2 | `zone_biome_theme_produces_multiple_terrain_kinds` | tests/biome_theme_painter.rs | AC-BIOME-4: ≥2 distinct kinds across zone tiles when theme has ≥2 mix entries |
| 3 | `zone_biome_theme_distribution_matches_mix_weights` | tests/biome_theme_painter.rs | AC-BIOME-4 quality: 70/20/10 mix produces output within ±15% of weights on a 48×48 zone |
| 4 | `background_biome_paints_all_non_zone_tiles` | tests/biome_theme_painter.rs | AC-BIOME-5: 0 tiles with u8==0 in terrain_layer |
| 5 | `background_biome_does_not_overwrite_zone_tiles` | tests/biome_theme_painter.rs | Zone tiles painted by TerrainPainter (with biome_theme=None) survive the background pass |
| 6 | `placer_is_deterministic_over_100_runs` | tests/biome_theme_painter.rs | AC-BIOME-6: byte-identical terrain_layer across 100 runs |
| 7 | `two_zones_same_theme_have_uncorrelated_perlin_patterns` | tests/biome_theme_painter.rs | AC-BIOME-7: histograms differ across zones with same theme |
| 8 | `unknown_biome_id_is_silent_no_op` | tests/biome_theme_painter.rs | LOW-5 contract: typo'd id template-loads + placer skips zone |
| 9 | `terrain_kind_from_tag_round_trips_all_ten` | tile.rs (unit) | NEW `from_tag` matches every `tag()` value |
| 10 | `terrain_kind_from_tag_returns_none_for_unknown` | tile.rs (unit) | `from_tag("atmosphere")` → None |
| 11 | `cdf_sample_with_u_minus_one_picks_first_entry` | biome_theme_painter.rs (unit) | u = -1.0 → normalized = 0.0 → first non-zero-weight entry |
| 12 | `cdf_sample_with_u_plus_one_picks_last_entry` | biome_theme_painter.rs (unit) | u = +1.0 → normalized = ~1.0 → last entry (or last by defensive fallback) |
| 13 | `cdf_sample_threshold_falls_on_boundary` | biome_theme_painter.rs (unit) | 50/50 mix: u that produces threshold == first weight → second entry |
| 14 | `seed_u32_for_is_deterministic_and_diversified_by_label` | biome_theme_painter.rs (unit) | Same seed + label → same u32; different labels → different u32 (high probability) |
| 15 | `chunk_b_snapshot_pin_for_zone_only_fixture` | tests/biome_theme_painter.rs | Blake3 hash of a Zone-only opt-in fixture's terrain_layer pinned as regression anchor |
| 16 | `chunk_b_snapshot_pin_for_background_only_fixture` | tests/biome_theme_painter.rs | Blake3 hash of a Background-only opt-in fixture's terrain_layer pinned |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Cross-platform Perlin drift | `noise 0.9` pure-Rust pinned exact; if CI Linux ≠ Windows on the snapshot pin, branch the literal by `cfg(target_os)` or fall back to a histogram-shape assertion |
| Patches too small / too large | `BIOME_PERLIN_SCALE` const tunable; chunk-C demo will visually confirm |
| Float roundoff in CDF causes invariant violation | `clamp(0.0, 0.999_999_99)` on normalized + defensive last-entry fallback |
| Background pass writes over RoadPlacer's road tiles (would corrupt) | Background pass runs BEFORE RoadPlacer in pipeline — roads carve last, so order is safe |
| Pre-existing `terrain_layer[i] != 0` check accidentally skips a u8==0 zone tile (shouldn't happen but defensively) | TerrainPainter is guaranteed to paint every assigned tile (asserted in its tests). If a zone tile is u8==0, it's a TerrainPainter bug that the background pass would mask |
| Per-zone iteration cost on a 256² grid with 50 zones | O(grid_area) total work; Perlin sample ~10ns → ~650µs per zone × 50 = 30ms worst case. Acceptable |

## Out of scope (chunk C)

- Frontend MetadataPanel "biomes: N" count row
- minimal.json opt-in demo
- Browser smoke (AC-BIOME-8)
