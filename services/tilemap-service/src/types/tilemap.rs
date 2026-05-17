//! `TilemapView` aggregate (T2 / Channel scope) — primary tilemap-service output.
//! Mirrors [TMP_001 §3.1](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).
//!
//! Phase 0a captures the **field surface** but leaves runtime detail (e.g. `assigned_tiles`
//! bitmask shape, `free_paths` post-fractalize core skeleton) as `Vec<TileCoord>` placeholders.
//! Phase 1 will refine these into proper `TileMask` types when the modificator pipeline lands.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::object::TilemapObjectPlacement;
use crate::types::template::TilemapTemplateId;
use crate::types::tile::{TerrainKind, TileCoord};
use crate::types::zone::{ZoneId, ZoneRole};

/// Grid dimensions in tiles. TMP_001 §2 defaults: Continent 256² · Country 192² ·
/// District 128² · Town 64². Author-configurable per template.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct GridSize {
    pub width: u32,
    pub height: u32,
}

impl GridSize {
    pub const CONTINENT_DEFAULT: GridSize = GridSize { width: 256, height: 256 };
    pub const COUNTRY_DEFAULT: GridSize = GridSize { width: 192, height: 192 };
    pub const DISTRICT_DEFAULT: GridSize = GridSize { width: 128, height: 128 };
    pub const TOWN_DEFAULT: GridSize = GridSize { width: 64, height: 64 };

    /// Tile count for this grid.
    pub fn tile_count(self) -> usize {
        (self.width as usize) * (self.height as usize)
    }
}

/// V1+30d engine-only generation vs V2 LLM-augmented. Mirrors CSC_001
/// `Layer3Source` pattern.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum GenerationSource {
    /// V1+30d default per AC-TMP-10 — engine-only, no LLM call.
    EngineGenerated,
    /// V2 — L3 zone classifier + L4 narration augmented.
    LlmAugmented {
        /// Provider-routed model ref (`model_ref` per gateway StreamRequest).
        model: String,
        /// Retry count via TMP_008b §5 per-object retry.
        attempts: u32,
        /// Fiction-time of generation (used for L4 cache invalidation).
        generated_at_fiction_time: String,
    },
}

/// Runtime per-zone state after zone placement + modificator pipeline.
/// Phase 0a is structural placeholder; Phase 1 fills in TileMask + concrete fields.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneRuntime {
    pub zone_id: ZoneId,
    pub zone_role: ZoneRole,
    /// Final centre after force-directed converge.
    pub center_position: TileCoord,
    /// Phase 0a placeholder — Phase 1 swaps to a bitmask type.
    #[serde(default)]
    pub assigned_tiles: Vec<TileCoord>,
    /// Post-TerrainPainter primary terrain.
    pub terrain_type: TerrainKind,
}

/// Primary tilemap-service aggregate per TMP_001 §3.1.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapView {
    pub channel_id: ChannelId,
    /// Denormalized tier — must NOT be `Cell` (TMP-A1).
    pub tier: ChannelTier,
    pub grid_size: GridSize,
    pub template_id: TilemapTemplateId,
    /// Deterministic blake3 seed per TMP-A4. See [`crate::seed`].
    pub seed: u64,
    /// Runtime zone state.
    #[serde(default)]
    pub zones: Vec<ZoneRuntime>,
    /// Flat terrain layer — index = y*width + x; value = `TerrainKind` u8 index.
    /// Length MUST equal `grid_size.tile_count()`. Empty in Phase 0a until
    /// modificator pipeline lands at Phase 1.
    #[serde(default)]
    pub terrain_layer: Vec<u8>,
    /// All placed objects (treasures, towns, landmarks, mines, monoliths, decorations).
    #[serde(default)]
    pub object_placements: Vec<TilemapObjectPlacement>,
    /// Derived from MAP_001 (x, y) per TMP-A6 via DP-Ch24 subscribe — updated on map_layout deltas.
    #[serde(default)]
    pub child_cell_anchors: HashMap<String, TileCoord>,
    /// V1+30d default `EngineGenerated`; V2 lifts to `LlmAugmented` per AC-TMP-10.
    pub generation_source: GenerationSource,
    /// L4 narration cache (V1+30d: None; V2: cached prose).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub regional_narration: Option<String>,
    /// L4 cache invalidator (bumps when the L4 prompt template version changes).
    #[serde(default)]
    pub prompt_template_version: u32,
}

impl TilemapView {
    /// Construct a minimal Phase 0a `TilemapView` for tests + future fixture loading.
    /// Engine-only generation; empty zones/terrain/objects; cell anchors empty.
    pub fn empty(
        channel_id: ChannelId,
        tier: ChannelTier,
        grid_size: GridSize,
        template_id: TilemapTemplateId,
        seed: u64,
    ) -> Self {
        Self {
            channel_id,
            tier,
            grid_size,
            template_id,
            seed,
            zones: Vec::new(),
            terrain_layer: Vec::new(),
            object_placements: Vec::new(),
            child_cell_anchors: HashMap::new(),
            generation_source: GenerationSource::EngineGenerated,
            regional_narration: None,
            prompt_template_version: 0,
        }
    }
}
