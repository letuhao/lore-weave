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

use ruleset_core::{CanonEncode, Ruleset};

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

fn hex(d: &[u8; 32]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect()
}

fn blake3_of(bytes: &[u8]) -> [u8; 32] {
    *blake3::hash(bytes).as_bytes()
}


/// A `v1` artifact — written before `law_version` existed — loads on this
/// engine, and arrives in the CURRENT shape so no caller branches on layout.
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

// ═══════════════════════════════════════════════════════════════════════════
// Moved here from `digest.rs` on 2026-07-30, when `Q2`'s repin-log entry pushed
// that file past its IMP-D3 ceiling. The seam is the right one and predates the
// line count: `digest.rs` proves WHAT IS IN THE BYTES (the golden pin, the
// per-field perturbation, provenance staying out); everything below proves the
// DECODER reads those bytes back — which is versioning's subject, not the
// digest's. Q1 had already split this file out for exactly that reason.

// ── V2/V3 · the decoder (F2) ────────────────────────────────────────────────

/// A tiny deterministic PRNG so the round trip covers ARBITRARY rulesets, not
/// the one default the golden test pins. SplitMix64, same family as `DetRng` —
/// no dependency, and a failure reproduces exactly from its seed.
fn rand_ruleset(seed: u64) -> Ruleset {
    let mut z = seed;
    let mut next = || {
        z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut x = z;
        x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        x ^ (x >> 31)
    };
    let mut r = Ruleset::engine_default();
    let c = &mut r.combat;
    // Full i64 range INCLUDING negatives: `resist_pm` is legitimately negative
    // in a ruleset granting vulnerability, and a decoder that read the two's
    // complement wrong would pass a positives-only round trip.
    for f in [
        &mut c.hit_base_pm, &mut c.hit_floor_pm, &mut c.hit_ceiling_pm,
        &mut c.roll_band_lo_pm, &mut c.roll_band_hi_pm, &mut c.elem_mult_pm,
        &mut c.resist_pm, &mut c.defend_divisor, &mut c.max_hit,
        &mut c.av_base, &mut c.av_slowed_pm, &mut c.av_hasted_pm,
        &mut c.av_stunned_pm, &mut c.av_initiator_first_pm,
    ] {
        *f = next() as i64;
    }
    c.ko_duration_rounds = next() as u8;
    let s = &mut r.stats;
    for slot in s.slot_defaults.iter_mut().chain(s.melee_archetype.iter_mut()) {
        *slot = next() as i32;
    }
    s.move_base = next() as i32;
    s.move_speed_per_tile = next() as i32;
    s.move_max = next() as i32;
    r
}

/// **The mechanism that holds the encoder and decoder together.**
///
/// `canon` is spelled twice — once forward, once back — in one language with no
/// compiler checking the correspondence, which is the same shape as the Go/Rust
/// envelope mirror. Exhaustive destructuring guards the ENCODE side only. This
/// is what guards the pair, and it does it over arbitrary values rather than
/// the single default `v1` pins.
#[test]
fn v2_canon_round_trips_for_arbitrary_rulesets() {
    for seed in 0..256u64 {
        let a = rand_ruleset(seed);
        let bytes = a.canon_bytes();
        let b = Ruleset::from_canon_bytes(&bytes)
            .unwrap_or_else(|e| panic!("seed {seed}: decode failed: {e}"));
        assert_eq!(a, b, "seed {seed}: round trip changed the ruleset");
        assert_eq!(a.digest(), b.digest(), "seed {seed}: digest moved across a round trip");
        assert_eq!(b.canon_bytes(), bytes, "seed {seed}: re-encoding is not byte-identical");
    }
}

#[test]
fn v3_decoder_refuses_rather_than_guesses() {
    let good = Ruleset::engine_default().canon_bytes();
    assert!(Ruleset::from_canon_bytes(&good).is_ok());

    // TRAILING BYTES — the one a lenient decoder swallows. A prefix that
    // decodes cleanly is the most dangerous possible failure: it produces a
    // plausible ruleset from an artifact that is not one.
    let mut extra = good.clone();
    extra.push(0);
    assert!(
        matches!(
            Ruleset::from_canon_bytes(&extra),
            Err(ruleset_core::CanonError::TrailingBytes { .. })
        ),
        "a decoder that tolerates trailing bytes will read a truncated artifact \
         into something plausible"
    );

    // TRUNCATED
    assert!(matches!(
        Ruleset::from_canon_bytes(&good[..good.len() - 1]),
        Err(ruleset_core::CanonError::ShortRead { .. })
    ));

    // WRONG DOMAIN — a stream of some other artifact with a compatible layout.
    let mut c = ruleset_core::Canon::new("loreweave.somethingelse.v1");
    Ruleset::engine_default().canon(&mut c);
    assert!(matches!(
        Ruleset::from_canon_bytes(&c.finish()),
        Err(ruleset_core::CanonError::WrongDomain { .. })
    ));

    // UNKNOWN SCHEMA VERSION — refused, never read with this build's offsets.
    let mut future = Ruleset::engine_default();
    future.schema_version = ruleset_core::RULESET_SCHEMA_VERSION + 1;
    assert!(matches!(
        Ruleset::from_canon_bytes(&future.canon_bytes()),
        Err(ruleset_core::CanonError::UnknownSchemaVersion { .. })
    ));

    // EMPTY
    assert!(Ruleset::from_canon_bytes(&[]).is_err());
}
