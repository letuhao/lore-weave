//! Channel identity + tier — mirrors MAP_001 `ChannelTier` (5 V1 closed enum)
//! and DP-K1 `ChannelId`.
//!
//! Per TMP-A1, **Cell tier is excluded** from any `tilemap_view` — CSC_001
//! is authoritative for the in-scene 16×16 interior. tilemap-service only
//! generates tile data for the four non-cell tiers.

use serde::{Deserialize, Serialize};

/// Stable channel identity. Phase 0a is a string newtype — Phase 2 will swap
/// in the real DP-K1 `ChannelId` once the Rust DP SDK exists.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ChannelId(pub String);

impl std::fmt::Display for ChannelId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// MAP_001 5-tier closed enum. tilemap-service consumes the four non-cell tiers;
/// `Cell` is included for completeness when interacting with shared MAP types but
/// generates no `tilemap_view` (TMP-A1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChannelTier {
    Continent,
    Country,
    District,
    Town,
    /// Excluded from tilemap generation per TMP-A1.
    Cell,
}

impl ChannelTier {
    /// `true` for tiers that generate a `tilemap_view`.
    pub fn generates_tilemap(self) -> bool {
        !matches!(self, ChannelTier::Cell)
    }
}
