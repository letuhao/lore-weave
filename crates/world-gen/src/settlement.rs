//! Stage 6 — settlement placement (burg-score weighted Poisson-disk) + roles.

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::SettlementDensity;
use crate::pathfind;
use crate::political::Political;
use crate::rng::{self, Rng};
use crate::world_map::{Settlement, SettlementRole};

/// Build the settlement layer.
// Eight pipeline inputs — each a distinct prior-stage array; bundling them
// into a context struct would not reduce the real coupling.
#[allow(clippy::too_many_arguments)]
pub fn build(
    seed: u64,
    centers: &[(f32, f32)],
    biomes: &[BiomeKind],
    climate: &[ClimateZone],
    river_flux: &[f32],
    is_coast: &[bool],
    density: SettlementDensity,
    political: &Political,
) -> Vec<Settlement> {
    let n = centers.len();

    // --- burg score per land cell ---
    let mut burg = vec![0.0f32; n];
    let mut max_burg = 0.0f32;
    for i in 0..n {
        if biomes[i].is_water() {
            continue;
        }
        // `river_flux[i] > 0.0` (and the `burg > 0.05` / RNG conjuncts below)
        // are branches on identically-recomputed finite f32 ⇒ bit-stable.
        let water_bonus = if is_coast[i] {
            1.3
        } else if river_flux[i] > 0.0 {
            1.15
        } else {
            1.0
        };
        let b = biomes[i].population_potential() * water_bonus * climate_friendly(climate[i]);
        burg[i] = b;
        max_burg = max_burg.max(b);
    }
    // All-barren land (e.g. a hypothetical all-Glacier continent) → keep
    // max_burg positive so the burg ratio stays finite. The Poisson pass then
    // places nothing (burg 0 fails the `> 0.05` conjunct) but the Capital
    // force-place below still gives every state a Capital — so criterion #4
    // holds even on a degenerate map. (Practically unreachable.)
    if max_burg <= 0.0 {
        max_burg = 1.0;
    }

    // --- weighted Poisson-disk placement ---
    let land_count = biomes.iter().filter(|b| !b.is_water()).count();
    // Floor the target so a small map (e.g. Pocket + Sparse, where the raw
    // divisor yields 0) is never settlement-starved — it would otherwise
    // carry only the force-placed Capitals.
    let target = (land_count / density.cells_per_settlement()).max(3);
    let min_sep2 = {
        let s = density.min_separation();
        s * s
    };
    let mut rng = Rng::for_stage(seed, b"settlement");
    let mut order: Vec<u32> = (0..n as u32)
        .filter(|&c| !biomes[c as usize].is_water())
        .collect();
    rng::shuffle(&mut rng, &mut order);

    let mut placed: Vec<u32> = Vec::new();
    for &c in &order {
        if placed.len() >= target {
            break;
        }
        let ci = c as usize;
        // Short-circuit `&&` in exactly this order: the RNG draw is last and
        // is consumed only when the burg + spacing tests both pass
        // (byte-stability contract). `order` holds each land cell exactly
        // once, so a `!placed.contains(&c)` guard would be vacuous.
        if burg[ci] > 0.05
            && pathfind::spaced_ok(c, &placed, centers, min_sep2)
            && rng.next_f32() < burg[ci] / max_burg
        {
            placed.push(c);
        }
    }

    let mut settlements: Vec<Settlement> = placed
        .iter()
        .map(|&c| Settlement {
            cell: c,
            role: SettlementRole::Hamlet,
            population_tier: 1,
            name: String::new(),
        })
        .collect();

    // --- Capital per state (political-first) ---
    for st in &political.states {
        let cap_prov = &political.provinces[st.capital_province as usize];
        let (ccx, ccy) = centers[cap_prov.capital_cell as usize];
        // settlement in this province nearest the province capital cell;
        // tie-break (distance, cell_id) lowest.
        let mut best: Option<usize> = None;
        let mut best_key = (f32::INFINITY, u32::MAX);
        for (si, s) in settlements.iter().enumerate() {
            if political.province_of[s.cell as usize] != cap_prov.id {
                continue;
            }
            let (sx, sy) = centers[s.cell as usize];
            let d2 = (sx - ccx) * (sx - ccx) + (sy - ccy) * (sy - ccy);
            // `d2` is a finite sum of squares computed identically every run,
            // so this `(f32, u32)` tuple comparison is bit-stable; the `cell`
            // component is the integer tie-break.
            let key = (d2, s.cell);
            if key < best_key {
                best_key = key;
                best = Some(si);
            }
        }
        match best {
            Some(si) => settlements[si].role = SettlementRole::Capital,
            None => {
                // The province has zero settlements ⇒ its capital_cell (which
                // lies in the province) is unoccupied ⇒ collision-free.
                settlements.push(Settlement {
                    cell: cap_prov.capital_cell,
                    role: SettlementRole::Capital,
                    population_tier: 5,
                    name: String::new(),
                });
            }
        }
    }

    // --- non-Capital roles by burg rank ---
    let mut ranked: Vec<usize> = (0..settlements.len())
        .filter(|&si| settlements[si].role != SettlementRole::Capital)
        .collect();
    ranked.sort_by(|&a, &b| {
        let ba = burg[settlements[a].cell as usize];
        let bb = burg[settlements[b].cell as usize];
        bb.total_cmp(&ba)
            .then(settlements[a].cell.cmp(&settlements[b].cell))
    });
    let total = ranked.len().max(1);
    for (rank, &si) in ranked.iter().enumerate() {
        let frac = rank as f32 / total as f32;
        settlements[si].role = if frac < 0.12 {
            SettlementRole::City
        } else if frac < 0.34 {
            SettlementRole::Town
        } else if frac < 0.67 {
            SettlementRole::Village
        } else {
            SettlementRole::Hamlet
        };
    }

    // --- Fortress override: a non-Capital settlement on a Mountain cell ---
    for s in &mut settlements {
        if s.role != SettlementRole::Capital && biomes[s.cell as usize] == BiomeKind::Mountain {
            s.role = SettlementRole::Fortress;
        }
    }

    // --- population_tier from role ---
    for s in &mut settlements {
        s.population_tier = match s.role {
            SettlementRole::Capital => 5,
            SettlementRole::City => 4,
            SettlementRole::Town => 3,
            SettlementRole::Village | SettlementRole::Fortress => 2,
            SettlementRole::Hamlet => 1,
        };
    }

    settlements
}

/// Climate habitability multiplier for the burg score.
fn climate_friendly(z: ClimateZone) -> f32 {
    match z {
        ClimateZone::Temperate | ClimateZone::Mediterranean => 1.0,
        ClimateZone::Subtropical => 0.9,
        ClimateZone::Tropical => 0.7,
        ClimateZone::Boreal => 0.6,
        ClimateZone::Arid | ClimateZone::Highland => 0.5,
        ClimateZone::Polar => 0.3,
    }
}
