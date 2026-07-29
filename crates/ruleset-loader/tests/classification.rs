//! S1a — `Strategy::Forbidden`: keys no layer may declare.
//!
//! Its own file rather than more of `load.rs`, because `load.rs` crossed the
//! IMP-D3 400-line ceiling the moment these landed — and allowlisting a
//! violation created by the same commit that builds the ceiling gate would
//! have started that gate's life already compromised.

use ruleset_loader::{parse_layer, Layer, LoadError};

// ── S1a · `Strategy::Forbidden` — keys no layer may declare ─────────────────

/// Each `FORBIDDEN_KEYS` entry is refused **at every layer**, including
/// `forge_override`, which is the one that would otherwise be a post-creation
/// mutation of a claim the engine makes about itself.
#[test]
fn a_forbidden_key_is_refused_at_every_layer_with_its_reason() {
    for (field, _) in ruleset_core::FORBIDDEN_KEYS {
        for layer in Layer::ALL {
            let src = format!("{field} = 3\n[combat]\nmax_hit = 500\n");
            let err = parse_layer(layer, &src)
                .unwrap_err_or_else_msg(&format!("layer {} accepted `{field}`", layer.name()));
            assert!(
                matches!(err, LoadError::ForbiddenField { field: f, .. } if f == *field),
                "expected ForbiddenField for `{field}` at layer {}, got {err}",
                layer.name()
            );
            let msg = format!("{err}");
            assert!(msg.contains(field), "the diagnostic must name the field: {msg}");
            assert!(
                msg.contains("Forbidden"),
                "the diagnostic must say WHY, not just refuse: {msg}"
            );
        }
    }
}

/// The other half, and the half that makes the test above mean something: the
/// same document **without** the forbidden line must load. Without this, a
/// `parse_layer` that refused everything would pass the test above.
#[test]
fn the_same_layer_without_the_forbidden_key_loads() {
    let src = "[combat]\nmax_hit = 500\n";
    let ok = parse_layer(Layer::Reality, src).expect("the remainder is a valid layer");
    assert_eq!(ok.patch.combat.max_hit, Some(500));
}

/// `schema_version` reached `deny_unknown_fields` before S1a and produced
/// *"unknown field"*. It is neither unknown nor the author's to set, and the
/// difference is the whole point of naming the refusal.
#[test]
fn a_forbidden_key_is_not_reported_as_an_unknown_field() {
    let err = parse_layer(Layer::Reality, "schema_version = 3\n").unwrap_err();
    let msg = format!("{err}");
    assert!(
        !msg.contains("unknown field"),
        "a forbidden key must not be diagnosed as unknown: {msg}"
    );
    assert!(matches!(err, LoadError::ForbiddenField { .. }), "got {err}");
}

/// A helper that keeps the loop above readable while still failing loudly.
trait UnwrapErrOrElseMsg<T, E> {
    fn unwrap_err_or_else_msg(self, msg: &str) -> E;
}
impl<T: std::fmt::Debug, E> UnwrapErrOrElseMsg<T, E> for Result<T, E> {
    fn unwrap_err_or_else_msg(self, msg: &str) -> E {
        match self {
            Err(e) => e,
            Ok(v) => panic!("{msg}; got Ok({v:?})"),
        }
    }
}
