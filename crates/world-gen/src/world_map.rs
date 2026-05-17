//! `WorldMap` — the generator output value.
//!
//! Phase 1 populates the geometry layer (cells + adjacency + heightmap +
//! sea level). A plain value — no event-sourcing aggregate, no deltas
//! (dropped per GEO_GENERATOR_PLAN §1).

use serde::{Deserialize, Serialize};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::WorldScale;

/// One Voronoi cell — a centre, an elevation, and the cell's vertex polygon.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Cell {
    /// Normalized centre in `[0,1]²`.
    pub center: (f32, f32),
    /// Elevation `0..=65535`; `< WorldMap.sea_level` ⇒ water.
    pub elevation: u16,
    /// The cell's Voronoi polygon — an angle-ordered vertex ring in `[0,1]²`
    /// (≥ 3 vertices). Geometry for rendering and downstream consumers.
    pub vertex_polygon: Vec<(f32, f32)>,
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
    /// The state-seed province (farthest-point sampled within the state's
    /// land component) — its capital.
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

/// A route between two cells, including the cell path it traverses.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Route {
    pub kind: RouteKind,
    pub from_cell: u32,
    pub to_cell: u32,
    /// Path cost (terrain-cost units) or hop count.
    pub distance: u32,
    /// The ordered cell path the route traverses, `from_cell … to_cell`
    /// inclusive. Lets a renderer or downstream consumer follow the route
    /// over real terrain instead of drawing a straight endpoint-to-endpoint
    /// line. Always has length ≥ 2 (`from_cell` and `to_cell` differ).
    pub path: Vec<u32>,
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

    /// blake3 over a canonical fixed-order byte view of the map — the
    /// determinism digest. f32 fields are hashed by their IEEE-754 bit
    /// pattern (`to_le_bytes`).
    ///
    /// MAINTENANCE: feed **every** `WorldMap` field here **except**
    /// `content_hash` itself (folding the digest into its own input is
    /// circular and would make `verify_hash` permanently false). When
    /// `WorldMap` grows, extend this method.
    ///
    /// NOTE: `verify_hash` proves only that the produce path (`generate`) and
    /// the verify path agree — NOT that this method covers every field. If a
    /// new field is added but `compute_hash` is not extended, `verify_hash`
    /// still passes. Field-list completeness is pinned by the
    /// `compute_hash_covers_every_field` test in `tests/serde.rs`, which
    /// tampers each `WorldMap` field of a generated map and asserts
    /// `verify_hash` then returns `false`.
    pub fn compute_hash(&self) -> [u8; 32] {
        let mut h = blake3::Hasher::new();
        h.update(&self.seed.to_le_bytes());
        h.update(&[self.scale.tag()]);
        h.update(&self.sea_level.to_le_bytes());
        for c in &self.cells {
            h.update(&c.center.0.to_le_bytes());
            h.update(&c.center.1.to_le_bytes());
            h.update(&c.elevation.to_le_bytes());
            h.update(&(c.vertex_polygon.len() as u32).to_le_bytes());
            for &(vx, vy) in &c.vertex_polygon {
                h.update(&vx.to_le_bytes());
                h.update(&vy.to_le_bytes());
            }
        }
        for list in &self.neighbors {
            h.update(&(list.len() as u32).to_le_bytes());
            for &n in list {
                h.update(&n.to_le_bytes());
            }
        }
        for &z in &self.climate {
            h.update(&[z.tag()]);
        }
        for &b in &self.biome {
            h.update(&[b.tag()]);
        }
        for &f in &self.river_flux {
            h.update(&f.to_le_bytes());
        }
        for &coast in &self.is_coast {
            h.update(&[u8::from(coast)]);
        }
        for &p in &self.province_of {
            h.update(&p.to_le_bytes());
        }
        for p in &self.provinces {
            h.update(&p.id.to_le_bytes());
            h.update(&p.capital_cell.to_le_bytes());
            h.update(&p.state.to_le_bytes());
        }
        for s in &self.states {
            h.update(&s.id.to_le_bytes());
            h.update(&s.capital_province.to_le_bytes());
        }
        for s in &self.settlements {
            h.update(&s.cell.to_le_bytes());
            h.update(&[s.role.tag(), s.population_tier]);
        }
        for r in &self.routes {
            h.update(&[r.kind.tag()]);
            h.update(&r.from_cell.to_le_bytes());
            h.update(&r.to_cell.to_le_bytes());
            h.update(&r.distance.to_le_bytes());
            h.update(&(r.path.len() as u32).to_le_bytes());
            for &c in &r.path {
                h.update(&c.to_le_bytes());
            }
        }
        for &c in &self.culture_of {
            h.update(&c.to_le_bytes());
        }
        for cr in &self.culture_regions {
            h.update(&cr.id.to_le_bytes());
            h.update(&cr.hearth_cell.to_le_bytes());
        }
        *h.finalize().as_bytes()
    }

    /// Whether the stored `content_hash` matches a fresh recompute — detects a
    /// hand-edited or corrupted JSON. (See `compute_hash` on what this does
    /// and does not prove.)
    pub fn verify_hash(&self) -> bool {
        self.compute_hash() == self.content_hash
    }
}
