//! `PGN-A2` — the schema closure is EXPORTED from the side that owns it, and
//! the committed contract cannot drift from the type.
//!
//! The red team's finding this answers, in full: a coverage check computed on
//! the Python side would be *"a second implementation of a Rust type — a mirror
//! nothing forces to agree"*, which is `CPL-A2`'s own objection one tier up. So
//! Rust exports, `contracts/` holds the artifact, and this test is what forces
//! them to agree.
//!
//! Regenerate deliberately with `REGEN_PROGRESSION_SCHEMA=1 cargo test -p
//! ruleset-core --test schema_export`.

use ruleset_core::{
    assert_paths_are_total, required_paths, schema_fingerprint, schema_paths, Askable, BodyOrSoul,
    BreakthroughCondition, CapRule, CurveKind, ProgressionKindDecl, ProgressionType, TierDecl,
    WithinTierCurve,
};

fn contract_path() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../contracts/progression-schema.json")
}

/// Hand-rolled rather than pulling `serde_json` into `ruleset-core` for one
/// artifact. The shape is four keys; a dependency would be the larger change.
fn render() -> String {
    let mut s = String::new();
    s.push_str("{\n");
    s.push_str("  \"_generated_by\": \"cargo test -p ruleset-core --test schema_export\",\n");
    s.push_str("  \"_why\": \"PGN-A2. The pipeline's question set must be ASSERTED total against this list, not assumed so. Rust owns the schema; this file is generated from it; the consuming service reads it and never re-derives it, because a re-derivation is a mirror nothing forces to agree (CPL-A2).\",\n");
    s.push_str(&format!("  \"fingerprint\": \"{}\",\n", schema_fingerprint()));
    s.push_str("  \"paths\": [\n");
    let all = schema_paths();
    for (i, f) in all.iter().enumerate() {
        let (kind, why) = match f.askable {
            Askable::Required => ("required", String::new()),
            Askable::Defaultable(w) => ("defaultable", w.to_string()),
            Askable::Magnitude(w) => ("magnitude", w.to_string()),
        };
        s.push_str(&format!(
            "    {{ \"path\": \"{}\", \"askable\": \"{}\"{} }}{}\n",
            f.path,
            kind,
            if why.is_empty() {
                String::new()
            } else {
                format!(", \"why\": \"{}\"", why.replace('"', "'"))
            },
            if i + 1 == all.len() { "" } else { "," }
        ));
    }
    s.push_str("  ]\n}\n");
    s
}

fn sample() -> ProgressionKindDecl {
    ProgressionKindDecl {
        quantity: 0,
        progression_type: ProgressionType::Stage,
        body_or_soul: BodyOrSoul::Body,
        curve: CurveKind::Stage,
        tiers: vec![TierDecl {
            tier_index: 0,
            tier_max: 10,
            within_tier_curve: WithinTierCurve::Linear { rate_milli: 1000 },
            breakthrough: BreakthroughCondition::AtMax,
            initial_value_on_advance: 0,
        }],
        cap_rule: CapRule::TierBased,
        initial_value: 0,
        initial_tier: Some(0),
        derives_from: None,
    }
}

/// **The totality proof, kept alive by being called.**
///
/// Its VALUE is that it compiles: `assert_paths_are_total` destructures every
/// type in the reachable graph with no `..`, so a new field on
/// `ProgressionKindDecl` or `TierDecl` is a **compile error** until
/// `schema_paths` names it. Calling it is what makes its deletion a test
/// failure rather than a silent gap — the same reason
/// `every_shipped_field_is_classified` calls its own proofs.
#[test]
fn every_reachable_field_has_a_path() {
    assert_paths_are_total(&sample());

    // A second, INDEPENDENT proof of the same property. The destructure catches
    // a field with no path; this catches a path quietly deleted, which the
    // destructure cannot see.
    assert_eq!(
        schema_paths().len(),
        22,
        "the schema closure changed size. If deliberate, update this count AND regenerate \
         contracts/progression-schema.json - a question set is asserted against that file"
    );
    assert_eq!(
        required_paths().len(),
        11,
        "the set of positions the pipeline MUST ask about changed. This is the number a \
         brief's coverage map is checked against; moving it silently is how a question \
         disappears"
    );
}

/// The committed contract is what the Python service reads. If it drifts, the
/// service asserts coverage against a schema the engine no longer has.
#[test]
fn the_committed_contract_matches_the_code() {
    let want = render();
    let p = contract_path();
    if std::env::var("REGEN_PROGRESSION_SCHEMA").is_ok() {
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, &want).unwrap();
        return;
    }
    let got = std::fs::read_to_string(&p).unwrap_or_else(|_| {
        panic!(
            "contracts/progression-schema.json is MISSING. It is generated: \
             REGEN_PROGRESSION_SCHEMA=1 cargo test -p ruleset-core --test schema_export"
        )
    });
    assert_eq!(
        got.replace("\r\n", "\n"),
        want,
        "contracts/progression-schema.json is STALE. The pipeline's question set is asserted \
         total against that file, so a stale one means coverage is checked against a schema \
         the engine no longer has. Regenerate with REGEN_PROGRESSION_SCHEMA=1"
    );
}

/// **The property `PGN-A2` v1 did not have.** A fingerprint that only tracked a
/// version could not see a question disappear. This one covers each position's
/// `askable`, so silently reclassifying `Required` to `Defaultable` — the way a
/// question vanishes without the list getting shorter — moves it.
#[test]
fn the_fingerprint_covers_reclassification_not_just_membership() {
    let f = schema_fingerprint();
    assert_eq!(f.len(), 64);
    assert_eq!(f, schema_fingerprint(), "and it is stable across calls");

    // The list is `&'static`, so reclassification cannot be simulated at
    // runtime — it is a source edit. What CAN be asserted here is that the
    // fingerprint reads the askable at all, which is the half v1 lacked: a hash
    // over paths alone would be identical for any classification of them.
    let paths_only = {
        let mut h = blake3::Hasher::new();
        h.update(b"lw.progression.schema.v1");
        for p in schema_paths() {
            h.update(p.path.as_bytes());
            h.update(&[0]);
        }
        h.finalize().to_hex().to_string()
    };
    assert_ne!(
        f, paths_only,
        "the fingerprint must depend on each position's `askable`, not only on its name - \
         otherwise turning a Required into a Defaultable moves nothing and the question is \
         gone with the list the same length"
    );
}

/// Every `Defaultable` and `Magnitude` carries a REASON. *"Defaultable"* with no
/// reason is how a required field quietly becomes optional, and `Magnitude` with
/// no reason is how a balance decision gets asked of a model.
#[test]
fn every_non_required_position_says_why() {
    for f in schema_paths() {
        match f.askable {
            Askable::Required => {}
            Askable::Defaultable(w) | Askable::Magnitude(w) => assert!(
                w.len() > 20,
                "`{}` is not Required and its reason is too thin to audit: {w:?}",
                f.path
            ),
        }
    }
}
