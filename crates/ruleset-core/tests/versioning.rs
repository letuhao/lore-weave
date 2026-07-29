//! `QTY-A11` — the version machinery, and the proof it is not vacuous.
//!
//! Split out of `digest.rs` 2026-07-29 (`Q1`), because the IMP-D3 ceiling gate
//! reddened on that file **for the right reason**: its repin log accretes an
//! entry per schema change, so it grows every time this machinery is exercised.
//! Bumping its allowlisted size on first contact would have made the gate's
//! "allowlisted debt that GROWS reds again" rule theatre, one slice after that
//! rule was written.
//!
//! Version dispatch is also a distinct concern from "does the digest cover this
//! field": these tests ask whether an OLD artifact still loads, which is a
//! property of the codec set rather than of the hash.

use ruleset_core::{Ruleset, RULESET_SCHEMA_VERSION, SCHEMA_VERSION_OLDEST};

// ── V6 · QTY-A11 — the version machinery, and the proof it is not vacuous ────
//
// The whole point of a version dispatch is that an artifact written BEFORE a
// field existed still loads. That claim is untestable while there is only one
// version, which is why `LAW_VERSION` (QTY-D13) was chosen as the first
// migration rather than a hypothetical one: it makes `v1` a real thing that
// really exists, so every test below reads bytes no current encoder produces.
//
// Note none of these fabricate a fixture by hand. `canon_bytes_at(1)` IS the
// frozen v1 encoder — the same code path `RulesetStore::get` verifies with. A
// hand-written byte array would test my typing, not the codec.

/// A `v1` artifact — written before `law_version` existed — loads on this
/// engine, and arrives in the CURRENT shape so no caller branches on layout.

fn hex(d: &[u8; 32]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect()
}

fn blake3_of(bytes: &[u8]) -> [u8; 32] {
    *blake3::hash(bytes).as_bytes()
}


#[test]
fn a_v1_artifact_loads_on_a_v2_engine() {
    let mut original = Ruleset::engine_default();
    original.combat.max_hit = 4242;

    let v1_bytes = original.canon_bytes_at(1).expect("v1 codec exists");
    assert_ne!(
        v1_bytes,
        original.canon_bytes(),
        "the v1 layout must differ from v2, or this test proves nothing"
    );

    let (loaded, src) = Ruleset::from_canon_bytes_versioned(&v1_bytes).expect("v1 decodes");
    assert_eq!(src, 1, "the source version must be reported, not assumed");
    assert_eq!(loaded.schema_version, ruleset_core::RULESET_SCHEMA_VERSION,
               "upcast: the caller always receives the current shape");
    assert_eq!(loaded.combat.max_hit, 4242, "the rules must survive the upcast");
}

/// **The property `RulesetStore::get` stands on**, and the one the first draft
/// of QTY-A11 would have broken: a decoded-then-upcast ruleset must re-encode
/// at its ORIGINAL version to the exact original bytes.
///
/// Without it, `get` re-digests an old artifact at the current layout, gets a
/// different hash, and reports the store's own file as corrupt — turning every
/// pre-bump reality `Unloadable`, which is the outcome the growth path exists
/// to prevent.
#[test]
fn a_v1_artifact_re_encodes_to_exactly_its_original_bytes() {
    let mut original = Ruleset::engine_default();
    original.combat.max_hit = 4242;
    let v1_bytes = original.canon_bytes_at(1).unwrap();

    let (loaded, src) = Ruleset::from_canon_bytes_versioned(&v1_bytes).unwrap();

    assert_eq!(loaded.canon_bytes_at(src).unwrap(), v1_bytes,
               "re-encoding at the source version is not byte-identical");
    assert_eq!(hex(&loaded.digest_at(src).unwrap().0), hex(&blake3_of(&v1_bytes)),
               "digest_at(source) must reproduce the digest the file was filed under");
    assert_ne!(hex(&loaded.digest().0), hex(&blake3_of(&v1_bytes)),
               "and the CURRENT digest must differ — QTY-D14: the upcast is a new \
                artifact B2/D2, which is why moving a binding to it is an epoch switch \
                rather than something that can happen silently");
}

/// Forward compatibility stays impossible, on purpose. Reading a newer artifact
/// with older field offsets would be reinterpretation of the worst kind:
/// silent, and numerically plausible.
#[test]
fn a_future_schema_version_is_refused() {
    let mut bytes = Ruleset::engine_default().canon_bytes();
    // The schema version is the first u32 after the domain tag. Rewrite it to a
    // version this engine cannot know.
    let tag_len = "loreweave.ruleset.v1".len();
    let off = tag_len + 4; // length-prefixed tag
    bytes[off..off + 4].copy_from_slice(&99u32.to_be_bytes());

    let err = Ruleset::from_canon_bytes(&bytes).unwrap_err();
    assert!(format!("{err:?}").contains("UnknownSchemaVersion"), "{err:?}");
}

/// A version below the oldest frozen codec is equally a refusal — "we used to
/// be able to read this" is not the same as "we can".
#[test]
fn a_version_below_the_oldest_codec_is_refused() {
    assert!(Ruleset::engine_default().canon_bytes_at(0).is_none());
    assert!(Ruleset::engine_default()
        .canon_bytes_at(ruleset_core::RULESET_SCHEMA_VERSION + 1)
        .is_none());
}

/// **QTY-D13 non-vacuity.** `law_version` must actually reach the hash — a
/// field that is stored but not encoded is precisely the "covers less than it
/// appears to" failure this whole suite exists for, and it is what the digest
/// did for the laws until now.
#[test]
fn law_version_is_inside_the_hashed_bytes() {
    let a = Ruleset::engine_default();
    let mut b = a.clone();
    b.law_version += 1;

    assert_ne!(a.digest(), b.digest(),
               "two identical rulesets under DIFFERENT LAWS hash the same — the pin \
                is covering the config and calling it the rules");
    assert_ne!(a.canon_bytes(), b.canon_bytes(), "…and so must their canonical bytes");
}

/// An upcast records what the artifact ran under, and does NOT adopt the
/// engine's current laws. Overwriting it would erase the one fact the field
/// exists to carry, and would do it silently.
#[test]
fn an_upcast_does_not_claim_the_current_law_version() {
    let v1_bytes = Ruleset::engine_default().canon_bytes_at(1).unwrap();
    let (loaded, _) = Ruleset::from_canon_bytes_versioned(&v1_bytes).unwrap();

    assert_eq!(loaded.law_version, ruleset_core::LAW_VERSION_UNVERSIONED,
               "a pre-LAW_VERSION artifact asserts nothing about the laws; it must not \
                be made to assert the CURRENT ones");
    assert_ne!(loaded.law_version, ruleset_core::LAW_VERSION,
               "if these are ever equal this test is vacuous — LAW_VERSION must not be 0");
}
