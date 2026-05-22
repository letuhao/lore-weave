//! Stage 2b — hydraulic erosion (Path B v2).
//!
//! Path B's [`crate::terrain::height_at`] builds ridged ranges and an fBm
//! continent, but the heightmap is *uncarved* — no valleys cut by water. This
//! stage runs **stream-power incision** (the landscape-evolution-model /
//! Fastscape lineage) over the Voronoi mesh: it routes flow downhill,
//! accumulates drainage area, and incises each cell by `K·area^m·slope^n` —
//! the algorithm that produces **dendritic drainage networks**. It runs in two
//! phases: a *carve* phase (pure incision — cut the valleys) then a *settle*
//! phase that adds **transport-capacity deposition** — sediment beyond what a
//! channel can carry is dropped where flow slows (valley floors, mountain-front
//! fans). Hillslope diffusion rounds the sharp ridge crests incision leaves.
//!
//! [`apply`] runs *inside* [`crate::terrain::build`] on the `f32` elevation
//! field, after the coastline falloff and before u16-normalization (a
//! quantized field would round the small per-iteration incision steps to
//! zero). It is a pure function — no RNG, fixed mesh iteration order — so the
//! generator stays bit-reproducible.
//!
//! This module carries its own priority-flood rather than reusing
//! [`crate::hydrology`]'s: the latter is `u16`-keyed, runs post-climate with
//! climate-weighted rainfall, and seeds from the *final* sea level. Erosion's
//! is `f32`, pre-normalization, uniform-rain, and provisional-sea seeded —
//! genuinely different instantiations.

use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;

use crate::creative_seed::ErosionStrength;

/// Erosion tuning for one [`ErosionStrength`].
///
/// Erosion runs in two phases. The **carve** phase is pure stream-power
/// incision — it cuts the dendritic valley network into the raw heightmap.
/// The **settle** phase then enables sediment deposition: on the
/// already-graded landscape incision is mild, so the modest sediment it still
/// produces is dropped only where channel transport capacity falls away —
/// valley floors and mountain-front fans — instead of blanketing and
/// re-filling the freshly cut valleys.
struct ErosionParams {
    /// Pure-incision passes (phase 1 — carve the valleys).
    carve_iters: u32,
    /// Incision + deposition passes (phase 2 — settle sediment into fans).
    settle_iters: u32,
    /// `K` — stream-power erodibility per iteration.
    erodibility: f32,
    /// `Kc` — sediment transport-capacity coefficient. A channel carries
    /// `Kc·area^m·slope` of sediment; load above that capacity is over-supply.
    transport: f32,
    /// Fraction of the over-capacity load deposited per settle pass. Below 1
    /// so a transient over-supply flows on through rather than dumping in one
    /// step — only a *persistent* low-capacity spot accumulates a fan.
    settle_rate: f32,
    /// `D` — hillslope-diffusion (creep) coefficient, `0..1`.
    diffusion: f32,
}

/// Tuning per strength. `None` ⇒ zero iterations (a true no-op).
fn params(strength: ErosionStrength) -> ErosionParams {
    match strength {
        ErosionStrength::None => ErosionParams {
            carve_iters: 0,
            settle_iters: 0,
            erodibility: 0.0,
            transport: 0.0,
            settle_rate: 0.0,
            diffusion: 0.0,
        },
        ErosionStrength::Light => ErosionParams {
            carve_iters: 14,
            settle_iters: 6,
            erodibility: 2.0,
            transport: 4.0,
            settle_rate: 0.15,
            diffusion: 0.010,
        },
        ErosionStrength::Moderate => ErosionParams {
            carve_iters: 18,
            settle_iters: 8,
            erodibility: 3.0,
            transport: 4.0,
            settle_rate: 0.18,
            diffusion: 0.012,
        },
        ErosionStrength::Heavy => ErosionParams {
            carve_iters: 22,
            settle_iters: 10,
            erodibility: 4.0,
            transport: 4.0,
            settle_rate: 0.20,
            diffusion: 0.012,
        },
    }
}

/// Carve the `elev` field in place with hydraulic erosion.
///
/// `land_fraction` sets the provisional waterline (the `(1 - land_fraction)`
/// percentile of `elev`); cells below it are sea — fixed outlets, never
/// eroded. Returns immediately for [`ErosionStrength::None`] or a degenerate
/// (`< 2`-cell) mesh, leaving `elev` bit-identical.
pub fn apply(
    elev: &mut [f32],
    neighbors: &[Vec<u32>],
    land_fraction: f32,
    strength: ErosionStrength,
    erodibility: Option<&[f32]>,
) {
    let p = params(strength);
    if (p.carve_iters + p.settle_iters) == 0 || elev.len() < 2 {
        return;
    }
    // Provisional sea mask + waterline — computed once; erosion does not move
    // the coastline enough to warrant re-deriving the outlets each iteration.
    let (sea, sea_floor) = provisional_sea(elev, land_fraction);

    for i in 0..(p.carve_iters + p.settle_iters) {
        // Phase 1 (carve): pure incision — `settle_rate` 0 ⇒ no deposition.
        // Phase 2 (settle): deposition on, so sediment fans out.
        let settle_rate = if i < p.carve_iters { 0.0 } else { p.settle_rate };
        let (receiver, order, filled) = priority_flood(elev, &sea, neighbors);
        // Adopt the depression-filled field: every land cell now drains
        // monotonically to the sea, so the incision pass sees a non-negative
        // drop everywhere (a raw heightmap is riddled with local pits — incise
        // it directly and most cells have a zero drop and never erode).
        elev.copy_from_slice(&filled);
        let drainage = flow_accumulation(&order, &receiver, elev.len());
        let flow = Flow { receiver, order, drainage };
        incise(elev, &flow, &sea, sea_floor, &p, settle_rate, erodibility);
        diffuse(elev, neighbors, &sea, p.diffusion);
    }
}

/// Per-cell sea mask + the waterline elevation. A cell is sea where `elev` is
/// below the `(1 - land_fraction)` percentile threshold (mirrors
/// `terrain::pick_sea_level`). Sea cells are the fixed outlets — never eroded,
/// the priority-flood seeds. The threshold is also the floor incision may not
/// carve land below: erosion shapes the land surface, it should not punch a
/// speckle of sub-sea-level pits through it — reclassifying land as ocean is
/// the coastline stage's job.
fn provisional_sea(elev: &[f32], land_fraction: f32) -> (Vec<bool>, f32) {
    let n = elev.len();
    let mut sorted: Vec<f32> = elev.to_vec();
    sorted.sort_by(f32::total_cmp);
    let sea_count = ((1.0 - land_fraction) * n as f32).round() as usize;
    let idx = sea_count.clamp(1, n - 1);
    let threshold = sorted[idx];
    let mask = elev.iter().map(|&e| e < threshold).collect();
    (mask, threshold)
}

/// `f32` heap key ordered by [`f32::total_cmp`] — a correct total order for
/// every `f32` (no reliance on positive-float bit monotonicity).
#[derive(Clone, Copy)]
struct FKey(f32);
impl PartialEq for FKey {
    fn eq(&self, other: &Self) -> bool {
        self.0.total_cmp(&other.0) == Ordering::Equal
    }
}
impl Eq for FKey {}
impl PartialOrd for FKey {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for FKey {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0.total_cmp(&other.0)
    }
}

/// The flow-routing result for one iteration: the priority-flood receiver
/// tree plus the accumulated drainage area.
struct Flow {
    /// `receiver[c]` — the cell `c` drains into (`u32::MAX` for a sea cell or
    /// a land cell unreachable from the sea).
    receiver: Vec<u32>,
    /// Cells in ascending filled-elevation pop order.
    order: Vec<usize>,
    /// `drainage[c]` — number of cells draining through `c`.
    drainage: Vec<f32>,
}

/// Priority-flood (Barnes 2014): seed the min-heap with every sea cell, pop
/// ascending *filled* elevation. Each land cell, when first reached, records
/// the cell it drains into (`receiver`) and its depression-*filled* elevation
/// `max(elev, parent_filled)`; `order` is the pop order. Cells are closed at
/// *push* time → each is pushed exactly once → every heap entry has a unique
/// cell index → fully deterministic. `receiver` stays `u32::MAX` (and `filled`
/// stays the input `elev`) for sea cells and any land cell unreachable from
/// the sea.
fn priority_flood(
    elev: &[f32],
    sea: &[bool],
    neighbors: &[Vec<u32>],
) -> (Vec<u32>, Vec<usize>, Vec<f32>) {
    let n = elev.len();
    let mut receiver = vec![u32::MAX; n];
    let mut filled = elev.to_vec();
    let mut closed = vec![false; n];
    let mut order = Vec::with_capacity(n);
    let mut heap: BinaryHeap<Reverse<(FKey, u32)>> = BinaryHeap::new();

    for (i, &is_sea) in sea.iter().enumerate() {
        if is_sea {
            closed[i] = true;
            heap.push(Reverse((FKey(elev[i]), i as u32)));
        }
    }
    while let Some(Reverse((FKey(fe), c))) = heap.pop() {
        let c = c as usize;
        order.push(c);
        for &nb in &neighbors[c] {
            let nb = nb as usize;
            if !closed[nb] {
                let fill = elev[nb].max(fe);
                filled[nb] = fill;
                receiver[nb] = c as u32;
                closed[nb] = true;
                heap.push(Reverse((FKey(fill), nb as u32)));
            }
        }
    }
    (receiver, order, filled)
}

/// Uniform-rainfall flow accumulation: `drainage[c]` is the number of cells
/// draining through `c` (each cell contributes `1.0`). Summed in reverse pop
/// order, so a cell is complete before its receiver consumes it.
fn flow_accumulation(order: &[usize], receiver: &[u32], n: usize) -> Vec<f32> {
    let mut drainage = vec![1.0f32; n];
    for &c in order.iter().rev() {
        let r = receiver[c];
        if r != u32::MAX {
            drainage[r as usize] += drainage[c];
        }
    }
    drainage
}

/// Stream-power incision + transport-capacity deposition — one
/// reverse-pop-order pass. `settle_rate` 0 ⇒ deposition off (carve phase).
///
/// In reverse pop order each cell is processed before its (lower) receiver, so
/// `elev[receiver]` is still the start-of-iteration value when a donor reads
/// it, and `sediment_in[receiver]` is fully accumulated by the time the
/// receiver is reached — an explicit Euler step with no scratch buffer needed.
fn incise(
    elev: &mut [f32],
    flow: &Flow,
    sea: &[bool],
    sea_floor: f32,
    p: &ErosionParams,
    settle_rate: f32,
    erodibility: Option<&[f32]>,
) {
    let n = elev.len();
    let mut sediment_in = vec![0.0f32; n];
    for &c in flow.order.iter().rev() {
        if sea[c] {
            continue; // sea cells are fixed; their inbound sediment exits.
        }
        let r = flow.receiver[c];
        if r == u32::MAX {
            continue; // land unreachable from the sea — leave it untouched.
        }
        let r = r as usize;
        let drop = (elev[c] - elev[r]).max(0.0);
        let area = flow.drainage[c] / n as f32;

        // The shared stream-power factor `area^m·slope` — m = 0.5 (⇒ `sqrt`),
        // slope exponent n = 1 (⇒ the slope term is the receiver `drop`).
        let stream = area.sqrt() * drop;

        // Per-cell erodibility (ruggedness-gated in Tectonic mode): mountains
        // carve valleys, plains barely incise (so they stay flat) — but
        // deposition stays ungated below, so sediment from the highlands still
        // fills the lowlands (Musgrave's "silt smooths the lowlands").
        let k = p.erodibility * erodibility.map_or(1.0, |e| e[c]);

        // Stream-power incision, clamped to `drop`: `elev[c]` never sinks
        // below its receiver, so the tree stays monotone and elevations stay
        // `≥ 0` (the chain bottoms at a sea cell).
        let erosion = (k * stream).min(drop);

        // Transport-capacity deposition: the channel carries `Kc·stream` of
        // sediment; `settle_rate` of any load above that capacity is dropped
        // here (valley-floor fill, mountain-front fans). `settle_rate` is 0 in
        // the carve phase ⇒ pure incision. Clamped `≤ flux`: a cell can never
        // deposit more sediment than is passing through it.
        let flux = sediment_in[c] + erosion;
        let capacity = p.transport * stream;
        let deposition = (settle_rate * (flux - capacity).max(0.0)).min(flux);

        // Apply the net change, but never carve a land cell below the
        // waterline — that keeps every island/landmass intact (erosion may not
        // turn land into ocean) and avoids a speckle of sub-sea-level pits.
        let pre = elev[c];
        elev[c] = (pre + deposition - erosion).max(sea_floor);
        // Sediment is conserved: the flux leaving `c` is the inbound flux less
        // the net elevation gain the ground kept. Using the *actual* delta
        // keeps the books exact even when the waterline clamp curbs incision;
        // the result is `≥ 0` (the net gain never exceeds `sediment_in`).
        sediment_in[r] += (sediment_in[c] - (elev[c] - pre)).max(0.0);
    }
}

/// Hillslope diffusion (thermal creep): nudge each land cell toward the mean
/// of its neighbours by coefficient `d`. Simultaneous update via a scratch
/// copy so the result is order-independent; sea cells are left fixed.
fn diffuse(elev: &mut [f32], neighbors: &[Vec<u32>], sea: &[bool], d: f32) {
    let mut next = elev.to_vec();
    for c in 0..elev.len() {
        if sea[c] || neighbors[c].is_empty() {
            continue;
        }
        let mut sum = 0.0f32;
        for &nb in &neighbors[c] {
            sum += elev[nb as usize];
        }
        let mean = sum / neighbors[c].len() as f32;
        next[c] = elev[c] + d * (mean - elev[c]);
    }
    elev.copy_from_slice(&next);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A `side × side` 4-connected grid: cell `(i,j)` at index `j*side + i`.
    fn grid(side: usize) -> Vec<Vec<u32>> {
        let mut neighbors = vec![Vec::new(); side * side];
        for j in 0..side {
            for i in 0..side {
                let c = j * side + i;
                if i > 0 {
                    neighbors[c].push((c - 1) as u32);
                }
                if i + 1 < side {
                    neighbors[c].push((c + 1) as u32);
                }
                if j > 0 {
                    neighbors[c].push((c - side) as u32);
                }
                if j + 1 < side {
                    neighbors[c].push((c + side) as u32);
                }
            }
        }
        neighbors
    }

    /// A tilted plane with a sinusoidal ripple — slopes down toward `j = 0`,
    /// guaranteeing land that drains to a low edge once a sea mask is applied.
    fn tilted_field(side: usize) -> Vec<f32> {
        (0..side * side)
            .map(|c| {
                let (i, j) = (c % side, c / side);
                let ramp = j as f32 / side as f32;
                let ripple = 0.05 * ((i as f32 * 1.3).sin() + (j as f32 * 0.7).cos());
                (ramp + ripple).max(0.0)
            })
            .collect()
    }

    #[test]
    fn params_none_is_a_no_op() {
        let nb = grid(8);
        let before = tilted_field(8);
        let mut elev = before.clone();
        apply(&mut elev, &nb, 0.6, ErosionStrength::None, None);
        for (a, b) in elev.iter().zip(&before) {
            assert_eq!(a.to_bits(), b.to_bits(), "None must leave elev untouched");
        }
    }

    #[test]
    fn apply_is_deterministic() {
        let nb = grid(16);
        let base = tilted_field(16);
        let mut a = base.clone();
        let mut b = base.clone();
        apply(&mut a, &nb, 0.6, ErosionStrength::Moderate, None);
        apply(&mut b, &nb, 0.6, ErosionStrength::Moderate, None);
        for (x, y) in a.iter().zip(&b) {
            assert_eq!(x.to_bits(), y.to_bits(), "erosion is not reproducible");
        }
    }

    #[test]
    fn apply_output_is_finite_and_non_negative() {
        let nb = grid(20);
        for strength in [
            ErosionStrength::Light,
            ErosionStrength::Moderate,
            ErosionStrength::Heavy,
        ] {
            let mut elev = tilted_field(20);
            apply(&mut elev, &nb, 0.55, strength, None);
            for (c, &e) in elev.iter().enumerate() {
                assert!(e.is_finite() && e >= 0.0, "cell {c} = {e} ({strength:?})");
            }
        }
    }

    #[test]
    fn apply_carves_channels() {
        // Criterion 3: erosion must lower land cells (carve valleys).
        let nb = grid(24);
        let before = tilted_field(24);
        let mut after = before.clone();
        apply(&mut after, &nb, 0.6, ErosionStrength::Moderate, None);
        let incised: f32 = before
            .iter()
            .zip(&after)
            .map(|(&b, &a)| (b - a).max(0.0))
            .sum();
        assert!(incised > 0.0, "Moderate erosion carved nothing: {incised}");
    }

    #[test]
    fn erosion_is_monotone_in_strength() {
        // Criterion 6: total incised volume is non-decreasing in strength.
        let nb = grid(24);
        let before = tilted_field(24);
        let incised = |s| {
            let mut after = before.clone();
            apply(&mut after, &nb, 0.6, s, None);
            before
                .iter()
                .zip(&after)
                .map(|(&b, &a)| (b - a).max(0.0))
                .sum::<f32>()
        };
        let none = incised(ErosionStrength::None);
        let light = incised(ErosionStrength::Light);
        let moderate = incised(ErosionStrength::Moderate);
        let heavy = incised(ErosionStrength::Heavy);
        assert_eq!(none, 0.0, "None must incise nothing");
        assert!(
            none <= light && light <= moderate && moderate <= heavy,
            "not monotone: {none} {light} {moderate} {heavy}"
        );
    }

    #[test]
    fn diffuse_smooths_a_spiky_field() {
        // Criterion 4: hillslope diffusion reduces local relief.
        let side = 12;
        let nb = grid(side);
        let sea = vec![false; side * side];
        // Checkerboard spikes — maximal neighbour contrast.
        let mut elev: Vec<f32> = (0..side * side)
            .map(|c| if (c % side + c / side) % 2 == 0 { 1.0 } else { 0.0 })
            .collect();
        let roughness = |f: &[f32]| -> f32 {
            f.iter()
                .enumerate()
                .map(|(c, &e)| {
                    nb[c]
                        .iter()
                        .map(|&n| (e - f[n as usize]).abs())
                        .sum::<f32>()
                })
                .sum()
        };
        let before = roughness(&elev);
        diffuse(&mut elev, &nb, &sea, 0.10);
        assert!(
            roughness(&elev) < before,
            "diffusion did not smooth the field"
        );
    }

    #[test]
    fn flow_accumulation_conserves_cells() {
        // Every cell contributes 1.0; the receiver tree must conserve the sum.
        let side = 10;
        let nb = grid(side);
        let elev = tilted_field(side);
        let (sea, _floor) = provisional_sea(&elev, 0.6);
        let (receiver, order, _filled) = priority_flood(&elev, &sea, &nb);
        let drainage = flow_accumulation(&order, &receiver, elev.len());
        // The receiver forest roots are exactly the sea cells (`receiver ==
        // MAX`); their drainage must sum to the full popped-cell count.
        let root_sum: f32 = order
            .iter()
            .filter(|&&c| receiver[c] == u32::MAX)
            .map(|&c| drainage[c])
            .sum();
        assert_eq!(
            root_sum,
            order.len() as f32,
            "drainage lost cells in the receiver tree"
        );
    }

    #[test]
    fn settle_phase_deposits() {
        // The settle phase must actually deposit — one `incise` pass with
        // deposition on (`settle_rate > 0`) has to differ from the same pass
        // with it off, and depositing must raise some cell above the
        // carve-only result.
        let side = 24;
        let nb = grid(side);
        let base = tilted_field(side);
        let (sea, floor) = provisional_sea(&base, 0.6);
        let p = params(ErosionStrength::Heavy);
        let run = |settle_rate: f32| {
            let mut e = base.clone();
            let (receiver, order, filled) = priority_flood(&e, &sea, &nb);
            e.copy_from_slice(&filled);
            let drainage = flow_accumulation(&order, &receiver, e.len());
            let flow = Flow { receiver, order, drainage };
            incise(&mut e, &flow, &sea, floor, &p, settle_rate, None);
            e
        };
        let carve_only = run(0.0);
        let with_settle = run(p.settle_rate);
        assert!(
            carve_only
                .iter()
                .zip(&with_settle)
                .any(|(a, b)| b > a),
            "deposition did not raise any cell above the carve-only result"
        );
    }
}
