//! TMP-Q2 chunk B — `BiomeThemePainter` (Perlin sampler + CDF threshold).
//!
//! Runs AFTER [`super::TerrainPainter`], BEFORE
//! [`super::ConnectionsPlacer`]. Two passes:
//!
//! 1. **Zone override** — for every zone declaring `biome_theme = Some(id)`,
//!    OVERWRITES TerrainPainter's single-fill with a per-tile Perlin
//!    sample against the theme's weighted `mix` CDF.
//! 2. **Background fill** — when `template.background_biome = Some(id)`,
//!    paints all tiles where `terrain_layer[i] == 0` (= no zone, void)
//!    with a separate Perlin stream.
//!
//! Both fields default to `None`; the V2 single-fill path is byte-
//! identical when no biome opt-in is present (the placer early-returns
//! before touching any tile).
//!
//! Spec: [`docs/specs/2026-05-29-biome-theme-painter.md`](../../../../../docs/specs/2026-05-29-biome-theme-painter.md)
//! Plan: [`docs/plans/2026-05-29-biome-theme-painter-chunk-B.md`](../../../../../docs/plans/2026-05-29-biome-theme-painter-chunk-B.md)

use noise::{NoiseFn, Perlin};

use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::seed::{sub_seed, TilemapSeed};
use crate::types::biome_theme::BiomeMixEntry;
use crate::types::tile::TerrainKind;

/// Perlin frequency for biome sampling. Coherence length of `noise 0.9`'s
/// `Perlin` is ~1 unit in noise space; sampling at `tile * 0.125` puts
/// 8 tiles per coherent patch — large enough to be visually a "patch",
/// small enough that a 48×48 zone shows 5-7 patches.
///
/// Tunable later via a per-theme override (V3.1 if needed); kept const
/// here so the chunk-B snapshot pin stays well-defined.
const BIOME_PERLIN_SCALE: f64 = 0.125;

/// TMP-Q2 chunk B placer. See module doc.
#[derive(Debug)]
pub struct BiomeThemePainter;

impl Modificator for BiomeThemePainter {
    fn name(&self) -> &str {
        "biome_theme_painter"
    }

    fn dependencies(&self) -> Vec<&str> {
        // Must run AFTER TerrainPainter (we overwrite its output for zones
        // with biome_theme set). No other modificator depends on this
        // explicitly; the Kahn sort places it before any modificator that
        // declares a dependency on the per-tile terrain_layer state.
        vec!["terrain_painter"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        // Early-return: no biome opt-in anywhere ⇒ V2 path unchanged.
        // This is the load-bearing check that keeps the chunk-A blake3
        // hash pin (64d8d1b2...) passing post-chunk-B.
        let has_zone_theme = ctx.template.zones.iter().any(|z| z.biome_theme.is_some());
        let has_background = ctx.template.background_biome.is_some();
        if !has_zone_theme && !has_background {
            return Ok(());
        }

        // Pass 1 — Zone overrides.
        paint_zone_overrides(ctx);
        // Pass 2 — Background fill (non-zone tiles).
        paint_background(ctx);

        Ok(())
    }
}

/// Pass 1 — iterate every RUNTIME zone, look up its template by
/// `zone_id` to find the author's `biome_theme`. Each zone's
/// `(zone_id, "biome_theme:perlin")` sub-seed gives an INDEPENDENT
/// Perlin stream so two zones with the same theme still get distinct
/// patterns (AC-BIOME-7).
///
/// MED-1 fix from chunk-B /review-impl: iterate `state.zones` and look
/// up template by `zone_id` rather than assuming `template.zones[i]`
/// and `state.zones[i]` are parallel-indexed. Matches
/// [`super::TerrainPainter::pick_terrain`] discipline. Without the id
/// lookup, a future `place_zones` change that adds sea zones or
/// reorders runtime zones would silently apply zone A's theme to
/// zone B's tiles.
fn paint_zone_overrides(ctx: &mut ModificatorContext<'_>) {
    let width = ctx.grid.width;
    let seed = ctx.seed;
    for zone_idx in 0..ctx.state.zones.len() {
        let zone_id = ctx.state.zones[zone_idx].id.clone();
        let Some(spec) = ctx
            .template
            .zones
            .iter()
            .find(|z| z.zone_id == zone_id)
        else {
            // Runtime zone has no matching template ZoneSpec (e.g.
            // engine-synthesized sea zone). No biome_theme to apply.
            continue;
        };
        let Some(theme_id) = spec.biome_theme.as_ref() else {
            continue;
        };
        // Silent no-op on unknown id — matches the LOW-5 docstring
        // contract on `ZoneSpec.biome_theme`: an unknown id template-loads
        // cleanly and falls back to TerrainPainter's single-fill.
        let Some(theme) = ctx.registry.get_biome(theme_id) else {
            continue;
        };
        let label = format!("biome_theme:{}:perlin", zone_id.0);
        let perlin = make_perlin(seed, &label);
        // Snapshot the bitset into a Vec<TileCoord> so the iteration
        // doesn't borrow `state` while we mutate `state.terrain_layer`.
        let tiles: Vec<_> = ctx.state.zones[zone_idx]
            .assigned_tiles
            .iter_set()
            .collect();
        for tile in tiles {
            let u = sample_perlin(&perlin, tile.x, tile.y);
            let kind = sample_by_cdf(&theme.mix, u);
            ctx.state.terrain_layer[tile.flat_index(width)] = kind as u8;
        }
    }
}

/// Pass 2 — paint open-space tiles (`terrain_layer[i] == 0`, the
/// TerrainPainter void) using `template.background_biome`'s mix.
/// Uses a separate Perlin stream from the zone passes.
fn paint_background(ctx: &mut ModificatorContext<'_>) {
    let Some(bg_id) = ctx.template.background_biome.as_ref() else {
        return;
    };
    let Some(theme) = ctx.registry.get_biome(bg_id) else {
        return;
    };
    let width = ctx.grid.width;
    let perlin = make_perlin(ctx.seed, "background_biome:perlin");
    for (i, slot) in ctx.state.terrain_layer.iter_mut().enumerate() {
        if *slot != 0 {
            // Already painted by TerrainPainter or zone-override pass.
            continue;
        }
        let x = (i as u32) % width;
        let y = (i as u32) / width;
        let u = sample_perlin(&perlin, x, y);
        let kind = sample_by_cdf(&theme.mix, u);
        *slot = kind as u8;
    }
}

/// `sub_seed(seed, label)` returns `u64`; `Perlin::new` wants `u32`.
/// XOR-fold the high + low halves to keep all 64 bits influencing the
/// resulting seed (truncating would discard half the entropy and risk
/// label-collision-by-fold).
fn seed_u32_for(seed: TilemapSeed, label: &str) -> u32 {
    let s64 = sub_seed(seed, label);
    ((s64 >> 32) as u32) ^ (s64 as u32)
}

/// Build a deterministic Perlin generator for the given seed + label.
fn make_perlin(seed: TilemapSeed, label: &str) -> Perlin {
    Perlin::new(seed_u32_for(seed, label))
}

/// Sample the Perlin field at scaled (x, y). Returns ~[-1, 1].
fn sample_perlin(perlin: &Perlin, x: u32, y: u32) -> f64 {
    perlin.get([x as f64 * BIOME_PERLIN_SCALE, y as f64 * BIOME_PERLIN_SCALE])
}

/// Map a Perlin output `u ∈ ~[-1, 1]` to a `TerrainKind` via the mix's
/// weighted CDF.
///
/// `normalized = clamp((u + 1) / 2, 0, 0.99999999)` keeps the threshold
/// strictly within `[0, total_weight)` so the cumulative-sum loop never
/// runs off the end at u ≈ 1.0; the defensive `last-entry` fallback
/// catches the rare float-roundoff case where it still does.
///
/// Caller responsibility: `mix.len() >= 1` and every `terrain` tag is
/// `is_valid_biome_key`-validated (enforced at registry load by
/// [`BiomeThemeDef::validate`]). This lets the `from_tag().expect`
/// be unreachable in production.
fn sample_by_cdf(mix: &[BiomeMixEntry], u: f64) -> TerrainKind {
    debug_assert!(!mix.is_empty(), "validated at registry load");
    let normalized = ((u + 1.0) * 0.5).clamp(0.0, 0.999_999_99);
    let total: f64 = mix.iter().map(|e| e.weight as f64).sum();
    let threshold = normalized * total;
    let mut cum = 0.0_f64;
    for entry in mix {
        cum += entry.weight as f64;
        if cum > threshold {
            return TerrainKind::from_tag(&entry.terrain)
                .expect("BiomeMixEntry.terrain validated at registry load");
        }
    }
    // Defensive: float roundoff at u ≈ 1.0 might bypass the loop.
    TerrainKind::from_tag(&mix.last().expect("non-empty mix").terrain)
        .expect("BiomeMixEntry.terrain validated at registry load")
}

/// Total weight of the mix — exposed for unit tests; not used by
/// `process()` (which inlines the sum into `sample_by_cdf`).
#[cfg(test)]
fn mix_total_weight(mix: &[BiomeMixEntry]) -> f64 {
    mix.iter().map(|e| e.weight as f64).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(terrain: &str, weight: f32) -> BiomeMixEntry {
        BiomeMixEntry {
            terrain: terrain.to_string(),
            weight,
        }
    }

    #[test]
    fn seed_u32_for_is_deterministic() {
        let s = TilemapSeed(42);
        assert_eq!(seed_u32_for(s, "lw:foo"), seed_u32_for(s, "lw:foo"));
    }

    #[test]
    fn seed_u32_for_is_diversified_by_label() {
        let s = TilemapSeed(42);
        let a = seed_u32_for(s, "biome_theme:capital:perlin");
        let b = seed_u32_for(s, "biome_theme:frontier:perlin");
        let c = seed_u32_for(s, "background_biome:perlin");
        assert_ne!(a, b, "two zones must get different Perlin seeds");
        assert_ne!(a, c, "zone vs background must differ");
        assert_ne!(b, c, "second zone vs background must differ");
    }

    #[test]
    fn cdf_sample_with_u_minus_one_picks_first_entry() {
        // u = -1 → normalized = 0 → threshold = 0 → first non-zero
        // entry wins (cum after first iteration > 0).
        let mix = vec![entry("grass", 50.0), entry("forest", 50.0)];
        assert_eq!(sample_by_cdf(&mix, -1.0), TerrainKind::Grass);
    }

    #[test]
    fn cdf_sample_with_u_plus_one_picks_last_entry() {
        // u = +1 → normalized = clamp to 0.99999999 → threshold ≈ total
        // → cum > threshold only on the last iteration (or fallback).
        let mix = vec![entry("grass", 50.0), entry("forest", 50.0)];
        assert_eq!(sample_by_cdf(&mix, 1.0), TerrainKind::Forest);
    }

    #[test]
    fn cdf_sample_threshold_falls_on_first_weight_boundary() {
        // 50/50 mix, u that produces normalized ≈ 0.501 → threshold
        // slightly above the first entry's weight (50.0). Cumulative
        // sum after first entry = 50.0; threshold = 50.1 → loop
        // continues; cumulative after second = 100.0 > 50.1 → second.
        let mix = vec![entry("grass", 50.0), entry("forest", 50.0)];
        // (0.001 + 1) * 0.5 = 0.5005 → threshold 50.05 → second wins
        // because cum=50 (not > 50.05) on first, cum=100 > 50.05 on second.
        assert_eq!(sample_by_cdf(&mix, 0.001), TerrainKind::Forest);
    }

    #[test]
    fn cdf_sample_handles_single_entry_mix() {
        let mix = vec![entry("snow", 1.0)];
        assert_eq!(sample_by_cdf(&mix, -1.0), TerrainKind::Snow);
        assert_eq!(sample_by_cdf(&mix, 0.0), TerrainKind::Snow);
        assert_eq!(sample_by_cdf(&mix, 1.0), TerrainKind::Snow);
    }

    #[test]
    fn cdf_threshold_spacing_matches_mix_weights_under_uniform_u() {
        // LOW-5 fix from chunk-B /review-impl: renamed to clarify what
        // this test ACTUALLY verifies. A uniform sweep of `u` proves
        // that the CDF threshold spacing matches the mix weights —
        // i.e. 70/20/10 weights yield 70%/20%/10% of u values mapping
        // to each kind. It does NOT measure the actual Perlin
        // distribution; that's covered by the integration test
        // `zone_biome_theme_distribution_roughly_matches_mix_weights`.
        let mix = vec![
            entry("forest", 70.0),
            entry("grass", 20.0),
            entry("rough", 10.0),
        ];
        let mut counts = [0u32; 3];
        let n = 1000;
        for i in 0..n {
            let u = -1.0 + 2.0 * (i as f64) / (n as f64);
            match sample_by_cdf(&mix, u) {
                TerrainKind::Forest => counts[0] += 1,
                TerrainKind::Grass => counts[1] += 1,
                TerrainKind::Rough => counts[2] += 1,
                other => panic!("unexpected {other:?}"),
            }
        }
        assert!(
            (counts[0] as i32 - 700).abs() <= 50,
            "forest count {} not within ±50 of 700", counts[0]
        );
        assert!(
            (counts[1] as i32 - 200).abs() <= 50,
            "grass count {} not within ±50 of 200", counts[1]
        );
        assert!(
            (counts[2] as i32 - 100).abs() <= 50,
            "rough count {} not within ±50 of 100", counts[2]
        );
    }

    #[test]
    fn mix_total_weight_helper_matches_sum() {
        let mix = vec![entry("a", 1.0), entry("b", 2.5), entry("c", 0.5)];
        assert_eq!(mix_total_weight(&mix), 4.0);
    }

    // ─── paint_background direct exercise ─────────────────────────────
    //
    // The integration tests in `tests/biome_theme_painter.rs` go through
    // `place_zones` (Penrose tiling) which assigns EVERY tile of the
    // grid to some zone, so `terrain_layer[i] == 0` is impossible at
    // the time `paint_background` runs in production fixtures. This
    // test directly invokes the painter's helpers against a manually-
    // constructed state with synthetic void tiles, to exercise the
    // CDF-driven write path that the integration tests cannot reach.

    use crate::engine::build_state::TilemapBuildState;
    use crate::engine::pipeline::ModificatorContext;
    use crate::engine::placement::ZoneTiles;
    use crate::registry::Registry;
    use crate::types::template::{TilemapTemplate, TilemapTemplateId};
    use crate::types::tile::TileCoord;
    use crate::types::tile_mask::TileMask;
    use crate::types::tilemap::GridSize;
    use crate::types::zone::{ZoneId, ZoneRole};

    /// Build a TilemapBuildState whose single zone covers the FULL
    /// grid (the from_zones invariant requires full coverage). Tests
    /// then manually zero out terrain_layer cells AFTER from_zones to
    /// simulate the "void tile" state that paint_background processes.
    fn synthetic_full_coverage_state(width: u32, height: u32) -> TilemapBuildState {
        let mut assigned = TileMask::new(width, height);
        for y in 0..height {
            for x in 0..width {
                assigned.set(TileCoord::new(x, y));
            }
        }
        TilemapBuildState::from_zones(
            vec![ZoneTiles {
                id: ZoneId("full".to_string()),
                role: ZoneRole::Wilderness,
                center: TileCoord::new(width / 2, height / 2),
                assigned_tiles: assigned,
                free_paths: TileMask::new(width, height),
            }],
            GridSize { width, height },
        )
    }

    #[test]
    fn paint_background_fills_void_tiles_with_mix_kinds() {
        // Bypass TerrainPainter: build a full-coverage state whose
        // terrain_layer is all u8=0 (the from_zones default). Run
        // paint_background directly — every tile should be filled
        // because all 256 tiles are "void" from its perspective.
        let grid = GridSize { width: 16, height: 16 };
        let mut state = synthetic_full_coverage_state(grid.width, grid.height);
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("synth".to_string()),
            zones: vec![],  // no ZoneSpec — paint_zone_overrides is a no-op
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: Some("lw:biome.grassland_meadow".to_string()),
            decoration_family_density: None,
        };
        let registry = Registry::load_default().expect("registry");
        let mut ctx = ModificatorContext {
            template: &template,
            grid,
            seed: crate::seed::TilemapSeed(7),
            state: &mut state,
            registry: &registry,
        };
        BiomeThemePainter.process(&mut ctx).expect("paint");

        // Every tile in the synthetic grid (256 tiles) should now be
        // != 0 because background painted them all.
        let void_after = state.terrain_layer.iter().filter(|&&v| v == 0).count();
        assert_eq!(
            void_after, 0,
            "paint_background must fill every u8==0 tile when background_biome is set"
        );
        // Every painted kind must be one of the meadow mix entries
        // (grass / forest / rough).
        let allowed = [
            TerrainKind::Grass as u8,
            TerrainKind::Forest as u8,
            TerrainKind::Rough as u8,
        ];
        for (i, &v) in state.terrain_layer.iter().enumerate() {
            assert!(
                allowed.contains(&v),
                "paint_background wrote unexpected kind {v} at tile {i}"
            );
        }
        // At least 2 distinct kinds (Perlin patches should cross at
        // least one CDF threshold on a 16×16 grid).
        let distinct: std::collections::BTreeSet<u8> =
            state.terrain_layer.iter().copied().collect();
        assert!(
            distinct.len() >= 2,
            "background paint should produce ≥2 distinct kinds on a 16×16 grid (got {distinct:?})"
        );
    }

    #[test]
    fn paint_background_skips_already_painted_tiles() {
        // Pre-paint a row with an out-of-range u8 sentinel (200) — NOT
        // any valid TerrainKind. The background pass must NOT overwrite
        // those tiles; only u8==0 tiles get filled. This locks the
        // load-bearing "skip if already painted" guard.
        //
        // COSMETIC-1 fix from chunk-B /review-impl: a previous version
        // used TerrainKind::Water as the sentinel, which would pass
        // even if the skip-if-nonzero guard broke + the background mix
        // happened to (re)paint Water on those tiles. Using u8=200
        // makes the assertion unambiguous — only the skip path can
        // preserve this value.
        let grid = GridSize { width: 8, height: 8 };
        let mut state = synthetic_full_coverage_state(grid.width, grid.height);
        let sentinel: u8 = 200;
        for x in 0..grid.width {
            let idx = TileCoord::new(x, 0).flat_index(grid.width);
            state.terrain_layer[idx] = sentinel;
        }
        let template = TilemapTemplate {
            template_id: TilemapTemplateId("synth".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: Some("lw:biome.grassland_meadow".to_string()),
            decoration_family_density: None,
        };
        let registry = Registry::load_default().expect("registry");
        let mut ctx = ModificatorContext {
            template: &template,
            grid,
            seed: crate::seed::TilemapSeed(7),
            state: &mut state,
            registry: &registry,
        };
        BiomeThemePainter.process(&mut ctx).expect("paint");
        // The sentinel row must be untouched.
        for x in 0..grid.width {
            let idx = TileCoord::new(x, 0).flat_index(grid.width);
            assert_eq!(
                state.terrain_layer[idx], sentinel,
                "tile ({x}, 0) was {sentinel} before, must survive background pass"
            );
        }
        // Other rows (previously u8=0) MUST have been filled by the
        // background pass — count non-zero tiles outside row 0.
        let mut filled_outside_row_0 = 0;
        for y in 1..grid.height {
            for x in 0..grid.width {
                let idx = TileCoord::new(x, y).flat_index(grid.width);
                if state.terrain_layer[idx] != 0 {
                    filled_outside_row_0 += 1;
                }
            }
        }
        assert_eq!(
            filled_outside_row_0,
            ((grid.height - 1) * grid.width) as usize,
            "background pass must fill every u8==0 tile outside the pre-painted row"
        );
    }
}
