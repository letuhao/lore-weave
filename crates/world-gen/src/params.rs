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

use crate::biome::BiomeKind;

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

/// One resolved row of the hydraulic-erosion strength table — the tuning
/// `erosion::apply` uses for a single [`crate::ErosionStrength`]. Internal
/// working unit (not serde); built by [`ErosionParams::row`].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ErosionRow {
    /// Pure-incision passes (phase 1 — carve the valleys).
    pub carve_iters: u32,
    /// Incision + deposition passes (phase 2 — settle sediment into fans).
    pub settle_iters: u32,
    /// `K` — stream-power erodibility per iteration.
    pub erodibility: f32,
    /// `Kc` — sediment transport-capacity coefficient.
    pub transport: f32,
    /// Fraction of the over-capacity load deposited per settle pass.
    pub settle_rate: f32,
    /// `D` — hillslope-diffusion (creep) coefficient, `0..1`.
    pub diffusion: f32,
}

/// Hydraulic-erosion strength table (was the per-`ErosionStrength` match in
/// `erosion.rs`). Defaults are the exact prior Light/Moderate/Heavy values
/// (byte-identical baseline); `None` stays a hardcoded all-zero no-op row, not a
/// param. The stream-power exponents `m`/`n` (the `.sqrt()` and slope term in
/// `incise`) are **structural math, kept fixed internal** — `area.powf(0.5)` is
/// not bit-identical to `area.sqrt()`, so exposing them would break the
/// byte-identical invariant; per the cross-cutting rule "salts/math stay fixed".
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ErosionParams {
    // Light.
    pub light_carve_iters: u32,
    pub light_settle_iters: u32,
    pub light_erodibility: f32,
    pub light_transport: f32,
    pub light_settle_rate: f32,
    pub light_diffusion: f32,
    // Moderate (the CreativeSeed default strength).
    pub moderate_carve_iters: u32,
    pub moderate_settle_iters: u32,
    pub moderate_erodibility: f32,
    pub moderate_transport: f32,
    pub moderate_settle_rate: f32,
    pub moderate_diffusion: f32,
    // Heavy.
    pub heavy_carve_iters: u32,
    pub heavy_settle_iters: u32,
    pub heavy_erodibility: f32,
    pub heavy_transport: f32,
    pub heavy_settle_rate: f32,
    pub heavy_diffusion: f32,
}

impl Default for ErosionParams {
    fn default() -> Self {
        // Exact values that were the `erosion::params(strength)` table.
        ErosionParams {
            light_carve_iters: 14,
            light_settle_iters: 6,
            light_erodibility: 2.0,
            light_transport: 4.0,
            light_settle_rate: 0.15,
            light_diffusion: 0.010,
            moderate_carve_iters: 18,
            moderate_settle_iters: 8,
            moderate_erodibility: 3.0,
            moderate_transport: 4.0,
            moderate_settle_rate: 0.18,
            moderate_diffusion: 0.012,
            heavy_carve_iters: 22,
            heavy_settle_iters: 10,
            heavy_erodibility: 4.0,
            heavy_transport: 4.0,
            heavy_settle_rate: 0.20,
            heavy_diffusion: 0.012,
        }
    }
}

impl ErosionParams {
    /// Clamp every field to a sane rail (no panic). The macro [`IntensityKnobs`]
    /// carry no erosion scaler today (the `ErosionStrength` enum is erosion's
    /// high-level tier-1 knob) — `k` is accepted for call-shape uniformity and
    /// reserved for a future erosion knob. Identity at default ⇒ byte-identical.
    pub fn resolved(&self, _k: &IntensityKnobs) -> ErosionParams {
        let iters = |v: u32| v.min(10_000);
        let rate = |v: f32| v.clamp(0.0, 1.0);
        let coef = |v: f32| v.clamp(0.0, 1000.0);
        ErosionParams {
            light_carve_iters: iters(self.light_carve_iters),
            light_settle_iters: iters(self.light_settle_iters),
            light_erodibility: coef(self.light_erodibility),
            light_transport: coef(self.light_transport),
            light_settle_rate: rate(self.light_settle_rate),
            light_diffusion: rate(self.light_diffusion),
            moderate_carve_iters: iters(self.moderate_carve_iters),
            moderate_settle_iters: iters(self.moderate_settle_iters),
            moderate_erodibility: coef(self.moderate_erodibility),
            moderate_transport: coef(self.moderate_transport),
            moderate_settle_rate: rate(self.moderate_settle_rate),
            moderate_diffusion: rate(self.moderate_diffusion),
            heavy_carve_iters: iters(self.heavy_carve_iters),
            heavy_settle_iters: iters(self.heavy_settle_iters),
            heavy_erodibility: coef(self.heavy_erodibility),
            heavy_transport: coef(self.heavy_transport),
            heavy_settle_rate: rate(self.heavy_settle_rate),
            heavy_diffusion: rate(self.heavy_diffusion),
        }
    }
}

/// Hydrology thresholds (was the `hydrology.rs` consts). Defaults are the exact
/// prior values (byte-identical baseline).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct HydrologyParams {
    /// Land-flux percentile above which a cell is a `River` biome (was `0.96`).
    pub river_percentile: f32,
    /// A water component is ocean (vs. lake) iff its size exceeds
    /// `(n / lake_max_divisor).max(lake_max_floor)` (was `150`).
    pub lake_max_divisor: u32,
    /// Floor for the ocean/lake size threshold (was `24`).
    pub lake_max_floor: u32,
}

impl Default for HydrologyParams {
    fn default() -> Self {
        HydrologyParams { river_percentile: 0.96, lake_max_divisor: 150, lake_max_floor: 24 }
    }
}

impl HydrologyParams {
    /// Clamp to sane rails (no panic; divisor/floor ≥ 1 so the integer divide
    /// and `.max` never degenerate). `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> HydrologyParams {
        HydrologyParams {
            river_percentile: self.river_percentile.clamp(0.0, 1.0),
            lake_max_divisor: self.lake_max_divisor.max(1),
            lake_max_floor: self.lake_max_floor.max(1),
        }
    }
}

/// Settlement-placement tuning (was the `settlement.rs` consts: burg-score
/// water bonuses + threshold, the target floor, the role-rank percentiles, and
/// the per-climate habitability table). Defaults are the exact prior values
/// (byte-identical). The `SettlementDensity` enum (cells-per-settlement,
/// min-separation) stays settlement's high-level tier-1 knob.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SettlementParams {
    /// Burg-score multiplier for a coastal cell (was `1.3`).
    pub coast_bonus: f32,
    /// Burg-score multiplier for a (non-coast) river cell (was `1.15`).
    pub river_bonus: f32,
    /// A cell is a placement candidate only if its burg score exceeds this
    /// (was `0.05`).
    pub burg_threshold: f32,
    /// Minimum settlement target, so a tiny map isn't settlement-starved
    /// (was `3`).
    pub target_floor: u32,
    // Role-by-burg-rank percentiles (ascending fraction cutoffs). CLAMP-NOT-
    // VALIDATE: `resolved()` rails each to [0,1] but does NOT enforce the
    // `city_frac ≤ town_frac ≤ village_frac` ordering — a non-ascending profile
    // makes the higher roles unreachable (the if/else cascade short-circuits),
    // which is odd-but-deterministic, never a panic. GIGO for a tuning surface.
    pub city_frac: f32,
    pub town_frac: f32,
    pub village_frac: f32,
    // Per-climate habitability multipliers (was the `climate_friendly` match).
    pub habit_temperate: f32,
    pub habit_mediterranean: f32,
    pub habit_subtropical: f32,
    pub habit_tropical: f32,
    pub habit_boreal: f32,
    pub habit_arid: f32,
    pub habit_highland: f32,
    pub habit_polar: f32,
}

impl Default for SettlementParams {
    fn default() -> Self {
        // Exact values that were hardcoded in `settlement.rs`.
        SettlementParams {
            coast_bonus: 1.3,
            river_bonus: 1.15,
            burg_threshold: 0.05,
            target_floor: 3,
            city_frac: 0.12,
            town_frac: 0.34,
            village_frac: 0.67,
            habit_temperate: 1.0,
            habit_mediterranean: 1.0,
            habit_subtropical: 0.9,
            habit_tropical: 0.7,
            habit_boreal: 0.6,
            habit_arid: 0.5,
            habit_highland: 0.5,
            habit_polar: 0.3,
        }
    }
}

impl SettlementParams {
    /// Clamp every field to a sane rail (no panic). `k` reserved for call-shape
    /// uniformity. Identity at default ⇒ byte-identical.
    pub fn resolved(&self, _k: &IntensityKnobs) -> SettlementParams {
        let mult = |v: f32| v.clamp(0.0, 100.0);
        let frac = |v: f32| v.clamp(0.0, 1.0);
        SettlementParams {
            coast_bonus: mult(self.coast_bonus),
            river_bonus: mult(self.river_bonus),
            burg_threshold: self.burg_threshold.max(0.0),
            target_floor: self.target_floor.max(1),
            city_frac: frac(self.city_frac),
            town_frac: frac(self.town_frac),
            village_frac: frac(self.village_frac),
            habit_temperate: mult(self.habit_temperate),
            habit_mediterranean: mult(self.habit_mediterranean),
            habit_subtropical: mult(self.habit_subtropical),
            habit_tropical: mult(self.habit_tropical),
            habit_boreal: mult(self.habit_boreal),
            habit_arid: mult(self.habit_arid),
            habit_highland: mult(self.habit_highland),
            habit_polar: mult(self.habit_polar),
        }
    }
}

/// Route-network tuning (was the `routes.rs` consts: the MountainPass count, the
/// road/trail population-tier gates, the navigable-river min run). Defaults are
/// the exact prior values (byte-identical).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RouteParams {
    /// Top-N Mountain/Hill chokepoint edges promoted to MountainPass (was `5`).
    pub mountain_pass_target: u32,
    /// Settlements with `population_tier ≥` this are Road-eligible (was `2`).
    /// Filter-only ⇒ safe at any value (left unclamped). With the defaults the
    /// road (`≥2`) and trail (`≤1`) sets partition the settlements; if a profile
    /// sets `road_tier_min ≤ trail_tier_max` the sets *overlap* — a settlement
    /// is then both a road node and a trail origin. `RouteSink` dedups by
    /// `(kind, lo, hi)`, so the result is deterministic, just denser. GIGO.
    pub road_tier_min: u32,
    /// Settlements with `population_tier ≤` this get a Trail (was `1`).
    pub trail_tier_max: u32,
    /// Minimum consecutive navigable-river cells for a RiverNavigation route
    /// (was `3`).
    pub river_nav_min_run: u32,
}

impl Default for RouteParams {
    fn default() -> Self {
        RouteParams { mountain_pass_target: 5, road_tier_min: 2, trail_tier_max: 1, river_nav_min_run: 3 }
    }
}

impl RouteParams {
    /// Clamp to sane rails (no panic; `river_nav_min_run ≥ 2` so a run is a real
    /// edge). `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> RouteParams {
        RouteParams {
            mountain_pass_target: self.mountain_pass_target.min(100_000),
            road_tier_min: self.road_tier_min,
            trail_tier_max: self.trail_tier_max,
            river_nav_min_run: self.river_nav_min_run.max(2),
        }
    }
}

/// Political-tier quota tuning for the live 5-tier `political::build_nested`
/// (was the inline divisors + quota clamps). Each tier's seed count is
/// `(parent_size / *_per_seed).clamp(1, *_max)`. Defaults are the exact prior
/// values (byte-identical). The legacy `political::build` (civ adapter) keeps
/// its own consts. `county` subdivision count is a `CreativeSeed` tier-1 input;
/// only its upper clamp (`county_max`) is a param.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct PoliticalParams {
    /// Cells per province seed, within a region (was `150`).
    pub prov_cells_per_seed: u32,
    /// Max provinces per region (was `8`).
    pub prov_max: u32,
    /// Provinces per state seed, within a subcontinent (was `4`).
    pub state_provs_per_seed: u32,
    /// Max states per subcontinent (was `6`).
    pub state_max: u32,
    /// States per realm seed, within a continent (was `3`).
    pub realm_states_per_seed: u32,
    /// Max realms per continent (was `4`).
    pub realm_max: u32,
    /// Upper clamp on the `county_subdivision` input (counties per province,
    /// was `8`). The min stays the structural `1`.
    pub county_max: u32,
}

impl Default for PoliticalParams {
    fn default() -> Self {
        PoliticalParams {
            prov_cells_per_seed: 150,
            prov_max: 8,
            state_provs_per_seed: 4,
            state_max: 6,
            realm_states_per_seed: 3,
            realm_max: 4,
            county_max: 8,
        }
    }
}

impl PoliticalParams {
    /// Clamp to sane rails (no panic; divisors ≥ 1 so the integer divide never
    /// degenerates; maxes ≥ 1 so a tier always has ≥ 1 seed).
    pub fn resolved(&self, _k: &IntensityKnobs) -> PoliticalParams {
        PoliticalParams {
            prov_cells_per_seed: self.prov_cells_per_seed.max(1),
            prov_max: self.prov_max.max(1),
            state_provs_per_seed: self.state_provs_per_seed.max(1),
            state_max: self.state_max.max(1),
            realm_states_per_seed: self.realm_states_per_seed.max(1),
            realm_max: self.realm_max.max(1),
            county_max: self.county_max.clamp(1, 255),
        }
    }
}

/// Culture-layer tuning (was the `culture.rs` consts). Defaults are the exact
/// prior values (byte-identical). `culture_count` is a `CreativeSeed` tier-1
/// input; only its upper clamp (`count_max`) is a param.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CultureParams {
    /// Hearth great-circle spacing coefficient: `min_sep = coeff / √k · π`
    /// (was `0.85`). Higher = cultures spread farther apart.
    pub hearth_spacing_coeff: f32,
    /// Upper clamp on the `culture_count` input (was `16`). Min stays `1`.
    pub count_max: u32,
}

impl Default for CultureParams {
    fn default() -> Self {
        CultureParams { hearth_spacing_coeff: 0.85, count_max: 16 }
    }
}

impl CultureParams {
    /// Clamp to sane rails (no panic). `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> CultureParams {
        CultureParams {
            hearth_spacing_coeff: self.hearth_spacing_coeff.clamp(0.0, 10.0),
            count_max: self.count_max.clamp(1, 255),
        }
    }
}

/// Geometric-hierarchy tuning (was the `hierarchy.rs` consts). Defaults are the
/// exact prior values (byte-identical). Continents (= land components) and
/// subcontinents (= plates) are structural, not param-driven; only the L2-region
/// subdivision ceiling is exposed (`region_subdivision` is a `CreativeSeed`
/// tier-1 input, clamped to `[1, region_subdivision_max]`).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct HierarchyParams {
    /// Upper clamp on the `region_subdivision` input (L2 regions per
    /// subcontinent, was `12`). Min stays `1`.
    pub region_subdivision_max: u32,
}

impl Default for HierarchyParams {
    fn default() -> Self {
        HierarchyParams { region_subdivision_max: 12 }
    }
}

impl HierarchyParams {
    /// Clamp to a sane rail (no panic). `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> HierarchyParams {
        HierarchyParams { region_subdivision_max: self.region_subdivision_max.clamp(1, 255) }
    }
}

/// Biome-derivation tuning (was the `derive_biome` elevation-tier literals + the
/// `BiomeKind::{terrain_cost, culture_barrier, population_potential}` method
/// tables). The three tables are **fixed-size `[_; 14]` arrays** indexed by
/// [`BiomeKind::tag`] — fixed-size, not `Vec`, so `CreativeSeed` stays `Copy`
/// (the P1 `/review-impl` finding). Defaults are the exact prior values
/// (byte-identical); the `BiomeKind` methods remain as the canonical default
/// (still used by the legacy `political::build` + civ adapter + tests), guarded
/// against drift by a unit test.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BiomeParams {
    /// Land-tier below which a coast cell is Beach, not Coast (was `0.06`).
    pub beach_t: f32,
    /// Land-tier at/above which a cell is "mid" → Hill (was `0.22`).
    pub mid_t: f32,
    /// Land-tier at/above which a cell is "high" → Mountain/Glacier (was `0.55`).
    pub high_t: f32,
    /// A low cell is "wet" (→ Marsh, warm-humid) if `river_flux` exceeds this
    /// fraction of the river threshold (was `0.5`).
    pub wet_low_flux_frac: f32,
    /// Movement cost per biome (`None` = impassable); indexed by `BiomeKind::tag`.
    pub terrain_cost: [Option<u32>; 14],
    /// Culture-spread cost per biome (`None` = hard barrier); by `tag`.
    pub culture_barrier: [Option<u32>; 14],
    /// Base habitability per biome (burg score); by `tag`.
    pub population_potential: [f32; 14],
}

impl Default for BiomeParams {
    fn default() -> Self {
        // Tables in `BiomeKind::tag` order (0=Ocean … 13=Glacier); these mirror
        // the `BiomeKind` methods exactly (drift-guarded by a unit test).
        BiomeParams {
            beach_t: 0.06,
            mid_t: 0.22,
            high_t: 0.55,
            wet_low_flux_frac: 0.5,
            terrain_cost: [
                None, None, Some(2), Some(1), Some(1), Some(1), Some(2), Some(4), Some(4),
                Some(8), Some(3), Some(3), Some(3), Some(20),
            ],
            culture_barrier: [
                None, None, Some(1), Some(1), Some(1), Some(1), Some(1), Some(2), Some(2),
                Some(3), Some(2), Some(3), Some(2), Some(8),
            ],
            population_potential: [
                0.0, 0.0, 0.9, 0.9, 0.5, 1.0, 0.7, 0.4, 0.3, 0.15, 0.6, 0.2, 0.2, 0.0,
            ],
        }
    }
}

impl BiomeParams {
    /// Movement cost to enter a cell of biome `b` (`None` = impassable).
    pub fn terrain_cost(&self, b: BiomeKind) -> Option<u32> {
        self.terrain_cost[b.tag() as usize]
    }
    /// Culture-spread cost across biome `b` (`None` = hard barrier).
    pub fn culture_barrier(&self, b: BiomeKind) -> Option<u32> {
        self.culture_barrier[b.tag() as usize]
    }
    /// Base habitability of biome `b` for the burg score.
    pub fn population_potential(&self, b: BiomeKind) -> f32 {
        self.population_potential[b.tag() as usize]
    }

    /// Clamp the elevation tiers to `[0,1]`, habitability ≥ 0, and every
    /// movement / culture cost to `≤ COST_CEILING` (no panic). The cost ceiling
    /// matters: these costs feed the Dijkstra accumulator `c + step`, so a
    /// pathological `Some(u32::MAX)` (a human typo / LLM hallucination — exactly
    /// what the arc promises to bound) would overflow `u32`. `COST_CEILING`
    /// (10 000 — 500× the highest default of 20) keeps `n_cells × ceiling` far
    /// under `u32::MAX`. `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> BiomeParams {
        const COST_CEILING: u32 = 10_000;
        let cap = |c: Option<u32>| c.map(|v| v.min(COST_CEILING));
        let mut r = *self;
        r.beach_t = self.beach_t.clamp(0.0, 1.0);
        r.mid_t = self.mid_t.clamp(0.0, 1.0);
        r.high_t = self.high_t.clamp(0.0, 1.0);
        r.wet_low_flux_frac = self.wet_low_flux_frac.max(0.0);
        for p in &mut r.population_potential {
            *p = p.max(0.0);
        }
        for c in &mut r.terrain_cost {
            *c = cap(*c);
        }
        for c in &mut r.culture_barrier {
            *c = cap(*c);
        }
        r
    }
}

/// Render-time colour theme (was the `render.rs` palettes + `SS`/`BACKGROUND`).
/// Colours are stored as raw `[u8;3]` (serde/`Copy`-friendly; `render.rs` wraps
/// them in `image::Rgb` at use). Defaults are the exact prior literals
/// (byte-identical render output, pinned by `render::tests`). The render *math*
/// — hillshade/warp/detail and the per-style `StyleParams` in `relief.rs` —
/// stays fixed internal (the salts/math rule); only colours + supersample are
/// params. (P8b.)
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RenderTheme {
    /// Internal supersample factor (every raster renders at `SS×` then
    /// box-downsamples). Higher = smoother edges, ~`SS²` cost.
    pub supersample: u32,
    /// Out-of-globe background (Orthographic disc exterior).
    pub background: [u8; 3],
    /// Flat water fill for the categorical maps (culture/plate/region/realm/
    /// political). The hypsometric relief uses `water_*` ramps instead.
    pub water_flat: [u8; 3],
    /// Biome fill colours, indexed by [`BiomeKind::tag`].
    pub biome: [[u8; 3]; 14],
    /// Culture-region palette (cycled by id).
    pub culture: [[u8; 3]; 16],
    /// State (nation) palette (cycled by id) for the political map.
    pub state: [[u8; 3]; 12],
    /// Plate-boundary outline colours, indexed by `BoundaryKind` (FoldMountain,
    /// Subduction, IslandArc, Ridge, Rift, Fault, Interior).
    pub boundary: [[u8; 3]; 7],
    /// Continental-plate base tint (a per-id jitter is added at render).
    pub plate_continental: [u8; 3],
    /// Oceanic-plate base tint.
    pub plate_oceanic: [u8; 3],
    /// Route colours, indexed by `RouteKind` (Road, Trail, RiverNavigation,
    /// SeaLane, MountainPass).
    pub route: [[u8; 3]; 5],
    /// Settlement dot colours, indexed by `SettlementRole` (Capital, City, Town,
    /// Village, Hamlet, Fortress).
    pub settlement: [[u8; 3]; 6],
    /// Outer-tier choropleth border (continent / realm).
    pub tier1_border: [u8; 3],
    /// Inner-tier choropleth border (subcontinent / state).
    pub tier2_border: [u8; 3],
    /// Atlas-style coastline ink.
    pub coast_ink: [u8; 3],
    /// Choropleth region/province tint saturation + value (golden-ratio hue).
    pub choropleth_sat: f32,
    pub choropleth_val: f32,
    /// Hypsometric land ramps `(normalized-height-above-sea, rgb)`, ascending.
    pub land_realistic: [(f32, [u8; 3]); 8],
    pub land_atlas: [(f32, [u8; 3]); 5],
    /// Hypsometric water ramps `(normalized-depth-below-sea, rgb)`, ascending.
    pub water_realistic: [(f32, [u8; 3]); 4],
    pub water_atlas: [(f32, [u8; 3]); 2],
}

impl Default for RenderTheme {
    fn default() -> Self {
        // Exact literals that were hardcoded in `render.rs`.
        RenderTheme {
            supersample: 2,
            background: [12, 14, 18],
            water_flat: [40, 70, 120],
            biome: [
                [30, 60, 130],   // Ocean
                [60, 110, 190],  // Lake
                [90, 150, 210],  // River
                [200, 190, 130], // Coast
                [235, 220, 160], // Beach
                [130, 190, 90],  // Plain
                [50, 120, 55],   // Forest
                [25, 95, 40],    // Jungle
                [95, 120, 70],   // Marsh
                [140, 135, 130], // Mountain
                [120, 140, 80],  // Hill
                [220, 200, 130], // Desert
                [170, 160, 150], // Tundra
                [240, 245, 250], // Glacier
            ],
            culture: [
                [210, 100, 100], [100, 160, 210], [160, 200, 100], [210, 180, 90],
                [150, 120, 200], [100, 200, 170], [220, 140, 170], [140, 170, 110],
                [190, 150, 210], [120, 190, 130], [210, 200, 120], [170, 130, 120],
                [120, 140, 200], [200, 170, 140], [150, 200, 200], [180, 110, 150],
            ],
            state: [
                [200, 120, 120], [120, 170, 200], [170, 200, 120], [200, 180, 110],
                [160, 130, 190], [120, 200, 170], [210, 150, 170], [150, 160, 120],
                [190, 160, 200], [130, 190, 140], [200, 200, 140], [170, 140, 130],
            ],
            boundary: [
                [220, 60, 50],   // FoldMountain
                [240, 140, 30],  // Subduction
                [240, 210, 60],  // IslandArc
                [90, 220, 200],  // Ridge
                [200, 90, 220],  // Rift
                [180, 180, 180], // Fault
                [0, 0, 0],       // Interior
            ],
            plate_continental: [150, 120, 70],
            plate_oceanic: [40, 70, 130],
            route: [
                [40, 30, 20],    // Road
                [120, 90, 50],   // Trail
                [90, 160, 220],  // RiverNavigation
                [225, 225, 255], // SeaLane
                [220, 80, 60],   // MountainPass
            ],
            settlement: [
                [255, 40, 40],   // Capital
                [255, 205, 40],  // City
                [255, 255, 255], // Town
                [205, 205, 205], // Village
                [150, 150, 150], // Hamlet
                [130, 50, 130],  // Fortress
            ],
            tier1_border: [15, 15, 20],
            tier2_border: [70, 70, 78],
            coast_ink: [66, 56, 48],
            choropleth_sat: 0.55,
            choropleth_val: 0.85,
            land_realistic: [
                (0.00, [78, 126, 68]),
                (0.10, [100, 146, 78]),
                (0.24, [132, 154, 90]),
                (0.42, [160, 150, 100]),
                (0.60, [150, 120, 84]),
                (0.76, [126, 112, 104]),
                (0.90, [172, 168, 162]),
                (1.00, [255, 255, 255]),
            ],
            land_atlas: [
                (0.00, [208, 202, 170]),
                (0.30, [196, 184, 146]),
                (0.60, [178, 160, 132]),
                (0.85, [162, 152, 138]),
                (1.00, [200, 199, 197]),
            ],
            water_realistic: [
                (0.00, [128, 182, 200]),
                (0.12, [86, 144, 184]),
                (0.45, [44, 94, 148]),
                (1.00, [16, 38, 84]),
            ],
            water_atlas: [(0.00, [182, 196, 202]), (1.00, [138, 160, 180])],
        }
    }
}

impl RenderTheme {
    /// Clamp to sane rails (no panic): supersample ≥ 1, sat/val ∈ [0,1]. Colours
    /// (`u8`) and ramp stops pass through. `k` reserved for call-shape uniformity.
    pub fn resolved(&self, _k: &IntensityKnobs) -> RenderTheme {
        let mut r = *self;
        r.supersample = self.supersample.clamp(1, 8);
        r.choropleth_sat = self.choropleth_sat.clamp(0.0, 1.0);
        r.choropleth_val = self.choropleth_val.clamp(0.0, 1.0);
        r
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
    fn erosion_default_knobs_are_identity() {
        let p = ErosionParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default erosion must be identity");
    }

    #[test]
    fn erosion_params_clamp_no_panic() {
        let junk = ErosionParams {
            moderate_carve_iters: 99_999,
            moderate_settle_rate: 9.0,
            moderate_erodibility: -5.0,
            ..ErosionParams::default()
        };
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.moderate_carve_iters, 10_000, "iters clamp to rail");
        assert_eq!(r.moderate_settle_rate, 1.0, "settle_rate clamps to [0,1]");
        assert_eq!(r.moderate_erodibility, 0.0, "erodibility clamps non-negative");
    }

    #[test]
    fn hydrology_default_knobs_are_identity() {
        let p = HydrologyParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default hydrology must be identity");
    }

    #[test]
    fn hydrology_params_clamp_no_panic() {
        let junk = HydrologyParams { river_percentile: 5.0, lake_max_divisor: 0, lake_max_floor: 0 };
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.river_percentile, 1.0, "percentile clamps to [0,1]");
        assert_eq!(r.lake_max_divisor, 1, "divisor clamps ≥ 1 (no divide-by-zero)");
        assert_eq!(r.lake_max_floor, 1, "floor clamps ≥ 1");
    }

    #[test]
    fn settlement_default_knobs_are_identity() {
        let p = SettlementParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default settlement must be identity");
    }

    #[test]
    fn settlement_params_clamp_no_panic() {
        let junk = SettlementParams {
            city_frac: 9.0,
            burg_threshold: -1.0,
            target_floor: 0,
            habit_polar: -3.0,
            ..SettlementParams::default()
        };
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.city_frac, 1.0, "frac clamps to [0,1]");
        assert_eq!(r.burg_threshold, 0.0, "threshold clamps non-negative");
        assert_eq!(r.target_floor, 1, "target_floor clamps ≥ 1");
        assert_eq!(r.habit_polar, 0.0, "habitability clamps non-negative");
    }

    #[test]
    fn route_default_knobs_are_identity() {
        let p = RouteParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default route must be identity");
    }

    #[test]
    fn route_params_clamp_no_panic() {
        let junk = RouteParams { river_nav_min_run: 0, ..RouteParams::default() };
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.river_nav_min_run, 2, "min run clamps ≥ 2 (a run is a real edge)");
    }

    #[test]
    fn political_culture_hierarchy_defaults_are_identity() {
        let pp = PoliticalParams::default();
        assert_eq!(pp, pp.resolved(&IntensityKnobs::default()));
        let cp = CultureParams::default();
        assert_eq!(cp, cp.resolved(&IntensityKnobs::default()));
        let hp = HierarchyParams::default();
        assert_eq!(hp, hp.resolved(&IntensityKnobs::default()));
    }

    #[test]
    fn political_culture_hierarchy_clamp_no_panic() {
        let pp = PoliticalParams {
            prov_cells_per_seed: 0, prov_max: 0, county_max: 9999, ..PoliticalParams::default()
        }
        .resolved(&IntensityKnobs::default());
        assert_eq!(pp.prov_cells_per_seed, 1, "divisor clamps ≥ 1 (no div-by-zero)");
        assert_eq!(pp.prov_max, 1, "max clamps ≥ 1");
        assert_eq!(pp.county_max, 255, "county_max clamps ≤ 255 (fits u8)");
        let cp = CultureParams { hearth_spacing_coeff: -1.0, count_max: 0 }
            .resolved(&IntensityKnobs::default());
        assert_eq!(cp.hearth_spacing_coeff, 0.0, "spacing clamps non-negative");
        assert_eq!(cp.count_max, 1, "count_max clamps ≥ 1");
        let hp = HierarchyParams { region_subdivision_max: 0 }.resolved(&IntensityKnobs::default());
        assert_eq!(hp.region_subdivision_max, 1, "region max clamps ≥ 1");
    }

    #[test]
    fn biome_default_knobs_are_identity() {
        let p = BiomeParams::default();
        assert_eq!(p, p.resolved(&IntensityKnobs::default()), "default biome must be identity");
    }

    #[test]
    fn biome_default_tables_match_the_methods() {
        // Drift guard: the BiomeParams default tables must mirror the canonical
        // `BiomeKind` methods (still used by the legacy political::build + civ
        // adapter). If a method changes, this trips until the table is updated.
        let bp = BiomeParams::default();
        for b in [
            BiomeKind::Ocean, BiomeKind::Lake, BiomeKind::River, BiomeKind::Coast,
            BiomeKind::Beach, BiomeKind::Plain, BiomeKind::Forest, BiomeKind::Jungle,
            BiomeKind::Marsh, BiomeKind::Mountain, BiomeKind::Hill, BiomeKind::Desert,
            BiomeKind::Tundra, BiomeKind::Glacier,
        ] {
            assert_eq!(bp.terrain_cost(b), b.terrain_cost(), "terrain_cost drift: {b:?}");
            assert_eq!(bp.culture_barrier(b), b.culture_barrier(), "culture_barrier drift: {b:?}");
            assert_eq!(
                bp.population_potential(b), b.population_potential(),
                "population_potential drift: {b:?}"
            );
        }
    }

    #[test]
    fn biome_params_clamp_no_panic() {
        let mut junk = BiomeParams { high_t: 9.0, wet_low_flux_frac: -2.0, ..BiomeParams::default() };
        junk.population_potential[5] = -3.0;
        junk.terrain_cost[9] = Some(u32::MAX);
        junk.culture_barrier[9] = Some(u32::MAX);
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.high_t, 1.0, "tier clamps to [0,1]");
        assert_eq!(r.wet_low_flux_frac, 0.0, "wet fraction clamps non-negative");
        assert_eq!(r.population_potential[5], 0.0, "habitability clamps non-negative");
        assert_eq!(r.terrain_cost[9], Some(10_000), "terrain cost clamps to ceiling (no Dijkstra overflow)");
        assert_eq!(r.culture_barrier[9], Some(10_000), "culture barrier clamps to ceiling");
    }

    #[test]
    fn render_theme_default_is_identity_and_clamps() {
        let t = RenderTheme::default();
        assert_eq!(t, t.resolved(&IntensityKnobs::default()), "default theme must be identity");
        let junk = RenderTheme { supersample: 0, choropleth_sat: 9.0, choropleth_val: -1.0, ..t };
        let r = junk.resolved(&IntensityKnobs::default());
        assert_eq!(r.supersample, 1, "supersample clamps ≥ 1");
        assert_eq!(r.choropleth_sat, 1.0, "sat clamps to [0,1]");
        assert_eq!(r.choropleth_val, 0.0, "val clamps to [0,1]");
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
