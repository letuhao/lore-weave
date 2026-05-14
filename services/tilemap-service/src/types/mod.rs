//! Domain types mirroring [TMP_001 §2](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).
//!
//! Per TMP-A1 cell tier has no `tilemap_view` — these types only apply to
//! non-cell channels (continent / country / district / town).
//!
//! Phase 0a scope: data types only — no behaviour. Inner detail (e.g.,
//! [`ZoneRuntime::assigned_tiles`]) is intentionally opaque; concrete shapes land
//! at Phase 1 when the zone placer + modificator pipeline is built.

pub mod channel;
pub mod object;
pub mod template;
pub mod tile;
pub mod tilemap;
pub mod zone;

pub use channel::{ChannelId, ChannelTier};
pub use object::{TilemapObjectKind, TilemapObjectPlacement};
pub use template::{TilemapTemplate, TilemapTemplateId, ZoneSpec};
pub use tile::{TerrainKind, TileCoord, TileState};
pub use tilemap::{GenerationSource, GridSize, TilemapView, ZoneRuntime};
pub use zone::{PassageKind, ZoneEdge, ZoneId, ZoneRole};
