//! TMP-Q1 — `DecorationPlacer` (chunk C: placement logic).
//!
//! Fills the walkable OPEN region of each zone with cosmetic
//! `primitive: Decoration` objects. Opt-in via
//! [`crate::types::template::TilemapTemplate::decoration_density`].
//!
//! Algorithm (per plan v2 §C):
//! 1. Look up the zone's `TerrainKind` → biome key.
//! 2. Build the "free for decorations" mask: zone OPEN region minus
//!    every prior placement's full footprint, road waypoints, river
//!    waypoints, and the zone center.
//! 3. Compute target = `density.target_for(free.count_ones())`.
//! 4. Per-zone RNG via `sub_seed(ctx.seed, "decoration_placer:{zone_id}")`
//!    — collision-safe with treasure_placer's sub_seed pattern.
//! 5. Loop up to `target` placements: roll weighted tag → sample
//!    candidate tile → verify per-tag min_spacing via Chebyshev →
//!    place or retry. On MAX_TRIES exhaustion, fall back to a
//!    lower-min_spacing tag from the same biome pool (bounded by
//!    MAX_FALLBACK_ATTEMPTS to ensure termination).
//!
//! Determinism: BTreeMap for `placed_by_tag`, sorted `pool` from
//! chunk B, deterministic `sample_set` (flat-index iter + `gen_range`),
//! deterministic weighted roll. Same `(template, seed, registry)` ⇒
//! byte-identical decoration list.
//!
//! Spec: [`docs/specs/2026-05-28-decoration-placer-density-pass.md`](../../../../docs/specs/2026-05-28-decoration-placer-density-pass.md)
//! Plan: [`docs/plans/2026-05-28-decoration-placer-build.md`](../../../../docs/plans/2026-05-28-decoration-placer-build.md)

use std::collections::BTreeMap;

use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

use crate::engine::pipeline::{Modificator, ModificatorContext};
use crate::registry::DecorationRef;
use crate::seed::sub_seed;
use crate::types::object::{TilemapObjectKind, TilemapObjectPlacement};
use crate::types::primitive::ObjectPrimitive;
use crate::types::registry::FootprintSize;
use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;

/// Visual-density pass. See module doc.
#[derive(Debug)]
pub struct DecorationPlacer;

impl Modificator for DecorationPlacer {
    fn name(&self) -> &str {
        "decoration_placer"
    }

    fn dependencies(&self) -> Vec<&str> {
        // Must run AFTER every modificator that mutates the OPEN region
        // or places objects/road/river segments. The Kahn sort treats
        // unregistered names as satisfied (pipeline D7) so partial-
        // pipeline test sites stay safe.
        vec![
            "terrain_painter",
            "treasure_placer",
            "road_placer",
            "river_placer",
            "obstacle_fill_placer",
        ]
    }

    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        let Some(density) = ctx.template.decoration_density else {
            return Ok(());
        };

        // TMP-Q1 chunk D MED-2: fail fast on pathological density values
        // with a source-pinpoint error rather than silently under-placing.
        density
            .validate()
            .map_err(|e| crate::Error::Modificator {
                name: "decoration_placer".to_string(),
                reason: format!("decoration_density invalid: {e}"),
            })?;

        for zone_idx in 0..ctx.state.zones.len() {
            place_in_zone(zone_idx, density, ctx);
        }
        Ok(())
    }
}

/// Per-zone placement. Skips silently on missing terrain or empty pool
/// — both are deterministic outcomes. Chunk D wires browser smoke that
/// surfaces zero-decoration zones to the operator via MetadataPanel.
fn place_in_zone(
    zone_idx: usize,
    density: crate::types::decoration::DecorationDensity,
    ctx: &mut ModificatorContext<'_>,
) {
    let zone_id = ctx.state.zones[zone_idx].id.clone();

    let Some(terrain) = ctx.state.zone_terrain[zone_idx] else {
        // No terrain painted yet — unreachable in production (TerrainPainter
        // runs first) but defensive against test pipelines.
        return;
    };
    let pool: Vec<DecorationRef> = ctx.registry.decorations_for_terrain(terrain).to_vec();
    if pool.is_empty() {
        return;
    }

    // Build the "free for decorations" mask.
    let mut free = ctx.state.zone_area_open(zone_idx);
    subtract_footprints(&mut free, ctx);
    subtract_road_river_waypoints(&mut free, ctx);
    free.clear(ctx.state.zones[zone_idx].center);

    if free.count_ones() == 0 {
        return;
    }

    let target = density.target_for(free.count_ones() as u32);
    if target == 0 {
        return;
    }

    let max_tries_per_slot = compute_max_tries(free.count_ones());

    // Per-zone deterministic RNG sub-stream — sub_seed labels prevent
    // collision with other placers' streams (treasure_placer pattern).
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(
        ctx.seed,
        &format!("decoration_placer:{}", zone_id.0),
    ));

    // BTreeMap (not HashMap) so iteration order is deterministic if any
    // future code path scans `placed_by_tag`.
    let mut placed_by_tag: BTreeMap<String, Vec<TileCoord>> = BTreeMap::new();
    let mut placed: u32 = 0;

    'slots: while placed < target {
        let mut current_tag = roll_weighted_tag(&pool, &mut rng);
        let mut fallback_attempts: u32 = 0;
        // LOW-1 from chunk-C /review-impl: `min_by_key` on the
        // `< current_tag.min_spacing` filter picks the absolute minimum
        // in pool, so the SECOND fallback would filter `< 0` and return
        // None — only 1 effective fallback iteration ever runs. The bound
        // is set to 2 so the check `fallback_attempts >= 2` fires AFTER
        // the 1st fallback's inner loop has run (success or fail), not
        // before. Semantic: "try original tag, then try one fallback,
        // then give up." If the strategy ever changes to
        // next-lower-by-one, raise this bound to allow >1 effective
        // fallback.
        const MAX_FALLBACK_ATTEMPTS: u32 = 2;

        let placed_this_slot = loop {
            let mut tries: u32 = 0;
            let success = loop {
                if tries >= max_tries_per_slot {
                    break false;
                }
                let Some(candidate) = free.sample_set(&mut rng) else {
                    // free mask exhausted — under-shoot is tolerated per AC-DECO-11.
                    break false;
                };
                let placed_for_tag = placed_by_tag
                    .entry(current_tag.kind_id.clone())
                    .or_default();
                if chebyshev_min_distance(placed_for_tag, candidate)
                    >= current_tag.min_spacing
                {
                    ctx.state.object_placements.push(TilemapObjectPlacement {
                        kind: TilemapObjectKind::Decoration,
                        anchor: candidate,
                        canon_ref: None,
                        biome_object_type: None,
                        value: None,
                        tier_index: None,
                        primitive: Some(ObjectPrimitive::Decoration),
                        tag: Some(current_tag.kind_id.clone()),
                        footprint: Some(FootprintSize::unit()),
                        orientation: None,
                        properties: serde_json::Value::Object(serde_json::Map::new()),
                    });
                    placed_for_tag.push(candidate);
                    free.clear(candidate);
                    break true;
                }
                tries += 1;
            };
            if success {
                break true;
            }
            // Fallback: pick a strictly lower-min_spacing tag from the
            // pool. Among ties, pool's id-sorted order picks the first
            // — deterministic.
            let fallback = pool
                .iter()
                .filter(|t| t.min_spacing < current_tag.min_spacing)
                .min_by_key(|t| t.min_spacing);
            let Some(fallback) = fallback else {
                break false;
            };
            fallback_attempts += 1;
            if fallback_attempts >= MAX_FALLBACK_ATTEMPTS {
                break false;
            }
            current_tag = fallback;
        };

        if placed_this_slot {
            placed += 1;
        } else {
            // No tag in this pool can find a free slot — give up.
            // AC-DECO-11 tolerates under-shoot within 10%.
            break 'slots;
        }

        if free.count_ones() == 0 {
            break 'slots;
        }
    }
}

/// Subtract every prior placement's full footprint (width × height)
/// from `free`. Plan v2 MED-2: anchors alone are insufficient — Town
/// is 4×4, Mine 2×2, etc. — so a decoration could otherwise land on
/// a Town's interior tile.
///
/// `zone_area_open` already filters out tiles in `TileState::Occupied`,
/// which existing placers may use for the anchor. This step is the
/// defensive fallback when a placer marks ONLY the anchor as Occupied
/// while declaring a multi-tile footprint — the other footprint tiles
/// stay `Open` in tile_state but the decoration must still avoid them.
/// Tested by `decoration_skips_synthetic_multi_tile_footprint`.
fn subtract_footprints(free: &mut TileMask, ctx: &ModificatorContext<'_>) {
    for placement in &ctx.state.object_placements {
        let footprint = placement.footprint.unwrap_or(FootprintSize::unit());
        for dy in 0..footprint.height {
            for dx in 0..footprint.width {
                // LOW-4 from chunk-C /review-impl: `TileMask::clear`
                // silently ignores out-of-bounds coords — that is the
                // load-bearing safeguard against off-grid iteration,
                // NOT saturating_add. Realistic placers constrain anchors
                // so footprints fit in-grid; the OOB tolerance below
                // catches authoring bugs without panicking.
                let t = TileCoord::new(placement.anchor.x + dx, placement.anchor.y + dy);
                free.clear(t);
            }
        }
    }
}

/// Subtract every road + river polyline waypoint from `free`. Roads
/// and rivers are 1-tile-wide (geometric placers) so the anchor IS
/// the full footprint.
fn subtract_road_river_waypoints(free: &mut TileMask, ctx: &ModificatorContext<'_>) {
    for road in &ctx.state.road_segments {
        for &t in &road.waypoints {
            free.clear(t);
        }
    }
    for river in &ctx.state.river_segments {
        for &t in &river.tiles {
            free.clear(t);
        }
    }
}

/// Bounded retry budget per slot. Plan v2 LOW-5 documented the
/// heuristic: `clamp(free / 4, 8, 64)`. A small zone (free=10) gets 8
/// tries (the floor) so it still terminates fast; a large zone
/// (free=256) gets 64 tries before falling back. Deterministic given
/// `free` count.
fn compute_max_tries(free_count: usize) -> u32 {
    ((free_count / 4) as u32).clamp(8, 64)
}

/// Weighted random selection of one decoration tag. Total = sum of
/// weights; roll `[0, total)`; subtract weights until <= 0. Pool is
/// non-empty by caller invariant. Deterministic given `(pool, rng)`.
fn roll_weighted_tag<'a>(
    pool: &'a [DecorationRef],
    rng: &mut impl rand::Rng,
) -> &'a DecorationRef {
    let total: f32 = pool.iter().map(|r| r.density_weight).sum();
    // Chunk-B validation guarantees weights are finite + positive, so
    // `total > 0` and `gen_range(0.0..total)` won't panic.
    let mut roll: f32 = rng.random_range(0.0..total);
    for r in pool {
        roll -= r.density_weight;
        if roll <= 0.0 {
            return r;
        }
    }
    // Float drift can leave a tiny positive remainder; pool's last item
    // is the natural fallback. Pool non-empty per caller invariant.
    pool.last().expect("pool must be non-empty per caller invariant")
}

/// Chebyshev (chessboard) min distance from `candidate` to any tile
/// in `placed`. Returns `u32::MAX` for an empty `placed` slice (no
/// constraint).
fn chebyshev_min_distance(placed: &[TileCoord], candidate: TileCoord) -> u32 {
    placed
        .iter()
        .map(|p| {
            let dx = (p.x as i32 - candidate.x as i32).unsigned_abs();
            let dy = (p.y as i32 - candidate.y as i32).unsigned_abs();
            dx.max(dy)
        })
        .min()
        .unwrap_or(u32::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn name_is_stable() {
        assert_eq!(DecorationPlacer.name(), "decoration_placer");
    }

    #[test]
    fn dependencies_cover_last_running_upstream_placers() {
        let deps = DecorationPlacer.dependencies();
        assert!(deps.contains(&"road_placer"));
        assert!(deps.contains(&"river_placer"));
        assert!(deps.contains(&"obstacle_fill_placer"));
    }

    #[test]
    fn compute_max_tries_clamps() {
        assert_eq!(compute_max_tries(0), 8, "floor on tiny zone");
        assert_eq!(compute_max_tries(10), 8, "small zone floors at 8");
        assert_eq!(compute_max_tries(40), 10, "mid zone scales linearly");
        assert_eq!(compute_max_tries(256), 64, "large zone caps at 64");
        assert_eq!(compute_max_tries(1_000_000), 64, "huge zone caps at 64");
    }

    #[test]
    fn chebyshev_min_distance_empty_returns_max() {
        let placed: Vec<TileCoord> = vec![];
        let candidate = TileCoord::new(5, 5);
        assert_eq!(chebyshev_min_distance(&placed, candidate), u32::MAX);
    }

    #[test]
    fn chebyshev_min_distance_picks_max_of_dx_dy() {
        let placed = vec![TileCoord::new(0, 0)];
        // (3, 4) → max(3, 4) = 4
        assert_eq!(chebyshev_min_distance(&placed, TileCoord::new(3, 4)), 4);
        // (1, 0) → max(1, 0) = 1
        assert_eq!(chebyshev_min_distance(&placed, TileCoord::new(1, 0)), 1);
        // self → 0
        assert_eq!(chebyshev_min_distance(&placed, TileCoord::new(0, 0)), 0);
    }

    #[test]
    fn chebyshev_min_distance_picks_min_across_placed() {
        let placed = vec![
            TileCoord::new(0, 0),
            TileCoord::new(10, 10),
            TileCoord::new(5, 5),
        ];
        // (4, 4) is closest to (5, 5) → 1
        assert_eq!(chebyshev_min_distance(&placed, TileCoord::new(4, 4)), 1);
    }

    #[test]
    fn roll_weighted_tag_picks_only_member() {
        let pool = vec![DecorationRef {
            kind_id: "solo".to_string(),
            density_weight: 1.0,
            min_spacing: 0,
        }];
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let picked = roll_weighted_tag(&pool, &mut rng);
        assert_eq!(picked.kind_id, "solo");
    }

    #[test]
    fn roll_weighted_tag_handles_tiny_weights_without_panic() {
        // LOW-5 from chunk-C /review-impl. Weights at the f32 precision
        // edge could in theory cause the subtraction loop to underflow
        // before any tag matches `roll <= 0.0`. The function's
        // `pool.last()` fallback handles this gracefully. Verify no
        // panic; the returned tag must be a pool member.
        let pool = vec![
            DecorationRef { kind_id: "a".to_string(), density_weight: 1e-7, min_spacing: 0 },
            DecorationRef { kind_id: "b".to_string(), density_weight: 1e-7, min_spacing: 0 },
            DecorationRef { kind_id: "c".to_string(), density_weight: 1e-7, min_spacing: 0 },
        ];
        let mut rng = ChaCha8Rng::seed_from_u64(7);
        for _ in 0..100 {
            let picked = roll_weighted_tag(&pool, &mut rng);
            assert!(
                ["a", "b", "c"].contains(&picked.kind_id.as_str()),
                "fallback must return a pool member, got {}",
                picked.kind_id
            );
        }
    }

    #[test]
    fn roll_weighted_tag_distribution_skews_to_high_weight() {
        let pool = vec![
            DecorationRef {
                kind_id: "rare".to_string(),
                density_weight: 0.1,
                min_spacing: 0,
            },
            DecorationRef {
                kind_id: "common".to_string(),
                density_weight: 0.9,
                min_spacing: 0,
            },
        ];
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let mut common_count = 0;
        for _ in 0..1000 {
            let picked = roll_weighted_tag(&pool, &mut rng);
            if picked.kind_id == "common" {
                common_count += 1;
            }
        }
        // 0.9 of 1000 ≈ 900, ±50 for sample noise.
        assert!(
            (850..=950).contains(&common_count),
            "expected ~900 common picks, got {}",
            common_count
        );
    }
}
