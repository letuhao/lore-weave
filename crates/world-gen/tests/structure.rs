//! Structural invariants — cell count, neighbour degree, symmetry, land
//! coherence, sea-level band. (Phase 1 acceptance criteria #3–#6.)

use world_gen::{BiomeKind, CoastlineProfile, CreativeSeed, WorldMap, WorldScale, generate};

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

// ── Phase 2 — climate / biome / river criteria ───────────────────────────

/// Criterion #3 — every `Highland` climate cell sits above the elevation
/// threshold (`elev_norm > 0.62`). Universal property → seed sweep.
#[test]
fn climate_highland_implies_high_elevation() {
    for profile in PROFILES {
        for seed in 0..12u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            for (i, &zone) in map.climate.iter().enumerate() {
                if zone == world_gen::ClimateZone::Highland {
                    let elev_norm = f32::from(map.cells[i].elevation) / 65535.0;
                    assert!(
                        elev_norm > 0.62,
                        "{profile:?} seed {seed} cell {i}: Highland but elev_norm {elev_norm}"
                    );
                }
            }
        }
    }
}

/// Criterion #4 — water cells are Ocean/Lake, land cells are neither;
/// every layer is parallel. Universal property → seed sweep.
#[test]
fn biome_water_land_consistency() {
    for scale in [WorldScale::Pocket, WorldScale::Continent] {
        for seed in 0..12u64 {
            let cs = CreativeSeed {
                world_scale: scale,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            let n = map.cell_count();
            assert_eq!(map.biome.len(), n);
            assert_eq!(map.climate.len(), n);
            assert_eq!(map.river_flux.len(), n);
            assert_eq!(map.is_coast.len(), n);
            for i in 0..n {
                let water_by_elev = !map.is_land(i);
                let water_by_biome = map.biome[i].is_water();
                assert_eq!(
                    water_by_elev, water_by_biome,
                    "{scale:?} seed {seed} cell {i}: elevation/biome water disagreement ({:?})",
                    map.biome[i]
                );
            }
        }
    }
}

/// Criterion #5 — every `River` cell has a neighbour that is a water biome
/// or carries strictly greater flux (no land dead-end). Seed sweep.
#[test]
fn rivers_descend_to_water() {
    for profile in PROFILES {
        for seed in 0..12u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            for i in 0..map.cell_count() {
                if map.biome[i] != BiomeKind::River {
                    continue;
                }
                let descends = map.neighbors[i].iter().any(|&nb| {
                    let nb = nb as usize;
                    map.biome[nb].is_water() || map.river_flux[nb] > map.river_flux[i]
                });
                assert!(
                    descends,
                    "{profile:?} seed {seed} River cell {i} dead-ends on land (flux {})",
                    map.river_flux[i]
                );
            }
        }
    }
}

/// Criterion #6 — biomes form contiguous patches: ≥ 85 % of land cells have
/// ≥1 same-biome neighbour. Universal property → seed sweep.
#[test]
fn biome_patch_coherence() {
    for profile in PROFILES {
        for seed in 0..12u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            let mut land = 0u32;
            let mut patched = 0u32;
            for i in 0..map.cell_count() {
                if !map.is_land(i) {
                    continue;
                }
                land += 1;
                if map.neighbors[i]
                    .iter()
                    .any(|&nb| map.biome[nb as usize] == map.biome[i])
                {
                    patched += 1;
                }
            }
            assert!(land > 0, "{profile:?} seed {seed}: no land");
            let frac = patched as f32 / land as f32;
            assert!(
                frac >= 0.85,
                "{profile:?} seed {seed}: only {frac} of land cells have a same-biome neighbour"
            );
        }
    }
}

/// Criterion #7 — realised land fraction is near the profile target, or the
/// sea level floored at its best-effort minimum (clears DEFERRED #013).
#[test]
fn land_fraction_near_target() {
    for profile in [
        CoastlineProfile::Island,
        CoastlineProfile::Peninsula,
        CoastlineProfile::Coastal,
        CoastlineProfile::Inland,
    ] {
        for seed in 0..16u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            let land = (0..map.cell_count()).filter(|&i| map.is_land(i)).count();
            let frac = land as f32 / map.cell_count() as f32;
            let target = profile.land_fraction();
            // The 8192 best-effort floor still gets a (looser) finite bound:
            // a bare `|| sea_level == 8192` would never check `frac` for the
            // `inland` profile, which always floors (code-review r2 WARN-1).
            let ok =
                frac >= target - 0.08 || (map.sea_level == 8192 && frac >= target - 0.18);
            assert!(
                ok,
                "{profile:?} seed {seed}: land fraction {frac} vs target {target} \
                 (sea_level {})",
                map.sea_level
            );
        }
    }
}

/// Mean of `value(i)` over the cells whose climate satisfies `want`.
fn mean_climate<V: Fn(usize) -> f32>(
    map: &WorldMap,
    want: impl Fn(world_gen::ClimateZone) -> bool,
    value: V,
) -> Option<f32> {
    let vs: Vec<f32> = (0..map.cell_count())
        .filter(|&i| want(map.climate[i]))
        .map(value)
        .collect();
    (!vs.is_empty()).then(|| vs.iter().sum::<f32>() / vs.len() as f32)
}

/// Criterion #3 — the hemisphere flip is correct: cold zones cluster toward
/// the pole (Northern → high `y`, Southern → low `y`, Equatorial → both map
/// edges). End-to-end check of the per-hemisphere latitude wiring, all three
/// orientations (review-impl Finding 1).
#[test]
fn hemisphere_flip_orients_climate() {
    use world_gen::{ClimateZone, HemisphereOrientation};
    let cold = |z: ClimateZone| matches!(z, ClimateZone::Polar | ClimateZone::Boreal);
    let warm = |z: ClimateZone| matches!(z, ClimateZone::Tropical | ClimateZone::Subtropical);
    let mut checked = 0u32;

    for seed in 0..8u64 {
        for hemi in [
            HemisphereOrientation::Northern,
            HemisphereOrientation::Southern,
            HemisphereOrientation::Equatorial,
        ] {
            let cs = CreativeSeed {
                hemisphere_orientation: hemi,
                world_scale: WorldScale::Continent,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            match hemi {
                // Northern/Southern: compare mean y of cold vs warm cells.
                HemisphereOrientation::Northern | HemisphereOrientation::Southern => {
                    let y = |i: usize| map.cells[i].center.1;
                    let (Some(cold_y), Some(warm_y)) =
                        (mean_climate(&map, cold, y), mean_climate(&map, warm, y))
                    else {
                        continue;
                    };
                    checked += 1;
                    if hemi == HemisphereOrientation::Northern {
                        assert!(
                            cold_y > warm_y,
                            "Northern seed {seed}: cold mean-y {cold_y} not poleward of warm {warm_y}"
                        );
                    } else {
                        assert!(
                            cold_y < warm_y,
                            "Southern seed {seed}: cold mean-y {cold_y} not poleward of warm {warm_y}"
                        );
                    }
                }
                // Equatorial: both edges are polar → cold sits farther from
                // y=0.5 (compare mean |y-0.5|, not mean y, which would ~0.5).
                HemisphereOrientation::Equatorial => {
                    let pd = |i: usize| (map.cells[i].center.1 - 0.5).abs();
                    let (Some(cold_d), Some(warm_d)) =
                        (mean_climate(&map, cold, pd), mean_climate(&map, warm, pd))
                    else {
                        continue;
                    };
                    checked += 1;
                    assert!(
                        cold_d > warm_d,
                        "Equatorial seed {seed}: cold mean |Δy| {cold_d} not > warm {warm_d}"
                    );
                }
            }
        }
    }
    assert!(checked > 0, "hemisphere test was vacuous — no seed had both bands");
}
