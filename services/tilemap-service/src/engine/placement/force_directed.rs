//! TMP_002 §3.2–§3.3 — Fruchterman-Reingold force-directed convergence.
//!
//! Takes the §3.1 grid-seed layout and relaxes it: connected zones attract
//! (FR spring force `d²/k`), every zone pair repels (`k²/d`), `Adversarial`
//! edges add extra repulsion regardless of distance, and zones near the
//! unit-square boundary are pushed inward. Exponential simulated annealing
//! (Kirkpatrick, Gelatt & Vecchi 1983) caps per-iteration movement; a
//! misplaced-zone swap (§3.3, tabu-guarded — Glover 1990) escapes local minima.
//!
//! **Determinism (TMP-A4):** the only RNG is a small symmetry-breaking jitter
//! applied once to the grid seed, drawn from the `"force_directed"` sub-stream
//! ([`sub_seed`]). FR itself is a fixed sequence of `f64` ops (spec D4), single
//! threaded — replays are bit-identical. Cap handling splits by which cap trips
//! (spec D5): the **iteration cap** is seed-deterministic, so it returns the FR
//! best-found layout (the work is kept); the **wall-clock cap** is machine-
//! dependent, so it falls back to the grid-seed layout (TMP-PLACE-Q2) — a pure
//! function of the template — and never feeds a non-deterministic layout out.

use std::cmp::Ordering;
use std::collections::HashMap;
use std::time::{Duration, Instant};

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::seed::{TilemapSeed, sub_seed};
use crate::types::template::TilemapTemplate;
use crate::types::zone::PassageKind;

use super::{PlacedZone, Vec2};

/// Initial annealing temperature — also the per-iteration movement cap, in
/// normalized `[0,1]` units. 0.10 lets a zone cross 10 % of the map per step.
const T_INITIAL: f64 = 0.10;
/// Annealing floor — once the temperature cools below this the layout is
/// declared converged (moves are sub-pixel at any practical grid size).
const T_MINIMUM: f64 = 1.0e-4;
/// Exponential cooling factor applied on every no-improvement iteration
/// (TMP_002 §3.2 — exponential, not FR's original linear schedule).
const COOLING_FACTOR: f64 = 0.97;
/// Zones within this fraction of an edge get an inward boundary push.
const BOUNDARY_MARGIN: f64 = 0.05;
/// Gain on the boundary push so it is comparable to the FR forces.
const BOUNDARY_GAIN: f64 = 4.0;
/// Extra repulsion multiplier on `Adversarial` edges (§3.2).
const ADVERSARIAL_STRENGTH: f64 = 2.0;
/// Symmetry-breaking jitter magnitude, as a fraction of the optimal distance
/// `k`. The regular grid seed is highly symmetric; a tiny seed-derived nudge
/// breaks exact force ties so FR settles cleanly.
const JITTER_FRACTION: f64 = 0.20;
/// Distance floor guarding force divisions against coincident zones.
const MIN_DIST: f64 = 1.0e-4;
/// Improvement threshold — a fitness gain smaller than this counts as "no
/// improvement" (stops float noise from blocking convergence forever).
const EPSILON: f64 = 1.0e-9;

/// Undirected edges as zone-index pairs, each normalized `(lo, hi)`.
type EdgeList = Vec<(usize, usize)>;

/// Convergence caps (spec D5 / TMP_002 §3.2 / TMP-Q5).
#[derive(Debug, Clone, Copy)]
pub struct ConvergenceCaps {
    /// Hard iteration cap (TMP-Q5 default 1000). Seed-deterministic — on trip
    /// the engine keeps the FR best-found layout.
    pub max_iterations: u32,
    /// Wall-clock cap (TMP-Q5 default 5 s). Machine-dependent — on trip the
    /// engine falls back to the grid-seed layout, the only choice that keeps
    /// the output deterministic across machines.
    pub max_wall_clock: Duration,
    /// Consecutive no-improvement iterations that declare convergence.
    pub no_improvement_limit: u32,
}

impl Default for ConvergenceCaps {
    fn default() -> Self {
        Self {
            max_iterations: 1000,
            max_wall_clock: Duration::from_secs(5),
            no_improvement_limit: 50,
        }
    }
}

/// Outcome of [`force_directed_converge`].
#[derive(Debug, Clone)]
pub struct ConvergenceResult {
    /// The placed zones. On convergence or an iteration-cap trip these are the
    /// FR best-found layout; on a wall-clock-cap trip, the grid-seed layout.
    pub zones: Vec<PlacedZone>,
    /// Iterations actually run (metadata only — never feeds the tilemap).
    pub iteration_count: u32,
    /// `true` if FR settled; `false` if either cap was hit (spec D5).
    pub converged: bool,
}

/// Relax `seed_layout` (the §3.1 grid seed) via Fruchterman-Reingold.
///
/// Never errors: hitting either cap falls back to the grid-seed layout with
/// `converged: false` (spec D5).
pub fn force_directed_converge(
    seed_layout: Vec<PlacedZone>,
    template: &TilemapTemplate,
    seed: TilemapSeed,
    caps: ConvergenceCaps,
) -> ConvergenceResult {
    let n = seed_layout.len();
    if n < 2 {
        // Nothing to relax — 0 or 1 zone is trivially placed.
        return ConvergenceResult {
            zones: seed_layout,
            iteration_count: 0,
            converged: true,
        };
    }

    let k = (1.0 / n as f64).sqrt();
    let (prox, adv) = classify_edges(template, &seed_layout);
    let radii = zone_radii(&seed_layout, k);

    // Jitter the grid seed once to break the lattice symmetry — the only RNG
    // in FR (see module docs). Drawn from the `"force_directed"` sub-stream.
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(seed, "force_directed"));
    let jitter = k * JITTER_FRACTION;
    let mut current: Vec<Vec2> = seed_layout
        .iter()
        .map(|z| {
            let jx = rng.random_range(-jitter..=jitter);
            let jy = rng.random_range(-jitter..=jitter);
            clamp_unit(Vec2::new(z.pos.x + jx, z.pos.y + jy))
        })
        .collect();

    let mut best = current.clone();
    let mut best_fitness = fitness(&best, &prox, &radii, k);
    let mut temperature = T_INITIAL;
    let mut no_improvement = 0u32;
    let mut iteration_count = 0u32;
    let mut tabu: Vec<usize> = Vec::new();
    let start = Instant::now();

    let outcome = loop {
        if no_improvement >= caps.no_improvement_limit || temperature <= T_MINIMUM {
            break Outcome::Converged;
        }
        // Check the iteration cap before the wall-clock cap: a run that
        // legitimately reaches it is seed-deterministic and must never be
        // mis-attributed to the machine-dependent wall-clock path.
        if iteration_count >= caps.max_iterations {
            break Outcome::IterationCap;
        }
        if start.elapsed() >= caps.max_wall_clock {
            break Outcome::WallClockCap;
        }

        fr_step(&mut current, &prox, &adv, k, temperature);
        iteration_count += 1;

        let f = fitness(&current, &prox, &radii, k);
        if f + EPSILON < best_fitness {
            best_fitness = f;
            best.copy_from_slice(&current);
            no_improvement = 0;
            tabu.clear();
        } else {
            no_improvement += 1;
            // Drastic move to escape the local minimum, then cool (§3.2-§3.3).
            try_drastic_swap(&mut current, &prox, &radii, k, &mut tabu);
            temperature *= COOLING_FACTOR;
        }
    };

    // Spec D5: convergence and the seed-deterministic iteration cap both keep
    // the FR best-found layout; only the machine-dependent wall-clock cap falls
    // back to the grid seed (TMP-PLACE-Q2) so the output stays deterministic.
    let (zones, converged) = match outcome {
        Outcome::Converged => (apply_positions(seed_layout, &best), true),
        Outcome::IterationCap => (apply_positions(seed_layout, &best), false),
        Outcome::WallClockCap => {
            // The wall-clock cap is machine-dependent — a slow machine can
            // trip it where a fast one would converge, so the grid-seed
            // fallback can differ across machines for the same seed. The
            // fallback itself is silent in the output; surface it in logs so
            // a production divergence is observable (spec D5 residual caveat
            // / DEFERRED #015). The ops-dashboard event is deferred to Phase 2.
            tracing::warn!(
                iteration_count,
                "force-directed convergence hit the wall-clock cap — falling \
                 back to the grid-seed layout; this layout is NOT guaranteed \
                 identical across machines for the same seed (DEFERRED #015)"
            );
            (seed_layout, false)
        }
    };
    ConvergenceResult {
        zones,
        iteration_count,
        converged,
    }
}

/// Why [`force_directed_converge`]'s annealing loop stopped.
#[derive(Debug)]
enum Outcome {
    /// FR settled — no-improvement limit or temperature floor reached.
    Converged,
    /// Hit the iteration cap (seed-deterministic) — keep the FR best layout.
    IterationCap,
    /// Hit the wall-clock cap (machine-dependent) — fall back to the grid seed.
    WallClockCap,
}

/// One FR iteration: accumulate repulsive + attractive + boundary forces, then
/// move each zone by its capped displacement.
fn fr_step(pos: &mut [Vec2], prox: &[(usize, usize)], adv: &[(usize, usize)], k: f64, temp: f64) {
    let n = pos.len();
    let mut disp = vec![Vec2::new(0.0, 0.0); n];

    // Repulsion between every zone pair — FR `k²/d`.
    for i in 0..n {
        for j in (i + 1)..n {
            let (u, d) = pair_offset(pos[i], pos[j]);
            let push = u.scale(k * k / d.max(MIN_DIST));
            disp[i] = disp[i] - push;
            disp[j] = disp[j] + push;
        }
    }
    // Attraction along proximity edges — FR `d²/k`.
    for &(i, j) in prox {
        let (u, d) = pair_offset(pos[i], pos[j]);
        let pull = u.scale(d * d / k);
        disp[i] = disp[i] + pull;
        disp[j] = disp[j] - pull;
    }
    // Adversarial edges add extra repulsion regardless of distance (§3.2).
    for &(i, j) in adv {
        let (u, d) = pair_offset(pos[i], pos[j]);
        let push = u.scale(k * k / d.max(MIN_DIST) * ADVERSARIAL_STRENGTH);
        disp[i] = disp[i] - push;
        disp[j] = disp[j] + push;
    }
    // Boundary repulsion + capped move.
    for i in 0..n {
        let total = disp[i] + boundary_force(pos[i]);
        pos[i] = clamp_unit(pos[i] + cap_magnitude(total, temp));
    }
}

/// §3.3 — when an iteration fails to improve, swap the two worst-placed,
/// mutually-unconnected zones (escape the local minimum). The `tabu` set holds
/// the previous swap's zones so no zone is swapped twice in a row (Glover
/// 1990). When no valid swap exists, nudge the single worst zone instead.
fn try_drastic_swap(
    pos: &mut [Vec2],
    prox: &[(usize, usize)],
    radii: &[f64],
    k: f64,
    tabu: &mut Vec<usize>,
) {
    let n = pos.len();
    if n < 2 {
        return;
    }
    let score = misplacement(pos, prox, radii, k);

    // Zones ranked worst-first; score ties break to the lower index so the
    // heuristic is fully deterministic.
    let mut ranked: Vec<usize> = (0..n).collect();
    ranked.sort_by(|&a, &b| {
        score[b]
            .partial_cmp(&score[a])
            .unwrap_or(Ordering::Equal)
            .then(a.cmp(&b))
    });

    let Some(&worst) = ranked.iter().find(|i| !tabu.contains(i)) else {
        return;
    };
    if score[worst] <= EPSILON {
        return; // nothing is meaningfully misplaced
    }

    // Prefer swapping with another misplaced, non-tabu, unconnected zone.
    let partner = ranked.iter().copied().find(|&v| {
        v != worst && !tabu.contains(&v) && score[v] > EPSILON && !edge_exists(prox, worst, v)
    });

    match partner {
        Some(other) => {
            pos.swap(worst, other);
            *tabu = vec![worst, other];
        }
        None => {
            nudge_worst(pos, prox, k, worst);
            *tabu = vec![worst];
        }
    }
}

/// Move `worst` toward the centroid of its connected zones (reduce distance
/// excess); if it has no connections, away from its nearest zone (reduce
/// overlap). Step length is half the optimal distance `k`.
fn nudge_worst(pos: &mut [Vec2], prox: &[(usize, usize)], k: f64, worst: usize) {
    let neighbours: Vec<usize> = prox
        .iter()
        .filter_map(|&(a, b)| match (a == worst, b == worst) {
            (true, _) => Some(b),
            (_, true) => Some(a),
            _ => None,
        })
        .collect();
    let step = k * 0.5;

    let dir = if let Some(target) = centroid(pos, &neighbours) {
        target - pos[worst] // toward connected zones
    } else if let Some(z) = nearest_other(pos, worst) {
        pos[worst] - pos[z] // away from nearest zone
    } else {
        return;
    };
    let mag = dir.magnitude();
    if mag > MIN_DIST {
        pos[worst] = clamp_unit(pos[worst] + dir.scale(step / mag));
    }
}

/// FR fitness — `(distance_excess + 1) * (overlap + 1)` (§3.2 step 4). Lower is
/// better. `distance_excess` sums how far connected zones exceed `k`; `overlap`
/// sums how far zone soft-spheres interpenetrate.
fn fitness(pos: &[Vec2], prox: &[(usize, usize)], radii: &[f64], k: f64) -> f64 {
    let mut excess = 0.0;
    for &(i, j) in prox {
        let d = pos[i].distance(pos[j]);
        if d > k {
            excess += d - k;
        }
    }
    let mut overlap = 0.0;
    let n = pos.len();
    for i in 0..n {
        for j in (i + 1)..n {
            let d = pos[i].distance(pos[j]);
            let min_d = radii[i] + radii[j];
            if d < min_d {
                overlap += min_d - d;
            }
        }
    }
    (excess + 1.0) * (overlap + 1.0)
}

/// Per-zone misplacement — connected-distance excess + soft-sphere overlap.
/// Used by the §3.3 swap heuristic to rank the worst-placed zones.
fn misplacement(pos: &[Vec2], prox: &[(usize, usize)], radii: &[f64], k: f64) -> Vec<f64> {
    let n = pos.len();
    let mut s = vec![0.0; n];
    for &(i, j) in prox {
        let d = pos[i].distance(pos[j]);
        if d > k {
            let e = d - k;
            s[i] += e;
            s[j] += e;
        }
    }
    for i in 0..n {
        for j in (i + 1)..n {
            let d = pos[i].distance(pos[j]);
            let min_d = radii[i] + radii[j];
            if d < min_d {
                let o = min_d - d;
                s[i] += o;
                s[j] += o;
            }
        }
    }
    s
}

/// Soft-sphere radii — radius ∝ `sqrt(size)`, normalized so an average-size
/// zone has radius `k/2` (two average zones touch at exactly `k`).
fn zone_radii(layout: &[PlacedZone], k: f64) -> Vec<f64> {
    let sqrt_sizes: Vec<f64> = layout.iter().map(|z| (z.size as f64).sqrt()).collect();
    let total: f64 = sqrt_sizes.iter().sum();
    if total <= MIN_DIST {
        return vec![0.0; layout.len()];
    }
    let avg = total / layout.len() as f64;
    sqrt_sizes.iter().map(|&s| k * 0.5 * s / avg).collect()
}

/// Extract undirected proximity + adversarial edges as index pairs into the
/// zone-id-ordered `layout`. Each edge is normalized `(lo, hi)`; both vectors
/// are sorted + deduped so iteration order is deterministic. `Portal` edges
/// impose no spatial constraint and are dropped (mirrors §3.1 / `grid_seed`).
fn classify_edges(template: &TilemapTemplate, layout: &[PlacedZone]) -> (EdgeList, EdgeList) {
    let index: HashMap<&str, usize> = layout
        .iter()
        .enumerate()
        .map(|(i, z)| (z.id.0.as_str(), i))
        .collect();

    let mut prox = Vec::new();
    let mut adv = Vec::new();
    for spec in &template.zones {
        let Some(&a) = index.get(spec.zone_id.0.as_str()) else {
            continue;
        };
        for conn in &spec.connections {
            let Some(&b) = index.get(conn.to_zone.0.as_str()) else {
                continue;
            };
            if a == b {
                continue;
            }
            let edge = if a < b { (a, b) } else { (b, a) };
            match conn.kind {
                PassageKind::Threshold | PassageKind::Open | PassageKind::Hint => prox.push(edge),
                PassageKind::Adversarial => adv.push(edge),
                PassageKind::Portal => {}
            }
        }
    }
    prox.sort_unstable();
    prox.dedup();
    adv.sort_unstable();
    adv.dedup();
    (prox, adv)
}

/// Whether a proximity edge connects zones `a` and `b` (`edges` is sorted).
fn edge_exists(edges: &[(usize, usize)], a: usize, b: usize) -> bool {
    let e = if a < b { (a, b) } else { (b, a) };
    edges.binary_search(&e).is_ok()
}

/// Centroid of the zones at `idx`, or `None` when `idx` is empty.
fn centroid(pos: &[Vec2], idx: &[usize]) -> Option<Vec2> {
    if idx.is_empty() {
        return None;
    }
    let sum = idx
        .iter()
        .fold(Vec2::new(0.0, 0.0), |acc, &i| acc + pos[i]);
    Some(sum.scale(1.0 / idx.len() as f64))
}

/// Index of the zone nearest to `w` (ties break to the lower index).
fn nearest_other(pos: &[Vec2], w: usize) -> Option<usize> {
    (0..pos.len()).filter(|&z| z != w).min_by(|&a, &b| {
        pos[w]
            .distance_sq(pos[a])
            .partial_cmp(&pos[w].distance_sq(pos[b]))
            .unwrap_or(Ordering::Equal)
            .then(a.cmp(&b))
    })
}

/// Unit vector from `a` toward `b` plus their distance. For (near-)coincident
/// points returns a fixed `+x` direction — the engine never divides by zero
/// and replays identically.
fn pair_offset(a: Vec2, b: Vec2) -> (Vec2, f64) {
    let delta = b - a;
    let d = delta.magnitude();
    if d < MIN_DIST {
        (Vec2::new(1.0, 0.0), d)
    } else {
        (delta.scale(1.0 / d), d)
    }
}

/// Inward boundary push for a zone within [`BOUNDARY_MARGIN`] of any edge.
fn boundary_force(p: Vec2) -> Vec2 {
    let mut f = Vec2::new(0.0, 0.0);
    if p.x < BOUNDARY_MARGIN {
        f.x += BOUNDARY_MARGIN - p.x;
    } else if p.x > 1.0 - BOUNDARY_MARGIN {
        f.x -= p.x - (1.0 - BOUNDARY_MARGIN);
    }
    if p.y < BOUNDARY_MARGIN {
        f.y += BOUNDARY_MARGIN - p.y;
    } else if p.y > 1.0 - BOUNDARY_MARGIN {
        f.y -= p.y - (1.0 - BOUNDARY_MARGIN);
    }
    f.scale(BOUNDARY_GAIN)
}

/// Scale `v` down to at most `cap` length, leaving shorter vectors untouched.
fn cap_magnitude(v: Vec2, cap: f64) -> Vec2 {
    let m = v.magnitude();
    if m > cap && m > MIN_DIST {
        v.scale(cap / m)
    } else {
        v
    }
}

/// Clamp a point into the `[0,1] × [0,1]` placement square.
fn clamp_unit(p: Vec2) -> Vec2 {
    Vec2::new(p.x.clamp(0.0, 1.0), p.y.clamp(0.0, 1.0))
}

/// Write the solved positions back onto the placed zones (preserves identity).
fn apply_positions(mut layout: Vec<PlacedZone>, pos: &[Vec2]) -> Vec<PlacedZone> {
    for (zone, &p) in layout.iter_mut().zip(pos) {
        zone.pos = p;
    }
    layout
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::placement::initial_grid_layout;
    use crate::types::template::{TemplateConnection, TilemapTemplateId, ZoneSpec};
    use crate::types::zone::{ZoneId, ZoneRole};

    fn zone(id: &str, conns: &[(&str, PassageKind)]) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: conns
                .iter()
                .map(|(to, kind)| TemplateConnection::new(ZoneId(to.to_string()), *kind))
                .collect(),
            treasure_tiers: vec![],
            biome_selection_rules: None,
            inherit_treasure_from: None,
            biome_theme: None,
        }
    }

    fn template(zones: Vec<ZoneSpec>) -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones,
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
        }
    }

    /// Distance between two zones in a converged layout, by zone id.
    fn dist(zones: &[PlacedZone], a: &str, b: &str) -> f64 {
        let p = |id: &str| zones.iter().find(|z| z.id.0 == id).unwrap().pos;
        p(a).distance(p(b))
    }

    fn converge(t: &TilemapTemplate, seed: u64) -> ConvergenceResult {
        force_directed_converge(
            initial_grid_layout(t),
            t,
            TilemapSeed(seed),
            ConvergenceCaps::default(),
        )
    }

    #[test]
    fn empty_layout_is_trivially_converged() {
        let r = converge(&template(vec![]), 1);
        assert!(r.zones.is_empty());
        assert!(r.converged);
        assert_eq!(r.iteration_count, 0);
    }

    #[test]
    fn single_zone_is_trivially_converged() {
        let r = converge(&template(vec![zone("a", &[])]), 1);
        assert_eq!(r.zones.len(), 1);
        assert!(r.converged);
        assert_eq!(r.iteration_count, 0);
    }

    #[test]
    fn small_graph_converges() {
        // A graph this small settles long before any cap.
        let r = converge(
            &template(vec![
                zone("a", &[("b", PassageKind::Threshold)]),
                zone("b", &[("c", PassageKind::Open)]),
                zone("c", &[]),
                zone("d", &[]),
            ]),
            7,
        );
        assert!(r.converged, "small graph should settle, not hit a cap");
        assert!(r.iteration_count < ConvergenceCaps::default().max_iterations);
    }

    #[test]
    fn connected_zones_converge_closer_than_unconnected() {
        // a–b connected; c and d isolated. FR attraction should leave b nearer
        // a than either unconnected zone (AC-3).
        let r = converge(
            &template(vec![
                zone("a", &[("b", PassageKind::Threshold)]),
                zone("b", &[]),
                zone("c", &[]),
                zone("d", &[]),
            ]),
            42,
        );
        assert!(r.converged);
        let ab = dist(&r.zones, "a", "b");
        assert!(
            ab < dist(&r.zones, "a", "c") && ab < dist(&r.zones, "a", "d"),
            "connected a–b ({ab}) should end closer than a's unconnected zones",
        );
    }

    #[test]
    fn adversarial_zones_pushed_farther_apart() {
        // Same 4-zone graph, once with a–b Adversarial and once unconnected.
        // The adversarial edge must push a and b strictly farther apart.
        let adv = converge(
            &template(vec![
                zone("a", &[("b", PassageKind::Adversarial)]),
                zone("b", &[]),
                zone("c", &[]),
                zone("d", &[]),
            ]),
            9,
        );
        let base = converge(
            &template(vec![
                zone("a", &[]),
                zone("b", &[]),
                zone("c", &[]),
                zone("d", &[]),
            ]),
            9,
        );
        assert!(
            dist(&adv.zones, "a", "b") > dist(&base.zones, "a", "b"),
            "adversarial a–b should end farther apart than the unconnected baseline",
        );
    }

    #[test]
    fn iteration_cap_returns_fr_best_layout() {
        // The iteration cap is seed-deterministic (spec D5) — on trip the
        // engine keeps the FR best-found layout, not the grid seed, with
        // converged: false. A 2-iteration cap cannot converge.
        let t = template(vec![
            zone("a", &[("b", PassageKind::Threshold)]),
            zone("b", &[]),
            zone("c", &[]),
            zone("d", &[]),
        ]);
        let r = force_directed_converge(
            initial_grid_layout(&t),
            &t,
            TilemapSeed(3),
            ConvergenceCaps {
                max_iterations: 2,
                max_wall_clock: Duration::from_secs(5),
                no_improvement_limit: 50,
            },
        );
        assert!(!r.converged, "a 2-iteration cap cannot converge");
        assert_eq!(r.iteration_count, 2);
        assert_eq!(r.zones.len(), 4);
        for z in &r.zones {
            assert!(
                (0.0..=1.0).contains(&z.pos.x) && (0.0..=1.0).contains(&z.pos.y),
                "FR best layout must stay in the unit square",
            );
        }
    }

    #[test]
    fn wall_clock_cap_falls_back_to_grid_seed() {
        // The wall-clock cap is machine-dependent (spec D5) — on trip the
        // engine falls back to the grid-seed layout verbatim so the result
        // stays deterministic. A zero budget trips it on the first loop check,
        // before any FR step runs (iteration_count 0).
        let t = template(vec![
            zone("a", &[("b", PassageKind::Threshold)]),
            zone("b", &[]),
            zone("c", &[]),
            zone("d", &[]),
        ]);
        let expected = initial_grid_layout(&t);
        let r = force_directed_converge(
            initial_grid_layout(&t),
            &t,
            TilemapSeed(3),
            ConvergenceCaps {
                max_iterations: 1000,
                max_wall_clock: Duration::ZERO,
                no_improvement_limit: 50,
            },
        );
        assert!(!r.converged, "a zero wall-clock budget cannot converge");
        assert_eq!(r.iteration_count, 0, "wall-clock trips before any FR step");
        for (got, want) in r.zones.iter().zip(&expected) {
            assert_eq!(got.id, want.id);
            assert_eq!(got.pos, want.pos, "wall-clock fallback must be the grid seed");
        }
    }

    #[test]
    fn deterministic_same_seed_same_layout() {
        let t = template(vec![
            zone("a", &[("b", PassageKind::Threshold)]),
            zone("b", &[("c", PassageKind::Adversarial)]),
            zone("c", &[("d", PassageKind::Open)]),
            zone("d", &[("e", PassageKind::Hint)]),
            zone("e", &[]),
        ]);
        let r1 = converge(&t, 0xABCD);
        let r2 = converge(&t, 0xABCD);
        assert_eq!(r1.converged, r2.converged);
        assert_eq!(r1.iteration_count, r2.iteration_count);
        for (z1, z2) in r1.zones.iter().zip(&r2.zones) {
            assert_eq!(z1.id, z2.id);
            assert_eq!(z1.pos, z2.pos, "same seed must yield byte-identical layout");
        }
    }

    #[test]
    fn converged_zones_stay_in_unit_square() {
        let r = converge(
            &template(vec![
                zone("a", &[("b", PassageKind::Adversarial)]),
                zone("b", &[("c", PassageKind::Adversarial)]),
                zone("c", &[("a", PassageKind::Adversarial)]),
            ]),
            5,
        );
        for z in &r.zones {
            assert!(
                (0.0..=1.0).contains(&z.pos.x) && (0.0..=1.0).contains(&z.pos.y),
                "zone {} escaped the unit square: {:?}",
                z.id.0,
                z.pos,
            );
        }
    }
}
