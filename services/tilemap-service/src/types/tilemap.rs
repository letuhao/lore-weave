//! `TilemapView` aggregate (T2 / Channel scope) — primary tilemap-service output.
//! Mirrors [TMP_001 §3.1](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).
//!
//! Phase 1 refines the per-zone runtime detail: `assigned_tiles` + `free_paths`
//! are [`TileMask`] bitsets (the zone placer + fractalize fill them).

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::object::TilemapObjectPlacement;
use crate::types::template::TilemapTemplateId;
use crate::types::tile::{TerrainKind, TileCoord};
use crate::types::tile_mask::TileMask;
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
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneRuntime {
    pub zone_id: ZoneId,
    pub zone_role: ZoneRole,
    /// Final centre — force-directed converge then Penrose centroid recompute.
    /// Always a tile inside `assigned_tiles`.
    pub center_position: TileCoord,
    /// Tiles owned by this zone. Zones form a disjoint partition of the grid
    /// (every tile belongs to exactly one zone) — TMP_002 §4.
    pub assigned_tiles: TileMask,
    /// Connected free-path skeleton carved within the zone — TMP_002 §5
    /// fractalize. Empty for `Forbidden` zones (all tiles blocked) and `Hub`
    /// zones use a single straight path.
    pub free_paths: TileMask,
    /// Post-TerrainPainter primary terrain.
    pub terrain_type: TerrainKind,
}

/// A road polyline — the realised path of one MST edge (TMP_003 §3.4 / Phase E
/// `RoadPlacer`). `waypoints` runs ordered from the edge's source anchor to its
/// destination anchor; every waypoint tile is painted `TerrainKind::Road` and
/// stays passable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RoadSegment {
    pub waypoints: Vec<TileCoord>,
}

/// How a river tile stays passable where it would otherwise block traversal
/// (TMP_003 §3.5 / Phase E `RiverPlacer`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CrossingKind {
    /// The river runs under an existing road — the road bridges it.
    Bridge,
    /// A shallow point kept passable (a connectivity-required crossing, or the
    /// every-Nth guaranteed crossing on a long river).
    Ford,
}

/// A passable point on a river (TMP_003 §3.5 step 4).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct RiverCrossing {
    pub at: TileCoord,
    pub kind: CrossingKind,
}

/// A river polyline (TMP_003 §3.5 / Phase E `RiverPlacer`). `tiles` runs ordered
/// from the mountain-source edge to the lake/sea sink — every river tile,
/// including its bridge/ford crossings. `crossings` is the passable subset; a
/// `tiles` entry not in `crossings` is a carved (impassable) river tile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RiverSegment {
    pub tiles: Vec<TileCoord>,
    pub crossings: Vec<RiverCrossing>,
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
    /// Road polylines — one per realised MST edge (Phase E `RoadPlacer`).
    /// Additive (TMP-A8).
    #[serde(default)]
    pub road_segments: Vec<RoadSegment>,
    /// River polylines — mountain-source → lake/sea-sink flow paths (Phase E
    /// `RiverPlacer`). Additive (TMP-A8).
    #[serde(default)]
    pub river_segments: Vec<RiverSegment>,
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
            road_segments: Vec::new(),
            river_segments: Vec::new(),
            child_cell_anchors: HashMap::new(),
            generation_source: GenerationSource::EngineGenerated,
            regional_narration: None,
            prompt_template_version: 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::channel::ChannelId;

    #[test]
    fn road_segment_round_trips() {
        // Phase E — a RoadSegment survives a JSON round-trip.
        let s = RoadSegment {
            waypoints: vec![TileCoord::new(1, 2), TileCoord::new(1, 3), TileCoord::new(2, 3)],
        };
        let back: RoadSegment =
            serde_json::from_str(&serde_json::to_string(&s).unwrap()).unwrap();
        assert_eq!(s, back);
    }

    #[test]
    fn river_segment_and_crossing_round_trip() {
        // Phase E — a RiverSegment with both crossing kinds round-trips, and
        // CrossingKind serialises as the snake_case tag.
        let seg = RiverSegment {
            tiles: vec![TileCoord::new(0, 0), TileCoord::new(0, 1), TileCoord::new(0, 2)],
            crossings: vec![
                RiverCrossing { at: TileCoord::new(0, 1), kind: CrossingKind::Bridge },
                RiverCrossing { at: TileCoord::new(0, 2), kind: CrossingKind::Ford },
            ],
        };
        let json = serde_json::to_string(&seg).unwrap();
        assert!(json.contains("\"bridge\""), "Bridge must serialise snake_case: {json}");
        assert!(json.contains("\"ford\""), "Ford must serialise snake_case: {json}");
        let back: RiverSegment = serde_json::from_str(&json).unwrap();
        assert_eq!(seg, back);
    }

    #[test]
    fn pre_phase_e_view_json_deserializes_without_road_or_river_segments() {
        // AC-12 — TMP-A8: a TilemapView JSON predating Phase E (no
        // `road_segments` / `river_segments` keys) still loads; both default to
        // an empty Vec.
        let json = r#"{
            "channel_id": "ch_legacy",
            "tier": "country",
            "grid_size": { "width": 8, "height": 8 },
            "template_id": "legacy_tpl",
            "seed": 42,
            "generation_source": { "kind": "engine_generated" }
        }"#;
        let v: TilemapView = serde_json::from_str(json).unwrap();
        assert!(v.road_segments.is_empty(), "road_segments must default empty");
        assert!(v.river_segments.is_empty(), "river_segments must default empty");
    }

    #[test]
    fn empty_view_has_no_road_or_river_segments() {
        // AC-12 — an engine-empty view carries empty segment lists.
        let v = TilemapView::empty(
            ChannelId("ch".to_string()),
            ChannelTier::Country,
            GridSize { width: 4, height: 4 },
            TilemapTemplateId("t".to_string()),
            1,
        );
        assert!(v.road_segments.is_empty());
        assert!(v.river_segments.is_empty());
    }
}
