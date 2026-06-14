//! Generation tuning parameters — the granular knobs of the centralized
//! [`crate::CreativeSeed`] profile (world-gen parameterization arc).
//!
//! Every field defaults to the value that used to be a hardcoded `const`, so a
//! **default profile reproduces the byte-identical baseline** — parameterization
//! changes the *surface*, not the *output*. Macro [`IntensityKnobs`] scale
//! groups of these for quick (human/LLM) dialing; `resolved()` applies the knobs
//! and clamps every field to a sane rail (so a human typo or an LLM
//! hallucination is bounded, never panics).
//!
//! Stages add their own param struct here (P1 `TectonicsParams`, then relief,
//! climate, …). All are `#[serde(default)]` so partial / older config JSON loads.

use serde::{Deserialize, Serialize};

/// Macro "intensity" knobs — convenience scalers that multiply *groups* of
/// granular params (`effective = granular · knob`). Default `1.0` = no-op (the
/// byte-identical baseline). Grows per stage (new fields are `serde`-defaulted).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct IntensityKnobs {
    /// Mountain-building: scales fold/arc orogeny peaks + collision crustal
    /// thickening + isostasy slope (P1).
    pub orogeny: f32,
    /// How often plates collide: inversely scales the transform-fault shear
    /// ratio (higher ⇒ fewer faults ⇒ more convergent boundaries) (P1).
    pub collision_frequency: f32,
}

impl Default for IntensityKnobs {
    fn default() -> Self {
        IntensityKnobs { orogeny: 1.0, collision_frequency: 1.0 }
    }
}

/// Tectonics / isostasy tuning (was the `plates.rs` consts). Defaults are the
/// exact prior const values (byte-identical baseline).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TectonicsParams {
    /// Continental crust isostatic base height (signed, sea = 0).
    pub cont_base: f32,
    /// Oceanic crust isostatic base height.
    pub ocean_base: f32,
    /// Convergent continent–continent fold-belt peak uplift.
    pub fold_peak: f32,
    /// Subduction continental-arc peak uplift.
    pub arc_peak: f32,
    /// Subduction oceanic-side trench depth.
    pub trench_depth: f32,
    /// Oceanic–oceanic island-arc peak uplift.
    pub island_arc_peak: f32,
    /// Divergent oceanic mid-ocean-ridge peak.
    pub ridge_peak: f32,
    /// Divergent continental rift-valley depth.
    pub rift_depth: f32,
    /// Transform-fault relief.
    pub fault_peak: f32,
    /// Orogeny decay length (BFS hops from the boundary).
    pub decay_hops: f32,
    /// Oceanic crust thickness (km).
    pub ocean_crust_km: f32,
    /// Continental (neutral) crust thickness (km).
    pub cont_crust_km: f32,
    /// Extra crust stacked at a continental collision (km).
    pub collision_thicken_km: f32,
    /// Collision-plateau breadth (BFS hops; wider than `decay_hops`).
    pub plateau_hops: f32,
    /// Airy isostasy slope: base-height rise per km of crust above `cont_crust_km`.
    pub cont_iso_slope: f32,
    /// Shear-to-closing ratio above which a boundary is a transform fault.
    pub fault_shear_ratio: f32,
    /// Plate-boundary fractal warp frequency / amplitude / octaves.
    pub warp_freq: f32,
    pub warp_amp: f32,
    pub warp_octaves: u32,
}

impl Default for TectonicsParams {
    fn default() -> Self {
        // These are the exact values that were hardcoded in `plates.rs`.
        TectonicsParams {
            cont_base: 0.10,
            ocean_base: -0.55,
            fold_peak: 0.85,
            arc_peak: 0.55,
            trench_depth: 0.30,
            island_arc_peak: 0.45,
            ridge_peak: 0.20,
            rift_depth: 0.28,
            fault_peak: 0.05,
            decay_hops: 4.0,
            ocean_crust_km: 7.0,
            cont_crust_km: 35.0,
            collision_thicken_km: 35.0,
            plateau_hops: 7.0,
            cont_iso_slope: 0.30 / 35.0,
            fault_shear_ratio: 2.0,
            warp_freq: 1.8,
            warp_amp: 0.32,
            warp_octaves: 4,
        }
    }
}

impl TectonicsParams {
    /// Apply the macro [`IntensityKnobs`] and clamp every field to a sane rail,
    /// returning the **effective** params the generator uses. With default knobs
    /// (all `1.0`) and default params this is the identity (byte-identical
    /// baseline): `x · 1.0 == x` and `x / 1.0 == x` exactly, and every default
    /// is inside its rail.
    pub fn resolved(&self, k: &IntensityKnobs) -> TectonicsParams {
        let o = k.orogeny.clamp(0.0, 3.0);
        // Guard the divisor away from 0 (collision_frequency scales 1/ratio).
        let cf = k.collision_frequency.clamp(0.05, 3.0);
        TectonicsParams {
            cont_base: self.cont_base.clamp(-2.0, 2.0),
            ocean_base: self.ocean_base.clamp(-2.0, 2.0),
            fold_peak: (self.fold_peak * o).clamp(0.0, 5.0),
            arc_peak: (self.arc_peak * o).clamp(0.0, 5.0),
            trench_depth: self.trench_depth.clamp(0.0, 5.0),
            island_arc_peak: self.island_arc_peak.clamp(0.0, 5.0),
            ridge_peak: self.ridge_peak.clamp(0.0, 5.0),
            rift_depth: self.rift_depth.clamp(0.0, 5.0),
            fault_peak: self.fault_peak.clamp(0.0, 5.0),
            decay_hops: self.decay_hops.clamp(0.5, 30.0),
            ocean_crust_km: self.ocean_crust_km.clamp(0.0, 300.0),
            cont_crust_km: self.cont_crust_km.clamp(0.0, 300.0),
            collision_thicken_km: (self.collision_thicken_km * o).clamp(0.0, 300.0),
            plateau_hops: self.plateau_hops.clamp(0.5, 30.0),
            cont_iso_slope: (self.cont_iso_slope * o).clamp(0.0, 0.1),
            fault_shear_ratio: (self.fault_shear_ratio / cf).clamp(0.25, 20.0),
            warp_freq: self.warp_freq.clamp(0.0, 10.0),
            warp_amp: self.warp_amp.clamp(0.0, 2.0),
            warp_octaves: self.warp_octaves.clamp(1, 8),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_knobs_are_identity() {
        let p = TectonicsParams::default();
        let r = p.resolved(&IntensityKnobs::default());
        assert_eq!(p, r, "default knobs must reproduce the params exactly (byte-identical)");
    }

    #[test]
    fn orogeny_scales_mountain_building() {
        let p = TectonicsParams::default();
        let r = p.resolved(&IntensityKnobs { orogeny: 2.0, ..Default::default() });
        assert!((r.fold_peak - p.fold_peak * 2.0).abs() < 1e-6);
        assert!((r.collision_thicken_km - p.collision_thicken_km * 2.0).abs() < 1e-6);
        // non-orogeny fields untouched.
        assert_eq!(r.trench_depth, p.trench_depth);
    }

    #[test]
    fn collision_frequency_inversely_scales_fault_ratio() {
        let p = TectonicsParams::default();
        let more = p.resolved(&IntensityKnobs { collision_frequency: 2.0, ..Default::default() });
        let less = p.resolved(&IntensityKnobs { collision_frequency: 0.5, ..Default::default() });
        assert!(more.fault_shear_ratio < p.fault_shear_ratio, "more collisions ⇒ lower ratio");
        assert!(less.fault_shear_ratio > p.fault_shear_ratio, "fewer collisions ⇒ higher ratio");
    }

    #[test]
    fn knobs_and_params_clamp_no_panic() {
        let p = TectonicsParams::default();
        let r = p.resolved(&IntensityKnobs { orogeny: 999.0, collision_frequency: 0.0 });
        assert_eq!(r.fold_peak, (p.fold_peak * 3.0).clamp(0.0, 5.0), "orogeny clamps to 3");
        assert!(r.fault_shear_ratio.is_finite(), "cf=0 must not divide-by-zero to inf");
        // a garbage granular value clamps too.
        let junk = TectonicsParams { fold_peak: 999.0, decay_hops: -5.0, ..p };
        let rj = junk.resolved(&IntensityKnobs::default());
        assert_eq!(rj.fold_peak, 5.0);
        assert_eq!(rj.decay_hops, 0.5);
    }
}
