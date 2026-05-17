//! TMP_006 §2 — `TreasureTierSpec`. A zone's author-declared treasure tiers.
//! Consumed by TreasurePlacer (Phase C); Phase A adds only the type so the
//! `ZoneSpec` schema can carry it (additive, TMP-A8).

use serde::{Deserialize, Serialize};

/// One treasure tier for a zone (TMP_006 §2). `density` is piles per
/// zone-tile-thousand — target pile count = `density * zone_tiles / 1000`.
/// Order across a zone's tiers does not matter; the placer sorts by `max`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreasureTierSpec {
    /// Minimum pile value.
    pub min: u32,
    /// Maximum pile value.
    pub max: u32,
    /// Piles per zone-tile-thousand (a soft target — actual count may be lower
    /// if placement fails).
    pub density: u16,
}
