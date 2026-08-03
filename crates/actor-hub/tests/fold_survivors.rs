//! The mutations a round-10 cold-start review left ALIVE — 113 mutations, nine
//! actionable survivors, each proven non-equivalent by a probe that passes on
//! clean code and reds on its mutant.
//!
//! Every test here exists because deleting or weakening the thing it names left
//! the whole suite green. The shape repeats and is worth stating once: **the
//! existing tests asserted the interesting half of a rule and left the boring
//! half — the other row kind, the other sign, the boundary itself, the exact
//! value rather than its direction — to be inferred.** A mutation lives in the
//! inferred half.
//!
//! Integration test, so it reaches only the PUBLIC surface — the same surface a
//! plugin crate written next year would have.

use actor_hub::*;
use ruleset_core::{ModifierOp, OpKind, QuantityTable};

fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).unwrap()
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).unwrap()
}

/// Two plugins. Plugin 0 owns `hp`/`speed`/`move_range` and declares fold layers
/// 10 and 20; plugin 1 owns `qi` and declares layer 30.
fn fixture() -> (HubRegistry, PluginSet, [i32; MAX_DECLARED_QUANTITIES]) {
    let table = QuantityTable::assign(&["hp", "qi", "speed", "move_range"]).unwrap();
    let decls = vec![
        PluginDecl {
            ordinal: p(0),
            quantities: vec![
                QuantityDecl { ordinal: q(0), initial: 100 },
                QuantityDecl { ordinal: q(2), initial: 10_000 },
                QuantityDecl { ordinal: q(3), initial: 1 },
            ],
            fold_layers: vec![FoldLayer(10), FoldLayer(20)],
        },
        PluginDecl {
            ordinal: p(1),
            quantities: vec![QuantityDecl { ordinal: q(1), initial: 0 }],
            fold_layers: vec![FoldLayer(30)],
        },
    ];
    let registry = HubRegistry::build(&table, &decls).unwrap();
    let attached = PluginSet::EMPTY.attach(p(0)).attach(p(1));
    let mut stored = [0i32; MAX_DECLARED_QUANTITIES];
    for raw in 0..4u16 {
        if let Some(v) = registry.initial_value(attached, q(raw)) {
            stored[q(raw).index()] = v;
        }
    }
    (registry, attached, stored)
}

fn deriv(target: u16, source_quantity: u16, layer: u8) -> DerivationRow {
    DerivationRow {
        target: q(target),
        source_quantity: q(source_quantity),
        op: OpKind::Flat,
        factor_milli: 1_000,
        divisor: 1,
        bound: None,
        source: p(0),
        fold_layer: FoldLayer(layer),
    }
}

/// **A refused DERIVATION is recorded, not merely dropped.**
///
/// Deleting the `refused.push(… RowRef::Derivation(i) …)` arm was green: every
/// fold-level refusal assertion in the suite used `RowRef::Modifier`, so the
/// derivation half of a two-arm rule was asserted by nobody. A derivation that
/// vanishes without an event is exactly what substrate §7 forbids.
#[test]
fn a_refused_derivation_is_recorded_with_its_row_index() {
    let (r, _, s) = fixture();
    // Plugin 1 DETACHED, so `qi` is not present. (Ownership is deliberately not
    // enforced on writes -- any attached plugin may target any present quantity
    // -- so an "unowned target" refuses nothing. Presence is the rule.)
    let a = PluginSet::EMPTY.attach(p(0));
    let good = deriv(3, 2, 20);
    let bad = deriv(1, 2, 20);

    let out = fold(a, &s, &r, &[], &[good, bad]);

    assert_eq!(out.refused.len(), 1, "the refused derivation produced no event");
    assert_eq!(
        out.refused[0].row,
        RowRef::Derivation(1),
        "a refusal must name WHICH row, and it must be the derivation index"
    );
}

/// **Refusals are ordered: modifiers first, then derivations, each in
/// submission order.** The fold's own comment states it; nothing asserted it, so
/// reordering the two loops was green.
#[test]
fn refusals_are_modifiers_then_derivations_each_in_submission_order() {
    let (r, _, s) = fixture();
    // Plugin 1 detached, so every row targeting `qi` is refused. Interleaved
    // with accepted rows so the refused indices are not 0,1.
    let a = PluginSet::EMPTY.attach(p(0));
    let ok_mod = ModifierRow {
        target: q(0),
        op: ModifierOp::Flat(1),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let bad_mod = ModifierRow { target: q(1), ..ok_mod };
    let bad_deriv = deriv(1, 2, 20);

    let out = fold(
        a,
        &s,
        &r,
        &[ok_mod, bad_mod, bad_mod],
        &[deriv(3, 2, 20), bad_deriv, bad_deriv],
    );

    let rows: Vec<RowRef> = out.refused.iter().map(|x| x.row).collect();
    assert_eq!(
        rows,
        vec![
            RowRef::Modifier(1),
            RowRef::Modifier(2),
            RowRef::Derivation(1),
            RowRef::Derivation(2),
        ],
        "refusal order is part of the report's determinism, not an accident of loop order"
    );
}

/// **`check_derivation` really does check the fold layer.**
///
/// Turning its `self.check_layer(row.fold_layer)?` into `let _ = …` was green,
/// while the identical deletion on the MODIFIER path went red — the same rule,
/// tested on one of its two paths.
#[test]
fn a_derivation_on_an_undeclared_fold_layer_is_refused() {
    let (r, a, s) = fixture();
    // Layer 99 is declared by nobody.
    let out = fold(a, &s, &r, &[], &[deriv(3, 2, 99)]);

    assert_eq!(out.refused.len(), 1, "an undeclared fold layer was accepted");
    assert_eq!(out.refused[0].row, RowRef::Derivation(0));
    assert!(
        matches!(out.refused[0].reason, RowRefusal::UndeclaredFoldLayer { .. }),
        "expected UndeclaredFoldLayer, got {:?}",
        out.refused[0].reason
    );
    assert_eq!(out.value(q(3)), Some(1), "a refused row must contribute nothing");
}

/// **A zero divisor and a contradictory bound are refused on the derivation
/// path**, both of which sit beside the layer check that had no case.
#[test]
fn a_zero_divisor_and_a_contradictory_bound_are_refused() {
    let (r, a, s) = fixture();
    let zero = DerivationRow { divisor: 0, ..deriv(3, 2, 20) };
    let contradictory = DerivationRow {
        bound: Some(ContributionBound { min: 10, max: 5 }),
        ..deriv(3, 2, 20)
    };

    let out = fold(a, &s, &r, &[], &[zero, contradictory]);

    assert_eq!(out.refused.len(), 2);
    assert!(matches!(out.refused[0].reason, RowRefusal::ZeroDivisor));
    assert!(matches!(
        out.refused[1].reason,
        RowRefusal::ContradictoryBound { min: 10, max: 5 }
    ));
    assert_eq!(out.value(q(3)), Some(1), "neither refused row may contribute");
}

/// **`Accumulator.wanted` carries the EXACT pre-clamp total, not its sign.**
///
/// The only assertions on this field were `< 0` and `> 0`, so replacing it with
/// the emitted value was green — and this is the field whose module doc records
/// a review finding it understating the truth by a factor of ~6 000.
#[test]
fn the_accumulator_record_carries_the_exact_wanted_total() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    // `Percent` is PER-MILLE: the factor is `max(0, 1000 + Sum pct)/1000`, so
    // `Percent(1000)` doubles. The i64 accumulator holds 2 × i32::MAX and the
    // emit clamps to i32::MAX; `wanted` must be the former.
    let boost = ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(1_000),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let out = fold(a, &s, &r, &[boost], &[]);

    let want = (i32::MAX as i64) * 2;
    assert_eq!(out.value(q(0)), Some(i32::MAX));
    let cap = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::Emit)
        .expect("an emit that clamped produced no record");
    assert_eq!(
        cap.wanted, want,
        "`wanted` must be the value the fold actually computed, not the one it emitted"
    );
    assert_eq!(cap.emitted, i32::MAX);
}

/// **`pre_emit` is the value BEFORE the emit clamp**, which is the only thing
/// that distinguishes it from `value`. Every existing case had the two equal, so
/// assigning `value` to it was green.
#[test]
fn pre_emit_differs_from_value_when_the_emit_clamps() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    let boost = ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(1_000),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let out = fold(a, &s, &r, &[boost], &[]);

    let ex = out.explain(q(0)).expect("no explanation for a folded quantity");
    assert_eq!(ex.value, i32::MAX, "the emitted value is clamped");
    assert_eq!(
        ex.pre_emit,
        (i32::MAX as i64) * 2,
        "`pre_emit` must show what the clamp removed; equal to `value` it explains nothing"
    );
}

/// **A bound whose FLOOR bites is a `DerivedBound` cap.**
///
/// The only bound case in the suite had the ceiling bite, so a mutation that
/// reported nothing when the floor raised a value was green. Both directions of
/// `clamp` are the author's declaration working, and substrate §7 wants an event
/// for either.
#[test]
fn a_bound_whose_floor_bites_is_reported() {
    let (r, a, mut s) = fixture();
    s[2] = -5_000;
    let floored = DerivationRow {
        bound: Some(ContributionBound { min: 0, max: 100 }),
        ..deriv(3, 2, 20)
    };
    let out = fold(a, &s, &r, &[], &[floored]);

    assert_eq!(out.value(q(3)), Some(1), "the floor must have raised -5 000 to 0");
    let cap = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::DerivedBound)
        .expect("the floor bit and said nothing");
    // The factor is applied BEFORE the divisor, so the raw amount is
    // -5 000 × 1 000 / 1. `wanted` is that -- the value the row asked for --
    // and `emitted` is what the floor allowed.
    assert_eq!(cap.wanted, -5_000_000);
    assert_eq!(cap.emitted, 0);
}

/// **A derivation's division truncates toward zero, on NEGATIVE input too.**
///
/// Every divisor case used positive values, where truncate-toward-zero and
/// floor agree. They disagree on negatives, so the rounding rule was unpinned in
/// the only place it is observable.
#[test]
fn a_negative_derivation_truncates_toward_zero() {
    let (r, a, mut s) = fixture();
    s[2] = -10;
    let third = DerivationRow { divisor: 3, ..deriv(3, 2, 20) };
    let out = fold(a, &s, &r, &[], &[third]);

    // raw = -10 × 1 000 / 3 = -3 333.33: **-3 333 truncating toward zero,
    // -3 334 flooring.** Positive inputs cannot tell the two apart, which is why
    // every existing divisor case left the rule unpinned.
    assert_eq!(
        out.value(q(3)),
        Some(1 - 3_333),
        "-10000/3 must truncate toward zero (-3 333), not floor (-3 334)"
    );
}

/// **An ordinal EQUAL to the declared table length is past the end.**
///
/// The only case used ordinal 9 against a 4-entry table — five past the
/// boundary — so weakening `>=` to `>` was green and a 4-entry table accepted
/// ordinal 4. Off-by-one lives at the boundary, and only a test at the boundary
/// can see it.
#[test]
fn an_ordinal_exactly_at_the_table_length_is_refused() {
    let table = QuantityTable::assign(&["hp", "qi", "speed", "move_range"]).unwrap();
    let decls = vec![PluginDecl {
        ordinal: p(0),
        quantities: vec![QuantityDecl { ordinal: q(4), initial: 1 }],
        fold_layers: vec![FoldLayer(10)],
    }];

    let err = HubRegistry::build(&table, &decls).expect_err("ordinal 4 in a 4-entry table was accepted");
    assert!(
        matches!(err, RegistryError::OrdinalPastDeclaredTable { ordinal: 4, declared: 4 }),
        "expected OrdinalPastDeclaredTable{{4, 4}}, got {err:?}"
    );

    // ...and the last VALID ordinal still builds, so the fix is a boundary and
    // not a blanket refusal.
    let ok = vec![PluginDecl {
        ordinal: p(0),
        quantities: vec![QuantityDecl { ordinal: q(3), initial: 1 }],
        fold_layers: vec![FoldLayer(10)],
    }];
    assert!(HubRegistry::build(&table, &ok).is_ok(), "ordinal 3 is the last valid one");
}
