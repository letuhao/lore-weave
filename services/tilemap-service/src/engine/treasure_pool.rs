//! TMP_006 §3.1 / spec D1 — the V1+30d treasure-object value pool.
//!
//! A small fixed set of generic value-bearing objects (scattered gold, caches,
//! chests, hoards) the pile composer draws from. The V2 special object sources
//! — Dwellings, Seer Huts, Prisons, Pandora Boxes (TMP_006 §3.1 sources 2-5) —
//! are out of scope; the V1+30d pool is generic value containers only.
//!
//! Mirrors `biome_library.rs`: a fixed-order `Vec` built by one engine
//! function, so the pool is deterministic (TMP-A4) and `engine_treasure_pool()`
//! is its single source.

/// One value-bearing object the pile composer draws from (TMP_006 §3.1).
///
/// `value` is the object's gold worth (summed into a pile's value); `rarity`
/// is its weighted-pick weight — a higher `rarity` is sampled more often, so
/// cheap objects are common and dear ones rare. A `TreasureObject` carries no
/// footprint: a V1+30d pile places as a single 1×1 `Treasure` object (spec
/// D1/D4), so the pool is a pure value/rarity distribution, never a placement
/// template.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TreasureObject {
    /// Stable identifier — debugging / future authoring, not placement.
    pub id: &'static str,
    /// Gold worth contributed to a composed pile's value sum. Always > 0.
    pub value: u32,
    /// Weighted-pick weight — higher is sampled more often. Always > 0 (a
    /// zero-weight object could never be picked).
    pub rarity: u16,
}

/// The fixed V1+30d treasure-object pool (spec D1).
///
/// A deliberate value spread — `scattered_gold` (cheap, common) through
/// `great_hoard` (dear, rare) — so `compose_pile` can land piles across the
/// TMP_006 §2.3-style tier ranges (low `[min, max]` from a single cheap object,
/// high tiers by summing). The order is fixed, so every call returns an equal
/// `Vec` — the determinism `compose_pile` and AC-1 rely on (TMP-A4).
pub fn engine_treasure_pool() -> Vec<TreasureObject> {
    vec![
        TreasureObject { id: "scattered_gold", value: 250, rarity: 100 },
        TreasureObject { id: "coin_pouch", value: 500, rarity: 64 },
        TreasureObject { id: "decorative_cache", value: 750, rarity: 40 },
        TreasureObject { id: "jeweled_casket", value: 1200, rarity: 22 },
        TreasureObject { id: "treasure_chest", value: 2000, rarity: 12 },
        TreasureObject { id: "rich_hoard", value: 5000, rarity: 5 },
        TreasureObject { id: "great_hoard", value: 9000, rarity: 2 },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pool_is_non_empty_and_deterministic() {
        // AC-1 — the pool is non-empty and the same call yields an equal Vec
        // (a fixed-order Vec literal — TMP-A4).
        let a = engine_treasure_pool();
        let b = engine_treasure_pool();
        assert!(!a.is_empty(), "the treasure pool must be non-empty");
        assert_eq!(a, b, "engine_treasure_pool() must be deterministic");
    }

    #[test]
    fn every_object_has_positive_value_and_rarity() {
        // AC-1 — value > 0 (a zero-value object never advances a pile toward
        // its tier min) and rarity > 0 (a zero-weight object can never be
        // picked, so it would be dead pool weight).
        for obj in engine_treasure_pool() {
            assert!(obj.value > 0, "{} has value 0", obj.id);
            assert!(obj.rarity > 0, "{} has rarity 0", obj.id);
        }
    }

    #[test]
    fn pool_has_a_wide_value_spread() {
        // AC-1 — a real spread: the cheapest object is far cheaper than the
        // dearest, so piles can be composed across both low and high tiers.
        let pool = engine_treasure_pool();
        let min = pool.iter().map(|o| o.value).min().expect("pool is non-empty");
        let max = pool.iter().map(|o| o.value).max().expect("pool is non-empty");
        assert!(min < max, "the pool has no value spread: min {min} == max {max}");
        assert!(
            max >= min * 10,
            "the spread is not wide: cheapest {min}, dearest {max}",
        );
    }
}
