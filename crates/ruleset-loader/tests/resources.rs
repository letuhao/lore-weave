//! `Q2 B1` — a reality declares a POOL, and it survives resolve → digest.
//!
//! `QTY-A4`'s claim is that *adding a pool is a declared row, not a
//! `SLOT_COUNT` change*. These tests are what makes that a fact rather than a
//! sentence: nothing in this file touches the engine binary's slot vocabulary,
//! and a reality ends up with a working `qi` pool anyway.

use ruleset_loader::{parse_layer, resolve, Layer, LoadError};
use ruleset_core::{CeilingBinding, RegenType, StatSlot, ZeroBehaviour};

fn reality(toml: &str) -> Result<ruleset_core::Ruleset, LoadError> {
    let layer = parse_layer(Layer::Reality, toml).expect("parses");
    resolve(&[layer])
}

/// **The slice's headline.** `qi` is an identity this engine has never heard
/// of; it becomes a pool with a ceiling bound to a stat slot, and no engine
/// vocabulary moved.
#[test]
fn a_reality_declares_a_pool_the_engine_has_never_heard_of() {
    let r = reality(
        r#"
        quantities = ["qi"]

        [[resources]]
        quantity = "qi"
        min = 0
        base = 0
        ceiling_slot = "max_stamina"
        regen_rate = 5
        regen_type = "flat"
        zero_behaviour = "block_costs"
        "#,
    )
    .expect("a reality may declare its own pool");

    let ordinal = r.quantities.ordinal_of("qi").expect("qi was declared");
    let pool = r.resources.for_quantity(ordinal).expect("and it has a pool row");

    assert_eq!(pool.quantity, ordinal, "the pool is keyed by the QUANTITY ordinal — one space");
    assert_eq!(pool.ceiling, CeilingBinding::Slot(StatSlot::MaxStamina));
    assert_eq!(pool.regen_rate, 5);
    assert_eq!(pool.regen_type, RegenType::Flat);
    assert_eq!(pool.zero_behaviour, ZeroBehaviour::BlockCosts);
}

/// A pool declared in the SAME file as its quantity. The most natural thing an
/// author writes, and it only works because the fold resolves names to ordinals
/// *after* this layer's quantities are in.
#[test]
fn a_quantity_and_its_pool_may_be_declared_in_one_layer() {
    let r = reality(
        r#"
        quantities = ["qi", "mana"]

        [[resources]]
        quantity = "mana"
        ceiling_fixed = 100
        base = 100
        "#,
    )
    .expect("declaring both in one file is the common case");
    let mana = r.quantities.ordinal_of("mana").unwrap();
    assert_eq!(r.resources.for_quantity(mana).unwrap().ceiling, CeilingBinding::Fixed(100));
    // `qi` is declared but is NOT a pool. Most declared quantities are not.
    let qi = r.quantities.ordinal_of("qi").unwrap();
    assert!(r.resources.for_quantity(qi).is_none());
}

/// Rows are stored in ordinal order regardless of authoring order, so the
/// ENCODING is canonical without a sort at digest time — and two files that
/// differ only in the order they list pools produce the SAME digest.
#[test]
fn authoring_order_does_not_move_the_digest() {
    let a = reality(
        r#"
        quantities = ["qi", "mana"]
        [[resources]]
        quantity = "mana"
        ceiling_fixed = 10
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 20
        "#,
    )
    .unwrap();
    let b = reality(
        r#"
        quantities = ["qi", "mana"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 20
        [[resources]]
        quantity = "mana"
        ceiling_fixed = 10
        "#,
    )
    .unwrap();
    assert_eq!(
        a.digest(),
        b.digest(),
        "listing the same pools in a different order is the same ruleset; if these \
         digests differ, a reformat of a TOML file would strand a running reality"
    );
    assert_eq!(a.resources.rows()[0].quantity, 0, "and the rows are in ordinal order");
}

// ── the refusals ────────────────────────────────────────────────────────────

#[test]
fn a_pool_for_an_undeclared_quantity_is_refused() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "mana"
        ceiling_fixed = 10
        "#,
    )
    .expect_err("mana was never declared");
    let msg = format!("{err}");
    assert!(msg.contains("never be named, spent or displayed"), "{msg}");
}

#[test]
fn two_pools_for_one_quantity_are_refused_not_deduped() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 10
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 20
        "#,
    )
    .expect_err("two rows, one identity");
    assert!(format!("{err}").contains("hide which layer's declaration won"));
}

/// **There is no default ceiling, and the refusal says why.** An unbounded pool
/// and a zero-capped one are both plausible readings of "no ceiling given", and
/// both are wrong to guess.
#[test]
fn a_pool_with_no_ceiling_is_refused() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        "#,
    )
    .expect_err("no ceiling");
    let msg = format!("{err}");
    assert!(msg.contains("no ceiling"), "{msg}");
    assert!(msg.contains("QTY-A8"), "the message must say a ceiling is CONTRIBUTED to: {msg}");
}

#[test]
fn two_ceilings_are_refused_rather_than_one_being_picked() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_slot = "max_hp"
        ceiling_fixed = 10
        "#,
    )
    .expect_err("both ceilings");
    assert!(format!("{err}").contains("silently discard the other"));
}

/// A closed-set string must be refused with the legal values, never defaulted.
/// An author who writes `linear` and silently gets `none` spends an afternoon
/// wondering why the pool never refills.
#[test]
fn an_unknown_regen_type_is_refused_with_the_legal_values() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 10
        regen_type = "linear"
        "#,
    )
    .expect_err("linear is not a regen type");
    assert!(format!("{err}").contains("none, flat or per_mille"));
}

/// **`defeat` is the value an author reaches for first**, so the refusal names
/// it explicitly instead of only listing what exists.
#[test]
fn zero_behaviour_defeat_is_refused_and_the_message_says_why() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 10
        zero_behaviour = "defeat"
        "#,
    )
    .expect_err("a declared pool may not end an encounter");
    let msg = format!("{err}");
    assert!(msg.contains("defeat is an engine law reading hp"), "{msg}");
    assert!(
        msg.contains("cannot change which value ends an encounter"),
        "the author must be told WHY, not just that the value is unknown: {msg}"
    );
}

#[test]
fn an_unknown_ceiling_slot_is_refused() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_slot = "max_qi"
        "#,
    )
    .expect_err("max_qi is not a stat slot");
    assert!(format!("{err}").contains("not a stat slot"));
}

#[test]
fn base_outside_the_bounds_is_refused_at_declaration() {
    let err = reality(
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 10
        base = 50
        "#,
    )
    .expect_err("base above a fixed ceiling");
    assert!(format!("{err}").contains("spawn clamped"));
}

/// `RLS-A16` — the pool floor. The engine default ships engine vocabulary, not
/// world content: a pool declared below `preset` would be inherited by every
/// reality on this binary without any of them asking, and `QTY-A10(c)` means
/// they could never remove it.
#[test]
fn a_pool_below_the_preset_floor_is_refused() {
    let layer = parse_layer(
        Layer::EngineDefault,
        r#"
        quantities = ["qi"]
        [[resources]]
        quantity = "qi"
        ceiling_fixed = 10
        "#,
    )
    .expect("parses");
    let err = resolve(&[layer]).expect_err("engine_default may not declare content");
    let msg = format!("{err}");
    assert!(msg.contains("lowest permissible layer"), "{msg}");
}
