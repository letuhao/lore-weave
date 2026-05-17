//! Zone-level types: `ZoneRole` enum, `PassageKind` enum, `ZoneEdge`, `ZoneId`.
//!
//! Mirrors [TMP_001 §2.1 + §2.2](../../../../docs/03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md).

use serde::{Deserialize, Serialize};

/// Stable per-template zone identifier (e.g. `"jianghu_capital"`, `"sea_north"`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ZoneId(pub String);

/// V1+30d 4-variant `ZoneRole` enum per TMP_001 §2.1.
/// V2+ multiplayer (TMP-D12) reserves `AllyHome` / `RivalHome`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ZoneRole {
    /// Exploration zone; treasure + monster guards; no main town.
    Wilderness,
    /// Crossroads zone; not fractalized; single straight path through.
    Hub,
    /// Completely blocked; only enterable via `PassageKind::Portal`.
    Forbidden,
    /// Water zone — one per tilemap maximum (singleton invariant).
    Sea,
}

/// V1+30d 5-variant `PassageKind` enum per TMP_001 §2.2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PassageKind {
    /// Default — monster-guarded passage with a road.
    Threshold,
    /// Free passage; zones share a wide border; no guard, no road.
    Open,
    /// Narrative-only edge; no physical passage; influences placement.
    Hint,
    /// Pushes zones apart (negative attraction) for rival-faction zones.
    Adversarial,
    /// Teleport pair materialized as a monolith pair regardless of border.
    Portal,
}

/// Author-declared connection between two zones in a `TilemapTemplate`.
/// Runtime shape lands at Phase 1 when modificators populate guard positions
/// + road polylines into [`crate::types::ZoneRuntime`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZoneEdge {
    pub zone_a: ZoneId,
    pub zone_b: ZoneId,
    pub kind: PassageKind,
    /// Default 0 — author override per-edge.
    #[serde(default)]
    pub guard_strength: u32,
}
