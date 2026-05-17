//! The tilemap generation engine — zone placement (TMP_002) + the modificator
//! pipeline (TMP_003).
//!
//! [`place_tilemap`] is the top-level entry: a `TilemapTemplate` + seed in, a
//! fully-placed [`TilemapView`] out — deterministic per the TMP-A4 axiom.

use std::collections::HashMap;

use crate::engine::build_state::TilemapBuildState;
use crate::engine::modificators::{ObstaclePlacer, TerrainPainter};
use crate::engine::pipeline::{ModificatorContext, ModificatorRegistry};
use crate::engine::placement::place_zones;
use crate::seed::TilemapSeed;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::template::TilemapTemplate;
use crate::types::tile::TerrainKind;
use crate::types::tilemap::{GenerationSource, GridSize, TilemapView, ZoneRuntime};

pub mod biome_library;
pub mod biome_select;
pub mod build_state;
pub mod geometry;
pub mod modificators;
pub mod object_manager;
pub mod pipeline;
pub mod placement;

/// Generate a complete [`TilemapView`] from a template + seed.
///
/// Runs the full engine: TMP_002 [`place_zones`] (grid seed → Fruchterman-
/// Reingold → Penrose → fractalize) then the TMP_003 modificator pipeline
/// (Phase 1: TerrainPainter only). Single-threaded — the determinism axiom
/// (TMP-A4) holds: same `(template, channel_id, tier, grid, seed)` ⇒
/// byte-identical output.
///
/// `channel_id` + `tier` scope the resulting view (they are channel metadata
/// the placement algorithm does not synthesize — spec AC-1's `(template, seed,
/// grid_size)` sketch is widened here to carry them).
///
/// Errors propagate from §4 Penrose assignment — an empty zone or a degenerate
/// tiling (both template misconfigurations).
pub fn place_tilemap(
    template: &TilemapTemplate,
    channel_id: ChannelId,
    tier: ChannelTier,
    grid: GridSize,
    seed: TilemapSeed,
) -> crate::Result<TilemapView> {
    // TMP_002 §3-§5 — placed zones with assigned_tiles + free_paths.
    let tiled = place_zones(template, grid, seed)?;

    // TMP_003 — build the mutable generation state and run the modificator
    // pipeline (Phase 1: TerrainPainter only).
    let mut state = TilemapBuildState::from_zones(tiled, grid);
    let mut registry = ModificatorRegistry::new();
    registry.add(Box::new(TerrainPainter));
    registry.add(Box::new(ObstaclePlacer));
    {
        let mut ctx = ModificatorContext {
            template,
            grid,
            seed,
            state: &mut state,
        };
        registry.execute(&mut ctx)?;
    }

    // Assemble the per-zone runtime records from the build state.
    let zones: Vec<ZoneRuntime> = state
        .zones
        .into_iter()
        .zip(state.zone_terrain)
        .map(|(zone, terrain)| ZoneRuntime {
            zone_id: zone.id,
            zone_role: zone.role,
            center_position: zone.center,
            assigned_tiles: zone.assigned_tiles,
            free_paths: zone.free_paths,
            // TerrainPainter paints every zone; the fallback is defensive only.
            terrain_type: terrain.unwrap_or(TerrainKind::Grass),
        })
        .collect();

    Ok(TilemapView {
        channel_id,
        tier,
        grid_size: grid,
        template_id: template.template_id.clone(),
        seed: seed.raw(),
        zones,
        terrain_layer: state.terrain_layer,
        object_placements: state.object_placements,
        child_cell_anchors: HashMap::new(),
        generation_source: GenerationSource::EngineGenerated,
        regional_narration: None,
        prompt_template_version: 0,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::geometry::neighbors4;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::tile::TileCoord;
    use crate::types::tile_mask::TileMask;
    use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

    /// A `ZoneSpec` with the given role + connections (mirrors the proven
    /// `tests/determinism.rs` fixture, so `place_zones` runs on a known-good
    /// multi-zone template).
    fn zone(id: &str, role: ZoneRole, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: role,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
        }
    }

    /// A 5-zone fixture covering every `ZoneRole`.
    fn fixture() -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("ac10_connectivity".to_string()),
            zones: vec![
                zone("capital", ZoneRole::Wilderness, &[("crossroad", PassageKind::Threshold)]),
                zone("crossroad", ZoneRole::Hub, &[("frontier", PassageKind::Open)]),
                zone("frontier", ZoneRole::Wilderness, &[("rival", PassageKind::Adversarial)]),
                zone("inland_sea", ZoneRole::Sea, &[]),
                zone("rival", ZoneRole::Forbidden, &[]),
            ],
            seed_offset: 0,
        }
    }

    /// Independent 4-connected flood-fill from `start` over `region` — the
    /// AC-10 reachability oracle, sharing no implementation with
    /// `would_seal_a_gap` or `connected_components`.
    fn flood(start: TileCoord, region: &TileMask, grid: GridSize) -> TileMask {
        let mut seen = TileMask::new(grid.width, grid.height);
        if !region.get(start) {
            return seen;
        }
        let mut stack = vec![start];
        seen.set(start);
        while let Some(t) = stack.pop() {
            for n in neighbors4(t, grid.width, grid.height) {
                if region.get(n) && !seen.get(n) {
                    seen.set(n);
                    stack.push(n);
                }
            }
        }
        seen
    }

    /// Every 4-connected component of `region`, each as its own mask.
    fn components(region: &TileMask, grid: GridSize) -> Vec<TileMask> {
        let mut remaining = region.clone();
        let mut out = Vec::new();
        while !remaining.is_empty() {
            let start = remaining.iter_set().next().expect("non-empty mask has a set tile");
            let comp = flood(start, &remaining, grid);
            remaining.subtract(&comp);
            out.push(comp);
        }
        out
    }

    #[test]
    fn ac10_place_tilemap_pipeline_never_splits_a_zone_passable_region() {
        // AC-10 — end-to-end: after the `place_tilemap` modificator pipeline no
        // non-Forbidden zone's passable region (`Walkable ∪ Open`) has been
        // split. `place_tilemap` returns a `TilemapView` that drops the
        // build-internal `TileState`, so the test drives the *same* pipeline at
        // the `TilemapBuildState` level — where `zone_passable` is observable —
        // and verifies with an INDEPENDENT 4-connected flood-fill (not
        // `connected_components`, not `would_seal_a_gap`): every pre-pipeline
        // passable component that keeps a survivor keeps all its survivors
        // mutually reachable. Eroding an already-isolated `Open` pocket away
        // entirely is permitted — it strands nothing. AC-10 is a *universal*
        // property, so the check runs over several seeds — each a different
        // `place_zones` geometry — not one (a single-seed test for a universal
        // property is falsely green).
        let template = fixture();
        let grid = GridSize { width: 64, height: 64 };
        for raw_seed in [0xA11CE_u64, 1, 2, 0xB0B, 0xC0FFEE] {
            let seed = TilemapSeed(raw_seed);
            let tiled = place_zones(&template, grid, seed).expect("place_zones on the fixture");
            let mut state = TilemapBuildState::from_zones(tiled, grid);
            let pre: Vec<TileMask> =
                (0..state.zones.len()).map(|i| state.zone_passable(i)).collect();

            // The exact modificator set `place_tilemap` registers, run the same way.
            let mut registry = ModificatorRegistry::new();
            registry.add(Box::new(TerrainPainter));
            registry.add(Box::new(ObstaclePlacer));
            {
                let mut ctx = ModificatorContext {
                    template: &template,
                    grid,
                    seed,
                    state: &mut state,
                };
                registry.execute(&mut ctx).expect("modificator pipeline");
            }

            for (i, pre_passable) in pre.iter().enumerate() {
                if state.zones[i].role == ZoneRole::Forbidden {
                    continue; // a Forbidden zone is all-Obstacle — no passable region
                }
                let zone_id = &state.zones[i].id.0;
                let post = state.zone_passable(i);
                assert!(
                    !post.is_empty(),
                    "seed {raw_seed:#x} zone {zone_id}: the pipeline sealed the entire zone",
                );
                for comp in components(pre_passable, grid) {
                    let survivors: Vec<TileCoord> =
                        comp.iter_set().filter(|&t| post.get(t)).collect();
                    if survivors.is_empty() {
                        continue; // an isolated pocket eroded away — not a split
                    }
                    let reached = flood(survivors[0], &post, grid);
                    for &s in &survivors {
                        assert!(
                            reached.get(s),
                            "seed {raw_seed:#x} zone {zone_id}: \
                             the pipeline split the zone's passable region",
                        );
                    }
                }
            }
        }
    }
}
