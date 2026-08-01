//! F2 verification — the artifact, the fold, the validators and the store.

use ruleset_core::{Ruleset, RulesetDigest};
use ruleset_loader::{
    engine_default_from_artifact, parse_layer, resolve, validate, Layer, LoadError, RulesetStore,
    StoreError, ValidationError,
};

// ── V1 · RLS-D2: the artifact IS the default ────────────────────────────────

/// The shipped `engine_default.toml` must resolve to exactly the same ruleset
/// the `const fn` produces — same digest, not merely "the same numbers".
///
/// **This is what makes RLS-D2 real.** Every feature document states its own
/// defaults, which made *"omit the field → the feature default applies"*
/// unverifiable. Now the claim is an assertion. The `const fn` stays as the
/// bootstrap floor (a node must boot with no filesystem); this test is what
/// stops the two drifting apart in silence — which they would, the first time
/// someone tunes one and forgets the other.
#[test]
fn v1_engine_default_artifact_matches_the_code() {
    let from_file = engine_default_from_artifact().expect("the shipped artifact must load");
    let from_code = Ruleset::engine_default();
    assert_eq!(
        from_file.digest().to_hex(),
        from_code.digest().to_hex(),
        "engine_default.toml and Ruleset::engine_default() have drifted apart — \
         one of them was edited without the other"
    );
    assert_eq!(from_file, from_code);
}

/// …and the artifact must be TOTAL, which the test above cannot see.
///
/// **This was a hole in the test one commit earlier.** `engine_default.toml` is
/// applied as a PATCH over `Ruleset::engine_default()`, so a field deleted from
/// the file just inherits the `const fn` and the digest comparison still
/// passes. The artifact could be half empty and "match the code" — proven by
/// deleting `hit_base_pm` and watching the suite stay green.
///
/// Only the `engine_default` layer is required to be total; every other layer
/// is a partial override by design. `missing_fields` is built on exhaustive
/// destructuring, so a new rules field cannot quietly shrink what total means.
#[test]
fn v1_engine_default_artifact_declares_every_field() {
    let patch = parse_layer(Layer::EngineDefault, ruleset_loader::ENGINE_DEFAULT_TOML)
        .unwrap()
        .patch;
    let missing = patch.missing_fields();
    assert!(
        missing.is_empty(),
        "engine_default.toml is the layer that must declare EVERYTHING — a field          omitted here silently inherits the const fn, so the artifact stops being          the source of truth it claims to be. Undeclared: {missing:?}"
    );
}

// ── V5 · the layer fold ─────────────────────────────────────────────────────

#[test]
fn v5_no_layers_folds_to_the_engine_default() {
    let r = resolve(&[]).expect("an empty stack is the engine default, not an error");
    assert_eq!(r, Ruleset::engine_default());
}

#[test]
fn v5_an_empty_patch_is_an_identity() {
    let empty = parse_layer(Layer::Reality, "").unwrap();
    assert!(empty.patch.is_empty());
    assert_eq!(resolve(&[empty]).unwrap(), Ruleset::engine_default());
}

#[test]
fn v5_a_higher_layer_wins_regardless_of_slice_order() {
    let preset = parse_layer(Layer::Preset, "[combat]\nmax_hit = 500\n").unwrap();
    let reality = parse_layer(Layer::Reality, "[combat]\nmax_hit = 999\n").unwrap();

    // Deliberately passed in the WRONG order: `resolve` sorts by priority, so a
    // caller cannot accidentally invert the stack. An ordering contract that
    // depends on callers is the kind nobody sees violated in a diff.
    let a = resolve(&[reality.clone(), preset.clone()]).unwrap();
    let b = resolve(&[preset, reality]).unwrap();
    assert_eq!(a, b, "the fold must not depend on the order the caller passed");
    assert_eq!(a.combat.max_hit, 999, "the reality layer outranks the preset");
}

#[test]
fn v5_layers_compose_across_disjoint_fields() {
    let preset = parse_layer(Layer::Preset, "[combat]\nmax_hit = 500\n").unwrap();
    let reality = parse_layer(Layer::Reality, "[stats]\nmove_max = 7\n").unwrap();
    let r = resolve(&[preset, reality]).unwrap();
    assert_eq!(r.combat.max_hit, 500);
    assert_eq!(r.stats.move_max, 7);
    // …and everything untouched still comes from the engine default.
    assert_eq!(r.combat.hit_base_pm, Ruleset::engine_default().combat.hit_base_pm);
}

#[test]
fn v5_a_different_ruleset_has_a_different_digest() {
    let reality = parse_layer(Layer::Reality, "[combat]\nmax_hit = 500\n").unwrap();
    let r = resolve(&[reality]).unwrap();
    assert_ne!(
        r.digest(),
        Ruleset::engine_default().digest(),
        "authoring a reality with different rules must produce a different pin — \
         this is the whole point of F2"
    );
}

/// A misspelled key must be an ERROR, never a silent no-op.
///
/// This is the single most likely authoring mistake, and serde's default is to
/// ignore it — so the author's edit does nothing while they tune the number
/// that had no effect, twice, before suspecting the file. Same reasoning as
/// RLS-A5's rule that a tombstone against a missing ID is a load error.
#[test]
fn a_misspelled_key_is_refused_not_ignored() {
    let err = parse_layer(Layer::Reality, "[combat]\nmax_hitt = 500\n").unwrap_err();
    assert!(matches!(err, LoadError::Parse { .. }), "got {err}");
    assert!(format!("{err}").contains("max_hitt"), "the diagnostic must name the key");

    // …and a misspelled TABLE too.
    assert!(matches!(
        parse_layer(Layer::Reality, "[combatt]\nmax_hit = 500\n"),
        Err(LoadError::Parse { .. })
    ));
}

/// …and the diagnostic must carry the LINE, which is the whole reason the
/// refusal above is worth having.
///
/// **This test exists because the property was silently destroyed and nothing
/// noticed.** S1a's forbidden-key check parsed the document to a `toml::Value`
/// and then deserialized the patch *from that value*, which looks free and
/// drops every span — `toml` anchors spans to the source text, so `Value -> T`
/// can only say *"unknown field `max_hitt` in `combat`"*.
///
/// The test above stayed green the whole time: it asserts the key NAME appears,
/// and it did. An author fixing a typo in a 200-line preset would have been
/// handed a message with no line number, in a module whose doc justifies the
/// entire refusal by *"turning twenty minutes of confusion into one line of
/// diagnostic"*. Found by `/review-impl`, not by the suite.
#[test]
fn a_bad_key_is_reported_with_its_line_and_the_source_text() {
    let src = "[combat]\nmax_hit = 500\nhit_base_pm = 500\nmax_hitt = 9\n";
    let msg = format!("{}", parse_layer(Layer::Reality, src).unwrap_err());
    assert!(
        msg.contains("line 4"),
        "the diagnostic lost its line number — an author cannot find the key: {msg}"
    );
    assert!(
        msg.contains("max_hitt = 9"),
        "the diagnostic lost the offending SOURCE LINE: {msg}"
    );
}

// ── V6 · the validators (RLS-A10) ───────────────────────────────────────────

fn bad(toml: &str) -> Vec<ValidationError> {
    match resolve(&[parse_layer(Layer::Reality, toml).expect("parses")]) {
        Err(LoadError::Invalid(errs)) => errs,
        other => panic!("expected a validation failure, got {other:?}"),
    }
}

/// Each of the six load-time rules refuses its own bad ruleset.
///
/// Every one of these is *also* guarded at runtime in the laws. Both stay: the
/// runtime floor keeps a bad ruleset PREDICTABLE (including one stored before
/// this validator existed, which RLS-D18 forbids re-validating), and the
/// validator stops one being STORED. Deleting the runtime floors "because the
/// loader checks now" would break exactly the old-artifact case.
#[test]
fn v6_each_validator_refuses_its_own_bad_ruleset() {
    assert!(matches!(
        bad("[combat]\nhit_floor_pm = 900\nhit_ceiling_pm = 100\n")[..],
        [ValidationError::HitClampInverted { floor_pm: 900, ceiling_pm: 100 }]
    ));
    assert!(matches!(
        bad("[combat]\nroll_band_lo_pm = 1000\nroll_band_hi_pm = 900\n")[..],
        [ValidationError::RollBandInverted { .. }]
    ));
    assert!(matches!(
        bad("[combat]\ndefend_divisor = 0\n")[..],
        [ValidationError::DefendDivisorTooSmall { found: 0 }]
    ));
    assert!(matches!(
        bad("[stats]\nmove_speed_per_tile = 0\n")[..],
        [ValidationError::MoveSpeedPerTileTooSmall { found: 0 }]
    ));
    assert!(matches!(
        bad("[stats]\nmove_max = 0\n")[..],
        // move_max = 0 trips BOTH "too small" and "base exceeds max" — which is
        // the point of collecting all errors rather than the first.
        [ValidationError::MoveMaxTooSmall { found: 0 }, ValidationError::MoveBaseExceedsMax { .. }]
    ));
    assert!(matches!(
        bad("[stats]\nmove_base = 50\n")[..],
        [ValidationError::MoveBaseExceedsMax { base: 50, max: 10 }]
    ));

    // The engine default passes — otherwise the suite above proves nothing.
    validate(&Ruleset::engine_default()).expect("the engine default must be loadable");
}

#[test]
fn v6_all_problems_are_reported_not_just_the_first() {
    let errs = bad("[combat]\ndefend_divisor = 0\n\n[stats]\nmove_speed_per_tile = 0\n");
    assert_eq!(
        errs.len(),
        2,
        "an author fixing one number per round trip is how a validator earns the \
         reputation that gets it bypassed"
    );
}

// ── V4 · the store ──────────────────────────────────────────────────────────

fn tmp_store(name: &str) -> RulesetStore {
    let dir = std::env::temp_dir().join(format!("loreweave-ruleset-store-{name}"));
    let _ = std::fs::remove_dir_all(&dir);
    RulesetStore::new(dir)
}

#[test]
fn v4_put_then_get_round_trips_and_is_idempotent() {
    let store = tmp_store("roundtrip");
    let mut r = Ruleset::engine_default();
    r.combat.max_hit = 4242;

    let d1 = store.put(&r).unwrap();
    let d2 = store.put(&r).unwrap();
    assert_eq!(d1, d2, "content addressing makes a re-put a no-op");
    assert_eq!(d1, r.digest());
    assert!(store.contains(&d1));

    let back = store.get(&d1).unwrap().expect("stored");
    assert_eq!(back, r);
    assert_eq!(back.digest(), d1);

    // An unstored digest is None, not an error — "not here" and "here but
    // wrong" are different situations and must not share a return.
    assert!(store.get(&Ruleset::engine_default().digest()).unwrap().is_none());
}

/// A content-addressed store that trusts its own filenames is not
/// content-addressed — it is a directory with suggestive names.
///
/// Tamper with the bytes and it must REFUSE, because serving a substituted
/// ruleset under the right digest is precisely the attack the digest exists to
/// detect. Silent here would defeat F3 before F3 is written.
#[test]
fn v4_a_tampered_file_is_refused() {
    let store = tmp_store("tamper");
    let mut r = Ruleset::engine_default();
    r.combat.max_hit = 777;
    let digest = store.put(&r).unwrap();

    // Rewrite the file under the SAME name with different rules.
    let mut evil = Ruleset::engine_default();
    evil.combat.max_hit = 1; // a reality where everything dies instantly
    let path = std::env::temp_dir()
        .join("loreweave-ruleset-store-tamper")
        .join(format!("{}.canon", digest.to_hex()));
    std::fs::write(&path, evil.canon_bytes()).unwrap();

    let err = store.get(&digest).unwrap_err();
    assert!(
        matches!(err, StoreError::DigestMismatch { .. }),
        "a store that serves whatever is under the right filename provides no \
         guarantee at all; got {err}"
    );
    assert!(format!("{err}").contains("CORRUPTION"));
}

#[test]
fn v4_garbage_in_the_store_is_malformed_not_a_panic() {
    let store = tmp_store("garbage");
    store.ensure_root().unwrap();
    let digest = RulesetDigest([7u8; 32]);
    let path = std::env::temp_dir()
        .join("loreweave-ruleset-store-garbage")
        .join(format!("{}.canon", digest.to_hex()));
    std::fs::write(&path, b"not a canonical ruleset").unwrap();

    assert!(matches!(store.get(&digest), Err(StoreError::Malformed(_))));
}

/// The store is what makes a HISTORICAL ruleset resolvable — the thing
/// `Island::restore`'s refusal and F3's replay check both need, and the thing
/// that does not exist while `engine_default()` is compiled into the binary.
#[test]
fn v4_two_rulesets_coexist_and_stay_distinguishable() {
    let store = tmp_store("coexist");
    let mut old = Ruleset::engine_default();
    old.combat.max_hit = 1_000;
    let mut new = Ruleset::engine_default();
    new.combat.max_hit = 2_000;

    let d_old = store.put(&old).unwrap();
    let d_new = store.put(&new).unwrap();
    assert_ne!(d_old, d_new);

    // Six months later, replay asks for the OLD rules by digest and gets them —
    // not whatever this binary happens to have compiled in.
    assert_eq!(store.get(&d_old).unwrap().unwrap().combat.max_hit, 1_000);
    assert_eq!(store.get(&d_new).unwrap().unwrap().combat.max_hit, 2_000);
}

/// Doc 26 §6's F2 exit criterion, taken literally: **from a FILE.**
///
/// The tests above parse from strings, which exercises the algebra but not the
/// path a reality actually takes. This one writes a `.toml` to disk and reads
/// it back through `read_layer`, so a broken file-reading path cannot hide
/// behind a green in-memory suite.
#[test]
fn a_reality_loads_its_ruleset_from_a_file_and_the_digest_follows() {
    let dir = std::env::temp_dir().join("loreweave-f2-file");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("reality.toml");
    std::fs::write(
        &path,
        "# a grittier reality\n[combat]\nmax_hit = 250\n\n[stats]\nmove_max = 4\n",
    )
    .unwrap();

    let layer = ruleset_loader::read_layer(Layer::Reality, &path).expect("reads from disk");
    let r = resolve(&[layer]).expect("loads");
    assert_eq!(r.combat.max_hit, 250);
    assert_eq!(r.stats.move_max, 4);
    assert_ne!(r.digest(), Ruleset::engine_default().digest());

    // …and it survives the store, which is what a later replay resolves from.
    let store = tmp_store("from-file");
    let d = store.put(&r).unwrap();
    assert_eq!(store.get(&d).unwrap().unwrap(), r);

    // A missing file is an Io error naming the layer, not a panic.
    assert!(matches!(
        ruleset_loader::read_layer(Layer::Reality, &dir.join("nope.toml")),
        Err(LoadError::Io { layer: Layer::Reality, .. })
    ));
}

// ── V6 · QTY-A11 — an artifact written before the last schema bump still loads ─

/// **The store must be able to read its own history.**
///
/// `get` verifies content against name by RE-ENCODING the decoded value, which
/// is deliberately stricter than hashing the raw bytes — it checks the decoder
/// too. But re-encoding an OLD artifact at the CURRENT layout produces different
/// bytes and a different digest, so a naive version of that check reports the
/// store's own file as corrupt and turns every pre-bump reality `Unloadable`.
///
/// That is not hypothetical: it is what the first draft of QTY-A11 would have
/// caused, and the axiom's whole purpose was to prevent exactly that outcome.
/// `digest_at(source_version)` is the fix, and this is the test that says so.
///
/// The v1 bytes here come from the frozen v1 encoder rather than a hand-written
/// fixture — a byte array would test my typing, not the codec.
#[test]
fn a_v1_artifact_survives_put_and_get() {
    let store = tmp_store("v1-artifact");

    let mut rules = Ruleset::engine_default();
    rules.combat.max_hit = 4242;
    let v1_bytes = rules.canon_bytes_at(1).expect("v1 codec exists");
    // Digest the v1 bytes the same way the store will, via the codec itself.
    let v1_digest = rules.digest_at(1).expect("v1 codec exists");

    // Write the artifact the way F2 wrote it before the bump: raw bytes under
    // their own digest. `put` would encode at the CURRENT version, which is a
    // different file — this is the pre-existing one.
    store.ensure_root().expect("root");
    std::fs::write(
        store.path_for(&v1_digest),
        &v1_bytes,
    )
    .expect("place the historical artifact");

    let loaded = store.get(&v1_digest).expect("v1 artifact verifies").expect("present");
    assert_eq!(loaded.combat.max_hit, 4242, "the rules must survive");
    assert_eq!(
        loaded.law_version,
        ruleset_core::LAW_VERSION_UNVERSIONED,
        "and it must still say it makes no claim about the laws"
    );

    // The upcast value's CURRENT digest is a different artifact — QTY-D14. That
    // is why moving a reality onto it is an epoch switch and not a side effect.
    assert_ne!(loaded.digest(), v1_digest);
    assert!(!store.contains(&loaded.digest()), "and it is not in the store until someone puts it");
}
