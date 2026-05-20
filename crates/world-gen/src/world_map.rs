//! `WorldMap` — the generator output value.
//!
//! Phase 1 populates the geometry layer (cells + adjacency + heightmap +
//! sea level). A plain value — no event-sourcing aggregate, no deltas
//! (dropped per GEO_GENERATOR_PLAN §1).
//!
//! The `name` fields on the feature structs are a separate, non-deterministic
//! authoring layer (`crate::naming`) — `generate` leaves them empty and they
//! are excluded from `content_hash`.

use serde::{Deserialize, Serialize};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::WorldScale;

/// One Voronoi cell — a centre, an elevation, and the cell's vertex polygon.
///
/// **Phase 1 world-tier redesign (2026-05-20):** all geometry is **on the
/// unit sphere** — `center` is a 3D unit vector, `vertex_polygon` is a ring
/// of 3D unit vectors. Latitude and longitude are derived (see [`Cell::lat`] /
/// [`Cell::lon`]).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Cell {
    /// Cell centre on the unit sphere — 3D Cartesian unit vector.
    pub center: [f32; 3],
    /// Elevation `0..=65535`; `< WorldMap.sea_level` ⇒ water.
    pub elevation: u16,
    /// The cell's spherical Voronoi polygon — an angle-ordered vertex ring of
    /// 3D unit-sphere points (≥ 3 vertices). Geometry for rendering and
    /// downstream consumers.
    pub vertex_polygon: Vec<[f32; 3]>,
}

impl Cell {
    /// Latitude in radians, `[-π/2, π/2]`. North pole = +π/2.
    pub fn lat(&self) -> f32 {
        self.center[2].clamp(-1.0, 1.0).asin()
    }

    /// Longitude in radians, `(-π, π]`. Equivalent to `atan2(y, x)`.
    pub fn lon(&self) -> f32 {
        self.center[1].atan2(self.center[0])
    }
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
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Province {
    pub id: u32,
    /// The province's seed/capital cell.
    pub capital_cell: u32,
    /// The state this province belongs to.
    pub state: u32,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
}

/// A state — a cluster of provinces.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct State {
    pub id: u32,
    /// The state-seed province (farthest-point sampled within the state's
    /// land component) — its capital.
    pub capital_province: u32,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
}

/// A settlement.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Settlement {
    /// The cell this settlement occupies (unique per settlement).
    pub cell: u32,
    pub role: SettlementRole,
    /// Abstract population tier 0..=5.
    pub population_tier: u8,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
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
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CultureRegion {
    pub id: u32,
    /// The hearth cell this culture spread from.
    pub hearth_cell: u32,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
}

/// A mountain range — a connected cluster of `Mountain`-biome cells
/// (`crate::feature`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MountainRange {
    pub id: u32,
    /// The cells forming this range.
    pub cells: Vec<u32>,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
}

/// A river — a connected system of `River`-biome cells (`crate::feature`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct River {
    pub id: u32,
    /// The cells forming this river system.
    pub cells: Vec<u32>,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
}

/// Whether a `WaterBody` is open sea or an inland lake.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WaterBodyKind {
    Sea,
    Lake,
}

impl WaterBodyKind {
    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            WaterBodyKind::Sea => 0,
            WaterBodyKind::Lake => 1,
        }
    }
}

/// A water body — a connected cluster of `Ocean` cells (a sea) or `Lake`
/// cells (a lake) (`crate::feature`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WaterBody {
    pub id: u32,
    pub kind: WaterBodyKind,
    /// The cells forming this water body.
    pub cells: Vec<u32>,
    /// Authored name; empty until named by `crate::naming`. Not hashed.
    #[serde(default)]
    pub name: String,
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
    /// Mountain ranges — connected `Mountain`-biome clusters (`crate::feature`).
    pub mountain_ranges: Vec<MountainRange>,
    /// Rivers — connected `River`-biome systems (`crate::feature`).
    pub rivers: Vec<River>,
    /// Water bodies — seas and lakes (`crate::feature`).
    pub water_bodies: Vec<WaterBody>,
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
    /// `content_hash` itself and the `name` fields. Names are a separate
    /// non-deterministic LLM authoring layer (`crate::naming`); hashing them
    /// would make a freshly-named map fail `verify_hash`. When `WorldMap`
    /// grows a deterministic field, extend this method.
    ///
    /// NOTE: `verify_hash` proves only that the produce path (`generate`) and
    /// the verify path agree — NOT that this method covers every field. If a
    /// new field is added but `compute_hash` is not extended, `verify_hash`
    /// still passes. Field-list completeness (and the deliberate `name`
    /// carve-out) is pinned by the `compute_hash_covers_every_field` test in
    /// `tests/serde.rs`, which tampers each `WorldMap` field of a generated
    /// map and asserts `verify_hash` then returns `false` — except a `name`,
    /// which must leave it `true`.
    pub fn compute_hash(&self) -> [u8; 32] {
        let mut h = blake3::Hasher::new();
        h.update(&self.seed.to_le_bytes());
        h.update(&[self.scale.tag()]);
        h.update(&self.sea_level.to_le_bytes());
        for c in &self.cells {
            // 3D centre — Phase 1 world-tier redesign 2026-05-20.
            h.update(&c.center[0].to_le_bytes());
            h.update(&c.center[1].to_le_bytes());
            h.update(&c.center[2].to_le_bytes());
            h.update(&c.elevation.to_le_bytes());
            h.update(&(c.vertex_polygon.len() as u32).to_le_bytes());
            for v in &c.vertex_polygon {
                h.update(&v[0].to_le_bytes());
                h.update(&v[1].to_le_bytes());
                h.update(&v[2].to_le_bytes());
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
        // Extracted geographic features — geometry is deterministic; the
        // `name` fields are deliberately not hashed (see MAINTENANCE above).
        for mr in &self.mountain_ranges {
            h.update(&mr.id.to_le_bytes());
            h.update(&(mr.cells.len() as u32).to_le_bytes());
            for &c in &mr.cells {
                h.update(&c.to_le_bytes());
            }
        }
        for rv in &self.rivers {
            h.update(&rv.id.to_le_bytes());
            h.update(&(rv.cells.len() as u32).to_le_bytes());
            for &c in &rv.cells {
                h.update(&c.to_le_bytes());
            }
        }
        for wb in &self.water_bodies {
            h.update(&wb.id.to_le_bytes());
            h.update(&[wb.kind.tag()]);
            h.update(&(wb.cells.len() as u32).to_le_bytes());
            for &c in &wb.cells {
                h.update(&c.to_le_bytes());
            }
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
