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
use crate::registry::{DecorationRef, Registry};
use crate::seed::sub_seed;
use crate::types::object::{TilemapObjectKind, TilemapObjectPlacement};
use crate::types::primitive::ObjectPrimitive;
use crate::types::registry::{validate_decoration_family_density, FootprintSize};
use crate::types::template::TilemapTemplate;
use crate::types::tile::TileCoord;
use crate::types::tile_mask::TileMask;
use crate::types::zone::ZoneRole;

/// TMP-Q5 chunk C — role-aware decoration density multiplier.
///
/// Per spec §1 #4: Wilderness zones get +20% density (sense of being
/// wild), Hub zones get -30% (cleared roads + market), Forbidden and
/// Sea stay at 0 (defensive — Forbidden is already all-Obstacle so
/// `free.count_ones()` would be 0 anyway, but the explicit ×0 protects
/// against future template-author edge cases where Sea has a small
/// Open band or Forbidden has been mis-flagged).
///
/// Hard-coded for V1; future per-book override via
/// `RegistryRef.role_decoration_multipliers` is deferred (spec §10).
const fn role_density_multiplier(role: ZoneRole) -> f32 {
    match role {
        ZoneRole::Wilderness => 1.2,
        ZoneRole::Hub => 0.7,
        ZoneRole::Forbidden => 0.0,
        ZoneRole::Sea => 0.0,
    }
}

/// TMP-Q6 chunk B — resolve the effective per-family decoration density
/// multiplier for a given family at placement time.
///
/// Resolution chain (per spec
/// `docs/specs/2026-05-30-decoration-family-splits.md` §4):
/// 1. Template — `template.decoration_family_density[family]` wins per
///    family. Sparse — an absent family falls back to registry.
/// 2. Registry — `registry.reference().decoration_family_density[family]`
///    is the per-book baseline. Sparse same as template.
/// 3. Default — 1.0 (no bias) when neither layer declares the family.
///
/// `family == None` (the tag wasn't annotated, or this is one of the
/// grandfathered TYPE-marker entries) returns 1.0 unconditionally —
/// chunk B's bias only applies to entries that declared an
/// `ObjectKindDef.family` in chunk A.
///
/// **Composition with role-bias (chunk-C TMP-Q5):** the role multiplier
/// is applied to TARGET COUNT at `place_in_zone` entry; this family
/// multiplier is applied to PER-TAG WEIGHT inside `roll_weighted_tag`.
/// The two are independent dimensions: role bias changes how many
/// decorations get placed, family bias changes WHICH tags get picked
/// within the target count.
fn resolve_family_multiplier(
    family: Option<&str>,
    template: &TilemapTemplate,
    registry: &Registry,
) -> f32 {
    let Some(family) = family else { return 1.0 };
    if let Some(map) = template.decoration_family_density.as_ref() {
        if let Some(&m) = map.get(family) {
            return m;
        }
    }
    if let Some(map) = registry.reference().decoration_family_density.as_ref() {
        if let Some(&m) = map.get(family) {
            return m;
        }
    }
    1.0
}

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

        // TMP-Q6 chunk B — validate the template-side
        // `decoration_family_density` map at process time. Registry side
        // already validated at `Registry::from_file`. Same helper at both
        // layers so a malformed entry rejects identically.
        if let Some(map) = ctx.template.decoration_family_density.as_ref() {
            validate_decoration_family_density(map).map_err(|e| {
                crate::Error::Modificator {
                    name: "decoration_placer".to_string(),
                    reason: format!("template decoration_family_density: {e}"),
                }
            })?;
        }

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

    let raw_target = density.target_for(free.count_ones() as u32);
    // TMP-Q5 chunk C — role-aware density bias. Applied AFTER
    // density.target_for so the per-zone density math is unchanged
    // for any explicit multiplier of 1.0 (none today). Forbidden /
    // Sea collapse to target=0 here even when raw_target was > 0.
    //
    // Re-clamp to `max_per_zone` AFTER the multiplier so Wilderness
    // (×1.2) can't take a max-bounded zone above the configured
    // ceiling — that would silently break AC-DECO-4 (max_per_zone is
    // a hard invariant per template author's intent). Hub (×0.7)
    // never exceeds max so the clamp is a no-op there.
    let role = ctx.state.zones[zone_idx].role;
    let multiplier = role_density_multiplier(role);
    let biased = ((raw_target as f32) * multiplier) as u32;
    let target = biased.min(density.max_per_zone);
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

    // TMP-Q6 chunk B — closure factory for the per-family multiplier
    // lookup. Captured once per zone so `roll_weighted_tag` doesn't need
    // template + registry refs in its signature. Closure is cheap (two
    // HashMap lookups per call); deterministic given the template +
    // registry stay constant across rolls.
    let family_mult =
        |family: Option<&str>| resolve_family_multiplier(family, ctx.template, ctx.registry);

    'slots: while placed < target {
        // TMP-Q6 chunk B — `roll_weighted_tag` now returns Option: every
        // family in pool with multiplier 0.0 (e.g. author wrote
        // `bone = 0.0` to filter the family out) produces total weight
        // 0.0, which means "no decorations of these families here".
        // Abandon the slot loop — under-shoot is tolerated per AC-DECO-11.
        let Some(mut current_tag) = roll_weighted_tag(&pool, &family_mult, &mut rng)
        else {
            break 'slots;
        };
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
/// `density_weight × family_mult(family)`; roll `[0, total)`; subtract
/// scaled weights until <= 0. Pool is non-empty by caller invariant.
/// Deterministic given `(pool, family_mult, rng)`.
///
/// TMP-Q6 chunk B — the family multiplier closure scales each tag's
/// effective weight by the resolved per-family bias (template > registry
/// > 1.0). A multiplier of 0.0 filters that family from the pool. If
/// every family in pool has multiplier 0.0, total == 0.0 and we return
/// `None` so the caller can abandon the slot. This is the documented
/// "no decorations of any family here" exit.
fn roll_weighted_tag<'a, F: Fn(Option<&str>) -> f32>(
    pool: &'a [DecorationRef],
    family_mult: &F,
    rng: &mut impl rand::Rng,
) -> Option<&'a DecorationRef> {
    // Compute scaled weights once so the subtraction loop reads the
    // same values the total summed. Avoids divergence if `family_mult`
    // is ever non-pure (today's closure IS pure, but future versions
    // may stamp metrics or sample from non-deterministic sources).
    let scaled: Vec<f32> = pool
        .iter()
        .map(|r| r.density_weight * family_mult(r.family.as_deref()))
        .collect();
    let total: f32 = scaled.iter().sum();
    if total <= 0.0 {
        return None;
    }
    let mut roll: f32 = rng.gen_range(0.0..total);
    for (i, r) in pool.iter().enumerate() {
        roll -= scaled[i];
        if roll <= 0.0 {
            return Some(r);
        }
    }
    // Float drift can leave a tiny positive remainder; pool's last item
    // is the natural fallback. The precheck `total <= 0.0 ⇒ return None`
    // guarantees we never reach here with all-zero weights, so the
    // selected fallback always represents a family that wasn't filtered.
    // LOW-3 fix from chunk-B /review-impl: replaced an unreachable
    // reverse-scan loop with the chunk-A discipline (single fallback,
    // matches pre-Q6 behavior when family bias is all 1.0).
    Some(pool.last().expect("pool must be non-empty per caller invariant"))
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

    /// TMP-Q6 chunk B — identity multiplier closure used in pre-Q6 tests
    /// that don't care about family bias. Returns 1.0 for every family
    /// so `roll_weighted_tag` reduces to the pre-Q6 behavior.
    fn identity_family_mult(_: Option<&str>) -> f32 {
        1.0
    }

    /// TMP-Q6 chunk B — minimal placer fixture for testing
    /// `resolve_family_multiplier` directly. Constructs a TilemapTemplate
    /// + Registry with the requested decoration_family_density maps so
    /// the resolution chain can be exercised without spinning up the
    /// full place_tilemap pipeline.
    fn make_template_with_family_density(
        map: Option<std::collections::HashMap<String, f32>>,
    ) -> TilemapTemplate {
        use crate::types::template::TilemapTemplateId;
        TilemapTemplate {
            template_id: TilemapTemplateId("rfm_test".to_string()),
            zones: vec![],
            seed_offset: 0,
            world_zone: None,
            decoration_density: None,
            background_biome: None,
            decoration_family_density: map,
        }
    }

    fn make_registry_with_family_density(
        map: Option<std::collections::HashMap<String, f32>>,
    ) -> Registry {
        // Start from the default registry and rewrite its reference's map.
        let mut registry = Registry::load_default().unwrap();
        registry.set_reference_decoration_family_density_for_test(map);
        registry
    }

    #[test]
    fn resolve_family_multiplier_returns_1_0_for_none_family() {
        // LOW-2 fix from chunk-B /review-impl — direct unit test of the
        // "family=None ⇒ multiplier 1.0" invariant. Previously only
        // tested transitively via `roll_weighted_tag_unfamilied_tag_uses_multiplier_1_0`
        // which was tautological (closure under test returned 1.0 for
        // None). Now hits resolve_family_multiplier directly.
        //
        // The closure setup uses a registry+template map that would
        // resolve to 99.0 for any HIT — so if the None-family branch ever
        // consults the maps (e.g. a future refactor that uses an empty
        // string as a "default" key), this test fires.
        let mut bias = std::collections::HashMap::new();
        bias.insert("rock".to_string(), 99.0_f32);
        let template = make_template_with_family_density(Some(bias.clone()));
        let registry = make_registry_with_family_density(Some(bias));
        assert_eq!(
            resolve_family_multiplier(None, &template, &registry),
            1.0,
            "family=None must return 1.0 unconditionally — chunk B's bias only \
             applies to entries that declared ObjectKindDef.family in chunk A"
        );
    }

    #[test]
    fn resolve_family_multiplier_template_hit_overrides_registry() {
        // LOW-2 fix — direct test of resolution chain step 1 (template wins).
        let mut template_map = std::collections::HashMap::new();
        template_map.insert("rock".to_string(), 2.0_f32);
        let mut registry_map = std::collections::HashMap::new();
        registry_map.insert("rock".to_string(), 5.0_f32);
        let template = make_template_with_family_density(Some(template_map));
        let registry = make_registry_with_family_density(Some(registry_map));
        assert_eq!(
            resolve_family_multiplier(Some("rock"), &template, &registry),
            2.0,
            "template's 2.0 must override registry's 5.0 (resolution chain step 1)"
        );
    }

    #[test]
    fn resolve_family_multiplier_registry_fallback_when_template_absent_for_family() {
        // LOW-2 fix — direct test of resolution chain step 2 (registry fallback
        // for a family the template doesn't declare).
        let mut template_map = std::collections::HashMap::new();
        template_map.insert("rock".to_string(), 2.0_f32);
        let mut registry_map = std::collections::HashMap::new();
        registry_map.insert("bone".to_string(), 0.5_f32);
        let template = make_template_with_family_density(Some(template_map));
        let registry = make_registry_with_family_density(Some(registry_map));
        // Template has rock but no bone; registry has bone. Bone lookup
        // falls through to registry.
        assert_eq!(
            resolve_family_multiplier(Some("bone"), &template, &registry),
            0.5,
            "registry's 0.5 must apply when template doesn't declare 'bone' \
             (resolution chain step 2 — sparse template falls back per-family)"
        );
    }

    #[test]
    fn resolve_family_multiplier_defaults_to_1_0_when_neither_layer_declares() {
        // LOW-2 fix — direct test of resolution chain step 3 (default 1.0).
        let template = make_template_with_family_density(None);
        let registry = make_registry_with_family_density(None);
        assert_eq!(
            resolve_family_multiplier(Some("rock"), &template, &registry),
            1.0,
            "neither layer declares any family ⇒ default 1.0"
        );

        // Also: both layers declare maps but neither has 'rock'.
        let mut template_map = std::collections::HashMap::new();
        template_map.insert("bone".to_string(), 2.0_f32);
        let mut registry_map = std::collections::HashMap::new();
        registry_map.insert("vegetation".to_string(), 0.5_f32);
        let template = make_template_with_family_density(Some(template_map));
        let registry = make_registry_with_family_density(Some(registry_map));
        assert_eq!(
            resolve_family_multiplier(Some("rock"), &template, &registry),
            1.0,
            "both layers have maps but neither declares 'rock' ⇒ default 1.0 \
             (sparse-fallthrough-to-default)"
        );
    }

    #[test]
    fn roll_weighted_tag_picks_only_member() {
        let pool = vec![DecorationRef {
            kind_id: "solo".to_string(),
            density_weight: 1.0,
            min_spacing: 0,
            family: None,
        }];
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let picked = roll_weighted_tag(&pool, &identity_family_mult, &mut rng).unwrap();
        assert_eq!(picked.kind_id, "solo");
    }

    #[test]
    fn roll_weighted_tag_handles_tiny_weights_without_panic() {
        // LOW-5 from chunk-C /review-impl. Weights at the f32 precision
        // edge could in theory cause the subtraction loop to underflow
        // before any tag matches `roll <= 0.0`. The function's
        // last-non-zero fallback handles this gracefully. Verify no
        // panic; the returned tag must be a pool member.
        let pool = vec![
            DecorationRef { kind_id: "a".to_string(), density_weight: 1e-7, min_spacing: 0, family: None },
            DecorationRef { kind_id: "b".to_string(), density_weight: 1e-7, min_spacing: 0, family: None },
            DecorationRef { kind_id: "c".to_string(), density_weight: 1e-7, min_spacing: 0, family: None },
        ];
        let mut rng = ChaCha8Rng::seed_from_u64(7);
        for _ in 0..100 {
            let picked = roll_weighted_tag(&pool, &identity_family_mult, &mut rng).unwrap();
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
                family: None,
            },
            DecorationRef {
                kind_id: "common".to_string(),
                density_weight: 0.9,
                min_spacing: 0,
                family: None,
            },
        ];
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let mut common_count = 0;
        for _ in 0..1000 {
            let picked = roll_weighted_tag(&pool, &identity_family_mult, &mut rng).unwrap();
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

    #[test]
    fn roll_weighted_tag_family_bias_up_increases_picks_of_target_family() {
        // TMP-Q6 chunk B AC-DFS-7 — biasing a family up shifts the
        // weighted distribution toward that family's tags. Pool: 1 rock
        // tag + 1 bone tag, both at density_weight 1.0. With identity
        // closure: ~50/50 split. With rock=3.0/bone=1.0: ~75/25 split.
        let pool = vec![
            DecorationRef {
                kind_id: "lw:decoration.boulder".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("rock".to_string()),
            },
            DecorationRef {
                kind_id: "lw:decoration.bones".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("bone".to_string()),
            },
        ];

        // Baseline (identity) — should be ~50/50.
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let mut baseline_rock = 0;
        for _ in 0..2000 {
            let picked = roll_weighted_tag(&pool, &identity_family_mult, &mut rng).unwrap();
            if picked.family.as_deref() == Some("rock") {
                baseline_rock += 1;
            }
        }
        assert!(
            (900..=1100).contains(&baseline_rock),
            "baseline ~50/50, got {baseline_rock} rocks of 2000"
        );

        // Biased — rock=3.0, bone=1.0 → 75/25 mix.
        let biased = |family: Option<&str>| -> f32 {
            match family {
                Some("rock") => 3.0,
                Some("bone") => 1.0,
                _ => 1.0,
            }
        };
        let mut rng2 = ChaCha8Rng::seed_from_u64(42);
        let mut biased_rock = 0;
        for _ in 0..2000 {
            let picked = roll_weighted_tag(&pool, &biased, &mut rng2).unwrap();
            if picked.family.as_deref() == Some("rock") {
                biased_rock += 1;
            }
        }
        assert!(
            biased_rock > baseline_rock,
            "bias-up family must increase picks vs identity: biased={biased_rock} \
             baseline={baseline_rock}"
        );
        assert!(
            (1400..=1600).contains(&biased_rock),
            "biased ~75/25, got {biased_rock} rocks of 2000"
        );
    }

    #[test]
    fn roll_weighted_tag_zero_multiplier_excludes_family_from_pool() {
        // TMP-Q6 chunk B — multiplier 0.0 filters the family out of
        // the weighted roll entirely. Pool: 1 rock + 1 bone, both
        // density_weight 1.0. With bone=0.0, NO bone gets picked.
        let pool = vec![
            DecorationRef {
                kind_id: "rock_tag".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("rock".to_string()),
            },
            DecorationRef {
                kind_id: "bone_tag".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("bone".to_string()),
            },
        ];
        let mult = |family: Option<&str>| -> f32 {
            match family {
                Some("bone") => 0.0,
                _ => 1.0,
            }
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        for _ in 0..500 {
            let picked = roll_weighted_tag(&pool, &mult, &mut rng).unwrap();
            assert_eq!(
                picked.family.as_deref(),
                Some("rock"),
                "bone family must be filtered out by 0.0 multiplier"
            );
        }
    }

    #[test]
    fn roll_weighted_tag_returns_none_when_all_multipliers_zero() {
        // TMP-Q6 chunk B — every family in pool has multiplier 0.0 →
        // total weight 0.0 → returns None. Caller breaks slot loop.
        let pool = vec![
            DecorationRef {
                kind_id: "a".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("rock".to_string()),
            },
            DecorationRef {
                kind_id: "b".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: Some("bone".to_string()),
            },
        ];
        let mult = |_: Option<&str>| 0.0_f32;
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        assert!(roll_weighted_tag(&pool, &mult, &mut rng).is_none());
    }

    #[test]
    fn roll_weighted_tag_unfamilied_tag_uses_multiplier_1_0() {
        // TMP-Q6 chunk B — an entry with family=None is unaffected by
        // family bias (multiplier always 1.0 for None per
        // `resolve_family_multiplier`). The closure here would return
        // 99.0 for ANY family — but since the pool entries have
        // family=None, closure is called with None and the test closure
        // returns 1.0 for None.
        let pool = vec![
            DecorationRef {
                kind_id: "legacy".to_string(),
                density_weight: 1.0,
                min_spacing: 0,
                family: None,
            },
        ];
        let mult = |family: Option<&str>| -> f32 {
            match family {
                None => 1.0,
                _ => 99.0,
            }
        };
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let picked = roll_weighted_tag(&pool, &mult, &mut rng).unwrap();
        assert_eq!(picked.kind_id, "legacy");
    }
}
