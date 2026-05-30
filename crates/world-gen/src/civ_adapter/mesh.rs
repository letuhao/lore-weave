//! Mesh & substrate primitives for the civilization adapter.
//!
//! Owns the `CivView` struct, the FlatWorld → mesh-interface conversion
//! ([`build_civ_view`]), the synthetic-ocean augmenter
//! ([`augment_with_ocean`]), the flat → unit-sphere projection
//! ([`project_to_sphere`] / [`build_civ_view_spherical`]), the
//! elevation quantiser ([`elevation_to_u16`]), and the lossy Köppen → System-A
//! biome / climate translations ([`koppen_to_biome_kind`] /
//! [`derive_climate_zone`]).
//!
//! All convenience pipelines downstream (`pipeline.rs`,
//! `bundle.rs`, `render.rs`, `naming.rs`) consume the types and
//! functions exported from this file.

use delaunator::{triangulate, Point};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::flat_climate::{compute_zone_climate, Biome, WorldClimateParams, ZoneClimate};
use crate::flatworld::{FlatWorld, BASE_LEVEL};
use crate::rng::Rng;

/// A mesh-shaped view of a `FlatWorld` ready to feed into the System-A
/// civilization stack. Lengths of every per-cell vector equal
/// `centers.len()`.
#[derive(Debug, Clone)]
pub struct CivView {
    /// Sub-zone centres in 3D. `build_civ_view` returns flat
    /// `[x, y, 0]`; the pipeline layer projects to unit sphere via
    /// [`project_to_sphere`] before downstream civilization builders
    /// run (their distance metric `1 - dot` requires unit vectors —
    /// see /review-impl HIGH-1 in session 92).
    pub centers: Vec<[f32; 3]>,
    /// Adjacency lists from a Delaunay triangulation over `centers`. Each
    /// `neighbors[i]` is the deduped sorted set of cell indices sharing a
    /// triangle edge with cell `i`.
    pub neighbors: Vec<Vec<u32>>,
    /// Coarse System-A biome — translated from the Köppen
    /// `flat_climate::Biome` via [`koppen_to_biome_kind`].
    pub biomes: Vec<BiomeKind>,
    /// Coarse System-A climate zone — translated from `flat_climate`
    /// per-cell mean temperature + annual precipitation via
    /// [`derive_climate_zone`].
    pub climate: Vec<ClimateZone>,
    /// Per-cell river flux. v1 leaves this at `0.0`; civ-layer Ship 4
    /// overrides via `build_hydrology_view` when settlement::build needs
    /// it.
    pub river_flux: Vec<f32>,
    /// Whether a cell sits next to the ocean (any neighbor cell is
    /// `BiomeKind::Ocean`). Used by `settlement::build` to bias toward
    /// coastal cities.
    pub is_coast: Vec<bool>,
    /// Per-cell elevation read from [`FlatWorld::elevation_at`] at the
    /// sub-zone centre. Units: same as `FlatWorld` elevation (relative;
    /// `0.0` = void floor, ~1.0 = collision peaks).
    pub elevation: Vec<f32>,
    /// Sea level. v1 uses a fixed `0.5` — the FlatWorld's `BASE_LEVEL`
    /// per-plate floor; cells above are "land", at or below are "sea".
    pub sea_level: f32,
}

impl CivView {
    /// Number of cells.
    pub fn len(&self) -> usize {
        self.centers.len()
    }

    /// True when the cell list is empty (degenerate world).
    pub fn is_empty(&self) -> bool {
        self.centers.is_empty()
    }
}

/// Build the civilization-view from a `FlatWorld` + the climate params
/// the caller used (or will use) for biome rendering. The climate sweep
/// runs **once per sub-zone**, not per pixel — significantly cheaper
/// than `flat_climate::export_zone_climates`'s default coverage.
///
/// **Pre-condition**: `world.plates[*].zones[*].subzones` must be
/// populated (true since v4.2a SCHEMA ship).
///
/// **Note**: this returns *flat* `[x, y, 0]` centres for compatibility
/// with Ship 1's Delaunay tests. Most callers should use
/// [`build_civ_view_spherical`] (or any of the `pipeline::*` convenience
/// functions, which project internally) so the downstream civ
/// builders' sphere-distance metric works correctly. See HIGH-1 in
/// session 92 /review-impl.
pub fn build_civ_view(world: &FlatWorld, climate_params: &WorldClimateParams) -> CivView {
    // Edge-distance grid drives the continentality term in
    // `compute_zone_climate`. Build it the same way
    // `flat_climate::export_zone_climates` does: classify every pixel as
    // sea (no plate covers it) vs. land, then BFS distances out of the
    // sea set via `zonegen::edge_dist_from_sea`.
    let w = world.width as usize;
    let h = world.height as usize;
    let mut is_sea = vec![false; w * h];
    for py in 0..h {
        for px in 0..w {
            if world
                .plates_at(px as f32 + 0.5, py as f32 + 0.5)
                .is_empty()
            {
                is_sea[py * w + px] = true;
            }
        }
    }
    let edge_dist_sea = crate::zonegen::edge_dist_from_sea(&is_sea, w, h);

    let mut centers_2d: Vec<(f32, f32)> = Vec::new();
    let mut zone_climates: Vec<ZoneClimate> = Vec::new();
    let mut elevation: Vec<f32> = Vec::new();
    for plate in &world.plates {
        for (zi, zone) in plate.zones.iter().enumerate() {
            let zone_clim = compute_zone_climate(
                world,
                climate_params,
                plate.id,
                zi,
                &edge_dist_sea,
            );
            for sub in &zone.subzones {
                centers_2d.push(sub.center);
                zone_climates.push(zone_clim);
                elevation.push(world.elevation_at(sub.center.0, sub.center.1));
            }
        }
    }

    let centers: Vec<[f32; 3]> = centers_2d
        .iter()
        .map(|&(x, y)| [x, y, 0.0])
        .collect();

    let neighbors = build_delaunay_neighbors(&centers_2d);

    // Biome derivation: physical features (Ocean / Mountain / Hill) win
    // over climate-driven Köppen biomes. Thresholds calibrated against
    // flatworld constants: BASE_LEVEL = 0.35, collision uplift adds
    // 0.05-0.25 per overlapping pair.
    let biomes: Vec<BiomeKind> = centers_2d
        .iter()
        .zip(zone_climates.iter())
        .zip(elevation.iter())
        .map(|((&(x, y), c), &elev)| {
            if world.plates_at(x, y).is_empty() {
                BiomeKind::Ocean
            } else if elev > 0.55 {
                BiomeKind::Mountain
            } else if elev > 0.45 {
                BiomeKind::Hill
            } else {
                koppen_to_biome_kind(c.biome)
            }
        })
        .collect();
    let climate: Vec<ClimateZone> = zone_climates
        .iter()
        .map(|c| derive_climate_zone(c.temp_mean, c.precip_annual))
        .collect();

    let is_coast = compute_is_coast(&biomes, &neighbors);

    CivView {
        centers,
        neighbors,
        biomes,
        climate,
        river_flux: vec![0.0; centers_2d.len()],
        is_coast,
        elevation,
        sea_level: 0.5,
    }
}

/// **Civ Ship 2** — augment a `CivView` with synthetic ocean cells.
///
/// Sub-zones are by construction inside plates, so a raw
/// [`build_civ_view`] never produces `BiomeKind::Ocean` cells. Without
/// ocean cells, [`crate::feature::extract`] can't find water bodies,
/// `is_coast` stays false everywhere, and `settlement::build` has no
/// incentive to place coastal cities.
///
/// Samples points in the world's void region (any spot where
/// `world.plates_at` returns empty), assigns `BiomeKind::Ocean`,
/// rebuilds the Delaunay adjacency over the combined point set, and
/// recomputes `is_coast` so coastal land sub-zones flip to `true`.
///
/// Deterministic: seeded from world dimensions + target_count.
pub fn augment_with_ocean(view: CivView, world: &FlatWorld, target_count: usize) -> CivView {
    let w = world.width as f32;
    let h = world.height as f32;
    let target = target_count.max(1);

    let cell_area = (w * h) / (target as f32);
    let min_sep = cell_area.sqrt() * 0.7;
    let min_sep2 = min_sep * min_sep;

    // **LOW-1 fix (review 2026-05-30)**: previous seed `(w<<32) | h | target`
    // collided whenever `target` bits subsumed into `height` bits (e.g.
    // height=256 target=256 → same seed as height=256 target=0). Switch
    // to a multiplicative mix with the FNV-1a 64-bit prime so distinct
    // (w, h, target) triples produce distinct seeds with high probability.
    const FNV_PRIME_64: u64 = 0x100_0000_01B3;
    let seed_u64 = (world.width as u64)
        .wrapping_mul(FNV_PRIME_64)
        .wrapping_add(world.height as u64)
        .wrapping_mul(FNV_PRIME_64)
        .wrapping_add(target as u64);
    let mut rng = Rng::for_stage(seed_u64, b"civ-ocean");
    let max_attempts = target.saturating_mul(80).max(2_000);
    let mut ocean_centers: Vec<(f32, f32)> = Vec::with_capacity(target);
    let mut attempts = 0_usize;
    while ocean_centers.len() < target && attempts < max_attempts {
        attempts += 1;
        let x = rng.next_f32() * w;
        let y = rng.next_f32() * h;
        if !world.plates_at(x, y).is_empty() {
            continue;
        }
        if ocean_centers
            .iter()
            .all(|&(ox, oy)| (x - ox) * (x - ox) + (y - oy) * (y - oy) >= min_sep2)
        {
            ocean_centers.push((x, y));
        }
    }

    if ocean_centers.is_empty() {
        return view;
    }

    let land_n = view.centers.len();
    let mut centers_2d: Vec<(f32, f32)> = view
        .centers
        .iter()
        .map(|c| (c[0], c[1]))
        .collect();
    let mut centers = view.centers;
    let mut biomes = view.biomes;
    let mut climate = view.climate;
    let mut river_flux = view.river_flux;
    let mut elevation = view.elevation;
    for &(ox, oy) in &ocean_centers {
        centers_2d.push((ox, oy));
        centers.push([ox, oy, 0.0]);
        biomes.push(BiomeKind::Ocean);
        climate.push(ClimateZone::Tropical);
        river_flux.push(0.0);
        elevation.push(0.0);
    }

    let neighbors = build_delaunay_neighbors(&centers_2d);
    let is_coast = compute_is_coast(&biomes, &neighbors);

    debug_assert_eq!(centers.len(), land_n + ocean_centers.len());
    debug_assert_eq!(biomes.len(), centers.len());
    debug_assert_eq!(neighbors.len(), centers.len());

    CivView {
        centers,
        neighbors,
        biomes,
        climate,
        river_flux,
        is_coast,
        elevation,
        sea_level: view.sea_level,
    }
}

/// **Civ Ship 4** — quantise the civ view's f32 elevation into the
/// u16 grid System-A's hydrology stack expects.
///
/// Calibration: flatworld f32 elevation lives in `[0.0, ~0.9]` —
/// `0.0` is void / synthetic ocean, `BASE_LEVEL = 0.35` is plate
/// interior. Maps `[0, 1]` → `[0, 65535]` (clamping past `1.0`) and
/// sets `sea_level_u16` halfway between void (`0`) and `BASE_LEVEL`
/// so every void / synthetic-ocean cell (elev `0.0`) lands strictly
/// below sea level and every plate interior (`≥ BASE_LEVEL`) lands
/// strictly above.
pub fn elevation_to_u16(view: &CivView) -> (Vec<u16>, u16) {
    let elev: Vec<u16> = view
        .elevation
        .iter()
        .map(|&e| (e.clamp(0.0, 1.0) * 65535.0).round() as u16)
        .collect();
    let sea_level = ((BASE_LEVEL * 0.5) * 65535.0).round() as u16;
    (elev, sea_level)
}

/// **Approach A step 2** — project a flat civ view onto a unit sphere
/// via equirectangular projection.
///
/// For each cell centre `(x, y, 0)` in `view.centers`:
/// - longitude `lon = (x / w − 0.5) · 2π ∈ [−π, π]`
/// - latitude  `lat = (0.5 − y / h) · π ∈ [−π/2, π/2]` (y=0 is north pole)
/// - 3D unit sphere point `(cos(lat)·cos(lon), cos(lat)·sin(lon), sin(lat))`
///
/// **Topology caveat (LOW-1).** Equirectangular is a homeomorphism only
/// on the *open* rectangle interior: the left and right edges
/// (`x = 0` and `x = w`) map to the **same meridian** (the
/// antimeridian); the top and bottom edges (`y = 0` and `y = h`) map
/// to **single points** (the poles). Plate polygons that touch any
/// boundary edge will have Delaunay neighbour links that no longer
/// represent adjacency on the sphere. Phase-A continent-scale worlds
/// keep plates well inside the interior via `flatworld::place_centers`'s
/// `min_sep` margin, so this is empirically fine today.
///
/// **Why this projection is the correct substrate (not just an
/// upgrade).** System-A's civilization builders compute distance as
/// `1 - dot(c_a, c_b)` — monotone-equivalent to great-circle distance
/// only when both `c_a` and `c_b` are **unit vectors**. On flat
/// `[x, y, 0]` centres the metric becomes degenerate (HIGH-1 in
/// session 92 /review-impl).
pub fn project_to_sphere(view: &mut CivView, world: &FlatWorld) {
    let w = world.width as f32;
    let h = world.height as f32;
    if w <= 0.0 || h <= 0.0 {
        return;
    }
    for c in view.centers.iter_mut() {
        let (x, y) = (c[0], c[1]);
        let lon = (x / w - 0.5) * std::f32::consts::TAU;
        let lat = (0.5 - y / h) * std::f32::consts::PI;
        let cos_lat = lat.cos();
        c[0] = cos_lat * lon.cos();
        c[1] = cos_lat * lon.sin();
        c[2] = lat.sin();
    }
}

/// **Approach A step 2** — explicit-sphere variant of [`build_civ_view`]
/// that bakes the [`project_to_sphere`] step in.
///
/// Most callers want this. [`build_civ_view`] is kept as a flat opt-out
/// for the Ship-1 Delaunay tests that need direct access to the planar
/// adjacency; the pipeline convenience functions
/// (`extract_features` / `build_political` / `build_settlement` /
/// `build_routes` / `build_culture` / `bundle_civ`) all internally
/// project to sphere so their outputs match the metric assumed by
/// System-A's civilization builders.
pub fn build_civ_view_spherical(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
) -> CivView {
    let mut view = build_civ_view(world, climate_params);
    project_to_sphere(&mut view, world);
    view
}

// ---------- Internal helpers ----------

/// Build neighbor lists from a Delaunay triangulation over the 2D cell
/// centres. The triangulation's edge set becomes the adjacency.
fn build_delaunay_neighbors(centers_2d: &[(f32, f32)]) -> Vec<Vec<u32>> {
    let n = centers_2d.len();
    let mut neighbors: Vec<Vec<u32>> = vec![Vec::new(); n];
    if n < 3 {
        return neighbors;
    }
    let points: Vec<Point> = centers_2d
        .iter()
        .map(|&(x, y)| Point { x: x as f64, y: y as f64 })
        .collect();
    let tri = triangulate(&points);
    for t in tri.triangles.chunks_exact(3) {
        let (a, b, c) = (t[0] as u32, t[1] as u32, t[2] as u32);
        for (u, v) in [(a, b), (b, c), (c, a)] {
            neighbors[u as usize].push(v);
            neighbors[v as usize].push(u);
        }
    }
    for nb in neighbors.iter_mut() {
        nb.sort_unstable();
        nb.dedup();
    }
    neighbors
}

/// Cells that sit next to an ocean cell are coast.
fn compute_is_coast(biomes: &[BiomeKind], neighbors: &[Vec<u32>]) -> Vec<bool> {
    let mut out = vec![false; biomes.len()];
    for (i, nb) in neighbors.iter().enumerate() {
        if biomes[i] == BiomeKind::Ocean {
            continue;
        }
        if nb
            .iter()
            .any(|&j| matches!(biomes[j as usize], BiomeKind::Ocean))
        {
            out[i] = true;
        }
    }
    out
}

/// Lossy mapping from the flatworld 21-cell Köppen classification to the
/// System-A 14-cell coarse biome. Trade-off: political / settlement /
/// route algorithms care about Forest-vs-Plain-vs-Desert distinctions,
/// not the Köppen subtypes that drive biome render colours.
pub fn koppen_to_biome_kind(koppen: Biome) -> BiomeKind {
    match koppen {
        Biome::Ef => BiomeKind::Glacier,
        Biome::Et => BiomeKind::Tundra,
        Biome::Dfd | Biome::Dfc => BiomeKind::Forest,
        Biome::Dfb | Biome::Dfa | Biome::Dwa => BiomeKind::Forest,
        Biome::Cfb | Biome::Cfa | Biome::Cwa => BiomeKind::Forest,
        Biome::Csa | Biome::Csb => BiomeKind::Plain,
        Biome::Bsh | Biome::Bsk => BiomeKind::Plain,
        Biome::Bwh | Biome::Bwk => BiomeKind::Desert,
        Biome::Af | Biome::Am => BiomeKind::Jungle,
        Biome::Aw => BiomeKind::Plain,
    }
}

/// Coarse System-A `ClimateZone` from per-cell temperature + precipitation
/// — the simple bucket-classifier System A's `climate::build` would have
/// produced with the same inputs.
pub fn derive_climate_zone(temp_mean: f32, precip_annual: f32) -> ClimateZone {
    if temp_mean < -5.0 {
        return ClimateZone::Polar;
    }
    if temp_mean < 5.0 {
        return ClimateZone::Boreal;
    }
    if precip_annual < 250.0 {
        return ClimateZone::Arid;
    }
    if temp_mean > 22.0 {
        return ClimateZone::Tropical;
    }
    if temp_mean > 15.0 {
        if precip_annual < 600.0 {
            ClimateZone::Mediterranean
        } else {
            ClimateZone::Subtropical
        }
    } else {
        ClimateZone::Temperate
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::{generate, FlatParams};

    pub(super) fn small_world() -> FlatWorld {
        let p = FlatParams {
            width: 256,
            height: 192,
            plate_count: 4,
            seed: 7,
            ..Default::default()
        };
        generate(&p)
    }

    #[test]
    fn civ_view_has_one_cell_per_subzone() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        let expected: usize = world
            .plates
            .iter()
            .flat_map(|p| p.zones.iter())
            .map(|z| z.subzones.len())
            .sum();
        assert_eq!(view.centers.len(), expected);
        assert_eq!(view.neighbors.len(), expected);
        assert_eq!(view.biomes.len(), expected);
        assert_eq!(view.climate.len(), expected);
        assert_eq!(view.river_flux.len(), expected);
        assert_eq!(view.is_coast.len(), expected);
        assert_eq!(view.elevation.len(), expected);
    }

    #[test]
    fn delaunay_neighbors_are_symmetric_and_deduped() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        for (i, nb) in view.neighbors.iter().enumerate() {
            let mut sorted = nb.clone();
            sorted.sort_unstable();
            assert_eq!(*nb, sorted, "cell {i}: neighbors should be sorted");
            assert!(
                nb.windows(2).all(|w| w[0] != w[1]),
                "cell {i}: neighbors should be deduped"
            );
            for &j in nb {
                assert!(
                    view.neighbors[j as usize].contains(&(i as u32)),
                    "adjacency asymmetric: {i} -> {j} but not back"
                );
            }
        }
    }

    #[test]
    fn delaunay_produces_planar_density() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        if view.centers.len() < 4 {
            return;
        }
        let total_edges: usize = view.neighbors.iter().map(|nb| nb.len()).sum();
        let avg = total_edges as f32 / view.centers.len() as f32;
        assert!(
            (3.0..=12.0).contains(&avg),
            "average neighbors per cell {avg:.2} outside [3, 12]; planar graph density is broken",
        );
    }

    #[test]
    fn koppen_translation_covers_every_input_variant() {
        let variants = [
            Biome::Ef, Biome::Et,
            Biome::Dfd, Biome::Dfc, Biome::Dfb, Biome::Dfa, Biome::Dwa,
            Biome::Cfb, Biome::Cfa, Biome::Csa, Biome::Csb, Biome::Cwa,
            Biome::Bsk, Biome::Bwk, Biome::Bsh, Biome::Bwh,
            Biome::Af, Biome::Am, Biome::Aw,
        ];
        for v in variants {
            let _ = koppen_to_biome_kind(v);
        }
    }

    #[test]
    fn climate_zone_derivation_hits_each_bucket() {
        assert_eq!(derive_climate_zone(-20.0, 200.0), ClimateZone::Polar);
        assert_eq!(derive_climate_zone(0.0, 600.0), ClimateZone::Boreal);
        assert_eq!(derive_climate_zone(10.0, 100.0), ClimateZone::Arid);
        assert_eq!(derive_climate_zone(28.0, 2000.0), ClimateZone::Tropical);
        assert_eq!(derive_climate_zone(18.0, 400.0), ClimateZone::Mediterranean);
        assert_eq!(derive_climate_zone(20.0, 1200.0), ClimateZone::Subtropical);
        assert_eq!(derive_climate_zone(12.0, 1200.0), ClimateZone::Temperate);
    }

    #[test]
    fn coast_flag_set_for_cells_neighbouring_ocean() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        for (i, &biome) in view.biomes.iter().enumerate() {
            if biome == BiomeKind::Ocean {
                for &nb in &view.neighbors[i] {
                    let j = nb as usize;
                    if view.biomes[j] != BiomeKind::Ocean {
                        assert!(
                            view.is_coast[j],
                            "cell {j} (biome {:?}) is adjacent to ocean cell {i} but is_coast is false",
                            view.biomes[j]
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn augment_with_ocean_adds_synthetic_ocean_cells() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        let land_n = view.centers.len();
        let augmented = augment_with_ocean(view, &world, 16);
        let total_n = augmented.centers.len();
        assert!(
            total_n > land_n,
            "augment should grow the cell count; before {land_n}, after {total_n}",
        );
        let ocean_n = augmented
            .biomes
            .iter()
            .filter(|&&b| b == BiomeKind::Ocean)
            .count();
        assert!(ocean_n >= 1, "should have ≥1 synthetic Ocean cell");
        for (i, &biome) in augmented.biomes.iter().enumerate().skip(land_n) {
            assert_eq!(biome, BiomeKind::Ocean, "appended cell {i} should be Ocean");
            let [x, y, _] = augmented.centers[i];
            assert!(
                world.plates_at(x, y).is_empty(),
                "synthetic ocean cell {i} at ({x:.1},{y:.1}) lands inside a plate"
            );
        }
    }

    #[test]
    fn augment_with_ocean_flips_coast_flag_on_neighbouring_land() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        let land_n = view.centers.len();
        let augmented = augment_with_ocean(view, &world, 16);
        let mut coast_hits = 0usize;
        for (i, &biome) in augmented.biomes.iter().enumerate().take(land_n) {
            if biome == BiomeKind::Ocean {
                continue;
            }
            let touches_ocean = augmented.neighbors[i]
                .iter()
                .any(|&j| augmented.biomes[j as usize] == BiomeKind::Ocean);
            if touches_ocean {
                assert!(
                    augmented.is_coast[i],
                    "land cell {i} touches ocean but is_coast is false"
                );
                coast_hits += 1;
            }
        }
        assert!(
            coast_hits > 0,
            "expected at least one coast cell after augment; got 0"
        );
    }

    #[test]
    fn augment_with_ocean_is_deterministic_per_target() {
        let world = small_world();
        let a = augment_with_ocean(
            build_civ_view(&world, &WorldClimateParams::default()),
            &world,
            12,
        );
        let b = augment_with_ocean(
            build_civ_view(&world, &WorldClimateParams::default()),
            &world,
            12,
        );
        assert_eq!(a.centers, b.centers);
        assert_eq!(a.biomes, b.biomes);
    }

    #[test]
    fn spherical_centers_lie_on_unit_sphere() {
        let world = generate(&FlatParams::default());
        let view = build_civ_view_spherical(&world, &WorldClimateParams::default());
        for (i, c) in view.centers.iter().enumerate() {
            let mag2 = c[0] * c[0] + c[1] * c[1] + c[2] * c[2];
            assert!(
                (mag2 - 1.0).abs() < 1e-4,
                "cell {i} centre {:?} has |c|² = {mag2}; should be 1.0",
                c
            );
        }
    }

    #[test]
    fn spherical_centers_preserve_distinctness() {
        // **review-impl MED-2**: 1 mrad quantisation (vs the 1µ in the
        // original; equirectangular per-pixel pitch is ~5 mrad so 1 mrad
        // catches near-degenerate collisions while staying above f32
        // round-off).
        let world = generate(&FlatParams::default());
        let view = build_civ_view_spherical(&world, &WorldClimateParams::default());
        let mut seen: std::collections::HashSet<(i32, i32, i32)> =
            std::collections::HashSet::new();
        let q = 1_000.0_f32;
        for c in &view.centers {
            let key = (
                (c[0] * q) as i32,
                (c[1] * q) as i32,
                (c[2] * q) as i32,
            );
            assert!(
                seen.insert(key),
                "two sphere centres landed within 1 mrad of each other at quantised key {:?}",
                key
            );
        }
    }

    #[test]
    fn project_to_sphere_zero_dim_world_is_noop() {
        let world = FlatWorld {
            width: 0,
            height: 0,
            plates: vec![],
            collision_gain: 1.0,
        };
        let mut view = CivView {
            centers: vec![[1.0, 2.0, 3.0]],
            neighbors: vec![vec![]],
            biomes: vec![BiomeKind::Ocean],
            climate: vec![ClimateZone::Tropical],
            river_flux: vec![0.0],
            is_coast: vec![false],
            elevation: vec![0.0],
            sea_level: 0.5,
        };
        project_to_sphere(&mut view, &world);
        assert_eq!(view.centers[0], [1.0, 2.0, 3.0], "no-op on zero-dim world");
    }

    #[test]
    fn elevation_to_u16_keeps_void_below_sea_and_base_above() {
        let world = generate(&FlatParams::default());
        let view = augment_with_ocean(
            build_civ_view(&world, &WorldClimateParams::default()),
            &world,
            32,
        );
        let (elev_u16, sea) = elevation_to_u16(&view);
        for (i, &biome) in view.biomes.iter().enumerate() {
            if biome == BiomeKind::Ocean {
                assert!(
                    elev_u16[i] < sea,
                    "ocean cell {i} elev_u16 {} should be < sea {sea}",
                    elev_u16[i]
                );
            } else {
                assert!(
                    elev_u16[i] >= sea,
                    "land cell {i} (biome {biome:?}) elev_u16 {} should be ≥ sea {sea}",
                    elev_u16[i]
                );
            }
        }
    }
}
