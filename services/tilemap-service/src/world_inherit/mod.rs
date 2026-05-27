//! World-inheritance module — tilemap-service consumes the upstream
//! `lore-weave-game/world-gen` consumer contract (§11.2 base + §11.5
//! climate/polygon levers) as input constraints on per-zone biome
//! selection.
//!
//! Two-layer architecture (information-only inheritance):
//!
//! - **World map** (upstream, sibling repo): SSOT for plate identity,
//!   climate, biome, elevation, polygon
//! - **Tilemap** (this service, downstream): receives `WorldZoneSnapshot`
//!   as input, applies `BiomeBridge` constraint, generates per-tile content
//!   inside the constraint
//!
//! See spec: docs/specs/2026-05-24-tilemap-world-inheritance-contract.md

pub mod biome_bridge;
pub mod error;
pub mod source;
pub mod types;
mod wire;

pub use biome_bridge::{BiomeBridge, BridgeParseError, BridgeViolation};
pub use error::WorldInheritError;
pub use source::{MockFileWorldSource, WorldSource};
pub use types::{RegionPath, WorldBiome, WorldZoneSnapshot, ZoneClimate};
