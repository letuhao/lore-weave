//! `TilemapView` aggregate (T2 / Channel scope) — primary tilemap-service output.
//! Mirrors [TMP_001 §3.1](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).
//!
//! Phase 1 refines the per-zone runtime detail: `assigned_tiles` + `free_paths`
//! are [`TileMask`] bitsets (the zone placer + fractalize fill them).

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::types::channel::{ChannelId, ChannelTier};
use crate::types::object::TilemapObjectPlacement;
use crate::types::registry::RegistryRef;
use crate::types::template::TilemapTemplateId;
use crate::types::tile::{TerrainCell, TerrainKind, TileCoord};
use crate::types::tile_mask::TileMask;
use crate::types::zone::{ZoneId, ZoneRole};

/// Grid dimensions in tiles.
///
/// ⚠ RENAMED 2026-08-22 — `SPG-R13`. These were `CONTINENT_DEFAULT` /
/// `COUNTRY_DEFAULT` / `DISTRICT_DEFAULT` / `TOWN_DEFAULT`, keyed by
/// `ChannelTier`, which `SPG-R1` retired. They are NOT a per-kind map and never
/// were: under `SPG-A3`'s containment matrix **depth is not a kind**, so a
/// `Region` at depth 1 and a `Region` at depth 3 share a kind and want different
/// sizes — a per-kind default cannot reproduce that and should stop pretending
/// to. What they actually are is a **zoom ladder**, and the ladder is what
/// `SPG-A3` removed. So they are named by the size they give.
///
/// The authored `grid_size` on the view stays authoritative; these are presets
/// an author picks, which is what this comment already said before the rename
/// ("author-configurable per template") and what made the rename cheap.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct GridSize {
    pub width: u32,
    pub height: u32,
}

impl GridSize {
    pub const ZOOM_256: GridSize = GridSize { width: 256, height: 256 };
    pub const ZOOM_192: GridSize = GridSize { width: 192, height: 192 };
    pub const ZOOM_128: GridSize = GridSize { width: 128, height: 128 };
    pub const ZOOM_64: GridSize = GridSize { width: 64, height: 64 };

    /// Tile count for this grid.
    pub fn tile_count(self) -> usize {
        (self.width as usize) * (self.height as usize)
    }
}

#[cfg(test)]
mod grid_size_preset_tests {
    use super::GridSize;

    /// WHY THIS EXISTS, and it was found by biting rather than by review.
    ///
    /// `SPG-R13` renamed these presets off the retired `ChannelTier` rungs.
    /// Immediately after the rename, `ZOOM_64` was mutated from 64 to 32 and
    /// **all 521 tilemap-service tests still passed** -- the constants are used
    /// as INPUTS to tests that assert relative properties, and no assertion
    /// anywhere tied a value to `TMP_001` section 2.
    ///
    /// Before the rename the tier NAME carried that tie by implication
    /// (`TOWN_DEFAULT` was obviously the town figure). Renaming to a size role
    /// makes the name self-consistent with any value, so the tie has to become
    /// an assertion or it is gone. This is the rename paying for what it took.
    #[test]
    fn presets_match_tmp_001_section_2_and_descend() {
        assert_eq!((GridSize::ZOOM_256.width, GridSize::ZOOM_256.height), (256, 256));
        assert_eq!((GridSize::ZOOM_192.width, GridSize::ZOOM_192.height), (192, 192));
        assert_eq!((GridSize::ZOOM_128.width, GridSize::ZOOM_128.height), (128, 128));
        assert_eq!((GridSize::ZOOM_64.width, GridSize::ZOOM_64.height), (64, 64));

        // A ZOOM LADDER is the thing they are (`SPG-R13`), so it must descend
        // strictly -- two presets with the same size would not be a ladder, and
        // an ascending one would not be a zoom.
        let ladder = [GridSize::ZOOM_256, GridSize::ZOOM_192, GridSize::ZOOM_128, GridSize::ZOOM_64];
        for w in ladder.windows(2) {
            assert!(
                w[0].tile_count() > w[1].tile_count(),
                "the zoom ladder must descend strictly: {:?} then {:?}",
                w[0],
                w[1]
            );
        }

        // Every preset is square. The name says one number; two would be a lie.
        for g in ladder {
            assert_eq!(g.width, g.height, "preset {g:?} is not square");
        }
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
///
/// TMP-Q3 chunk C — `Eq` dropped because `terrain_vocabulary: Vec<TerrainCell>`
/// now carries optional `f32` blend hints. Same pattern as
/// `TilemapTemplate` (see `types/template.rs` "Note on Eq"). No call
/// site uses `TilemapView` as a HashMap key — only `assert_eq!` for
/// determinism / round-trip tests, which works with `PartialEq` alone.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
    /// Flat terrain layer — index = y*width + x; value = u8 indexing into
    /// `terrain_vocabulary`. Length MUST equal `grid_size.tile_count()`.
    /// Empty in Phase 0a until modificator pipeline lands at Phase 1.
    ///
    /// V1 wire compat: u8 values 1..=10 align with the legacy
    /// `TerrainKind` enum order; `terrain_vocabulary` is keyed by these
    /// values so existing fixtures continue to load.
    #[serde(default)]
    pub terrain_layer: Vec<u8>,
    /// V2 terrain dictionary indexed by `terrain_layer` u8 values.
    /// `terrain_vocabulary[k]` describes what tile-kind k means in
    /// terms of engine primitive + registry tag. Skipped on wire
    /// when empty so pre-V2 fixtures still round-trip.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub terrain_vocabulary: Vec<TerrainCell>,
    /// V2 registry pin — which registry was used to build this view.
    /// Frontend reads this to know which sprite pack / behavior table
    /// applies; mismatched versions warn but don't crash.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub registry_ref: Option<RegistryRef>,
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
            terrain_vocabulary: Vec::new(),
            registry_ref: None,
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
