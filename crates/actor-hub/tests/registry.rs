//! The declaration registry and the submission-time refusals, asserted from
//! OUTSIDE the crate — see `tests/fold.rs` for why these live here.

use actor_hub::*;
use ruleset_core::{ModifierOp, OpKind, QuantityTable};


fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).unwrap()
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).unwrap()
}

/// A reality that declared four quantities. Names are the author's; the hub
/// never reads them.
fn table() -> QuantityTable {
    QuantityTable::assign(&["hp", "qi", "speed", "move_range"]).unwrap()
}

fn combat_like() -> PluginDecl {
    PluginDecl {
        ordinal: p(0),
        quantities: vec![
            QuantityDecl { ordinal: q(0), initial: 100 },
            QuantityDecl { ordinal: q(2), initial: 10 },
            QuantityDecl { ordinal: q(3), initial: 1 },
        ],
        fold_layers: vec![FoldLayer(10), FoldLayer(20)],
    }
}

fn cultivation_like() -> PluginDecl {
    PluginDecl {
        ordinal: p(1),
        quantities: vec![QuantityDecl { ordinal: q(1), initial: 0 }],
        fold_layers: vec![FoldLayer(20), FoldLayer(30)],
    }
}

#[test]
fn a_registry_records_who_declares_what() {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    assert_eq!(r.owner_of(q(0)), Some(p(0)));
    assert_eq!(r.owner_of(q(1)), Some(p(1)));
    assert_eq!(r.owner_of(q(2)), Some(p(0)));
    assert_eq!(r.declared_plugins().len(), 2);
}

/// The collision check, which is the reason this type refuses rather than
/// merges: two owners make *"is the declaring plugin attached"* ambiguous.
#[test]
fn two_plugins_claiming_one_ordinal_is_refused() {
    let clash = PluginDecl {
        ordinal: p(1),
        quantities: vec![QuantityDecl { ordinal: q(0), initial: 7 }],
        fold_layers: vec![],
    };
    let err = HubRegistry::build(&table(), &[combat_like(), clash]).unwrap_err();
    assert_eq!(
        err,
        RegistryError::QuantityClaimedTwice { ordinal: 0, first: 0, second: 1 }
    );
}

#[test]
fn a_duplicate_plugin_ordinal_is_refused() {
    let err = HubRegistry::build(&table(), &[combat_like(), combat_like()]).unwrap_err();
    assert_eq!(err, RegistryError::PluginDeclaredTwice { ordinal: 0 });
}

/// `QTY-A14` — an ordinal past the reality's own table is not a quantity
/// this reality has.
#[test]
fn an_ordinal_past_the_declared_table_is_refused() {
    let over = PluginDecl {
        ordinal: p(2),
        quantities: vec![QuantityDecl { ordinal: q(9), initial: 1 }],
        fold_layers: vec![],
    };
    let err = HubRegistry::build(&table(), &[over]).unwrap_err();
    assert_eq!(err, RegistryError::OrdinalPastDeclaredTable { ordinal: 9, declared: 4 });
}

/// **Hub §3.4b, the whole obligation.** A quantity of an unattached plugin
/// is ABSENT — `None`, not `Some(0)`.
#[test]
fn an_unattached_plugins_quantity_is_absent_not_zero() {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let combat_only = PluginSet::EMPTY.attach(p(0));

    assert_eq!(r.initial_value(combat_only, q(0)), Some(100));
    assert_eq!(
        r.initial_value(combat_only, q(1)),
        None,
        "a stone has no qi because cultivation is not attached — and ABSENT is not zero"
    );
    assert!(r.is_present(combat_only, q(0)));
    assert!(!r.is_present(combat_only, q(1)));

    let both = combat_only.attach(p(1));
    assert_eq!(r.initial_value(both, q(1)), Some(0));
}

/// Building is order-independent: the same declarations in any order give
/// the same registry, so a loader that folds layers differently cannot
/// change what a reality means.
#[test]
fn build_is_order_independent() {
    let forward = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let backward = HubRegistry::build(&table(), &[cultivation_like(), combat_like()]).unwrap();
    assert_eq!(forward, backward);
}

// ── submission-time refusals (M-5), including U-7 ────────────────────────

fn registry_and_actor() -> (HubRegistry, PluginSet) {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let attached = PluginSet::EMPTY.attach(p(0)).attach(p(1));
    (r, attached)
}

fn modifier(target: u16, layer: u8, source: u8) -> ModifierRow {
    ModifierRow {
        target: q(target),
        op: ModifierOp::Flat(5),
        source: p(source),
        fold_layer: FoldLayer(layer),
    }
}

#[test]
fn a_well_formed_row_is_accepted() {
    let (r, a) = registry_and_actor();
    assert_eq!(r.check_modifier(a, &modifier(0, 10, 0)), Ok(()));
}

/// **`U-7` in its non-vacuous form.** A plugin ships a row for a layer it
/// forgot to declare, and the row is refused rather than landing in an
/// order nothing defines.
#[test]
fn a_row_naming_an_undeclared_fold_layer_is_refused() {
    let (r, a) = registry_and_actor();
    assert_eq!(
        r.check_modifier(a, &modifier(0, 99, 0)),
        Err(RowRefusal::UndeclaredFoldLayer { layer: 99 })
    );
    // ...and the declared ones still pass, so the check is discriminating
    // rather than uniformly refusing.
    for declared in [10u8, 20, 30] {
        assert_eq!(r.check_modifier(a, &modifier(0, declared, 0)), Ok(()));
    }
}

#[test]
fn a_row_from_an_unattached_plugin_is_refused() {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let combat_only = PluginSet::EMPTY.attach(p(0));
    assert_eq!(
        r.check_modifier(combat_only, &modifier(1, 20, 1)),
        Err(RowRefusal::SourceNotAttached { plugin: 1 })
    );
}

#[test]
fn a_row_targeting_an_absent_quantity_is_refused() {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let combat_only = PluginSet::EMPTY.attach(p(0));
    assert_eq!(
        r.check_modifier(combat_only, &modifier(1, 10, 0)),
        Err(RowRefusal::UndeclaredTarget { ordinal: 1 })
    );
}

fn derivation(divisor: i32, bound: Option<ContributionBound>) -> DerivationRow {
    DerivationRow {
        target: q(3),
        source_quantity: q(2),
        op: OpKind::Flat,
        factor_milli: 1,
        divisor,
        bound,
        source: p(0),
        fold_layer: FoldLayer(10),
    }
}

#[test]
fn a_zero_divisor_is_refused_at_submission() {
    let (r, a) = registry_and_actor();
    assert_eq!(r.check_derivation(a, &derivation(3, None)), Ok(()));
    assert_eq!(r.check_derivation(a, &derivation(0, None)), Err(RowRefusal::ZeroDivisor));
}

#[test]
fn a_contradictory_bound_is_refused_at_submission() {
    let (r, a) = registry_and_actor();
    let ok = ContributionBound { min: 1, max: 5 };
    let empty = ContributionBound { min: 200, max: 3 };
    assert_eq!(r.check_derivation(a, &derivation(1, Some(ok))), Ok(()));
    assert_eq!(
        r.check_derivation(a, &derivation(1, Some(empty))),
        Err(RowRefusal::ContradictoryBound { min: 200, max: 3 })
    );
}

#[test]
fn a_derivation_reading_an_absent_quantity_is_refused() {
    let r = HubRegistry::build(&table(), &[combat_like(), cultivation_like()]).unwrap();
    let cultivation_only = PluginSet::EMPTY.attach(p(1));
    let mut row = derivation(1, None);
    row.source = p(1);
    row.target = q(1);
    row.fold_layer = FoldLayer(30);
    assert_eq!(
        r.check_derivation(cultivation_only, &row),
        Err(RowRefusal::UndeclaredSource { ordinal: 2 })
    );
}

/// **The whole fold-layer ordinal space must be indexable, at both ends.**
///
/// Added after a review measured that narrowing the registry's declared-layer
/// index to 128 compiled, kept a `const` assertion green and passed every test —
/// while making `FoldLayer(200)` panic out of bounds inside a fold documented as
/// total. Deriving the width from `FoldLayer`'s own type removed the drift; THIS
/// is what makes the width itself observable.
#[test]
fn every_fold_layer_ordinal_is_declarable_and_checkable() {
    let table = QuantityTable::assign(&["hp"]).unwrap();
    let extremes = vec![FoldLayer(0), FoldLayer(127), FoldLayer(128), FoldLayer(255)];
    let r = HubRegistry::build(
        &table,
        &[PluginDecl {
            ordinal: p(0),
            quantities: vec![QuantityDecl { ordinal: q(0), initial: 1 }],
            fold_layers: extremes.clone(),
        }],
    )
    .unwrap();
    let attached = PluginSet::EMPTY.attach(p(0));

    for l in &extremes {
        assert!(r.is_declared_layer(*l), "layer {} was declared and is not visible", l.get());
        let row = ModifierRow {
            target: q(0),
            op: ModifierOp::Flat(1),
            source: p(0),
            fold_layer: *l,
        };
        assert_eq!(r.check_modifier(attached, &row), Ok(()));
    }
    // ...and an undeclared one at the top of the space is still refused, so the
    // check is discriminating across the whole range rather than saturating.
    assert!(!r.is_declared_layer(FoldLayer(254)));
    assert_eq!(
        r.check_modifier(
            attached,
            &ModifierRow {
                target: q(0),
                op: ModifierOp::Flat(1),
                source: p(0),
                fold_layer: FoldLayer(254),
            }
        ),
        Err(RowRefusal::UndeclaredFoldLayer { layer: 254 })
    );
}
