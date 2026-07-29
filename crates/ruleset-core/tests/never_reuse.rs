//! `QTY-A5`'s never-reuse arm, finally with a subject.
//!
//! `Q1` shipped this axiom's first three clauses (ordinals assigned, monotonic,
//! table inside the hashed bytes) and deliberately did NOT build the fourth.
//! Within one ruleset an ordinal *is* the position, and the layer merge is a
//! union with no verb for removal — so nothing can be removed and the rule had
//! no possible violation. A validator that returns *permitted* for every input
//! that can exist is the `NV-2` shape, so it was left as an asserted trigger
//! pointing here.
//!
//! An **epoch switch** is what gives it a subject: a new layer stack can simply
//! omit what the old one declared, and then the freed ordinal is available to
//! mean something else. These tests are that subject, exercised.

use ruleset_core::QuantityTable;

fn table(names: &[&str]) -> QuantityTable {
    QuantityTable::assign(names).expect("valid identifiers")
}

/// A reality that declares nothing — the state every reality is in today.
fn empty() -> QuantityTable {
    QuantityTable::EMPTY
}

/// The additive case, which is the one that must keep working: epoch 2 adds a
/// quantity and every earlier ordinal keeps its meaning.
#[test]
fn adding_a_quantity_is_permitted() {
    let e1 = table(&["qi", "karma"]);
    let e2 = table(&["qi", "karma", "fire"]);
    assert!(e2.check_never_reused(&[&e1]).is_ok());
}

/// **The violation the axiom exists for.** `karma` is dropped and `fire` takes
/// ordinal 1 — so every committed event that recorded a change to quantity 1
/// silently becomes a statement about fire.
#[test]
fn rebinding_an_ordinal_to_a_different_identity_is_refused() {
    let e1 = table(&["qi", "karma"]);
    let e2 = table(&["qi", "fire"]);
    let err = e2.check_never_reused(&[&e1]).expect_err("ordinal 1 changed meaning");
    assert_eq!(err.ordinal, 1);
    assert_eq!(err.was, "karma");
    assert_eq!(err.now, "fire");
    assert!(
        format!("{err}").contains("BY NUMBER"),
        "the diagnostic must say WHY reuse is fatal, or the next reader files it \
         as a naming rule: {err}"
    );
}

/// **The reason the binding table keeps one row PER EPOCH.**
///
/// Drop `karma` at epoch 2, then declare something new at epoch 3. Checking only
/// against epoch 2 finds ordinal 1 free and hands it out — while epoch 1's
/// committed events still mean `karma` by it. The union over EVERY prior epoch
/// is what catches it, and it is why `QTY-Q6` closed with an append-only history
/// instead of a mutable `current_ruleset_digest` column.
#[test]
fn an_ordinal_freed_two_epochs_ago_is_still_not_available() {
    let e1 = table(&["qi", "karma"]);
    let e2 = table(&["qi"]); // karma dropped — permitted, ordinal 1 retired
    assert!(e2.check_never_reused(&[&e1]).is_ok());

    let e3 = table(&["qi", "fire"]); // fire lands on the retired ordinal 1
    assert!(
        e3.check_never_reused(&[&e2]).is_ok(),
        "against epoch 2 ALONE this looks fine — which is the trap"
    );
    let err = e3
        .check_never_reused(&[&e1, &e2])
        .expect_err("epoch 1 still means karma by ordinal 1");
    assert_eq!((err.ordinal, err.was.as_str()), (1, "karma"));
}

/// Dropping from the tail is permitted: for every committed event, a retired
/// trailing ordinal is indistinguishable from one that was never declared.
#[test]
fn retiring_a_trailing_ordinal_is_permitted() {
    let e1 = table(&["qi", "karma", "fire"]);
    let e2 = table(&["qi", "karma"]);
    assert!(e2.check_never_reused(&[&e1]).is_ok());
}

/// Order of the priors must not matter — it is a union, not a sequence.
#[test]
fn the_priors_are_a_set_not_a_sequence() {
    let e1 = table(&["qi", "karma"]);
    let e2 = table(&["qi"]);
    let e3 = table(&["qi", "fire"]);
    let forward = e3.check_never_reused(&[&e1, &e2]);
    let reversed = e3.check_never_reused(&[&e2, &e1]);
    assert_eq!(forward, reversed, "the verdict must not depend on prior order");
    assert!(forward.is_err());
}

/// The negative control for every test above. Without it they would all pass
/// for an implementation that refused every switch, which would make an epoch
/// switch impossible rather than safe.
#[test]
fn an_unchanged_table_is_permitted_and_so_is_a_first_epoch() {
    let e1 = table(&["qi", "karma"]);
    assert!(e1.check_never_reused(&[&e1]).is_ok(), "re-activating identical rules");
    assert!(
        table(&["qi"]).check_never_reused(&[]).is_ok(),
        "epoch 1 has no priors and cannot reuse anything"
    );
    assert!(
        empty().check_never_reused(&[&empty()]).is_ok(),
        "two empty tables — every reality that declares nothing"
    );
}

/// A reality that declared nothing may start declaring; and one that declared
/// may not drop to empty and then re-declare something else.
#[test]
fn declaring_from_empty_is_permitted_but_does_not_launder_history() {
    let first = table(&["qi"]);
    assert!(first.check_never_reused(&[&empty()]).is_ok());

    // …and going back to empty does not erase what ordinal 0 meant.
    let err = table(&["karma"])
        .check_never_reused(&[&empty(), &first])
        .expect_err("ordinal 0 was qi");
    assert_eq!((err.ordinal, err.was.as_str(), err.now.as_str()), (0, "qi", "karma"));
}
