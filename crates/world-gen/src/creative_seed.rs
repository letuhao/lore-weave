//! `CreativeSeed` — the creative-direction input to the generator.
//!
//! Phase 1 carries only the geometry-relevant fields (scale, archetype,
//! coastline). Later phases extend this with climate / political / culture
//! direction. `CreativeSeed` is *not* the RNG seed — `generate(seed, &cs)`
//! takes the `u64` seed separately.

use serde::{Deserialize, Serialize};

use crate::climate::ClimateZone;

/// Creative direction for a generated world.
// `Eq` dropped in Phase 2 — `continental_fraction: f32` is not `Eq`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CreativeSeed {
    pub world_scale: WorldScale,
    /// World genre. **Currently inert** — see [`WorldArchetype`].
    pub world_archetype: WorldArchetype,
    pub coastline_profile: CoastlineProfile,
    /// Which way the continent faces the poles — drives latitude → climate.
    pub hemisphere_orientation: HemisphereOrientation,
    /// Direction the prevailing wind blows *from* — drives the orographic rain
    /// shadow. `#[serde(default)]` (`West`) so a pre-wind config JSON loads.
    #[serde(default)]
    pub prevailing_wind: PrevailingWind,
    /// How hard hydraulic erosion carves the heightmap (valleys, drainage
    /// networks, sediment fans). `#[serde(default)]` (`Moderate`) so a
    /// pre-erosion config JSON loads.
    #[serde(default)]
    pub erosion: ErosionStrength,
    /// Optional nudge toward a climate zone (`None` = unbiased).
    pub climate_bias: Option<ClimateZone>,
    /// How densely settlements are placed (Phase 3).
    pub settlement_density: SettlementDensity,
    /// Number of culture regions (Phase 3); clamped to `1..=16` at use.
    pub culture_count: u8,
    /// How the macro landform is generated (Phase 2). `#[serde(default)]`
    /// (`Tectonic`) so a pre-Phase-2 config JSON loads — and gets the new
    /// world-tier default (a multi-continent planet) rather than the legacy
    /// single-continent profile.
    #[serde(default)]
    pub terrain_mode: TerrainMode,
    /// Number of tectonic plates (`Tectonic` mode). `#[serde(default)]` = 8;
    /// clamped to `3..=24` at use.
    #[serde(default = "default_plate_count")]
    pub plate_count: u8,
    /// Fraction of plates carrying continental crust (`Tectonic` mode).
    /// `#[serde(default)]` = 0.4; clamped to `0.1..=0.9` at use.
    #[serde(default = "default_continental_fraction")]
    pub continental_fraction: f32,
    /// Target number of geographic **regions** (L2) per subcontinent in the
    /// geometric hierarchy (C3 arc). `#[serde(default)]` = 4; clamped to
    /// `1..=12` at use. A subcontinent with fewer cells than this gets one
    /// region per cell.
    #[serde(default = "default_region_subdivision")]
    pub region_subdivision: u8,
}

fn default_plate_count() -> u8 {
    8
}

fn default_continental_fraction() -> f32 {
    0.4
}

fn default_region_subdivision() -> u8 {
    4
}

impl Default for CreativeSeed {
    fn default() -> Self {
        CreativeSeed {
            world_scale: WorldScale::Continent,
            world_archetype: WorldArchetype::HighFantasy,
            coastline_profile: CoastlineProfile::Coastal,
            hemisphere_orientation: HemisphereOrientation::Northern,
            prevailing_wind: PrevailingWind::West,
            erosion: ErosionStrength::Moderate,
            climate_bias: None,
            settlement_density: SettlementDensity::Medium,
            culture_count: 5,
            terrain_mode: TerrainMode::Tectonic,
            plate_count: default_plate_count(),
            continental_fraction: default_continental_fraction(),
            region_subdivision: default_region_subdivision(),
        }
    }
}

/// How the macro landform is generated (Phase 2 world-tier redesign).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum TerrainMode {
    /// Plate-tectonic multi-continent — the default. The number, placement and
    /// ocean basins of continents come from [`crate::plates`]; the
    /// `coastline_profile` field is ignored.
    #[default]
    Tectonic,
    /// Legacy single-continent radial-mask profile (Phase 1). Uses
    /// `coastline_profile` + `enforce_coherence`.
    Profile,
}

/// Settlement placement density (Phase 3).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SettlementDensity {
    Sparse,
    Medium,
    Dense,
}

impl SettlementDensity {
    /// Land cells per settlement (target-count divisor).
    pub fn cells_per_settlement(self) -> usize {
        match self {
            SettlementDensity::Sparse => 800,
            SettlementDensity::Medium => 400,
            SettlementDensity::Dense => 200,
        }
    }

    /// Poisson-disk minimum separation (normalized distance).
    pub fn min_separation(self) -> f32 {
        match self {
            SettlementDensity::Sparse => 0.08,
            SettlementDensity::Medium => 0.05,
            SettlementDensity::Dense => 0.03,
        }
    }
}

/// Continent orientation relative to the poles (latitude convention).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HemisphereOrientation {
    /// Map top (`y → 1`) is the pole.
    Northern,
    /// Map bottom (`y → 0`) is the pole.
    Southern,
    /// Equator across the middle (`y = 0.5`); both edges are polar.
    Equatorial,
}

/// Direction the prevailing wind blows *from* (meteorological convention — a
/// "westerly" is a wind *from* the west). Drives the orographic moisture march
/// in [`crate::climate`]. Map convention: `+x` is east, `+y` is north.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum PrevailingWind {
    North,
    NorthEast,
    East,
    SouthEast,
    South,
    SouthWest,
    /// Westerly — the default; the dominant mid-latitude wind on Earth.
    #[default]
    West,
    NorthWest,
}

impl PrevailingWind {
    /// Unit vector of the direction the air *moves* — away from the source, so
    /// a `West` wind blows toward `+x` (east). Map space: `+x` east, `+y` north.
    pub fn vector(self) -> (f32, f32) {
        // 1/√2 for the diagonal components.
        const D: f32 = 0.707_106_77;
        match self {
            PrevailingWind::North => (0.0, -1.0),
            PrevailingWind::NorthEast => (-D, -D),
            PrevailingWind::East => (-1.0, 0.0),
            PrevailingWind::SouthEast => (-D, D),
            PrevailingWind::South => (0.0, 1.0),
            PrevailingWind::SouthWest => (D, D),
            PrevailingWind::West => (1.0, 0.0),
            PrevailingWind::NorthWest => (D, -D),
        }
    }
}

/// How hard hydraulic erosion carves the heightmap — drives the iteration
/// count + erodibility in [`crate::erosion`]. `None` is a true no-op (the
/// heightmap is left exactly as Path B's `height_at` built it); `Moderate` is
/// the default — a visible, natural amount of valley carving.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum ErosionStrength {
    /// No erosion — the raw Path B heightmap.
    None,
    /// Light carving — gentle valleys, ridges stay crisp.
    Light,
    /// The default — clear dendritic valleys and rounded hillslopes.
    #[default]
    Moderate,
    /// Heavy carving — deep valleys, broad sediment fans, soft ridges.
    Heavy,
}

/// World size — sets the deterministic mesh dimensions (GEO_001 §6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorldScale {
    Pocket,
    Region,
    Continent,
    SuperContinent,
    Megaplanet,
    /// A genuinely planet-sized map — a 708² grid ≈ 501k cells, ~30× the
    /// `Megaplanet`. The smaller scales read as a zone or a region; this is
    /// the true world-map scale.
    Gigaplanet,
}

impl WorldScale {
    /// Grid side `g` ≈ round(√target) for the GEO_001 §6 cell-count target.
    /// The mesh is a perimeter ring + a `(g-2)×(g-2)` jittered interior.
    pub fn grid_side(self) -> usize {
        match self {
            WorldScale::Pocket => 32,
            WorldScale::Region => 45,
            WorldScale::Continent => 91,
            WorldScale::SuperContinent => 111,
            WorldScale::Megaplanet => 128,
            WorldScale::Gigaplanet => 708,
        }
    }

    /// Exact, deterministic total cell count = `(g-2)² + 4·(g-1)`.
    /// → 1024 / 2025 / 8281 / 12321 / 16384 / 501264. The first five are the
    /// GEO_001 `[1024, 16384]` band; `Gigaplanet` deliberately exceeds it —
    /// the true planet scale (~30× `Megaplanet`).
    pub fn cell_count(self) -> usize {
        let g = self.grid_side();
        (g - 2) * (g - 2) + 4 * (g - 1)
    }

    /// Stable discriminant byte for the content hash.
    pub fn tag(self) -> u8 {
        match self {
            WorldScale::Pocket => 0,
            WorldScale::Region => 1,
            WorldScale::Continent => 2,
            WorldScale::SuperContinent => 3,
            WorldScale::Megaplanet => 4,
            WorldScale::Gigaplanet => 5,
        }
    }
}

/// World genre. **Currently inert**: stored on `CreativeSeed` and serialized,
/// but no generation stage reads it — archetype-conditioned terrain is the
/// GEO_001 `GEO-D7` deferral (V2). The CLI `--archetype` flag and the LLM
/// author still accept it for forward compatibility.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorldArchetype {
    Wuxia,
    HighFantasy,
    LowFantasy,
    Cyberpunk,
    SteamPunk,
    Postapocalyptic,
    ScienceFiction,
    Historical,
    Mythological,
    Romance,
    Mystery,
    Custom,
}

/// Coastline shape — drives the heightmap radial falloff + sea-level target.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CoastlineProfile {
    Island,
    Peninsula,
    Coastal,
    Inland,
    Archipelago,
}

impl CoastlineProfile {
    /// Target land fraction — drives the percentile sea-level pick.
    pub fn land_fraction(self) -> f32 {
        match self {
            CoastlineProfile::Island => 0.38,
            CoastlineProfile::Peninsula => 0.46,
            CoastlineProfile::Coastal => 0.55,
            CoastlineProfile::Inland => 0.70,
            CoastlineProfile::Archipelago => 0.32,
        }
    }

    /// Archipelago worlds are intentionally fragmented (scattered islands).
    pub fn is_archipelago(self) -> bool {
        matches!(self, CoastlineProfile::Archipelago)
    }

    /// Amplitude of the Inland continental dome (terrain stage). A broad radial
    /// dome biases the high-land `Inland` profile (0.70 land target) toward one
    /// coherent central landmass. Other profiles do not need it → 0.0, no
    /// terrain change. See [`crate::terrain`].
    pub fn base_amplitude(self) -> f32 {
        match self {
            CoastlineProfile::Inland => 0.75,
            _ => 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cell_counts_match_design_table() {
        assert_eq!(WorldScale::Pocket.cell_count(), 1024);
        assert_eq!(WorldScale::Region.cell_count(), 2025);
        assert_eq!(WorldScale::Continent.cell_count(), 8281);
        assert_eq!(WorldScale::SuperContinent.cell_count(), 12321);
        assert_eq!(WorldScale::Megaplanet.cell_count(), 16384);
        assert_eq!(WorldScale::Gigaplanet.cell_count(), 501_264);
    }

    #[test]
    fn cell_counts_within_bounds() {
        // the first five are the GEO_001 [1024, 16384] band; `Gigaplanet`
        // is the deliberately-larger planet scale.
        for s in [
            WorldScale::Pocket,
            WorldScale::Region,
            WorldScale::Continent,
            WorldScale::SuperContinent,
            WorldScale::Megaplanet,
            WorldScale::Gigaplanet,
        ] {
            assert!((1024..=501_264).contains(&s.cell_count()));
        }
    }

    #[test]
    fn prevailing_wind_vectors_are_distinct_unit_vectors() {
        let all = [
            PrevailingWind::North,
            PrevailingWind::NorthEast,
            PrevailingWind::East,
            PrevailingWind::SouthEast,
            PrevailingWind::South,
            PrevailingWind::SouthWest,
            PrevailingWind::West,
            PrevailingWind::NorthWest,
        ];
        for w in all {
            let (x, y) = w.vector();
            let len = (x * x + y * y).sqrt();
            assert!((len - 1.0).abs() < 1e-4, "{w:?} vector is not unit length: {len}");
        }
        // a typo'd or copy-pasted direction would share a vector with another.
        for i in 0..all.len() {
            for j in (i + 1)..all.len() {
                assert_ne!(
                    all[i].vector(),
                    all[j].vector(),
                    "{:?} and {:?} share a wind vector",
                    all[i],
                    all[j]
                );
            }
        }
    }

    #[test]
    fn creative_seed_json_without_prevailing_wind_defaults_to_west() {
        // `#[serde(default)]` lets a pre-wind config JSON still load.
        let json = r#"{
            "world_scale": "Continent",
            "world_archetype": "HighFantasy",
            "coastline_profile": "Coastal",
            "hemisphere_orientation": "Northern",
            "climate_bias": null,
            "settlement_density": "Medium",
            "culture_count": 5
        }"#;
        let cs: CreativeSeed =
            serde_json::from_str(json).expect("a pre-wind config JSON must still load");
        assert_eq!(cs.prevailing_wind, PrevailingWind::West);
        // the same JSON also predates `erosion` ⇒ #[serde(default)] → Moderate.
        assert_eq!(cs.erosion, ErosionStrength::Moderate);
    }

    #[test]
    fn erosion_strength_round_trips_through_json() {
        for e in [
            ErosionStrength::None,
            ErosionStrength::Light,
            ErosionStrength::Moderate,
            ErosionStrength::Heavy,
        ] {
            let cs = CreativeSeed { erosion: e, ..CreativeSeed::default() };
            let json = serde_json::to_string(&cs).expect("serialize");
            let back: CreativeSeed = serde_json::from_str(&json).expect("deserialize");
            assert_eq!(back.erosion, e);
        }
    }
}
