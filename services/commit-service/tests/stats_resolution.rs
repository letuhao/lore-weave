//! DF07 — stat resolution, asserted against its axioms.
//!
//! Each test names the axiom it pins and the failure mode that axiom exists to
//! prevent. Several of these encode corrections the spec itself records, which
//! is the strongest signal they are worth testing: someone already got them
//! backwards once.

use commit_service::stats::{
    resolve_block, Clamp, ModifierOp, ModifierSource, StatBlock, StatEpoch, StatModifier, StatSlot,
    StatSnapshot, StatTuning,
};

fn tuning() -> StatTuning {
    StatTuning::default()
}

fn flat(slot: StatSlot, v: i32, source: ModifierSource) -> StatModifier {
    StatModifier { slot, op: ModifierOp::Flat(v), source }
}

fn pct(slot: StatSlot, v: i32, source: ModifierSource) -> StatModifier {
    StatModifier { slot, op: ModifierOp::Percent(v), source }
}

/// **DF7-A6 — playable with zero declaration.** A reality that declares no
/// progression kinds and no stat slots still yields a valid block.
///
/// Kill-mutation: defaulting slots to 0. Speed 0 alone would make `av =
/// 10000/speed` undefined and every unconfigured NPC unplayable.
#[test]
fn a_bare_block_is_already_playable() {
    let b = resolve_block(&StatBlock::default(), &[], &[], &[], &tuning());
    assert_eq!(b.get(StatSlot::MaxHp), 100);
    assert_eq!(b.get(StatSlot::StrikePower), 10);
    assert_eq!(b.get(StatSlot::Speed), 100);
    assert_eq!(b.get(StatSlot::CritMult), 1500, "1.5x as per-mille");
    assert!(b.get(StatSlot::Speed) >= 1, "speed is never zero — av would be undefined");
}

/// **DF7-A5 — percent modifiers SUM, never chain.**
///
/// Two +50% buffs give ×2.0, not ×2.25. Chaining multiplicatively is how buff
/// stacking goes exponential and how a stat system stops being balanceable.
/// It also makes the result depend on application ORDER, which replay cannot
/// guarantee.
#[test]
fn percent_modifiers_sum_rather_than_chain() {
    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 100);

    let mods = [
        pct(StatSlot::StrikePower, 500, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 500, ModifierSource::Status),
    ];
    let b = resolve_block(&arch, &mods, &[], &[], &tuning());

    assert_eq!(b.get(StatSlot::StrikePower), 200, "100 x (1000+500+500)/1000 = 200, not 225");
}

/// Summing also makes the outcome INDEPENDENT OF ORDER — the property that
/// makes it safe for modifiers to arrive from equipment, status and Lex in
/// whatever sequence the caller happens to build them.
#[test]
fn percent_order_does_not_matter() {
    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 100);

    let a = [
        pct(StatSlot::StrikePower, 300, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 700, ModifierSource::Status),
    ];
    let b = [
        pct(StatSlot::StrikePower, 700, ModifierSource::Status),
        pct(StatSlot::StrikePower, 300, ModifierSource::Equipment),
    ];
    assert_eq!(
        resolve_block(&arch, &a, &[], &[], &tuning()).get(StatSlot::StrikePower),
        resolve_block(&arch, &b, &[], &[], &tuning()).get(StatSlot::StrikePower),
    );
}

/// **DF7-A3 — the LEX CLAMP RUNS LAST, and this is a recorded correction.**
///
/// The first DRAFT ran `Lex → slot clamp`, reasoning that "an author clamp
/// cannot escape a world rule". That is backwards: whichever clamp runs last
/// wins, so a slot clamp whose `min` exceeds the Lex ceiling would raise the
/// value *back through* it (DF07_002 EC-1).
///
/// This test is the shape of that bug: a Lex ceiling of 50 with an author
/// floor of 80. Correct order ⇒ 50. Reversed ⇒ 80, and the world rule is
/// silently escapable by any author who sets a high enough minimum.
#[test]
fn a_world_rule_is_never_escapable_by_an_author_clamp() {
    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 100);

    let b = resolve_block(
        &arch,
        &[],
        &[Clamp { slot: StatSlot::StrikePower, min: 80, max: 500 }], // author
        &[Clamp { slot: StatSlot::StrikePower, min: 0, max: 50 }],   // world rule
        &tuning(),
    );

    assert_eq!(
        b.get(StatSlot::StrikePower),
        50,
        "the Lex ceiling holds; reversing the clamp order would yield 80"
    );
}

/// Flat layers apply before percent, so a percent buff scales the equipped
/// total rather than the naked base. Kill-mutation: applying percent first
/// makes equipment feel worthless on a buffed character.
#[test]
fn flat_layers_land_before_percent() {
    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 100);

    let mods = [
        flat(StatSlot::StrikePower, 100, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 1000, ModifierSource::Status),
    ];
    let b = resolve_block(&arch, &mods, &[], &[], &tuning());
    assert_eq!(b.get(StatSlot::StrikePower), 400, "(100+100) x 2.0 — not 100x2 + 100");
}

/// **DF7-A4 — integer determinism.** Same inputs, byte-identical block. No
/// float means no cross-target drift, which is what makes a replayed
/// encounter resolve identically on another machine.
#[test]
fn resolution_is_bit_identical_for_identical_inputs() {
    let mut arch = StatBlock::default();
    arch.set(StatSlot::StrikePower, 37);
    arch.set(StatSlot::Speed, 133);
    let mods = [
        flat(StatSlot::StrikePower, 13, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 333, ModifierSource::Status),
        pct(StatSlot::Speed, 111, ModifierSource::Progression),
    ];

    let a = resolve_block(&arch, &mods, &[], &[], &tuning());
    let b = resolve_block(&arch, &mods, &[], &[], &tuning());
    assert_eq!(a, b);
    // And repeated resolution never drifts — there is no accumulator to round.
    for _ in 0..100 {
        assert_eq!(resolve_block(&arch, &mods, &[], &[], &tuning()), a);
    }
}

/// `MoveRange` is derived, not authored: `clamp(base + speed/per_tile, 1, max)`.
/// Default speed 100 ⇒ 3 + 2 = 5 tiles on a 16×16 grid.
#[test]
fn move_range_is_derived_from_speed_and_clamped() {
    let b = resolve_block(&StatBlock::default(), &[], &[], &[], &tuning());
    assert_eq!(b.get(StatSlot::MoveRange), 5, "3 + floor(100/50)");

    let mut fast = StatBlock::default();
    fast.set(StatSlot::Speed, 10_000);
    let b = resolve_block(&fast, &[], &[], &[], &tuning());
    assert_eq!(b.get(StatSlot::MoveRange), 10, "capped at max_move — not 203 tiles");

    let mut slow = StatBlock::default();
    slow.set(StatSlot::Speed, 1);
    let b = resolve_block(&slow, &[], &[], &[], &tuning());
    assert!(b.get(StatSlot::MoveRange) >= 1, "never zero — an actor that cannot move at all");
}

/// **DF07 §8.2 — the epoch makes staleness DETECTABLE.**
///
/// Its whole purpose is that a snapshot is re-resolved rather than repaired
/// (DF7-A2). A snapshot that could not tell it was stale would silently keep
/// serving pre-equipment numbers for the rest of an encounter.
#[test]
fn a_snapshot_knows_when_its_inputs_moved() {
    let epoch = StatEpoch { equipment_version: 7, ..Default::default() };
    let snap = StatSnapshot { stats: StatBlock::default(), epoch };

    assert!(!snap.is_stale(&epoch), "unchanged inputs ⇒ still valid");
    assert!(
        snap.is_stale(&StatEpoch { equipment_version: 8, ..epoch }),
        "an equipment change invalidates the snapshot"
    );
    assert!(
        snap.is_stale(&StatEpoch { progression_turn: 1, ..epoch }),
        "so does a progression tick — striking trains swordsmanship mid-fight"
    );
}
