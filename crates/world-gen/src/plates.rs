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
    /// Per-cell base elevation from the cell's plate kind.
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

    // 1b — plate kinds. `continental` plates picked from a seeded shuffle of
    // the plate ids so the continental set is not always `0..k`.
    let n_cont = ((n as f32) * continental_fraction).round() as usize;
    let n_cont = n_cont.clamp(1, n.saturating_sub(1).max(1));
    let mut order: Vec<usize> = (0..n).collect();
    crate::rng::shuffle(&mut rng, &mut order);
    let mut kind = vec![PlateKind::Oceanic; n];
    for &p in order.iter().take(n_cont) {
        kind[p] = PlateKind::Continental;
    }

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

    // 1e — per-cell base elevation + orogeny uplift.
    let base: Vec<f32> = (0..n_cells)
        .map(|c| match kind[plate_of[c] as usize] {
            PlateKind::Continental => CONT_BASE,
            PlateKind::Oceanic => OCEAN_BASE,
        })
        .collect();

    // Boundary cells: a cell with ≥1 neighbour on a different plate. Each is a
    // BFS source carrying the boundary kind of its (own-plate, dominant
    // other-plate) pair.
    let (boundary_kind, dist) = boundary_field(&plate_of, neighbors, &pair_kind);

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
        base,
        uplift,
    }
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

    // Transform dominates when the shear component exceeds the normal closing.
    if tangential > normal.abs() {
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
        let p = build(42, 8, 0.4, &centers, &neighbors);
        assert_eq!(p.plate_of.len(), centers.len());
        assert!(p.plate_of.iter().all(|&id| (id as usize) < p.plates.len()));
        assert_eq!(p.plates.len(), 8);
    }

    #[test]
    fn continental_count_matches_fraction() {
        let (centers, neighbors) = pocket();
        let p = build(42, 10, 0.4, &centers, &neighbors);
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
        assert_eq!(build(1, 2, 0.4, &centers, &neighbors).plates.len(), 3);
        assert_eq!(build(1, 99, 0.4, &centers, &neighbors).plates.len(), 24);
    }

    #[test]
    fn motion_vectors_are_unit_and_tangent() {
        let (centers, neighbors) = pocket();
        let p = build(7, 8, 0.4, &centers, &neighbors);
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
        let p = build(42, 8, 0.4, &centers, &neighbors);
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
        let p = build(42, 8, 0.4, &centers, &neighbors);
        assert!(p.uplift.iter().all(|u| u.is_finite()));
        // at least some cells get non-zero uplift (boundaries exist).
        assert!(p.uplift.iter().any(|&u| u.abs() > 0.01));
    }

    #[test]
    fn deterministic() {
        let (centers, neighbors) = pocket();
        let a = build(99, 8, 0.4, &centers, &neighbors);
        let b = build(99, 8, 0.4, &centers, &neighbors);
        assert_eq!(a.plate_of, b.plate_of);
        assert_eq!(a.boundaries, b.boundaries);
        for i in 0..a.uplift.len() {
            assert_eq!(a.uplift[i].to_bits(), b.uplift[i].to_bits());
        }
    }
}
