//! TMP-Q2 §4 — Biome-theme definition (chunk A).
//!
//! Opt-in via [`crate::types::template::TilemapTemplate::background_biome`]
//! and [`crate::types::template::ZoneSpec::biome_theme`]: `None` (the
//! implicit serde default) keeps the V2 path byte-identical and the
//! chunk-B `BiomeThemePainter` early-returns. `Some(id)` activates the
//! biome-theme pass — id resolves to a registry [`BiomeThemeDef`].
//!
//! Spec: [`docs/specs/2026-05-29-biome-theme-painter.md`](../../../../docs/specs/2026-05-29-biome-theme-painter.md)

use serde::{Deserialize, Serialize};

/// A biome theme = weighted mix of [`crate::types::tile::TerrainKind`]
/// variants. Stored in registry TOML under `[[biome]]` array of tables,
/// indexed by `Registry::biome_by_id` for O(1) lookup at placer time.
///
/// `mix` is a weighted distribution sampled per-tile by chunk-B Perlin
/// noise + CDF threshold. Entries with weight 70/20/10 produce roughly
/// 70%/20%/10% of zone tiles assigned to that `TerrainKind` (modulo
/// Perlin's spatial correlation — patches, not i.i.d.).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BiomeThemeDef {
    /// Stable namespaced id (e.g. `lw:biome.forest_temperate`).
    /// Validated by [`crate::registry::is_valid_id`] at registry load.
    pub id: String,
    /// Display label ("Temperate Forest"). UI shows this.
    pub label: String,
    /// Weighted distribution over [`crate::types::tile::TerrainKind`]
    /// variants. Must be non-empty; validated by [`Self::validate`].
    pub mix: Vec<BiomeMixEntry>,
}

/// A single weighted entry in a [`BiomeThemeDef::mix`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BiomeMixEntry {
    /// `TerrainKind::tag()` value (snake_case: `"grass"`, `"forest"`,
    /// `"mountain"`, `"water"`, `"sand"`, `"snow"`, `"swamp"`, `"road"`,
    /// `"rough"`, `"subterranean"`). Validated at registry load —
    /// unknown tags reject the whole registry.
    pub terrain: String,
    /// Relative weight in the mix's CDF. Must be finite and positive
    /// (zero would silently never-pick; negative breaks CDF arithmetic).
    pub weight: f32,
}

/// Validation error for [`BiomeThemeDef`] / [`BiomeMixEntry`].
///
/// `Eq` dropped (and on the parent `BiomeThemeError`) because the
/// `NonFiniteWeight` / `NonPositiveWeight` variants carry `f32` which
/// only impls `PartialEq`. Same discipline as `DecorationDensityError`
/// (see `types/decoration.rs` "Eq dropped" note).
#[derive(Debug, Clone, PartialEq)]
pub enum BiomeThemeError {
    /// `mix.is_empty()` — placer cannot sample from an empty pool.
    EmptyMix,
    /// Weight is NaN, +Inf, or -Inf — CDF arithmetic would propagate.
    NonFiniteWeight { idx: usize, value: f32 },
    /// Weight ≤ 0.0 — zero-weight entry never picks; negative breaks CDF.
    NonPositiveWeight { idx: usize, value: f32 },
    /// `terrain` is not a `TerrainKind::tag()` value.
    UnknownTerrain { idx: usize, tag: String },
    /// Same `terrain` tag appears in two `mix` entries — would silently
    /// over-weight the kind. Author must consolidate weights.
    DuplicateTerrain { tag: String },
}

impl std::fmt::Display for BiomeThemeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyMix => write!(f, "biome theme mix must be non-empty"),
            Self::NonFiniteWeight { idx, value } => write!(
                f,
                "biome theme mix[{idx}].weight ({value}) must be finite"
            ),
            Self::NonPositiveWeight { idx, value } => write!(
                f,
                "biome theme mix[{idx}].weight ({value}) must be > 0 \
                 (zero-weight entries never sample; negatives break CDF)"
            ),
            Self::UnknownTerrain { idx, tag } => write!(
                f,
                "biome theme mix[{idx}].terrain ({tag:?}) is not a TerrainKind tag \
                 (grass, forest, mountain, water, sand, snow, swamp, road, rough, subterranean)"
            ),
            Self::DuplicateTerrain { tag } => write!(
                f,
                "biome theme mix contains duplicate terrain {tag:?} \
                 (author must consolidate weights into one entry)"
            ),
        }
    }
}

impl std::error::Error for BiomeThemeError {}

impl BiomeThemeDef {
    /// Validate the theme's `mix`. Called from `Registry::from_file`
    /// before the index is built so a bad theme fails the whole
    /// registry load with a precise error.
    ///
    /// Uses [`crate::registry::is_valid_biome_key`] to check terrain
    /// tags — the same check `ObjectKindDef.biomes` uses, so adding a
    /// future `TerrainKind` variant fails fast in both places.
    pub fn validate(&self) -> Result<(), BiomeThemeError> {
        if self.mix.is_empty() {
            return Err(BiomeThemeError::EmptyMix);
        }
        let mut seen: std::collections::HashSet<&str> =
            std::collections::HashSet::with_capacity(self.mix.len());
        for (idx, entry) in self.mix.iter().enumerate() {
            if !entry.weight.is_finite() {
                return Err(BiomeThemeError::NonFiniteWeight {
                    idx,
                    value: entry.weight,
                });
            }
            if entry.weight <= 0.0 {
                return Err(BiomeThemeError::NonPositiveWeight {
                    idx,
                    value: entry.weight,
                });
            }
            if !crate::registry::is_valid_biome_key(&entry.terrain) {
                return Err(BiomeThemeError::UnknownTerrain {
                    idx,
                    tag: entry.terrain.clone(),
                });
            }
            if !seen.insert(entry.terrain.as_str()) {
                return Err(BiomeThemeError::DuplicateTerrain {
                    tag: entry.terrain.clone(),
                });
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mk_entry(terrain: &str, weight: f32) -> BiomeMixEntry {
        BiomeMixEntry {
            terrain: terrain.to_string(),
            weight,
        }
    }

    fn mk_theme(id: &str, mix: Vec<BiomeMixEntry>) -> BiomeThemeDef {
        BiomeThemeDef {
            id: id.to_string(),
            label: "T".to_string(),
            mix,
        }
    }

    #[test]
    fn validate_accepts_well_formed_mix() {
        let theme = mk_theme(
            "lw:biome.forest_temperate",
            vec![
                mk_entry("forest", 70.0),
                mk_entry("grass", 20.0),
                mk_entry("rough", 10.0),
            ],
        );
        theme.validate().expect("forest_temperate must validate");
    }

    #[test]
    fn validate_rejects_empty_mix() {
        let theme = mk_theme("lw:biome.bad", vec![]);
        assert_eq!(theme.validate().unwrap_err(), BiomeThemeError::EmptyMix);
    }

    #[test]
    fn validate_rejects_non_finite_weight() {
        for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            let theme = mk_theme(
                "lw:biome.bad",
                vec![mk_entry("grass", 1.0), mk_entry("forest", bad)],
            );
            assert!(
                matches!(
                    theme.validate().unwrap_err(),
                    BiomeThemeError::NonFiniteWeight { idx: 1, .. }
                ),
                "weight {bad} must be rejected as non-finite"
            );
        }
    }

    #[test]
    fn validate_rejects_non_positive_weight() {
        for bad in [0.0_f32, -0.1, -1.0] {
            let theme = mk_theme(
                "lw:biome.bad",
                vec![mk_entry("grass", 1.0), mk_entry("forest", bad)],
            );
            assert!(
                matches!(
                    theme.validate().unwrap_err(),
                    BiomeThemeError::NonPositiveWeight { idx: 1, .. }
                ),
                "weight {bad} must be rejected as non-positive"
            );
        }
    }

    #[test]
    fn validate_rejects_unknown_terrain() {
        let theme = mk_theme(
            "lw:biome.bad",
            vec![mk_entry("grass", 1.0), mk_entry("atmosphere", 1.0)],
        );
        assert!(matches!(
            theme.validate().unwrap_err(),
            BiomeThemeError::UnknownTerrain { idx: 1, .. }
        ));
    }

    #[test]
    fn validate_rejects_duplicate_terrain() {
        let theme = mk_theme(
            "lw:biome.bad",
            vec![
                mk_entry("grass", 50.0),
                mk_entry("forest", 30.0),
                mk_entry("grass", 20.0),
            ],
        );
        assert!(matches!(
            theme.validate().unwrap_err(),
            BiomeThemeError::DuplicateTerrain { .. }
        ));
    }

    #[test]
    fn serde_round_trip_preserves_mix_order_and_weights() {
        let theme = mk_theme(
            "lw:biome.swamp_mangrove",
            vec![
                mk_entry("swamp", 60.0),
                mk_entry("water", 25.0),
                mk_entry("grass", 15.0),
            ],
        );
        let json = serde_json::to_string(&theme).unwrap();
        let back: BiomeThemeDef = serde_json::from_str(&json).unwrap();
        assert_eq!(back, theme);
    }
}
