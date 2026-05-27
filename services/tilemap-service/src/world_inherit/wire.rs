//! Internal serde structs that mirror the on-disk shape of upstream
//! `world-gen` JSON exports (and our mock fixtures). NOT part of the public
//! tilemap-service API — callers see the projected [`WorldZoneSnapshot`]
//! from [`super::types`] instead.
//!
//! Wire shape reference:
//! `services/tilemap-service/tests/fixtures/world-mock/README.md`.

use serde::Deserialize;

use super::types::{RegionPath, WorldBiome};

#[derive(Debug, Deserialize)]
pub(super) struct WorldFile {
    /// Versioning key the parser checks. Today recognised: prefix
    /// `world-gen.v1`; additive `+climate.v1` / `+polygon.v1` segments.
    /// Reject unknown major versions in the future; for now we only log.
    #[serde(default)]
    #[allow(dead_code)] // surfaced via fn schema_version() if needed
    pub schema_version: String,

    #[serde(default)]
    #[allow(dead_code)]
    pub schema_note: String,

    #[serde(default)]
    #[allow(dead_code)]
    pub generator: String,

    #[allow(dead_code)] // header fields not consumed yet; surfaced when needed
    pub world: WireWorldHeader,
    pub plates: Vec<WirePlate>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub(super) struct WireWorldHeader {
    pub width: u32,
    pub height: u32,
    pub seed: u64,
    pub plate_count: usize,
    pub base_level: f32,
    pub void_level: f32,
    pub collision_gain: f32,
}

#[derive(Debug, Deserialize)]
pub(super) struct WirePlate {
    pub path: Vec<u32>,
    #[allow(dead_code)]
    pub center: [f32; 2],
    #[allow(dead_code)]
    pub velocity: [f32; 2],
    #[allow(dead_code)]
    pub boundary: Vec<[f32; 2]>,
    pub zones: Vec<WireZone>,
}

#[derive(Debug, Deserialize)]
pub(super) struct WireZone {
    pub path: Vec<u32>,
    pub site: [f32; 2],
    pub base_elevation: f32,
    #[serde(default)]
    pub boundary: Vec<[f32; 2]>,
    pub climate: WireClimate,
    /// Forward-compat: v1 `MockFileWorldSource` only services zone-depth
    /// paths, so sub-zones are parsed but not consumed. When tilemap adds
    /// sub-zone-anchored templates (spec §6), this field becomes
    /// load-bearing — keep it deserialized so the wire shape doesn't
    /// silently drift away from upstream `WorldData`.
    #[serde(default)]
    #[allow(dead_code)]
    pub subzones: Vec<WireSubZone>,
}

#[derive(Debug, Deserialize)]
pub(super) struct WireClimate {
    pub temp_mean: f32,
    pub precip_annual: f32,
    pub biome_tag: u8,
    pub biome_name: WorldBiome,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub(super) struct WireSubZone {
    pub path: Vec<u32>,
    pub site: [f32; 2],
}

impl WireZone {
    /// Project this wire zone onto the public typed [`super::types::WorldZoneSnapshot`].
    ///
    /// Validates that `biome_tag` and `biome_name` agree (defends against
    /// fixture corruption — a mismatched tag is the kind of typo that
    /// silently broke the asset spike round-trip checks last quarter).
    pub(super) fn to_snapshot(&self) -> Result<super::types::WorldZoneSnapshot, super::WorldInheritError> {
        if self.climate.biome_name.tag() != self.climate.biome_tag {
            return Err(super::WorldInheritError::BiomeTagMismatch {
                tag: self.climate.biome_tag,
                name: self.climate.biome_name,
            });
        }
        Ok(super::types::WorldZoneSnapshot {
            path: RegionPath(self.path.clone()),
            site: self.site,
            base_elevation: self.base_elevation,
            boundary: self.boundary.clone(),
            climate: super::types::ZoneClimate {
                temp_mean: self.climate.temp_mean,
                precip_annual: self.climate.precip_annual,
                biome_tag: self.climate.biome_tag,
                biome_name: self.climate.biome_name,
            },
        })
    }
}
