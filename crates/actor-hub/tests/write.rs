//! **The write verb** — `set_quantity`, the door `M1` needed and `M2`'s `Delta`
//! primitive goes through.
//!
//! An INTEGRATION test rather than a `#[cfg(test)]` module, and not only for
//! `IMP-D3`'s line ceiling: `set_quantity` is public surface, so exercising it
//! from outside the crate proves a plugin author can reach it. A unit test can
//! pass against a verb no consumer could actually call.

use actor_hub::{
    Actor, EntityId, FoldLayer, HubRegistry, ModifierOp, ModifierRow, PluginDecl, PluginOrdinal,
    QuantityDecl, QuantityOrdinal, WriteError,
};
use ruleset_core::QuantityTable;

fn q(raw: u16) -> QuantityOrdinal {
    QuantityOrdinal::new(raw).unwrap()
}

fn p(raw: u8) -> PluginOrdinal {
    PluginOrdinal::new(raw).unwrap()
}

fn registry() -> HubRegistry {
    let table = QuantityTable::assign(&["hp", "qi", "speed"]).unwrap();
    HubRegistry::build(
        &table,
        &[
            PluginDecl {
                ordinal: p(0),
                quantities: vec![
                    QuantityDecl { ordinal: q(0), initial: 100 },
                    QuantityDecl { ordinal: q(2), initial: 30 },
                ],
                fold_layers: vec![FoldLayer(10)],
            },
            PluginDecl {
                ordinal: p(1),
                quantities: vec![QuantityDecl { ordinal: q(1), initial: 7 }],
                fold_layers: vec![FoldLayer(20)],
            },
        ],
    )
    .unwrap()
}

/// The write verb carries; it does not decide. No clamp, no ceiling — those are
/// the ruleset's and the hub cannot see them.
#[test]
fn the_declaring_plugin_may_write_its_own_quantity() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    assert_eq!(a.quantity(&r, q(0)), Some(100));
    assert_eq!(a.set_quantity(&r, p(0), q(0), 37), Ok(()));
    assert_eq!(a.quantity(&r, q(0)), Some(37));
    // Values the hub has no opinion about, because it has no opinion.
    assert_eq!(a.set_quantity(&r, p(0), q(0), -5), Ok(()));
    assert_eq!(a.quantity(&r, q(0)), Some(-5));
    assert_eq!(a.set_quantity(&r, p(0), q(0), i32::MAX), Ok(()));
    assert_eq!(a.quantity(&r, q(0)), Some(i32::MAX));
}

/// A plugin may not write a quantity it does not declare — the reason the verb
/// takes a writer at all.
#[test]
fn a_plugin_may_not_write_a_quantity_it_does_not_declare() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    a.attach(&r, p(1)).unwrap();
    assert_eq!(
        a.set_quantity(&r, p(1), q(0), 0),
        Err(WriteError::NotOwner { ordinal: 0, owner: Some(0), writer: 1 })
    );
    assert_eq!(a.quantity(&r, q(0)), Some(100), "the refused write changed nothing");
}

/// **ABSENT is not zero, on the write path too.** Owning the ordinal in this
/// reality is not the same as being attached to THIS actor, and the two refusals
/// stay distinguishable.
#[test]
fn writing_an_absent_quantity_is_refused_and_names_absence() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    assert_eq!(a.set_quantity(&r, p(1), q(1), 9), Err(WriteError::Absent { ordinal: 1 }));
    assert_eq!(a.quantity(&r, q(1)), None);

    // No plugin in this reality declares ordinal 7, so the answer is NotOwner
    // with no owner to name — not Absent, which would imply the quantity exists
    // somewhere and merely is not here.
    assert_eq!(
        a.set_quantity(&r, p(0), q(7), 1),
        Err(WriteError::NotOwner { ordinal: 7, owner: None, writer: 0 })
    );
}

/// **The test `attach`'s comment promised and could not write.**
///
/// Kill-mutation: relax `attach`'s `registry.owner_of(q) == Some(p)` to
/// `.is_some()`. Before `set_quantity` existed that change reddened nothing,
/// because re-initialising wrote back the value already there. It now restores a
/// wounded actor to full health the moment an unrelated plugin attaches, and
/// this test is what says so. Measured 2026-08-06: mutated, RED here and nowhere
/// else; restored, green.
#[test]
fn attaching_a_second_plugin_does_not_reset_the_first() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    a.set_quantity(&r, p(0), q(0), 12).unwrap();

    a.attach(&r, p(1)).unwrap();

    assert_eq!(
        a.quantity(&r, q(0)),
        Some(12),
        "attaching plugin 1 re-initialised plugin 0's quantity — the actor healed          because something unrelated was attached to them"
    );
    assert_eq!(a.quantity(&r, q(1)), Some(7), "and the new plugin still got its own initial");
}

/// A written value reaches the FOLD, not only the getter — otherwise the write
/// and the resolution would be two stores of one number.
#[test]
fn a_written_value_is_what_the_fold_starts_from() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    a.set_quantity(&r, p(0), q(0), 40).unwrap();
    let out = a.fold(
        &r,
        &[ModifierRow {
            target: q(0),
            op: ModifierOp::Flat(5),
            source: p(0),
            fold_layer: FoldLayer(10),
        }],
        &[],
    );
    assert_eq!(out.value(q(0)), Some(45), "the fold read the WRITTEN value, not the initial");
}
