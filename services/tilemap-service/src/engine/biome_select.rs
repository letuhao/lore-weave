//! TMP_005 §4.1 — per-zone biome selection. Filters the biome library by the
//! zone's terrain + level, groups by object type, and applies the
//! `BiomeSelectionRules` in priority order with a deterministic ChaCha8
//! sub-stream. `xor_with` is resolved with **one two-coin decision per pair**
//! (spec D3 — `P(neither) = 0.5`, never both).

use std::collections::BTreeMap;

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::seed::{TilemapSeed, sub_seed};
use crate::types::biome::{
    BiomeLevel, BiomeObjectType, BiomeSelection, BiomeSelectionRule, BiomeSet,
};
use crate::types::tile::TerrainKind;
use crate::types::zone::ZoneId;

/// TMP_005 §4.1 — select the biomes for one zone.
///
/// `rules` is the already-resolved rule list (the zone's override or the engine
/// defaults — the caller decides). `library` is `engine_biome_library()`.
/// Deterministic: a per-`(zone, "obstacle_placer:biome_select")` sub-stream.
///
/// §9 TMP-BIOME-Q3 fallback: a rule whose `object_type` has no
/// terrain-matching biome falls back to *all* library biomes of that type
/// (the terrain filter is dropped — see the rule loop); the `BiomeSelection`
/// is still produced, no panic. If the library stocks no biome of that type
/// at all, the rule contributes nothing.
pub fn select_biomes(
    zone_id: &ZoneId,
    terrain: TerrainKind,
    rules: &[BiomeSelectionRule],
    library: &[BiomeSet],
    seed: TilemapSeed,
) -> BiomeSelection {
    // Filter — terrain + level. V1+30d: `factions` / `alignments` are empty on
    // every library biome, so the §4.1 faction/alignment filter passes all.
    let mut by_type: BTreeMap<BiomeObjectType, Vec<&BiomeSet>> = BTreeMap::new();
    for biome in library {
        let level_ok = matches!(biome.level, BiomeLevel::Surface | BiomeLevel::Both);
        if biome.terrain_types.contains(&terrain) && level_ok {
            by_type.entry(biome.object_type).or_default().push(biome);
        }
    }

    let label = format!("obstacle_placer:biome_select:{}", zone_id.0);
    let mut rng = ChaCha8Rng::seed_from_u64(sub_seed(seed, &label));
    let mut selection = BiomeSelection::default();

    // Rules in priority order — `First` < `Normal` < `Last` (stable, so the
    // §2.3 declaration order is the tie-break).
    let mut ordered: Vec<&BiomeSelectionRule> = rules.iter().collect();
    ordered.sort_by_key(|r| r.priority);

    // One decision per `{type, xor_with}` pair, keyed on the sorted pair.
    let mut xor_decision: BTreeMap<(BiomeObjectType, BiomeObjectType), Option<BiomeObjectType>> =
        BTreeMap::new();

    for rule in ordered {
        if let Some(other) = rule.xor_with {
            let key = if rule.object_type <= other {
                (rule.object_type, other)
            } else {
                (other, rule.object_type)
            };
            // First rule of the pair makes the decision; the mirror reads it.
            let decided = *xor_decision.entry(key).or_insert_with(|| {
                // Two 50/50 coins: feature-or-not, then this-or-other.
                if !rng.gen_bool(0.5) {
                    None
                } else if rng.gen_bool(0.5) {
                    Some(key.0)
                } else {
                    Some(key.1)
                }
            });
            if decided != Some(rule.object_type) {
                continue; // the pair chose the other type, or neither
            }
        }

        // §9 TMP-BIOME-Q3 fallback (spec D3): the zone's terrain has no biome
        // of this `object_type` → fall back to *all* library biomes of that
        // type. The terrain filter is dropped; the level filter is kept (a
        // no-op in the all-`Surface` V1+30d library, but it keeps an
        // Underground-only biome off a Surface zone). A `Sea` zone's mandatory
        // `Tree` rule (§2.3, `count_min: 1`) takes this path — §6's Water row
        // has no `Tree` biome.
        let pool: Vec<&BiomeSet> = match by_type.get(&rule.object_type) {
            Some(terrain_matched) => terrain_matched.clone(),
            None => library
                .iter()
                .filter(|b| {
                    b.object_type == rule.object_type
                        && matches!(b.level, BiomeLevel::Surface | BiomeLevel::Both)
                })
                .collect(),
        };
        if pool.is_empty() {
            // No biome of this type anywhere — even the fallback is empty (the
            // library stocks no set of this `object_type` at all).
            continue;
        }
        let count = rng.gen_range(rule.count_min..=rule.count_max);
        for _ in 0..count {
            let pick = pool[rng.gen_range(0..pool.len())];
            selection.push(rule.object_type, pick.biome_id.clone());
        }
    }
    selection
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::biome_library::{engine_biome_library, engine_default_biome_selection_rules};
    use crate::types::biome::{BiomePriority, BiomeSelectionRule};

    fn zone(id: &str) -> ZoneId {
        ZoneId(id.to_string())
    }

    #[test]
    fn selects_only_terrain_matching_biomes_within_count_bounds() {
        // AC-3 — a Grass zone selects only Grass biomes; counts respect rules.
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&zone("z"), TerrainKind::Grass, &rules, &lib, TilemapSeed(1));
        for biome_id in sel.by_type.values().flatten() {
            assert!(biome_id.0.starts_with("grass_"), "non-Grass biome {biome_id:?} selected");
        }
        // §2.3: Mountain count 1..=1, Tree 1..=2.
        assert_eq!(sel.of_type(BiomeObjectType::Mountain).len(), 1);
        assert!((1..=2).contains(&sel.of_type(BiomeObjectType::Tree).len()));
    }

    #[test]
    fn selection_is_deterministic_for_a_fixed_zone_and_seed() {
        // AC-3 — determinism.
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let a = select_biomes(&zone("z"), TerrainKind::Forest, &rules, &lib, TilemapSeed(7));
        let b = select_biomes(&zone("z"), TerrainKind::Forest, &rules, &lib, TilemapSeed(7));
        assert_eq!(a, b);
    }

    #[test]
    fn xor_pair_yields_all_three_outcomes_never_both() {
        // AC-3 — the Lake/Crater xor is one two-coin decision per pair. Run
        // against the **production** `engine_biome_library()` — the engine must
        // stock a `Crater` biome for the xor to work; a synthetic library that
        // hand-stocks Crater would mask an unstocked-Crater regression (the
        // round-3 BLOCK). Custom `count 1..=1` rules make the decision directly
        // observable (`count_min: 0` would fold count-0 draws into `neither`).
        let lib = engine_biome_library();
        let rules = vec![
            BiomeSelectionRule {
                object_type: BiomeObjectType::Lake,
                count_min: 1,
                count_max: 1,
                xor_with: Some(BiomeObjectType::Crater),
                priority: BiomePriority::First,
            },
            BiomeSelectionRule {
                object_type: BiomeObjectType::Crater,
                count_min: 1,
                count_max: 1,
                xor_with: Some(BiomeObjectType::Lake),
                priority: BiomePriority::First,
            },
        ];
        let (mut lake_only, mut crater_only, mut neither) = (0, 0, 0);
        for s in 0..400u64 {
            let sel = select_biomes(&zone("z"), TerrainKind::Grass, &rules, &lib, TilemapSeed(s));
            let has_lake = !sel.of_type(BiomeObjectType::Lake).is_empty();
            let has_crater = !sel.of_type(BiomeObjectType::Crater).is_empty();
            assert!(!(has_lake && has_crater), "xor selected both at seed {s}");
            match (has_lake, has_crater) {
                (true, false) => lake_only += 1,
                (false, true) => crater_only += 1,
                (false, false) => neither += 1,
                _ => unreachable!(),
            }
        }
        assert!(
            lake_only > 0 && crater_only > 0 && neither > 0,
            "an outcome never occurred — lake_only={lake_only} crater_only={crater_only} \
             neither={neither} (crater_only=0 ⇒ engine_biome_library stocks no Crater biome)",
        );
        // two-coin model: P(neither) = 0.5 — assert a wide band clear of 0.25.
        assert!((140..=260).contains(&neither), "neither={neither}/400 — off the 0.5 model");
    }

    #[test]
    fn xor_realized_water_feature_rate_on_engine_defaults() {
        // AC-3 — the *realized* rate with the SHIPPED §2.3 rules. The xor
        // *decision* picks a feature-type ≈50 % of the time (verified by
        // `xor_pair_yields_all_three_outcomes_never_both` with `count` pinned
        // to 1); the §2.3 default `Lake`/`Crater` rules then draw `count 0..=1`,
        // independently halving each chosen type — so a water-feature biome
        // actually appears ≈0.25 of the time, `neither` ≈0.75. The xor
        // invariant (never both) and Crater reachability hold on the shipped
        // rule config too, not only the count-1 test config.
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let (mut lake, mut crater, mut neither) = (0, 0, 0);
        for s in 0..400u64 {
            let sel = select_biomes(&zone("z"), TerrainKind::Grass, &rules, &lib, TilemapSeed(s));
            let has_lake = !sel.of_type(BiomeObjectType::Lake).is_empty();
            let has_crater = !sel.of_type(BiomeObjectType::Crater).is_empty();
            assert!(!(has_lake && has_crater), "xor selected both at seed {s}");
            if has_lake {
                lake += 1;
            }
            if has_crater {
                crater += 1;
            }
            if !has_lake && !has_crater {
                neither += 1;
            }
        }
        assert!(lake > 0 && crater > 0, "a water-feature type never appeared — lake={lake} crater={crater}");
        // Realized `neither` ≈0.75 — clearly above the 0.5 xor-decision rate
        // (the §2.3 `count 0-1` adds the second halving), well below 1.0.
        assert!(
            (240..=360).contains(&neither),
            "neither={neither}/400 — off the realized ≈0.75 model (decision ≈0.5 × count≥1 ≈0.5)",
        );
    }

    #[test]
    fn q3_fallback_fills_a_terrain_with_no_native_biomes() {
        // AC-4 — §9 Q3: `Subterranean` has no library biome of *any* type, so
        // every rule takes the all-templates-of-type fallback. The selection is
        // non-empty (no panic, no silent skip): the two mandatory `count_min ≥
        // 1` rules — Mountain and Tree — are always satisfied by the fallback.
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&zone("cave"), TerrainKind::Subterranean, &rules, &lib, TilemapSeed(3));
        assert!(!sel.is_empty(), "the §9 Q3 fallback must still produce a selection");
        assert_eq!(sel.of_type(BiomeObjectType::Mountain).len(), 1, "Mountain count 1..=1 via fallback");
        assert!(
            (1..=2).contains(&sel.of_type(BiomeObjectType::Tree).len()),
            "the mandatory Tree rule (count_min 1) must be satisfied by the fallback",
        );
    }

    #[test]
    fn sea_zone_gets_trees_via_the_q3_fallback() {
        // AC-1 / AC-4 — TMP_005 §6's Water row has no `Tree` biome, yet the
        // §2.3 Tree rule is mandatory (`count_min: 1`). A `Water`-terrain zone
        // must take the §9 Q3 fallback and still select ≥1 Tree.
        let lib = engine_biome_library();
        let rules = engine_default_biome_selection_rules();
        let sel = select_biomes(&zone("inland_sea"), TerrainKind::Water, &rules, &lib, TilemapSeed(11));
        assert!(
            !sel.of_type(BiomeObjectType::Tree).is_empty(),
            "a Water zone must get Tree biomes via the Q3 fallback (no native Water Tree)",
        );
        // The fallback Tree biomes are land biomes — the library stocks no
        // `water_tree` set, so no selected Tree is a Water biome.
        for tree in sel.of_type(BiomeObjectType::Tree) {
            assert!(!tree.0.starts_with("water_"), "no Water Tree biome exists: {tree:?}");
        }
    }

    #[test]
    fn priority_order_is_first_normal_last() {
        // AC-3 — `select_biomes` sorts rules First → Normal → Last. A rule list
        // disordered *across* priorities (the `Last` rule rotated to the front,
        // within-priority order untouched) yields the same selection as the
        // priority-ordered list. (Re-ordering rules *within* a priority does
        // change the RNG draw order and is legitimately not invariant.)
        let lib = engine_biome_library();
        let mut rotated = engine_default_biome_selection_rules();
        rotated.rotate_right(1); // the `Other` (Last) rule jumps to the front
        let a = select_biomes(&zone("z"), TerrainKind::Snow, &rotated, &lib, TilemapSeed(5));
        let ordered = engine_default_biome_selection_rules(); // already First→Last
        let b = select_biomes(&zone("z"), TerrainKind::Snow, &ordered, &lib, TilemapSeed(5));
        assert_eq!(a, b, "cross-priority disorder must not change the selection");
        assert_eq!(a.of_type(BiomeObjectType::Mountain).len(), 1, "First Mountain rule → 1");
    }
}
