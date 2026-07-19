//! TMP_006 §3.3-§3.4 / spec D2-D3 — treasure-pile composition + spacing.
//!
//! [`compose_pile`] samples the [`engine_treasure_pool`](crate::engine::treasure_pool::engine_treasure_pool)
//! objects — weighted by `rarity`, value-capped — until a running value sum
//! lands inside a tier's `[min, max]` window. [`min_distance`] scales the
//! placement spacing a pile demands by its value. All three functions are pure
//! (the RNG is the caller's): the same `(pool, tier, rng-state)` always
//! composes the same pile, the basis of the TMP-A4 determinism axiom.

use rand::Rng;

use crate::engine::treasure_pool::TreasureObject;
use crate::types::treasure::TreasureTierSpec;

/// A composed treasure pile (TMP_006 §3.3) — build-internal, no placement
/// record yet. `value` is the summed gold worth of the objects drawn;
/// `object_count` is how many pool draws composed it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TreasurePile {
    /// Summed gold value — lands inside the composing tier's `[min, max]`.
    pub value: u32,
    /// Number of pool objects summed into the pile (≥ 1 for any pile
    /// [`compose_pile`] returns).
    pub object_count: u32,
}

/// [`compose_pile`]'s belt-and-suspenders iteration cap (TMP_006 §3.3). Every
/// pool object has `value > 0`, so a pile's running sum strictly increases each
/// iteration and the loop self-terminates well before this — the cap only
/// matters if that pool invariant is ever violated. Kept verbatim from §3.3
/// rather than silently dropped.
const MAX_COMPOSE_ATTEMPTS: u32 = 100;

/// TMP_006 §3.3 / spec D2 — pick one pool object weighted by `rarity` from the
/// **eligible** subset (`value ≤ value_cap`), or `None` if no pool object fits
/// under the cap.
///
/// One `gen_range` roll over the eligible objects' summed `rarity` weights,
/// resolved by a fixed-pool-order cumulative walk — so the pick is fully
/// determined by the RNG state (TMP-A4). A higher-`rarity` object claims a
/// wider slice of the roll and is picked more often.
pub fn sample_weighted_by_rarity(
    pool: &[TreasureObject],
    value_cap: u32,
    rng: &mut impl Rng,
) -> Option<TreasureObject> {
    // Total weight over the eligible (value ≤ cap) subset, in fixed pool order.
    let total: u32 = pool
        .iter()
        .filter(|o| o.value <= value_cap)
        .map(|o| u32::from(o.rarity))
        .sum();
    // total == 0 ⇒ no pool object fits under the cap (the pool guarantees
    // rarity > 0, so a zero total cannot mean "eligible but weightless"): the
    // sampler is dry.
    if total == 0 {
        return None;
    }
    let roll = rng.random_range(0..total);
    let mut acc: u32 = 0;
    for obj in pool.iter().filter(|o| o.value <= value_cap) {
        acc += u32::from(obj.rarity);
        if roll < acc {
            return Some(*obj);
        }
    }
    // `roll < total` and the cumulative weights reach exactly `total` at the
    // last eligible object, so the loop always returns above.
    unreachable!("weighted pick fell through: roll {roll} >= total {total}")
}

/// TMP_006 §3.3 / spec D2 — compose one treasure pile for `tier`, or `None` on
/// a failed composition.
///
/// A `max == 0` tier is TMP_006 §2's filler/empty tier (`{0, 0, 1}`) — it
/// composes nothing and returns `None` immediately. Otherwise the loop draws
/// pool objects (value-capped to keep the running sum ≤ `tier.max`) until the
/// sum reaches `tier.min` — a non-filler tier always composes ≥ 1 object, even
/// a `min == 0` one. It returns `Some` iff the pile holds ≥ 1 object and its
/// value landed in `[tier.min, tier.max]`; a `None` means the sampler ran dry
/// (no pool object fit under the shrinking value cap) before reaching `min`.
pub fn compose_pile(
    pool: &[TreasureObject],
    tier: TreasureTierSpec,
    rng: &mut impl Rng,
) -> Option<TreasurePile> {
    // The filler/empty tier composes no pile — never a phantom
    // `Some(value: 0, object_count: 0)`.
    if tier.max == 0 {
        return None;
    }
    let mut running_sum: u32 = 0;
    let mut object_count: u32 = 0;
    let mut attempts: u32 = 0;
    // Loop while the pile has not reached `tier.min` OR holds no object yet,
    // bounded by the §3.3 attempt cap.
    while (running_sum < tier.min || object_count == 0) && attempts < MAX_COMPOSE_ATTEMPTS {
        // `value_cap` keeps `running_sum ≤ tier.max` by construction (a drawn
        // object has `value ≤ value_cap`), so this subtraction never underflows.
        let value_cap = tier.max - running_sum;
        match sample_weighted_by_rarity(pool, value_cap, rng) {
            Some(obj) => {
                running_sum += obj.value;
                object_count += 1;
                attempts += 1;
            }
            // Sampler dry — no pool object fits under `value_cap`; the pile
            // cannot grow further, so stop (a failed composition).
            None => break,
        }
    }
    // Success iff ≥ 1 object AND the value landed in the tier window.
    if object_count >= 1 && (tier.min..=tier.max).contains(&running_sum) {
        Some(TreasurePile { value: running_sum, object_count })
    } else {
        None
    }
}

/// TMP_006 §3.4 / spec D3 — the minimum spacing a pile of `value` demands from
/// every other placed object: `√(value / 100) + 5`. A 5-tile floor (low-value
/// piles may cluster), growing with the square root of value (high-value piles
/// spread out). Pure function.
pub fn min_distance(value: u32) -> f32 {
    (value as f32 / 100.0).sqrt() + 5.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::treasure_pool::engine_treasure_pool;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn sample_weighted_by_rarity_never_exceeds_the_value_cap() {
        // AC-2 — the sampler never returns an object dearer than the cap; a
        // cap below the cheapest object yields None (no eligible object).
        let pool = engine_treasure_pool();
        let mut rng = ChaCha8Rng::seed_from_u64(0x5A3);
        for cap in [0u32, 100, 250, 600, 1500, 9000, 50_000] {
            for _ in 0..200 {
                if let Some(obj) = sample_weighted_by_rarity(&pool, cap, &mut rng) {
                    assert!(
                        obj.value <= cap,
                        "sampled {} (value {}) over cap {cap}",
                        obj.id, obj.value,
                    );
                }
            }
        }
    }

    #[test]
    fn compose_pile_lands_inside_a_reachable_tier() {
        // AC-2 — a non-filler tier the pool can reach composes a pile with
        // value in `[min, max]` and ≥ 1 object. `[1000, 6000]` is reachable
        // for every seed: while `running_sum < 1000` the value cap stays well
        // above the cheapest object, so the sampler never dries early.
        let pool = engine_treasure_pool();
        let tier = TreasureTierSpec { min: 1000, max: 6000, density: 1 };
        for seed in 0..64u64 {
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            let pile = compose_pile(&pool, tier, &mut rng)
                .unwrap_or_else(|| panic!("reachable tier failed to compose at seed {seed}"));
            assert!(pile.object_count >= 1, "seed {seed}: object_count is 0");
            assert!(
                (tier.min..=tier.max).contains(&pile.value),
                "seed {seed}: pile value {} outside [{}, {}]",
                pile.value, tier.min, tier.max,
            );
        }
    }

    #[test]
    fn compose_pile_is_deterministic_for_a_fixed_tier_and_seed() {
        // AC-2 — same `(tier, seed)` ⇒ identical pile.
        let pool = engine_treasure_pool();
        let tier = TreasureTierSpec { min: 1500, max: 6000, density: 1 };
        let a = compose_pile(&pool, tier, &mut ChaCha8Rng::seed_from_u64(0xD00D));
        let b = compose_pile(&pool, tier, &mut ChaCha8Rng::seed_from_u64(0xD00D));
        assert_eq!(a, b, "compose_pile must be deterministic for a fixed (tier, seed)");
    }

    #[test]
    fn compose_pile_returns_none_for_a_tier_below_the_cheapest_object() {
        // AC-2 — `max` below the cheapest pool object: the sampler is dry on
        // the very first draw, so compose_pile returns None (it does not hang).
        let pool = engine_treasure_pool();
        let cheapest = pool.iter().map(|o| o.value).min().expect("pool is non-empty");
        let tier = TreasureTierSpec { min: 1, max: cheapest - 1, density: 1 };
        for seed in 0..16u64 {
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            assert!(
                compose_pile(&pool, tier, &mut rng).is_none(),
                "seed {seed}: a tier below the cheapest object must not compose",
            );
        }
    }

    #[test]
    fn compose_pile_returns_none_for_an_unreachable_narrow_tier() {
        // AC-2 — the genuine high-side unreachable case. `[260, 480]`: the
        // first draw can only be the 250-value object (the sole one ≤ 480);
        // the running sum is then 250 < 260, and the value cap drops to 230 —
        // below the cheapest object — so the sampler dries and the sum is
        // stranded short of `min`. None for every seed (the first draw is
        // forced, so the result does not depend on the RNG).
        let pool = engine_treasure_pool();
        let tier = TreasureTierSpec { min: 260, max: 480, density: 1 };
        for seed in 0..16u64 {
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            assert!(
                compose_pile(&pool, tier, &mut rng).is_none(),
                "seed {seed}: a narrow value-cap-stranded tier must not compose",
            );
        }
    }

    #[test]
    fn compose_pile_reaches_a_tier_above_total_pool_value_by_repetition() {
        // The pool is sampled WITH replacement (D1 — a value/rarity
        // distribution), so a tier whose `min` exceeds the pool's total object
        // value is still reachable: objects repeat. This is why AC-2's genuine
        // "unreachable" case is a value-cap-stranded window (the test above),
        // not simply `min > sum(pool values)`.
        let pool = engine_treasure_pool();
        let total: u32 = pool.iter().map(|o| o.value).sum();
        let tier = TreasureTierSpec { min: total + 1000, max: total * 4, density: 1 };
        let mut rng = ChaCha8Rng::seed_from_u64(7);
        let pile = compose_pile(&pool, tier, &mut rng)
            .expect("repeated draws reach a tier above the pool total");
        assert!(
            (tier.min..=tier.max).contains(&pile.value),
            "pile value {} outside [{}, {}]",
            pile.value, tier.min, tier.max,
        );
        assert!(pile.object_count >= 2, "a tier above the pool total needs repeated draws");
    }

    #[test]
    fn compose_pile_returns_none_for_the_filler_tier() {
        // AC-2 — TMP_006 §2's filler tier `{0, 0, 1}` (max == 0) composes no
        // pile; never a phantom `Some(value: 0, object_count: 0)`.
        let pool = engine_treasure_pool();
        let filler = TreasureTierSpec { min: 0, max: 0, density: 1 };
        let mut rng = ChaCha8Rng::seed_from_u64(0);
        assert!(compose_pile(&pool, filler, &mut rng).is_none());
    }

    #[test]
    fn min_distance_is_at_least_five_at_zero() {
        // AC-3 — the 5-tile floor: even a zero-value pile keeps a 5-tile gap.
        assert!(min_distance(0) >= 5.0, "min_distance(0) = {}", min_distance(0));
    }

    #[test]
    fn min_distance_is_monotonic_non_decreasing() {
        // AC-3 — a dearer pile demands at least as much spacing as a cheaper
        // one (√ is monotonic, the +5 floor is constant).
        let mut prev = min_distance(0);
        for value in (0..=20_000).step_by(50) {
            let d = min_distance(value);
            assert!(d >= prev, "min_distance not monotonic: {value} gave {d} < {prev}");
            prev = d;
        }
    }

    #[test]
    fn compose_pile_terminates_on_a_degenerate_zero_value_pool() {
        // The production pool guarantees every object `value > 0` (AC-1), so
        // the running sum strictly increases and the loop self-terminates well
        // before MAX_COMPOSE_ATTEMPTS — the cap never fires in production. A
        // hand-built pool with a sole 0-value object is the only way to drive
        // the loop to the cap: the sum never advances, so the `attempts < 100`
        // conjunct is what must stop the loop and yield `None` (no hang).
        let degenerate = [TreasureObject { id: "void", value: 0, rarity: 1 }];
        let tier = TreasureTierSpec { min: 100, max: 1000, density: 1 };
        let mut rng = ChaCha8Rng::seed_from_u64(0);
        assert!(
            compose_pile(&degenerate, tier, &mut rng).is_none(),
            "a zero-value pool cannot reach a positive `min` — the attempt cap must yield None",
        );
    }

    #[test]
    fn compose_pile_returns_none_for_a_malformed_min_greater_than_max_tier() {
        // A tier whose `min` exceeds its `max` is an author error. `compose_pile`
        // must return `None` (the running sum can never satisfy the empty
        // `[min, max]` window) without panicking or hanging.
        let pool = engine_treasure_pool();
        let malformed = TreasureTierSpec { min: 5000, max: 800, density: 1 };
        for seed in 0..8u64 {
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            assert!(
                compose_pile(&pool, malformed, &mut rng).is_none(),
                "seed {seed}: a min>max tier must not compose",
            );
        }
    }
}
