//! `TilemapTemplate` aggregate — author-declared template document.
//! Mirrors [TMP_001 §2 + §3.2](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md)
//! plus [TMP_004](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_004_template_authoring.md)
//! authoring detail. Phase 0a captures only the shape needed for the
//! `tilemap_view` reference fields; full author-editor schema lands in Phase 4+.

use serde::{Deserialize, Serialize};

use crate::types::tile::TerrainKind;
use crate::types::zone::{PassageKind, ZoneId, ZoneRole};

/// Stable per-reality template identifier (e.g. `"wuxia_southern_song_v1"`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct TilemapTemplateId(pub String);

/// Author-declared zone specification. Phase 0a captures the structural minimum;
/// TMP_004 has the full schema (size, treasure tiers, mines, town hints, etc.).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneSpec {
    pub zone_id: ZoneId,
    pub zone_role: ZoneRole,
    /// Relative size weight (TMP_002 §2.1). The zone placer scales a zone's
    /// force-directed soft-sphere radius by `sqrt(size)`. Author-tunable;
    /// defaults to a neutral mid weight so a template that omits it still
    /// places sanely (all zones equal-size).
    #[serde(default = "default_zone_size")]
    pub size: u32,
    /// Allowed terrain types in this zone (post-TerrainPainter).
    #[serde(default)]
    pub terrain_types: Vec<TerrainKind>,
    /// Author monster-strength tag (V1+30d freeform; closed enum at Phase 4+).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub monster_strength: Option<String>,
    /// Author connections (full graph at template level; runtime placement
    /// converts to `ZoneEdge` records on `tilemap_view`).
    #[serde(default)]
    pub connections: Vec<TemplateConnection>,
}

/// Default `ZoneSpec.size` — a neutral mid weight (all zones equal when the
/// author does not differentiate).
fn default_zone_size() -> u32 {
    100
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TemplateConnection {
    pub to_zone: ZoneId,
    pub kind: PassageKind,
}

/// V2/Reality aggregate. Phase 0a is structural minimum.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TilemapTemplate {
    pub template_id: TilemapTemplateId,
    pub zones: Vec<ZoneSpec>,
    /// Author seed offset — combined with channel_id into the final blake3 seed
    /// (per TMP-A4). Default 0; non-zero forces a different deterministic seed
    /// for the same template applied to the same channel.
    #[serde(default)]
    pub seed_offset: u64,
}
