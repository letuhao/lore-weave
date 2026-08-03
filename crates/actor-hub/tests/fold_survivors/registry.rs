//! The `HubRegistry` half of the survivor register — the checks that refuse a
//! ROW before the fold ever sees it: the fold layer, the divisor, the bound, the
//! ordinal boundary, and the ORDER those refusals are reported in.
//!
//! Split out of `fold_survivors.rs` when `file-ceiling-gate` fired at 445 lines
//! against a 400 ceiling. That gate exists to create this moment: an append-only
//! register that gains a test per proven survivor only ever gets longer, so
//! there is no size at which anyone would otherwise be obliged to split it.
//!
//! Same test BINARY, reached by `#[path]` from the root file — a bare `mod` there
//! resolves to the SIBLING `tests/registry.rs` and silently compiles it twice — so
//! the mutation harness still runs `--test fold_survivors`; these are addressed as
//! `registry::<name>`.

use super::{deriv, fixture, p, q};
use actor_hub::*;
use ruleset_core::QuantityTable;

/// **`check_derivation` really does check the fold layer.**
///
/// Turning its `self.check_layer(row.fold_layer)?` into `let _ = …` was green,
/// while the identical deletion on the MODIFIER path went red — the same rule,
/// tested on one of its two paths.
#[test]
fn a_derivation_on_an_undeclared_fold_layer_is_refused() {
    let (r, a, s) = fixture();
    // Layer 99 is declared by nobody.
    let out = fold(a, &s, &r, &[], &[deriv(3, 2, 99)]);

    assert_eq!(out.refused.len(), 1, "an undeclared fold layer was accepted");
    assert_eq!(out.refused[0].row, RowRef::Derivation(0));
    assert!(
        matches!(out.refused[0].reason, RowRefusal::UndeclaredFoldLayer { .. }),
        "expected UndeclaredFoldLayer, got {:?}",
        out.refused[0].reason
    );
    assert_eq!(out.value(q(3)), Some(1), "a refused row must contribute nothing");
}

/// **A zero divisor and a contradictory bound are refused on the derivation
/// path**, both of which sit beside the layer check that had no case.
#[test]
fn a_zero_divisor_and_a_contradictory_bound_are_refused() {
    let (r, a, s) = fixture();
    let zero = DerivationRow { divisor: 0, ..deriv(3, 2, 20) };
    let contradictory = DerivationRow {
        bound: Some(ContributionBound { min: 10, max: 5 }),
        ..deriv(3, 2, 20)
    };

    let out = fold(a, &s, &r, &[], &[zero, contradictory]);

    assert_eq!(out.refused.len(), 2);
    assert!(matches!(out.refused[0].reason, RowRefusal::ZeroDivisor));
    assert!(matches!(
        out.refused[1].reason,
        RowRefusal::ContradictoryBound { min: 10, max: 5 }
    ));
    assert_eq!(out.value(q(3)), Some(1), "neither refused row may contribute");
}

/// **An EXACT bound — `min == max` — is legal.**
///
/// `ContributionBound`'s own doc says *"inclusive on both ends. `min > max` is
/// refused"*, so a bound pinning a contribution to one value is a supported
/// declaration. Weakening the refusal to `>=` was green: the only case used
/// `{min: 10, max: 5}`, strictly greater — the interesting half — and left the
/// boundary itself inferred. **That is the exact shape this file's own module
/// doc says it exists to eliminate**, and its sibling
/// `an_ordinal_exactly_at_the_table_length_is_refused` is the same defect one
/// file over. A round of 113 mutations did not find it; round 11 did.
#[test]
fn an_exact_bound_is_legal_and_pins_the_contribution() {
    let (r, a, mut s) = fixture();
    s[2] = 90_000;
    let exact = DerivationRow {
        bound: Some(ContributionBound { min: 7, max: 7 }),
        ..deriv(3, 2, 20)
    };

    let out = fold(a, &s, &r, &[], &[exact]);

    assert!(
        out.refused.is_empty(),
        "an exact bound min==max must NOT be refused: {:?}",
        out.refused
    );
    assert_eq!(out.value(q(3)), Some(1 + 7), "the bound must pin the contribution to 7");
    assert!(
        out.capped.iter().any(|c| c.site == CapSite::DerivedBound),
        "the bound bit and said nothing"
    );
}

/// **An ordinal EQUAL to the declared table length is past the end.**
///
/// The only case used ordinal 9 against a 4-entry table — five past the
/// boundary — so weakening `>=` to `>` was green and a 4-entry table accepted
/// ordinal 4. Off-by-one lives at the boundary, and only a test at the boundary
/// can see it.
#[test]
fn an_ordinal_exactly_at_the_table_length_is_refused() {
    let table = QuantityTable::assign(&["hp", "qi", "speed", "move_range"]).unwrap();
    let decls = vec![PluginDecl {
        ordinal: p(0),
        quantities: vec![QuantityDecl { ordinal: q(4), initial: 1 }],
        fold_layers: vec![FoldLayer(10)],
    }];

    let err = HubRegistry::build(&table, &decls).expect_err("ordinal 4 in a 4-entry table was accepted");
    assert!(
        matches!(err, RegistryError::OrdinalPastDeclaredTable { ordinal: 4, declared: 4 }),
        "expected OrdinalPastDeclaredTable{{4, 4}}, got {err:?}"
    );

    // ...and the last VALID ordinal still builds, so the fix is a boundary and
    // not a blanket refusal.
    let ok = vec![PluginDecl {
        ordinal: p(0),
        quantities: vec![QuantityDecl { ordinal: q(3), initial: 1 }],
        fold_layers: vec![FoldLayer(10)],
    }];
    assert!(HubRegistry::build(&table, &ok).is_ok(), "ordinal 3 is the last valid one");
}

/// **The layer check runs BEFORE the divisor check.**
///
/// `check_derivation` refuses in a fixed order, and the sibling precedence —
/// source before target — has a case. This pair did not, so swapping the two
/// lines was green: a row violating BOTH reported `ZeroDivisor` where the
/// shipped contract reports `UndeclaredFoldLayer`. A refusal REASON is the
/// whole product of substrate §7; reporting the second of two is a wrong
/// answer, not a cosmetic one.
#[test]
fn an_undeclared_layer_is_reported_before_a_zero_divisor() {
    let (r, a, _) = fixture();
    let mut bad = deriv(3, 2, 99); // layer 99 is declared by nobody...
    bad.divisor = 0; // ...and the divisor is zero as well.

    let err = r
        .check_derivation(a, &bad)
        .expect_err("a row with an undeclared layer AND a zero divisor was accepted");

    assert!(
        matches!(err, RowRefusal::UndeclaredFoldLayer { .. }),
        "the layer check must run first; got {err:?}"
    );

    // ...and with the layer fixed, the divisor is still reported — so the
    // assertion above is about ORDER and not about the divisor check being dead.
    let mut only_divisor = deriv(3, 2, 20);
    only_divisor.divisor = 0;
    assert!(
        matches!(r.check_derivation(a, &only_divisor), Err(RowRefusal::ZeroDivisor)),
        "the divisor check must still fire once the layer is legal"
    );
}
