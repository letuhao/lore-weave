//! The tilemap generation engine — zone placement (TMP_002) + the modificator
//! pipeline (TMP_003).
//!
//! [`place_tilemap`] is the top-level entry: a `TilemapTemplate` + seed in, a
//! fully-placed [`TilemapView`] out — deterministic per the TMP-A4 axiom.

use std::collections::HashMap;

use crate::engine::build_state::TilemapBuildState;
use crate::engine::modificators::TerrainPainter;
use crate::engine::pipeline::{ModificatorContext, ModificatorRegistry};
use crate::engine::placement::place_zones;
use crate::seed::TilemapSeed;
use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::template::TilemapTemplate;
use crate::types::tile::TerrainKind;
use crate::types::tilemap::{GenerationSource, GridSize, TilemapView, ZoneRuntime};

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
