//! TMP-Q1 §5 — Decoration density configuration.
//!
//! Opt-in via [`crate::types::template::TilemapTemplate::decoration_density`]:
//! `None` (the implicit serde default) keeps the V2 golden byte-identical
//! and the `DecorationPlacer` early-returns. `Some(DecorationDensity)`
//! activates the density pass (chunk C).
//!
//! Spec: [`docs/specs/2026-05-28-decoration-placer-density-pass.md`](../../../../docs/specs/2026-05-28-decoration-placer-density-pass.md)

use serde::{Deserialize, Serialize};

/// Per-zone decoration density target.
///
/// `target = clamp(round(fraction_of_free * free_count), min_per_zone, max_per_zone)`.
///
/// Per-tier defaults (Q1 PO-locked, spec §5):
/// - Town (64²)     : `{ min: 20, max: 40, fraction: 0.10 }`
/// - District (128²): `{ min: 50, max: 90, fraction: 0.08 }`
/// - Country (192²) : `{ min: 100, max: 200, fraction: 0.06 }`
/// - Continent (256²): `{ min: 200, max: 500, fraction: 0.04 }`
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct DecorationDensity {
    pub min_per_zone: u32,
    pub max_per_zone: u32,
    pub fraction_of_free: f32,
}

/// TMP-Q1 chunk D MED-2 — validation error for misconfigured
/// `DecorationDensity` fields. Surfaces source-pinpoint diagnostics
/// when an author template ships pathological values.
///
/// `Eq` dropped because the `FractionOutOfRange` variant carries `f32`
/// which only impls `PartialEq`. Same discipline as `TilemapTemplate`
/// (see `types/template.rs` "Note on Eq").
#[derive(Debug, Clone, PartialEq)]
pub enum DecorationDensityError {
    /// `min_per_zone > max_per_zone` — clamp would degenerate to min.
    MinExceedsMax { min: u32, max: u32 },
    /// `fraction_of_free` outside `[0.0, 1.0]` or non-finite.
    FractionOutOfRange { value: f32 },
    /// `max_per_zone > MAX_REASONABLE_PER_ZONE` — practical upper limit
    /// to prevent operator typos from running the algorithm to free-mask
    /// exhaustion needlessly.
    MaxTooHigh { max: u32, limit: u32 },
}

impl std::fmt::Display for DecorationDensityError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MinExceedsMax { min, max } => write!(
                f,
                "decoration_density.min_per_zone ({min}) > max_per_zone ({max}) — clamp would degenerate"
            ),
            Self::FractionOutOfRange { value } => write!(
                f,
                "decoration_density.fraction_of_free ({value}) must be in [0.0, 1.0] and finite"
            ),
            Self::MaxTooHigh { max, limit } => write!(
                f,
                "decoration_density.max_per_zone ({max}) exceeds practical limit ({limit})"
            ),
        }
    }
}

impl std::error::Error for DecorationDensityError {}

impl DecorationDensity {
    /// Practical upper bound on `max_per_zone`. The algorithm self-limits
    /// via free-mask exhaustion so larger values don't DoS, but a value
    /// in the millions is almost certainly an author typo.
    pub const MAX_REASONABLE_PER_ZONE: u32 = 10_000;

    /// TMP-Q1 chunk D MED-2 — validate field bounds at template-load /
    /// placer-entry. Called from `DecorationPlacer::process` before the
    /// per-zone loop so a bad template fails fast with a clear error
    /// rather than producing silent under-placement.
    pub fn validate(&self) -> Result<(), DecorationDensityError> {
        if self.min_per_zone > self.max_per_zone {
            return Err(DecorationDensityError::MinExceedsMax {
                min: self.min_per_zone,
                max: self.max_per_zone,
            });
        }
        if !self.fraction_of_free.is_finite() || !(0.0..=1.0).contains(&self.fraction_of_free) {
            return Err(DecorationDensityError::FractionOutOfRange {
                value: self.fraction_of_free,
            });
        }
        if self.max_per_zone > Self::MAX_REASONABLE_PER_ZONE {
            return Err(DecorationDensityError::MaxTooHigh {
                max: self.max_per_zone,
                limit: Self::MAX_REASONABLE_PER_ZONE,
            });
        }
        Ok(())
    }

    /// Town-tier preset.
    pub const TOWN: Self = Self {
        min_per_zone: 20,
        max_per_zone: 40,
        fraction_of_free: 0.10,
    };
    /// District-tier preset.
    pub const DISTRICT: Self = Self {
        min_per_zone: 50,
        max_per_zone: 90,
        fraction_of_free: 0.08,
    };
    /// Country-tier preset.
    pub const COUNTRY: Self = Self {
        min_per_zone: 100,
        max_per_zone: 200,
        fraction_of_free: 0.06,
    };
    /// Continent-tier preset.
    pub const CONTINENT: Self = Self {
        min_per_zone: 200,
        max_per_zone: 500,
        fraction_of_free: 0.04,
    };

    /// Compute the placement target for a zone with `free_count` walkable
    /// tiles remaining after upstream placers have run.
    ///
    /// `clamp(round(fraction_of_free * free_count), min_per_zone, max_per_zone)`.
    /// Non-finite or negative fraction is treated as zero (defensive).
    ///
    /// **Caller responsibility:** when `free_count == 0` this returns
    /// `min_per_zone` (the clamp floor). A target ≥ 1 against an empty
    /// free-mask is unrealizable; callers (chunk C placer) MUST check
    /// `free_count > 0` (or equivalently `free.count_ones() > 0`)
    /// before consuming the target.
    pub fn target_for(&self, free_count: u32) -> u32 {
        if !self.fraction_of_free.is_finite() || self.fraction_of_free <= 0.0 {
            return self.min_per_zone.min(self.max_per_zone);
        }
        let raw = (self.fraction_of_free * free_count as f32).round();
        let clamped = raw.clamp(self.min_per_zone as f32, self.max_per_zone as f32);
        clamped as u32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn target_clamps_to_min_when_fraction_under_shoots() {
        // 0.10 * 100 = 10 — below Town.min (20); clamps up.
        assert_eq!(DecorationDensity::TOWN.target_for(100), 20);
    }

    #[test]
    fn target_clamps_to_max_when_fraction_over_shoots() {
        // 0.10 * 10_000 = 1000 — above Town.max (40); clamps down.
        assert_eq!(DecorationDensity::TOWN.target_for(10_000), 40);
    }

    #[test]
    fn target_in_range_passes_through() {
        // 0.10 * 300 = 30 — within Town [20, 40].
        assert_eq!(DecorationDensity::TOWN.target_for(300), 30);
    }

    #[test]
    fn target_handles_non_finite_fraction_as_zero() {
        let bad = DecorationDensity { min_per_zone: 5, max_per_zone: 10, fraction_of_free: f32::NAN };
        assert_eq!(bad.target_for(1_000), 5);
    }

    #[test]
    fn target_handles_negative_fraction_as_zero() {
        let bad = DecorationDensity { min_per_zone: 5, max_per_zone: 10, fraction_of_free: -0.5 };
        assert_eq!(bad.target_for(1_000), 5);
    }

    #[test]
    fn tier_presets_match_spec_q1_lock() {
        assert_eq!(DecorationDensity::TOWN.min_per_zone, 20);
        assert_eq!(DecorationDensity::CONTINENT.max_per_zone, 500);
    }

    #[test]
    fn serde_round_trip() {
        let json = serde_json::to_string(&DecorationDensity::TOWN).unwrap();
        let back: DecorationDensity = serde_json::from_str(&json).unwrap();
        assert_eq!(back, DecorationDensity::TOWN);
    }

    #[test]
    fn validate_accepts_all_tier_presets() {
        // MED-2 from chunk-D /review-impl: all PO-locked tier presets
        // must pass validation (they are the conformant baseline).
        DecorationDensity::TOWN.validate().expect("TOWN must validate");
        DecorationDensity::DISTRICT.validate().expect("DISTRICT must validate");
        DecorationDensity::COUNTRY.validate().expect("COUNTRY must validate");
        DecorationDensity::CONTINENT.validate().expect("CONTINENT must validate");
    }

    #[test]
    fn validate_rejects_min_exceeds_max() {
        let bad = DecorationDensity { min_per_zone: 50, max_per_zone: 20, fraction_of_free: 0.10 };
        assert!(matches!(
            bad.validate().unwrap_err(),
            DecorationDensityError::MinExceedsMax { min: 50, max: 20 }
        ));
    }

    #[test]
    fn validate_rejects_fraction_out_of_range() {
        for bad_fraction in [-0.1, 1.1, f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            let bad = DecorationDensity {
                min_per_zone: 20,
                max_per_zone: 40,
                fraction_of_free: bad_fraction,
            };
            assert!(
                matches!(
                    bad.validate().unwrap_err(),
                    DecorationDensityError::FractionOutOfRange { .. }
                ),
                "fraction {bad_fraction} must be rejected"
            );
        }
    }

    #[test]
    fn validate_rejects_max_too_high() {
        let bad = DecorationDensity {
            min_per_zone: 10,
            max_per_zone: 1_000_000,
            fraction_of_free: 0.10,
        };
        assert!(matches!(
            bad.validate().unwrap_err(),
            DecorationDensityError::MaxTooHigh { max: 1_000_000, .. }
        ));
    }

    #[test]
    fn target_for_zero_free_count_returns_min() {
        // LOW-1 fix: locks the caller-responsibility contract. When the
        // free mask is empty, target_for still returns min_per_zone (the
        // clamp floor). Chunk C must skip the zone before consuming.
        assert_eq!(DecorationDensity::TOWN.target_for(0), 20);
        assert_eq!(DecorationDensity::CONTINENT.target_for(0), 200);
    }
}
