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

// `#[path]` because this file IS the crate root, so a bare `mod registry;`
// resolves to the SIBLING `tests/registry.rs` -- an auto-discovered test target
// of its own, which it then compiles a second time into this binary. Measured:
// 22 tests where 13 were expected, and the five moved here never ran.
#[path = "fold_survivors/registry.rs"]
mod registry;

#[path = "fold_survivors/capping.rs"]
mod capping;

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

/// **`order_key`'s middle component is the SUBMITTING PLUGIN.**
///
/// `M-13` states the intra-layer order as (fold layer, submitting plugin,
/// submission index). Layer and index each had a case; the plugin did not, so
/// replacing `c.source.get()` with a constant survived the whole suite. One
/// plugin cannot show an ordering key that sorts by plugin — the fixture has to
/// submit from two, with submission order inverted against plugin order.
#[test]
fn contributions_at_one_layer_are_ordered_by_submitting_plugin() {
    let (r, a, s) = fixture();
    // Both plugins write `hp` on layer 10, and plugin 1 submits FIRST — so
    // submission order and plugin order disagree, which is the only arrangement
    // that can tell the two keys apart.
    let from_one = ModifierRow {
        target: q(0),
        op: ModifierOp::Flat(7),
        source: p(1),
        fold_layer: FoldLayer(10),
    };
    let from_zero = ModifierRow { op: ModifierOp::Flat(3), source: p(0), ..from_one };

    let out = fold(a, &s, &r, &[from_one, from_zero], &[]);

    let ex = out.explain(q(0)).expect("no explanation for a folded quantity");
    let order: Vec<u8> = ex.contributions.iter().map(|c| c.source.get()).collect();
    assert_eq!(
        order,
        vec![0, 1],
        "at one fold layer the SUBMITTING PLUGIN orders the contributions,          ahead of submission index — plugin 1 submitted first and must sort second"
    );
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

/// **Two derivations at one (layer, plugin) keep SUBMISSION order.**
///
/// `order_key`'s third component is `usize::MAX / 2 + i` for a derivation. The
/// layer half of that key is cased and the plugin half is cased; the INDEX half
/// is not, so flipping `+ i` to `- i` reverses two derivations that share a
/// layer and a plugin and every one of the 294 tests stayed green.
/// `Explanation.contributions` is public output, so the order is a promise.
///
/// Round 10 fixed one component of a three-part key and left its sibling — the
/// same shape as the round that found this one.
#[test]
fn two_derivations_from_one_plugin_at_one_layer_keep_submission_order() {
    let (r, a, s) = fixture();
    // Both target `move_range` (initial 1), both read `speed` (10 000), same
    // layer, same plugin — so ONLY the submission index can separate them.
    let mut first = deriv(3, 2, 20);
    first.factor_milli = 1_000;
    let mut second = deriv(3, 2, 20);
    second.factor_milli = 2_000;

    let out = fold(a, &s, &r, &[], &[first, second]);
    let ex = out.explain(q(3)).expect("move_range must be present");
    let order: Vec<RowRef> = ex.contributions.iter().map(|c| c.row).collect();

    assert_eq!(
        order,
        vec![RowRef::Derivation(0), RowRef::Derivation(1)],
        "two derivations at one (layer, plugin) must stay in submission order"
    );
}

/// **The division TRUNCATES on positive input too — not half-up, not half-even.**
///
/// The negative direction is pinned (`a_negative_derivation_truncates_toward_zero`
/// separates truncation from flooring) and the ceiling direction is caught by an
/// existing case. **Half-rounding is neither**, and both data points the divisor
/// case uses — `10 000 × 1/3 = 3 333.33` and `10 000 × 333/1000 = 3 330` — are
/// invariant under it: one rounds down either way, the other is exact.
///
/// So `(n + d/2) / d` survived all 296 tests. One of three rounding modes was
/// pinned, and the test asserting the divisor's whole reason for existing was
/// the one that could not see it.
#[test]
fn a_positive_derivation_truncates_rather_than_rounding_half_up() {
    let (r, a, s) = fixture();
    // 10 000 × 2/3 = 6 666.67: **6 666 truncating, 6 667 rounding half-up.**
    // `move_range` starts at 1, so the emitted value is 1 + the contribution.
    let mut row = deriv(3, 2, 20);
    row.factor_milli = 2;
    row.divisor = 3;

    let out = fold(a, &s, &r, &[], &[row]);

    assert_eq!(
        out.value(q(3)),
        Some(1 + 6_666),
        "10000×2/3 must truncate to 6 666, not round to 6 667"
    );
}

