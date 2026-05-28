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

impl DecorationDensity {
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
    fn target_for_zero_free_count_returns_min() {
        // LOW-1 fix: locks the caller-responsibility contract. When the
        // free mask is empty, target_for still returns min_per_zone (the
        // clamp floor). Chunk C must skip the zone before consuming.
        assert_eq!(DecorationDensity::TOWN.target_for(0), 20);
        assert_eq!(DecorationDensity::CONTINENT.target_for(0), 200);
    }
}
