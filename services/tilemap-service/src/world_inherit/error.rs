//! Errors produced by the `world_inherit` module.
//!
//! `WorldInheritError` is standalone — when callers need to bubble these to
//! the top-level `crate::Error`, add a `#[from]` variant there. Today only
//! the world_inherit module touches these values, so the standalone shape
//! keeps the surface minimal.

use thiserror::Error;

use super::types::WorldBiome;

#[derive(Debug, Error)]
pub enum WorldInheritError {
    #[error("failed to parse world-gen JSON: {0}")]
    Parse(#[from] serde_json::Error),

    #[error("failed to read world-gen fixture from {path}: {source}")]
    IoLoad {
        path: String,
        #[source]
        source: std::io::Error,
    },

    /// Wire `biome_tag` is outside the canonical 0..=9 range from upstream
    /// `Biome::tag()`. The tag was actually unknown.
    #[error("unknown upstream biome tag {0} (expected 0..=9)")]
    UnknownBiomeTag(u8),

    /// Wire `biome_tag` and `biome_name` disagree. Both fields are in range,
    /// but they would map to different `WorldBiome` variants — a fixture
    /// corruption signal that round-trip tests would miss without this
    /// explicit cross-check.
    #[error("biome_tag {tag} does not match biome_name {name:?} (expected tag {})", name.tag())]
    BiomeTagMismatch { tag: u8, name: WorldBiome },

    #[error("no zone at path {path} in world fixture")]
    MissingZone { path: String },
}
