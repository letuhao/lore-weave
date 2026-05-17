//! `WorldMap` — the generator output value.
//!
//! Phase 1 populates the geometry layer (cells + adjacency + heightmap +
//! sea level). A plain value — no event-sourcing aggregate, no deltas
//! (dropped per GEO_GENERATOR_PLAN §1).

use serde::{Deserialize, Serialize};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::WorldScale;

/// One Voronoi cell — a centre point and an elevation.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Cell {
    /// Normalized centre in `[0,1]²`.
    pub center: (f32, f32),
    /// Elevation `0..=65535`; `< WorldMap.sea_level` ⇒ water.
    pub elevation: u16,
}

/// Settlement role (GEO_001 §4.3).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SettlementRole {
    Hamlet,
    Village,
    Town,
    City,
    Capital,
    Fortress,
}

impl SettlementRole {
    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            SettlementRole::Hamlet => 0,
            SettlementRole::Village => 1,
            SettlementRole::Town => 2,
            SettlementRole::City => 3,
            SettlementRole::Capital => 4,
            SettlementRole::Fortress => 5,
        }
    }
}

/// Route kind (GEO_001 §4.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RouteKind {
    Road,
    Trail,
    RiverNavigation,
    SeaLane,
    MountainPass,
}

impl RouteKind {
    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            RouteKind::Road => 0,
            RouteKind::Trail => 1,
            RouteKind::RiverNavigation => 2,
            RouteKind::SeaLane => 3,
            RouteKind::MountainPass => 4,
        }
    }
}

/// A province — a cell cluster grown from one political seed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Province {
    pub id: u32,
    /// The province's seed/capital cell.
    pub capital_cell: u32,
    /// The state this province belongs to.
    pub state: u32,
}

/// A state — a cluster of provinces.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct State {
    pub id: u32,
    /// The lowest-id province in the state — its capital.
    pub capital_province: u32,
}

/// A settlement.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Settlement {
    /// The cell this settlement occupies (unique per settlement).
    pub cell: u32,
    pub role: SettlementRole,
    /// Abstract population tier 0..=5.
    pub population_tier: u8,
}

/// A route edge between two cells.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Route {
    pub kind: RouteKind,
    pub from_cell: u32,
    pub to_cell: u32,
    /// Path cost (terrain-cost units) or hop count.
    pub distance: u32,
}

/// A culture region — a cell cluster grown from one cultural hearth.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct CultureRegion {
    pub id: u32,
    /// The hearth cell this culture spread from.
    pub hearth_cell: u32,
}

/// A fully generated world map.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WorldMap {
    /// The `u64` generation seed (provenance).
    pub seed: u64,
    /// The world scale this map was generated at.
    pub scale: WorldScale,
    /// Cells; the vector index is the cell id.
    pub cells: Vec<Cell>,
    /// Adjacency; `neighbors[i]` is sorted ascending + deduped, parallel to
    /// `cells`, and symmetric (`j ∈ neighbors[i] ⇔ i ∈ neighbors[j]`).
    pub neighbors: Vec<Vec<u32>>,
    /// Elevation threshold; `cell.elevation < sea_level` ⇒ water cell.
    pub sea_level: u16,
    /// Per-cell climate zone (Phase 2). Parallel to `cells`.
    pub climate: Vec<ClimateZone>,
    /// Per-cell biome (Phase 2). Parallel to `cells`.
    pub biome: Vec<BiomeKind>,
    /// Per-cell accumulated downhill flow (Phase 2). Parallel to `cells`.
    pub river_flux: Vec<f32>,
    /// Per-cell flag: land cell adjacent to an ocean cell. Parallel to `cells`.
    pub is_coast: Vec<bool>,
    /// Per-cell province id (Phase 3); `u32::MAX` for water cells.
    pub province_of: Vec<u32>,
    /// Provinces (Phase 3).
    pub provinces: Vec<Province>,
    /// States (Phase 3).
    pub states: Vec<State>,
    /// Settlements (Phase 3).
    pub settlements: Vec<Settlement>,
    /// Routes (Phase 3).
    pub routes: Vec<Route>,
    /// Per-cell culture id (Phase 3); `u32::MAX` for water cells.
    pub culture_of: Vec<u32>,
    /// Culture regions (Phase 3).
    pub culture_regions: Vec<CultureRegion>,
    /// blake3 hash over the canonical byte view — the determinism check.
    pub content_hash: [u8; 32],
}

impl WorldMap {
    /// Number of cells.
    pub fn cell_count(&self) -> usize {
        self.cells.len()
    }

    /// Whether `cell` is land (elevation at or above sea level).
    pub fn is_land(&self, cell: usize) -> bool {
        self.cells[cell].elevation >= self.sea_level
    }
}
