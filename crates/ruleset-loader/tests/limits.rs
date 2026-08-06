//! `LIM-1` — **the reality declares its own size; the engine only says what the
//! binary can hold.**
//!
//! Its own file rather than more of `quantities.rs`/`resources.rs`, and the seam
//! is the one the feature draws: those two are about whether a ROW is well
//! formed, this is about whether the WORLD has room for it. They fail for
//! different reasons and are read by different people — an author fixes the
//! first, a deployer sometimes has to fix the second.
//!
//! ## What must be able to fail here, and how
//!
//! The whole feature is a refusal, so every test below is paired: one that
//! refuses and one that ACCEPTS the same shape with the limit moved. Without the
//! accepting half, a `room_for` that returned `Err` unconditionally would pass
//! every refusal test in this file.

use ruleset_core::{LimitError, Limits, OrdinalSpace};
use ruleset_loader::{parse_layer, resolve, Layer, LoadError};

fn layer(l: Layer, toml: &str) -> ruleset_loader::LayerSource {
    parse_layer(l, toml).expect("parses")
}

/// A verb row, parameterised only by name — the rows themselves are irrelevant
/// here, only how many there are.
fn verb(name: &str) -> String {
    format!(
        "[[verbs]]\nname = \"{name}\"\ncue = 1\ntarget = \"actor\"\n\
         effect_quantity = \"focus\"\neffect_amount = -1\n"
    )
}

fn preset_with(limits: &str, verbs: &[&str]) -> String {
    let mut s = String::from("quantities = [\"focus\"]\n");
    s.push_str(limits);
    for v in verbs {
        s.push_str(&verb(v));
    }
    s
}

// ── the refusal that did not exist before, and its accepting twin ───────────

/// **The headline: a world that declares itself small IS small.**
///
/// Before `LIM-1` this manifest loaded. The only ceiling in the engine was the
/// engine's own, and 2 verbs is comfortably under it — so a reality had no way
/// to say *"two is one too many for me"*.
#[test]
fn a_reality_declares_its_own_verb_ceiling_and_the_engine_honours_it() {
    let src = preset_with("[limits]\nverbs = 1\n", &["gather", "brace"]);
    let err = resolve(&[layer(Layer::Preset, &src)]).expect_err("the second verb must not fit");

    let LoadError::Limit { source: LimitError::AtLimit { space, limit, row }, .. } = &err else {
        panic!("expected an AtLimit refusal, got {err}");
    };
    assert_eq!(*space, OrdinalSpace::Verbs);
    assert_eq!(*limit, 1);
    assert_eq!(row, "brace", "the message must name the row that did not fit, not just a count");

    // The diagnostic has to point the author at THEIR number. A message naming
    // only the engine's capacity is the exact defect `LIM-1` exists to remove.
    let msg = format!("{err}");
    assert!(msg.contains("brace"), "must name the row: {msg}");
    assert!(msg.contains("[limits] verbs"), "must name the key to edit: {msg}");
    assert!(msg.contains("YOUR world's number"), "must say whose number it is: {msg}");
}

/// The accepting twin. **Without this the test above proves nothing** — a
/// `room_for` hardwired to refuse would satisfy it.
#[test]
fn the_same_two_verbs_load_when_the_reality_declares_room_for_them() {
    let src = preset_with("[limits]\nverbs = 2\n", &["gather", "brace"]);
    let r = resolve(&[layer(Layer::Preset, &src)]).expect("two verbs under a limit of two");
    assert_eq!(r.verbs.len(), 2);
}

/// A manifest that declares no `[limits]` block behaves exactly as every
/// manifest did before this feature existed (`AUTHOR-1`: the authored surface
/// stays optional).
#[test]
fn no_limits_block_means_the_binarys_capacity() {
    let src = preset_with("", &["gather", "brace"]);
    let r = resolve(&[layer(Layer::Preset, &src)]).expect("no [limits] block is not zero limits");
    assert_eq!(r.verbs.len(), 2);
}

/// **The shipped preset's `[limits]` block has a CONSUMER, and this is it.**
///
/// Without this test the block in `proving-ground.toml` would be prose that
/// happens to live in a data file — the shape `scripts/deferral-gate.py` exists
/// to refuse one tier up. The proving ground declares `verbs = 4`; a later layer
/// pushing it to five is refused by the PRESET's number, not the engine's.
#[test]
fn the_shipped_proving_ground_declares_a_size_and_is_held_to_it() {
    let preset = layer(Layer::Preset, ruleset_loader::PROVING_GROUND_TOML);
    let as_shipped = resolve(&[preset.clone()]).expect("the proving ground loads as shipped");
    assert_eq!(as_shipped.verbs.len(), 1, "gather");
    assert_eq!(as_shipped.quantities.len(), 4);

    // Three more verbs reach the declared four; the fourth does not fit.
    let three: String = (0..3).map(|i| verb(&format!("extra{i}"))).collect();
    resolve(&[preset.clone(), layer(Layer::Reality, &three)]).expect("four verbs is the limit");

    let four: String = (0..4).map(|i| verb(&format!("extra{i}"))).collect();
    let err = resolve(&[preset, layer(Layer::Reality, &four)]).expect_err("five is one too many");
    assert!(
        matches!(&err, LoadError::Limit { source: LimitError::AtLimit { limit: 4, row, .. }, .. }
                 if row == "extra3"),
        "expected the preset's own limit of 4 to refuse `extra3`, got {err}"
    );
}

// ── the OTHER audience: a size the binary cannot hold ───────────────────────

/// **The refusal that names a rebuild rather than an authoring mistake.**
///
/// This is the sentence the engine is entitled to say, and the only one: *the
/// world is fine, this build is too small.* It must not be confused with
/// `AtLimit`, which is the author's problem.
#[test]
fn a_limit_above_the_builds_capacity_is_a_deployment_refusal() {
    let asked = OrdinalSpace::Verbs.capacity() + 1;
    let src = preset_with(&format!("[limits]\nverbs = {asked}\n"), &[]);
    let err = resolve(&[layer(Layer::Preset, &src)]).expect_err("past capacity");

    let LoadError::Limit { source: LimitError::AboveCapacity { space, capacity, .. }, .. } = &err
    else {
        panic!("expected AboveCapacity, got {err}");
    };
    assert_eq!(*space, OrdinalSpace::Verbs);
    assert_eq!(*capacity, OrdinalSpace::Verbs.capacity());

    let msg = format!("{err}");
    assert!(msg.contains("rebuild"), "must name the remedy: {msg}");
    assert!(msg.contains("moves no existing digest"), "must say the rebuild is safe: {msg}");
}

/// Its twin: exactly AT capacity is fine. A `>` that had been written `>=` would
/// pass the test above and fail here.
#[test]
fn a_limit_exactly_at_capacity_is_accepted() {
    let src = preset_with(&format!("[limits]\nverbs = {}\n", OrdinalSpace::Verbs.capacity()), &[]);
    resolve(&[layer(Layer::Preset, &src)]).expect("capacity itself is a legal limit");
}

// ── narrowing, which is the case that can corrupt a fold ────────────────────

/// A higher layer may not narrow the world out from under rows a lower layer
/// already put in it — that would leave the resolved ruleset holding an ordinal
/// past its own declared ceiling, a state no later check looks for.
#[test]
fn a_layer_may_not_narrow_below_what_lower_layers_declared() {
    let err = resolve(&[
        layer(Layer::Preset, "quantities = [\"a\", \"b\", \"c\"]\n"),
        layer(Layer::Reality, "[limits]\nquantities = 2\n"),
    ])
    .expect_err("2 is below the 3 already declared");

    let LoadError::Limit { source: LimitError::BelowDeclared { asked, declared, .. }, .. } = &err
    else {
        panic!("expected BelowDeclared, got {err}");
    };
    assert_eq!((*asked, *declared), (2, 3));
}

/// Narrowing to exactly what is declared is legal, and is how a reality freezes
/// its own vocabulary against later layers. The accepting twin of the above, and
/// the reason `BelowDeclared` uses `<` rather than `<=`.
#[test]
fn narrowing_to_exactly_what_is_declared_freezes_the_space() {
    let frozen = resolve(&[
        layer(Layer::Preset, "quantities = [\"a\", \"b\", \"c\"]\n"),
        layer(Layer::Reality, "[limits]\nquantities = 3\n"),
    ])
    .expect("narrowing to exactly the declared count is legal");
    assert_eq!(frozen.quantities.len(), 3);

    // ...and a space frozen at its current size admits no further row. This is
    // the half that makes "exactly" mean something: a `<=` in `BelowDeclared`
    // would pass the assertion above and this one would still catch it, because
    // a limit that silently became 4 would let `d` in.
    let err = resolve(&[
        layer(Layer::Preset, "quantities = [\"a\", \"b\", \"c\"]\n"),
        layer(Layer::Reality, "quantities = [\"d\"]\n[limits]\nquantities = 3\n"),
    ])
    .expect_err("a frozen space admits no further rows");
    assert!(
        matches!(&err, LoadError::Limit { source: LimitError::AtLimit { row, .. }, .. } if row == "d"),
        "expected `d` to be refused by the frozen space, got {err}"
    );
}

/// **`deny_unknown_fields` reaches the new block too.**
///
/// Written because it is the one property of `[limits]` that is inherited
/// rather than authored, and an inherited guarantee is `NV-4` waiting to
/// happen: it holds only while the attribute happens to be on the struct. A
/// misspelled ceiling that silently did nothing would be the worst possible
/// failure of this feature — the author would see their limit ignored and
/// conclude limits do not work.
#[test]
fn a_misspelled_limits_key_is_refused_rather_than_ignored() {
    let err = parse_layer(Layer::Reality, "[limits]\nquantites = 3\n")
        .expect_err("a misspelling must not be silently dropped");
    let msg = format!("{err}");
    assert!(msg.contains("quantites"), "must name the bad key: {msg}");
    assert!(msg.contains("quantities"), "must name the keys that DO exist: {msg}");
}

/// **A layer raises its own ceiling and uses the room in the SAME file.**
///
/// This is why `[limits]` is applied before the rows of its own layer. Applying
/// it after would refuse the most natural thing an author writes, and the bug
/// would look like the limit "not working".
#[test]
fn a_layer_may_widen_and_spend_the_room_in_one_file() {
    let r = resolve(&[
        layer(Layer::Preset, "quantities = [\"a\", \"b\"]\n[limits]\nquantities = 2\n"),
        layer(Layer::Reality, "quantities = [\"c\", \"d\"]\n[limits]\nquantities = 4\n"),
    ])
    .expect("a layer sees its own raise");
    assert_eq!(r.quantities.len(), 4);
}

// ── the three spaces are independent ────────────────────────────────────────

/// A limit on one space must not be read as a limit on another. Written because
/// `Limits` is an array indexed by a `#[repr(usize)]` enum, and an off-by-one in
/// that indexing would be invisible in every single-space test above.
#[test]
fn each_space_is_limited_independently() {
    for space in OrdinalSpace::ALL {
        let mut l = Limits::CAPACITY;
        l.declare(space, 1, 0).expect("1 is under every capacity");
        for other in OrdinalSpace::ALL {
            let expected = if other == space { 1 } else { other.capacity() };
            assert_eq!(
                l.get(other),
                expected,
                "declaring {space} moved {other}"
            );
        }
    }
}

/// A resource row is limited by the RESOURCE space, not by the quantity space
/// that shares its capacity number. The two are aliases in the binary
/// (`MAX_DECLARED_RESOURCES = MAX_DECLARED_QUANTITIES`), which is exactly the
/// coincidence that would hide a wrong space here.
#[test]
fn a_resource_row_is_limited_by_the_resource_space() {
    let src = "quantities = [\"a\", \"b\"]\n\
               [limits]\nresources = 1\n\
               [[resources]]\nquantity = \"a\"\nmin = 0\nbase = 1\nceiling_fixed = 1\n\
               regen_type = \"none\"\nzero_behaviour = \"clamp\"\n\
               [[resources]]\nquantity = \"b\"\nmin = 0\nbase = 1\nceiling_fixed = 1\n\
               regen_type = \"none\"\nzero_behaviour = \"clamp\"\n";
    let err = resolve(&[layer(Layer::Preset, src)]).expect_err("the second pool must not fit");
    let LoadError::Limit { source: LimitError::AtLimit { space, row, .. }, .. } = &err else {
        panic!("expected AtLimit, got {err}");
    };
    assert_eq!(*space, OrdinalSpace::Resources, "a pool is limited as a RESOURCE");
    assert_eq!(row, "b");
}

// ── what a limit must NOT touch ─────────────────────────────────────────────

/// **`RLS-A15`'s precedent, applied: a declared size is not part of the rules.**
///
/// Two realities with identical rows and different `[limits]` produce the same
/// numbers for every actor, so they are the same rules and must intern under one
/// digest. The alternative would move every existing reality's digest to record
/// a number no law reads.
#[test]
fn a_limit_does_not_move_the_digest() {
    let rows = |limits: &str| preset_with(limits, &["gather"]);
    let tight = resolve(&[layer(Layer::Preset, &rows("[limits]\nverbs = 1\n"))]).expect("tight");
    let loose = resolve(&[layer(Layer::Preset, &rows("[limits]\nverbs = 9\n"))]).expect("loose");
    let none = resolve(&[layer(Layer::Preset, &rows(""))]).expect("unlimited");

    assert_eq!(tight.digest(), loose.digest(), "a ceiling is not a rule");
    assert_eq!(tight.digest(), none.digest(), "declaring one changes no reality's identity");

    // ...and the guard against this test being vacuous: a row DOES move it.
    let more = resolve(&[layer(Layer::Preset, &preset_with("", &["gather", "brace"]))])
        .expect("two verbs");
    assert_ne!(tight.digest(), more.digest(), "a ROW is a rule");
}
