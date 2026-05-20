//! Zone placement — TMP_002. The geometric pipeline that turns a zone-graph
//! template into placed zones: §3 force-directed → §4 Penrose tiling → §5
//! fractalize.
//!
//! Chunks 1–4 land §3.1 — the deterministic initial grid seed — §3.2–§3.3 —
//! Fruchterman-Reingold force-directed convergence — §4 — Penrose tiling + tile
//! assignment — §5 — fractalize — plus [`place_zones`], the §6 orchestrator
//! that wires the three stages into one deterministic placement pass.

pub mod force_directed;
pub mod fractalize;
pub mod grid_seed;
pub mod penrose;
pub(crate) mod spatial;

pub use force_directed::{ConvergenceCaps, ConvergenceResult, force_directed_converge};
pub use fractalize::fractalize_zone;
pub use grid_seed::initial_grid_layout;
pub use penrose::assign_zone_tiles;

use crate::seed::TilemapSeed;
use crate::types::template::TilemapTemplate;
use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;
use crate::types::zone::{ZoneId, ZoneRole};

/// A 2-D point in the engine's normalized `[0.0, 1.0] × [0.0, 1.0]` placement
/// space. Force-directed convergence + Penrose run here in `f64`; the final
/// quantization to `u32` grid coordinates happens at tile assignment (§4).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Vec2 {
    pub x: f64,
    pub y: f64,
}

impl Vec2 {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    /// Squared Euclidean distance — cheaper than [`Vec2::distance`] when only
    /// comparing magnitudes.
    pub fn distance_sq(self, other: Vec2) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        dx * dx + dy * dy
    }

    /// Euclidean distance.
    pub fn distance(self, other: Vec2) -> f64 {
        self.distance_sq(other).sqrt()
    }

    /// Uniform scale.
    pub fn scale(self, factor: f64) -> Vec2 {
        Vec2::new(self.x * factor, self.y * factor)
    }

    /// Vector length (distance from the origin).
    pub fn magnitude(self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}

impl std::ops::Add for Vec2 {
    type Output = Vec2;
    /// Component-wise sum.
    fn add(self, other: Vec2) -> Vec2 {
        Vec2::new(self.x + other.x, self.y + other.y)
    }
}

impl std::ops::Sub for Vec2 {
    type Output = Vec2;
    /// Component-wise difference.
    fn sub(self, other: Vec2) -> Vec2 {
        Vec2::new(self.x - other.x, self.y - other.y)
    }
}

/// A zone as the placement engine works with it — its identity + the runtime
/// position being solved for. `pos` is in normalized `[0,1]` space (see
/// [`Vec2`]); §4 Penrose assigns the concrete `assigned_tiles` afterward.
#[derive(Debug, Clone)]
pub struct PlacedZone {
    pub id: ZoneId,
    pub role: ZoneRole,
    /// Relative size weight (`ZoneSpec.size`) — §3.2 scales the soft-sphere
    /// radius by `sqrt(size)`.
    pub size: u32,
    /// Current normalized position. Set by §3.1, refined by §3.2.
    pub pos: Vec2,
}

/// A zone after §4 Penrose tile assignment: its identity plus the concrete grid
/// tiles it owns. `free_paths` is filled by §5 fractalize (empty until then);
/// §6 maps this to a [`crate::types::ZoneRuntime`] once terrain is painted.
#[derive(Debug, Clone)]
pub struct ZoneTiles {
    pub id: ZoneId,
    pub role: ZoneRole,
    /// Centroid of `assigned_tiles`, guaranteed to be a member of the mask
    /// (TMP_002 §4.4 — recomputed from the assigned tiles, snapped inward if
    /// the raw centroid falls in a concavity).
    pub center: TileCoord,
    /// Tiles owned by this zone — a disjoint partition slice of the grid.
    pub assigned_tiles: TileMask,
    /// Connected free-path skeleton (§5 fractalize). Empty until chunk 4.
    pub free_paths: TileMask,
}

/// TMP_002 §6 — the zone-placement orchestrator. Wires the three deterministic
/// stages: §3.1 grid seed → §3.2-§3.3 Fruchterman-Reingold convergence → §4
/// Penrose tile assignment → §5 per-zone fractalize.
///
/// Returns one [`ZoneTiles`] per template zone, fully placed: `assigned_tiles`,
/// `center`, and `free_paths` all filled. Errors propagate from §4 (an empty
/// zone or a degenerate tiling). Single-threaded — determinism before the
/// parallelism optimisation (spec D6).
pub fn place_zones(
    template: &TilemapTemplate,
    grid: GridSize,
    seed: TilemapSeed,
) -> crate::Result<Vec<ZoneTiles>> {
    let seed_layout = initial_grid_layout(template);
    let converged =
        force_directed_converge(seed_layout, template, seed, ConvergenceCaps::default());
    let mut tiled = assign_zone_tiles(&converged.zones, grid, seed)?;
    for zone in &mut tiled {
        fractalize_zone(zone, seed);
    }
    Ok(tiled)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::zone::PassageKind;

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
            inherit_treasure_from: None,
        }
    }

    fn template(zones: Vec<ZoneSpec>) -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones,
            seed_offset: 0,
        }
    }

    fn fixture() -> TilemapTemplate {
        template(vec![
            zone("a", ZoneRole::Wilderness, &[("b", PassageKind::Threshold)]),
            zone("b", ZoneRole::Hub, &[("c", PassageKind::Open)]),
            zone("c", ZoneRole::Sea, &[]),
            zone("d", ZoneRole::Forbidden, &[]),
        ])
    }

    #[test]
    fn place_zones_empty_template_yields_no_zones() {
        let out = place_zones(&template(vec![]), GridSize::TOWN_DEFAULT, TilemapSeed(1)).unwrap();
        assert!(out.is_empty());
    }

    #[test]
    fn place_zones_fills_every_zone() {
        let grid = GridSize { width: 48, height: 48 };
        let out = place_zones(&fixture(), grid, TilemapSeed(0x101)).unwrap();
        assert_eq!(out.len(), 4);
        for z in &out {
            // AC-1 — every zone owns tiles and its centre is inside the mask.
            assert!(!z.assigned_tiles.is_empty(), "zone {} has no tiles", z.id.0);
            assert!(z.assigned_tiles.get(z.center), "centre outside mask");
            // AC-1 — free_paths is empty only for Forbidden zones.
            if z.role == ZoneRole::Forbidden {
                assert!(z.free_paths.is_empty(), "Forbidden zone has free paths");
            } else {
                assert!(!z.free_paths.is_empty(), "zone {} has no free path", z.id.0);
            }
        }
    }

    #[test]
    fn place_zones_partitions_the_grid() {
        // AC-2 — assigned_tiles form a disjoint partition of the whole grid.
        let grid = GridSize { width: 48, height: 48 };
        let out = place_zones(&fixture(), grid, TilemapSeed(0x202)).unwrap();
        let mut union = TileMask::new(grid.width, grid.height);
        for z in &out {
            union.union_with(&z.assigned_tiles);
        }
        assert_eq!(union.count_ones(), grid.tile_count());
        for i in 0..out.len() {
            for j in (i + 1)..out.len() {
                assert!(!out[i].assigned_tiles.intersects(&out[j].assigned_tiles));
            }
        }
    }

    #[test]
    fn place_zones_is_deterministic() {
        let grid = GridSize { width: 40, height: 40 };
        let r1 = place_zones(&fixture(), grid, TilemapSeed(0xABBA)).unwrap();
        let r2 = place_zones(&fixture(), grid, TilemapSeed(0xABBA)).unwrap();
        assert_eq!(r1.len(), r2.len());
        for (a, b) in r1.iter().zip(&r2) {
            assert_eq!(a.id, b.id);
            assert_eq!(a.center, b.center);
            assert_eq!(a.assigned_tiles, b.assigned_tiles);
            assert_eq!(a.free_paths, b.free_paths);
        }
    }
}
