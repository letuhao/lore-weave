//! Stage 5 — political layer: provinces (terrain-cost flood-fill) + states.

use crate::biome::BiomeKind;
use crate::params::PoliticalParams;
use crate::pathfind::{self, NONE};
use crate::rng::{self, Rng};
use crate::world_map::{County, Province, Realm, State, World};

/// Stage-5 output.
pub struct Political {
    /// Per-cell province id; `NONE` for water cells.
    pub province_of: Vec<u32>,
    pub provinces: Vec<Province>,
    pub states: Vec<State>,
}

/// Build the political layer.
///
/// **Phase 1 Stage B (2026-05-20):** `centers` is now 3D unit-sphere points;
/// spacing tests use great-circle angle (radians). The flood-fill is
/// graph-based and unchanged.
pub fn build(
    seed: u64,
    centers: &[[f32; 3]],
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
    // Min-separation in **radians** of great-circle angle on the sphere.
    // The original `0.85 / sqrt(n_prov)` was in `[0,1]²` units; multiplied
    // by ~π (the sphere's radius scale in great-circle terms) brings the
    // visual seed density close to the prior look. Empirical retune.
    let min_sep = 0.85_f32 / (n_prov as f32).sqrt() * std::f32::consts::PI;
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
            if pathfind::spaced_ok(cell, &seeds, centers, min_sep) {
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

    // The flat/legacy builder has no sphere geometric hierarchy, so the C-2
    // nesting ids are the `NONE` sentinel here. `build_nested` (the sphere
    // builder) sets real values.
    let states: Vec<State> = seed_provs
        .iter()
        .enumerate()
        .map(|(sid, &sp)| State {
            id: sid as u32,
            capital_province: sp as u32,
            subcontinent: NONE,
            realm: NONE,
            name: String::new(),
        })
        .collect();
    let provinces: Vec<Province> = (0..np)
        .map(|p| Province {
            id: p as u32,
            capital_cell: seeds[p],
            state: state_of_prov[p],
            region: NONE,
            name: String::new(),
        })
        .collect();

    Political {
        province_of,
        provinces,
        states,
    }
}

/// The sphere builder's output — the 5-tier strict-nested political layer.
pub struct PoliticalNested {
    pub province_of: Vec<u32>,
    pub provinces: Vec<Province>,
    pub states: Vec<State>,
    pub county_of: Vec<u32>,
    pub counties: Vec<County>,
    pub realms: Vec<Realm>,
    pub world: World,
}

/// 3D dot product on unit-sphere cell centres (great-circle proximity surrogate).
fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/// Group cell ids (ascending) by a per-cell `u32` label; labels `>= n_groups`
/// (e.g. the `NONE` sentinel for water) are skipped.
fn group_cells(label_of: &[u32], n_groups: usize) -> Vec<Vec<u32>> {
    let mut groups = vec![Vec::new(); n_groups];
    for (c, &l) in label_of.iter().enumerate() {
        if (l as usize) < n_groups {
            groups[l as usize].push(c as u32);
        }
    }
    groups
}

/// Group item ids (ascending) by a per-item `u32` label.
fn group_items(label_of: &[u32], n_groups: usize) -> Vec<Vec<usize>> {
    let mut groups = vec![Vec::new(); n_groups];
    for (i, &l) in label_of.iter().enumerate() {
        if (l as usize) < n_groups {
            groups[l as usize].push(i);
        }
    }
    groups
}

/// Farthest-point sampling over raw cells (ascending → lowest-index tie-break).
fn farthest_point_cells(cells: &[u32], quota: usize, centers: &[[f32; 3]]) -> Vec<u32> {
    let quota = quota.clamp(1, cells.len());
    let mut chosen = vec![cells[0]];
    while chosen.len() < quota {
        let mut best: Option<u32> = None;
        let mut best_min = f32::NEG_INFINITY;
        for &c in cells {
            if chosen.contains(&c) {
                continue;
            }
            let cc = centers[c as usize];
            let mut min_d = f32::INFINITY;
            for &s in &chosen {
                let d = 1.0 - dot(cc, centers[s as usize]);
                if d < min_d {
                    min_d = d;
                }
            }
            if min_d > best_min {
                best_min = min_d;
                best = Some(c);
            }
        }
        match best {
            Some(c) => chosen.push(c),
            None => break,
        }
    }
    chosen
}

/// Nearest seed (max dot) among `seed_cells`, lowest index on ties.
fn nearest_seed(cell: u32, seed_cells: &[u32], centers: &[[f32; 3]]) -> u32 {
    let cc = centers[cell as usize];
    let mut best = 0u32;
    let mut best_dot = dot(cc, centers[seed_cells[0] as usize]);
    for (i, &sc) in seed_cells.iter().enumerate().skip(1) {
        let d = dot(cc, centers[sc as usize]);
        if d > best_dot {
            best_dot = d;
            best = i as u32;
        }
    }
    best
}

/// Build the 5-tier political layer **strictly nested inside the C-1a geometric
/// hierarchy**: province ⊆ region, state ⊆ subcontinent, realm ⊆ continent,
/// county ⊆ province. Reuses [`build`]'s flood-fill + farthest-point-cluster
/// machinery, only scoping each tier to its geometric parent. Deterministic
/// (no RNG — every tier is a deterministic function of the geometry).
#[allow(clippy::too_many_arguments)]
pub fn build_nested(
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    region_of: &[u32],
    subcontinent_of: &[u32],
    continent_of: &[u32],
    n_regions: usize,
    n_subcontinents: usize,
    n_continents: usize,
    county_subdivision: u8,
    pp: &PoliticalParams,
) -> PoliticalNested {
    let n = centers.len();

    // --- PROVINCE ⊆ region: terrain-cost flood-fill confined to each region --
    let cells_by_region = group_cells(region_of, n_regions);
    let mut province_of = vec![NONE; n];
    let mut prov_capital: Vec<u32> = Vec::new();
    let mut prov_region: Vec<u32> = Vec::new();
    for (r, cells) in cells_by_region.iter().enumerate() {
        if cells.is_empty() {
            continue;
        }
        let quota = (cells.len() / pp.prov_cells_per_seed as usize).clamp(1, pp.prov_max as usize);
        let seeds = farthest_point_cells(cells, quota, centers);
        let base = prov_capital.len() as u32;
        let assign = pathfind::multi_source_assign(
            &seeds,
            |c| (region_of[c] == r as u32).then(|| biomes[c].terrain_cost()).flatten(),
            neighbors,
        );
        for &c in cells {
            let owner = assign[c as usize];
            // A region can be disconnected (a Voronoi cell needn't be); fall
            // back to the nearest seed so the province stays ⊆ the region.
            let local = if owner == NONE {
                nearest_seed(c, &seeds, centers)
            } else {
                owner
            };
            province_of[c as usize] = base + local;
        }
        for &sc in &seeds {
            prov_capital.push(sc);
            prov_region.push(r as u32);
        }
    }
    let np = prov_capital.len();

    // --- COUNTY ⊆ province: subdivide each province ------------------------
    let cells_by_prov = group_cells(&province_of, np);
    let k_county = usize::from(county_subdivision.clamp(1, pp.county_max.clamp(1, 255) as u8));
    let mut county_of = vec![NONE; n];
    let mut counties: Vec<County> = Vec::new();
    for (p, cells) in cells_by_prov.iter().enumerate() {
        if cells.is_empty() {
            continue;
        }
        let seeds = farthest_point_cells(cells, k_county, centers);
        let base = counties.len() as u32;
        let assign = pathfind::multi_source_assign(
            &seeds,
            |c| (province_of[c] == p as u32).then(|| biomes[c].terrain_cost()).flatten(),
            neighbors,
        );
        for &c in cells {
            let owner = assign[c as usize];
            let local = if owner == NONE {
                nearest_seed(c, &seeds, centers)
            } else {
                owner
            };
            county_of[c as usize] = base + local;
        }
        for (i, &sc) in seeds.iter().enumerate() {
            counties.push(County {
                id: base + i as u32,
                capital_cell: sc,
                province: p as u32,
                name: String::new(),
            });
        }
    }

    // --- STATE (nation) ⊆ subcontinent: cluster the subcontinent's provinces -
    let prov_subcont: Vec<u32> = (0..np)
        .map(|p| subcontinent_of[prov_capital[p] as usize])
        .collect();
    let provs_by_sub = group_items(&prov_subcont, n_subcontinents);
    let mut state_of_prov = vec![0u32; np];
    let mut states: Vec<State> = Vec::new();
    for (sub, provs) in provs_by_sub.iter().enumerate() {
        if provs.is_empty() {
            continue;
        }
        let quota = (provs.len() / pp.state_provs_per_seed as usize)
            .clamp(1, pp.state_max as usize)
            .min(provs.len());
        let mut seed_provs = farthest_point(provs, quota, &prov_capital, centers);
        seed_provs.sort_unstable(); // ascending province id → ascending state id
        let base = states.len() as u32;
        let seed_cells: Vec<u32> = seed_provs.iter().map(|&sp| prov_capital[sp]).collect();
        let assign = pathfind::multi_source_assign(
            &seed_cells,
            |c| (subcontinent_of[c] == sub as u32)
                .then(|| biomes[c].terrain_cost())
                .flatten(),
            neighbors,
        );
        for &p in provs {
            let owner = assign[prov_capital[p] as usize];
            let local = if owner == NONE {
                nearest_seed(prov_capital[p], &seed_cells, centers)
            } else {
                owner
            };
            state_of_prov[p] = base + local;
        }
        for (i, &sp) in seed_provs.iter().enumerate() {
            states.push(State {
                id: base + i as u32,
                capital_province: sp as u32,
                subcontinent: sub as u32,
                realm: NONE,
                name: String::new(),
            });
        }
    }
    let ns = states.len();

    // --- REALM ⊆ continent: cluster the continent's states -----------------
    let state_cap_cell: Vec<u32> = (0..ns)
        .map(|s| prov_capital[states[s].capital_province as usize])
        .collect();
    let state_cont: Vec<u32> = (0..ns)
        .map(|s| continent_of[state_cap_cell[s] as usize])
        .collect();
    let states_by_cont = group_items(&state_cont, n_continents);
    let mut realms: Vec<Realm> = Vec::new();
    for (cont, sts) in states_by_cont.iter().enumerate() {
        if sts.is_empty() {
            continue;
        }
        let quota = (sts.len() / pp.realm_states_per_seed as usize)
            .clamp(1, pp.realm_max as usize)
            .min(sts.len());
        let mut seed_states = farthest_point(sts, quota, &state_cap_cell, centers);
        seed_states.sort_unstable();
        let base = realms.len() as u32;
        let seed_cells: Vec<u32> = seed_states.iter().map(|&ss| state_cap_cell[ss]).collect();
        for &s in sts {
            let local = nearest_seed(state_cap_cell[s], &seed_cells, centers);
            states[s].realm = base + local;
        }
        for (i, &ss) in seed_states.iter().enumerate() {
            realms.push(Realm {
                id: base + i as u32,
                capital_state: ss as u32,
                continent: cont as u32,
                name: String::new(),
            });
        }
    }

    let provinces: Vec<Province> = (0..np)
        .map(|p| Province {
            id: p as u32,
            capital_cell: prov_capital[p],
            state: state_of_prov[p],
            region: prov_region[p],
            name: String::new(),
        })
        .collect();

    PoliticalNested {
        province_of,
        provinces,
        states,
        county_of,
        counties,
        realms,
        world: World::default(),
    }
}

/// Farthest-point sampling: pick `quota` provinces from `provs`, maximally
/// spread by capital-cell distance. Starts from the lowest province id; ties
/// resolve to the lower province id → deterministic.
fn farthest_point(
    provs: &[usize],
    quota: usize,
    seeds: &[u32],
    centers: &[[f32; 3]],
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
            // Sphere distance² (in radians²) — `acos` is monotone in dot,
            // so we can stay in cosine space for monotone comparisons.
            // We use **(1 − dot)** as a monotonically-equivalent distance²
            // surrogate to keep the f32 ordering identical to the old
            // Euclidean distance² flow without branching into acos.
            let q3 = centers[seeds[q] as usize];
            let mut mind2 = f32::INFINITY;
            for &c in &chosen {
                let c3 = centers[seeds[c] as usize];
                let dot = q3[0] * c3[0] + q3[1] * c3[1] + q3[2] * c3[2];
                let d2 = 1.0 - dot;
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
