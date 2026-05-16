//! TMP_003 §3.1 — the TerrainPainter modificator (Phase-1 cut, spec D7).

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::engine::placement::ZoneTiles;
use crate::seed::{TilemapSeed, sub_seed};
use crate::types::template::TilemapTemplate;
use crate::types::tile::TerrainKind;
use crate::types::zone::ZoneRole;

/// Surface terrains a non-`Sea` zone may be painted with when its `ZoneSpec`
/// declares no `terrain_types` (TMP_003 §3.1 — "all surface terrains").
/// `Water` is `Sea`-only, `Road` is RoadPlacer's output, and `Subterranean` is
/// V3 underground — all three are excluded from the random surface set.
const SURFACE_TERRAINS: [TerrainKind; 7] = [
    TerrainKind::Grass,
    TerrainKind::Forest,
    TerrainKind::Mountain,
    TerrainKind::Sand,
    TerrainKind::Snow,
    TerrainKind::Swamp,
    TerrainKind::Rough,
];

/// TMP_003 §3.1 TerrainPainter — paints every tile of each zone with the zone's
/// primary terrain.
///
/// **Phase-1 cut (spec D7):** `Sea` → `Water`; otherwise the first declared
/// `ZoneSpec.terrain_types`, or a seed-random surface terrain when none is
/// declared. The 15 % decoration variant (cosmetic, no `TileState` impact) and
/// faction-native terrain (`match_terrain_to_town`, needs TownPlacer) are out.
#[derive(Debug)]
pub struct TerrainPainter;

impl Modificator for TerrainPainter {
    fn name(&self) -> &str {
        "terrain_painter"
    }

    fn dependencies(&self) -> Vec<&str> {
        // §3.1 declares DEPENDENCY(TownPlacer) + DEPENDENCY_ALL(WaterAdopter).
        // Neither modificator exists in Phase 1 — the registry treats an
        // unregistered dependency as already satisfied (spec D7), so the
        // single-modificator pipeline still runs.
        vec!["town_placer", "water_adopter"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        let width = ctx.grid.width;
        for (i, zone) in ctx.zones.iter().enumerate() {
            let terrain = pick_terrain(zone, ctx.template, ctx.seed);
            ctx.zone_terrain[i] = Some(terrain);
            let value = terrain as u8;
            for tile in zone.assigned_tiles.iter_set() {
                ctx.terrain_layer[tile.flat_index(width)] = value;
            }
        }
        Ok(())
    }
}

/// Choose a zone's primary terrain — TMP_003 §3.1 step 1, Phase-1 cut.
fn pick_terrain(zone: &ZoneTiles, template: &TilemapTemplate, seed: TilemapSeed) -> TerrainKind {
    if zone.role == ZoneRole::Sea {
        return TerrainKind::Water;
    }
    let declared = template
        .zones
        .iter()
        .find(|z| z.zone_id == zone.id)
        .and_then(|spec| spec.terrain_types.first());
    if let Some(&first) = declared {
        return first;
    }
    // No declared terrain — pick deterministically from the surface set via a
    // per-(zone, modificator) sub-stream (spec D1).
    let label = format!("mod:terrain_painter:{}", zone.id.0);
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(seed, &label));
    SURFACE_TERRAINS[rng.gen_range(0..SURFACE_TERRAINS.len())]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::template::{TilemapTemplateId, ZoneSpec};
    use crate::types::tile::TileCoord;
    use crate::types::tile_mask::TileMask;
    use crate::types::tilemap::GridSize;
    use crate::types::zone::ZoneId;

    fn zone_tiles(id: &str, role: ZoneRole, w: u32, h: u32) -> ZoneTiles {
        let mut assigned = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                assigned.set(TileCoord::new(x, y));
            }
        }
        ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(w / 2, h / 2),
            assigned_tiles: assigned,
            free_paths: TileMask::new(w, h),
        }
    }

    fn template_with(zones: Vec<ZoneSpec>) -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones,
            seed_offset: 0,
        }
    }

    fn spec(id: &str, role: ZoneRole, terrains: Vec<TerrainKind>) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: role,
            size: 100,
            terrain_types: terrains,
            monster_strength: None,
            connections: vec![],
        }
    }

    fn run(zones: &[ZoneTiles], template: &TilemapTemplate, grid: GridSize) -> (Vec<u8>, Vec<Option<TerrainKind>>) {
        let mut terrain_layer = vec![0u8; grid.tile_count()];
        let mut zone_terrain = vec![None; zones.len()];
        let mut ctx = ModificatorContext {
            zones,
            template,
            grid,
            seed: TilemapSeed(1),
            terrain_layer: &mut terrain_layer,
            zone_terrain: &mut zone_terrain,
        };
        TerrainPainter.process(&mut ctx).unwrap();
        (terrain_layer, zone_terrain)
    }

    #[test]
    fn sea_zone_is_painted_water() {
        // AC-6 — Sea zones → Water.
        let grid = GridSize { width: 8, height: 8 };
        let zones = [zone_tiles("sea", ZoneRole::Sea, 8, 8)];
        let template = template_with(vec![spec("sea", ZoneRole::Sea, vec![])]);
        let (layer, zone_terrain) = run(&zones, &template, grid);
        assert_eq!(zone_terrain[0], Some(TerrainKind::Water));
        assert!(layer.iter().all(|&t| t == TerrainKind::Water as u8));
    }

    #[test]
    fn declared_terrain_is_used() {
        let grid = GridSize { width: 8, height: 8 };
        let zones = [zone_tiles("z", ZoneRole::Wilderness, 8, 8)];
        let template = template_with(vec![spec(
            "z",
            ZoneRole::Wilderness,
            vec![TerrainKind::Snow, TerrainKind::Forest],
        )]);
        let (_, zone_terrain) = run(&zones, &template, grid);
        assert_eq!(zone_terrain[0], Some(TerrainKind::Snow), "first declared wins");
    }

    #[test]
    fn undeclared_terrain_falls_back_to_a_surface_terrain() {
        let grid = GridSize { width: 8, height: 8 };
        let zones = [zone_tiles("z", ZoneRole::Wilderness, 8, 8)];
        let template = template_with(vec![spec("z", ZoneRole::Wilderness, vec![])]);
        let (_, zone_terrain) = run(&zones, &template, grid);
        let picked = zone_terrain[0].unwrap();
        assert!(SURFACE_TERRAINS.contains(&picked), "got {picked:?}");
    }

    #[test]
    fn every_assigned_tile_is_painted() {
        // AC-6 — TerrainPainter paints every assigned tile (no 0 left).
        let grid = GridSize { width: 8, height: 8 };
        let zones = [zone_tiles("z", ZoneRole::Wilderness, 8, 8)];
        let template = template_with(vec![spec("z", ZoneRole::Wilderness, vec![TerrainKind::Grass])]);
        let (layer, _) = run(&zones, &template, grid);
        assert!(layer.iter().all(|&t| t != 0), "an assigned tile was left unpainted");
    }
}
