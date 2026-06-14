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
    /// Continental relief detail: scales the belt ridged-range + hill + interior
    /// upland amplitudes (P2). Higher = more rugged/jagged land.
    pub relief: f32,
    /// Ocean depth: scales the *physical* abyssal depth (`ocean_abyss`) (P2).
    /// Higher = deeper oceans (lower deep-ocean u16; saturates at the floor).
    pub ocean_depth: f32,
    /// Global warmth: shifts sea-level temperatures (`±(warmth−1)·20 °C`) (P3).
    /// >1 = hotter world (more tropics/arid), <1 = colder (more polar/boreal).
    pub warmth: f32,
    /// Rainfall: scales the latitude-band precipitation (P3). >1 = wetter
    /// (fewer deserts), <1 = drier.
    pub rainfall: f32,
    /// Seasonality: scales the *latitude-dependent* seasonal amplitude (P3). >1
    /// = harsher winters/summers (more continental), <1 = milder. NOTE: scales
    /// `amp_maritime`/`amp_cont_gain` only, **not** the equatorial floor
    /// `amp_eq` — so `seasonality=0` leaves the physically-correct ~2 °C tropical
    /// swing, not a dead-flat year (same "scale the variable part, keep the
    /// floor" shape as `ocean_depth` scaling `ocean_abyss` not `ocean_full`).
    pub seasonality: f32,
}

impl Default for IntensityKnobs {
    fn default() -> Self {
        IntensityKnobs {
            orogeny: 1.0,
            collision_frequency: 1.0,
            relief: 1.0,
            ocean_depth: 1.0,
            warmth: 1.0,
            rainfall: 1.0,
            seasonality: 1.0,
        }
    }
}

/// Climate classification tuning (was the `climate.rs` consts + the inline Köppen
/// classifier cutoffs). Defaults are the exact prior values (byte-identical).
/// *(P3 scope: the temperature/precip/seasonality/Köppen/highland tuning of
/// `climate::build`. The moisture-transport consts and the cross-module
/// `wetness()`/`bias_delta` tables are a tracked P3 follow-up.)*
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ClimateParams {
    pub t_eq: f32,
    pub t_pole: f32,
    pub lapse_c: f32,
    pub precip_eq: f32,
    pub precip_subtropic: f32,
    pub precip_midlat: f32,
    pub precip_polar: f32,
    pub amp_eq: f32,
    pub amp_maritime: f32,
    pub amp_cont_gain: f32,
    pub winter_frac: f32,
    pub highland_elev: f32,
    // Köppen classifier cutoffs (°C / fraction).
    //
    // CLAMP-NOT-VALIDATE: `resolved()` rails each cutoff to a finite range but
    // does NOT cross-validate their *ordering* (e.g. nothing forbids
    // `boreal_cold_c > tropical_cold_c`). A pathological profile yields an
    // odd-but-deterministic cascade — never a panic. GIGO is acceptable for a
    // creative tuning surface; the load-bearing invariant is determinism, not
    // climatological sanity.
    //
    // DORMANT AT DEFAULT `winter_frac`: the live pipeline pins `winter_frac=0.5`
    // (v1 — Mediterranean unreachable by design), so `med_winter_frac`,
    // `winter_summer_thresh`, `winter_winter_thresh`, and the dry-summer/winter
    // aridity offsets only take effect once `winter_frac` is overridden (config
    // path) or the deferred v2 winter-seasonality lands. They are exposed ahead
    // of that work, not dead.
    pub polar_warm_c: f32,
    pub tropical_cold_c: f32,
    pub boreal_cold_c: f32,
    pub med_winter_frac: f32,
    pub subtropical_warm_c: f32,
    pub aridity_slope: f32,
    pub aridity_offset_dry_summer: f32,
    pub aridity_offset_dry_winter: f32,
    pub aridity_offset_even: f32,
    pub winter_summer_thresh: f32,
    pub winter_winter_thresh: f32,
}

impl Default for ClimateParams {
    fn default() -> Self {
        // Exact values that were hardcoded in `climate.rs`.
        ClimateParams {
            t_eq: 28.0,
            t_pole: -15.0,
            lapse_c: 40.0,
            precip_eq: 2400.0,
            precip_subtropic: 180.0,
            precip_midlat: 900.0,
            precip_polar: 150.0,
            amp_eq: 2.0,
            amp_maritime: 4.0,
            amp_cont_gain: 24.0,
            winter_frac: 0.5,
            highland_elev: 0.30,
            polar_warm_c: 10.0,
            tropical_cold_c: 18.0,
            boreal_cold_c: -3.0,
            med_winter_frac: 0.65,
            subtropical_warm_c: 22.0,
            aridity_slope: 20.0,
            aridity_offset_dry_summer: -70.0,
            aridity_offset_dry_winter: 140.0,
            aridity_offset_even: 70.0,
            winter_summer_thresh: 0.70,
            winter_winter_thresh: 0.30,
        }
    }
}

impl ClimateParams {
    /// Apply the macro `warmth`/`rainfall`/`seasonality` knobs + clamp. Identity
    /// at default knobs (byte-identical): `warmth=1 ⇒ +0 °C`, `×1.0` elsewhere.
    pub fn resolved(&self, k: &IntensityKnobs) -> ClimateParams {
        let warm_shift = (k.warmth.clamp(0.0, 3.0) - 1.0) * 20.0;
        let rain = k.rainfall.clamp(0.0, 5.0);
        let seas = k.seasonality.clamp(0.0, 5.0);
        ClimateParams {
            t_eq: (self.t_eq + warm_shift).clamp(-60.0, 80.0),
            t_pole: (self.t_pole + warm_shift).clamp(-80.0, 60.0),
            lapse_c: self.lapse_c.clamp(0.0, 200.0),
            precip_eq: (self.precip_eq * rain).clamp(0.0, 20000.0),
            precip_subtropic: (self.precip_subtropic * rain).clamp(0.0, 20000.0),
            precip_midlat: (self.precip_midlat * rain).clamp(0.0, 20000.0),
            precip_polar: (self.precip_polar * rain).clamp(0.0, 20000.0),
            amp_eq: self.amp_eq.clamp(0.0, 60.0),
            amp_maritime: (self.amp_maritime * seas).clamp(0.0, 80.0),
            amp_cont_gain: (self.amp_cont_gain * seas).clamp(0.0, 120.0),
            winter_frac: self.winter_frac.clamp(0.0, 1.0),
            highland_elev: self.highland_elev.clamp(0.0, 1.0),
            polar_warm_c: self.polar_warm_c.clamp(-40.0, 40.0),
            tropical_cold_c: self.tropical_cold_c.clamp(-40.0, 40.0),
            boreal_cold_c: self.boreal_cold_c.clamp(-40.0, 40.0),
            med_winter_frac: self.med_winter_frac.clamp(0.0, 1.0),
            subtropical_warm_c: self.subtropical_warm_c.clamp(-40.0, 60.0),
            aridity_slope: self.aridity_slope.clamp(0.0, 200.0),
            aridity_offset_dry_summer: self.aridity_offset_dry_summer.clamp(-1000.0, 1000.0),
            aridity_offset_dry_winter: self.aridity_offset_dry_winter.clamp(-1000.0, 1000.0),
            aridity_offset_even: self.aridity_offset_even.clamp(-1000.0, 1000.0),
            winter_summer_thresh: self.winter_summer_thresh.clamp(0.0, 1.0),
            winter_winter_thresh: self.winter_winter_thresh.clamp(0.0, 1.0),
        }
    }
}

/// Continental relief, ocean bathymetry, quantize and heightmap-noise tuning
/// (was the `terrain.rs` consts). Defaults are the exact prior values
/// (byte-identical baseline). Noise *salts* and the fixed `ARCH_ISLANDS`
/// geometry stay internal in `terrain.rs`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ReliefParams {
    // Profile-mode domain warp + heightmap noise (frequency / octaves / weights).
    pub warp_freq: f32,
    pub warp_amp: f32,
    pub warp_octaves: u32,
    pub cont_freq: f32,
    pub cont_octaves: u32,
    pub mtn_freq: f32,
    pub mtn_octaves: u32,
    pub belt_freq: f32,
    pub belt_octaves: u32,
    pub hill_freq: f32,
    pub hill_octaves: u32,
    pub cont_weight: f32,
    pub mtn_weight: f32,
    pub hill_weight: f32,
    // Tectonic-mode relief.
    pub tec_hill_weight: f32,
    pub tec_plain_weight: f32,
    pub plain_freq: f32,
    pub rugged_freq: f32,
    pub tect_uplift_lo: f32,
    pub tect_uplift_hi: f32,
    pub tect_belt_lift: f32,
    pub tect_range_weight: f32,
    pub interior_rugged_cap: f32,
    // Ocean bathymetry.
    pub ocean_shelf: f32,
    pub ocean_abyss: f32,
    pub ocean_abyss_hops: f32,
    pub ocean_ripple_weight: f32,
    pub ocean_ripple_freq: f32,
    pub ocean_arc_gate_near: f32,
    pub ocean_arc_gate_far: f32,
    // Quantize (hypsometry).
    pub sea_frac: f32,
    pub land_full: f32,
    pub ocean_full: f32,
    // Archipelago disc radius (Profile mode).
    pub arch_radius: f32,
}

impl Default for ReliefParams {
    fn default() -> Self {
        // Exact values that were hardcoded in `terrain.rs`.
        ReliefParams {
            warp_freq: 2.2,
            warp_amp: 0.09,
            warp_octaves: 3,
            cont_freq: 1.7,
            cont_octaves: 4,
            mtn_freq: 4.5,
            mtn_octaves: 5,
            belt_freq: 1.9,
            belt_octaves: 3,
            hill_freq: 7.5,
            hill_octaves: 4,
            cont_weight: 1.00,
            mtn_weight: 1.35,
            hill_weight: 0.15,
            tec_hill_weight: 0.22,
            tec_plain_weight: 0.022,
            plain_freq: 2.6,
            rugged_freq: 2.2,
            tect_uplift_lo: 0.20,
            tect_uplift_hi: 0.45,
            tect_belt_lift: 0.12,
            tect_range_weight: 0.60,
            interior_rugged_cap: 0.28,
            ocean_shelf: -0.04,
            ocean_abyss: -0.58,
            ocean_abyss_hops: 7.0,
            ocean_ripple_weight: 0.02,
            ocean_ripple_freq: 5.0,
            ocean_arc_gate_near: 1.0,
            ocean_arc_gate_far: 4.0,
            sea_frac: 0.40,
            land_full: 0.78,
            ocean_full: 0.62,
            arch_radius: 0.30,
        }
    }
}

impl ReliefParams {
    /// Apply the macro [`IntensityKnobs`] (`relief`, `ocean_depth`) and clamp
    /// every field to a sane rail. Identity at default knobs (byte-identical).
    pub fn resolved(&self, k: &IntensityKnobs) -> ReliefParams {
        let r = k.relief.clamp(0.0, 4.0);
        let od = k.ocean_depth.clamp(0.1, 4.0);
        ReliefParams {
            // noise / frequencies — clamped, not knob-scaled.
            warp_freq: self.warp_freq.clamp(0.0, 20.0),
            warp_amp: self.warp_amp.clamp(0.0, 2.0),
            warp_octaves: self.warp_octaves.clamp(1, 8),
            cont_freq: self.cont_freq.clamp(0.1, 20.0),
            cont_octaves: self.cont_octaves.clamp(1, 8),
            mtn_freq: self.mtn_freq.clamp(0.1, 20.0),
            mtn_octaves: self.mtn_octaves.clamp(1, 8),
            belt_freq: self.belt_freq.clamp(0.1, 20.0),
            belt_octaves: self.belt_octaves.clamp(1, 8),
            hill_freq: self.hill_freq.clamp(0.1, 20.0),
            hill_octaves: self.hill_octaves.clamp(1, 8),
            cont_weight: self.cont_weight.clamp(0.0, 5.0),
            mtn_weight: (self.mtn_weight * r).clamp(0.0, 10.0),
            hill_weight: (self.hill_weight * r).clamp(0.0, 5.0),
            tec_hill_weight: (self.tec_hill_weight * r).clamp(0.0, 5.0),
            tec_plain_weight: self.tec_plain_weight.clamp(0.0, 5.0),
            plain_freq: self.plain_freq.clamp(0.1, 20.0),
            rugged_freq: self.rugged_freq.clamp(0.1, 20.0),
            tect_uplift_lo: self.tect_uplift_lo.clamp(0.0, 1.0),
            tect_uplift_hi: self.tect_uplift_hi.clamp(0.01, 2.0),
            tect_belt_lift: (self.tect_belt_lift * r).clamp(0.0, 2.0),
            tect_range_weight: (self.tect_range_weight * r).clamp(0.0, 5.0),
            interior_rugged_cap: (self.interior_rugged_cap * r).clamp(0.0, 2.0),
            ocean_shelf: self.ocean_shelf.clamp(-2.0, 0.0),
            // `ocean_depth` scales the *physical* abyssal depth only. The
            // quantize denominator (`ocean_full`, below) stays fixed — scaling
            // both would leave `|e|/ocean_full` invariant, so a "deeper" abyss
            // wouldn't actually lower the deep-ocean u16 (review-impl P2, #1).
            ocean_abyss: (self.ocean_abyss * od).clamp(-3.0, 0.0),
            ocean_abyss_hops: self.ocean_abyss_hops.clamp(0.5, 50.0),
            ocean_ripple_weight: self.ocean_ripple_weight.clamp(0.0, 1.0),
            ocean_ripple_freq: self.ocean_ripple_freq.clamp(0.1, 20.0),
            ocean_arc_gate_near: self.ocean_arc_gate_near.clamp(0.0, 50.0),
            ocean_arc_gate_far: self.ocean_arc_gate_far.clamp(0.0, 50.0),
            sea_frac: self.sea_frac.clamp(0.05, 0.95),
            land_full: self.land_full.clamp(0.05, 5.0),
            ocean_full: self.ocean_full.clamp(0.05, 5.0),
            arch_radius: self.arch_radius.clamp(0.01, 1.5),
        }
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
    fn relief_default_knobs_are_identity() {
        let p = ReliefParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default knobs must be identity");
    }

    #[test]
    fn relief_and_ocean_depth_knobs_scale() {
        let p = ReliefParams::default();
        let r = p.resolved(&IntensityKnobs { relief: 2.0, ocean_depth: 1.5, ..Default::default() });
        assert!((r.tect_range_weight - p.tect_range_weight * 2.0).abs() < 1e-6);
        assert!((r.tec_hill_weight - p.tec_hill_weight * 2.0).abs() < 1e-6);
        assert!((r.ocean_abyss - p.ocean_abyss * 1.5).abs() < 1e-6);
        // ocean_full (the quantize mapping) is deliberately NOT scaled.
        assert_eq!(r.ocean_full, p.ocean_full);
        // a frequency is not knob-scaled.
        assert_eq!(r.mtn_freq, p.mtn_freq);
    }

    #[test]
    fn relief_params_clamp_no_panic() {
        let junk = ReliefParams { tect_range_weight: 999.0, sea_frac: 9.0, mtn_octaves: 0, ..ReliefParams::default() };
        let r = junk.resolved(&IntensityKnobs { relief: 999.0, ocean_depth: 0.0, ..Default::default() });
        assert_eq!(r.tect_range_weight, 5.0, "range weight clamps to rail");
        assert_eq!(r.sea_frac, 0.95, "sea_frac clamps to rail");
        assert_eq!(r.mtn_octaves, 1, "octaves clamp ≥ 1");
        assert!(r.ocean_full.is_finite() && r.ocean_full >= 0.05);
    }

    #[test]
    fn climate_default_knobs_are_identity() {
        let p = ClimateParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default knobs must be identity");
    }

    #[test]
    fn climate_knobs_scale() {
        let p = ClimateParams::default();
        let r = p.resolved(&IntensityKnobs {
            warmth: 1.5, rainfall: 2.0, seasonality: 0.5, ..Default::default()
        });
        // warmth shifts temps by (1.5-1)*20 = +10 °C.
        assert!((r.t_eq - (p.t_eq + 10.0)).abs() < 1e-4);
        assert!((r.t_pole - (p.t_pole + 10.0)).abs() < 1e-4);
        // rainfall scales precip bands.
        assert!((r.precip_eq - p.precip_eq * 2.0).abs() < 1e-3);
        // seasonality scales amplitude gains.
        assert!((r.amp_cont_gain - p.amp_cont_gain * 0.5).abs() < 1e-4);
        // a Köppen cutoff is not knob-scaled.
        assert_eq!(r.tropical_cold_c, p.tropical_cold_c);
    }

    #[test]
    fn climate_params_clamp_no_panic() {
        let junk = ClimateParams { t_eq: 9999.0, precip_eq: -50.0, ..ClimateParams::default() };
        let r = junk.resolved(&IntensityKnobs { warmth: 99.0, rainfall: 99.0, ..Default::default() });
        assert!(r.t_eq.is_finite() && r.t_eq <= 80.0, "t_eq clamps to rail");
        assert!(r.precip_eq >= 0.0, "precip clamps non-negative");
    }

    #[test]
    fn knobs_and_params_clamp_no_panic() {
        let p = TectonicsParams::default();
        let r = p.resolved(&IntensityKnobs { orogeny: 999.0, collision_frequency: 0.0, ..Default::default() });
        assert_eq!(r.fold_peak, (p.fold_peak * 3.0).clamp(0.0, 5.0), "orogeny clamps to 3");
        assert!(r.fault_shear_ratio.is_finite(), "cf=0 must not divide-by-zero to inf");
        // a garbage granular value clamps too.
        let junk = TectonicsParams { fold_peak: 999.0, decay_hops: -5.0, ..p };
        let rj = junk.resolved(&IntensityKnobs::default());
        assert_eq!(rj.fold_peak, 5.0);
        assert_eq!(rj.decay_hops, 0.5);
    }
}
