//! Elevation-redesign **S4** acceptance gate — age-based oceanic bathymetry.
//!
//! Ocean depth is driven by **oceanic-crust age** (GDH1 `√age`): new crust at a
//! divergent ridge is shallow and deepens as it spreads, replacing the old
//! coast-distance curve that saturated to a flat abyss.
//!
//! Two properties:
//! - **Mechanism** (`depth_increases_with_crust_age`) — in a real generated
//!   terrain, mean open-ocean elevation strictly *decreases* (gets deeper) across
//!   crust-age quartiles. White-box: reads `terrain::build`'s `Plates::crust_age`.
//! - **Distribution** (`age_bathymetry_spreads_the_ocean_mode`) — the deep-abyss
//!   spike that piled > 50 % of ocean cells into the single deepest elevation bin
//!   (D4) is broken: the deepest bin is now a minority and depth spans many bins.
//!
//! Spec: `docs/specs/2026-05-31-elevation-redesign.md` (S4);
//! plan: `docs/plans/2026-06-14-elevation-s4-age-bathymetry.md`.

use world_gen::{CreativeSeed, PlateKind, WorldScale, generate, mesh, terrain};

/// BFS hops from the coast over ocean cells (land = `u32::MAX`).
fn coast_distance(is_land: &[bool], neighbors: &[Vec<u32>]) -> Vec<u32> {
    let n = is_land.len();
    let mut dist = vec![u32::MAX; n];
    let mut frontier: Vec<u32> = Vec::new();
    for c in 0..n {
        if !is_land[c] && neighbors[c].iter().any(|&nb| is_land[nb as usize]) {
            dist[c] = 0;
            frontier.push(c as u32);
        }
    }
    let mut d = 0u32;
    while !frontier.is_empty() {
        let mut next = Vec::new();
        for &c in &frontier {
            for &nb in &neighbors[c as usize] {
                let nb = nb as usize;
                if !is_land[nb] && dist[nb] == u32::MAX {
                    dist[nb] = d + 1;
                    next.push(nb as u32);
                }
            }
        }
        frontier = next;
        d += 1;
    }
    dist
}

/// **Mechanism** — mean open-ocean depth grows monotonically with crust age.
/// White-box: builds the tectonic terrain directly so it can read `crust_age`
/// (a `Plates` field, parallel to S3's `crust_thickness`).
#[test]
fn depth_increases_with_crust_age() {
    let seeds: [u64; 4] = [7, 13, 42, 2024];
    // Accumulate (sum_elev, count) per age quartile across the sweep.
    let mut bucket = [(0f64, 0u64); 4];
    for &seed in &seeds {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let m = mesh::build(seed, cs.world_scale);
        let t = terrain::build(seed, &cs, &m.centers, &m.neighbors);
        let plates = t.plates.as_ref().expect("Tectonic mode exposes plates");

        let is_land: Vec<bool> = t.elevation.iter().map(|&e| e >= t.sea_level).collect();
        let coast = coast_distance(&is_land, &m.neighbors);

        // Open-ocean oceanic-plate cells with a finite age, past the shelf ramp.
        let mut samples: Vec<(u32, u16)> = (0..m.centers.len())
            .filter(|&c| {
                !is_land[c]
                    && coast[c] >= 4
                    && plates.plates[plates.plate_of[c] as usize].kind == PlateKind::Oceanic
                    && plates.crust_age[c] != u32::MAX
            })
            .map(|c| (plates.crust_age[c], t.elevation[c]))
            .collect();
        assert!(samples.len() >= 40, "seed {seed}: too few open-ocean samples ({})", samples.len());
        samples.sort_by_key(|&(age, _)| age);

        let q = samples.len() / 4;
        for (qi, slot) in bucket.iter_mut().enumerate() {
            let lo = qi * q;
            let hi = if qi == 3 { samples.len() } else { (qi + 1) * q };
            for &(_, elev) in &samples[lo..hi] {
                slot.0 += f64::from(elev);
                slot.1 += 1;
            }
        }
    }

    let means: Vec<f64> = bucket.iter().map(|&(s, n)| s / n.max(1) as f64).collect();
    eprintln!("depth_increases_with_crust_age: quartile mean elevation = {means:?}");
    // Younger crust (lower quartile) is shallower ⇒ higher elevation; older crust
    // is deeper ⇒ lower elevation. Strictly decreasing across quartiles.
    for w in means.windows(2) {
        assert!(
            w[0] > w[1],
            "mean ocean elevation not strictly deepening with age: {means:?}"
        );
    }
}

/// **Distribution** — the age curve breaks the deep-abyss spike (D4). At HEAD the
/// coast-distance curve put **51 %** of ocean cells in the single deepest bin;
/// the √age curve must drop that well below 40 % and spread depth across the
/// column.
#[test]
fn age_bathymetry_spreads_the_ocean_mode() {
    const NB: usize = 20;
    let seeds = [7u64, 13, 42, 99, 123, 2024];
    let mut hist = [0u64; NB];
    let mut ocean = 0u64;
    for &s in &seeds {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let m = generate(s, &cs);
        for c in 0..m.cell_count() {
            if m.cells[c].elevation < m.sea_level {
                let b = ((m.cells[c].elevation as usize) * NB / 65536).min(NB - 1);
                hist[b] += 1;
                ocean += 1;
            }
        }
    }
    let deepest = hist.iter().take(8).cloned().max().unwrap_or(0);
    let deepest_pct = 100.0 * deepest as f64 / ocean.max(1) as f64;
    let nonempty = hist.iter().filter(|&&h| h > 0).count();
    let bin0_pct = 100.0 * hist[0] as f64 / ocean.max(1) as f64;
    eprintln!(
        "age_bathymetry_spreads_the_ocean_mode: ocean={ocean}, bin0 {bin0_pct:.1}%, \
         deepest-mode {deepest_pct:.1}%, nonempty bins {nonempty}"
    );
    assert!(
        bin0_pct < 40.0,
        "deepest bin still {bin0_pct:.1}% of ocean (was 51% at HEAD) — the abyss spike persists"
    );
    assert!(nonempty >= 5, "ocean depth spans only {nonempty} bins — no depth structure");
}
