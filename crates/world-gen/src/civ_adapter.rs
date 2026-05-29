//! **Civ Ship 1** — adapter that exposes a `flatworld::FlatWorld` through
//! the same `(centers, neighbors, biomes, climate, river_flux, is_coast,
//! elevation, sea_level)` interface the System-A civilization stack
//! ([`crate::political`], [`crate::settlement`], [`crate::routes`],
//! [`crate::culture`], [`crate::feature`], [`crate::naming`]) already
//! consumes. The downstream code is 100% mesh-agnostic — it doesn't care
//! whether `centers` come from a Fibonacci sphere or a flat rectangle —
//! so a single adapter unlocks all those layers for the flatworld track.
//!
//! ## Cell granularity
//!
//! v1 uses **L2 sub-zone = cell** (`world.plates[p].zones[z].subzones[s]`).
//! The default world is ~150 sub-zones — coarse but enough to validate the
//! adapter wiring; later civilization ships can opt for finer granularity
//! by sampling extra cells inside each sub-zone polygon.
//!
//! ## Adjacency
//!
//! Built via Delaunay triangulation over sub-zone centers using the
//! `delaunator` crate (already a dependency from `shape::slime`). Each
//! Delaunay edge becomes a bidirectional neighbor link. This produces a
//! planar graph with the right asymptotic density for the System-A
//! political/route algorithms (≈6 neighbors per cell vs. the spherical
//! Voronoi's ≈6 — same scale).
//!
//! ## Biome / climate
//!
//! Sub-zone biome is computed by sampling [`flat_climate::compute_zone_climate`]
//! at the sub-zone centre, then translating the Köppen classification
//! (`flat_climate::Biome` — 21 cells) to System A's coarser
//! [`crate::biome::BiomeKind`] (14 cells) and [`crate::climate::ClimateZone`]
//! (8 cells). The translation is intentionally lossy — System A's
//! political/settlement code only needs the coarser distinctions to drive
//! province / settlement / route placement.

use delaunator::{triangulate, Point};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::SettlementDensity;
use crate::culture::{self, Culture};
use crate::feature::{self, Features};
use crate::flat_climate::{compute_zone_climate, Biome, WorldClimateParams, ZoneClimate};
use crate::flatworld::{FlatWorld, BASE_LEVEL};
use crate::hydrology::{self, Hydrology};
use crate::political::{self, Political};
use crate::rng::Rng;
use crate::routes::{self};
use crate::settlement::{self};
use crate::world_map::{Route, Settlement};

/// A mesh-shaped view of a `FlatWorld` ready to feed into the System-A
/// civilization stack. Lengths of every per-cell vector equal
/// `centers.len()`.
#[derive(Debug, Clone)]
pub struct CivView {
    /// Sub-zone centres in 3D (z=0 for the flat substrate). Cell `i` is
    /// at `centers[i]`.
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
    /// Per-cell river flux. v1 leaves this at `0.0`; civ-layer Ship 2+
    /// will sample the flatworld hydrology MVP at the cell centre.
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
            // Compute the parent-zone climate once; sub-zones inherit it
            // for biome/temp/precip in v1. Differentiating climate per
            // sub-zone is a civ-layer Ship 6+ refinement.
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
    // over climate-driven Köppen biomes. A sub-zone centre that falls in
    // void (no plate covers it) is Ocean; high-elevation centres are
    // Mountain/Hill; everything else is classified by Köppen via
    // [`koppen_to_biome_kind`].
    let biomes: Vec<BiomeKind> = centers_2d
        .iter()
        .zip(zone_climates.iter())
        .zip(elevation.iter())
        .map(|((&(x, y), c), &elev)| {
            // Thresholds calibrated against `flatworld` elevation
            // constants: `BASE_LEVEL = 0.35` (interior of a single
            // plate), collision overlap adds `collision_strength *
            // collision_gain` (typically 0.05-0.25 per overlapping
            // pair). Mountain at `> 0.55` catches collision peaks
            // (≥0.20 above base); Hill at `> 0.45` catches modest
            // collision uplift (≥0.10 above base). Cells exactly at
            // BASE_LEVEL stay climate-classified.
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
/// ocean cells:
///
/// - [`feature::extract`] can't find water bodies.
/// - `is_coast` stays false for every cell.
/// - `settlement::build` has no incentive to place coastal cities.
///
/// This pass samples points in the world's **void region** (any spot
/// where `world.plates_at` returns empty), assigns
/// `BiomeKind::Ocean` to each, rebuilds the Delaunay adjacency over the
/// combined point set, and recomputes `is_coast` so coastal land
/// sub-zones flip to `true`.
///
/// Sampling is deterministic — seeded from `world.collision_gain` +
/// `target_count` so the same `(world, target_count)` always yields the
/// same ocean point set. Uses simple Poisson-disk rejection with a
/// minimum-separation derived from the world's area so coverage stays
/// even.
pub fn augment_with_ocean(view: CivView, world: &FlatWorld, target_count: usize) -> CivView {
    let w = world.width as f32;
    let h = world.height as f32;
    let target = target_count.max(1);

    // Min-separation tuned for even coverage. Area / target = expected
    // cell area; the rejection radius is ~70 % of that side length so
    // we get a slightly-jittered grid pattern, not a Poisson-blue spot
    // distribution. Coarser is fine — we just need enough ocean cells
    // for water-body components to form and is_coast to fire.
    let cell_area = (w * h) / (target as f32);
    let min_sep = cell_area.sqrt() * 0.7;
    let min_sep2 = min_sep * min_sep;

    let mut rng = Rng::for_stage(
        ((world.width as u64) << 32) | (world.height as u64) | (target as u64),
        b"civ-ocean",
    );
    let max_attempts = target.saturating_mul(80).max(2_000);
    let mut ocean_centers: Vec<(f32, f32)> = Vec::with_capacity(target);
    let mut attempts = 0_usize;
    while ocean_centers.len() < target && attempts < max_attempts {
        attempts += 1;
        let x = rng.next_f32() * w;
        let y = rng.next_f32() * h;
        if !world.plates_at(x, y).is_empty() {
            continue; // inside a plate — not void
        }
        if ocean_centers
            .iter()
            .all(|&(ox, oy)| (x - ox) * (x - ox) + (y - oy) * (y - oy) >= min_sep2)
        {
            ocean_centers.push((x, y));
        }
    }

    if ocean_centers.is_empty() {
        // World is entirely covered by plates (rare; tiny test worlds).
        // Return the view unchanged — no synthetic Ocean is honest.
        return view;
    }

    // Stitch ocean cells onto the existing CivView.
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
        // Ocean climate is `Tropical` (warmest of the system-A buckets);
        // settlement/route code doesn't read climate on water cells, so
        // the specific bucket doesn't matter — just stays consistent.
        climate.push(ClimateZone::Tropical);
        river_flux.push(0.0);
        elevation.push(0.0);
    }

    // Rebuild Delaunay neighbors over the union of land+ocean centers,
    // then re-derive coast flags on the joint biome vec.
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

/// **Civ Ship 2** — convenience pipeline: build a civ view, augment it
/// with synthetic ocean cells, then run System-A's mesh-agnostic
/// [`feature::extract`] to get named mountain ranges, rivers, and water
/// bodies for downstream naming / political / settlement layers.
///
/// `ocean_target` is the number of ocean cells to synthesize. A default
/// world (1280×720, 12 plates) reads well with 40-80 ocean cells; tiny
/// test worlds with 8-16. Pass `0` to skip ocean augmentation (matches
/// Ship-1 behaviour).
///
/// Returns `(view, features)` so callers can pass both to System-A's
/// political / settlement / route builders without re-running the
/// expensive climate sweep inside [`build_civ_view`].
pub fn extract_features(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
) -> (CivView, Features) {
    let view = build_civ_view(world, climate_params);
    let view = if ocean_target > 0 {
        augment_with_ocean(view, world, ocean_target)
    } else {
        view
    };
    let features = feature::extract(&view.biomes, &view.neighbors);
    (view, features)
}

/// **Civ Ship 4** — quantise the civ view's f32 elevation into the
/// u16 grid System-A's hydrology stack expects. Returns the per-cell
/// `Vec<u16>` and the matching `sea_level` cutoff.
///
/// Calibration: flatworld f32 elevation lives in `[0.0, ~0.9]` —
/// `0.0` is void / synthetic ocean, `BASE_LEVEL = 0.35` is the
/// interior of an uncontested plate, and collision overlap can push
/// land cells up toward ~0.9. We linearly map `[0, 1]` → `[0, 65535]`
/// (clamping past `1.0`) and set `sea_level_u16` halfway between
/// void (`0`) and `BASE_LEVEL` so every void / synthetic-ocean cell
/// (elev `0.0`) lands strictly below sea level and every plate
/// interior (`≥ BASE_LEVEL`) lands strictly above.
pub fn elevation_to_u16(view: &CivView) -> (Vec<u16>, u16) {
    let elev: Vec<u16> = view
        .elevation
        .iter()
        .map(|&e| (e.clamp(0.0, 1.0) * 65535.0).round() as u16)
        .collect();
    let sea_level = ((BASE_LEVEL * 0.5) * 65535.0).round() as u16;
    (elev, sea_level)
}

/// **Civ Ship 4** — run System-A's hydrology pipeline (priority-flood
/// receiver graph + flow accumulation → river flux) on the civ view.
/// The output's `river_flux` and `is_coast` overrides the view's
/// adjacency-only is_coast from Ship 2 — hydrology's coast detection
/// uses real connectivity to the ocean network, not just immediate
/// neighbors.
pub fn build_hydrology_view(view: &CivView) -> Hydrology {
    let (elev_u16, sea_level_u16) = elevation_to_u16(view);
    hydrology::build(
        &view.centers,
        &elev_u16,
        sea_level_u16,
        &view.neighbors,
        &view.climate,
    )
}

/// **Civ Ship 4** — full pipeline through System-A's settlement
/// builder. Chains build_political → hydrology → settlement::build so
/// the caller gets the full (CivView, Features, Political, Hydrology,
/// Vec<Settlement>) bundle. Hydrology output overrides the view's
/// `river_flux` and `is_coast` since it computes both from real
/// drainage analysis.
pub fn build_settlement(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
) -> (CivView, Features, Political, Hydrology, Vec<Settlement>) {
    let (mut view, features, political) =
        build_political(world, climate_params, ocean_target, seed);
    let hydro = build_hydrology_view(&view);
    view.river_flux = hydro.river_flux.clone();
    view.is_coast = hydro.is_coast.clone();
    let settlements = settlement::build(
        seed,
        &view.centers,
        &view.biomes,
        &view.climate,
        &view.river_flux,
        &view.is_coast,
        density,
        &political,
    );
    (view, features, political, hydro, settlements)
}

// ============================================================================
// Civ Ship 7 — synthetic deterministic naming
// ============================================================================

// Pools of evocative fantasy names — seeded RNG picks one per feature.
// Short on purpose: the goal of Ship 7 is to give every feature a
// stable, non-empty name so SVG export (Ship 9) has labels to render.
// LLM-driven naming via a future `TextProvider` trait can replace these
// in Ship 7b without changing the rest of the civ pipeline.
const SETTLEMENT_NAMES: &[&str] = &[
    "Aetherholt", "Brightford", "Cinderwatch", "Dawnreach", "Embervale",
    "Frostmere", "Goldenhall", "Hollowbarrow", "Ironkeep", "Jadewood",
    "Kingsford", "Larkspur", "Mistmoor", "Northwatch", "Oakenshield",
    "Pinevale", "Quietwater", "Ravenholm", "Stonehearth", "Thornbury",
    "Umbergate", "Vinewreath", "Willowbrook", "Yewglen", "Zephyrport",
];

const STATE_NAMES: &[&str] = &[
    "Aelvarra", "Brennor", "Caldaris", "Drakhalim", "Eronthel",
    "Faerondale", "Glenwarde", "Hjarsgrad", "Iskandar", "Jorvik",
    "Kelmarine", "Lirenoth", "Mythraal", "Northkin", "Ostralia",
    "Parthenor", "Querion", "Rikhalim", "Sundarial", "Thalassia",
];

const PROVINCE_PREFIXES: &[&str] = &[
    "Vale of", "March of", "Reach of", "Hold of", "Span of", "Realm of",
    "Domain of", "Land of",
];

const PROVINCE_ROOTS: &[&str] = &[
    "Ashwynne", "Briarfall", "Caelwood", "Deepford", "Elder Pines",
    "Falconcrest", "Glimmerlake", "Hawthorn", "Ironbark", "Larkmere",
    "Mistgate", "Nightspire", "Oldhollow", "Pondbridge", "Quartzcliff",
    "Redmoor", "Silverbrook", "Twilight Glade", "Umbra", "Whitewater",
];

const CULTURE_NAMES: &[&str] = &[
    "Aelir", "Brenn", "Caelori", "Dhuran", "Eldari",
    "Fenni", "Gwynar", "Hjorl", "Iskari", "Jolvik",
    "Kelmar", "Lirthen", "Myrran", "Norval", "Ostren",
];

const MOUNTAIN_DESCRIPTORS: &[&str] = &[
    "Cloudpiercer", "Frostfang", "Sunspear", "Stormcrown", "Ashpeak",
    "Greyhorn", "Ironreach", "Mistwall", "Skyforge", "Thunderridge",
];

const RIVER_DESCRIPTORS: &[&str] = &[
    "Quickwater", "Silvercourse", "Black", "Goldrun", "Whisper",
    "Coldstream", "Greenway", "Bright", "Stillrun", "Hollow",
];

const WATER_BODY_DESCRIPTORS: &[&str] = &[
    "Whitecap Sea", "Sunken Bay", "Twilight Reach", "Sapphire Strait",
    "Mistwarden Sea", "Forgotten Bay", "Crystal Reach", "Halcyon Sound",
    "Verdant Coast", "Stormwatch Sea",
];

fn pick<'a>(pool: &'a [&'a str], rng: &mut Rng) -> &'a str {
    pool[(rng.next_u32() as usize) % pool.len()]
}

/// **Civ Ship 7** — assign deterministic synthetic names to every named
/// feature in the bundle. Seeded RNG picks each name from a small
/// per-category pool so a given `seed` always produces the same name
/// set. Settlement IDs disambiguate when the pool is smaller than the
/// settlement count (e.g. `"Brightford-7"`).
///
/// **NOT an LLM call.** LLM-driven naming requires a new `TextProvider`
/// trait (the v4.3 [`crate::shape::llm::LlmProvider`] is structured for
/// ShapeKind picking, not free-form text generation). Ship 7b will add
/// that trait + Anthropic / OpenAI / Ollama impls and replace this
/// stub. Until then synthetic names keep SVG export (Ship 9) labelable.
#[allow(clippy::too_many_arguments)]
pub fn apply_synthetic_names(
    features: &mut Features,
    political: &mut Political,
    settlements: &mut [Settlement],
    culture: &mut Culture,
    seed: u64,
) {
    let mut rng = Rng::for_stage(seed, b"civ-naming");
    for (i, s) in settlements.iter_mut().enumerate() {
        s.name = format!("{}-{i}", pick(SETTLEMENT_NAMES, &mut rng));
    }
    for (i, st) in political.states.iter_mut().enumerate() {
        st.name = format!("{}-{i}", pick(STATE_NAMES, &mut rng));
    }
    for (i, p) in political.provinces.iter_mut().enumerate() {
        let prefix = pick(PROVINCE_PREFIXES, &mut rng);
        let root = pick(PROVINCE_ROOTS, &mut rng);
        p.name = format!("{prefix} {root}-{i}");
    }
    for (i, c) in culture.culture_regions.iter_mut().enumerate() {
        c.name = format!("{}-{i}", pick(CULTURE_NAMES, &mut rng));
    }
    for (i, mr) in features.mountain_ranges.iter_mut().enumerate() {
        mr.name = format!(
            "{} Mountains-{i}",
            pick(MOUNTAIN_DESCRIPTORS, &mut rng)
        );
    }
    for (i, rv) in features.rivers.iter_mut().enumerate() {
        rv.name = format!("{} River-{i}", pick(RIVER_DESCRIPTORS, &mut rng));
    }
    for (i, wb) in features.water_bodies.iter_mut().enumerate() {
        wb.name = format!("{}-{i}", pick(WATER_BODY_DESCRIPTORS, &mut rng));
    }
}

/// **Civ Ship 5** — full pipeline through System-A's routes builder.
/// Chains [`build_settlement`] then [`routes::build`] using the
/// `Hydrology.river_threshold` for river-route detection.
pub fn build_routes(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
) -> (
    CivView,
    Features,
    Political,
    Hydrology,
    Vec<Settlement>,
    Vec<Route>,
) {
    let (view, features, political, hydro, settlements) =
        build_settlement(world, climate_params, ocean_target, seed, density);
    let routes_v = routes::build(
        &view.centers,
        &view.neighbors,
        &view.biomes,
        &view.river_flux,
        hydro.river_threshold,
        &view.is_coast,
        &settlements,
    );
    (view, features, political, hydro, settlements, routes_v)
}

/// **Civ Ship 6** — full pipeline through System-A's culture builder.
/// Adds [`culture::build`] on top of [`build_routes`].
///
/// `culture_count` is the requested number of distinct cultures
/// (clamped 1..=16 internally by System A). 5 is the typical default.
#[allow(clippy::too_many_arguments)]
pub fn build_culture(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
    culture_count: u8,
) -> (
    CivView,
    Features,
    Political,
    Hydrology,
    Vec<Settlement>,
    Vec<Route>,
    Culture,
) {
    let (view, features, political, hydro, settlements, routes_v) =
        build_routes(world, climate_params, ocean_target, seed, density);
    let culture_v = culture::build(seed, &view.centers, &view.neighbors, &view.biomes, culture_count);
    (
        view,
        features,
        political,
        hydro,
        settlements,
        routes_v,
        culture_v,
    )
}

/// **Civ Ship 3** — full pipeline through System-A's political builder.
/// Computes the CivView, augments with synthetic ocean cells, extracts
/// features, then derives provinces + states via [`political::build`].
///
/// Returns `(view, features, political)` so callers can pass any
/// combination into the downstream settlement / route / culture
/// builders.
pub fn build_political(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
) -> (CivView, Features, Political) {
    let (view, features) = extract_features(world, climate_params, ocean_target);
    let political = political::build(seed, &view.centers, &view.neighbors, &view.biomes);
    (view, features, political)
}

/// Build neighbor lists from a Delaunay triangulation over the 2D cell
/// centres. The triangulation's edge set becomes the adjacency.
fn build_delaunay_neighbors(centers_2d: &[(f32, f32)]) -> Vec<Vec<u32>> {
    let n = centers_2d.len();
    let mut neighbors: Vec<Vec<u32>> = vec![Vec::new(); n];
    if n < 3 {
        // Delaunay needs at least 3 points; degenerate cases produce no
        // edges. The civilization stack still works on a disconnected
        // graph — it just won't have any provinces / settlements.
        return neighbors;
    }
    let points: Vec<Point> = centers_2d
        .iter()
        .map(|&(x, y)| Point { x: x as f64, y: y as f64 })
        .collect();
    let tri = triangulate(&points);
    // Each triangle is 3 consecutive entries in `tri.triangles`.
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

/// Cells that sit next to an ocean cell are coast — `settlement::build`
/// biases toward these.
fn compute_is_coast(biomes: &[BiomeKind], neighbors: &[Vec<u32>]) -> Vec<bool> {
    let mut out = vec![false; biomes.len()];
    for (i, nb) in neighbors.iter().enumerate() {
        if biomes[i] == BiomeKind::Ocean {
            continue; // ocean itself isn't "coast"
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
        // Polar
        Biome::Ef => BiomeKind::Glacier,
        Biome::Et => BiomeKind::Tundra,
        // Continental
        Biome::Dfd | Biome::Dfc => BiomeKind::Forest, // boreal forest (taiga)
        Biome::Dfb | Biome::Dfa | Biome::Dwa => BiomeKind::Forest,
        // Temperate
        Biome::Cfb | Biome::Cfa | Biome::Cwa => BiomeKind::Forest,
        Biome::Csa | Biome::Csb => BiomeKind::Plain, // Mediterranean — open
        // Arid
        Biome::Bsh | Biome::Bsk => BiomeKind::Plain, // steppe → grassland
        Biome::Bwh | Biome::Bwk => BiomeKind::Desert,
        // Tropical
        Biome::Af | Biome::Am => BiomeKind::Jungle,
        Biome::Aw => BiomeKind::Plain, // savanna
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
    use crate::feature;
    use crate::flatworld::{generate, FlatParams};

    fn small_world() -> FlatWorld {
        // Small but multi-plate so neighbors / coast detection have
        // something to chew on — 4 plates × default zone/sub counts is
        // ~30-40 cells.
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
        // A Delaunay triangulation over interior points has on average ≈6
        // neighbors per vertex (Euler's formula, planar graph). Boundary
        // vertices have fewer. The average across the view should land in
        // a sane window — proves the triangulation is actually building
        // edges, not returning an empty mesh.
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        if view.centers.len() < 4 {
            return; // degenerate small test world
        }
        let total_edges: usize = view.neighbors.iter().map(|nb| nb.len()).sum();
        let avg = total_edges as f32 / view.centers.len() as f32;
        assert!(
            (3.0..=12.0).contains(&avg),
            "average neighbors per cell {avg:.2} outside [3, 12]; planar graph density is broken",
        );
    }

    #[test]
    fn feature_extract_accepts_civ_view_without_panicking() {
        // Smoke: System-A's mesh-agnostic feature::extract should accept
        // the adapter's (biomes, neighbors) and not panic. We don't pin
        // a specific feature count here — Ship 1's civilization adapter
        // only emits BiomeKind from L2 sub-zone centres, and those are
        // by construction inside plates (no synthetic Ocean cells yet),
        // so feature counts can be zero on small test worlds. Synthetic
        // ocean/river adjacency lands in civ-layer Ship 2.
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        let features = feature::extract(&view.biomes, &view.neighbors);
        // Just touch the result so the compiler doesn't optimise it out.
        let _ = features.mountain_ranges.len()
            + features.rivers.len()
            + features.water_bodies.len();
    }

    #[test]
    fn koppen_translation_covers_every_input_variant() {
        // Exhaustive: every Köppen variant must map to *some* BiomeKind.
        // Compiler enforcement — adding a Köppen variant fails this test
        // with E0004 until the match arm is added in
        // koppen_to_biome_kind.
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
        // Smoke that the cutoffs aren't tangled: a hot wet point lands in
        // Tropical; a cold point lands in Polar; etc.
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
        // If any cell is ocean and any of its neighbours is land, the
        // land neighbour must be flagged is_coast. If no ocean cell
        // exists in the test world the assertion vacuously holds.
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        for (i, &biome) in view.biomes.iter().enumerate() {
            if biome == BiomeKind::Ocean {
                for &nb in &view.neighbors[i] {
                    let j = nb as usize;
                    if view.biomes[j] != BiomeKind::Ocean {
                        assert!(
                            view.is_coast[j],
                            "cell {j} (biome {:?}) is adjacent to ocean cell {i} \
                             but is_coast is false",
                            view.biomes[j]
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn augment_with_ocean_adds_synthetic_ocean_cells() {
        // Ship 2: augment pass should append BiomeKind::Ocean cells AND
        // those cells should fall in void area (no plate covers them).
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
        // Each synthetic ocean cell's centre must be in void.
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
        // After ocean augmentation a coastal land sub-zone (adjacent to
        // at least one synthetic ocean cell) must have is_coast=true.
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
        // Same world + same target_count must produce the same ocean
        // point set (Civ-layer must be byte-deterministic to keep the
        // generate→export pipeline reproducible).
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
    fn extract_features_default_world_yields_water_and_mountains() {
        // Ship 2 acceptance: on a default-sized world the convenience
        // pipeline must produce ≥1 water_body AND ≥1 mountain_range —
        // proves the (ocean synthesis + biome derivation + Delaunay
        // adjacency + feature::extract) chain actually does work
        // end-to-end. Smaller worlds were too sparse in Ship 1.
        let world = generate(&FlatParams::default());
        let (_view, features) = extract_features(&world, &WorldClimateParams::default(), 64);
        assert!(
            !features.water_bodies.is_empty(),
            "default world should produce ≥1 water body after ocean synth"
        );
        assert!(
            !features.mountain_ranges.is_empty(),
            "default world should produce ≥1 mountain range from collision uplift"
        );
    }

    #[test]
    fn extract_features_with_zero_ocean_target_skips_augment() {
        // ocean_target=0 should be a no-op (matches Ship 1 behaviour).
        let world = small_world();
        let view_ship1 = build_civ_view(&world, &WorldClimateParams::default());
        let (view_skip, _) = extract_features(&world, &WorldClimateParams::default(), 0);
        assert_eq!(view_skip.centers.len(), view_ship1.centers.len());
        assert_eq!(view_skip.biomes, view_ship1.biomes);
    }

    #[test]
    fn build_political_produces_provinces_and_states_on_default_world() {
        // Ship 3 acceptance: System-A's political::build, fed the civ
        // adapter output, must produce ≥1 province AND ≥1 state on a
        // default-sized world. Small worlds may degenerate (too few land
        // cells for the province/state thresholds) so this MUST run
        // against the default `FlatParams`.
        let world = generate(&FlatParams::default());
        let (_view, _features, political) = build_political(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
        );
        assert!(
            !political.provinces.is_empty(),
            "default world should produce ≥1 province"
        );
        assert!(
            !political.states.is_empty(),
            "default world should produce ≥1 state"
        );
    }

    #[test]
    fn build_political_assigns_every_land_cell_to_a_province() {
        // Every land cell must have province_of != NONE (NONE = u32::MAX
        // by convention in world_map.rs). Ocean cells stay NONE — they
        // belong to no province.
        let world = generate(&FlatParams::default());
        let (view, _features, political) = build_political(
            &world,
            &WorldClimateParams::default(),
            64,
            7,
        );
        let none = u32::MAX;
        for (i, &biome) in view.biomes.iter().enumerate() {
            let p = political.province_of[i];
            if biome == BiomeKind::Ocean {
                // Ocean cells should be unassigned.
                assert_eq!(
                    p, none,
                    "ocean cell {i} got assigned province {p}",
                );
            } else {
                assert_ne!(
                    p, none,
                    "land cell {i} (biome {biome:?}) has no province assignment",
                );
            }
        }
    }

    #[test]
    fn build_political_is_deterministic_per_seed() {
        // Same (world, climate, ocean_target, seed) → same political
        // output. Civ-layer pipeline must stay byte-deterministic to
        // preserve the generate→export reproducibility guarantee.
        let world = generate(&FlatParams::default());
        let (_, _, a) = build_political(&world, &WorldClimateParams::default(), 32, 99);
        let (_, _, b) = build_political(&world, &WorldClimateParams::default(), 32, 99);
        assert_eq!(a.province_of, b.province_of);
        assert_eq!(a.provinces.len(), b.provinces.len());
        assert_eq!(a.states.len(), b.states.len());
    }

    #[test]
    fn elevation_to_u16_keeps_void_below_sea_and_base_above() {
        // Void/synthetic-ocean cells (elev 0.0) must end up STRICTLY
        // below sea_level_u16; cells at BASE_LEVEL (0.35) must end up
        // STRICTLY above. This is the contract Ship 4 relies on so
        // hydrology's priority-flood correctly identifies ocean cells.
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

    #[test]
    fn build_settlement_produces_settlements_on_default_world() {
        // Ship 4 acceptance: System-A's settlement::build, fed the civ
        // adapter output + hydrology-derived river_flux + is_coast,
        // must produce ≥3 settlements on a default-sized world.
        let world = generate(&FlatParams::default());
        let (_view, _f, _pol, _hyd, settlements) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
        );
        assert!(
            settlements.len() >= 3,
            "expected ≥3 settlements on default world, got {}",
            settlements.len()
        );
    }

    #[test]
    fn settlements_only_land_cells_not_ocean() {
        let world = generate(&FlatParams::default());
        let (view, _, _, _, settlements) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            64,
            7,
            SettlementDensity::Medium,
        );
        for s in &settlements {
            let cell = s.cell as usize;
            assert_ne!(
                view.biomes[cell],
                BiomeKind::Ocean,
                "settlement '{}' placed on Ocean cell {cell}",
                s.name
            );
        }
    }

    #[test]
    fn build_settlement_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, a) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
        );
        let (_, _, _, _, b) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
        );
        assert_eq!(a.len(), b.len());
        for (sa, sb) in a.iter().zip(b.iter()) {
            assert_eq!(sa.cell, sb.cell);
            assert_eq!(sa.role, sb.role);
        }
    }

    #[test]
    fn build_routes_produces_routes_on_default_world() {
        // Ship 5 acceptance: System-A's routes::build, fed the full civ
        // pipeline, must produce ≥1 Route on a default-sized world.
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, routes_v) = build_routes(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
        );
        assert!(
            !routes_v.is_empty(),
            "default world should produce ≥1 route"
        );
    }

    #[test]
    fn build_culture_produces_multiple_regions_on_default_world() {
        // Ship 6 acceptance: System-A's culture::build, fed the full civ
        // pipeline, must produce ≥2 culture regions when culture_count=5
        // is requested on a default-sized world.
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, _, culture_v) = build_culture(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        assert!(
            culture_v.culture_regions.len() >= 2,
            "default world should produce ≥2 culture regions, got {}",
            culture_v.culture_regions.len()
        );
    }

    #[test]
    fn build_culture_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, _, a) = build_culture(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        let (_, _, _, _, _, _, b) = build_culture(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        assert_eq!(a.culture_of, b.culture_of);
        assert_eq!(a.culture_regions.len(), b.culture_regions.len());
    }

    #[test]
    fn synthetic_names_populate_every_named_feature() {
        // Ship 7: every named feature in the bundle must end up with a
        // non-empty `name` after `apply_synthetic_names`. Empty names
        // would crash the SVG export label rendering in Ship 9.
        let world = generate(&FlatParams::default());
        let (_view, mut features, mut political, _hyd, mut settlements, _routes_v, mut culture_v) =
            build_culture(
                &world,
                &WorldClimateParams::default(),
                64,
                42,
                SettlementDensity::Medium,
                5,
            );
        apply_synthetic_names(
            &mut features,
            &mut political,
            &mut settlements,
            &mut culture_v,
            42,
        );
        for s in &settlements {
            assert!(!s.name.is_empty(), "settlement {} unnamed", s.cell);
        }
        for st in &political.states {
            assert!(!st.name.is_empty(), "state {} unnamed", st.id);
        }
        for p in &political.provinces {
            assert!(!p.name.is_empty(), "province {} unnamed", p.id);
        }
        for c in &culture_v.culture_regions {
            assert!(!c.name.is_empty(), "culture {} unnamed", c.id);
        }
        for mr in &features.mountain_ranges {
            assert!(!mr.name.is_empty(), "mountain {} unnamed", mr.id);
        }
        for wb in &features.water_bodies {
            assert!(!wb.name.is_empty(), "water body {} unnamed", wb.id);
        }
    }

    #[test]
    fn synthetic_names_are_deterministic_per_seed() {
        // Same seed → same names.
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                99,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        apply_synthetic_names(&mut fa, &mut pa, &mut sa, &mut ca, 99);
        apply_synthetic_names(&mut fb, &mut pb, &mut sb, &mut cb, 99);
        for (a, b) in sa.iter().zip(sb.iter()) {
            assert_eq!(a.name, b.name);
        }
        for (a, b) in pa.provinces.iter().zip(pb.provinces.iter()) {
            assert_eq!(a.name, b.name);
        }
    }

    #[test]
    fn synthetic_names_differ_across_seeds() {
        // Different seeds should produce different name sets — proves
        // the seed actually flows into the picker (regression catch).
        let world = generate(&FlatParams::default());

        let make_bundle = || {
            let (_, f, p, _, s, _, c) = build_culture(
                &world,
                &WorldClimateParams::default(),
                32,
                7,
                SettlementDensity::Medium,
                5,
            );
            (f, p, s, c)
        };
        let (mut fa, mut pa, mut sa, mut ca) = make_bundle();
        let (mut fb, mut pb, mut sb, mut cb) = make_bundle();
        apply_synthetic_names(&mut fa, &mut pa, &mut sa, &mut ca, 1);
        apply_synthetic_names(&mut fb, &mut pb, &mut sb, &mut cb, 999);
        // At least one settlement name must differ between seeds.
        let differ = sa
            .iter()
            .zip(sb.iter())
            .any(|(a, b)| a.name != b.name);
        assert!(
            differ,
            "two distinct seeds produced identical settlement names; \
             RNG isn't reaching the picker"
        );
    }
}
