//! The hub's five things, exercised from OUTSIDE the crate.
//!
//! These were `#[cfg(test)]` unit tests inside `actor.rs`. `M1` moved them out
//! when the write verb pushed that file past `IMP-D3`'s 400-line ceiling — and
//! the move is an improvement rather than a line-count dodge: every item they
//! touch is public surface, so a unit test could pass against an API a plugin
//! author cannot actually reach. `D-311` argues the hub's SDK IS its public
//! crate surface; a test that only compiles inside the crate does not test it.

use actor_hub::{
    Actor, AttachError, DetachError, EntityId, FoldLayer, GoneState, HubRegistry, ModifierRow,
    PluginDecl, PluginOrdinal, QuantityDecl, QuantityOrdinal,
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

#[test]
fn a_new_actor_has_identity_is_live_and_has_no_quantities() {
    let r = registry();
    let a = Actor::new(EntityId(42));
    assert_eq!(a.id(), EntityId(42));
    assert_eq!(a.existence(), GoneState::Active);
    assert!(a.attached().is_empty());
    for raw in 0..3u16 {
        assert_eq!(
            a.quantity(&r, q(raw)),
            None,
            "an actor with nothing attached has ABSENT quantities, not zeroed ones"
        );
    }
}

/// **Hub §3.4b.** Attaching initialises from the plugin's own declaration,
/// and only the quantities that plugin declares.
#[test]
fn attaching_initialises_exactly_its_own_quantities() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    assert_eq!(a.quantity(&r, q(0)), Some(100));
    assert_eq!(a.quantity(&r, q(2)), Some(30));
    assert_eq!(a.quantity(&r, q(1)), None, "qi belongs to a plugin that is not attached");

    a.attach(&r, p(1)).unwrap();
    assert_eq!(a.quantity(&r, q(1)), Some(7));
}

#[test]
fn attaching_an_undeclared_plugin_is_refused() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    assert_eq!(a.attach(&r, p(9)), Err(AttachError::NotDeclared { plugin: 9 }));
    assert!(a.attached().is_empty());
}

/// A second attach would silently reset a being to its birth values, so it
/// is refused rather than swallowed.
#[test]
fn attaching_twice_is_refused_not_a_silent_reset() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    assert_eq!(a.attach(&r, p(0)), Err(AttachError::AlreadyAttached { plugin: 0 }));
}

#[test]
fn detaching_makes_its_quantities_absent_again() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    a.attach(&r, p(1)).unwrap();
    a.detach(p(1)).unwrap();
    assert_eq!(a.quantity(&r, q(1)), None);
    assert_eq!(a.quantity(&r, q(0)), Some(100), "detaching one plugin left the other alone");
}

/// The other half of *"nothing silent"*: detaching what was never
/// attached is a caller bug, and it is reported rather than swallowed.
#[test]
fn detaching_something_that_is_not_attached_is_refused() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    assert_eq!(a.detach(p(0)), Err(DetachError::NotAttached { plugin: 0 }));
    a.attach(&r, p(0)).unwrap();
    assert_eq!(a.detach(p(0)), Ok(()));
    assert_eq!(a.detach(p(0)), Err(DetachError::NotAttached { plugin: 0 }));
}

#[test]
fn existence_is_platform_state_and_is_carried_not_adjudicated() {
    let mut a = Actor::new(EntityId(1));
    assert!(a.existence().is_live());
    a.set_existence(GoneState::Archived);
    assert!(!a.existence().is_live());
    assert!(!a.existence().is_terminal());
    a.set_existence(GoneState::UserErased);
    assert!(a.existence().is_terminal());

    // **The second half of this test's own name, which nothing witnessed.**
    // A verifier swapped the assignment for `higher(self.existence, state)`
    // -- real adjudication, forbidden two lines above `set_existence` -- and
    // all 91 tests passed, because every transition above moves UPWARD
    // through a lattice `higher` preserves. A DOWNWARD move is the only
    // input that separates carrying from adjudicating (`D-529`).
    a.set_existence(GoneState::Active);
    assert_eq!(
        a.existence(),
        GoneState::Active,
        "the hub CARRIES the state it is given; adjudicating here makes it \
         the authority on erasure, which hub §3.3 assigns to the platform"
    );
}

/// The five things, folded — item 5 reached through items 1..4.
#[test]
fn an_actor_folds_its_attached_plugins_contributions() {
    let r = registry();
    let mut a = Actor::new(EntityId(1));
    a.attach(&r, p(0)).unwrap();
    let rows = [ModifierRow {
        target: q(0),
        op: ruleset_core::ModifierOp::Flat(50),
        source: p(0),
        fold_layer: FoldLayer(10),
    }];
    let out = a.fold(&r, &rows, &[]);
    assert_eq!(out.value(q(0)), Some(150));
    assert_eq!(out.value(q(1)), None);
}

/// The pinned size, asserted at runtime as well so the number appears in a
/// test report and not only in a compile error.
#[test]
fn the_actor_is_the_pinned_size() {
    assert_eq!(core::mem::size_of::<Actor>(), 144);
}
