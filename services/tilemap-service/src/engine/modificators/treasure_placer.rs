//! TMP_006 §3 — the `TreasurePlacer` modificator. Per zone, per author tier
//! (high-`max` first): compose `target_count` treasure piles and place each via
//! the Phase-A `place_and_connect_object`, guarding the high-value ones with a
//! `MonsterLair`.
//!
//! Unlike `ObstaclePlacer`, treasures route through `place_and_connect_object`
//! — a pile must keep its zone connected and reachable (TMP_006 §4), so it
//! needs the gap-safety check, the distance oracle, and an access path.

use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

use crate::engine::build_state::TilemapBuildState;
use crate::engine::geometry::neighbors4;
use crate::engine::object_manager::{
    OptimizeType, PlacementError, choose_guard, place_and_connect_object,
};
use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::engine::treasure_pool::{TreasureObject, engine_treasure_pool};
use crate::engine::treasure_select::{compose_pile, min_distance};
use crate::seed::sub_seed;
use crate::types::object::TilemapObjectKind;
use crate::types::object_template::{FootprintCell, TilemapObjectTemplate};
use crate::types::template::TilemapTemplate;
use crate::types::tile_mask::TileMask;
use crate::types::treasure::TreasureTierSpec;
use crate::types::zone::{ZoneId, ZoneRole};

/// A pile of this value or more gets a `MonsterLair` guard (TMP_006 §3.5,
/// engine default).
const MIN_GUARD_VALUE: u32 = 2000;

/// TMP_006 §3 TreasurePlacer — tiered value-density treasure-pile placement.
#[derive(Debug)]
pub struct TreasurePlacer;

impl Modificator for TreasurePlacer {
    fn name(&self) -> &str {
        "treasure_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // TerrainPainter must paint terrain before `choose_guard` reads it;
        // `connections_placer` is unregistered in Phase C (the registry treats
        // an unregistered dependency as satisfied — pipeline D7) and orders the
        // §7-step-4 connection guards before treasures once Phase D lands.
        vec!["terrain_painter", "connections_placer"]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        let assets = TreasureAssets {
            pool: engine_treasure_pool(),
            pile_template: treasure_pile_template(),
            guard_template: guard_template(),
        };

        for zone_idx in 0..ctx.state.zones.len() {
            // A `Forbidden` zone is all-`Obstacle` — no `Open` area to place
            // into; skip it (D4).
            if ctx.state.zones[zone_idx].role == ZoneRole::Forbidden {
                continue;
            }
            let zone_id = ctx.state.zones[zone_idx].id.clone();
            let assigned_count = ctx.state.zones[zone_idx].assigned_tiles.count_ones();

            // D9 — effective tiers: the zone's own `treasure_tiers`, or, when
            // `inherit_treasure_from` is set, the inherited zone's literal
            // tiers. A zone with empty effective tiers contributes nothing.
            let mut tiers = resolve_effective_tiers(ctx.template, &zone_id);
            if tiers.is_empty() {
                continue;
            }
            // D4 — high-`max` first; the `min`/`density` sub-keys pin a
            // deterministic order for equal-`max` tiers, so the result never
            // rests on sort stability (TMP-A4).
            tiers.sort_by(|a, b| {
                b.max
                    .cmp(&a.max)
                    .then_with(|| b.min.cmp(&a.min))
                    .then_with(|| b.density.cmp(&a.density))
            });

            // D7 — a per-zone deterministic RNG sub-stream, so composition
            // sampling is order-independent across zones.
            let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(
                ctx.seed,
                &format!("treasure_placer:{}", zone_id.0),
            ));

            // TMP-Q4 HIGH-1 — pass each tier's post-sort position as its
            // `tier_index` for value-band visualization. `enumerate` index
            // is 0..N where 0 is the highest-`max` band of this zone.
            // Real authoring has 1-3 tiers per zone; if a pathological
            // template declares more than `u8::MAX` (256) tiers, we BREAK
            // — silent saturation would collide multiple tiers onto
            // index 255 (lossy). The skipped tiers' piles never get
            // placed; this is documented + accepted (template load has
            // no validation hook to reject upstream).
            //
            // LOW-5 from chunk-A /review-impl — emit a tracing::warn so an
            // author's ops dashboard surfaces the truncation rather than
            // silently dropping tiers. Mirrors the existing
            // `tilemap.density_reduced` info-event discipline (TMP-TR-Q4).
            let total_tiers = tiers.len();
            for (tier_pos, tier) in tiers.into_iter().enumerate() {
                let Ok(tier_index) = u8::try_from(tier_pos) else {
                    tracing::warn!(
                        zone = %zone_id.0,
                        declared_tiers = total_tiers,
                        placed_tiers = tier_pos,
                        "TMP-Q4: zone declares more than 256 treasure tiers; \
                         only the first 256 are placed (tier_index is u8)",
                    );
                    break;
                };
                place_tier(ctx.state, zone_idx, tier, tier_index, assigned_count, &assets, &mut rng, ctx.registry);
            }
        }
        Ok(())
    }
}

/// D9 — resolve a zone's **effective** treasure tiers.
///
/// `inherit_treasure_from: Some(y)` ⇒ zone `y`'s **literal** `treasure_tiers`
/// (this zone's own are ignored — REPLACE, not union); a dangling reference (no
/// such zone) ⇒ empty (no treasure, never a panic). Resolution is **one level,
/// non-transitive** — `y`'s own `inherit_treasure_from` is never chased, which
/// also makes an inheritance cycle structurally impossible. `None` ⇒ the zone's
/// own `treasure_tiers`.
fn resolve_effective_tiers(template: &TilemapTemplate, zone_id: &ZoneId) -> Vec<TreasureTierSpec> {
    let Some(spec) = template.zones.iter().find(|z| &z.zone_id == zone_id) else {
        // A build-state zone always has a matching `ZoneSpec`; this arm is
        // defensive — no spec, no tiers.
        return Vec::new();
    };
    match &spec.inherit_treasure_from {
        Some(source_id) => template
            .zones
            .iter()
            .find(|z| &z.zone_id == source_id)
            .map(|source| source.treasure_tiers.clone())
            .unwrap_or_default(),
        None => spec.treasure_tiers.clone(),
    }
}

/// The read-only engine data the per-tier placement loop needs — built once
/// per `process` call and shared across every zone and tier.
struct TreasureAssets {
    pool: Vec<TreasureObject>,
    pile_template: TilemapObjectTemplate,
    guard_template: TilemapObjectTemplate,
}

/// D4 / D6 — compose and place one tier's piles into zone `zone_idx`.
///
/// `target_count` is the §3.3 density target; a separate `emergency` counter,
/// bounded at `target_count`, caps **failures only** — a successful pile never
/// consumes budget (TMP_006 §3.3 / §4.4), so a clean zone reaches exactly
/// `target_count` piles and the realized count is a *soft* target.
#[allow(clippy::too_many_arguments)]
fn place_tier(
    state: &mut TilemapBuildState,
    zone_idx: usize,
    tier: TreasureTierSpec,
    tier_index: u8,
    assigned_count: usize,
    assets: &TreasureAssets,
    rng: &mut ChaCha8Rng,
    registry: &crate::registry::Registry,
) {
    // D6 — piles per zone-tile-thousand; the `as u32` truncation means a zone
    // with `density × tiles < 1000` holds no piles of this tier (intended).
    // Capped at the zone's current `Open`-tile count: a zone cannot hold more
    // 1×1 piles than it has `Open` tiles, so this bounds the loop against a
    // pathological author `density` (`u16`, up to 65535) without affecting any
    // realistic target (`density_target` is far below `open_count` in practice).
    let density_target = (tier.density as f32 * assigned_count as f32 / 1000.0) as u32;
    let open_count = state.zone_area_open(zone_idx).count_ones() as u32;
    let target_count = density_target.min(open_count);
    let mut placed: u32 = 0;
    let mut emergency: u32 = 0;
    // D6 — successes never touch `emergency`; only failures are capped, at
    // `target_count`, after which the loop stops (placement failure is normal).
    while placed < target_count && emergency < target_count {
        let Some(pile) = compose_pile(&assets.pool, tier, rng) else {
            // compose_pile → None — the pool could not reach `[min, max]`: a
            // failed composition (D6).
            emergency += 1;
            continue;
        };
        // D4 — recompute the `Open` area fresh: already-placed piles and
        // guards are `Occupied`, so they are excluded.
        let search_area = state.zone_area_open(zone_idx);
        let outcome = place_and_connect_object(
            state,
            zone_idx,
            &assets.pile_template,
            TilemapObjectKind::Treasure,
            Some(pile.value),
            Some(tier_index),
            &search_area,
            min_distance(pile.value),
            OptimizeType::BothDistanceAndCenter,
            registry,
        );
        match outcome {
            Ok(placement) => {
                placed += 1;
                // D5 — a pile worth `MIN_GUARD_VALUE`+ gets a MonsterLair guard.
                if pile.value >= MIN_GUARD_VALUE {
                    place_guard(
                        state,
                        zone_idx,
                        pile.value,
                        tier_index,
                        &placement.footprint,
                        &assets.guard_template,
                        registry,
                    );
                }
            }
            // D6 — the *pile's* NoSpace is a failed placement. A guard NoSpace
            // is handled inside `place_guard` and never reaches this counter.
            Err(PlacementError::NoSpace) => {
                emergency += 1;
            }
            Err(PlacementError::NoSuchZone(z)) => {
                // `zone_idx` ranges over `0..zones.len()`, so this is
                // unreachable — surface a wiring bug, never silently miscount.
                unreachable!("TreasurePlacer: pile placed into out-of-range zone {z}");
            }
        }
    }
}

/// D5 — place a `MonsterLair` guard beside a just-placed high-value pile.
///
/// The guard sits on an `Open` tile 4-adjacent to the pile footprint
/// (`OptimizeType::Center`, `min_distance` 0 — the guard is *meant* to be next
/// to the pile it guards). The search mask is **grid-dimensioned** — it starts
/// as the zone's `zone_area_open` (so it matches `place_and_connect_object`'s
/// dimension assert) and is intersected down to the footprint neighbourhood.
/// `NoSpace` ⇒ the guard is skipped and the pile left unguarded, a valid
/// outcome (TMP_006 §5.3). `place_guard` returns nothing, so a guard skip can
/// never touch the caller's `emergency` budget (spec D6 / review r6 finding 1).
#[allow(clippy::too_many_arguments)]
fn place_guard(
    state: &mut TilemapBuildState,
    zone_idx: usize,
    pile_value: u32,
    // TMP-Q4 LOW-1 — guard inherits the pile's tier_index so the inspector
    // reads "tier N pile + tier N guard" as one logical unit. Without this,
    // a lair adjacent to a tier-0 pile would show no tier on hover.
    pile_tier_index: u8,
    pile_footprint: &TileMask,
    guard_template: &TilemapObjectTemplate,
    registry: &crate::registry::Registry,
) {
    // D5 — terrain is `Some`: TerrainPainter is a declared dependency, so the
    // registry runs it first. A `None` here is a pipeline-wiring bug, so a
    // panic is the correct surfacing (the unwrap ObstaclePlacer already uses).
    let terrain = state.zone_terrain[zone_idx]
        .expect("TerrainPainter runs before TreasurePlacer (dependency edge)");
    let guard = choose_guard(terrain, pile_value / 10);

    // D5 — the guard search mask: a grid-dimensioned `zone_area_open`
    // intersected with the pile footprint's 4-neighbourhood, so the candidates
    // are the pile's own `Open` neighbours while the mask stays grid-sized.
    let grid = state.grid;
    let mut neighbourhood = TileMask::new(grid.width, grid.height);
    for fp in pile_footprint.iter_set() {
        for n in neighbors4(fp, grid.width, grid.height) {
            neighbourhood.set(n);
        }
    }
    let mut guard_search_area = state.zone_area_open(zone_idx);
    guard_search_area.intersect_with(&neighbourhood);

    match place_and_connect_object(
        state,
        zone_idx,
        guard_template,
        TilemapObjectKind::MonsterLair,
        Some(guard.strength),
        Some(pile_tier_index),
        &guard_search_area,
        0.0,
        OptimizeType::Center,
        registry,
    ) {
        // Guard placed, or skipped for want of a non-sealing adjacent `Open`
        // tile (D5) — either way the pile stands; nothing more to do.
        Ok(_) | Err(PlacementError::NoSpace) => {}
        Err(PlacementError::NoSuchZone(z)) => {
            unreachable!("TreasurePlacer: guard placed into out-of-range zone {z}");
        }
    }
}

/// A treasure pile's placement footprint — a single 1×1 blocking tile (spec
/// D4: a V1+30d pile places as one `Treasure` object; its multi-object
/// composition is build-internal value, not a multi-tile footprint).
fn treasure_pile_template() -> TilemapObjectTemplate {
    TilemapObjectTemplate {
        name: "treasure_pile".to_string(),
        cells: vec![FootprintCell::blocking(0, 0)],
    }
}

/// A monster-lair guard's placement footprint — a single 1×1 blocking tile
/// (spec D5).
fn guard_template() -> TilemapObjectTemplate {
    TilemapObjectTemplate {
        name: "monster_lair".to_string(),
        cells: vec![FootprintCell::blocking(0, 0)],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::place_tilemap;
    use crate::engine::placement::ZoneTiles;
    use crate::engine::treasure_pool::engine_treasure_pool;
    use crate::engine::treasure_select::compose_pile;
    use crate::seed::TilemapSeed;
    use crate::types::channel::{ChannelId, ChannelTier};
    use crate::types::object::TilemapObjectPlacement;
    use crate::types::template::{TilemapTemplateId, ZoneSpec};
    use crate::types::tile::{TerrainKind, TileCoord};
    use crate::types::tilemap::GridSize;

    /// A `w × h` single-zone build state: one zone `id` covering the grid,
    /// `free_paths` along the top row (a Walkable skeleton on one edge, every
    /// other tile `Open`), `zone_terrain` pre-set. This is the AC-6
    /// "guard-placeable" geometry — a pile in the wide `Open` interior always
    /// has a non-sealing `Open` tile 4-adjacent to it.
    fn solo_state(id: &str, w: u32, h: u32, role: ZoneRole) -> TilemapBuildState {
        let grid = GridSize { width: w, height: h };
        let mut assigned = TileMask::new(w, h);
        for y in 0..h {
            for x in 0..w {
                assigned.set(TileCoord::new(x, y));
            }
        }
        let mut free = TileMask::new(w, h);
        for x in 0..w {
            free.set(TileCoord::new(x, 0));
        }
        let zone = ZoneTiles {
            id: ZoneId(id.to_string()),
            role,
            center: TileCoord::new(w / 2, h / 2),
            assigned_tiles: assigned,
            free_paths: free,
        };
        let mut state = TilemapBuildState::from_zones(vec![zone], grid);
        // TerrainPainter would set this; the harness sets it directly so the
        // fixtures stay fully pinned (no RNG-driven terrain choice).
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        state
    }

    /// A `TreasureTierSpec` shorthand.
    fn tier(min: u32, max: u32, density: u16) -> TreasureTierSpec {
        TreasureTierSpec { min, max, density }
    }

    /// A `ZoneSpec` carrying `tiers` and an optional `inherit_treasure_from`.
    fn zone_spec(id: &str, tiers: Vec<TreasureTierSpec>, inherit: Option<&str>) -> ZoneSpec {
        ZoneSpec {
            zone_id: ZoneId(id.to_string()),
            zone_role: ZoneRole::Wilderness,
            size: 100,
            terrain_types: vec![],
            monster_strength: None,
            connections: vec![],
            treasure_tiers: tiers,
            biome_selection_rules: None,
            inherit_treasure_from: inherit.map(|s| ZoneId(s.to_string())),
            biome_theme: None,
        }
    }

    /// Wrap `zones` in a `TilemapTemplate`.
    fn template(zones: Vec<ZoneSpec>) -> TilemapTemplate {
        TilemapTemplate {
            template_id: TilemapTemplateId("treasure_placer_test".to_string()),
            zones,
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
        }
    }

    /// Run `TreasurePlacer` over `state` with `template` at `seed`.
    fn run_placer(state: &mut TilemapBuildState, template: &TilemapTemplate, seed: u64) {
        let grid = state.grid;
        let reg = crate::registry::Registry::load_default().unwrap();
        let mut ctx = ModificatorContext {
            template,
            grid,
            seed: TilemapSeed(seed),
            state,
            registry: &reg,
        };
        TreasurePlacer
            .process(&mut ctx)
            .expect("TreasurePlacer::process must not error");
    }

    /// The placed `Treasure` records, in placement order.
    fn treasures(state: &TilemapBuildState) -> Vec<&TilemapObjectPlacement> {
        state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::Treasure)
            .collect()
    }

    /// The placed `MonsterLair` (guard) records, in placement order.
    fn lairs(state: &TilemapBuildState) -> Vec<&TilemapObjectPlacement> {
        state
            .object_placements
            .iter()
            .filter(|p| p.kind == TilemapObjectKind::MonsterLair)
            .collect()
    }

    #[test]
    fn ac5a_clean_zone_places_exactly_target_count() {
        // AC-5(a) — a clean zone (a reliably-reachable tier, an ample `Open`
        // area): the §3.3 loop places exactly `target_count` Treasure objects,
        // no composition or placement failure. 20×20 = 400 tiles, density 8 ⇒
        // target_count = (8 × 400 / 1000) as u32 = 3. Tier [300, 800] is
        // reachable for every seed, and a value < 2000 places no guard.
        for seed in 0..8u64 {
            let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
            let tmpl = template(vec![zone_spec("z", vec![tier(300, 800, 8)], None)]);
            run_placer(&mut state, &tmpl, seed);
            assert_eq!(
                treasures(&state).len(),
                3,
                "seed {seed}: a clean zone must place exactly target_count (3) piles",
            );
            assert!(lairs(&state).is_empty(), "seed {seed}: a sub-2000 tier places no guard");
        }
    }

    #[test]
    fn ac5c_sub_thousand_density_truncates_target_to_zero() {
        // AC-5(c) — density × tiles < 1000 ⇒ target_count truncates to 0 ⇒
        // zero Treasure objects. 400 tiles × density 2 = 800 < 1000.
        let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(300, 800, 2)], None)]);
        run_placer(&mut state, &tmpl, 1);
        assert!(
            treasures(&state).is_empty(),
            "a sub-thousand density×tiles zone must hold no piles of that tier",
        );
    }

    #[test]
    fn ac5d_each_treasure_records_its_pile_value() {
        // AC-5(d) — every placed Treasure carries value == Some(v) (D10), with
        // v inside the composing tier's [min, max].
        let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(300, 800, 8)], None)]);
        run_placer(&mut state, &tmpl, 5);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "the fixture must place at least one Treasure");
        for p in ts {
            let v = p.value.expect("a Treasure placement must carry Some(value)");
            assert!(
                (300..=800).contains(&v),
                "Treasure value {v} outside the composing tier [300, 800]",
            );
        }
    }

    #[test]
    fn ac4_ac6a_high_value_tier_guards_every_pile() {
        // AC-4 + AC-6(a) — a tier with min ≥ 2000 (every composed pile clears
        // the guard threshold) places one MonsterLair per Treasure, each lair
        // 4-adjacent to its pile, each lair value == Some(pile_value / 10).
        // 24×24 = 576 tiles, density 4 ⇒ target_count = 2; tier [2000, 3000]
        // is reachable for every seed and small enough to place two guarded
        // piles with room to spare.
        let mut state = solo_state("z", 24, 24, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(2000, 3000, 4)], None)]);
        run_placer(&mut state, &tmpl, 3);
        let ts = treasures(&state);
        let ls = lairs(&state);
        assert!(!ts.is_empty(), "the fixture must place at least one guarded pile");
        assert_eq!(ls.len(), ts.len(), "every min≥2000 pile must get exactly one guard");
        // The placer places a pile then immediately its guard, so
        // object_placements pairs them: [Treasure, MonsterLair, Treasure, …].
        for pair in state.object_placements.chunks(2) {
            let [pile, guard] = pair else {
                panic!("object_placements must pair each pile with its guard");
            };
            assert_eq!(pile.kind, TilemapObjectKind::Treasure);
            assert_eq!(guard.kind, TilemapObjectKind::MonsterLair);
            let pile_value = pile.value.expect("a pile carries Some(value)");
            assert_eq!(
                guard.value,
                Some(pile_value / 10),
                "guard strength must be pile_value / 10 (D5/D10)",
            );
            assert!(
                neighbors4(pile.anchor, state.grid.width, state.grid.height)
                    .any(|n| n == guard.anchor),
                "the guard must sit 4-adjacent to its pile footprint",
            );
        }
    }

    #[test]
    fn tmp_q4_pile_carries_tier_index_zero_for_single_tier() {
        // TMP-Q4 AC-VBT-2 — a zone with one tier places piles with
        // tier_index = Some(0) (the sort makes it the highest band).
        let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(300, 800, 8)], None)]);
        run_placer(&mut state, &tmpl, 5);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "the fixture must place piles");
        for p in ts {
            assert_eq!(
                p.tier_index,
                Some(0),
                "single-tier zone: every pile gets tier_index=Some(0)",
            );
        }
    }

    #[test]
    fn tmp_q4_pile_tier_index_follows_max_desc_sort() {
        // TMP-Q4 AC-VBT-2 — declare two value-disjoint tiers in low-first
        // order; the placer sorts by max desc; the high-`max` tier's piles
        // carry tier_index=0, the low-`max` tier's piles carry tier_index=1.
        for seed in 0..4u64 {
            let mut state = solo_state("z", 24, 24, ZoneRole::Wilderness);
            let tmpl = template(vec![zone_spec(
                "z",
                vec![tier(300, 800, 5), tier(5000, 9000, 4)],
                None,
            )]);
            run_placer(&mut state, &tmpl, seed);
            let ts = treasures(&state);
            assert!(!ts.is_empty(), "seed {seed}: fixture must place piles");
            for p in ts {
                let v = p.value.expect("pile carries Some(value)");
                let expected_tier = if v >= 5000 { 0u8 } else { 1u8 };
                assert_eq!(
                    p.tier_index,
                    Some(expected_tier),
                    "seed {seed}: pile value {v} should have tier_index {expected_tier} \
                     (high-max tier sorts to index 0)",
                );
            }
        }
    }

    #[test]
    fn tmp_q4_unreachable_mid_tier_doesnt_shift_indices() {
        // TMP-Q4 LOW-4 from /review-impl — a 3-tier zone where the
        // post-sort MIDDLE tier (by max desc) is value-unreachable for
        // the engine pool. The mid tier produces zero piles but its
        // tier_index slot (1) is RESERVED — the low tier still gets
        // tier_index=2. A future refactor that moved enumerate inside
        // the compose retry loop would silently shift indices and this
        // test would fail.
        //
        // The engine treasure pool's object values are
        //   {250, 500, 750, 1200, 2000, 5000, 9000}.
        // Tier `[3001, 3001]` (min==max==3001) is genuinely unreachable
        // for these values — the running sum can hit 2000 + 1200 = 3200
        // (over) or 2000 + 750 = 2750 (under), but never exactly 3001.
        // After sort by max desc: high [5000,9000] → 0; mid [3001,3001]
        // → 1 (UNREACHABLE); low [300,800] → 2 (reachable).
        let mut state = solo_state("z", 24, 24, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec(
            "z",
            vec![
                tier(5000, 9000, 5),
                tier(3001, 3001, 5),
                tier(300, 800, 5),
            ],
            None,
        )]);
        run_placer(&mut state, &tmpl, 11);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "high + low tiers must place some piles");
        // Mid tier produces nothing — no pile should have tier_index=1.
        let mid_tier_pile_count = ts.iter().filter(|p| p.tier_index == Some(1)).count();
        assert_eq!(
            mid_tier_pile_count, 0,
            "the unreachable mid tier MUST produce zero piles \
             (tier_index=1 slot stays empty)",
        );
        // Crucially: low-tier piles must still carry tier_index=2,
        // NOT 1. A regression where enumerate shifted on compose
        // failure would land them at 1.
        for p in ts {
            let v = p.value.unwrap();
            let expected = if v >= 5000 { Some(0) } else { Some(2) };
            assert_eq!(
                p.tier_index, expected,
                "pile value {v}: an unreachable tier between high and \
                 low MUST NOT shift the low tier's index from 2 to 1",
            );
        }
    }

    #[test]
    fn tmp_q4_inherited_tiers_use_source_zone_tier_index() {
        // TMP-Q4 LOW-3 from /review-impl — when zone X inherits Y's
        // treasure_tiers via `inherit_treasure_from: Some("y")`, the
        // tier_index of X's piles is derived from Y's (sorted) tier list,
        // NOT X's own (REPLACE-discarded) tier list. A regression where
        // tier_index reverted to X's own tiers would still pass
        // `ac10a_inherit_replaces_own_tiers` (which only checks value
        // range), so we pin the index mapping here too.
        //
        // Y declares two value-disjoint tiers in low-first order:
        //   - [300, 800]    → after sort: tier_index=1
        //   - [5000, 9000]  → after sort: tier_index=0
        // X inherits from Y and has its own SINGLE tier [100, 200] that
        // gets DISCARDED. If a regression used X's own list, every X
        // pile would land at tier_index=0. With correct sourcing, X's
        // piles split between Y's high (index 0) and low (index 1).
        let mut state = solo_state("x", 24, 24, ZoneRole::Wilderness);
        let tmpl = template(vec![
            zone_spec("x", vec![tier(100, 200, 8)], Some("y")),
            zone_spec(
                "y",
                vec![tier(300, 800, 5), tier(5000, 9000, 4)],
                None,
            ),
        ]);
        run_placer(&mut state, &tmpl, 13);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "x must inherit y's tiers and place piles");
        // Every pile must use Y's index mapping: high → 0, low → 1.
        // No pile should carry tier_index=Some(0) for a value in [100,200]
        // (that would mean we used x's own tiers).
        for p in ts {
            let v = p.value.unwrap();
            let expected_idx = if (5000..=9000).contains(&v) {
                Some(0u8)
            } else if (300..=800).contains(&v) {
                Some(1u8)
            } else {
                panic!(
                    "pile value {v} must be in Y's ranges; x's own [100,200] \
                     is REPLACE-discarded by inherit_treasure_from"
                );
            };
            assert_eq!(
                p.tier_index, expected_idx,
                "value {v} must use the SOURCE zone (y)'s tier_index mapping, \
                 not x's own discarded tiers",
            );
        }
    }

    #[test]
    fn tmp_q4_guard_inherits_pile_tier_index() {
        // TMP-Q4 LOW-1 + AC-VBT-2 — the MonsterLair guard placed next to a
        // pile inherits the pile's tier_index so the inspector reads
        // "tier N pile + tier N guard". With a single tier [2000, 3000]
        // (guarded), every pair (pile, guard) shares tier_index=Some(0).
        let mut state = solo_state("z", 24, 24, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(2000, 3000, 4)], None)]);
        run_placer(&mut state, &tmpl, 7);
        let ts = treasures(&state);
        let ls = lairs(&state);
        assert!(!ts.is_empty(), "fixture must place guarded piles");
        assert_eq!(ls.len(), ts.len(), "every pile gets a guard");
        for pair in state.object_placements.chunks(2) {
            let [pile, guard] = pair else { unreachable!() };
            assert_eq!(
                pile.tier_index,
                Some(0),
                "single-tier zone: pile is tier 0",
            );
            assert_eq!(
                guard.tier_index, pile.tier_index,
                "guard must inherit its pile's tier_index for consistent inspector reading",
            );
        }
    }

    #[test]
    fn ac4_ac6b_low_value_tier_places_no_guard() {
        // AC-4 + AC-6(b) — a tier whose `max` is below 2000 can compose no pile
        // that reaches the guard threshold: zero MonsterLair objects.
        let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("z", vec![tier(300, 800, 5)], None)]);
        run_placer(&mut state, &tmpl, 2);
        assert!(!treasures(&state).is_empty(), "the fixture must place Treasure piles");
        assert!(
            lairs(&state).is_empty(),
            "no pile of a max<2000 tier can reach the guard threshold",
        );
    }

    #[test]
    fn forbidden_zone_is_skipped() {
        // D4 — a Forbidden zone is all-Obstacle; TreasurePlacer skips it even
        // when its ZoneSpec declares treasure tiers.
        let mut state = solo_state("z", 12, 12, ZoneRole::Forbidden);
        let tmpl = template(vec![zone_spec("z", vec![tier(300, 9000, 50)], None)]);
        run_placer(&mut state, &tmpl, 9);
        assert!(
            state.object_placements.is_empty(),
            "a Forbidden zone must receive no treasure",
        );
    }

    #[test]
    fn ac5b_higher_max_tier_is_consumed_first() {
        // AC-5(b) — a zone with two pool-reachable, value-disjoint tiers (so
        // each placement's tier is identifiable): the higher-`max` tier
        // ([5000,9000]) is consumed before the lower ([300,800]), so its piles
        // precede the low tier's in object_placements. The tiers are declared
        // low-first, so this pins the (max desc) sort, not author order. The
        // ordering is structural (seed-independent) — so, per the universal-
        // property discipline, it is checked over a seed range and decoupled
        // from any exact pile count: on each seed, every placed high-max pile
        // must precede every placed low-max pile.
        for seed in 0..8u64 {
            let mut state = solo_state("z", 20, 20, ZoneRole::Wilderness);
            let tmpl = template(vec![zone_spec(
                "z",
                vec![tier(300, 800, 5), tier(5000, 9000, 5)],
                None,
            )]);
            run_placer(&mut state, &tmpl, seed);
            let ts = treasures(&state);
            // Both tiers are pool-reachable for every seed, so each places ≥ 1.
            let first_low = ts
                .iter()
                .position(|p| p.value.unwrap() <= 800)
                .unwrap_or_else(|| panic!("seed {seed}: the low tier placed no pile"));
            let last_high = ts
                .iter()
                .rposition(|p| p.value.unwrap() >= 5000)
                .unwrap_or_else(|| panic!("seed {seed}: the high tier placed no pile"));
            assert!(
                last_high < first_low,
                "seed {seed}: every high-max pile must precede every low-max pile: {:?}",
                ts.iter().map(|p| p.value).collect::<Vec<_>>(),
            );
        }
    }

    #[test]
    fn ac5e_failure_path_still_reaches_target_count() {
        // AC-5(e) — the D6 emergency-bound gate. Tier [1250,1350] is reachable
        // for *some* compositions but not others (it fails when the 1200-value
        // object is the first draw — that strands the running sum at 1200): the
        // §3.3 loop deterministically hits ≥ 1 compose_pile → None, yet the
        // corrected bound (failures capped separately, successes never consume
        // budget) still places exactly target_count piles. 30×30 = 900 tiles,
        // density 7 ⇒ target_count = 6.
        //
        // E_SEED chosen so the §3.3 loop deterministically hits ≥ 1 None (the
        // failure path) under the ChaCha8 draw order. (Re-pinned from 0 → 2 at
        // the rand 0.9 upgrade: `random_range` changed the draw sequence, so the
        // old seed no longer stranded a pile; the D6-bound behaviour under test
        // is unchanged.)
        const E_SEED: u64 = 2;
        let mut state = solo_state("z", 30, 30, ZoneRole::Wilderness);
        let t = tier(1250, 1350, 7);
        let tmpl = template(vec![zone_spec("z", vec![t], None)]);
        run_placer(&mut state, &tmpl, E_SEED);
        assert_eq!(
            treasures(&state).len(),
            6,
            "the corrected D6 bound must still reach target_count despite failures",
        );
        // Independently confirm the failure path ran: replay compose_pile over
        // the same tier + per-zone sub-seed (a pure function), mirroring the
        // placer's loop exactly (placement never fails here — low-value piles,
        // an ample grid — so every Some ⇒ a placed pile).
        let pool = engine_treasure_pool();
        let mut rng =
            ChaCha8Rng::seed_from_u64(sub_seed(TilemapSeed(E_SEED), "treasure_placer:z"));
        let (mut somes, mut nones) = (0u32, 0u32);
        while somes < 6 && nones < 6 {
            match compose_pile(&pool, t, &mut rng) {
                Some(_) => somes += 1,
                None => nones += 1,
            }
        }
        assert_eq!(somes, 6, "the replay must reach 6 successful compositions");
        assert!(
            nones >= 1,
            "AC-5(e) vacuous — the failure path never ran (replay saw {nones} None)",
        );
    }

    #[test]
    fn ac10a_inherit_replaces_own_tiers() {
        // AC-10(a) — zone "x" declares BOTH inherit_treasure_from: Some("y")
        // and its own treasure_tiers, with its own range disjoint from y's.
        // D9 is REPLACE: x's effective tiers are y's literal tiers, x's own are
        // inert. Every placed Treasure in x lands in y's range [300,800], none
        // in x's own [5000,9000] (a prefer-own or union resolver would fail).
        let mut state = solo_state("x", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![
            zone_spec("x", vec![tier(5000, 9000, 8)], Some("y")),
            zone_spec("y", vec![tier(300, 800, 8)], None),
        ]);
        run_placer(&mut state, &tmpl, 6);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "x must inherit y's (non-empty) tiers and place piles");
        for p in ts {
            let v = p.value.unwrap();
            assert!(
                (300..=800).contains(&v),
                "inherited pile value {v} must land in y's range [300,800], not x's own",
            );
        }
    }

    #[test]
    fn ac10b_inheritance_is_non_transitive() {
        // AC-10(b) — a three-zone chain: x inherits y, y inherits z, and y
        // carries its OWN non-empty tiers disjoint from z's. D9 is one level,
        // non-transitive: x's effective tiers are y's *literal* tiers
        // ([300,800]), NOT z's ([5000,9000]) — y's own inherit_treasure_from is
        // never chased. A transitive-chase resolver would land x's piles in z's
        // range and fail here.
        let mut state = solo_state("x", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![
            zone_spec("x", vec![], Some("y")),
            zone_spec("y", vec![tier(300, 800, 8)], Some("z")),
            zone_spec("z", vec![tier(5000, 9000, 8)], None),
        ]);
        run_placer(&mut state, &tmpl, 6);
        let ts = treasures(&state);
        assert!(!ts.is_empty(), "x must inherit y's own tiers and place piles");
        for p in ts {
            let v = p.value.unwrap();
            assert!(
                (300..=800).contains(&v),
                "non-transitive: pile value {v} must land in y's own range, not z's",
            );
        }
    }

    #[test]
    fn ac10b_inheritance_cycle_terminates() {
        // AC-10(b) — an authoring cycle x → y → x. D9's non-transitivity makes
        // the cycle structurally harmless (resolution is one hop, never
        // chased): place_tilemap terminates with a deterministic result, no
        // panic and no hang. The test completing is the no-hang proof.
        use crate::types::template::TemplateConnection;
        use crate::types::zone::PassageKind;
        let mut x = zone_spec("x", vec![tier(300, 800, 4)], Some("y"));
        x.connections = vec![TemplateConnection::new(ZoneId("y".to_string()), PassageKind::Open)];
        let mut y = zone_spec("y", vec![tier(300, 800, 4)], Some("x"));
        y.connections = vec![TemplateConnection::new(ZoneId("x".to_string()), PassageKind::Open)];
        let tmpl = template(vec![x, y]);
        // A small grid keeps this full-`place_tilemap` test fast — it only has
        // to prove the cycle terminates deterministically without a panic.
        let grid = GridSize { width: 24, height: 24 };
        let run = || {
            place_tilemap(
                &tmpl,
                ChannelId("ch".to_string()),
                ChannelTier::Country,
                grid,
                TilemapSeed(11),
            )
        };
        let a = run().expect("a cyclic inherit_treasure_from must not panic place_tilemap");
        let b = run().expect("place_tilemap must remain deterministic");
        assert_eq!(
            serde_json::to_string(&a).unwrap(),
            serde_json::to_string(&b).unwrap(),
            "place_tilemap output must be byte-identical on replay",
        );
    }

    #[test]
    fn ac10c_dangling_inherit_yields_no_treasure() {
        // AC-10(c) — inherit_treasure_from points at a zone absent from the
        // template. D9: the effective tiers are empty (never a panic, never a
        // fallback to the zone's own tiers), so the zone gets zero treasure
        // despite declaring a juicy own tier.
        let mut state = solo_state("x", 20, 20, ZoneRole::Wilderness);
        let tmpl = template(vec![zone_spec("x", vec![tier(300, 9000, 50)], Some("ghost"))]);
        run_placer(&mut state, &tmpl, 6);
        assert!(
            state.object_placements.is_empty(),
            "a dangling inherit_treasure_from must yield zero treasure (not fall back to own)",
        );
    }

    #[test]
    fn guard_skipped_when_the_pile_has_no_open_neighbour() {
        // D5 / review r6-finding-1 — when a guard's `place_and_connect_object`
        // returns `NoSpace` (no `Open` tile 4-adjacent to the pile), the guard
        // is skipped and the pile stands unguarded; the skip is benign, never
        // an error, and never an emergency. This pins the `place_guard`
        // `NoSpace` arm, which the guard-placeable-geometry tests (ac6a/ac7)
        // never reach. Geometry: a 3×3 zone whose centre is the sole `Open`
        // tile, ringed by `Walkable` `free_paths` — the pile is forced
        // dead-centre and its four neighbours are all `Walkable`, so the guard
        // search area is empty.
        let grid = GridSize { width: 3, height: 3 };
        let mut assigned = TileMask::new(3, 3);
        let mut free = TileMask::new(3, 3);
        for y in 0..3 {
            for x in 0..3 {
                assigned.set(TileCoord::new(x, y));
                if (x, y) != (1, 1) {
                    free.set(TileCoord::new(x, y)); // the ring is Walkable
                }
            }
        }
        let zone = ZoneTiles {
            id: ZoneId("g".to_string()),
            role: ZoneRole::Wilderness,
            center: TileCoord::new(1, 1),
            assigned_tiles: assigned,
            free_paths: free,
        };
        let mut state = TilemapBuildState::from_zones(vec![zone], grid);
        state.zone_terrain.fill(Some(TerrainKind::Grass));
        // density 200 ⇒ target_count 1 on the 9-tile / 1-Open-tile zone; tier
        // min ≥ 2000 so the single pile is guard-eligible.
        let tmpl = template(vec![zone_spec("g", vec![tier(2000, 6000, 200)], None)]);
        run_placer(&mut state, &tmpl, 1);

        let ts = treasures(&state);
        assert_eq!(ts.len(), 1, "the centre Open tile must take exactly one pile");
        let v = ts[0].value.expect("a Treasure carries Some(value)");
        assert!(
            v >= MIN_GUARD_VALUE,
            "the pile must be guard-eligible (value {v} >= {MIN_GUARD_VALUE}) — \
             otherwise an empty lair set would not prove the guard was *skipped*",
        );
        assert!(
            lairs(&state).is_empty(),
            "the guard has no Open tile to occupy — it must be skipped, not placed",
        );
    }
}
