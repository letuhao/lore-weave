//! Domain types mirroring [TMP_001 §2](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).
//!
//! Per TMP-A1 cell tier has no `tilemap_view` — these types only apply to
//! non-cell channels (continent / country / district / town).
//!
//! Data types + the [`TileMask`] bitset. Behaviour (the zone placer +
//! modificator pipeline) lives in the `engine` module (added Phase 1).

pub mod channel;
pub mod object;
pub mod object_template;
pub mod template;
pub mod tile;
pub mod tile_mask;
pub mod tilemap;
pub mod treasure;
pub mod zone;

pub use channel::{ChannelId, ChannelTier};
pub use object::{TilemapObjectKind, TilemapObjectPlacement};
pub use object_template::{FootprintCell, TilemapObjectTemplate};
pub use template::{TemplateConnection, TilemapTemplate, TilemapTemplateId, ZoneSpec};
pub use tile::{TerrainKind, TileCoord, TileState};
pub use tile_mask::TileMask;
pub use tilemap::{GenerationSource, GridSize, TilemapView, ZoneRuntime};
pub use treasure::TreasureTierSpec;
pub use zone::{PassageKind, RoadOption, ZoneEdge, ZoneId, ZoneRole};
