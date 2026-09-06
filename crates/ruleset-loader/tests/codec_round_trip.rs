//! `QTY-A11` — `encode_at(v, decode(b)) == b`, over a ruleset that DECLARES things.
//!
//! Split out of `load.rs` at `IMP-D3`'s ceiling, and the seam is exactly the
//! distinction that made this test necessary: `load.rs` is about the LAYER FOLD
//! (does a higher layer win, is an empty patch an identity, is a bad key
//! refused), and this is about the CODEC (do the bytes survive a round trip at
//! every frozen version). They fail for different reasons.

/// **`QTY-A11` over a POPULATED ruleset — the round-trip the codec tests could
/// not reach.**
///
/// Every existing round-trip test uses `Ruleset::engine_default()`, which
/// declares **zero resources and zero verbs**. So `ResourceTable::canon_at`'s
/// `if version >= ROLE_SINCE` branch and every byte of `VerbTable`'s per-row
/// codec were **never executed by any test**: the engine default's v5 and v6
/// encodings are identical but for the version word, and its v6→v7 growth is a
/// bare length prefix. A cold-start reviewer measured it — changing `ROLE_SINCE`
/// from 6 to 5 reddened nothing.
///
/// That is the *"subject cannot vary"* shape `docs/standards/non-vacuity.md`
/// names first, sitting in the tests that guard a codec change. This runs the
/// property over the shipped preset, which has four role-bearing pools and a
/// verb with both a `requires` and a `spend`.
#[test]
fn the_round_trip_holds_over_a_ruleset_that_actually_declares_things() {
    let r = ruleset_loader::proving_ground().expect("the shipped preset resolves");
    assert!(!r.resources.is_empty(), "a table with no rows cannot exercise a row codec");
    assert!(!r.verbs.is_empty(), "same for verbs — this is the whole point of the test");
    assert!(
        r.resources.rows().iter().any(|x| x.role != ruleset_core::EngineRole::None),
        "at least one role-bearing row, or the v6 role byte is never written"
    );

    for v in ruleset_core::SCHEMA_VERSION_OLDEST..=ruleset_core::RULESET_SCHEMA_VERSION {
        let bytes = r.canon_bytes_at(v).expect("every frozen version has a codec");
        let (back, reported) =
            ruleset_core::Ruleset::from_canon_bytes_versioned(&bytes).expect("decodes");
        assert_eq!(reported, v, "v{v}: the decoder must report the version it read");
        let re = back.canon_bytes_at(v).expect("re-encodes at its own version");
        assert_eq!(
            bytes, re,
            "v{v}: encode_at(v, decode(b)) != b — a stored artifact would re-digest to a \
             different name and RulesetStore::get would reject the store's own bytes"
        );
    }

    // …and the two version gates BITE. A v5 artifact carries no role byte and a
    // v6 one does, so their encodings must differ by more than the version word;
    // same for v6 vs v7 and the verb table. Without this, `ROLE_SINCE` could be
    // moved and nothing would notice.
    let v5 = r.canon_bytes_at(5).unwrap();
    let v6 = r.canon_bytes_at(6).unwrap();
    let v7 = r.canon_bytes_at(7).unwrap();
    assert_eq!(
        v6.len() - v5.len(),
        r.resources.len(),
        "v6 adds exactly one role byte PER DECLARED POOL — {} pools",
        r.resources.len()
    );
    assert!(
        v7.len() > v6.len() + 4,
        "v7 must add more than a bare length prefix: the preset declares {} verb(s), \
         and their rows are the bytes this test exists to reach",
        r.verbs.len()
    );
}
