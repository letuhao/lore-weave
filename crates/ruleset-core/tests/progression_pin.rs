//! `S-1b` — the progression pin on `Ruleset`, and the properties it has to have
//! for `Q0b B3`'s epoch switch to carry a progression change unchanged.
//!
//! Split from `progression.rs` at `IMP-D3`'s 400-line ceiling. The seam: that
//! file tests the TABLE, this one tests the POINTER to it.

mod common;
use common::*;

use ruleset_core::{
    ProgressionDigest, ProgressionTable, Ruleset, RULESET_SCHEMA_VERSION,
};
/// The engine declares no progression, and says so as `None` — **never a zero
/// digest**. `zero-digest-gate` exists because `RulesetDigest([0u8; 32])`
/// shipped in 15 places and *"looks like a value"*; `Option` puts the
/// distinction in the type system instead of in a convention.
#[test]
fn the_engine_default_declares_no_progression_as_none() {
    assert_eq!(Ruleset::engine_default().progression, None);
    assert_eq!(RULESET_SCHEMA_VERSION, 5);
}

/// **The property the whole placement rests on.** Editing a tier ladder moves
/// the progression digest, which moves the RULESET digest — which is what lets
/// `Q0b B3`'s epoch switch carry a progression change with no second hash on
/// the binding and no new version axis.
#[test]
fn pinning_a_progression_table_moves_the_ruleset_digest() {
    let bare = Ruleset::engine_default();
    let mut pinned = Ruleset::engine_default();
    pinned.progression = Some(fixture_table().digest());
    assert_ne!(bare.digest(), pinned.digest());

    let mut edited = Ruleset::engine_default();
    let mut k = nei_gong();
    k.tiers[1].tier_max += 1;
    edited.progression =
        Some(ProgressionTable::declare(vec![k, jian_shu(), wu_xing()]).unwrap().digest());
    assert_ne!(
        pinned.digest(),
        edited.digest(),
        "a one-unit tier edit must move the reality's digest, or a ladder change could \
         ride into a live world with nothing going red"
    );
}

#[test]
fn a_pinned_ruleset_survives_encode_decode() {
    let mut r = Ruleset::engine_default();
    r.progression = Some(fixture_table().digest());
    let (back, v) = Ruleset::from_canon_bytes_versioned(&r.canon_bytes()).unwrap();
    assert_eq!(v, 5);
    assert_eq!(back.progression, r.progression);
    assert_eq!(back.digest(), r.digest());
}

/// `QTY-A11` — a v4 artifact predates the pin, so it decodes to `None` rather
/// than to a guess, and **re-encodes at v4 to exactly its original bytes**.
/// That round-trip is what makes `digest_at` meaningful for a store checking a
/// name it did not choose.
#[test]
fn a_v4_artifact_decodes_to_none_and_re_encodes_unchanged() {
    let r = Ruleset::engine_default();
    let v4 = r.canon_bytes_at(4).expect("v4 is a known version");
    let (back, v) = Ruleset::from_canon_bytes_versioned(&v4).unwrap();
    assert_eq!(v, 4);
    assert_eq!(back.progression, None, "an artifact from before S-1b declared none");
    assert_eq!(back.canon_bytes_at(4).unwrap(), v4, "the upcast must be purely ADDITIVE");
    assert_ne!(
        back.canon_bytes_at(5).unwrap(),
        v4,
        "and v5 must differ, or the presence byte is not actually written"
    );
}

/// **`D-PROGRESSION-EMPTY-PIN` — CLOSED by `PGN-R2a`.**
///
/// `None` and `Some(digest_of_an_empty_table)` are the same *behavioural* state
/// — this reality has no progression kinds — under two different pins. One set
/// of rules with two digests is what `RLS-A13` forbids.
///
/// **This file cannot enforce it.** `ruleset-core` has no store, and the pin is
/// a plain `pub` field, so the refusal has to live on the path that MINTS one.
/// It now does, in `ruleset-loader`: `ProgressionStore::put` refuses an empty
/// table, and `resolve_progression` refuses an empty pin that reached the store
/// by some other route — a rule enforced at exactly one end holds only until
/// someone adds a second end.
///
/// What survives here is the fact those refusals rest on: the two spellings are
/// genuinely **distinguishable**. If they ever collided, the refusals over there
/// would be guarding nothing, and this is what would say so.
#[test]
fn the_two_spellings_of_no_progression_are_distinguishable() {
    let none = Ruleset::engine_default();
    let mut empty = Ruleset::engine_default();
    empty.progression = Some(ProgressionTable::EMPTY.digest());
    assert_eq!(none.progression, None);
    assert_ne!(
        none.digest(),
        empty.digest(),
        "if these ever collide, PGN-R2a's empty-pin refusals are guarding nothing"
    );
    assert_ne!(
        ProgressionTable::EMPTY.digest(),
        // zero-digest-gate: ok — an ASSERTION THAT THE ZERO IS WRONG, not a pin.
        // Nothing is constructed with it; it is the right-hand side of an
        // assert_ne! whose whole job is to prove an empty table's content address
        // is a real hash and not a sentinel. The gate caught this line the moment
        // `ProgressionDigest` joined its type list — which is the gate working,
        // and is why this carries a reason instead of the type being left out.
        ProgressionDigest([0u8; 32]),
        "an empty table still has a real content address - it is not the zero digest,          which is why `None` and not a zero sentinel is the spelling for 'no progression'"
    );
}
