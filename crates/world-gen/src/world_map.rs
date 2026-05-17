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
