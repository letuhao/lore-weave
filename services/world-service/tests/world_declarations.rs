//! `A3` — every authored world declaration in the repo actually validates.
//!
//! ## Why this exists
//!
//! `contracts/world/*.json` is what `admin reality provision --world` reads and
//! what `ProvisionRequest.world` carries. A file there that `world_seed::validate`
//! would refuse is a **trap for whoever runs the command**: the refusal arrives at
//! provision time, against a reality that is already half-created, and it arrives
//! as a `SeedReject` in a log rather than as a test naming the file.
//!
//! So the declarations are validated here, where a break is cheap.
//!
//! ## Why this is a plain test and not a gate
//!
//! `validate` is Rust, pure, and already the single source of the rules
//! (`PF_001` §5, `SPG-A3`'s containment matrix, `DP-Ch1`'s depth). A gate would
//! have to reimplement it in Python — a second implementation of a rule set that
//! exists precisely so there is one. `world-scale-parity-gate` exists for the
//! case where a rule genuinely lives in two languages; this is not that case.

use std::path::PathBuf;

use world_service::world_seed::{self, NodeDecl};

fn declarations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/world")
}

fn declaration_files() -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = std::fs::read_dir(declarations_dir())
        .expect("contracts/world must exist")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    out.sort();
    out
}

#[test]
fn every_authored_world_declaration_parses_and_validates() {
    let files = declaration_files();

    // SUBJECT FLOOR. A walk that found nothing would pass this test forever and
    // prove nothing -- the shape `live-suite-registry-gate` was carrying until a
    // disk -> registry direction was added to it.
    assert!(
        !files.is_empty(),
        "no *.json under {} -- this test would pass vacuously",
        declarations_dir().display()
    );

    for path in &files {
        let raw = std::fs::read_to_string(path)
            .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
        let decls: Vec<NodeDecl> = serde_json::from_str(&raw).unwrap_or_else(|e| {
            panic!(
                "{} is not a NodeDecl array: {e}\n\
                 `admin reality provision --world` would refuse this file at the edge",
                path.display()
            )
        });
        assert!(
            !decls.is_empty(),
            "{} declares no nodes; an empty file and no --world flag are the same \
             outcome, so the file would be a lie",
            path.display()
        );
        if let Err(reject) = world_seed::validate(&decls) {
            panic!(
                "{} does not validate: {reject:?} (rule `{}`)\n\
                 This would be refused at PROVISION time, against a reality that is \
                 already half-created.",
                path.display(),
                reject.rule_id()
            );
        }
        // `place_type` is a CLOSED SET in SQL and `validate` does not know it --
        // it is pure and has never seen a `CHECK`. The live arm in
        // `world_seed_live` caught `"market"` in this very file (the column
        // wants `"marketplace"`), which is the whole argument for reading the
        // set HERE too: a declaration should not have to reach a database to
        // find out it is wrong.
        //
        // Read FROM the migration, never copied: two lists of ten strings would
        // drift, and `0026` is the one that decides.
        for d in &decls {
            if let Some(pl) = &d.place {
                assert!(
                    place_types().contains(&pl.place_type),
                    "{}: node {} declares place_type `{}`, which `0026_place`'s \
                     `place_type_closed` would refuse. Allowed: {:?}",
                    path.display(),
                    d.id,
                    pl.place_type,
                    place_types()
                );
            }
        }
    }

    eprintln!("A3: {} authored world declaration(s) parse and validate", files.len());
}

/// The check above is only worth having if `validate` can refuse a file.
///
/// Two arms, because the two ways a declaration goes wrong are different: a
/// STRUCTURAL break (two roots) and a RULE break (a `domain` with no place).
/// A test that only proved one would leave the other unguarded.
#[test]
fn the_validator_refuses_the_two_shapes_this_test_exists_to_catch() {
    let raw = std::fs::read_to_string(declarations_dir().join("demo_v1.json"))
        .expect("the demo declaration is the fixture");
    let good: Vec<NodeDecl> = serde_json::from_str(&raw).expect("parses");
    assert!(world_seed::validate(&good).is_ok(), "the fixture must start valid");

    // 1. STRUCTURAL — a second root. `0019`'s `channels_root_single` would refuse
    //    it in the database; refusing here refuses it earlier.
    let mut two_roots = good.clone();
    two_roots[1].parent = None;
    let err = world_seed::validate(&two_roots).expect_err("two roots must be refused");
    assert!(
        format!("{err:?}").contains("MultipleRoots"),
        "wanted MultipleRoots, got {err:?}"
    );

    // 2. RULE — a `domain` with its place removed. `PF_001` states place-on-domain
    //    is 1:1 and BOTH directions are rejections.
    let mut no_place = good.clone();
    let domain = no_place
        .iter_mut()
        .find(|d| d.place.is_some())
        .expect("the fixture has a domain with a place");
    domain.place = None;
    let err = world_seed::validate(&no_place).expect_err("a placeless domain must be refused");
    assert_eq!(err.rule_id(), "place.missing_decl", "got {err:?}");
}

/// `0026_place`'s `place_type_closed`, read from the migration.
///
/// Parsed rather than copied. A second list of ten strings in this file would
/// be a second source of truth for a closed set, and the first time `0026`
/// gained an eleventh the copy would silently keep refusing it.
fn place_types() -> Vec<String> {
    let sql = std::fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../contracts/migrations/per_reality/0026_place.up.sql"),
    )
    .expect("0026_place.up.sql");
    let start = sql.find("place_type_closed").expect("the constraint exists");
    let open = sql[start..].find("IN (").expect("an IN list") + start;
    let close = sql[open..].find(')').expect("a closing paren") + open;
    let out: Vec<String> = sql[open + 4..close]
        .split(',')
        .map(|s| s.trim().trim_matches('\'').to_string())
        .filter(|s| !s.is_empty())
        .collect();
    assert!(out.len() >= 5, "parsed only {out:?} from 0026 -- the parse is broken");
    out
}
