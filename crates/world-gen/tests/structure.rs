//! Structural invariants — cell count, neighbour degree, symmetry, land
//! coherence, sea-level band. (Phase 1 acceptance criteria #3–#6.)

use world_gen::{CoastlineProfile, CreativeSeed, WorldMap, WorldScale, generate};

const SCALES: [WorldScale; 5] = [
    WorldScale::Pocket,
    WorldScale::Region,
    WorldScale::Continent,
    WorldScale::SuperContinent,
    WorldScale::Megaplanet,
];

const PROFILES: [CoastlineProfile; 5] = [
    CoastlineProfile::Island,
    CoastlineProfile::Peninsula,
    CoastlineProfile::Coastal,
    CoastlineProfile::Inland,
    CoastlineProfile::Archipelago,
];

/// Criterion #3 — cell count is exactly `scale.cell_count()`.
#[test]
fn cell_count_exact_per_scale() {
    let expected = [
        (WorldScale::Pocket, 1024usize),
        (WorldScale::Region, 2025),
        (WorldScale::Continent, 8281),
        (WorldScale::SuperContinent, 12321),
        (WorldScale::Megaplanet, 16384),
    ];
    for (scale, want) in expected {
        assert_eq!(scale.cell_count(), want, "cell_count() for {scale:?}");
        let cs = CreativeSeed {
            world_scale: scale,
            ..CreativeSeed::default()
        };
        let map = generate(0xABCD, &cs);
        assert_eq!(map.cell_count(), want, "generated count for {scale:?}");
        assert!(
            (1024..=16384).contains(&map.cell_count()),
            "{scale:?} out of [1024,16384]"
        );
    }
}

/// Criterion #4 — every cell has neighbour degree in `[3, 12]`.
#[test]
fn neighbor_degree_within_bounds() {
    for scale in SCALES {
        let cs = CreativeSeed {
            world_scale: scale,
            ..CreativeSeed::default()
        };
        let map = generate(7, &cs);
        for (i, list) in map.neighbors.iter().enumerate() {
            let d = list.len();
            assert!(
                (3..=12).contains(&d),
                "{scale:?} cell {i}: degree {d} outside [3,12]"
            );
        }
    }
}

/// Criterion #4 — `neighbors` is sorted+deduped and symmetric, every scale.
#[test]
fn neighbors_sorted_deduped_and_symmetric() {
    for scale in SCALES {
        let cs = CreativeSeed {
            world_scale: scale,
            ..CreativeSeed::default()
        };
        let map = generate(123, &cs);
        for (i, list) in map.neighbors.iter().enumerate() {
            let mut canon = list.clone();
            canon.sort_unstable();
            canon.dedup();
            assert_eq!(&canon, list, "{scale:?} cell {i}: not sorted/deduped");
            for &n in list {
                assert!(
                    map.neighbors[n as usize].contains(&(i as u32)),
                    "{scale:?} asymmetric edge {i}<->{n}"
                );
                assert_ne!(n as usize, i, "{scale:?} cell {i}: self-loop");
            }
        }
    }
}

/// Criterion #5 — land coherence is a *universal* property, so it is swept
/// across many seeds (a single seed is no evidence for a universal claim,
/// per code-review r1 BLOCK-1) and across every `WorldScale` (per r2
/// Finding C — different scales are different blob-density regimes).
#[test]
fn land_coherence_per_profile() {
    for profile in PROFILES {
        for scale in SCALES {
            // Continent is the canonical scale → deep sweep; the others get
            // a lighter sweep to keep total runtime bounded.
            let seeds: u64 = if scale == WorldScale::Continent { 48 } else { 12 };
            for seed in 0..seeds {
                let cs = CreativeSeed {
                    coastline_profile: profile,
                    world_scale: scale,
                    ..CreativeSeed::default()
                };
                let map = generate(seed, &cs);
                let comps = land_components(&map);
                let land_total: usize = comps.iter().sum();
                assert!(
                    land_total > 0,
                    "{profile:?}/{scale:?} seed {seed}: no land at all"
                );
                let largest = *comps.iter().max().expect("land_total > 0 ⇒ a component");

                if profile == CoastlineProfile::Archipelago {
                    // The 5 fixed island discs are structural — the count is
                    // exactly 5, not merely "within 3..=30" (r2 Finding B).
                    assert_eq!(
                        comps.len(),
                        5,
                        "{profile:?}/{scale:?} seed {seed}: {} land components (expected 5 island discs)",
                        comps.len()
                    );
                    assert!(
                        (largest as f32) < 0.60 * land_total as f32,
                        "{profile:?}/{scale:?} seed {seed}: largest {largest}/{land_total} ≥ 60%"
                    );
                } else {
                    assert!(
                        (largest as f32) >= 0.85 * land_total as f32,
                        "{profile:?}/{scale:?} seed {seed}: largest {largest}/{land_total} < 85%"
                    );
                }
            }
        }
    }
}

/// Criterion #6 — sea level inside GEO_001's sane band.
#[test]
fn sea_level_in_band() {
    for scale in SCALES {
        for profile in PROFILES {
            let cs = CreativeSeed {
                world_scale: scale,
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(55, &cs);
            assert!(
                (8192..=57344).contains(&map.sea_level),
                "{scale:?}/{profile:?}: sea_level {} outside band",
                map.sea_level
            );
        }
    }
}

/// Connected-components flood-fill over land cells; returns component sizes.
fn land_components(map: &WorldMap) -> Vec<usize> {
    let n = map.cell_count();
    let mut seen = vec![false; n];
    let mut comps = Vec::new();
    for start in 0..n {
        if seen[start] || !map.is_land(start) {
            continue;
        }
        let mut size = 0usize;
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            size += 1;
            for &nb in &map.neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && map.is_land(nb) {
                    seen[nb] = true;
                    stack.push(nb);
                }
            }
        }
        comps.push(size);
    }
    comps
}
