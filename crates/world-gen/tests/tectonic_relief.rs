//! Elevation-redesign **S1+S2** acceptance gate.
//!
//! S1 (relief amplified from the tectonic uplift field) + S2 (a plate model
//! that actually collides) together make terrain elevation depend on plate
//! convergence — visibly and reliably:
//!
//! - **Concentration / fill** — high-relief land traces the convergent belts
//!   (`belts_fill_and_concentrate`).
//! - **Boundary realism** — all six `BoundaryKind`s fire across a seed sweep
//!   (incl. `FoldMountain`), `Fault` is a minority, and almost no world is left
//!   pancake-flat (`boundary_kinds_fire_and_few_flat_worlds`).
//!
//! Spec: `docs/specs/2026-05-31-elevation-redesign.md`;
//! plan: `docs/plans/2026-05-31-elevation-s1-uplift-relief.md`.
//!
//! Metric is **climate-independent**: a "high-relief" cell is one in the
//! Mountain *elevation* band (`land_t ≥ 0.55`), counting Mountain and the cold
//! `Glacier`-labelled high belts alike. (The spec's "0 % of Mountain cells near
//! convergent" was a measurement artifact of counting only the Mountain biome.)

use world_gen::{BiomeKind, BoundaryKind, CreativeSeed, PlateKind, WorldMap, WorldScale, generate};

/// Convergent boundary kinds — where crust collides and orogeny lifts mountains.
fn is_convergent(k: BoundaryKind) -> bool {
    matches!(
        k,
        BoundaryKind::FoldMountain | BoundaryKind::Subduction | BoundaryKind::IslandArc
    )
}

/// How many BFS hops from a convergent boundary count as inside the **collision
/// highland belt** — the orogeny ridge (~4 hops) plus the broad isostatic
/// plateau S3 stacks on top (crustal thickening, `PLATEAU_HOPS`). Measured conc
/// by window: ≤2 54 %, ≤3 77 %, **≤4 98 %**, ≤6 100 % — high-relief is tightly
/// collision-driven, just broader than a bare ridge once the plateau is added.
const NEAR_HOPS: u32 = 4;

/// A cell's land-elevation tier `(elev−sea)/(65535−sea)` (only meaningful for
/// land). `≥ 0.55` is the Mountain elevation band biome uses.
fn land_t(map: &WorldMap, c: usize) -> f64 {
    let sea = map.sea_level;
    f64::from(map.cells[c].elevation.saturating_sub(sea)) / f64::from((65535 - sea).max(1))
}

/// High-relief = land cell in the Mountain elevation band, climate-independent.
fn is_high_relief(map: &WorldMap, c: usize) -> bool {
    map.is_land(c) && land_t(map, c) >= 0.55
}

/// Plate-pair → boundary kind (unordered, plate_a < plate_b).
fn pair_kind(map: &WorldMap, a: u32, b: u32) -> BoundaryKind {
    let (lo, hi) = if a < b { (a, b) } else { (b, a) };
    map.plate_boundaries
        .iter()
        .find(|pb| pb.plate_a == lo && pb.plate_b == hi)
        .map_or(BoundaryKind::Interior, |pb| pb.kind)
}

/// Multi-source BFS hop distance from any cell satisfying `seed_pred`, capped at
/// `cap`. `u32::MAX` ⇒ farther than `cap`.
fn bfs_from<F: Fn(usize) -> bool>(map: &WorldMap, cap: u32, seed_pred: F) -> Vec<u32> {
    let n = map.cell_count();
    let mut dist = vec![u32::MAX; n];
    let mut frontier: Vec<u32> = Vec::new();
    for c in 0..n {
        if seed_pred(c) {
            dist[c] = 0;
            frontier.push(c as u32);
        }
    }
    let mut d = 0u32;
    while !frontier.is_empty() && d < cap {
        let mut next = Vec::new();
        for &c in &frontier {
            for &nb in &map.neighbors[c as usize] {
                let nb = nb as usize;
                if dist[nb] == u32::MAX {
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

/// Cell is a *convergent* boundary cell (≥1 neighbour on a different plate whose
/// pair-boundary is convergent).
fn at_convergent(map: &WorldMap, c: usize) -> bool {
    let pa = map.plate_of[c];
    map.neighbors[c].iter().any(|&nb| {
        let pb = map.plate_of[nb as usize];
        pb != pa && is_convergent(pair_kind(map, pa, pb))
    })
}

/// Cell is continental land ≤1 hop from a continental-arc (Subduction/Fold)
/// boundary — i.e. a cell that *should* be raised into an arc.
fn continental_arc(map: &WorldMap, arc_dist: &[u32], c: usize) -> bool {
    arc_dist[c] <= 1
        && map.is_land(c)
        && map.plates[map.plate_of[c] as usize].kind == PlateKind::Continental
}

/// **High-relief land traces the convergent belts** — across a seed/scale sweep,
/// a strong share of high-relief cells lies on/near a convergent boundary
/// (concentration), and convergent-arc bands fill into ranges rather than
/// speckle (fill). Both aggregated to be seed-robust.
#[test]
fn belts_fill_and_concentrate() {
    let seeds: [u64; 6] = [7, 13, 42, 99, 123, 2024];
    let scales = [WorldScale::Continent, WorldScale::SuperContinent];

    let (mut high, mut high_near) = (0usize, 0usize);
    let (mut arc, mut arc_high) = (0usize, 0usize);
    let mut lines: Vec<String> = Vec::new();
    for scale in scales {
        for &seed in &seeds {
            let cs = CreativeSeed { world_scale: scale, ..CreativeSeed::default() };
            let map = generate(seed, &cs);
            let n = map.cell_count();

            let conv = bfs_from(&map, NEAR_HOPS, |c| at_convergent(&map, c));
            let arc_dist = bfs_from(&map, 1, |c| {
                let pa = map.plate_of[c];
                map.neighbors[c].iter().any(|&nb| {
                    let pb = map.plate_of[nb as usize];
                    pb != pa
                        && matches!(
                            pair_kind(&map, pa, pb),
                            BoundaryKind::Subduction | BoundaryKind::FoldMountain
                        )
                })
            });

            let (mut h, mut hn, mut a, mut ah) = (0usize, 0usize, 0usize, 0usize);
            for c in 0..n {
                if is_high_relief(&map, c) {
                    h += 1;
                    if conv[c] != u32::MAX {
                        hn += 1;
                    }
                }
                if continental_arc(&map, &arc_dist, c) {
                    a += 1;
                    if is_high_relief(&map, c) {
                        ah += 1;
                    }
                }
            }
            high += h;
            high_near += hn;
            arc += a;
            arc_high += ah;
            lines.push(format!(
                "  {scale:?} seed {seed}: high {h}, near-conv {:.0}%, arc-fill {:.0}%",
                if h == 0 { 0.0 } else { 100.0 * hn as f64 / h as f64 },
                if a == 0 { 0.0 } else { 100.0 * ah as f64 / a as f64 },
            ));
        }
    }

    let report = lines.join("\n");
    let conc = 100.0 * high_near as f64 / high.max(1) as f64;
    let fill = 100.0 * arc_high as f64 / arc.max(1) as f64;
    eprintln!("belts_fill_and_concentrate:\n{report}\n  AGG conc≤{NEAR_HOPS} {conc:.0}%, arc-fill {fill:.0}%");

    assert!(high > 0, "no high-relief cells produced across the sweep\n{report}");
    assert!(arc > 0, "no continental-arc cells across the sweep\n{report}");
    assert!(
        conc >= 85.0,
        "only {conc:.0}% of high-relief cells lie within ≤{NEAR_HOPS} hops of a \
         convergent boundary (target ≥ 85% — high-relief must trace the collision \
         highland belt, not appear as noise elsewhere).\n{report}"
    );
    // 40% is a deliberate regression floor a few points below the measured ~45%
    // — a material terrain change that thins the belts *should* trip this.
    assert!(
        fill >= 40.0,
        "continental-arc bands only {fill:.0}% high-relief (target ≥ 40%): collisions \
         fail to raise continuous ranges.\n{report}"
    );
}

/// **No over-mountaining** — the S1+S2 relief boost must not flip continents
/// into all-mountain: high-relief (Mountain + Glacier) stays a land minority and
/// lowland biomes (Plain/Forest/Jungle/Desert/Hill/Coast…) still dominate. Guards
/// the plan's stated over-fill risk + the biome-proportion regression.
#[test]
fn mountains_stay_a_land_minority() {
    let seeds: [u64; 6] = [7, 13, 42, 99, 123, 2024];
    let (mut land, mut high, mut lowland) = (0usize, 0usize, 0usize);
    let mut lines: Vec<String> = Vec::new();
    for &seed in &seeds {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let map = generate(seed, &cs);
        let (mut l, mut h, mut low) = (0usize, 0usize, 0usize);
        for c in 0..map.cell_count() {
            if !map.is_land(c) {
                continue;
            }
            l += 1;
            match map.biome[c] {
                BiomeKind::Mountain | BiomeKind::Glacier => h += 1,
                BiomeKind::Plain | BiomeKind::Forest | BiomeKind::Jungle | BiomeKind::Desert => {
                    low += 1
                }
                _ => {}
            }
        }
        land += l;
        high += h;
        lowland += low;
        lines.push(format!(
            "  seed {seed}: land {l}, high {:.0}%, lowland {:.0}%",
            100.0 * h as f64 / l.max(1) as f64,
            100.0 * low as f64 / l.max(1) as f64,
        ));
    }
    let high_pct = 100.0 * high as f64 / land.max(1) as f64;
    let low_pct = 100.0 * lowland as f64 / land.max(1) as f64;
    eprintln!("mountains_stay_a_land_minority:\n{}\n  AGG high {high_pct:.0}%, lowland {low_pct:.0}%", lines.join("\n"));
    assert!(
        high_pct <= 40.0,
        "high-relief (Mountain+Glacier) is {high_pct:.0}% of land — over-mountained (target ≤ 40%)"
    );
    assert!(
        low_pct >= 25.0,
        "lowland biomes only {low_pct:.0}% of land — continents lost their plains (target ≥ 25%)"
    );
}

/// **Biome/climate proportion regression** (plan-required per stage) — the
/// S1+S2 relief/collision boost must not skew the carefully-tuned land mix:
/// `Desert` stays in a sane band (the session's origin metric — guard against
/// monotony returning *or* collapsing), land fraction stays Earth-like (guard
/// against rifts sinking continents or arcs welding them), and `Marsh` doesn't
/// explode (guard against the interior-upland erosion feeding runaway wetlands).
/// Wide tripwires, not tight pins — baseline at commit: Desert 19.7 %, land
/// 27.6 %, Marsh small.
#[test]
fn terrain_proportions_stay_in_band() {
    let seeds: [u64; 6] = [7, 13, 42, 99, 123, 2024];
    let (mut cells, mut land, mut desert, mut marsh) = (0usize, 0usize, 0usize, 0usize);
    for &seed in &seeds {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let map = generate(seed, &cs);
        cells += map.cell_count();
        for c in 0..map.cell_count() {
            if !map.is_land(c) {
                continue;
            }
            land += 1;
            match map.biome[c] {
                BiomeKind::Desert => desert += 1,
                BiomeKind::Marsh => marsh += 1,
                _ => {}
            }
        }
    }
    let land_pct = 100.0 * land as f64 / cells.max(1) as f64;
    let desert_pct = 100.0 * desert as f64 / land.max(1) as f64;
    let marsh_pct = 100.0 * marsh as f64 / land.max(1) as f64;
    eprintln!(
        "terrain_proportions_stay_in_band: land {land_pct:.1}% of cells, \
         Desert {desert_pct:.1}% of land, Marsh {marsh_pct:.1}% of land"
    );
    assert!(
        (18.0..=42.0).contains(&land_pct),
        "land fraction {land_pct:.1}% out of band [18,42] — continents welded or sank"
    );
    assert!(
        (10.0..=35.0).contains(&desert_pct),
        "Desert {desert_pct:.1}% of land out of band [10,35] — climate mix skewed"
    );
    assert!(
        marsh_pct <= 20.0,
        "Marsh {marsh_pct:.1}% of land > 20% — interior-upland erosion may be flooding lowland"
    );
}

/// **Bimodal hypsometry (S3, D6)** — the elevation distribution has two modes,
/// an ocean mode below sea level and a continental mode at/above it, separated
/// by an antimode (the shoreline dip) strictly lower than both. This is the
/// realism target (NOAA ETOPO1); locked so a later stage can't collapse it.
#[test]
fn elevation_histogram_is_bimodal() {
    const NB: usize = 20;
    let seeds = [7u64, 13, 42, 99, 123, 2024];
    let mut hist = [0u64; NB];
    let mut sea_acc = 0usize;
    for &s in &seeds {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let m = generate(s, &cs);
        sea_acc += (m.sea_level as usize) * NB / 65536;
        for c in 0..m.cell_count() {
            let b = ((m.cells[c].elevation as usize) * NB / 65536).min(NB - 1);
            hist[b] += 1;
        }
    }
    let sea_bin = (sea_acc / seeds.len()).clamp(1, NB - 2);
    let ocean_mode = (0..sea_bin).max_by_key(|&b| hist[b]).unwrap();
    let land_mode = (sea_bin..NB).max_by_key(|&b| hist[b]).unwrap();
    let antimode = (ocean_mode + 1..land_mode).min_by_key(|&b| hist[b]).unwrap_or(sea_bin);
    eprintln!(
        "elevation_histogram_is_bimodal: sea≈bin {sea_bin}, ocean_mode {ocean_mode} ({}), \
         antimode {antimode} ({}), land_mode {land_mode} ({})",
        hist[ocean_mode], hist[antimode], hist[land_mode]
    );
    assert!(ocean_mode < sea_bin, "ocean mode {ocean_mode} not below sea bin {sea_bin}");
    assert!(land_mode >= sea_bin, "land mode {land_mode} not at/above sea bin {sea_bin}");
    assert!(
        hist[antimode] < hist[ocean_mode] && hist[antimode] < hist[land_mode],
        "no antimode dip between modes — not bimodal (ocean {}, antimode {}, land {})",
        hist[ocean_mode], hist[antimode], hist[land_mode]
    );
}

/// **The plate model collides** — over a wide seed sweep all six non-interior
/// `BoundaryKind`s fire (incl. continent–continent `FoldMountain`), `Fault` is a
/// minority (not the ~78% the old `tangential > |normal|` test produced), and
/// almost no world is left pancake-flat.
#[test]
fn boundary_kinds_fire_and_few_flat_worlds() {
    const SEEDS: u64 = 60;
    let mut kind_seeds = [0u32; 7]; // seeds containing each BoundaryKind tag
    let mut flat = 0u32;
    let mut fault_frac_sum = 0.0f64;

    let mut lines: Vec<String> = Vec::new();
    for seed in 1..=SEEDS {
        let cs = CreativeSeed { world_scale: WorldScale::Continent, ..CreativeSeed::default() };
        let map = generate(seed, &cs);

        let mut present = [false; 7];
        let mut faults = 0u32;
        for b in &map.plate_boundaries {
            present[b.kind.tag() as usize] = true;
            if b.kind == BoundaryKind::Fault {
                faults += 1;
            }
        }
        for (t, &p) in present.iter().enumerate() {
            if p {
                kind_seeds[t] += 1;
            }
        }
        if !map.plate_boundaries.is_empty() {
            fault_frac_sum += f64::from(faults) / map.plate_boundaries.len() as f64;
        }
        let max_lt = (0..map.cell_count())
            .filter(|&c| map.is_land(c))
            .map(|c| land_t(&map, c))
            .fold(0.0_f64, f64::max);
        if max_lt < 0.55 {
            flat += 1;
        }
    }

    let names = ["Interior", "Fold", "Subduction", "IslandArc", "Ridge", "Rift", "Fault"];
    for (t, n) in kind_seeds.iter().enumerate().skip(1) {
        lines.push(format!("  {:<11} {n}/{SEEDS}", names[t]));
    }
    let fault_mean = 100.0 * fault_frac_sum / SEEDS as f64;
    eprintln!(
        "boundary_kinds_fire_and_few_flat_worlds:\n{}\n  fault-mean {fault_mean:.0}%, flat {flat}/{SEEDS}",
        lines.join("\n")
    );

    // All six non-interior kinds must fire somewhere in the sweep.
    for (t, name) in names.iter().enumerate().skip(1) {
        assert!(kind_seeds[t] > 0, "{name} (tag {t}) never fired across {SEEDS} seeds");
    }
    // FoldMountain is the rarest (needs adjacent converging continental plates);
    // require it in a meaningful share, not just once, so a future regression
    // that suppresses collisions is caught.
    assert!(
        kind_seeds[1] >= SEEDS as u32 / 5,
        "FoldMountain fired in only {}/{SEEDS} seeds (expected ≥ 20%)",
        kind_seeds[1]
    );
    assert!(
        fault_mean <= 50.0,
        "Fault still dominates: mean {fault_mean:.0}% of boundaries (target ≤ 50%)"
    );
    assert!(
        flat <= SEEDS as u32 / 10,
        "{flat}/{SEEDS} worlds are pancake-flat (max_land_t < 0.55) — collisions too rare \
         (target ≤ 10%)"
    );
}
