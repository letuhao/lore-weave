//! Structural invariants — cell count, neighbour degree, symmetry, land
//! coherence, sea-level band. (Phase 1 acceptance criteria #3–#6.)

use world_gen::{
    BiomeKind, CoastlineProfile, CreativeSeed, PrevailingWind, RouteKind, SettlementRole,
    WaterBodyKind, WorldMap, WorldScale, generate,
};

/// Per-cell land-component id (`u32::MAX` for water). DFS over `neighbors`.
fn component_of(map: &WorldMap) -> Vec<u32> {
    let n = map.cell_count();
    let mut comp = vec![u32::MAX; n];
    let mut next = 0u32;
    for start in 0..n {
        if comp[start] != u32::MAX || !map.is_land(start) {
            continue;
        }
        let id = next;
        next += 1;
        let mut stack = vec![start];
        comp[start] = id;
        while let Some(c) = stack.pop() {
            for &nb in &map.neighbors[c] {
                let nb = nb as usize;
                if comp[nb] == u32::MAX && map.is_land(nb) {
                    comp[nb] = id;
                    stack.push(nb);
                }
            }
        }
    }
    comp
}

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

/// The `Gigaplanet` scale (~501k cells) generates a valid, coherent map and is
/// deterministic. Kept out of the `SCALES` sweep on purpose — one generate at
/// this scale is seconds of work; sweeping it across every profile/seed (as
/// `land_coherence_per_profile` does) would run for many minutes.
///
/// `#[ignore]` — two 501k-cell generates run minutes in an unoptimized test
/// build. Run on demand: `cargo test --release -- --ignored gigaplanet`. The
/// criterion benchmark also exercises `generate` at this scale.
#[test]
#[ignore = "501k-cell scale — minutes in a debug build; run with --ignored"]
fn gigaplanet_generates_a_coherent_map() {
    let cs = CreativeSeed {
        world_scale: WorldScale::Gigaplanet,
        ..CreativeSeed::default()
    };
    let a = generate(20_260_518, &cs);

    let n = a.cell_count();
    assert_eq!(n, 501_264, "Gigaplanet cell count");
    assert!(a.verify_hash(), "fresh Gigaplanet map fails verify_hash");
    // every layer is fully populated at this scale.
    assert_eq!(a.climate.len(), n);
    assert_eq!(a.biome.len(), n);
    assert_eq!(a.province_of.len(), n);
    assert_eq!(a.culture_of.len(), n);
    assert!(!a.provinces.is_empty() && !a.states.is_empty());
    assert!(!a.settlements.is_empty() && !a.culture_regions.is_empty());
    assert!(!a.water_bodies.is_empty(), "a world map always has ocean");

    // deterministic — a second run is byte-identical.
    let b = generate(20_260_518, &cs);
    assert_eq!(a.content_hash, b.content_hash, "Gigaplanet not deterministic");
    assert_eq!(a, b);
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
                // Northern/Southern: compare mean **latitude** of cold vs warm
                // cells. (B2 sphere migration: `cell.lat()` replaces the old
                // `center.1` proxy — semantic is identical, more north = higher
                // latitude in Northern, lower in Southern.)
                HemisphereOrientation::Northern | HemisphereOrientation::Southern => {
                    let y = |i: usize| map.cells[i].lat();
                    let (Some(cold_y), Some(warm_y)) =
                        (mean_climate(&map, cold, y), mean_climate(&map, warm, y))
                    else {
                        continue;
                    };
                    checked += 1;
                    if hemi == HemisphereOrientation::Northern {
                        assert!(
                            cold_y > warm_y,
                            "Northern seed {seed}: cold mean-lat {cold_y} not poleward of warm {warm_y}"
                        );
                    } else {
                        assert!(
                            cold_y < warm_y,
                            "Southern seed {seed}: cold mean-lat {cold_y} not poleward of warm {warm_y}"
                        );
                    }
                }
                // Equatorial: both poles are cold → cold sits farther from the
                // equator (compare mean |lat|, where equator lat=0).
                HemisphereOrientation::Equatorial => {
                    let pd = |i: usize| map.cells[i].lat().abs();
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

// ── Phase 3 — political / settlement / route / culture criteria ──────────

/// Criterion #3 — provinces partition the land totally; water has none.
#[test]
fn provinces_partition_land() {
    for profile in PROFILES {
        for seed in 0..8u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            assert_eq!(map.province_of.len(), map.cell_count());
            for i in 0..map.cell_count() {
                let p = map.province_of[i];
                if map.is_land(i) {
                    assert_ne!(p, u32::MAX, "{profile:?} seed {seed}: land cell {i} no province");
                    assert!((p as usize) < map.provinces.len(), "province id {p} out of range");
                } else {
                    assert_eq!(p, u32::MAX, "{profile:?} seed {seed}: water cell {i} has province");
                }
            }
            // criterion #3 — provinces.len() equals the apportioned n_prov.
            let land = (0..map.cell_count()).filter(|&i| map.is_land(i)).count();
            let comp = component_of(&map);
            let n_components = comp
                .iter()
                .copied()
                .filter(|&c| c != u32::MAX)
                .max()
                .map_or(0, |m| m as usize + 1);
            let n_prov = (land / 200).clamp(4, 80).max(n_components);
            assert_eq!(
                map.provinces.len(),
                n_prov,
                "{profile:?} seed {seed}: province count != apportioned n_prov"
            );
        }
    }
}

/// Criterion #4 — state↔province back-references are consistent; every state
/// has exactly one Capital settlement. Swept across every coastline profile
/// (Archipelago's multi-component case especially) — review-impl C8.
#[test]
fn states_have_exactly_one_capital() {
    for profile in PROFILES {
        for seed in 0..5u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            for st in &map.states {
                assert!((st.capital_province as usize) < map.provinces.len());
                assert_eq!(
                    map.provinces[st.capital_province as usize].state,
                    st.id,
                    "{profile:?} seed {seed}: state {} capital province not in the state",
                    st.id
                );
            }
            for p in &map.provinces {
                assert!(
                    (p.state as usize) < map.states.len(),
                    "{profile:?} province {} bad state",
                    p.id
                );
            }
            let mut caps = vec![0u32; map.states.len()];
            for s in &map.settlements {
                if s.role == SettlementRole::Capital {
                    let pid = map.province_of[s.cell as usize];
                    caps[map.provinces[pid as usize].state as usize] += 1;
                }
            }
            for (sid, &c) in caps.iter().enumerate() {
                assert_eq!(
                    c, 1,
                    "{profile:?} seed {seed}: state {sid} has {c} capitals (want 1)"
                );
            }
        }
    }
}

/// Criterion #5 — settlement cells are unique land cells; tier matches role.
/// Swept across coastline profiles and both density extremes — review-impl C8.
#[test]
fn settlements_unique_land_cells() {
    use world_gen::SettlementDensity;
    for profile in PROFILES {
        for density in [SettlementDensity::Sparse, SettlementDensity::Dense] {
            for seed in 0..3u64 {
                let cs = CreativeSeed {
                    coastline_profile: profile,
                    settlement_density: density,
                    ..CreativeSeed::default()
                };
                let map = generate(seed, &cs);
                let mut cells: Vec<u32> = map.settlements.iter().map(|s| s.cell).collect();
                let count = cells.len();
                cells.sort_unstable();
                cells.dedup();
                assert_eq!(
                    cells.len(),
                    count,
                    "{profile:?}/{density:?} seed {seed}: duplicate settlement cells"
                );
                for s in &map.settlements {
                    assert!(
                        map.is_land(s.cell as usize),
                        "{profile:?}/{density:?} seed {seed}: settlement on water"
                    );
                    let want = match s.role {
                        SettlementRole::Capital => 5,
                        SettlementRole::City => 4,
                        SettlementRole::Town => 3,
                        SettlementRole::Village | SettlementRole::Fortress => 2,
                        SettlementRole::Hamlet => 1,
                    };
                    assert_eq!(
                        s.population_tier, want,
                        "{profile:?}/{density:?} seed {seed}: tier/role mismatch"
                    );
                }
            }
        }
    }
}

/// Criterion #6 — routes dedup per (kind,pair); the Road sub-graph is
/// connected within every land component holding ≥2 road-eligible settlements.
#[test]
fn routes_dedup_and_roads_connected() {
    for seed in 0..6u64 {
        let map = generate(seed, &CreativeSeed::default());
        let n = map.cell_count() as u32;
        // valid cells + dedup per (kind tag, lo, hi)
        let mut keys: Vec<(u8, u32, u32)> = Vec::new();
        for r in &map.routes {
            assert!(r.from_cell < n && r.to_cell < n, "seed {seed}: route cell out of range");
            let lo = r.from_cell.min(r.to_cell);
            let hi = r.from_cell.max(r.to_cell);
            keys.push((r.kind as u8, lo, hi));
        }
        let count = keys.len();
        keys.sort_unstable();
        keys.dedup();
        assert_eq!(keys.len(), count, "seed {seed}: duplicate route");

        // Road connectivity per land component.
        let comp = component_of(&map);
        // tier>=2 settlement cells, with a union-find index each
        let road: Vec<u32> = map
            .settlements
            .iter()
            .filter(|s| s.population_tier >= 2)
            .map(|s| s.cell)
            .collect();
        let idx_of = |cell: u32| road.iter().position(|&c| c == cell);
        let mut parent: Vec<usize> = (0..road.len()).collect();
        fn find(p: &mut [usize], x: usize) -> usize {
            let mut r = x;
            while p[r] != r {
                r = p[r];
            }
            r
        }
        for r in &map.routes {
            if r.kind != RouteKind::Road {
                continue;
            }
            if let (Some(a), Some(b)) = (idx_of(r.from_cell), idx_of(r.to_cell)) {
                let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
                if ra != rb {
                    parent[ra.max(rb)] = ra.min(rb);
                }
            }
        }
        // for each land component, the road settlements in it must share one class
        let mut comp_class: std::collections::BTreeMap<u32, Vec<usize>> = Default::default();
        for (ri, &cell) in road.iter().enumerate() {
            comp_class.entry(comp[cell as usize]).or_default().push(ri);
        }
        for (cid, members) in comp_class {
            if members.len() < 2 {
                continue; // trivially satisfied
            }
            let root0 = find(&mut parent, members[0]);
            for &m in &members[1..] {
                assert_eq!(
                    find(&mut parent, m),
                    root0,
                    "seed {seed}: component {cid} road sub-graph not connected"
                );
            }
        }
    }
}

/// `k < n_components`: only `k` components get a hearth, the rest fall back
/// to culture 0 — exercises the otherwise-uncovered branch (review-impl #1).
#[test]
fn culture_fewer_than_components_falls_back() {
    let cs = CreativeSeed {
        coastline_profile: CoastlineProfile::Archipelago, // 5 land components
        culture_count: 2,
        ..CreativeSeed::default()
    };
    for seed in 0..6u64 {
        let map = generate(seed, &cs);
        assert_eq!(
            map.culture_regions.len(),
            2,
            "seed {seed}: culture_count 2 → 2 regions"
        );
        for i in 0..map.cell_count() {
            if map.is_land(i) {
                assert!(
                    (map.culture_of[i] as usize) < 2,
                    "seed {seed}: land cell {i} bad culture {}",
                    map.culture_of[i]
                );
            } else {
                assert_eq!(map.culture_of[i], u32::MAX, "seed {seed}: water has culture");
            }
        }
    }
}

/// Criterion #7 — culture partitions the land; water has none.
#[test]
fn culture_partitions_land() {
    for profile in PROFILES {
        for seed in 0..6u64 {
            let cs = CreativeSeed {
                coastline_profile: profile,
                ..CreativeSeed::default()
            };
            let map = generate(seed, &cs);
            // criterion #7 — culture_regions.len() == culture_count.clamp(1,16).
            assert_eq!(
                map.culture_regions.len(),
                5,
                "{profile:?} seed {seed}: culture count (default 5)"
            );
            assert_eq!(map.culture_of.len(), map.cell_count());
            for i in 0..map.cell_count() {
                let c = map.culture_of[i];
                if map.is_land(i) {
                    assert!(
                        (c as usize) < map.culture_regions.len(),
                        "{profile:?} seed {seed}: land cell {i} bad culture {c}"
                    );
                } else {
                    assert_eq!(c, u32::MAX, "{profile:?} seed {seed}: water cell {i} has culture");
                }
            }
        }
    }
}

/// review-impl C4 — the multi-kind route system is live. The prior
/// `routes_dedup_and_roads_connected` asserted only Road connectivity, so
/// SeaLane / MountainPass could (and did) silently generate nothing. This
/// pins that they actually fire, and that every route carries a real path.
#[test]
fn route_kinds_are_generated() {
    use world_gen::RouteKind;

    // Archipelago: 5 island land components → the SeaLane MST must bridge
    // them; every inhabited, sea-reachable island joins the tree.
    let arch = CreativeSeed {
        coastline_profile: CoastlineProfile::Archipelago,
        ..CreativeSeed::default()
    };
    for seed in 0..6u64 {
        let map = generate(seed, &arch);
        let sealanes = map
            .routes
            .iter()
            .filter(|r| r.kind == RouteKind::SeaLane)
            .count();
        assert!(
            sealanes >= 1,
            "archipelago seed {seed}: no SeaLane — islands left unreachable"
        );
    }

    // A continent's mountainous interior must yield MountainPass chokepoints.
    let mut mountain_pass_seen = false;
    for seed in 0..6u64 {
        let map = generate(seed, &CreativeSeed::default());
        if map.routes.iter().any(|r| r.kind == RouteKind::MountainPass) {
            mountain_pass_seen = true;
        }
    }
    assert!(
        mountain_pass_seen,
        "no MountainPass generated across six continent seeds"
    );

    // Every route carries a ≥2-cell path whose ends match from/to_cell.
    for seed in 0..4u64 {
        let map = generate(seed, &CreativeSeed::default());
        for r in &map.routes {
            assert!(
                r.path.len() >= 2,
                "seed {seed}: {:?} route has a degenerate path",
                r.kind
            );
            assert_eq!(r.path[0], r.from_cell, "seed {seed}: path[0] != from_cell");
            assert_eq!(
                *r.path.last().unwrap(),
                r.to_cell,
                "seed {seed}: path end != to_cell"
            );
        }
    }
}

/// review-impl finding 1 — the orographic wind must thread through `generate`
/// and actually reshape the world. Flipping the prevailing wind has to change
/// the climate layer (and so the content hash); a refactor that dropped
/// `cs.prevailing_wind` would otherwise leave every other test green.
#[test]
fn prevailing_wind_reshapes_the_climate() {
    let west = CreativeSeed {
        prevailing_wind: PrevailingWind::West,
        ..CreativeSeed::default()
    };
    let east = CreativeSeed {
        prevailing_wind: PrevailingWind::East,
        ..CreativeSeed::default()
    };
    let a = generate(42, &west);
    let b = generate(42, &east);
    assert_ne!(
        a.climate, b.climate,
        "flipping the prevailing wind left the climate layer identical"
    );
    assert_ne!(
        a.content_hash, b.content_hash,
        "a wind-changed climate must change the content hash"
    );
}

/// Feature extraction partitions its biome: on a real generated map every cell
/// of a given biome lands in exactly one extracted entity, and every entity
/// cell really has that biome. Covers ranges, rivers, and water bodies.
#[test]
fn extracted_features_partition_their_biomes() {
    for seed in 0..4u64 {
        let map = generate(seed, &CreativeSeed::default());

        let ranges: Vec<&[u32]> =
            map.mountain_ranges.iter().map(|r| r.cells.as_slice()).collect();
        check_partition(seed, "range", &ranges, &map.biome, BiomeKind::Mountain);

        let rivers: Vec<&[u32]> = map.rivers.iter().map(|r| r.cells.as_slice()).collect();
        check_partition(seed, "river", &rivers, &map.biome, BiomeKind::River);

        // Each water body's cells match its kind; together they cover all water.
        for wb in &map.water_bodies {
            let want = match wb.kind {
                WaterBodyKind::Sea => BiomeKind::Ocean,
                WaterBodyKind::Lake => BiomeKind::Lake,
            };
            for &c in &wb.cells {
                assert_eq!(
                    map.biome[c as usize], want,
                    "seed {seed}: water-body cell {c} has the wrong biome"
                );
            }
        }
        let body_cells: usize = map.water_bodies.iter().map(|w| w.cells.len()).sum();
        let water_cells = map.biome.iter().filter(|b| b.is_water()).count();
        assert_eq!(
            body_cells, water_cells,
            "seed {seed}: water bodies must cover exactly the Ocean+Lake cells"
        );
    }
}

/// Assert the `entities`' cell lists partition exactly the `kind`-biome cells.
fn check_partition(
    seed: u64,
    label: &str,
    entities: &[&[u32]],
    biome: &[BiomeKind],
    kind: BiomeKind,
) {
    let mut seen = vec![false; biome.len()];
    for cells in entities {
        for &c in *cells {
            assert!(!seen[c as usize], "seed {seed}: cell {c} is in two {label}s");
            seen[c as usize] = true;
            assert_eq!(
                biome[c as usize], kind,
                "seed {seed}: {label} cell {c} has the wrong biome"
            );
        }
    }
    for (c, &b) in biome.iter().enumerate() {
        if b == kind {
            assert!(seen[c], "seed {seed}: a {kind:?} cell {c} is in no {label}");
        }
    }
}
