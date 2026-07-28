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
use sim_core::EntityId;

const SEED: u64 = 0xC0FFEE;

fn atk() -> CombatStats {
    CombatStats::archetype_melee(100)
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
    assert_eq!(hit_chance_pm(0, 0), 500, "the 0.5 base, in per-mille");
    assert_eq!(hit_chance_pm(10_000, 0), 950, "no build is unmissable");
    assert_eq!(hit_chance_pm(0, 10_000), 50, "no target is untouchable");
    // Monotonic in between: more accuracy is never worse.
    assert!(hit_chance_pm(300, 100) > hit_chance_pm(200, 100));
    assert!(hit_chance_pm(200, 200) < hit_chance_pm(200, 100));
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
        .map(|i| resolve_attack(&a, &tank, false, SEED, EntityId(1), i))
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
        .map(|i| resolve_attack(&a, &d, false, SEED, EntityId(1), i))
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
        let open = resolve_attack(&a, &d, false, SEED, EntityId(1), i);
        let guarded = resolve_attack(&a, &d, true, SEED, EntityId(1), i);
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
    let base = action_value(100, AvStatus::default(), false);
    assert_eq!(base, 100, "10000/100");

    assert!(action_value(200, AvStatus::default(), false) < base, "faster acts sooner");
    assert_eq!(action_value(100, AvStatus { slowed: true, ..Default::default() }, false), 120);
    assert_eq!(action_value(100, AvStatus { hasted: true, ..Default::default() }, false), 80);
    assert_eq!(action_value(100, AvStatus { stunned: true, ..Default::default() }, false), 200);
    assert_eq!(action_value(100, AvStatus::default(), true), 75, "initiator head start");
}

/// Speed 0 must not divide by zero. A stat debuff that over-subtracts would
/// otherwise panic inside `apply` — contained by the kernel as a poison pill,
/// but the encounter is dead either way.
#[test]
fn zero_speed_does_not_divide_by_zero() {
    assert!(action_value(0, AvStatus::default(), false) > 0);
    assert!(action_value(-5, AvStatus::default(), false) > 0);
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
        .filter(|i| resolve_attack(&a, &d, false, SEED, EntityId(1), *i).hit)
        .count();

    let expected = hit_chance_pm(a.accuracy_pm, d.dodge_pm); // 850
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
    use commit_service::stats::{resolve_block, StatBlock, StatSlot, StatTuning};

    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 33);
    arch.set(StatSlot::Armor, 7);
    arch.set(StatSlot::Accuracy, 321);
    arch.set(StatSlot::Speed, 250);
    let block = resolve_block(&arch, &[], &[], &[], &StatTuning::default());
    let view = CombatStats::from_block(&block);

    assert_eq!(view.strike_power, 33);
    assert_eq!(view.armor, 7);
    assert_eq!(view.accuracy_pm, 321, "per-mille stays per-mille");
    assert_eq!(view.speed, 250);
    assert_eq!(view.crit_mult_pm, 1500, "engine default 1.5x survives (DF7-A6)");
}
