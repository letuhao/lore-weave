//! Stage 1b — plate tectonics (Phase 2 world-tier redesign).
//!
//! Replaces the single-continent radial mask with a **plate-tectonic** model:
//! seed `N` plates over the sphere, assign each cell to its nearest plate
//! (spherical Voronoi), mark each plate oceanic or continental, give each a
//! motion vector, classify every adjacent plate pair's boundary by relative
//! motion, then build a per-cell **orogeny uplift** field that raises
//! mountain belts / arcs and carves trenches / rifts along boundaries.
//!
//! The output feeds [`crate::terrain`] in `Tectonic` mode: per-cell elevation
//! = plate-kind base + uplift + (dampened) fBm texture. Multi-continent worlds
//! emerge naturally — continental plates are land, oceanic plates are sea
//! floor, and there is no forced single landmass.
//!
//! Determinism: one seeded RNG stream (`b"plates"`); every tie broken by
//! ascending id / `BoundaryKind` tag; BFS over the sorted neighbour lists.

use crate::noise::fbm_3d;
use crate::rng::{Rng, sub_seed};
use crate::world_map::{BoundaryKind, Plate, PlateBoundary, PlateKind};

// --- tuning -----------------------------------------------------------------

/// Plate-kind base elevation in a **signed space where sea level = 0** (the
/// terrain stage quantizes with the sea level pinned at the 0-crossing). This
/// mirrors Earth's hypsometry directly: continental crust is a broad platform
/// sitting *just above* sea level (vast low green plains), oceanic crust is a
/// deep floor well below. Mountains are the high minority, built by the
/// orogeny uplift + ridged relief — not a raised plateau.
const CONT_BASE: f32 = 0.10;
const OCEAN_BASE: f32 = -0.55;

/// Orogeny peak magnitudes (signed deltas, sea level = 0), decaying with hop
/// distance via [`decay`]. Continental collision (fold) belts are the big
/// highs; subduction *coastal* arcs are modest (most of Earth's coasts are
/// low passive margins, not the Andes); oceanic arcs/ridges mostly stay
/// **subsea** (occasionally breaching as island chains — realistic); rifts
/// dip a continental valley below sea (a Red-Sea-like trough).
const FOLD_PEAK: f32 = 0.85;
const ARC_PEAK: f32 = 0.55;
const TRENCH_DEPTH: f32 = 0.30;
const ISLAND_ARC_PEAK: f32 = 0.45;
const RIDGE_PEAK: f32 = 0.20;
const RIFT_DEPTH: f32 = 0.28;
const FAULT_PEAK: f32 = 0.05;

/// Orogeny decay length, in BFS hops — how far a belt reaches from its
/// boundary. Scaled mildly so larger meshes get proportionally wider belts.
const DECAY_HOPS: f32 = 4.0;

// --- S3: crustal-thickness isostasy (elevation redesign, defect D2) ----------

/// Crustal thickness in km. Oceanic crust is thin (and dense) → floats low;
/// continental crust is thick (and light) → floats high; collision thickens it
/// further (research finding #2: continental crust 10→80 km, >80 at
/// Himalaya-Tibet). Drives the isostatic base height (Airy), replacing the old
/// two-constant base.
const OCEAN_CRUST_KM: f32 = 7.0;
const CONT_CRUST_KM: f32 = 35.0;
/// Extra crust stacked at a continental collision, decaying *broadly* from the
/// convergent boundary (a wide plateau — Tibet — not a sharp ridge). Up to
/// 35 km → 70 km total.
const COLLISION_THICKEN_KM: f32 = 35.0;
/// Plateau breadth: collision thickening decays over this many BFS hops —
/// wider than the orogeny `DECAY_HOPS` so the high ground is a broad plateau,
/// with the (sharper) `uplift` ridges riding on top.
const PLATEAU_HOPS: f32 = 7.0;
/// Airy isostasy slope: signed base-height rise per km of continental crust
/// above the neutral `CONT_CRUST_KM`. Calibrated so 35 km → `CONT_BASE` (+0.10)
/// and 70 km → ~+0.40 (a broad isostatic shoulder at collisions, on top of which
/// the orogeny `uplift` + ridged relief build the sharp peaks). This is the D2
/// mechanism — the base is now crust-thickness-driven, not a flat constant.
const CONT_ISO_SLOPE: f32 = 0.30 / 35.0;

/// Shear-to-closing ratio above which a boundary is a **transform (Fault)**
/// rather than convergent/divergent. Must be `> 1`: only motion whose
/// tangential (shear) component *strongly dominates* the normal (closing /
/// opening) component is a transform; otherwise the normal component decides
/// convergent vs divergent. The old `tangential > |normal|` test (ratio 1.0)
/// labelled ~75–80 % of boundaries Fault under random plate motion, so most
/// worlds had no collisions and read as pancake-flat (S2 fix).
const FAULT_SHEAR_RATIO: f32 = 2.0;

/// Plate-boundary warp — a 3D fBm displacement applied to each cell before the
/// nearest-seed (Voronoi) test, so plate boundaries are **fractal and
/// irregular** rather than clean Voronoi arcs. This is what stops every
/// continent from being a uniform round blob: warped boundaries give
/// peninsulas, embayments, isthmuses and varied continent shapes.
const PLATE_WARP_FREQ: f32 = 1.8;
const PLATE_WARP_AMP: f32 = 0.32;
const PLATE_WARP_OCTAVES: u32 = 4;
const SALT_PWX: u32 = 0x4B1D_77A3;
const SALT_PWY: u32 = 0x9E2C_51FF;
const SALT_PWZ: u32 = 0x2D8A_C40B;

/// The plate model output.
pub struct Plates {
    /// Per-cell plate id; parallel to the mesh cells.
    pub plate_of: Vec<u32>,
    /// The plates (length == requested `plate_count`).
    pub plates: Vec<Plate>,
    /// Classified adjacent plate-pair boundaries, sorted by `(plate_a, plate_b)`.
    pub boundaries: Vec<PlateBoundary>,
    /// Per-cell crustal thickness in km (S3): oceanic thin, continental thick +
    /// collision thickening. Drives [`Plates::base`] via Airy isostasy.
    pub crust_thickness: Vec<f32>,
    /// Per-cell isostatic base elevation from the cell's crust thickness/type.
    pub base: Vec<f32>,
    /// Per-cell signed orogeny uplift (mountains/arcs positive, trenches/rifts
    /// negative).
    pub uplift: Vec<f32>,
}

/// Build the plate model. `plate_count` is clamped to `3..=24` and
/// `continental_fraction` to `0.1..=0.9` by the caller (`creative_seed`).
pub fn build(
    seed: u64,
    plate_count: u8,
    continental_fraction: f32,
    continent_latitude_spread: f32,
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
) -> Plates {
    let n_cells = centers.len();
    let n = usize::from(plate_count).clamp(3, 24);
    let mut rng = Rng::for_stage(seed, b"plates");

    // 1a — seed plate points (uniform on the sphere).
    let seeds: Vec<[f32; 3]> = (0..n).map(|_| random_unit(&mut rng)).collect();

    // 1a — assign each cell to its nearest plate seed (max dot = spherical
    // Voronoi), but **warp the cell position with a 3D fBm first** so the plate
    // boundaries are fractal/irregular (varied, non-blobby continents). Ties →
    // lower plate id (strict `>` keeps the first max).
    let wseed = sub_seed(seed, b"plate-warp") as u32;
    let plate_of: Vec<u32> = centers
        .iter()
        .map(|c| {
            let wc = warp_cell(*c, wseed);
            let mut best = 0usize;
            let mut best_dot = dot(wc, seeds[0]);
            for (p, sp) in seeds.iter().enumerate().skip(1) {
                let d = dot(wc, *sp);
                if d > best_dot {
                    best_dot = d;
                    best = p;
                }
            }
            best as u32
        })
        .collect();

    // The cell nearest each plate seed (for `Plate::seed_cell`).
    let mut seed_cell = vec![0u32; n];
    {
        let mut best_dot = vec![f32::NEG_INFINITY; n];
        for (ci, c) in centers.iter().enumerate() {
            for (p, sp) in seeds.iter().enumerate() {
                let d = dot(*c, *sp);
                if d > best_dot[p] {
                    best_dot[p] = d;
                    seed_cell[p] = ci as u32;
                }
            }
        }
    }

    // 1b — plate kinds. A seeded shuffle gives every plate a random **rank**
    // (the shuffle is kept verbatim so the RNG stream — and the motion vectors
    // drawn after it — stay byte-identical). The continental subset is then
    // chosen by `select_continental_plates`, which blends that random rank with
    // a latitude-spread term (`continent_latitude_spread`).
    let n_cont = ((n as f32) * continental_fraction).round() as usize;
    let n_cont = n_cont.clamp(1, n.saturating_sub(1).max(1));
    let mut order: Vec<usize> = (0..n).collect();
    crate::rng::shuffle(&mut rng, &mut order);
    let kind = select_continental_plates(&seeds, &order, n_cont, continent_latitude_spread);

    // 1c — plate motion: a random tangent unit vector at each plate seed.
    let motion: Vec<[f32; 3]> = seeds
        .iter()
        .map(|&sp| {
            let dir = random_unit(&mut rng);
            tangent_unit(sp, dir)
        })
        .collect();

    // 1d — boundary classification, one record per adjacent plate pair.
    let boundaries = classify_boundaries(&seeds, &kind, &motion, &plate_of, neighbors);
    // Pair → kind lookup for the per-cell uplift seeding.
    let pair_kind = |a: u32, b: u32| -> BoundaryKind {
        let (lo, hi) = if a < b { (a, b) } else { (b, a) };
        boundaries
            .iter()
            .find(|pb| pb.plate_a == lo && pb.plate_b == hi)
            .map_or(BoundaryKind::Interior, |pb| pb.kind)
    };

    // Boundary cells: a cell with ≥1 neighbour on a different plate. Each is a
    // BFS source carrying the boundary kind of its (own-plate, dominant
    // other-plate) pair. (Computed before the base — the isostasy thickening
    // reads `(boundary_kind, dist)`.)
    let (boundary_kind, dist) = boundary_field(&plate_of, neighbors, &pair_kind);

    // 1e — per-cell crust thickness (S3, D2): oceanic crust is thin; continental
    // crust is thick and **thickens further at collisions** (broad plateau,
    // wider than the orogeny belt). Drives the isostatic base height below.
    let crust_thickness: Vec<f32> = (0..n_cells)
        .map(|c| {
            let continental = kind[plate_of[c] as usize] == PlateKind::Continental;
            if !continental {
                return OCEAN_CRUST_KM;
            }
            // Collision thickening on the continental side of a convergent
            // boundary (continent–continent fold, or the overriding arc of a
            // subduction). Broad `plateau_decay` → a high plateau, not a ridge.
            let thicken = match boundary_kind[c] {
                BoundaryKind::FoldMountain | BoundaryKind::Subduction => {
                    COLLISION_THICKEN_KM * plateau_decay(dist[c])
                }
                _ => 0.0,
            };
            CONT_CRUST_KM + thicken
        })
        .collect();

    // 1f — per-cell isostatic base elevation (Airy: thicker crust floats higher),
    // replacing the old two-constant base (D2).
    let base: Vec<f32> = (0..n_cells)
        .map(|c| {
            let continental = kind[plate_of[c] as usize] == PlateKind::Continental;
            isostasy_base(crust_thickness[c], continental)
        })
        .collect();

    // 1g — per-cell orogeny uplift (the relief signal on top of the base).
    let uplift: Vec<f32> = (0..n_cells)
        .map(|c| {
            let bk = boundary_kind[c];
            if bk == BoundaryKind::Interior {
                return 0.0;
            }
            let f = decay(dist[c]);
            let cell_continental = kind[plate_of[c] as usize] == PlateKind::Continental;
            match bk {
                BoundaryKind::FoldMountain => FOLD_PEAK * f,
                BoundaryKind::Subduction => {
                    // arc rises on the continental (overriding) side; the
                    // oceanic (subducting) side gets a trench notch.
                    if cell_continental {
                        ARC_PEAK * f
                    } else {
                        -TRENCH_DEPTH * f
                    }
                }
                BoundaryKind::IslandArc => ISLAND_ARC_PEAK * f,
                BoundaryKind::Ridge => RIDGE_PEAK * f,
                BoundaryKind::Rift => -RIFT_DEPTH * f,
                BoundaryKind::Fault => FAULT_PEAK * f,
                BoundaryKind::Interior => 0.0,
            }
        })
        .collect();

    let plates: Vec<Plate> = (0..n)
        .map(|p| Plate {
            id: p as u32,
            kind: kind[p],
            motion: motion[p],
            seed_cell: seed_cell[p],
        })
        .collect();

    Plates {
        plate_of,
        plates,
        boundaries,
        crust_thickness,
        base,
        uplift,
    }
}

/// Choose which `n_cont` plates are continental, blending the random shuffle
/// **rank** with a **latitude-spread** term so continents cover a range of
/// latitudes (a full tropics → boreal/polar biome gradient) instead of
/// clustering by luck.
///
/// Greedy farthest-point selection over **signed sin-latitude** `z = seed[2] ∈
/// [−1, 1]`. Each step picks the unchosen plate minimising
/// `cost = (1 − spread)·(rank/n) − spread·min_zdist_to_chosen`, ties broken by
/// rank then id (`total_cmp`, fully deterministic).
///
/// - `spread = 0` ⇒ `cost = rank/n` ⇒ picks the shuffle order `order[0..n_cont]`
///   — **byte-identical to the legacy random selection**.
/// - `spread = 1` ⇒ `cost = −min_zdist` ⇒ farthest-point spread covering both
///   poles + the equator. Using *signed* z (not `|lat|`) guarantees the
///   climate-cold `+z` pole is covered for every hemisphere orientation, with no
///   terrain↔climate coupling.
///
/// Returns the per-plate `PlateKind` vector.
fn select_continental_plates(
    seeds: &[[f32; 3]],
    order: &[usize],
    n_cont: usize,
    spread: f32,
) -> Vec<PlateKind> {
    let n = seeds.len();
    let spread = spread.clamp(0.0, 1.0);
    // rank[p] = position of plate p in the shuffled order (0 = picked first
    // under the legacy behaviour).
    let mut rank = vec![0usize; n];
    for (i, &p) in order.iter().enumerate() {
        rank[p] = i;
    }
    let z = |p: usize| seeds[p][2];

    let mut is_cont = vec![false; n];
    let mut chosen: Vec<usize> = Vec::with_capacity(n_cont);
    for _ in 0..n_cont.min(n) {
        let cost = |p: usize| -> f32 {
            let min_d = if chosen.is_empty() {
                0.0
            } else {
                chosen
                    .iter()
                    .map(|&q| (z(p) - z(q)).abs())
                    .fold(f32::INFINITY, f32::min)
            };
            (1.0 - spread) * (rank[p] as f32 / n as f32) - spread * min_d
        };
        let pick = (0..n)
            .filter(|&p| !is_cont[p])
            .min_by(|&a, &b| {
                cost(a)
                    .total_cmp(&cost(b))
                    .then(rank[a].cmp(&rank[b]))
                    .then(a.cmp(&b))
            })
            .expect("n_cont <= n, so an unchosen plate always exists");
        is_cont[pick] = true;
        chosen.push(pick);
    }

    (0..n)
        .map(|p| {
            if is_cont[p] {
                PlateKind::Continental
            } else {
                PlateKind::Oceanic
            }
        })
        .collect()
}

/// Classify every adjacent plate pair's boundary by relative motion + kinds.
fn classify_boundaries(
    seeds: &[[f32; 3]],
    kind: &[PlateKind],
    motion: &[[f32; 3]],
    plate_of: &[u32],
    neighbors: &[Vec<u32>],
) -> Vec<PlateBoundary> {
    use std::collections::BTreeSet;
    // Adjacent unordered plate pairs (a < b).
    let mut pairs: BTreeSet<(u32, u32)> = BTreeSet::new();
    for (c, nbs) in neighbors.iter().enumerate() {
        let pa = plate_of[c];
        for &nb in nbs {
            let pb = plate_of[nb as usize];
            if pa != pb {
                pairs.insert(if pa < pb { (pa, pb) } else { (pb, pa) });
            }
        }
    }

    pairs
        .into_iter()
        .map(|(a, b)| {
            let kind = boundary_kind_for_pair(
                seeds[a as usize],
                seeds[b as usize],
                motion[a as usize],
                motion[b as usize],
                kind[a as usize],
                kind[b as usize],
            );
            PlateBoundary {
                plate_a: a,
                plate_b: b,
                kind,
            }
        })
        .collect()
}

/// Resolve the boundary kind for one plate pair from the relative motion
/// resolved along the seed-to-seed normal + the two plate kinds.
fn boundary_kind_for_pair(
    sa: [f32; 3],
    sb: [f32; 3],
    ma: [f32; 3],
    mb: [f32; 3],
    ka: PlateKind,
    kb: PlateKind,
) -> BoundaryKind {
    // Boundary normal: tangent direction from a's seed toward b's seed.
    let n = tangent_unit(sa, sub(sb, sa));
    let rel = sub(ma, mb); // relative velocity of a w.r.t. b
    let normal = dot(rel, n); // > 0 closing (convergent), < 0 opening (divergent)
    let tangential = {
        let t = sub(rel, scale(n, normal));
        len(t)
    };

    let either_continental =
        ka == PlateKind::Continental || kb == PlateKind::Continental;
    let both_continental =
        ka == PlateKind::Continental && kb == PlateKind::Continental;
    let both_oceanic = ka == PlateKind::Oceanic && kb == PlateKind::Oceanic;

    // Transform only when the shear component *strongly dominates* the normal
    // closing/opening rate (`FAULT_SHEAR_RATIO`); otherwise the normal sign
    // decides convergent vs divergent. (A plain `tangential > |normal|` test
    // mislabels most random-motion boundaries Fault → no collisions.)
    if tangential > FAULT_SHEAR_RATIO * normal.abs() {
        return BoundaryKind::Fault;
    }
    if normal > 0.0 {
        // convergent
        if both_continental {
            BoundaryKind::FoldMountain
        } else if both_oceanic {
            BoundaryKind::IslandArc
        } else {
            BoundaryKind::Subduction
        }
    } else {
        // divergent
        if either_continental {
            BoundaryKind::Rift
        } else {
            BoundaryKind::Ridge
        }
    }
}

/// Multi-source BFS from every boundary cell → per-cell `(nearest boundary
/// kind, hop distance)`. Interior cells far from any boundary stay
/// `(Interior, large)`.
fn boundary_field(
    plate_of: &[u32],
    neighbors: &[Vec<u32>],
    pair_kind: &impl Fn(u32, u32) -> BoundaryKind,
) -> (Vec<BoundaryKind>, Vec<u32>) {
    let n = plate_of.len();
    let mut bkind = vec![BoundaryKind::Interior; n];
    let mut dist = vec![u32::MAX; n];
    let mut frontier: Vec<u32> = Vec::new();

    // Seed: boundary cells (ascending id for determinism).
    for c in 0..n {
        let pa = plate_of[c];
        // dominant differing neighbour plate = the lowest-id differing plate
        // (deterministic; the per-pair kind is symmetric so the exact choice
        // only affects which kind a multi-plate-corner cell takes — resolved
        // to the lowest other-plate id, then lowest kind tag implicitly).
        let mut other: Option<u32> = None;
        for &nb in &neighbors[c] {
            let pb = plate_of[nb as usize];
            if pb != pa {
                other = Some(match other {
                    Some(o) => o.min(pb),
                    None => pb,
                });
            }
        }
        if let Some(pb) = other {
            bkind[c] = pair_kind(pa, pb);
            dist[c] = 0;
            frontier.push(c as u32);
        }
    }

    // BFS waves. First writer wins (min dist); the seed order + sorted
    // neighbours make it deterministic.
    let mut d = 0u32;
    while !frontier.is_empty() {
        let mut next: Vec<u32> = Vec::new();
        for &c in &frontier {
            for &nb in &neighbors[c as usize] {
                let nb = nb as usize;
                if dist[nb] == u32::MAX {
                    dist[nb] = d + 1;
                    bkind[nb] = bkind[c as usize];
                    next.push(nb as u32);
                }
            }
        }
        frontier = next;
        d += 1;
    }
    (bkind, dist)
}

/// Orogeny decay with hop distance: 1 at the boundary, fading to ~0 by
/// several hops. Smooth exponential-ish falloff.
fn decay(hops: u32) -> f32 {
    let t = hops as f32 / DECAY_HOPS;
    (-t * t).exp()
}

/// Broad collision-plateau decay — same shape as [`decay`] but over the wider
/// [`PLATEAU_HOPS`], so crustal thickening forms a broad high plateau rather
/// than tracing the (narrower) orogeny ridge.
fn plateau_decay(hops: u32) -> f32 {
    let t = hops as f32 / PLATEAU_HOPS;
    (-t * t).exp()
}

/// Airy isostatic base height (signed, sea = 0) for a crust column: thicker
/// continental crust floats higher (the mechanism behind high collision
/// plateaus with no trench). Oceanic crust is uniform here — its depth varies
/// by lithospheric *age*, deferred to S4. Calibrated so oceanic 7 km →
/// `OCEAN_BASE`, continental 35 km → `CONT_BASE`, 70 km → ~+0.40.
fn isostasy_base(thickness_km: f32, continental: bool) -> f32 {
    if continental {
        CONT_BASE + CONT_ISO_SLOPE * (thickness_km - CONT_CRUST_KM)
    } else {
        OCEAN_BASE
    }
}

// --- vector helpers ---------------------------------------------------------

/// Displace a unit-sphere cell position by a 3D fBm field, re-normalized back
/// onto the sphere — the plate-boundary warp (fractal, irregular continents).
fn warp_cell(c: [f32; 3], seed: u32) -> [f32; 3] {
    let f = PLATE_WARP_FREQ;
    let wx = fbm_3d(c[0] * f, c[1] * f, c[2] * f, seed ^ SALT_PWX, PLATE_WARP_OCTAVES);
    let wy = fbm_3d(c[0] * f, c[1] * f, c[2] * f, seed ^ SALT_PWY, PLATE_WARP_OCTAVES);
    let wz = fbm_3d(c[0] * f, c[1] * f, c[2] * f, seed ^ SALT_PWZ, PLATE_WARP_OCTAVES);
    let v = [
        c[0] + PLATE_WARP_AMP * wx,
        c[1] + PLATE_WARP_AMP * wy,
        c[2] + PLATE_WARP_AMP * wz,
    ];
    let l = len(v).max(1e-6);
    [v[0] / l, v[1] / l, v[2] / l]
}

/// A uniform random point on the unit sphere (Marsaglia z + azimuth).
fn random_unit(rng: &mut Rng) -> [f32; 3] {
    let z = 2.0 * rng.next_f32() - 1.0;
    let theta = std::f32::consts::TAU * rng.next_f32();
    let r = (1.0 - z * z).max(0.0).sqrt();
    [r * theta.cos(), r * theta.sin(), z]
}

/// The component of `dir` tangent to the sphere at unit point `p`, normalized.
/// Falls back to an arbitrary tangent if `dir` is (nearly) parallel to `p`.
fn tangent_unit(p: [f32; 3], dir: [f32; 3]) -> [f32; 3] {
    let d = dot(dir, p);
    let t = sub(dir, scale(p, d));
    let l = len(t);
    if l > 1e-6 {
        [t[0] / l, t[1] / l, t[2] / l]
    } else {
        // dir ∥ p — pick any tangent via the least-aligned axis.
        let helper = if p[0].abs() <= p[1].abs() && p[0].abs() <= p[2].abs() {
            [1.0, 0.0, 0.0]
        } else if p[1].abs() <= p[2].abs() {
            [0.0, 1.0, 0.0]
        } else {
            [0.0, 0.0, 1.0]
        };
        let t = sub(helper, scale(p, dot(helper, p)));
        let l = len(t).max(1e-6);
        [t[0] / l, t[1] / l, t[2] / l]
    }
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
fn sub(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn scale(a: [f32; 3], s: f32) -> [f32; 3] {
    [a[0] * s, a[1] * s, a[2] * s]
}
fn len(a: [f32; 3]) -> f32 {
    dot(a, a).sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mesh;
    use crate::creative_seed::WorldScale;

    fn pocket() -> (Vec<[f32; 3]>, Vec<Vec<u32>>) {
        let m = mesh::build(42, WorldScale::Pocket);
        (m.centers, m.neighbors)
    }

    #[test]
    fn every_cell_assigned_a_valid_plate() {
        let (centers, neighbors) = pocket();
        let p = build(42, 8, 0.4, 0.0, &centers, &neighbors);
        assert_eq!(p.plate_of.len(), centers.len());
        assert!(p.plate_of.iter().all(|&id| (id as usize) < p.plates.len()));
        assert_eq!(p.plates.len(), 8);
    }

    #[test]
    fn continental_count_matches_fraction() {
        let (centers, neighbors) = pocket();
        let p = build(42, 10, 0.4, 0.0, &centers, &neighbors);
        let cont = p
            .plates
            .iter()
            .filter(|pl| pl.kind == PlateKind::Continental)
            .count();
        assert_eq!(cont, 4, "round(10 * 0.4) = 4 continental plates");
    }

    #[test]
    fn plate_count_is_clamped() {
        let (centers, neighbors) = pocket();
        assert_eq!(build(1, 2, 0.4, 0.0, &centers, &neighbors).plates.len(), 3);
        assert_eq!(build(1, 99, 0.4, 0.0, &centers, &neighbors).plates.len(), 24);
    }

    #[test]
    fn motion_vectors_are_unit_and_tangent() {
        let (centers, neighbors) = pocket();
        let p = build(7, 8, 0.4, 0.0, &centers, &neighbors);
        for pl in &p.plates {
            let m = pl.motion;
            let l = (m[0] * m[0] + m[1] * m[1] + m[2] * m[2]).sqrt();
            assert!((l - 1.0).abs() < 1e-3, "motion not unit: {l}");
            let sp = centers[pl.seed_cell as usize];
            let radial = m[0] * sp[0] + m[1] * sp[1] + m[2] * sp[2];
            // tangent at the seed *point*; seed_cell is the nearest cell, so a
            // small radial component is OK — just bound it.
            assert!(radial.abs() < 0.4, "motion not ~tangent: radial {radial}");
        }
    }

    #[test]
    fn boundaries_are_sorted_and_classified() {
        let (centers, neighbors) = pocket();
        let p = build(42, 8, 0.4, 0.0, &centers, &neighbors);
        assert!(!p.boundaries.is_empty(), "8 plates must share boundaries");
        for w in p.boundaries.windows(2) {
            assert!(
                (w[0].plate_a, w[0].plate_b) < (w[1].plate_a, w[1].plate_b),
                "boundaries not strictly sorted"
            );
        }
        for b in &p.boundaries {
            assert!(b.plate_a < b.plate_b);
            assert_ne!(b.kind, BoundaryKind::Interior);
        }
    }

    #[test]
    fn uplift_is_finite_and_zero_in_deep_interior() {
        let (centers, neighbors) = pocket();
        let p = build(42, 8, 0.4, 0.0, &centers, &neighbors);
        assert!(p.uplift.iter().all(|u| u.is_finite()));
        // at least some cells get non-zero uplift (boundaries exist).
        assert!(p.uplift.iter().any(|&u| u.abs() > 0.01));
    }

    /// Six plates on a meridian with distinct, evenly-spaced signed latitudes
    /// `z = −0.8..0.7`, and a fixed (non-identity) shuffle order.
    fn meridian_seeds() -> (Vec<[f32; 3]>, Vec<usize>) {
        let seeds: Vec<[f32; 3]> = (0..6)
            .map(|i| {
                let z = -0.8 + i as f32 * 0.3;
                let r = (1.0 - z * z).sqrt();
                [r, 0.0, z]
            })
            .collect();
        (seeds, vec![3usize, 1, 5, 0, 4, 2])
    }

    #[test]
    fn spread_zero_picks_the_shuffle_order() {
        // spread=0 ⇒ continental = the first n_cont of the shuffle order
        // ({3,1,5}) — byte-identical to the legacy `order.take(n_cont)`.
        let (seeds, order) = meridian_seeds();
        let kinds = select_continental_plates(&seeds, &order, 3, 0.0);
        let cont: Vec<usize> = (0..6)
            .filter(|&p| kinds[p] == PlateKind::Continental)
            .collect();
        assert_eq!(cont, vec![1, 3, 5], "spread=0 must equal shuffle order {{3,1,5}}");
    }

    #[test]
    fn spread_one_covers_the_latitude_extremes() {
        let (seeds, order) = meridian_seeds();
        let zr = |kinds: &[PlateKind]| -> f32 {
            let zs: Vec<f32> = (0..6)
                .filter(|&p| kinds[p] == PlateKind::Continental)
                .map(|p| seeds[p][2])
                .collect();
            zs.iter().cloned().fold(f32::MIN, f32::max)
                - zs.iter().cloned().fold(f32::MAX, f32::min)
        };
        let lo = select_continental_plates(&seeds, &order, 3, 0.0);
        let hi = select_continental_plates(&seeds, &order, 3, 1.0);
        // Farthest-point spread widens the latitude range...
        assert!(zr(&hi) > zr(&lo), "spread=1 range {} !> spread=0 range {}", zr(&hi), zr(&lo));
        // ...and includes both extreme-latitude plates (0 = z−0.8, 5 = z+0.7).
        assert_eq!(hi[0], PlateKind::Continental, "spread=1 must take the −0.8 pole plate");
        assert_eq!(hi[5], PlateKind::Continental, "spread=1 must take the +0.7 pole plate");
    }

    #[test]
    fn spread_one_is_deterministic() {
        let (seeds, order) = meridian_seeds();
        let a = select_continental_plates(&seeds, &order, 3, 1.0);
        let b = select_continental_plates(&seeds, &order, 3, 1.0);
        assert_eq!(a, b);
    }

    #[test]
    fn deterministic() {
        let (centers, neighbors) = pocket();
        let a = build(99, 8, 0.4, 0.0, &centers, &neighbors);
        let b = build(99, 8, 0.4, 0.0, &centers, &neighbors);
        assert_eq!(a.plate_of, b.plate_of);
        assert_eq!(a.boundaries, b.boundaries);
        for i in 0..a.uplift.len() {
            assert_eq!(a.uplift[i].to_bits(), b.uplift[i].to_bits());
            assert_eq!(a.crust_thickness[i].to_bits(), b.crust_thickness[i].to_bits());
        }
    }

    /// S3 — crust thickness splits ocean (thin) vs continent (thick), and
    /// continental crust never exceeds the neutral + collision-thickening cap.
    #[test]
    fn crust_thickness_splits_ocean_and_continent() {
        let (centers, neighbors) = pocket();
        let p = build(7, 8, 0.4, 0.0, &centers, &neighbors);
        assert_eq!(p.crust_thickness.len(), centers.len());
        let (mut thin, mut thick) = (0u32, 0u32);
        for (c, &t) in p.crust_thickness.iter().enumerate() {
            assert!(t.is_finite(), "crust thickness not finite at {c}");
            match p.plates[p.plate_of[c] as usize].kind {
                PlateKind::Oceanic => {
                    assert!((t - OCEAN_CRUST_KM).abs() < 1e-3, "oceanic crust {t} != {OCEAN_CRUST_KM}");
                    thin += 1;
                }
                PlateKind::Continental => {
                    assert!(
                        (CONT_CRUST_KM - 1e-3..=CONT_CRUST_KM + COLLISION_THICKEN_KM + 1e-3)
                            .contains(&t),
                        "continental crust {t} out of [{CONT_CRUST_KM}, {}]",
                        CONT_CRUST_KM + COLLISION_THICKEN_KM
                    );
                    thick += 1;
                }
            }
        }
        assert!(thin > 0 && thick > 0, "crust thickness not split ocean/continent");
    }

    /// S3 — isostasy: thicker continental crust floats strictly higher; oceanic
    /// crust sits at `OCEAN_BASE`; the calibration anchors hold.
    #[test]
    fn isostasy_base_rises_with_thickness() {
        assert!((isostasy_base(OCEAN_CRUST_KM, false) - OCEAN_BASE).abs() < 1e-6);
        assert!((isostasy_base(CONT_CRUST_KM, true) - CONT_BASE).abs() < 1e-6);
        // Tibet-thick crust floats well above the normal platform.
        let thick = isostasy_base(CONT_CRUST_KM + COLLISION_THICKEN_KM, true);
        assert!(thick > CONT_BASE + 0.2, "70km crust base {thick} not a plateau");
        assert!(thick > isostasy_base(CONT_CRUST_KM + 1.0, true), "isostasy not monotonic");
    }
}
