//! DF07 — stat resolution, asserted against its axioms.
//!
//! Each test names the axiom it pins and the failure mode that axiom exists to
//! prevent. Several of these encode corrections the spec itself records, which
//! is the strongest signal they are worth testing: someone already got them
//! backwards once.

use commit_service::stats::{
    resolve_block, Clamp, ModifierOp, ModifierSource, StatBlock, StatEpoch, StatModifier, StatSlot,
    StatRules, StatSnapshot,
};

/// F1 — `resolve_block` reads its four `MoveRange` numbers AND the ten slot
/// defaults from the ruleset instead of from `StatTuning::default()` /
/// `StatSlot::default_value()`. `engine_default` holds the same literals, so
/// every expected value in this file is unchanged.
fn rules() -> StatRules {
    StatRules::engine_default()
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
    let b = resolve_block(&StatBlock::from_defaults(&rules()), &[], &[], &[], &rules());
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
    let mut arch = StatBlock::from_defaults(&rules());
    arch.set(StatSlot::StrikePower, 100);

    let mods = [
        pct(StatSlot::StrikePower, 500, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 500, ModifierSource::Status),
    ];
    let b = resolve_block(&arch, &mods, &[], &[], &rules());

    assert_eq!(b.get(StatSlot::StrikePower), 200, "100 x (1000+500+500)/1000 = 200, not 225");
}

/// Summing also makes the outcome INDEPENDENT OF ORDER — the property that
/// makes it safe for modifiers to arrive from equipment, status and Lex in
/// whatever sequence the caller happens to build them.
#[test]
fn percent_order_does_not_matter() {
    let mut arch = StatBlock::from_defaults(&rules());
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
        resolve_block(&arch, &a, &[], &[], &rules()).get(StatSlot::StrikePower),
        resolve_block(&arch, &b, &[], &[], &rules()).get(StatSlot::StrikePower),
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
    let mut arch = StatBlock::from_defaults(&rules());
    arch.set(StatSlot::StrikePower, 100);

    let b = resolve_block(
        &arch,
        &[],
        &[Clamp { slot: StatSlot::StrikePower, min: 80, max: 500 }], // author
        &[Clamp { slot: StatSlot::StrikePower, min: 0, max: 50 }],   // world rule
        &rules(),
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
    let mut arch = StatBlock::from_defaults(&rules());
    arch.set(StatSlot::StrikePower, 100);

    let mods = [
        flat(StatSlot::StrikePower, 100, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 1000, ModifierSource::Status),
    ];
    let b = resolve_block(&arch, &mods, &[], &[], &rules());
    assert_eq!(b.get(StatSlot::StrikePower), 400, "(100+100) x 2.0 — not 100x2 + 100");
}

/// **DF7-A4 — integer determinism.** Same inputs, byte-identical block. No
/// float means no cross-target drift, which is what makes a replayed
/// encounter resolve identically on another machine.
#[test]
fn resolution_is_bit_identical_for_identical_inputs() {
    let mut arch = StatBlock::from_defaults(&rules());
    arch.set(StatSlot::StrikePower, 37);
    arch.set(StatSlot::Speed, 133);
    let mods = [
        flat(StatSlot::StrikePower, 13, ModifierSource::Equipment),
        pct(StatSlot::StrikePower, 333, ModifierSource::Status),
        pct(StatSlot::Speed, 111, ModifierSource::Progression),
    ];

    let a = resolve_block(&arch, &mods, &[], &[], &rules());
    let b = resolve_block(&arch, &mods, &[], &[], &rules());
    assert_eq!(a, b);
    // And repeated resolution never drifts — there is no accumulator to round.
    for _ in 0..100 {
        assert_eq!(resolve_block(&arch, &mods, &[], &[], &rules()), a);
    }
}

/// `MoveRange` is derived, not authored: `clamp(base + speed/per_tile, 1, max)`.
/// Default speed 100 ⇒ 3 + 2 = 5 tiles on a 16×16 grid.
#[test]
fn move_range_is_derived_from_speed_and_clamped() {
    let b = resolve_block(&StatBlock::from_defaults(&rules()), &[], &[], &[], &rules());
    assert_eq!(b.get(StatSlot::MoveRange), 5, "3 + floor(100/50)");

    let mut fast = StatBlock::from_defaults(&rules());
    fast.set(StatSlot::Speed, 10_000);
    let b = resolve_block(&fast, &[], &[], &[], &rules());
    assert_eq!(b.get(StatSlot::MoveRange), 10, "capped at max_move — not 203 tiles");

    let mut slow = StatBlock::from_defaults(&rules());
    slow.set(StatSlot::Speed, 1);
    let b = resolve_block(&slow, &[], &[], &[], &rules());
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
    let snap = StatSnapshot { stats: StatBlock::from_defaults(&rules()), epoch };

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

// ─────────────────── X1: the four silent-correctness defects ────────────────
//
// All four passed the entire pre-existing suite (76/76 green) and all four are
// deterministic, so the conformance suite stayed green and replay kept agreeing
// with itself. None was observable. That is what "silent" means here, and it is
// why each test below is written as a BITE: it must go red if the fix is
// reverted, not merely pass today.

/// **XST-D1 / DF07_002 EC-2 — a percent debuff past −100% must FLOOR, never invert.**
///
/// The spec found this on paper, fixed it, wrote the acceptance criterion, and
/// named the exact mutation that would reintroduce it — and the implementation
/// reintroduced it anyway, because it was written from the axiom list rather
/// than from the edge-case document.
///
/// Kill-mutation (AC-DF7-17, quoted): *"drop the `max(0, …)` on `factor` →
/// yields a negative stat."* With that dropped, `Σpct = −1200` gives −20 here.
#[test]
fn a_debuff_past_minus_one_hundred_percent_floors_at_zero() {
    let arch = StatBlock::from_defaults(&rules()); // StrikePower 10
    let mods = [
        pct(StatSlot::StrikePower, -600, ModifierSource::Status),
        pct(StatSlot::StrikePower, -600, ModifierSource::Status),
    ];
    let out = resolve_block(&arch, &mods, &[], &[], &rules());
    assert_eq!(
        out.get(StatSlot::StrikePower),
        0,
        "Σpct = −1200 must floor at 0; a negative StrikePower is EC-2 reintroduced"
    );

    // Paired positive case (IAS-D10): the floor must not swallow ordinary debuffs.
    let mild = [pct(StatSlot::StrikePower, -500, ModifierSource::Status)];
    let out = resolve_block(&arch, &mild, &[], &[], &rules());
    assert_eq!(out.get(StatSlot::StrikePower), 5, "a −50% debuff must still halve, not floor");
}

/// **XST-D6 / DF7-A3 — the Lex clamp is applied LAST and is therefore inescapable,
/// including on the one DERIVED slot.**
///
/// `MoveRange` is derived from Speed, so the derivation has to run after the
/// per-slot loop. It used to run after the *clamps* too, overwriting the slot
/// with its own `clamp(1, max_move)` and discarding the world rule entirely.
///
/// The existing `a_world_rule_is_never_escapable_by_an_author_clamp` test covers
/// `StrikePower` — so the invariant was tested everywhere except the one slot
/// where it was broken.
///
/// Kill-mutation: move `derive_move_range` back to the last statement of
/// `resolve_block` (dropping the re-clamp) → this yields 5 against a ceiling of 2.
#[test]
fn a_world_rule_binds_the_derived_slot_too() {
    let arch = StatBlock::from_defaults(&rules()); // Speed 100 ⇒ derived MoveRange 3 + 100/50 = 5
    let lex = [Clamp { slot: StatSlot::MoveRange, min: 1, max: 2 }];
    let out = resolve_block(&arch, &[], &[], &lex, &rules());
    assert_eq!(
        out.get(StatSlot::MoveRange),
        2,
        "the derivation must not escape the Lex ceiling — DF7-A3 says the world rule is last"
    );

    // Paired: with no world rule, the derivation is untouched.
    let out = resolve_block(&arch, &[], &[], &[], &rules());
    assert_eq!(out.get(StatSlot::MoveRange), 5, "an unclamped derivation must still derive");
}

/// **XST-D7 — every `ModifierSource` a caller can construct must be CONSUMED.**
///
/// The flat loop iterated an inline `[Progression, Equipment, Status]` literal,
/// so three of six sources were accepted and silently discarded — while the
/// percent path was not source-filtered at all. The result: a `Lex` Percent
/// applied and a `Lex` Flat vanished, so a world rule worked or did nothing
/// depending on which operator the author picked. This is the no-silent-no-op
/// class CLAUDE.md names as a shipped bug.
///
/// Kill-mutation: narrow the loop back to three sources → `Base`, `Archetype`
/// and `Lex` each yield 10 instead of 60.
#[test]
fn every_modifier_source_is_consumed() {
    let arch = StatBlock::from_defaults(&rules()); // StrikePower 10
    for source in ModifierSource::ALL {
        let mods = [flat(StatSlot::StrikePower, 50, source)];
        let out = resolve_block(&arch, &mods, &[], &[], &rules());
        assert_eq!(
            out.get(StatSlot::StrikePower),
            60,
            "Flat(+50) from {source:?} was dropped — the enum must not express what the \
             resolver ignores"
        );
    }
}

/// **XST-D7 (b) — the layer-order table cannot silently fall out of sync.**
///
/// `layer_index` is a `match` with no wildcard arm, so a seventh variant is a
/// compile error. This asserts the other half: that `ALL` lists the variants in
/// exactly the declared order, so the two cannot drift apart.
#[test]
fn the_layer_order_table_is_self_consistent() {
    assert_eq!(
        ModifierSource::ALL.len(),
        ModifierSource::COUNT,
        "ALL and COUNT disagree"
    );
    for (i, source) in ModifierSource::ALL.into_iter().enumerate() {
        assert_eq!(source.layer_index(), i, "{source:?} is out of position in ModifierSource::ALL");
    }
    // Every index in 0..COUNT is claimed exactly once. A duplicated or skipped
    // index means a layer runs twice or never — both silent.
    let mut seen = [false; ModifierSource::COUNT];
    for source in ModifierSource::ALL {
        assert!(!seen[source.layer_index()], "{source:?} duplicates a layer index");
        seen[source.layer_index()] = true;
    }
    assert!(seen.iter().all(|b| *b), "a layer index is unclaimed");
}

/// **XST-D8 — clamps COMPOSE; load order never decides the winner.**
///
/// `slot_clamps.iter().find(...)` took the first clamp for a slot and discarded
/// the rest, so two content packs both clamping `MaxHp` had their winner decided
/// by `Vec` position — order-dependence smuggled into the one mechanism DF7-A5
/// advertises as order-independent.
///
/// Kill-mutation: restore `.find()` → the reversed order below yields 200
/// instead of 120, and the two halves of this test disagree.
#[test]
fn clamps_compose_and_do_not_depend_on_declaration_order() {
    let arch = StatBlock::from_defaults(&rules());
    let mods = [flat(StatSlot::MaxHp, 400, ModifierSource::Equipment)]; // 100 + 400 = 500

    let a = [
        Clamp { slot: StatSlot::MaxHp, min: 0, max: 200 },
        Clamp { slot: StatSlot::MaxHp, min: 0, max: 120 },
    ];
    let b = [a[1], a[0]]; // same declarations, opposite order

    let out_a = resolve_block(&arch, &mods, &a, &[], &rules());
    let out_b = resolve_block(&arch, &mods, &b, &[], &rules());

    assert_eq!(out_a.get(StatSlot::MaxHp), 120, "the intersection of both clamps must bind");
    assert_eq!(
        out_a.get(StatSlot::MaxHp),
        out_b.get(StatSlot::MaxHp),
        "reversing the clamp slice changed the result — load order is deciding"
    );
}

/// **XST-D8 (b) — a contradictory intersection must not PANIC.**
///
/// `i32::clamp` panics when `min > max`, so two content packs declaring
/// `[50,100]` and `[200,300]` on the same slot would take the process down.
/// The floor wins, deterministically. (The loader should refuse this at load
/// time — F2 — but a runtime contradiction must degrade, not crash.)
#[test]
fn contradictory_clamps_degrade_rather_than_panic() {
    let arch = StatBlock::from_defaults(&rules());
    let contradictory = [
        Clamp { slot: StatSlot::MaxHp, min: 50, max: 100 },
        Clamp { slot: StatSlot::MaxHp, min: 200, max: 300 },
    ];
    let out = resolve_block(&arch, &[], &contradictory, &[], &rules());
    assert_eq!(out.get(StatSlot::MaxHp), 200, "empty intersection: the floor wins, no panic");
}
