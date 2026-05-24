//! Flat-world generator — a NEW, top-down hierarchical sketch, kept fully
//! separate from the sphere/`terrain.rs` pipeline.
//!
//! **Level 0 (this file): tectonic plates as polygons on a flat rectangle.**
//! A `width × height` rectangle holds `n` randomly-generated polygons (the
//! tectonic plates). They may overlap or sit far apart; the uncovered space
//! between them is the **void** (`hư vô`). No elevation yet — everything is
//! flat; this is purely the macro plate layout that later levels build on.
//!
//! Everything is deterministic (seeded [`Rng`]) and parameter-driven, so the
//! layout can be steered or pinned.

use crate::rng::Rng;
use serde::Serialize;
use std::f32::consts::TAU;

/// Inputs for [`generate`]. All fields are intervenable; [`Default`] gives the
/// reference layout (7 plates).
#[derive(Debug, Clone)]
pub struct FlatParams {
    /// Rectangle size in pixels.
    pub width: u32,
    pub height: u32,
    /// Number of plates (tectonic blocks). Reference value: 7.
    pub plate_count: usize,
    /// Master seed — same seed ⇒ same layout.
    pub seed: u64,
    /// Vertices per plate polygon, inclusive range. More verts ⇒ rounder.
    pub min_vertices: usize,
    pub max_vertices: usize,
    /// Plate "radius" as a fraction of the centre **pitch**
    /// (`sqrt(area / plate_count)`), inclusive range. Tying radius to the pitch
    /// (not the frame) keeps overlaps scale-invariant: ~`0.5` ⇒ neighbours just
    /// touch; a little above `0.5` ⇒ thin collision seams; well above ⇒ plates
    /// stack (avoid). Smaller ⇒ more void.
    pub min_radius_frac: f32,
    pub max_radius_frac: f32,
    /// Per-vertex radial jitter `0..1` — 0 = regular polygon, 1 = very ragged.
    pub edge_jitter: f32,
    /// Max plate drift speed (arbitrary units). Each plate gets a random
    /// direction + a speed in `0..max_speed`. Collisions = convergent drift.
    pub max_speed: f32,
    /// How much a unit of convergence raises the overlap elevation. Higher ⇒
    /// taller collision mountains. (`càng va mạnh càng nhô cao`.)
    pub collision_gain: f32,
    /// Minimum centre-to-centre spacing as a fraction of the ideal grid pitch
    /// `sqrt(area / plate_count)`. Higher ⇒ centres spread out ⇒ plates meet
    /// at thin boundary seams instead of stacking on top of each other (real
    /// plates tile the surface; they don't fully overlap). `0` = no constraint.
    pub separation: f32,
    /// Zones per plate, inclusive range — each plate is subdivided into a random
    /// count in `[min_zones, max_zones]` via an interior Voronoi partition.
    pub min_zones: usize,
    pub max_zones: usize,
    /// Sub-zones per zone, inclusive range — each L1 zone is subdivided again
    /// (nested Voronoi) into a random count in `[min_subzones, max_subzones]`.
    /// This is the depth-2 level of the region tree.
    pub min_subzones: usize,
    pub max_subzones: usize,
}

impl Default for FlatParams {
    fn default() -> Self {
        Self {
            width: 1024,
            height: 640,
            // B5 v2.1a default: 7 → 12 (per §6.2 sweep result). Min biome
            // variety guaranteed 4 → 5 distinct biomes; mean 5.4 → 6.2; no
            // more monoculture seeds.
            plate_count: 12,
            seed: 1,
            // V1 Phase A: bump 6/11 → 24/48 so plate outlines stop looking
            // like a kid's drawing — enough vertices to host multi-octave
            // noise deformation (bays + peninsulas) without aliasing the
            // low-freq lobes. See docs/plans/2026-05-25-world-map-v1-buildout.md §3.A.1.
            min_vertices: 24,
            max_vertices: 48,
            // Radius as a fraction of the centre pitch: just over 0.5 so
            // adjacent plates overlap in a thin seam (the boundary), not a
            // full stack — Earth-like. With `separation` ≈ 0.9 the closest
            // pairs collide thinly; farther pairs leave void.
            min_radius_frac: 0.50,
            max_radius_frac: 0.66,
            edge_jitter: 0.35,
            max_speed: 1.0,
            collision_gain: 0.35,
            separation: 0.90,
            min_zones: 3,
            max_zones: 7,
            min_subzones: 3,
            max_subzones: 6,
        }
    }
}

/// Plate base elevation (the "unchanged" height of land that isn't colliding).
/// Collisions add on top; void sits below. Named here as the obvious next
/// intervention point for the elevation pass.
pub const BASE_LEVEL: f32 = 0.35;
/// Elevation of the void (uncovered space between plates).
pub const VOID_LEVEL: f32 = 0.0;

/// V1 Phase A v3.0: a single closed polygon ring. A [`Plate`] now holds 1+
/// of these (the first is the **primary** continent; subsequent entries are
/// satellite islands once v3.3 ships true archipelago generation).
pub type Polygon = Vec<(f32, f32)>;

/// V1 Phase A v3.0: deterministic size class for plate generation. Real
/// continental landmasses span ~120× area ratio (Eurasia 54.8M km² vs
/// Baffin 0.5M km²) — uniform sampling can't capture that. Each rank gets
/// a calibrated radius band; total expected area across all ranks matches
/// the pre-v3.0 distribution within 5% so the climate eval composite
/// stays stable.
///
/// Distribution for the default 12-plate world: 1 Giant + 2 Large + 3
/// Medium + 4 Small + 2 Micro. See `assign_size_ranks`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize)]
pub enum SizeRank {
    /// Eurasia-scale supercontinent (~1.6× per-rank-mean area). One per world.
    Giant,
    /// Africa / N.America / S.America scale.
    Large,
    /// Australia / Antarctica / Greenland scale.
    Medium,
    /// Madagascar / Borneo / Sumatra scale.
    Small,
    /// Iceland / Hispaniola / island microplate scale.
    Micro,
}

impl SizeRank {
    /// Radius band `(r_min, r_max)` in units of `pitch = sqrt(area / plate_count)`.
    /// Calibrated so the default 12-plate distribution preserves expected
    /// total land area within 5% of pre-v3.0 (`12 × π × 0.34 × pitch² ≈ 12.76`).
    pub fn radius_band(self) -> (f32, f32) {
        match self {
            SizeRank::Giant => (1.00, 1.20),
            SizeRank::Large => (0.70, 0.85),
            SizeRank::Medium => (0.50, 0.62),
            SizeRank::Small => (0.28, 0.40),
            SizeRank::Micro => (0.15, 0.22),
        }
    }

    /// Aspect ratio range `(min, max)` — most ranks slightly anisotropic,
    /// large ranks more so (Eurasia 2.3:1 E-W; Italy 4:1 NW-SE).
    pub fn aspect_band(self) -> (f32, f32) {
        match self {
            SizeRank::Giant => (1.3, 2.5),    // forced elongation (Eurasia-like)
            SizeRank::Large => (1.0, 2.0),
            SizeRank::Medium => (1.0, 1.6),
            SizeRank::Small => (1.0, 2.0),    // small but can be peninsular
            SizeRank::Micro => (1.0, 1.4),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            SizeRank::Giant => "Giant",
            SizeRank::Large => "Large",
            SizeRank::Medium => "Medium",
            SizeRank::Small => "Small",
            SizeRank::Micro => "Micro",
        }
    }
}

/// V1 Phase A v3.0: assign size ranks to `n` plates deterministically.
/// Default 12-plate distribution: 1 Giant + 2 Large + 3 Medium + 4 Small + 2
/// Micro. For other counts, scale proportionally (giant always ≥1 for n≥1).
pub fn assign_size_ranks(n: usize) -> Vec<SizeRank> {
    if n == 0 { return Vec::new(); }
    if n == 12 {
        // Canonical hand-tuned distribution for the reference world.
        return vec![
            SizeRank::Giant,
            SizeRank::Large, SizeRank::Large,
            SizeRank::Medium, SizeRank::Medium, SizeRank::Medium,
            SizeRank::Small, SizeRank::Small, SizeRank::Small, SizeRank::Small,
            SizeRank::Micro, SizeRank::Micro,
        ];
    }
    // Scaled fallback: 8% Giant, 17% Large, 25% Medium, 33% Small, 17% Micro.
    let weights = [
        (SizeRank::Giant, 0.08),
        (SizeRank::Large, 0.17),
        (SizeRank::Medium, 0.25),
        (SizeRank::Small, 0.33),
        (SizeRank::Micro, 0.17),
    ];
    let mut counts: Vec<(SizeRank, usize)> = weights
        .iter()
        .map(|&(r, w)| (r, ((n as f32) * w).round() as usize))
        .collect();
    // Guarantee at least 1 Giant; absorb the deficit/surplus into Small.
    if counts[0].1 == 0 { counts[0].1 = 1; }
    let total: usize = counts.iter().map(|(_, c)| *c).sum();
    if total < n {
        counts[3].1 += n - total;
    } else if total > n {
        let mut over = total - n;
        for (_, c) in counts.iter_mut().rev() {
            if over == 0 { break; }
            let take = (*c).min(over);
            *c -= take;
            over -= take;
        }
    }
    counts.into_iter().flat_map(|(r, c)| std::iter::repeat_n(r, c)).collect()
}

// ── V1 Phase A: polygon realism constants ──────────────────────────────────
//
// Vertex deformation: multi-octave fbm warps each polygon vertex radially.
// AMP=0.30 keeps r in roughly [0.7·radius, 1.3·radius] (fbm range ~±0.71
// × 0.30 = ±0.21 on the (1 + ...) scale) — visibly more organic than the
// old smooth octagons, small enough to keep the angular spoke layout
// simple and to preserve the climate eval composite (~±1pt). FREQ=1.5 + 3
// octaves gives ~4-6 main lobes per plate perimeter at octave 1
// (continent-scale capes/bays), cascading to ~10 / ~20 lobes for smaller
// bumps and inlets. AMP=0.40 was tried but added a -6pt regression on a
// single eval seed (s42) — defer pushing further to Phase B+ when more
// rendering polish is in place to mask the geometry change.
//
// Crucially the old per-vertex random shrink (35% range, RNG-per-vertex)
// is GONE — at high vertex counts (24-48) it produced spiky stars instead
// of organic shapes. The shrink is now a constant bias derived from
// `edge_jitter` so E[r] still matches old behavior (preserves land:ocean
// ratio), while multi-octave noise carries all the geometric variation.
const EDGE_NOISE_AMP: f32 = 0.30;
const EDGE_NOISE_FREQ: f32 = 1.5;
const EDGE_NOISE_OCTAVES: u32 = 3;
// Per-vertex random shrink kept for "natural character" but scaled DOWN
// from 1.0 to avoid the spiky-star look at high vertex counts. ~0.10 means
// 10% of the old jitter magnitude per vertex (∼3.5% radius variation at
// default edge_jitter=0.35), which preserves the eval's per-vertex
// variability without dominating the smooth-noise lobes visually. Bias
// term in the vertex loop compensates so E[r] is unchanged.
const JITTER_RESIDUAL_SCALE: f32 = 0.10;

// Voronoi zone-boundary domain warp: at render time `zone_at` perturbs
// (x, y) by fbm noise before nearest-site lookup. WAVELENGTH ≈ 1/FREQ = 50px,
// AMP=8.0 → max displacement ≈ 8·0.71 ≈ 5.7px (fbm range ≈ [-0.71, 0.71]).
// Safe vs sliver creation: default site spacing ≥ ~80px (12 plates, 3–7
// zones each) → warp ≪ 0.3 × spacing, the cap recommended in spec §3.A.3.
const ZONE_WARP_AMP: f32 = 8.0;
const ZONE_WARP_FREQ: f32 = 0.02;
const ZONE_WARP_OCTAVES: u32 = 2;

/// One tectonic plate: a primary continent polygon + zero or more satellite
/// island polygons (the multi-component support is wired up in v3.0; only
/// `components.len() == 1` is produced until the Archipelago / IslandArc
/// templates land in v3.3).
#[derive(Debug, Clone)]
pub struct Plate {
    pub id: usize,
    pub center: (f32, f32),
    /// 1+ closed polygon rings. `components[0]` is the **primary** (largest,
    /// first-generated) continent body; `components[1..]` are satellite
    /// islands. Always at least 1 entry. Each polygon is simple
    /// (non-self-intersecting), ordered counter-clockwise around its own
    /// centre.
    pub components: Vec<Polygon>,
    /// Drift velocity (pixels-per-tick, arbitrary). Drives collision strength.
    pub velocity: (f32, f32),
    /// Voronoi sites for the plate's interior zones — [`Plate::zone_at`] assigns
    /// each interior point to its nearest site. `zone_sites.len()` = zone count.
    /// Zones span the **union** of all components; satellite islands inherit
    /// the nearest mainland zone.
    pub zone_sites: Vec<(f32, f32)>,
    /// Nested (depth-2) sub-zone Voronoi sites, indexed by L1 zone id:
    /// `subzone_sites[l1]` are the sub-sites belonging to zone `l1`.
    pub subzone_sites: Vec<Vec<(f32, f32)>>,
    /// V1 Phase A: per-plate noise seed for the [`Plate::zone_at`] domain
    /// warp (makes Voronoi seams wavy without changing site positions).
    /// Derived deterministically from the world seed + plate id.
    pub zone_warp_salt: u32,
    /// V1 Phase A v3.0: deterministic size class (Giant/Large/Medium/Small/Micro).
    /// Drives both the radius band sampled during generation and the template
    /// choice (v3.1+).
    pub size_rank: SizeRank,
    /// V1 Phase A v3.0: per-plate template-determinism seed. Each generation
    /// algorithm (v3.1 templates) seeds its randomness from this so dispatching
    /// to different templates doesn't interfere with cross-plate RNG order.
    /// Reserved for v3.1+ but populated already.
    pub shape_seed: u32,
}

impl Plate {
    /// Primary (first / largest) component polygon. Always present.
    pub fn primary(&self) -> &Polygon { &self.components[0] }

    /// Axis-aligned bounding box across **all** components: `(min_x, min_y, max_x, max_y)`.
    pub fn bounding_box(&self) -> (f32, f32, f32, f32) {
        let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
        let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
        for poly in &self.components {
            for &(x, y) in poly {
                minx = minx.min(x);
                miny = miny.min(y);
                maxx = maxx.max(x);
                maxy = maxy.max(y);
            }
        }
        (minx, miny, maxx, maxy)
    }

    /// Point-in-polygon (ray-casting), checking **every** component. Coordinates
    /// in the same pixel space as the plate's polygons.
    pub fn contains(&self, x: f32, y: f32) -> bool {
        self.components.iter().any(|poly| point_in_polygon(poly, x, y))
    }

    /// Index of the interior zone containing `(x, y)` — the nearest Voronoi
    /// site. `None` if the plate has no zones. (Does not check `contains`; the
    /// caller passes interior points.)
    ///
    /// **V1 Phase A**: applies a domain warp to `(x, y)` before the
    /// nearest-site search so zone boundaries become wavy instead of
    /// straight Voronoi edges, without moving the underlying sites
    /// (climate and adjacency code still index `zone_sites[zone_id]`
    /// directly). The warp scale is small enough vs. site spacing that no
    /// slivers form; see [`ZONE_WARP_AMP`].
    pub fn zone_at(&self, x: f32, y: f32) -> Option<usize> {
        let (qx, qy) = warped_query(x, y, self.zone_warp_salt);
        nearest_site(&self.zone_sites, qx, qy)
    }

    /// Nested (L1 zone, L2 sub-zone) indices containing `(x, y)`: the nearest
    /// L1 zone site, then the nearest sub-site **of that zone**. `None` if the
    /// plate has no zones.
    pub fn subzone_at(&self, x: f32, y: f32) -> Option<(usize, usize)> {
        let l1 = self.zone_at(x, y)?;
        let l2 = self
            .subzone_sites
            .get(l1)
            .and_then(|subs| nearest_site(subs, x, y))
            .unwrap_or(0);
        Some((l1, l2))
    }
}

/// Point-in-polygon ray-cast for a single closed ring. Returns true if `(x, y)`
/// is inside the polygon (exclusive of the boundary itself, by convention).
fn point_in_polygon(poly: &Polygon, x: f32, y: f32) -> bool {
    let n = poly.len();
    if n < 3 {
        return false;
    }
    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let (xi, yi) = poly[i];
        let (xj, yj) = poly[j];
        if (yi > y) != (yj > y) {
            let t = (y - yi) / (yj - yi);
            if x < xi + t * (xj - xi) {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

/// V1 Phase A: domain warp for [`Plate::zone_at`] queries — perturbs the
/// query position by 2D fbm so Voronoi seams render as wavy curves instead
/// of straight edges. X and Y warp use decorrelated noise (different salts
/// + offset) so the displacement is genuinely 2D, not a 1D ridge.
fn warped_query(x: f32, y: f32, salt: u32) -> (f32, f32) {
    let salt_y = salt.wrapping_add(0xDEAD_BEEF);
    let wx = crate::noise::fbm(
        x * ZONE_WARP_FREQ,
        y * ZONE_WARP_FREQ,
        salt,
        ZONE_WARP_OCTAVES,
    );
    let wy = crate::noise::fbm(
        x * ZONE_WARP_FREQ,
        y * ZONE_WARP_FREQ,
        salt_y,
        ZONE_WARP_OCTAVES,
    );
    (x + wx * ZONE_WARP_AMP, y + wy * ZONE_WARP_AMP)
}

/// Index of the nearest site to `(x, y)` (`None` if empty).
fn nearest_site(sites: &[(f32, f32)], x: f32, y: f32) -> Option<usize> {
    let mut best = None;
    let mut best_d = f32::INFINITY;
    for (i, &(sx, sy)) in sites.iter().enumerate() {
        let d = (x - sx) * (x - sx) + (y - sy) * (y - sy);
        if d < best_d {
            best_d = d;
            best = Some(i);
        }
    }
    best
}

/// A generated flat world: the rectangle + its plates. The void is implicit
/// (any point covered by zero plates).
#[derive(Debug, Clone)]
pub struct FlatWorld {
    pub width: u32,
    pub height: u32,
    pub plates: Vec<Plate>,
    /// Carried from [`FlatParams`] so [`FlatWorld::elevation_at`] is self-contained.
    pub collision_gain: f32,
}

impl FlatWorld {
    /// All plates covering a point (empty ⇒ void). Overlap ⇒ length ≥ 2.
    pub fn plates_at(&self, x: f32, y: f32) -> Vec<usize> {
        self.plates
            .iter()
            .filter(|p| p.contains(x, y))
            .map(|p| p.id)
            .collect()
    }

    /// Elevation at a point, by the plate-tectonic principle:
    /// - **void** (no plate) → [`VOID_LEVEL`];
    /// - a single plate, or non-converging plates → [`BASE_LEVEL`] (unchanged);
    /// - **overlapping, converging** plates → `BASE_LEVEL` + uplift summed over
    ///   every colliding pair, scaled by `collision_gain` (harder convergence
    ///   ⇒ higher).
    pub fn elevation_at(&self, x: f32, y: f32) -> f32 {
        let hits: Vec<&Plate> = self.plates.iter().filter(|p| p.contains(x, y)).collect();
        if hits.is_empty() {
            return VOID_LEVEL;
        }
        let mut e = BASE_LEVEL;
        for i in 0..hits.len() {
            for j in (i + 1)..hits.len() {
                e += collision_strength(hits[i], hits[j]) * self.collision_gain;
            }
        }
        e
    }
}

/// Convergence between two plates: the rate at which they close along the line
/// joining their centres. Positive ⇒ converging (uplift); ≤ 0 ⇒ diverging or
/// sliding (no uplift here — that's a rift/fault, deferred).
pub fn collision_strength(a: &Plate, b: &Plate) -> f32 {
    let dx = b.center.0 - a.center.0;
    let dy = b.center.1 - a.center.1;
    let len = (dx * dx + dy * dy).sqrt();
    if len < 1e-6 {
        return 0.0;
    }
    let (nx, ny) = (dx / len, dy / len);
    // Relative velocity of A with respect to B, projected onto A→B: if A drives
    // toward B (and/or B toward A), the projection is positive = closing.
    let vrx = a.velocity.0 - b.velocity.0;
    let vry = a.velocity.1 - b.velocity.1;
    (vrx * nx + vry * ny).max(0.0)
}

/// Generate the flat plate layout from `params`. Deterministic in `seed`.
pub fn generate(params: &FlatParams) -> FlatWorld {
    let mut rng = Rng::for_stage(params.seed, b"flatworld-plates");
    // Separate stream for motion, so adding velocities doesn't perturb the
    // polygon layout produced by the plate stream.
    let mut mrng = Rng::for_stage(params.seed, b"flatworld-motion");
    // Separate stream for interior zones — independent of layout + motion.
    let mut zrng = Rng::for_stage(params.seed, b"flatworld-zones");
    let w = params.width as f32;
    let h = params.height as f32;
    let max_v = params.max_vertices.max(params.min_vertices);

    // Spread the centres (min-separation rejection sampling) so plates meet at
    // thin seams instead of stacking. `min_sep` is `separation` × the ideal
    // grid pitch for `plate_count` blobs over the rectangle.
    let pitch = (w * h / params.plate_count.max(1) as f32).sqrt();
    let min_sep = params.separation * pitch;
    let centers = place_centers(&mut rng, w, h, params.plate_count, min_sep);

    let max_zones = params.max_zones.max(params.min_zones).max(1);

    // V1 Phase A v3.0: deterministic size-rank assignment. For the default
    // 12-plate world this is `[Giant, Large, Large, Medium×3, Small×4, Micro×2]`
    // — 120×-area-ratio diversity matching real-Earth continental landmasses.
    let size_ranks = assign_size_ranks(params.plate_count);

    let plates = centers
        .into_iter()
        .enumerate()
        .map(|(id, (cx, cy))| {
            // V1 Phase A v3.0: Pareto-style size diversity via per-rank radius
            // bands instead of one global [min_radius_frac, max_radius_frac].
            // Old `params.min/max_radius_frac` is no longer consulted (kept on
            // FlatParams for backwards struct compat; v3.1 templates can read
            // them if a particular template wants to override per-rank bands).
            let rank = size_ranks.get(id).copied().unwrap_or(SizeRank::Medium);
            let (rmin, rmax) = rank.radius_band();
            let radius = pitch * lerp(rmin, rmax, rng.next_f32());

            // V1 Phase A v3.0: anisotropic (rx, ry, theta_rot) instead of
            // scalar radius. rx · ry = radius² preserves expected area for
            // any aspect — climate-eval-stable. Most ranks slightly
            // elongated; Giant/Large/Small forced more anisotropic to
            // produce Eurasia/Italy/Korea-like shapes.
            let (amin, amax) = rank.aspect_band();
            let aspect = lerp(amin, amax, rng.next_f32());
            let rx = radius * aspect.sqrt();
            let ry = radius / aspect.sqrt();
            let theta_rot = rng.next_f32() * TAU;

            let nv = params.min_vertices
                + (rng.next_f32() * (max_v - params.min_vertices + 1) as f32) as usize;
            let nv = nv.clamp(3, max_v.max(3));

            // Even angular spokes + small per-spoke angular wobble keep the
            // ring ordered (simple polygon).
            //
            // V1 Phase A v1: multi-octave fbm noise on the radius adds the
            // organic lobes the spec wanted (low-freq → bay-scale; mid/high
            // → smaller bumps). Sampled at (cos·FREQ, sin·FREQ) so the noise
            // is naturally periodic around the perimeter.
            //
            // V1 Phase A v3.0: per-vertex computation uses ELLIPTICAL local
            // coords (rx·cos, ry·sin) then rotates by theta_rot, instead of
            // r·(cos, sin). Anisotropy makes Giant/Large plates look like
            // Eurasia (2.3:1 E-W) instead of fuzzy disks.
            //
            // Per-vertex RNG jitter is KEPT (the spec's "small residual
            // jitter for character") but scaled down by JITTER_RESIDUAL_SCALE
            // so the visual no longer reads as spiky stars at 24-48 verts;
            // `shrink_bias` compensates exactly so E[r] still equals
            // `(1 − edge_jitter/2) × radius` (the old expectation that
            // governs land:ocean ratio → climate eval composite is stable
            // within ±2pt).
            let plate_salt =
                (params.seed as u32).wrapping_mul(0x9E37_79B9) ^ (id as u32);
            let phase = rng.next_f32() * TAU;
            let cos_t = theta_rot.cos();
            let sin_t = theta_rot.sin();
            // Calibrated so E[shrink × bias] = 1 − edge_jitter/2 (preserves
            // mean polygon area despite the residual scale being < 1.0).
            let target_mean = 1.0 - params.edge_jitter * 0.5;
            let residual_mean = 1.0 - params.edge_jitter * JITTER_RESIDUAL_SCALE * 0.5;
            let shrink_bias = target_mean / residual_mean.max(1e-3);
            let primary: Polygon = (0..nv)
                .map(|k| {
                    let base = phase + TAU * (k as f32) / nv as f32;
                    let wobble = (rng.next_f32() - 0.5) * (TAU / nv as f32) * 0.6;
                    let ang = base + wobble;
                    let nx = ang.cos() * EDGE_NOISE_FREQ;
                    let ny = ang.sin() * EDGE_NOISE_FREQ;
                    let noise =
                        crate::noise::fbm(nx, ny, plate_salt, EDGE_NOISE_OCTAVES);
                    // Small per-vertex random shrink: ~3% range at default
                    // edge_jitter=0.35 → enough to give honest character,
                    // not so much that high-vertex polygons look fuzzy.
                    let residual =
                        1.0 - params.edge_jitter * JITTER_RESIDUAL_SCALE * rng.next_f32();
                    let radial_factor = shrink_bias * residual * (1.0 + EDGE_NOISE_AMP * noise);
                    // Elliptical local frame, then rotate by theta_rot.
                    let lx = rx * radial_factor * ang.cos();
                    let ly = ry * radial_factor * ang.sin();
                    (cx + lx * cos_t - ly * sin_t, cy + lx * sin_t + ly * cos_t)
                })
                .collect();

            let speed = mrng.next_f32() * params.max_speed;
            let vdir = mrng.next_f32() * TAU;
            let velocity = (speed * vdir.cos(), speed * vdir.sin());

            // V1 Phase A: per-plate domain-warp salt for `zone_at`
            // — distinct from `plate_salt` so the vertex noise and the
            // zone-seam noise don't share a hash signature.
            let zone_warp_salt =
                (params.seed as u32).wrapping_mul(0x85EB_CA6B) ^ (id as u32).wrapping_mul(0xC2B2_AE35);
            // V1 Phase A v3.0: per-plate template-determinism seed.
            // Distinct from plate_salt and zone_warp_salt so v3.1 templates
            // can run their own RNG without interfering with vertex/warp
            // noise. Populated already so the struct shape is stable.
            let shape_seed =
                (params.seed as u32).wrapping_mul(0x27D4_EB2F) ^ (id as u32).wrapping_mul(0x1656_67B1);

            let mut plate = Plate {
                id,
                center: (cx, cy),
                components: vec![primary],
                velocity,
                zone_sites: Vec::new(),
                subzone_sites: Vec::new(),
                zone_warp_salt,
                size_rank: rank,
                shape_seed,
            };
            let zone_count = params.min_zones
                + (zrng.next_f32() * (max_zones - params.min_zones + 1) as f32) as usize;
            plate.zone_sites = sample_zone_sites(&plate, zone_count.max(1), &mut zrng);

            // Depth-2: each L1 zone gets its own nested Voronoi sub-sites,
            // sampled inside the plate and filtered to that zone's cell.
            let max_sub = params.max_subzones.max(params.min_subzones).max(1);
            plate.subzone_sites = (0..plate.zone_sites.len())
                .map(|l1| {
                    let k = params.min_subzones
                        + (zrng.next_f32() * (max_sub - params.min_subzones + 1) as f32) as usize;
                    sample_subzone_sites(&plate, l1, k.max(1), &mut zrng)
                })
                .collect();
            plate
        })
        .collect();

    FlatWorld {
        width: params.width,
        height: params.height,
        plates,
        collision_gain: params.collision_gain,
    }
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Place `n` plate centres in the rectangle, rejecting any that fall within
/// `min_sep` of an already-placed centre (so plates spread out). Relaxes the
/// constraint if it can't place all centres (keeps generation total).
/// Place `n` plate centres with two-pass sampling:
///
/// **Pass 1 (y-quartile stratification):** for each of 4 horizontal strips
/// `[k·h/4, (k+1)·h/4]`, sample at least ONE centre within that strip,
/// respecting `min_sep` against earlier picks. This guarantees the world
/// spans all latitudes regardless of seed luck — the root fix for W1
/// (climate monotony from plates clustering in one lat band).
///
/// **Pass 2 (uniform fill):** sample the remaining `n - 4` centres uniformly
/// over the whole rectangle, respecting `min_sep`. If `n < 4`, the first
/// `n` strata each get one centre and pass 2 is skipped.
///
/// Both passes share the same `Rng` and the same `min_sep` constraint, so
/// the result remains fully deterministic from the seed. A final fallback
/// (unconstrained sampling) honors the plate count if `min_sep` is too
/// tight for the requested `n`.
fn place_centers(rng: &mut Rng, w: f32, h: f32, n: usize, min_sep: f32) -> Vec<(f32, f32)> {
    let mut pts: Vec<(f32, f32)> = Vec::with_capacity(n);
    let min_sep2 = min_sep * min_sep;
    const STRATA: usize = 4;

    // Pass 1: stratified — one mandatory plate per y-quartile (up to STRATA).
    let strata_to_fill = n.min(STRATA);
    for k in 0..strata_to_fill {
        let y_lo = h * (k as f32) / (STRATA as f32);
        let y_hi = h * ((k + 1) as f32) / (STRATA as f32);
        let cap = 60;
        let mut placed = false;
        for _ in 0..cap {
            let c = (rng.next_f32() * w, y_lo + rng.next_f32() * (y_hi - y_lo));
            if pts
                .iter()
                .all(|&(x, y)| (c.0 - x) * (c.0 - x) + (c.1 - y) * (c.1 - y) >= min_sep2)
            {
                pts.push(c);
                placed = true;
                break;
            }
        }
        if !placed {
            // Couldn't satisfy min_sep in this stratum — drop the constraint
            // for this one plate to keep the stratum guarantee.
            let c = (rng.next_f32() * w, y_lo + rng.next_f32() * (y_hi - y_lo));
            pts.push(c);
        }
    }

    // Pass 2: uniform fill the rest, respecting min_sep.
    let cap = (n - pts.len()) * 40;
    let mut tries = 0;
    while pts.len() < n && tries < cap {
        let c = (rng.next_f32() * w, rng.next_f32() * h);
        if pts
            .iter()
            .all(|&(x, y)| (c.0 - x) * (c.0 - x) + (c.1 - y) * (c.1 - y) >= min_sep2)
        {
            pts.push(c);
        }
        tries += 1;
    }
    // Fill any remainder unconstrained (dense layouts may not fit n spread
    // centres) so the plate count is always honoured.
    while pts.len() < n {
        pts.push((rng.next_f32() * w, rng.next_f32() * h));
    }
    pts
}

/// Rejection-sample `count` Voronoi sites inside a plate polygon (uniform over
/// its bounding box, kept if inside). Falls back to the centre if the polygon
/// is too thin to hit.
fn sample_zone_sites(plate: &Plate, count: usize, rng: &mut Rng) -> Vec<(f32, f32)> {
    let (minx, miny, maxx, maxy) = plate.bounding_box();
    let mut sites = Vec::with_capacity(count);
    let cap = count * 60;
    let mut tries = 0;
    while sites.len() < count && tries < cap {
        let x = lerp(minx, maxx, rng.next_f32());
        let y = lerp(miny, maxy, rng.next_f32());
        if plate.contains(x, y) {
            sites.push((x, y));
        }
        tries += 1;
    }
    if sites.is_empty() {
        sites.push(plate.center);
    }
    sites
}

/// Rejection-sample `count` nested sub-sites for L1 zone `l1`: points inside
/// the plate **and** whose nearest L1 site is `l1` (i.e. inside that zone's
/// Voronoi cell). Falls back to the L1 site if the cell is too thin to hit.
fn sample_subzone_sites(plate: &Plate, l1: usize, count: usize, rng: &mut Rng) -> Vec<(f32, f32)> {
    let (minx, miny, maxx, maxy) = plate.bounding_box();
    let mut sites = Vec::with_capacity(count);
    let cap = count * 120;
    let mut tries = 0;
    while sites.len() < count && tries < cap {
        let x = lerp(minx, maxx, rng.next_f32());
        let y = lerp(miny, maxy, rng.next_f32());
        if plate.contains(x, y) && plate.zone_at(x, y) == Some(l1) {
            sites.push((x, y));
        }
        tries += 1;
    }
    if sites.is_empty() {
        sites.push(plate.zone_sites.get(l1).copied().unwrap_or(plate.center));
    }
    sites
}

/// Render the flat world to an RGB byte buffer (`width * height * 3`, row-major
/// from the top-left). Void = near-black; each plate gets a distinct hue;
/// overlaps blend (averaged) so intersecting plates read as a seam.
pub fn render_rgb(world: &FlatWorld) -> Vec<u8> {
    const VOID: [u8; 3] = [10, 10, 14];
    let palette: Vec<[u8; 3]> = (0..world.plates.len())
        .map(|i| plate_color(i, world.plates.len()))
        .collect();

    let w = world.width as usize;
    let h = world.height as usize;
    let mut buf = vec![0u8; w * h * 3];
    for py in 0..h {
        for px in 0..w {
            // Sample at the pixel centre.
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            let hits = world.plates_at(x, y);
            let color = if hits.is_empty() {
                VOID
            } else {
                let mut acc = [0u32; 3];
                for &id in &hits {
                    let c = palette[id];
                    acc[0] += c[0] as u32;
                    acc[1] += c[1] as u32;
                    acc[2] += c[2] as u32;
                }
                let n = hits.len() as u32;
                [
                    (acc[0] / n) as u8,
                    (acc[1] / n) as u8,
                    (acc[2] / n) as u8,
                ]
            };
            let o = (py * w + px) * 3;
            buf[o] = color[0];
            buf[o + 1] = color[1];
            buf[o + 2] = color[2];
        }
    }
    buf
}

/// Render the elevation field to a grayscale RGB buffer on a **fixed** scale
/// (`[0,1]` → `[0,255]`, clamped): void = black, plate base = a constant grey
/// (`BASE_LEVEL`), collision belts brighter the harder the convergence — and
/// **comparable across seeds** (the same grey always means the same height).
/// Returns `(buffer, max_elevation)`; `max_elevation > 1.0` means the tallest
/// collision is clipping to white (lower `collision_gain` to bring it on-scale).
pub fn render_height_rgb(world: &FlatWorld) -> (Vec<u8>, f32) {
    let w = world.width as usize;
    let h = world.height as usize;

    let mut buf = vec![0u8; w * h * 3];
    let mut max_e = VOID_LEVEL;
    for py in 0..h {
        for px in 0..w {
            let e = world.elevation_at(px as f32 + 0.5, py as f32 + 0.5);
            if e > max_e {
                max_e = e;
            }
            let g = (e.clamp(0.0, 1.0) * 255.0).round() as u8;
            let o = (py * w + px) * 3;
            buf[o] = g;
            buf[o + 1] = g;
            buf[o + 2] = g;
        }
    }
    (buf, max_e)
}

/// Render the interior-zone subdivision: void = near-black; each plate keeps
/// its hue, and its zones are distinguished by stepped brightness/saturation
/// so the partition inside every plate is legible. In an overlap, the
/// lowest-id plate's zones are shown (stable choice — overlaps are thin now).
pub fn render_zones_rgb(world: &FlatWorld) -> Vec<u8> {
    const VOID: [u8; 3] = [10, 10, 14];
    let n = world.plates.len();
    let w = world.width as usize;
    let h = world.height as usize;
    let mut buf = vec![0u8; w * h * 3];
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            // First (lowest-id) plate covering the point owns the pixel.
            let color = match world.plates.iter().find(|p| p.contains(x, y)) {
                None => VOID,
                Some(p) => {
                    let z = p.zone_at(x, y).unwrap_or(0);
                    zone_color(p.id, n, z, p.zone_sites.len().max(1))
                }
            };
            let o = (py * w + px) * 3;
            buf[o] = color[0];
            buf[o + 1] = color[1];
            buf[o + 2] = color[2];
        }
    }
    buf
}

/// Colour for zone `z` of `n_zones` inside plate `plate_id` (of `n_plates`):
/// the plate's base hue, stepped in brightness + alternating saturation so
/// adjacent zones read as distinct patches.
fn zone_color(plate_id: usize, n_plates: usize, z: usize, n_zones: usize) -> [u8; 3] {
    let hue = (plate_id as f32 / n_plates.max(1) as f32) * 360.0;
    let t = if n_zones > 1 {
        z as f32 / (n_zones - 1) as f32
    } else {
        0.5
    };
    let val = 0.5 + 0.45 * t;
    let sat = if z % 2 == 0 { 0.7 } else { 0.45 };
    hsv_to_rgb(hue, sat, val)
}

/// Distinct, evenly-spread hue per plate (simple HSV→RGB at full S/V).
fn plate_color(i: usize, n: usize) -> [u8; 3] {
    let hue = (i as f32 / n.max(1) as f32) * 360.0;
    hsv_to_rgb(hue, 0.62, 0.92)
}

fn hsv_to_rgb(h: f32, s: f32, v: f32) -> [u8; 3] {
    let c = v * s;
    let hp = h / 60.0;
    let x = c * (1.0 - (hp % 2.0 - 1.0).abs());
    let (r, g, b) = match hp as u32 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let m = v - c;
    [
        ((r + m) * 255.0).round() as u8,
        ((g + m) * 255.0).round() as u8,
        ((b + m) * 255.0).round() as u8,
    ]
}

// ── Data export — the "anchor" for per-zone terrain generation ─────────────
//
// Mirrors the LOCKED region-tree schema at the levels built so far (plate =
// depth 0, zone = depth 1), with file/folder `path` ids. This is the data a
// future per-zone geo generator reads: each zone carries its anchor floor
// (`base_elevation`), and the partition is reproducible from the plate
// boundary + zone `site`s (Voronoi by nearest site).

/// Top-level export document.
#[derive(Debug, Clone, Serialize)]
pub struct WorldData {
    pub width: u32,
    pub height: u32,
    pub seed: u64,
    pub plate_count: usize,
    pub base_level: f32,
    pub void_level: f32,
    pub collision_gain: f32,
    pub plates: Vec<PlateData>,
}

/// A plate (region depth 0).
#[derive(Debug, Clone, Serialize)]
pub struct PlateData {
    /// File/folder path: `[plate_id]`.
    pub path: Vec<u32>,
    pub center: [f32; 2],
    /// Drift velocity — drives collision strength at boundaries.
    pub velocity: [f32; 2],
    /// V1 Phase A v3.0: list of polygon outlines. `boundaries[0]` is the
    /// primary continent; subsequent entries are satellite islands (single
    /// entry until v3.3 ships Archipelago templates).
    pub boundaries: Vec<Vec<[f32; 2]>>,
    /// V1 Phase A v3.0: deterministic size class.
    pub size_rank: &'static str,
    pub zones: Vec<ZoneData>,
}

/// A zone (region depth 1) — a Voronoi cell inside its plate.
#[derive(Debug, Clone, Serialize)]
pub struct ZoneData {
    /// File/folder path: `[plate_id, zone_id]`.
    pub path: Vec<u32>,
    /// Voronoi site (also the partition key — the cell is the points nearest it).
    pub site: [f32; 2],
    /// Anchor floor sampled at the site: `BASE_LEVEL` + any collision uplift.
    /// This is the elevation a per-zone generator builds its relief on top of.
    pub base_elevation: f32,
    /// Nested depth-2 sub-zones.
    pub subzones: Vec<SubZoneData>,
}

/// A sub-zone (region depth 2) — a nested Voronoi cell inside its L1 zone.
#[derive(Debug, Clone, Serialize)]
pub struct SubZoneData {
    /// File/folder path: `[plate_id, zone_id, subzone_id]`.
    pub path: Vec<u32>,
    pub site: [f32; 2],
}

/// Build the export document from a generated world. `seed` is recorded for
/// reproducibility (the world doesn't carry it).
pub fn export(world: &FlatWorld, seed: u64) -> WorldData {
    let plates = world
        .plates
        .iter()
        .map(|p| PlateData {
            path: vec![p.id as u32],
            center: [p.center.0, p.center.1],
            velocity: [p.velocity.0, p.velocity.1],
            boundaries: p
                .components
                .iter()
                .map(|poly| poly.iter().map(|&(x, y)| [x, y]).collect())
                .collect(),
            size_rank: p.size_rank.as_str(),
            zones: p
                .zone_sites
                .iter()
                .enumerate()
                .map(|(z, &(sx, sy))| ZoneData {
                    path: vec![p.id as u32, z as u32],
                    site: [sx, sy],
                    base_elevation: world.elevation_at(sx, sy),
                    subzones: p
                        .subzone_sites
                        .get(z)
                        .map(|subs| {
                            subs.iter()
                                .enumerate()
                                .map(|(sz, &(bx, by))| SubZoneData {
                                    path: vec![p.id as u32, z as u32, sz as u32],
                                    site: [bx, by],
                                })
                                .collect()
                        })
                        .unwrap_or_default(),
                })
                .collect(),
        })
        .collect();

    WorldData {
        width: world.width,
        height: world.height,
        seed,
        plate_count: world.plates.len(),
        base_level: BASE_LEVEL,
        void_level: VOID_LEVEL,
        collision_gain: world.collision_gain,
        plates,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn place_centers_stratifies_y_quartiles() {
        // W1 fix: y-quartile stratified placement guarantees ≥1 plate per
        // horizontal quartile, eliminating monoculture seeds where all plates
        // randomly clustered in one lat band. Verified across multiple seeds.
        for seed in [7u64, 13, 23, 42, 99, 555, 1024] {
            let p = FlatParams {
                plate_count: 7, // ≥4 so all strata fire
                seed,
                ..Default::default()
            };
            let world = generate(&p);
            let h = world.height as f32;
            let mut strata_hits = [0u32; 4];
            for plate in &world.plates {
                let k = ((plate.center.1 / h) * 4.0).floor().clamp(0.0, 3.0) as usize;
                strata_hits[k] += 1;
            }
            assert!(
                strata_hits.iter().all(|&c| c >= 1),
                "seed {seed}: y-quartiles must each have ≥1 plate, got {strata_hits:?}"
            );
        }
    }

    #[test]
    fn place_centers_fewer_than_strata_still_distributes() {
        // If plate_count < 4, can't fill all strata — should still produce
        // exactly `plate_count` plates, distributed across the first N strata.
        let p = FlatParams {
            plate_count: 2,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        assert_eq!(world.plates.len(), 2);
        let h = world.height as f32;
        let strata: std::collections::HashSet<usize> = world
            .plates
            .iter()
            .map(|pl| ((pl.center.1 / h) * 4.0).floor().clamp(0.0, 3.0) as usize)
            .collect();
        // 2 plates should land in 2 different strata (stratum 0 and stratum 1).
        assert_eq!(strata.len(), 2, "2 plates should occupy 2 distinct strata");
    }

    #[test]
    fn generates_the_requested_plate_count() {
        let p = FlatParams {
            plate_count: 7,
            ..Default::default()
        };
        let world = generate(&p);
        assert_eq!(world.plates.len(), 7);
        for plate in &world.plates {
            assert!(!plate.components.is_empty(), "plate needs ≥1 component");
            assert!(plate.primary().len() >= 3, "polygon needs ≥3 vertices");
        }
    }

    #[test]
    fn is_deterministic_in_seed() {
        let p = FlatParams::default();
        let a = generate(&p);
        let b = generate(&p);
        for (pa, pb) in a.plates.iter().zip(&b.plates) {
            assert_eq!(pa.components.len(), pb.components.len());
            for (poly_a, poly_b) in pa.components.iter().zip(&pb.components) {
                assert_eq!(poly_a.len(), poly_b.len());
                for (va, vb) in poly_a.iter().zip(poly_b) {
                    assert_eq!(va.0.to_bits(), vb.0.to_bits());
                    assert_eq!(va.1.to_bits(), vb.1.to_bits());
                }
            }
        }
    }

    #[test]
    fn distinct_seeds_differ() {
        let a = generate(&FlatParams { seed: 1, ..Default::default() });
        let b = generate(&FlatParams { seed: 2, ..Default::default() });
        let same = a
            .plates
            .iter()
            .zip(&b.plates)
            .all(|(pa, pb)| pa.center == pb.center);
        assert!(!same, "different seeds should give a different layout");
    }

    #[test]
    fn center_of_a_plate_is_inside_it() {
        let world = generate(&FlatParams::default());
        for plate in &world.plates {
            assert!(
                plate.contains(plate.center.0, plate.center.1),
                "plate {} should contain its own centre",
                plate.id
            );
        }
    }

    #[test]
    fn render_buffer_has_the_right_size() {
        let p = FlatParams {
            width: 64,
            height: 48,
            ..Default::default()
        };
        let world = generate(&p);
        assert_eq!(render_rgb(&world).len(), 64 * 48 * 3);
    }

    /// Axis-aligned square plate centred at `c` with half-size `r` and a given
    /// velocity — handy for constructing exact collision geometry.
    fn square(id: usize, c: (f32, f32), r: f32, velocity: (f32, f32)) -> Plate {
        Plate {
            id,
            center: c,
            components: vec![vec![
                (c.0 - r, c.1 - r),
                (c.0 + r, c.1 - r),
                (c.0 + r, c.1 + r),
                (c.0 - r, c.1 + r),
            ]],
            velocity,
            zone_sites: vec![c],
            subzone_sites: vec![vec![c]],
            // V1 Phase A: deterministic per-plate salt for `zone_at` warp.
            // Tests that don't care about warp can leave this at 0.
            zone_warp_salt: 0,
            // V1 Phase A v3.0: Medium rank is a neutral default for test
            // helpers (used by collision/elevation tests, not size-aware).
            size_rank: SizeRank::Medium,
            shape_seed: 0,
        }
    }

    #[test]
    fn void_is_lowest_single_plate_is_base() {
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![square(0, (50.0, 50.0), 20.0, (1.0, 0.0))],
            collision_gain: 1.0,
        };
        // Inside the lone plate → unchanged base (no collision).
        assert_eq!(world.elevation_at(50.0, 50.0), BASE_LEVEL);
        // Outside → void.
        assert_eq!(world.elevation_at(5.0, 5.0), VOID_LEVEL);
    }

    #[test]
    fn converging_overlap_rises_above_base() {
        // Two plates side by side, overlapping in the middle, driving together.
        let a = square(0, (40.0, 50.0), 25.0, (2.0, 0.0)); // moves +x (toward b)
        let b = square(1, (60.0, 50.0), 25.0, (-2.0, 0.0)); // moves -x (toward a)
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![a, b],
            collision_gain: 0.1,
        };
        // Overlap band around x=50 is covered by both → uplift.
        assert!(world.elevation_at(50.0, 50.0) > BASE_LEVEL);
        // A's exclusive interior (x≈20) is single-plate → base.
        assert_eq!(world.elevation_at(20.0, 50.0), BASE_LEVEL);
    }

    #[test]
    fn harder_convergence_is_higher() {
        let gentle = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![
                square(0, (40.0, 50.0), 25.0, (0.5, 0.0)),
                square(1, (60.0, 50.0), 25.0, (-0.5, 0.0)),
            ],
            collision_gain: 0.1,
        };
        let violent = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![
                square(0, (40.0, 50.0), 25.0, (3.0, 0.0)),
                square(1, (60.0, 50.0), 25.0, (-3.0, 0.0)),
            ],
            collision_gain: 0.1,
        };
        assert!(violent.elevation_at(50.0, 50.0) > gentle.elevation_at(50.0, 50.0));
    }

    #[test]
    fn diverging_overlap_stays_at_base() {
        // Overlapping but moving apart → no uplift (collision_strength = 0).
        let a = square(0, (40.0, 50.0), 25.0, (-2.0, 0.0)); // moves away from b
        let b = square(1, (60.0, 50.0), 25.0, (2.0, 0.0)); // moves away from a
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![a, b],
            collision_gain: 1.0,
        };
        assert_eq!(world.elevation_at(50.0, 50.0), BASE_LEVEL);
    }

    #[test]
    fn each_zone_is_subdivided_into_subzones() {
        let p = FlatParams {
            min_zones: 3,
            max_zones: 3,
            min_subzones: 2,
            max_subzones: 2,
            ..Default::default()
        };
        let world = generate(&p);
        for plate in &world.plates {
            assert_eq!(plate.subzone_sites.len(), plate.zone_sites.len());
            for (l1, subs) in plate.subzone_sites.iter().enumerate() {
                assert_eq!(subs.len(), 2, "plate {} zone {l1} subzone count", plate.id);
                // Each sub-site lies in its own L1 zone cell.
                for &(sx, sy) in subs {
                    assert_eq!(plate.zone_at(sx, sy), Some(l1));
                    let (a, _b) = plate.subzone_at(sx, sy).expect("subzone");
                    assert_eq!(a, l1);
                }
            }
        }
    }

    #[test]
    fn each_plate_is_subdivided_into_zones() {
        let p = FlatParams {
            min_zones: 4,
            max_zones: 4,
            ..Default::default()
        };
        let world = generate(&p);
        for plate in &world.plates {
            assert_eq!(plate.zone_sites.len(), 4, "plate {} zone count", plate.id);
            // Every interior site resolves to a valid zone index.
            for &(sx, sy) in &plate.zone_sites {
                let z = plate.zone_at(sx, sy).expect("site has a zone");
                assert!(z < plate.zone_sites.len());
            }
        }
    }

    #[test]
    fn separation_reduces_overlap() {
        // With strong separation, fewer pixels are covered by 2+ plates than
        // with none — plates meet at seams rather than stacking.
        let spread = generate(&FlatParams { separation: 1.1, seed: 9, ..Default::default() });
        let stacked = generate(&FlatParams { separation: 0.0, seed: 9, ..Default::default() });
        let overlap = |wld: &FlatWorld| {
            let mut n = 0u32;
            for py in (0..wld.height).step_by(4) {
                for px in (0..wld.width).step_by(4) {
                    if wld.plates_at(px as f32 + 0.5, py as f32 + 0.5).len() >= 2 {
                        n += 1;
                    }
                }
            }
            n
        };
        assert!(
            overlap(&spread) < overlap(&stacked),
            "separation should reduce overlap: spread={} stacked={}",
            overlap(&spread),
            overlap(&stacked)
        );
    }

    #[test]
    fn export_mirrors_the_tree_with_paths_and_anchors() {
        let p = FlatParams {
            plate_count: 5,
            min_zones: 3,
            max_zones: 3,
            seed: 42,
            ..Default::default()
        };
        let world = generate(&p);
        let data = export(&world, p.seed);
        assert_eq!(data.seed, 42);
        assert_eq!(data.plates.len(), 5);
        for (pi, plate) in data.plates.iter().enumerate() {
            assert_eq!(plate.path, vec![pi as u32]);
            assert_eq!(plate.zones.len(), 3);
            for (zi, zone) in plate.zones.iter().enumerate() {
                assert_eq!(zone.path, vec![pi as u32, zi as u32]);
                // Anchor floor is at least the plate base (collisions only add).
                assert!(zone.base_elevation >= BASE_LEVEL - 1e-6);
            }
        }
        // Serializes cleanly.
        let json = serde_json::to_string(&data).expect("serialize");
        assert!(json.contains("\"base_elevation\""));
    }

    // ── V1 Phase A: polygon-realism regression tests ─────────────────────

    #[test]
    fn phase_a_defaults_use_high_vertex_count() {
        // V1 Phase A: defaults bumped to 24..=48 vertices so plate outlines
        // stop looking like a child's drawing. Regression: future tweaks
        // mustn't quietly drop back to the toy-era 6..11 range.
        let p = FlatParams::default();
        assert!(p.min_vertices >= 24, "min_vertices regressed: {}", p.min_vertices);
        assert!(p.max_vertices >= 48, "max_vertices regressed: {}", p.max_vertices);
        let world = generate(&p);
        for plate in &world.plates {
            let n = plate.primary().len();
            assert!(
                n >= p.min_vertices,
                "plate {} primary has {} vertices (< min {})",
                plate.id, n, p.min_vertices,
            );
            assert!(
                n <= p.max_vertices,
                "plate {} primary has {} vertices (> max {})",
                plate.id, n, p.max_vertices,
            );
        }
    }

    #[test]
    fn phase_a_vertex_noise_keeps_centre_inside() {
        // V1 Phase A: multi-octave fbm warps each vertex radially. AMP=0.18
        // is small enough that the spoke-ordered polygon stays simple
        // (non-self-intersecting), so every plate must still contain its
        // own centre. Repeat across several seeds to catch unlucky noise.
        for seed in [1u64, 7, 13, 23, 42, 99, 555, 1024] {
            let world = generate(&FlatParams { seed, ..Default::default() });
            for plate in &world.plates {
                assert!(
                    plate.contains(plate.center.0, plate.center.1),
                    "seed {seed} plate {}: centre must stay inside post-warp",
                    plate.id,
                );
            }
        }
    }

    #[test]
    fn phase_a_zone_warp_is_deterministic() {
        // V1 Phase A: `zone_at` applies a domain warp keyed by
        // `Plate::zone_warp_salt`. Same plate + same (x, y) must yield the
        // same zone every call — otherwise climate / adjacency / hash pins
        // would jitter render-to-render.
        let world = generate(&FlatParams::default());
        let plate = &world.plates[0];
        for &(x, y) in &[(100.0_f32, 100.0_f32), (200.0, 300.0), (500.0, 250.0)] {
            let a = plate.zone_at(x, y);
            let b = plate.zone_at(x, y);
            assert_eq!(a, b, "zone_at must be deterministic at ({x}, {y})");
        }
    }

    #[test]
    fn phase_a_zone_warp_actually_perturbs_lookup() {
        // V1 Phase A: prove the warp is wired up — for a non-zero salt,
        // at least ONE query position in a dense grid must land in a
        // different zone than the unwarped (salt=0) lookup would give.
        // Otherwise the warp would be effectively dead code.
        let world = generate(&FlatParams { plate_count: 6, seed: 7, ..Default::default() });
        let plate = world
            .plates
            .iter()
            .find(|p| p.zone_sites.len() >= 4 && p.zone_warp_salt != 0)
            .expect("at least one plate with ≥4 zones and a warp salt");
        let mut differs = 0u32;
        // Sample a coarse grid covering the plate's bounding box.
        let (minx, miny, maxx, maxy) = plate.bounding_box();
        let steps = 24;
        for j in 0..steps {
            for i in 0..steps {
                let x = lerp(minx, maxx, i as f32 / (steps - 1) as f32);
                let y = lerp(miny, maxy, j as f32 / (steps - 1) as f32);
                if !plate.contains(x, y) { continue; }
                let warped = plate.zone_at(x, y);
                let plain = nearest_site(&plate.zone_sites, x, y);
                if warped != plain {
                    differs += 1;
                }
            }
        }
        assert!(
            differs > 0,
            "zone-warp didn't perturb a single lookup across {}² grid pts — warp is dead code?",
            steps,
        );
    }

    #[test]
    fn phase_a_zone_warp_salt_differs_per_plate() {
        // V1 Phase A: each plate must get its own salt — otherwise all
        // plates would share an identical noise pattern and the warp would
        // become a global shift rather than per-plate organic boundaries.
        let world = generate(&FlatParams::default());
        let salts: std::collections::HashSet<u32> =
            world.plates.iter().map(|p| p.zone_warp_salt).collect();
        assert_eq!(
            salts.len(),
            world.plates.len(),
            "all {} plates must have distinct zone_warp_salt; got {} unique",
            world.plates.len(),
            salts.len(),
        );
    }

    #[test]
    fn void_exists_with_tiny_plates() {
        // Tiny plates ⇒ lots of uncovered void.
        let p = FlatParams {
            width: 200,
            height: 200,
            plate_count: 3,
            min_radius_frac: 0.04,
            max_radius_frac: 0.06,
            ..Default::default()
        };
        let world = generate(&p);
        let mut void = 0;
        for py in 0..200 {
            for px in 0..200 {
                if world.plates_at(px as f32 + 0.5, py as f32 + 0.5).is_empty() {
                    void += 1;
                }
            }
        }
        assert!(void > 0, "small plates should leave void between them");
    }
}
