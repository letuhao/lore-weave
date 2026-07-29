//! Q1 — the L2 declared-quantity substrate, through the loader.
//!
//! `Ruleset`'s FIRST collection, so this is also where RLS-A4's
//! `UnionByIdOverride` finally gets exercised: F2 deferred it with the reason
//! *"`Ruleset` has none — building it now would be a mechanism with no
//! consumer."*

use ruleset_core::Ruleset;
use ruleset_loader::{parse_layer, resolve, Layer, LoadError};

fn layer(l: Layer, toml: &str) -> ruleset_loader::LayerSource {
    parse_layer(l, toml).expect("parses")
}

/// **The exit criterion doc 35 §12 sets for `Q1`**, minus the store round-trip
/// which `store_round_trip_preserves_ordinals` covers: a reality declares a
/// quantity the engine has never heard of, and it survives with its ordinal.
#[test]
fn a_reality_declares_a_quantity_the_engine_does_not_know() {
    let r = resolve(&[layer(Layer::Reality, "quantities = [\"qi\", \"spirit_stone\"]\n")])
        .expect("a reality may declare its own quantities");
    assert_eq!(r.quantities.len(), 2);
    assert_eq!(r.quantities.ordinal_of("qi"), Some(0));
    assert_eq!(r.quantities.ordinal_of("spirit_stone"), Some(1));
    assert_ne!(
        r.digest(),
        Ruleset::engine_default().digest(),
        "a declared quantity must move the digest — otherwise the ordinal it pins is not \
         actually pinned to anything (QTY-A5)"
    );
}

/// **`AdditiveOnly` (RLS-A17) enforced BY CONSTRUCTION, and this is the proof.**
///
/// The merge is a union with no verb for removal, so a lower layer's identity
/// cannot be dropped by any higher one. If someone later adds a removal syntax,
/// this test is what notices — which is why the property is asserted rather than
/// left as a claim about the code's shape.
#[test]
fn a_lower_layers_declaration_survives_every_higher_layer() {
    let r = resolve(&[
        layer(Layer::Preset, "quantities = [\"qi\"]\n"),
        layer(Layer::Book, "quantities = [\"karma\"]\n"),
        layer(Layer::Reality, "quantities = [\"fire\"]\n"),
        layer(Layer::ForgeOverride, "[combat]\nmax_hit = 500\n"),
    ])
    .expect("layers union");
    assert_eq!(r.quantities.ordinal_of("qi"), Some(0), "the preset's identity survived");
    assert_eq!(r.quantities.ordinal_of("karma"), Some(1));
    assert_eq!(r.quantities.ordinal_of("fire"), Some(2));
}

/// Ordinals are fixed by FIRST appearance, so restating an identity a lower
/// layer already declared is a no-op rather than a renumber. This is the whole
/// point of putting the table in the hashed bytes: the prior project derived
/// ordinals from a `sort()` over present config files, so adding one file
/// renumbered everything after it.
#[test]
fn restating_an_identity_does_not_renumber() {
    let with = resolve(&[
        layer(Layer::Preset, "quantities = [\"qi\", \"karma\"]\n"),
        layer(Layer::Reality, "quantities = [\"qi\", \"fire\"]\n"),
    ])
    .expect("restating is a no-op, not a conflict");
    assert_eq!(with.quantities.ordinal_of("qi"), Some(0));
    assert_eq!(with.quantities.ordinal_of("karma"), Some(1));
    assert_eq!(with.quantities.ordinal_of("fire"), Some(2));
    assert_eq!(with.quantities.len(), 3, "`qi` was declared twice and counted once");
}

/// Across layers a repeat is a legitimate no-op; WITHIN one layer it is an
/// authoring mistake nobody meant, and collapsing it silently is how an author
/// never learns their edit did nothing.
#[test]
fn a_repeat_within_one_layer_is_refused() {
    let err = resolve(&[layer(Layer::Reality, "quantities = [\"qi\", \"qi\"]\n")]).unwrap_err();
    assert!(matches!(err, LoadError::Quantity { .. }), "got {err}");
    assert!(format!("{err}").contains("qi"), "the diagnostic must name the identity");
}

/// **S1b's floor arm, and its first real subject.** Every Ruleset field's floor
/// was `preset` until `Q1`, so the check could refuse nothing and was
/// deliberately not built. This is the input that makes it bite.
#[test]
fn the_engine_default_layer_may_not_declare_a_quantity() {
    let err =
        resolve(&[layer(Layer::EngineDefault, "quantities = [\"qi\"]\n")]).unwrap_err();
    assert!(
        matches!(err, LoadError::BelowFloor { field: "quantities", .. }),
        "got {err}"
    );

    // …and the same declaration one layer up is fine. Without this the test
    // above would pass for a loader that refused every quantity everywhere.
    assert!(resolve(&[layer(Layer::Preset, "quantities = [\"qi\"]\n")]).is_ok());
}

#[test]
fn a_malformed_identity_is_refused_with_its_reason() {
    for bad in ["Qi", "1qi", "qi-pool", "khí"] {
        let src = format!("quantities = [\"{bad}\"]\n");
        let err = resolve(&[layer(Layer::Reality, &src)]).unwrap_err();
        assert!(matches!(err, LoadError::Quantity { .. }), "`{bad}` must be refused, got {err}");
    }
}

/// The engine declares nothing, so every reality that predates `Q1` resolves to
/// an empty table and behaves exactly as before.
#[test]
fn declaring_nothing_is_the_identity() {
    let r = resolve(&[layer(Layer::Reality, "[combat]\nmax_hit = 500\n")]).unwrap();
    assert!(r.quantities.is_empty());
    let mut expected = Ruleset::engine_default();
    expected.combat.max_hit = 500;
    assert_eq!(r, expected, "a layer that declares no quantities changes nothing else");
}
