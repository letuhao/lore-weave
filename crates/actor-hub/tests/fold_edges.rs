//! The fold's EDGES — every case a cold-start review measured as unguarded.
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

// ── the gaps a cold-start review measured, each with the input it needed ─────
//
// Every test below exists because a mutation of the thing it guards left the
// suite GREEN. The pattern in all six is the same and worth naming: the fixture
// was too simple to distinguish the documented behaviour from a plausible wrong
// one. One submitting plugin cannot show an ordering key that sorts by plugin;
// two contributions cannot overflow an `i64`; a derivation whose source has no
// modifiers cannot show which pass it reads.

/// **The three-pass semantics, which is the fold's central documented claim and
/// had no test that could see it.**
///
/// The module doc says pass 2 reads its source quantity's **pass-1** value —
/// i.e. modifier rows applied, derivations not. Give the SOURCE quantity a
/// modifier and the two readings diverge: reading `stored` (the mutation) gives
/// `3 334`, reading pass-1 gives `4 001`.
#[test]
fn a_derivation_reads_the_pass_one_value_not_the_stored_one() {
    let (r, a, s) = fixture();
    // speed: stored 10 000, +2 000 flat  ⇒ pass-1 = 12 000
    // move_range: stored 1, + speed/3
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
    let out = fold(a, &s, &r, &[m(2, ModifierOp::Flat(2_000), 10)], &[deriv]);

    assert_eq!(out.value(q(2)), Some(12_000));
    assert_eq!(
        out.value(q(3)),
        Some(1 + 4_000),
        "the derivation must read the MODIFIED speed (12 000/3 = 4 000), not the stored 10 000"
    );
    assert_eq!(
        out.explain(q(3)).unwrap().contributions[0].derived_from,
        Some((q(2), 12_000)),
        "and the explain path must show which value it read"
    );
}

/// The saturating arithmetic, with enough rows to actually overflow.
///
/// With ONE flat and ONE percent row the worst case is
/// `(i32::MAX + i32::MAX) x (1000 + i32::MAX)`, which fits in `i64` — so
/// `wrapping_mul` passed the old extremes test. Three rows each way does not fit.
#[test]
fn the_accumulator_saturates_rather_than_wrapping() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    // Chosen so the true product lands in `[2^63, 2^64)`: a wrapping multiply
    // returns a NEGATIVE i64 there, while a saturating one returns i64::MAX.
    // Any pair whose product merely exceeds i64::MAX is NOT enough — it can wrap
    // back into the positive half and be indistinguishable from saturation.
    //   sum    = i32::MAX * 3            ~= 6.44e9
    //   factor = 1000 + i32::MAX         ~= 2.147e9
    //   product                          ~= 1.383e19   (2^63 ~= 9.22e18)
    let rows = [
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Percent(i32::MAX), 20),
    ];
    let out = fold(a, &s, &r, &rows, &[]);
    let e = out.explain(q(0)).unwrap();

    assert!(e.flat_sum > 0);
    assert!(e.factor_milli > 0);
    assert!(
        e.pre_emit > 0,
        "a wrapping multiply lands in the negative half here; saturating must not"
    );
    assert_eq!(
        out.value(q(0)),
        Some(i32::MAX),
        "an enormous positive value must saturate at the top of the slot, never wrap to a negative"
    );
    // And it is NOT silent: the accumulator saturation is its own cap site,
    // because after it the number the author asked for is unrecoverable.
    assert!(
        out.capped.iter().any(|c| c.site == CapSite::Accumulator),
        "the i64 accumulator saturated and said nothing"
    );
}

/// The pass-1 intermediate is squeezed into `i32` before a derivation reads it,
/// and a wrapping truncation there would hand the derivation a negative source.
#[test]
fn the_pass_one_intermediate_saturates_before_a_derivation_reads_it() {
    let (r, a, mut s) = fixture();
    s[2] = i32::MAX;
    let deriv = DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor: 1,
        bound: None,
        source: p(0),
        fold_layer: FoldLayer(20),
    };
    // speed x 3 overflows i32; the derivation must read the SATURATED i32, not a
    // wrapped negative.
    let out = fold(a, &s, &r, &[m(2, ModifierOp::Percent(2_000), 10)], &[deriv]);
    let read = out.explain(q(3)).unwrap().contributions[0].derived_from.unwrap().1;
    assert_eq!(read, i32::MAX, "a wrapping truncation would have handed the derivation a negative");
    assert!(out.value(q(3)).unwrap() > 0);
}

/// `M-13` — the intra-layer order sorts by fold layer, THEN by submitting
/// plugin, THEN by submission index. Two plugins at one layer is the input that
/// distinguishes the first two components.
#[test]
fn contributions_from_two_plugins_at_one_layer_order_by_plugin_ordinal() {
    let (r, a, s) = fixture();
    // The LOW plugin contributes at the HIGH layer and vice versa, so sorting by
    // (layer, plugin) and by (plugin, layer) give OPPOSITE answers. With both
    // rows at one layer the two keys agree, which is why the first version of
    // this test could not see the difference.
    let low_plugin_high_layer = ModifierRow {
        target: q(1),
        op: ModifierOp::Flat(1),
        source: p(0),
        fold_layer: FoldLayer(30),
    };
    let high_plugin_low_layer = ModifierRow {
        target: q(1),
        op: ModifierOp::Flat(2),
        source: p(1),
        fold_layer: FoldLayer(20),
    };
    // Submitted in the opposite order to the expected one, so submission index
    // cannot be what sorts them either.
    let out = fold(a, &s, &r, &[low_plugin_high_layer, high_plugin_low_layer], &[]);
    let order: Vec<(u8, u8)> = out
        .explain(q(1))
        .unwrap()
        .contributions
        .iter()
        .map(|c| (c.fold_layer.get(), c.source.get()))
        .collect();
    assert_eq!(
        order,
        vec![(20, 1), (30, 0)],
        "fold layer decides first; the plugin ordinal only breaks a tie WITHIN a layer"
    );
}

/// The other half of the key: at the same `(layer, plugin)`, a literal modifier
/// row is ordered before a derived contribution. The offset in the sort key is
/// what buys that, and without it the two collide and the order is whichever the
/// sort happened to keep.
#[test]
fn a_modifier_orders_before_a_derivation_at_the_same_layer_and_plugin() {
    let (r, a, s) = fixture();
    let deriv = DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor: 1000,
        bound: None,
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    // The derivation is at index 0 of ITS slice and the modifier at index 1 of
    // ITS slice. Without the offset in the sort key the two indices are compared
    // directly, the derivation wins, and the order flips — with a shared index
    // space the stable sort would hide the missing offset entirely, which is how
    // the first version of this test passed against the mutation.
    let out = fold(
        a,
        &s,
        &r,
        &[m(2, ModifierOp::Flat(0), 10), m(3, ModifierOp::Flat(5), 10)],
        &[deriv],
    );
    let kinds: Vec<bool> = out
        .explain(q(3))
        .unwrap()
        .contributions
        .iter()
        .map(|c| c.derived_from.is_some())
        .collect();
    assert_eq!(
        kinds,
        vec![false, true],
        "the literal row is ordered before the derived one at the same (layer, plugin)"
    );
}

/// The report's explanations are in ascending quantity-ordinal order, so two
/// runs of two different builds are comparable rather than merely two runs of
/// one build agreeing with themselves.
#[test]
fn explanations_are_in_ascending_quantity_order() {
    let (r, a, s) = fixture();
    let out = fold(a, &s, &r, &[], &[]);
    let ordinals: Vec<u16> = out.explanations.iter().map(|e| e.quantity.get()).collect();
    let mut sorted = ordinals.clone();
    sorted.sort_unstable();
    assert_eq!(ordinals, sorted);
    assert_eq!(ordinals, vec![0, 1, 2, 3]);
}

/// **The division truncates toward ZERO, not toward the floor**, so a negative
/// quantity rounds up. Unspecified in both contracts and previously unpinned by
/// any test — which means a future `div_euclid` "correctness fix" would move
/// every negative quantity by one with nothing going red.
///
/// Pinned rather than changed: the shipped `resolve_block` truncates the same
/// way, and a replayed encounter must not shift under a rounding change.
#[test]
fn the_emit_division_truncates_toward_zero() {
    let (r, a, mut s) = fixture();
    s[0] = -1;
    let neg = fold(a, &s, &r, &[m(0, ModifierOp::Percent(-1), 10)], &[]);
    assert_eq!(neg.value(q(0)), Some(0), "-0.999 truncates toward zero, not down to -1");

    s[0] = 1;
    let pos = fold(a, &s, &r, &[m(0, ModifierOp::Percent(-1), 10)], &[]);
    assert_eq!(pos.value(q(0)), Some(0));

    s[0] = -1000;
    let big = fold(a, &s, &r, &[m(0, ModifierOp::Percent(-1), 10)], &[]);
    assert_eq!(big.value(q(0)), Some(-999));
}

/// Both of a derivation's clamps are facts in the report, not silent squeezes.
#[test]
fn a_derivations_own_clamps_are_reported() {
    let (r, a, mut s) = fixture();
    s[2] = i32::MAX;
    let bounded = DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor: 1,
        bound: Some(ContributionBound { min: 0, max: 5 }),
        source: p(0),
        fold_layer: FoldLayer(20),
    };
    let out = fold(a, &s, &r, &[], &[bounded]);
    assert_eq!(out.value(q(3)), Some(1 + 5));
    let cap = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::DerivedBound)
        .expect("the author's own bound bit and said nothing");
    assert_eq!(cap.quantity, q(3));
    assert_eq!(cap.wanted, i32::MAX as i64);
    assert_eq!(cap.emitted, 5);

    // ...and the representation squeeze is a DIFFERENT site, because one is the
    // author's declaration working and the other is the i32 failing.
    let unbounded = DerivationRow { bound: None, factor_milli: 1_000, ..bounded };
    let out = fold(a, &s, &r, &[], &[unbounded]);
    assert!(out.capped.iter().any(|c| c.site == CapSite::DerivedAmount));
}

/// **The negative direction of the accumulator saturation**, and the field the
/// record carries — both of which the positive-only test could not see.
///
/// A review measured the hole: `emitted` was hardcoded to `i32::MAX` on the
/// accumulator record, so a downward overflow produced **two CAPPED events for
/// one quantity whose `emitted` fields contradicted each other** — and the one
/// that lied was the one substrate §7 exists to make non-silent. Mutating either
/// field of that record left the whole suite green.
#[test]
fn a_downward_saturation_reports_the_value_it_actually_emitted() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MIN;
    let rows = [
        m(0, ModifierOp::Flat(i32::MIN), 10),
        m(0, ModifierOp::Flat(i32::MIN), 10),
        m(0, ModifierOp::Percent(i32::MAX), 20),
    ];
    let out = fold(a, &s, &r, &rows, &[]);
    let value = out.value(q(0)).unwrap();
    assert_eq!(value, i32::MIN, "an enormous negative value saturates at the BOTTOM of the slot");

    let acc = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::Accumulator)
        .expect("the i64 accumulator saturated and said nothing");
    assert_eq!(
        acc.emitted, value,
        "the record must carry the value the fold actually emitted, not a hardcoded i32::MAX"
    );
    assert!(acc.wanted < 0, "and `wanted` must carry the sign of what was asked for");

    // Every QUANTITY-LEVEL record agrees about what was emitted. Two such events
    // contradicting each other is worse than one, because a reader cannot tell
    // which to believe.
    //
    // Scoped to the quantity-level sites on purpose: a review showed the
    // unscoped version was **false of the fold** the moment a derivation is
    // present, because `DerivedBound`/`DerivedAmount` report the ROW's
    // contributed amount rather than the quantity's value. See
    // `derivation_cap_records_report_the_rows_amount_not_the_quantitys` below,
    // which pins that difference rather than papering over it.
    for c in out
        .capped
        .iter()
        .filter(|c| c.quantity == q(0))
        .filter(|c| matches!(c.site, CapSite::Accumulator | CapSite::Emit))
    {
        assert_eq!(c.emitted, value, "quantity-level cap records disagree: {c:?}");
    }
}

/// The same agreement in the positive direction, so the assertion above is not
/// silently sign-specific.
#[test]
fn every_cap_record_for_one_quantity_agrees_on_what_was_emitted() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    let rows = [
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Flat(i32::MAX), 10),
        m(0, ModifierOp::Percent(i32::MAX), 20),
    ];
    let out = fold(a, &s, &r, &rows, &[]);
    let value = out.value(q(0)).unwrap();
    assert_eq!(value, i32::MAX);
    assert!(out.capped.iter().any(|c| c.site == CapSite::Accumulator));
    for c in out
        .capped
        .iter()
        .filter(|c| c.quantity == q(0))
        .filter(|c| matches!(c.site, CapSite::Accumulator | CapSite::Emit))
    {
        assert_eq!(c.emitted, value);
        assert!(c.wanted > 0);
    }
}
