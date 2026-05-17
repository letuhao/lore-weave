//! Stage 5 — political layer: provinces (terrain-cost flood-fill) + states.

use crate::biome::BiomeKind;
use crate::pathfind::{self, NONE};
use crate::rng::{self, Rng};
use crate::world_map::{Province, State};

/// Stage-5 output.
pub struct Political {
    /// Per-cell province id; `NONE` for water cells.
    pub province_of: Vec<u32>,
    pub provinces: Vec<Province>,
    pub states: Vec<State>,
}

/// Build the political layer.
pub fn build(
    seed: u64,
    centers: &[(f32, f32)],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
) -> Political {
    let n = centers.len();
    let is_land: Vec<bool> = biomes.iter().map(|b| !b.is_water()).collect();
    let comps = pathfind::land_components(&is_land, neighbors);
    if comps.is_empty() {
        return Political {
            province_of: vec![NONE; n],
            provinces: Vec::new(),
            states: Vec::new(),
        };
    }

    let land_count: usize = comps.iter().map(Vec::len).sum();
    let n_components = comps.len();
    // clamp(4,80) is a target; .max(n_components) is the real lower bound.
    let n_prov = (land_count / 200).clamp(4, 80).max(n_components);
    let comp_sizes: Vec<usize> = comps.iter().map(Vec::len).collect();
    let quotas = pathfind::apportion(n_prov, &comp_sizes);

    // --- place exactly n_prov province seeds, `quota` per component ---
    let min_sep2 = {
        let s = 0.85 / (n_prov as f32).sqrt();
        s * s
    };
    let mut rng = Rng::for_stage(seed, b"political");
    let mut seeds: Vec<u32> = Vec::with_capacity(n_prov);
    for (ci, comp) in comps.iter().enumerate() {
        let quota = quotas[ci];
        let mut cells = comp.clone();
        rng::shuffle(&mut rng, &mut cells);
        let start = seeds.len();
        // pass 1 — spaced
        for &cell in &cells {
            if seeds.len() - start >= quota {
                break;
            }
            if pathfind::spaced_ok(cell, &seeds, centers, min_sep2) {
                seeds.push(cell);
            }
        }
        // pass 2 — fill the quota ignoring spacing (comp.len() >= quota)
        for &cell in &cells {
            if seeds.len() - start >= quota {
                break;
            }
            if !seeds[start..].contains(&cell) {
                seeds.push(cell);
            }
        }
    }
    let np = seeds.len();

    // --- province flood-fill (Voronoi-of-terrain-cost) ---
    let province_of =
        pathfind::multi_source_assign(&seeds, |c| biomes[c].terrain_cost(), neighbors);

    // --- states: pick `n_states` state-seed provinces, assign each province
    //     to the nearest state-seed in its own land component ---
    let mut comp_of = vec![usize::MAX; n];
    for (ci, comp) in comps.iter().enumerate() {
        for &c in comp {
            comp_of[c as usize] = ci;
        }
    }
    let prov_comp = |p: usize| comp_of[seeds[p] as usize];

    // provinces grouped by land component (ascending province id within each).
    let mut provs_by_comp: Vec<Vec<usize>> = vec![Vec::new(); n_components];
    for p in 0..np {
        provs_by_comp[prov_comp(p)].push(p);
    }
    let n_states = (np / 4).clamp(3, 12).min(np).max(n_components);
    let comp_prov_counts: Vec<usize> = provs_by_comp.iter().map(Vec::len).collect();
    let state_quota = pathfind::apportion(n_states, &comp_prov_counts);

    // state-seed provinces: farthest-point spread within each component.
    let mut seed_provs: Vec<usize> = Vec::new();
    for (ci, provs) in provs_by_comp.iter().enumerate() {
        let quota = state_quota[ci].min(provs.len()).max(1);
        seed_provs.extend(farthest_point(provs, quota, &seeds, centers));
    }
    seed_provs.sort_unstable(); // ascending province id → ascending state id

    // assign each province to the nearest state-seed by TerrainCost path
    // (GEO_002 §5.1 step 7 — not raw Euclidean distance, so state borders
    // follow the terrain). Water is impassable for `terrain_cost`, so the
    // multi-source Dijkstra also keeps every province inside its own land
    // component.
    let state_seed_cells: Vec<u32> = seed_provs.iter().map(|&sp| seeds[sp]).collect();
    let state_owner =
        pathfind::multi_source_assign(&state_seed_cells, |c| biomes[c].terrain_cost(), neighbors);
    let mut state_of_prov = vec![0u32; np];
    for p in 0..np {
        let owner = state_owner[seeds[p] as usize];
        // farthest_point places ≥1 state-seed per non-empty component, and
        // every land cell reaches every other in its component, so a
        // province always has a reachable state-seed — assert it loudly.
        debug_assert!(
            owner != NONE,
            "province {p} cell unreachable from every state-seed"
        );
        state_of_prov[p] = if owner == NONE { 0 } else { owner };
    }

    let states: Vec<State> = seed_provs
        .iter()
        .enumerate()
        .map(|(sid, &sp)| State {
            id: sid as u32,
            capital_province: sp as u32,
            name: String::new(),
        })
        .collect();
    let provinces: Vec<Province> = (0..np)
        .map(|p| Province {
            id: p as u32,
            capital_cell: seeds[p],
            state: state_of_prov[p],
            name: String::new(),
        })
        .collect();

    Political {
        province_of,
        provinces,
        states,
    }
}

/// Farthest-point sampling: pick `quota` provinces from `provs`, maximally
/// spread by capital-cell distance. Starts from the lowest province id; ties
/// resolve to the lower province id → deterministic.
fn farthest_point(
    provs: &[usize],
    quota: usize,
    seeds: &[u32],
    centers: &[(f32, f32)],
) -> Vec<usize> {
    if provs.is_empty() {
        return Vec::new();
    }
    let mut chosen = vec![provs[0]]; // provs is ascending → provs[0] is lowest id
    while chosen.len() < quota.min(provs.len()) {
        let mut best_d = f32::NEG_INFINITY;
        let mut pick = usize::MAX;
        for &q in provs {
            if chosen.contains(&q) {
                continue;
            }
            let (qx, qy) = centers[seeds[q] as usize];
            let mut mind2 = f32::INFINITY;
            for &c in &chosen {
                let (cx, cy) = centers[seeds[c] as usize];
                let d2 = (qx - cx) * (qx - cx) + (qy - cy) * (qy - cy);
                mind2 = mind2.min(d2);
            }
            // `mind2` is a finite, identically-recomputed min of sums of
            // squares ⇒ both the `>` and the exact `==` tie-test are
            // bit-stable across runs; the `q < pick` integer tie-break makes
            // the choice fully deterministic.
            if mind2 > best_d || (mind2 == best_d && q < pick) {
                best_d = mind2;
                pick = q;
            }
        }
        if pick == usize::MAX {
            break;
        }
        chosen.push(pick);
    }
    chosen
}
