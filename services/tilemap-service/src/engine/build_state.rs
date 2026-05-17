//! TMP_003 §2.2 / spec D1-D2 — `TilemapBuildState`, the mutable generation
//! state a modificator pass operates on. It owns the per-tile [`TileState`]
//! grid (the build-time single source of truth), the terrain layer, the placed
//! objects, the nearest-object-distance oracle, and per-zone build records.
//!
//! `TileState` is build-internal — it is reconstructed here from the
//! `place_zones` output and never stored on the `TilemapView` (TMP_001 §5).

use crate::engine::placement::ZoneTiles;
use crate::types::object::TilemapObjectPlacement;
use crate::types::tile::{TerrainKind, TileCoord, TileState};
use crate::types::tile_mask::TileMask;
use crate::types::tilemap::GridSize;
use crate::types::zone::{ZoneId, ZoneRole};

/// Per-zone mutable build record. `assigned_tiles` is fixed once placement
/// finishes; `free_paths` may grow when ConnectionsPlacer (Phase D) attaches a
/// cross-zone walkable path.
#[derive(Debug, Clone)]
pub struct ZoneBuildState {
    pub id: ZoneId,
    pub role: ZoneRole,
    pub center: TileCoord,
    pub assigned_tiles: TileMask,
    pub free_paths: TileMask,
}

/// The mutable state threaded through the modificator pipeline (spec D1).
#[derive(Debug, Clone)]
pub struct TilemapBuildState {
    pub grid: GridSize,
    /// Per-tile state, index `y*width + x`, length `grid.tile_count()` — the
    /// build-time single source of truth (spec D2).
    pub tile_state: Vec<TileState>,
    /// Flat terrain layer, index `y*width + x`, value `TerrainKind as u8`.
    pub terrain_layer: Vec<u8>,
    /// Per-zone primary terrain, index-aligned with `zones`.
    pub zone_terrain: Vec<Option<TerrainKind>>,
    /// Every object the pipeline has placed.
    pub object_placements: Vec<TilemapObjectPlacement>,
    /// Map-wide "distance to nearest placed object" oracle (spec D10), index
    /// `y*width + x`, init `f32::INFINITY`.
    pub nearest_object_distance: Vec<f32>,
    /// Per-zone build records.
    pub zones: Vec<ZoneBuildState>,
}

impl TilemapBuildState {
    /// Build the initial state from the `place_zones` output (spec D2 / §6.4).
    ///
    /// Init rule per assigned tile: `Walkable` if in the zone's `free_paths`,
    /// else `Obstacle` if the zone is `Forbidden` (completely blocked), else
    /// `Open`. `Sea` zones take the general path — non-free `Sea` tiles are
    /// `Open` (not special-cased; Phase B/C place objects in `Sea` zones).
    pub fn from_zones(zones: Vec<ZoneTiles>, grid: GridSize) -> Self {
        let tile_count = grid.tile_count();

        // §6.4 — a non-empty zone set from place_zones is a disjoint full-grid
        // partition; assert total coverage. An empty zone set is the legitimate
        // empty-template case (the whole grid stays the `Obstacle` default).
        debug_assert!(
            zones.is_empty() || {
                let mut covered = TileMask::new(grid.width, grid.height);
                for z in &zones {
                    covered.union_with(&z.assigned_tiles);
                }
                covered.count_ones() == tile_count
            },
            "from_zones: a non-empty zone set must cover the whole grid",
        );

        // Init to `Obstacle` (a safe "blocked" default — a tile somehow left
        // unassigned must not read as walkable); every assigned tile is then
        // overwritten with its real state.
        let mut tile_state = vec![TileState::Obstacle; tile_count];
        for zone in &zones {
            for tile in zone.assigned_tiles.iter_set() {
                let state = if zone.free_paths.get(tile) {
                    TileState::Walkable
                } else if zone.role == ZoneRole::Forbidden {
                    TileState::Obstacle
                } else {
                    TileState::Open
                };
                tile_state[tile.flat_index(grid.width)] = state;
            }
        }

        let zones: Vec<ZoneBuildState> = zones
            .into_iter()
            .map(|z| ZoneBuildState {
                id: z.id,
                role: z.role,
                center: z.center,
                assigned_tiles: z.assigned_tiles,
                free_paths: z.free_paths,
            })
            .collect();

        Self {
            grid,
            tile_state,
            terrain_layer: vec![0u8; tile_count],
            zone_terrain: vec![None; zones.len()],
            object_placements: Vec::new(),
            nearest_object_distance: vec![f32::INFINITY; tile_count],
            zones,
        }
    }

    /// The [`TileState`] of `c`. Out-of-bounds reads `Obstacle` (a coord outside
    /// the grid is not passable).
    pub fn tile_state_at(&self, c: TileCoord) -> TileState {
        if c.x >= self.grid.width || c.y >= self.grid.height {
            return TileState::Obstacle;
        }
        self.tile_state[c.flat_index(self.grid.width)]
    }

    /// Set the [`TileState`] of `c`. Out-of-bounds coords are ignored.
    pub fn set_tile_state(&mut self, c: TileCoord, state: TileState) {
        if c.x < self.grid.width && c.y < self.grid.height {
            let width = self.grid.width;
            self.tile_state[c.flat_index(width)] = state;
        }
    }

    /// A zone's `Open` tiles — the object-placement candidate area (TMP_005
    /// §4.2). Derived from `tile_state`, never stored (spec D2).
    pub fn zone_area_open(&self, zone_idx: usize) -> TileMask {
        self.zone_filtered(zone_idx, |s| s == TileState::Open)
    }

    /// A zone's passable tiles — `Walkable ∪ Open` (spec D5). The connectivity
    /// check and access-path search consume this.
    pub fn zone_passable(&self, zone_idx: usize) -> TileMask {
        self.zone_filtered(zone_idx, TileState::is_passable)
    }

    /// A zone's `Obstacle` tiles — the ObstaclePlacer fill region (TMP_005 §4.4).
    pub fn zone_obstacle(&self, zone_idx: usize) -> TileMask {
        self.zone_filtered(zone_idx, |s| s == TileState::Obstacle)
    }

    /// A zone's `assigned_tiles` filtered to tiles whose state satisfies `pred`.
    fn zone_filtered(&self, zone_idx: usize, pred: impl Fn(TileState) -> bool) -> TileMask {
        let zone = &self.zones[zone_idx];
        let mut mask = TileMask::new(self.grid.width, self.grid.height);
        for tile in zone.assigned_tiles.iter_set() {
            if pred(self.tile_state_at(tile)) {
                mask.set(tile);
            }
        }
        mask
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mask(w: u32, h: u32, tiles: &[(u32, u32)]) -> TileMask {
        let mut m = TileMask::new(w, h);
        for &(x, y) in tiles {
            m.set(TileCoord::new(x, y));
        }
        m
    }

    fn zone_tiles(
        id: &str,
        role: ZoneRole,
        w: u32,
        h: u32,
        assigned: &[(u32, u32)],
        free: &[(u32, u32)],
    ) -> ZoneTiles {
        ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(assigned[0].0, assigned[0].1),
            assigned_tiles: mask(w, h, assigned),
            free_paths: mask(w, h, free),
        }
    }

    /// A 4×2 grid partitioned into a `Wilderness` zone (left half) and a `Sea`
    /// zone (right half), each with one `free_paths` tile.
    fn land_and_sea() -> TilemapBuildState {
        let grid = GridSize { width: 4, height: 2 };
        let land = zone_tiles(
            "land",
            ZoneRole::Wilderness,
            4,
            2,
            &[(0, 0), (1, 0), (0, 1), (1, 1)],
            &[(0, 0)],
        );
        let sea = zone_tiles(
            "sea",
            ZoneRole::Sea,
            4,
            2,
            &[(2, 0), (3, 0), (2, 1), (3, 1)],
            &[(3, 1)],
        );
        TilemapBuildState::from_zones(vec![land, sea], grid)
    }

    #[test]
    fn from_zones_assigns_every_tile_exactly_one_state() {
        // AC-1 — full-grid coverage; free_paths ⟺ Walkable, the rest Open.
        let s = land_and_sea();
        assert_eq!(s.tile_state.len(), 8);
        assert_eq!(s.tile_state_at(TileCoord::new(0, 0)), TileState::Walkable, "land free path");
        assert_eq!(s.tile_state_at(TileCoord::new(1, 0)), TileState::Open, "land non-free");
        assert_eq!(s.tile_state_at(TileCoord::new(0, 1)), TileState::Open);
        assert_eq!(s.tile_state_at(TileCoord::new(1, 1)), TileState::Open);
    }

    #[test]
    fn sea_zone_non_free_tiles_are_open_not_special_cased() {
        // AC-1 — D2: Sea zones are not special-cased.
        let s = land_and_sea();
        assert_eq!(s.tile_state_at(TileCoord::new(3, 1)), TileState::Walkable, "sea free path");
        for &(x, y) in &[(2, 0), (3, 0), (2, 1)] {
            assert_eq!(
                s.tile_state_at(TileCoord::new(x, y)),
                TileState::Open,
                "sea non-free tile ({x},{y}) must be Open",
            );
        }
    }

    #[test]
    fn forbidden_zone_tiles_are_obstacle() {
        // AC-1 — a Forbidden zone is completely blocked (empty free_paths).
        let grid = GridSize { width: 2, height: 2 };
        let forbidden = zone_tiles(
            "vault",
            ZoneRole::Forbidden,
            2,
            2,
            &[(0, 0), (1, 0), (0, 1), (1, 1)],
            &[],
        );
        let s = TilemapBuildState::from_zones(vec![forbidden], grid);
        for &(x, y) in &[(0, 0), (1, 0), (0, 1), (1, 1)] {
            assert_eq!(s.tile_state_at(TileCoord::new(x, y)), TileState::Obstacle);
        }
    }

    #[test]
    fn zone_area_open_and_passable_are_derived_from_tile_state() {
        let s = land_and_sea();
        // land (zone 0): one Walkable + three Open.
        let open = s.zone_area_open(0);
        assert_eq!(open.count_ones(), 3, "land has 3 Open tiles");
        assert!(!open.get(TileCoord::new(0, 0)), "the Walkable tile is not Open");
        let passable = s.zone_passable(0);
        assert_eq!(passable.count_ones(), 4, "all of land is Walkable|Open");
        assert!(passable.get(TileCoord::new(0, 0)));
    }

    #[test]
    fn set_tile_state_round_trips_and_ignores_out_of_bounds() {
        let mut s = land_and_sea();
        s.set_tile_state(TileCoord::new(1, 0), TileState::Occupied);
        assert_eq!(s.tile_state_at(TileCoord::new(1, 0)), TileState::Occupied);
        // out of bounds — ignored on write, reads Obstacle.
        s.set_tile_state(TileCoord::new(99, 0), TileState::Walkable);
        assert_eq!(s.tile_state_at(TileCoord::new(99, 0)), TileState::Obstacle);
    }

    #[test]
    fn fresh_build_state_has_empty_objects_and_infinite_distance() {
        let s = land_and_sea();
        assert!(s.object_placements.is_empty());
        assert_eq!(s.nearest_object_distance.len(), 8);
        assert!(s.nearest_object_distance.iter().all(|d| d.is_infinite()));
        assert_eq!(s.zone_terrain, vec![None, None]);
    }
}
