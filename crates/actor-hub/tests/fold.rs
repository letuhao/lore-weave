//! The fold's behaviour, asserted from OUTSIDE the crate.
//!
//! These moved out of `src/fold.rs` when it passed `IMP-D3`'s 400-line ceiling,
//! and the move made them stronger rather than merely shorter: an integration
//! test can reach only the **public** surface, so nothing here can assert a
//! property through a `pub(crate)` back door that a plugin author would not have.

use actor_hub::*;
use ruleset_core::{ModifierOp, OpKind, QuantityTable};


fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).unwrap()
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).unwrap()
}

/// A two-plugin reality. `hp`/`speed`/`move_range` belong to plugin 0,
/// `qi` to plugin 1. The names are the author's; the hub never reads them.
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

fn m(target: u16, op: ModifierOp, layer: u8) -> ModifierRow {
    ModifierRow { target: q(target), op, source: p(0), fold_layer: FoldLayer(layer) }
}

#[test]
fn a_quantity_with_no_contributions_resolves_to_its_base() {
    let (r, a, s) = fixture();
    let out = fold(a, &s, &r, &[], &[]);
    assert_eq!(out.value(q(0)), Some(100));
    assert!(out.refused.is_empty());
    assert!(out.capped.is_empty());
}

/// **An unattached plugin's quantity is ABSENT, not zero** — so it does not
/// appear in the fold at all, and `value` is `None` rather than `Some(0)`.
#[test]
fn an_absent_quantity_is_none_not_zero() {
    let (r, _, s) = fixture();
    let combat_only = PluginSet::EMPTY.attach(p(0));
    let out = fold(combat_only, &s, &r, &[], &[]);
    assert_eq!(out.value(q(0)), Some(100));
    assert_eq!(out.value(q(1)), None);
    assert!(out.explain(q(1)).is_none());
}

#[test]
fn flat_and_percent_combine_by_the_formula() {
    let (r, a, s) = fixture();
    // (100 + 50) × (1000 + 200)/1000 = 180
    let out = fold(
        a,
        &s,
        &r,
        &[m(0, ModifierOp::Flat(50), 10), m(0, ModifierOp::Percent(200), 20)],
        &[],
    );
    assert_eq!(out.value(q(0)), Some(180));
    let e = out.explain(q(0)).unwrap();
    assert_eq!((e.base, e.flat_sum, e.percent_sum, e.factor_milli), (100, 50, 200, 1200));
}

/// **The `max(0, …)` floor, which was once absent.** Two −60 % debuffs are
/// ordinary play in a debuff-dense reality, and without the floor they give
/// a factor of −0.2 and a NEGATIVE quantity.
#[test]
fn two_heavy_debuffs_floor_at_zero_and_never_go_negative() {
    let (r, a, s) = fixture();
    let out = fold(
        a,
        &s,
        &r,
        &[m(0, ModifierOp::Percent(-600), 10), m(0, ModifierOp::Percent(-600), 10)],
        &[],
    );
    assert_eq!(out.explain(q(0)).unwrap().percent_sum, -1200);
    assert_eq!(out.explain(q(0)).unwrap().factor_milli, 0);
    assert_eq!(out.value(q(0)), Some(0), "the floor is what stops this being -20");
}

/// **Percent is SUMMED, not chained** — so the result cannot depend on the
/// order the rows arrived in.
#[test]
fn the_result_is_independent_of_row_order() {
    let (r, a, s) = fixture();
    let rows = [
        m(0, ModifierOp::Flat(50), 10),
        m(0, ModifierOp::Percent(200), 20),
        m(0, ModifierOp::Percent(-50), 10),
        m(0, ModifierOp::Flat(-10), 20),
    ];
    let forward = fold(a, &s, &r, &rows, &[]);
    let mut reversed = rows;
    reversed.reverse();
    let backward = fold(a, &s, &r, &reversed, &[]);
    assert_eq!(forward.value(q(0)), backward.value(q(0)));
    // And the EXPLANATION is stable too, up to the submission index, so two
    // runs are comparable.
    let f: Vec<_> = forward.explain(q(0)).unwrap().contributions.iter().map(|c| c.op).collect();
    let b: Vec<_> = backward.explain(q(0)).unwrap().contributions.iter().map(|c| c.op).collect();
    assert_eq!(f.len(), b.len());
    let mut fs = f.clone();
    let mut bs = b.clone();
    fs.sort_by_key(|o| (o.kind(), o.value()));
    bs.sort_by_key(|o| (o.kind(), o.value()));
    assert_eq!(fs, bs);
}

/// Contributions are ordered by `(fold_layer, plugin, index)` — `M-13`.
#[test]
fn contributions_are_ordered_by_layer_then_plugin_then_index() {
    let (r, a, s) = fixture();
    let mut late = m(0, ModifierOp::Flat(1), 20);
    late.source = p(0);
    let early = m(0, ModifierOp::Flat(2), 10);
    let out = fold(a, &s, &r, &[late, early], &[]);
    let layers: Vec<u8> = out
        .explain(q(0))
        .unwrap()
        .contributions
        .iter()
        .map(|c| c.fold_layer.get())
        .collect();
    assert_eq!(layers, vec![10, 20]);
}

/// **A `DerivationRow` CONTRIBUTES; it never SETS.** The shipped
/// `derive_move_range` overwrites a value six layers just resolved, so an
/// Equipment `Flat(+2)` on `MoveRange` is accepted and silently discarded.
/// Here the flat survives the derivation.
#[test]
fn a_derivation_contributes_and_does_not_discard_a_modifier() {
    let (r, a, s) = fixture();
    // move_range: base 1, +2 from a modifier, + speed(10_000)/3 derived.
    let deriv = DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor: 3,
        bound: None,
        source: p(0),
        fold_layer: FoldLayer(20),
    };
    let out = fold(a, &s, &r, &[m(3, ModifierOp::Flat(2), 10)], &[deriv]);
    assert_eq!(
        out.value(q(3)),
        Some(1 + 2 + 3_333),
        "SET would have discarded the +2; CONTRIBUTE keeps it"
    );
    let e = out.explain(q(3)).unwrap();
    assert_eq!(e.contributions.len(), 2);
    assert_eq!(e.contributions[1].derived_from, Some((q(2), 10_000)));
}

#[test]
fn a_derivation_bound_limits_only_its_own_contribution() {
    let (r, a, s) = fixture();
    let deriv = DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor: 3,
        bound: Some(ContributionBound { min: 1, max: 5 }),
        source: p(0),
        fold_layer: FoldLayer(20),
    };
    let out = fold(a, &s, &r, &[m(3, ModifierOp::Flat(2), 10)], &[deriv]);
    assert_eq!(out.value(q(3)), Some(1 + 2 + 5));
}

/// **Nothing silent (substrate §7).** A malformed row is REFUSED with its
/// reason and the fold continues — it does not take the encounter down.
#[test]
fn a_malformed_row_is_refused_and_the_fold_continues() {
    let (r, a, s) = fixture();
    let out = fold(
        a,
        &s,
        &r,
        &[
            m(0, ModifierOp::Flat(7), 99), // undeclared fold layer
            m(0, ModifierOp::Flat(3), 10), // fine
        ],
        &[],
    );
    assert_eq!(out.value(q(0)), Some(103));
    assert_eq!(
        out.refused,
        vec![Refused {
            row: RowRef::Modifier(0),
            reason: RowRefusal::UndeclaredFoldLayer { layer: 99 },
        }]
    );
    assert_eq!(out.explain(q(0)).unwrap().contributions.len(), 1);
}

/// The other half of §7: a value the representation cannot hold is CAPPED,
/// with a record of what it wanted.
#[test]
fn a_saturated_value_is_capped_with_a_record() {
    let (r, a, mut s) = fixture();
    s[q(0).index()] = i32::MAX;
    let out = fold(a, &s, &r, &[m(0, ModifierOp::Percent(1000), 10)], &[]);
    assert_eq!(out.value(q(0)), Some(i32::MAX));
    assert_eq!(out.capped.len(), 1);
    assert_eq!(out.capped[0].quantity, q(0));
    assert!(out.capped[0].wanted > i32::MAX as i64);
}

/// **`M-10` — *"why is this number 47"*.** Every term of the formula, and
/// every contribution with the plugin that submitted it.
#[test]
fn the_explain_path_reconstructs_the_number() {
    let (r, a, s) = fixture();
    let out = fold(
        a,
        &s,
        &r,
        &[m(0, ModifierOp::Flat(50), 10), m(0, ModifierOp::Percent(-500), 20)],
        &[],
    );
    let e = out.explain(q(0)).unwrap();
    // The reader can recompute the answer from the explanation alone.
    let recomputed = (e.base as i64 + e.flat_sum) * e.factor_milli / 1000;
    assert_eq!(recomputed, e.pre_emit);
    assert_eq!(e.value, 75);
    assert_eq!(e.contributions.len(), 2);
    assert_eq!(e.contributions[0].source, p(0));
}

/// Totality (`M-6`): the fold must not panic on any input, including the
/// arithmetic extremes that make a naive `i64` multiply overflow.
#[test]
fn the_fold_is_total_at_the_arithmetic_extremes() {
    let (r, a, mut s) = fixture();
    for base in [i32::MIN, -1, 0, 1, i32::MAX] {
        s[q(0).index()] = base;
        for v in [i32::MIN, -1, 0, 1, i32::MAX] {
            let out = fold(
                a,
                &s,
                &r,
                &[m(0, ModifierOp::Flat(v), 10), m(0, ModifierOp::Percent(v), 20)],
                &[],
            );
            // A value always comes out; the point is that nothing panicked.
            assert!(out.value(q(0)).is_some());
        }
    }
}

/// Determinism: the same inputs give a byte-identical report.
#[test]
fn the_fold_is_deterministic() {
    let (r, a, s) = fixture();
    let rows = [m(0, ModifierOp::Flat(5), 10), m(2, ModifierOp::Percent(120), 20)];
    let first = fold(a, &s, &r, &rows, &[]);
    let second = fold(a, &s, &r, &rows, &[]);
    assert_eq!(first, second);
}
