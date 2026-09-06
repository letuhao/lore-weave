//! The `CAPPED` records — what each site MEANS, and where two of them must agree.
//!
//! Substrate §7's second verb: *a value bound by a clamp is **CAPPED**, with an
//! event.* The subtlety these two tests exist for is that `Capped::emitted`
//! answers a **different question** at a row-level site than at a quantity-level
//! one, and an assertion written without that distinction reddens on correct
//! behaviour the moment a fixture gains a derivation.
//!
//! **New file, not a split.** An earlier header claimed both *"split out of
//! `fold_edges.rs`"* and *"moved out of `src/fold.rs`"* — two provenances, both
//! false, copy-pasted from the file these tests were written beside. `fold.rs`
//! was untouched and `fold_edges.rs` GREW in the same commit. A review caught
//! it, and the lesson is the one this round keeps relearning: **prose copied
//! with code describes the place it came from, not the place it landed.**

use actor_hub::*;
use ruleset_core::{ModifierOp, OpKind, QuantityTable};

fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).unwrap()
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).unwrap()
}

/// A two-plugin reality: `hp`/`speed`/`move_range` belong to plugin 0, `qi` to
/// plugin 1. The names are the author's; the hub never reads them.
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

/// **The two ROW-level cap sites answer a different question, and that is
/// pinned rather than assumed.**
///
/// A review constructed one fold in which the same quantity carries
/// `Accumulator{emitted: i32::MAX}` and `DerivedBound{emitted: 5}` — both
/// correct, because the first is the quantity's value and the second is the
/// row's contributed amount. The earlier unscoped agreement assertion would have
/// reddened on that correct behaviour the moment any fixture gained a
/// derivation.
#[test]
fn derivation_cap_records_report_the_rows_amount_not_the_quantitys() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    s[2] = i32::MAX;
    let deriv = DerivationRow {
        target: q(0),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1_000_000,
        divisor: 1,
        bound: Some(ContributionBound { min: 0, max: 5 }),
        source: p(0),
        fold_layer: FoldLayer(20),
    };
    let rows = [
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Percent(i32::MAX), 20),
    ];
    let out = fold(a, &s, &r, &rows, &[deriv]);
    let value = out.value(q(0)).unwrap();

    let bound = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::DerivedBound)
        .expect("the declared bound bit and said nothing");
    assert_eq!(bound.quantity, q(0));
    assert_eq!(bound.emitted, 5, "a row-level site reports the ROW's amount");
    assert_ne!(
        bound.emitted, value,
        "if these are ever equal this test has stopped distinguishing the two meanings"
    );

    for c in out
        .capped
        .iter()
        .filter(|c| c.quantity == q(0))
        .filter(|c| matches!(c.site, CapSite::Accumulator | CapSite::Emit))
    {
        assert_eq!(c.emitted, value, "quantity-level records still agree");
    }
}

/// `F9` — a contradictory bound is refused at submission, and if one reaches the
/// arithmetic anyway (both fields are `pub`) the FLOOR WINS rather than the
/// process dying. `Ord::clamp` panics when `min > max`; this is the shipped rule
/// from `intersect_clamps`, which chose the same degradation for the same reason.
#[test]
fn a_contradictory_bound_degrades_predictably_instead_of_panicking() {
    let row = DerivationRow {
        target: q(0),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1_000,
        divisor: 1,
        bound: Some(ContributionBound { min: 5, max: 0 }),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    // Would have panicked in `core::cmp::clamp` before the fix.
    assert_eq!(row.amount(42).value(), 5, "the floor wins");
    assert_eq!(row.amount(-42).value(), 5);
    // ...and submission still REFUSES it, so the degradation is a backstop and
    // not a licence.
    let (r, a, _) = fixture();
    assert_eq!(
        r.check_derivation(a, &row),
        Err(RowRefusal::ContradictoryBound { min: 5, max: 0 })
    );
}
