//! COMB_001 §4 — the combat laws, asserted as laws.
//!
//! These test the engine (`commit_service::combat`) directly rather than
//! through the island, because a law is a property of the rule and not of the
//! plumbing: `hit_chance` clamps, the damage chain floors at 1, initiative
//! picks the lowest AV. Driving each through a full island step would make a
//! failure say "the encounter is wrong" when the useful message is "the clamp
//! is wrong".
//!
//! The domain-level behaviour (rounds, KO, win/lose through `apply`) is
//! covered in `combat_encounter.rs`.

use commit_service::combat::{
    action_value, evaluate_outcome, hit_chance_pm, next_actor, resolve_attack, role_rng, AvStatus,
    CombatStats, EncounterOutcome, SeedRole, Side,
};
use commit_service::{CombatRules, StatRules};
use sim_core::EntityId;

const SEED: u64 = 0xC0FFEE;

/// F1 — the laws now take their constants by reference instead of embedding
/// them. These helpers supply the `engine_default` layer, which holds exactly
/// the literals the laws used to contain, so every expected value below is
/// unchanged. **A test that needed its expected value edited would be a
/// migration bug, not a test bug** — that is what makes this suite the proof
/// the constant move was value-preserving.
fn crules() -> CombatRules {
    CombatRules::engine_default()
}

fn srules() -> StatRules {
    StatRules::engine_default()
}

fn atk() -> CombatStats {
    CombatStats::archetype_melee(&srules(), 100)
}

// ───────────────────────────── hit / dodge ──────────────────────────────────

/// `clamp(0.5 + acc − dodge, 0.05, 0.95)`.
///
/// The clamps are the interesting part and each has a failure mode: without
/// the ceiling, stacking accuracy makes a build unmissable and dodge stops
/// being a stat; without the floor, a high-dodge target is untouchable and the
/// encounter can never resolve.
#[test]
fn hit_chance_is_clamped_at_both_ends() {
    assert_eq!(hit_chance_pm(&crules(), 0, 0), 500, "the 0.5 base, in per-mille");
    assert_eq!(hit_chance_pm(&crules(), 10_000, 0), 950, "no build is unmissable");
    assert_eq!(hit_chance_pm(&crules(), 0, 10_000), 50, "no target is untouchable");
    // Monotonic in between: more accuracy is never worse.
    assert!(hit_chance_pm(&crules(), 300, 100) > hit_chance_pm(&crules(), 200, 100));
    assert!(hit_chance_pm(&crules(), 200, 200) < hit_chance_pm(&crules(), 200, 100));
}

// ──────────────────────────── damage law-chain ──────────────────────────────

/// `max(1, sp − armor)` — the floor that keeps a heavily-armoured target
/// killable. Without it, armor ≥ strike_power makes damage 0 and the fight
/// becomes a stalemate the win/lose rule has no answer for.
#[test]
fn armor_cannot_make_a_target_immortal() {
    let mut a = atk();
    // NOTE: high accuracy does NOT guarantee a hit — `hit_chance` clamps at
    // 0.95, so ~5% still miss BY DESIGN. Sampling and filtering to the hits is
    // the honest way to isolate the damage law; asserting a single attack lands
    // would be a 1-in-20 flake.
    a.accuracy_pm = 10_000;
    let mut tank = atk();
    tank.armor = 9_999;
    tank.dodge_pm = 0;

    let hits: Vec<i64> = (0..50)
        .map(|i| resolve_attack(&crules(), &a, &tank, false, SEED, EntityId(1), i))
        .filter(|o| o.hit)
        .map(|o| o.damage)
        .collect();
    assert!(!hits.is_empty(), "at a 0.95 ceiling, 50 attempts land something");
    assert!(
        hits.iter().all(|d| *d >= 1),
        "damage floors at 1 however thick the armor: {hits:?}"
    );
}

/// The variance band is 0.85–1.15 and it is real: over many action indices the
/// same matchup must produce more than one damage value.
///
/// Kill-mutation: dropping the roll (a fixed 1.0 multiplier) makes combat
/// deterministic in the boring sense — every hit identical — which reads as a
/// broken game rather than a fair one.
#[test]
fn damage_varies_within_the_locked_band() {
    let mut a = atk();
    a.accuracy_pm = 10_000;
    a.crit_chance_pm = 0; // isolate the damage roll from crit
    let d = atk();

    // Filter to hits: a miss is damage 0 by design (and a separate law), so
    // including them here would test `hit_chance`, not the damage band.
    let dmgs: Vec<i64> = (0..200)
        .map(|i| resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), i))
        .filter(|o| o.hit)
        .map(|o| o.damage)
        .collect();

    let base = (a.strike_power - d.armor).max(1) as f64;
    let (lo, hi) = (
        (base * 0.85).floor().max(1.0) as i64,
        (base * 1.15).floor().max(1.0) as i64,
    );
    assert!(dmgs.iter().all(|x| (lo..=hi).contains(x)), "all rolls inside 0.85–1.15: {dmgs:?}");
    assert!(dmgs.iter().any(|x| *x != dmgs[0]), "the roll actually varies");
}

/// Defending halves the hit and never zeroes it.
#[test]
fn defending_halves_but_never_negates() {
    let mut a = atk();
    a.accuracy_pm = 10_000;
    let d = atk();

    let mut compared = 0;
    for i in 0..50 {
        let open = resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), i);
        let guarded = resolve_attack(&crules(), &a, &d, true, SEED, EntityId(1), i);
        // Same coordinate ⇒ same hit roll, so the two agree on landing.
        assert_eq!(open.hit, guarded.hit, "defending must not change WHETHER it hits");
        if !open.hit {
            continue;
        }
        compared += 1;
        assert!(guarded.damage >= 1, "a defended hit still hurts");
        assert!(guarded.damage <= open.damage, "defending never INCREASES damage");
    }
    assert!(compared > 0, "the comparison actually ran on landed hits");
}

// ─────────────────────────── seed independence ──────────────────────────────

/// **The property that makes replay survivable.** Each roll derives from its
/// own `(actor, action_idx, role)` coordinate, so rolls do not depend on draw
/// ORDER. Adding a new random call elsewhere — a future ability, a loot roll —
/// must not renumber existing rolls.
///
/// Kill-mutation: drawing sequentially from one shared stream. Every historical
/// encounter would then replay differently the first time a new roll is added
/// anywhere, and nothing would point at the cause.
#[test]
fn rolls_are_independent_of_draw_order() {
    let a = EntityId(7);
    let direct = role_rng(SEED, a, 3, SeedRole::Damage).next_u64();

    // Consume unrelated streams first; the damage roll must be unmoved.
    let mut noise = role_rng(SEED, a, 3, SeedRole::Hit);
    for _ in 0..100 {
        noise.next_u64();
    }
    let _ = role_rng(SEED, EntityId(9), 42, SeedRole::Loot).next_u64();

    assert_eq!(direct, role_rng(SEED, a, 3, SeedRole::Damage).next_u64());
}

/// Different roles at the same coordinate must not correlate — otherwise a
/// lucky hit implies a lucky damage roll and variance collapses in a way
/// players feel as "streaky".
#[test]
fn roles_do_not_collide() {
    let a = EntityId(1);
    let vals: Vec<u64> = [SeedRole::Damage, SeedRole::Crit, SeedRole::Hit, SeedRole::Position]
        .into_iter()
        .map(|r| role_rng(SEED, a, 5, r).next_u64())
        .collect();
    let mut uniq = vals.clone();
    uniq.sort_unstable();
    uniq.dedup();
    assert_eq!(uniq.len(), vals.len(), "each role gets its own stream: {vals:?}");
}

// ───────────────────────────── initiative ───────────────────────────────────

/// `av = 10000 / speed`, and status mutates it by the locked percentages.
#[test]
fn action_value_follows_speed_and_status() {
    let base = action_value(&crules(), 100, AvStatus::default(), false);
    assert_eq!(base, 100, "10000/100");

    assert!(action_value(&crules(), 200, AvStatus::default(), false) < base, "faster acts sooner");
    assert_eq!(action_value(&crules(), 100, AvStatus { slowed: true, ..Default::default() }, false), 120);
    assert_eq!(action_value(&crules(), 100, AvStatus { hasted: true, ..Default::default() }, false), 80);
    assert_eq!(action_value(&crules(), 100, AvStatus { stunned: true, ..Default::default() }, false), 200);
    assert_eq!(action_value(&crules(), 100, AvStatus::default(), true), 75, "initiator head start");
}

/// Speed 0 must not divide by zero. A stat debuff that over-subtracts would
/// otherwise panic inside `apply` — contained by the kernel as a poison pill,
/// but the encounter is dead either way.
#[test]
fn zero_speed_does_not_divide_by_zero() {
    assert!(action_value(&crules(), 0, AvStatus::default(), false) > 0);
    assert!(action_value(&crules(), -5, AvStatus::default(), false) > 0);
}

/// Lowest AV acts; ties break on entity id so the order is replay-stable.
/// Kill-mutation: breaking ties by iteration order of a hash container would
/// make the queue depend on something outside replay state, and the CNC-D5
/// conformance test would start failing.
#[test]
fn lowest_action_value_acts_and_ties_are_stable() {
    let q = [(EntityId(3), 120), (EntityId(1), 90), (EntityId(2), 90)];
    assert_eq!(next_actor(&q), Some(EntityId(1)), "lowest AV, lowest id on a tie");
    assert_eq!(next_actor(&[]), None, "an empty queue has nobody up");
}

// ────────────────────────────── win / lose ──────────────────────────────────

fn who(side: Side, hp: i64, fled: bool) -> (Side, i64, bool) {
    (side, hp, fled)
}

#[test]
fn victory_defeat_and_disengage() {
    // Both sides standing — unresolved.
    assert_eq!(
        evaluate_outcome([who(Side::A, 10, false), who(Side::B, 10, false)].into_iter()),
        None
    );
    assert_eq!(
        evaluate_outcome([who(Side::A, 10, false), who(Side::B, 0, false)].into_iter()),
        Some(EncounterOutcome::Victory)
    );
    assert_eq!(
        evaluate_outcome([who(Side::A, 0, false), who(Side::B, 10, false)].into_iter()),
        Some(EncounterOutcome::Defeat)
    );
}

/// **Fleeing is neither death nor presence.** Counting a fled actor as dead
/// would make running away a loss for your own side; counting it as present
/// would leave the encounter unable to end at all.
#[test]
fn fleeing_is_not_dying() {
    // Everyone alive but fled ⇒ Disengaged, not Victory or Defeat.
    assert_eq!(
        evaluate_outcome([who(Side::A, 10, true), who(Side::B, 10, true)].into_iter()),
        Some(EncounterOutcome::Disengaged)
    );
    // One side flees, the other stands ⇒ the standing side wins.
    assert_eq!(
        evaluate_outcome([who(Side::A, 10, false), who(Side::B, 10, true)].into_iter()),
        Some(EncounterOutcome::Victory)
    );
}

/// Misses actually happen, at roughly the rate the clamp implies.
///
/// This is a RATE and needs sampling — asserting it from a single encounter
/// makes the test a coin-flip on the seed. The archetype is accuracy 450‰ /
/// dodge 100‰, so `hit_chance = clamp(500 + 450 − 100) = 850‰`: about one in
/// seven attacks should miss.
///
/// Kill-mutation: dropping the hit roll entirely (every attack lands) — combat
/// becomes deterministic in the boring sense and dodge stops existing.
#[test]
fn misses_occur_at_the_archetype_rate() {
    let (a, d) = (atk(), atk());
    let n = 2_000;
    let hits = (0..n)
        .filter(|i| resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), *i).hit)
        .count();

    let expected = hit_chance_pm(&crules(), a.accuracy_pm, d.dodge_pm); // 850
    assert_eq!(expected, 850, "the archetype's hit chance is what we think");

    let observed_pm = (hits as i64 * 1000) / n as i64;
    assert!(
        (observed_pm - expected).abs() < 40,
        "observed {observed_pm}‰ vs expected {expected}‰ over {n} attacks"
    );
    assert!(hits < n as usize, "some attacks DO miss");
}

/// DF07 §8.1 mapping: the combat view reads the right slots, and the
/// per-mille slots stay per-mille rather than being silently divided twice.
#[test]
fn the_combat_view_maps_the_df07_slots() {
    use commit_service::stats::{resolve_block, StatBlock, StatSlot};

    let mut arch = StatBlock::from_defaults(&srules());
    arch.set(StatSlot::StrikePower, 33);
    arch.set(StatSlot::Armor, 7);
    arch.set(StatSlot::Accuracy, 321);
    arch.set(StatSlot::Speed, 250);
    let block = resolve_block(&arch, &[], &[], &[], &srules());
    let view = CombatStats::from_block(&block);

    assert_eq!(view.strike_power, 33);
    assert_eq!(view.armor, 7);
    assert_eq!(view.accuracy_pm, 321, "per-mille stays per-mille");
    assert_eq!(view.speed, 250);
    assert_eq!(view.crit_mult_pm, 1500, "engine default 1.5x survives (DF7-A6)");
}

/// **XST-D3 — the damage variance band reaches BOTH of its declared ends.**
///
/// `850 + roll_pm(..) * 300 / 1000` over a `0..=999` draw yields **850..=1149**:
/// the top of the declared 0.85–1.15 band was unreachable, and the mean landed
/// at 999.400‰ rather than 1000‰. Small, but it is a BIAS, not noise — it never
/// averages out, so every fight was permanently ~0.06 % weaker than the spec.
///
/// `damage_varies_within_the_locked_band` above could not catch this: it asserts
/// every roll is INSIDE the band, which a band that never reaches its top
/// satisfies perfectly. A containment test cannot detect a missing endpoint.
///
/// Kill-mutation: restore `850 + roll_pm(..) * 300 / 1000` → `hi` is 1149.
#[test]
fn the_damage_band_reaches_both_ends_and_centres_on_one() {
    // strike_power 1000 against armor 0 makes `base` exactly 1000, so a landed
    // non-crit hit's damage IS the band value in per-mille — read directly off
    // the damage rather than inferred from the formula.
    let mut a = atk();
    a.strike_power = 1000;
    a.accuracy_pm = 10_000;
    a.crit_chance_pm = 0;
    let mut d = atk();
    d.armor = 0;
    d.dodge_pm = 0;

    let dmgs: Vec<i64> = (0..4000)
        .map(|i| resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), i))
        .filter(|o| o.hit)
        .map(|o| o.damage)
        .collect();

    assert!(dmgs.len() > 3000, "expected most swings to land (got {})", dmgs.len());

    let hi = *dmgs.iter().max().unwrap();
    let lo = *dmgs.iter().min().unwrap();
    assert_eq!(hi, 1150, "the TOP of the declared band must be reachable (saw {hi})");
    assert_eq!(lo, 850, "the bottom of the declared band must be reachable (saw {lo})");

    // COVERAGE, not mean. A sample mean cannot detect a 0.06 % bias at any
    // affordable n — the standard error here is ~1.4, so a tolerance tight
    // enough to catch the old −0.6 shortfall would be flaky, and one loose
    // enough to be stable would be vacuous. Counting DISTINCT values is
    // deterministic instead: the band declares 301 values (850..=1150), the
    // old form could only ever produce 300.
    let distinct: std::collections::BTreeSet<i64> = dmgs.iter().copied().collect();
    assert_eq!(
        distinct.len(),
        301,
        "the band must cover all 301 declared values; saw {} spanning {lo}..={hi}",
        distinct.len()
    );
}

/// **XST-D2 — the damage chain must not saturate SILENTLY.**
///
/// The chain ran in `i64` with `saturating_mul` over four per-mille factors, so
/// above a base of ~1.6 M (at a modest 5× crit) **every hit returned the same
/// clipped number** and nothing said so. The comment above the divisor
/// congratulates fixed-point for making a scale error "fail LOUDLY"; the line
/// below it made overflow fail in total silence.
///
/// Two things are asserted, and the second is the one that matters: the
/// arithmetic no longer overflows, AND when the declared ceiling binds it is
/// REPORTED. A ceiling that binds quietly is a content bug wearing the costume
/// of a balance decision.
///
/// Kill-mutation: revert `numer`/`denom` to `i64` + `saturating_mul` → the huge
/// case stops scaling with `strike_power` and `capped` is never set.
#[test]
fn an_oversized_hit_is_capped_and_says_so() {
    let mut a = atk();
    a.accuracy_pm = 10_000;
    a.crit_chance_pm = 0;
    let mut d = atk();
    d.armor = 0;
    d.dodge_pm = 0;

    // Far past the old ~1.6M i64 saturation point.
    a.strike_power = 1_000_000_000_000;
    let big: Vec<_> = (0..20)
        .map(|i| resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), i))
        .filter(|o| o.hit)
        .collect();
    assert!(!big.is_empty());
    assert!(big.iter().all(|o| o.capped), "the ceiling bound but did not report");
    assert!(
        big.iter().all(|o| o.damage == crules().max_hit),
        "a capped hit must BE the declared ceiling, not an arbitrary saturated number"
    );

    // Ordinary play is untouched: no cap, and damage still tracks strike_power.
    a.strike_power = 1000;
    let small: Vec<_> = (0..20)
        .map(|i| resolve_attack(&crules(), &a, &d, false, SEED, EntityId(1), i))
        .filter(|o| o.hit)
        .collect();
    assert!(small.iter().all(|o| !o.capped), "a normal hit must not report a cap");
    assert!(small.iter().all(|o| (850..=1150).contains(&o.damage)));
}

/// **XST-D2 (b) — the chain still SCALES where the old one had gone flat.**
///
/// This is the assertion that would have caught the original bug. Under
/// `i64` + `saturating_mul`, two very different strike powers above the
/// saturation point produced the SAME damage — the failure was invisible
/// precisely because the number looked plausible.
#[test]
fn damage_scales_across_the_old_saturation_point() {
    let mut a = atk();
    a.accuracy_pm = 10_000;
    a.crit_chance_pm = 0;
    let mut d = atk();
    d.armor = 0;
    d.dodge_pm = 0;

    let dmg_at = |sp: i64| -> i64 {
        let mut a2 = a;
        a2.strike_power = sp;
        (0..20)
            .map(|i| resolve_attack(&crules(), &a2, &d, false, SEED, EntityId(1), i))
            .find(|o| o.hit)
            .map(|o| o.damage)
            .expect("a hit")
    };

    // The saturation point depends on crit: ~1.6M at a 5x crit, but ~8.02M with
    // crit OFF, which is how this test runs. My first attempt used 2M and 8M —
    // BOTH below 8.02M, so nothing saturated and the test passed against the
    // reverted code. The BITE-PROOF caught that; the test did not.
    //
    // 20M and 80M both sit well above 8.02M, so under `i64` + `saturating_mul`
    // both clamp to `i64::MAX` and return the SAME damage.
    let (lo, hi) = (dmg_at(20_000_000), dmg_at(80_000_000));
    assert!(hi > lo, "damage went FLAT above the old saturation point: {lo} vs {hi}");
    // Both sample the same roll (the hit/miss pattern does not depend on
    // strike_power, so the same action_idx is chosen), so the scaling is EXACT
    // rather than approximate — a sharper assertion than a ratio band.
    assert_eq!(hi, lo * 4, "4x the strike power must be exactly 4x the damage");
}

// ─────────────────── adversarial rulesets (F1 /review-impl) ──────────────────

/// Every runtime floor must hold for an ARBITRARY `i64` ruleset, not just for
/// `engine_default`.
///
/// F1 made these numbers author-supplied, and the code claims each bad value
/// "degrades predictably". Three of those claims were false: the guards were
/// computed by arithmetic that itself overflowed in `i64`. That is not merely a
/// panic risk — `[profile.release-commit]` inherits `release`, so
/// `overflow-checks` is **off** in the shipped binary: tests would have panicked
/// while production WRAPPED into a silently wrong number. Same class as XST-D2,
/// one layer up, on the surface F2 is about to open to authors.
///
/// **A floor computed by arithmetic that can overflow is not a floor.**
#[test]
fn an_extreme_ruleset_degrades_predictably_instead_of_overflowing() {
    let mut r = crules();
    r.roll_band_lo_pm = i64::MIN;
    r.roll_band_hi_pm = i64::MAX;
    // Would have overflowed `hi - lo + 1` in i64.
    assert!(r.roll_band_width() >= 1, "the band width floor must hold");

    let mut inverted = crules();
    inverted.roll_band_lo_pm = 1000;
    inverted.roll_band_hi_pm = -1000;
    assert_eq!(inverted.roll_band_width(), 1, "an inverted band collapses, never panics");

    // `hit_base_pm + acc − dodge` overflowed i64 before the i128 widening.
    let mut h = crules();
    h.hit_base_pm = i64::MAX;
    assert_eq!(
        hit_chance_pm(&h, i64::MAX, i64::MIN),
        h.hit_ceiling_pm,
        "an overflowing hit chance saturates to the declared ceiling"
    );
    h.hit_base_pm = i64::MIN;
    assert_eq!(hit_chance_pm(&h, i64::MIN, i64::MAX), h.hit_floor_pm);

    // floor > ceiling: floor wins, and `i64::clamp` must not panic.
    let mut inv = crules();
    inv.hit_floor_pm = 900;
    inv.hit_ceiling_pm = 100;
    assert_eq!(hit_chance_pm(&inv, 0, 0), 900, "floor wins, deterministically");

    // `(1000 − resist_pm)` was evaluated in i64 BEFORE the i128 cast.
    let mut e = crules();
    e.resist_pm = i64::MIN;
    let a = atk();
    let out = resolve_attack(&e, &a, &a, false, SEED, EntityId(1), 0);
    assert!(out.damage >= 1, "damage floor holds even for an absurd resist");

    // `defend_divisor = 0` must not divide by zero.
    let mut d = crules();
    d.defend_divisor = 0;
    let guarded = resolve_attack(&d, &a, &a, true, SEED, EntityId(1), 0);
    assert!(guarded.damage >= 1);
}

/// The same, for the stat path: `move_base` is author-supplied and its sum with
/// the speed term overflowed `i32`.
#[test]
fn an_extreme_move_tuning_stays_inside_i32() {
    use commit_service::stats::{resolve_block, StatBlock, StatSlot};

    let mut r = srules();
    r.move_base = i32::MAX;
    r.move_max = i32::MAX;
    r.move_speed_per_tile = 1;
    let mut arch = StatBlock::from_slots(&r.melee_archetype);
    arch.set(StatSlot::Speed, i32::MAX);

    let out = resolve_block(&arch, &[], &[], &[], &r);
    assert!(out.get(StatSlot::MoveRange) >= 1, "the move floor holds");

    // And an inverted max collapses to the floor rather than panicking in clamp.
    let mut inv = srules();
    inv.move_max = 0;
    let out = resolve_block(&arch, &[], &[], &[], &inv);
    assert_eq!(out.get(StatSlot::MoveRange), 1);
}
