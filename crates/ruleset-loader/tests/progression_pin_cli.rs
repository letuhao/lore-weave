// Test names use CAPS for the word under test — the convention this repo's
// gamegen suites use throughout, and the thing a failing line should shout.
#![allow(non_snake_case)]

//! S6 — the pin, and the property it exists for.
//!
//! `progression-validate` answers *"would this be admitted?"* against a throwaway
//! store. `progression-pin` answers *"admit it"* against the real one. The tests
//! that matter here are the ones about the difference: **`--expect`**, and the
//! fact that a run which is going to refuse never touches the real store.
//!
//! That second property was a real bug, found by running it. `resolve_and_pin`
//! PERSISTS before it returns, so comparing `--expect` after a resolution against
//! the real store left `<digest>.prog` and `<digest>.labels.toml` behind on a
//! mismatch — a table nobody approved, sitting in the store a reality resolves
//! from. The fix resolves into scratch first.

use std::io::Write;
use std::process::Command;

const OK_TOML: &str = r#"
quantities = ["internal_energy"]

[[progression_kinds]]
name = "內功"
quantity = "internal_energy"
type = "stage"
curve = "stage"
cap = "tier_based"
initial_tier = 0
[[progression_kinds.tiers]]
name = "練氣一層"
tier_max = 100
[[progression_kinds.tiers]]
name = "練氣二層"
tier_max = 300
"#;

const BAD_TOML: &str = r#"
quantities = ["internal_energy"]

[[progression_kinds]]
name = "內功"
quantity = "internal_energy"
type = "stage"
curve = "stage"
cap = "soft_cap"
cap_value = 500
initial_tier = 0
[[progression_kinds.tiers]]
name = "練氣一層"
tier_max = 100
"#;

const WRONG: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

struct Case {
    dir: tempdir::Dir,
}

/// Minimal scoped temp dir — no dev-dependency for four tests.
mod tempdir {
    pub struct Dir(pub std::path::PathBuf);
    impl Dir {
        pub fn new(tag: &str) -> Self {
            let p = std::env::temp_dir()
                .join(format!("pin-test-{}-{tag}", std::process::id()));
            let _ = std::fs::remove_dir_all(&p);
            std::fs::create_dir_all(&p).expect("temp dir");
            Self(p)
        }
    }
    impl Drop for Dir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
}

impl Case {
    fn new(tag: &str, body: &str) -> (Self, std::path::PathBuf, std::path::PathBuf) {
        let c = Case { dir: tempdir::Dir::new(tag) };
        let toml = c.dir.0.join("layer.toml");
        std::fs::File::create(&toml)
            .and_then(|mut f| f.write_all(body.as_bytes()))
            .expect("write layer");
        let store = c.dir.0.join("store");
        (c, toml, store)
    }
}

fn digest_of(toml: &std::path::Path) -> String {
    let out = Command::new(env!("CARGO_BIN_EXE_progression-validate"))
        .arg(format!("reality={}", toml.display()))
        .output()
        .expect("validate runs");
    let s = String::from_utf8_lossy(&out.stdout);
    let line = s
        .lines()
        .find(|l| l.contains("progression_digest"))
        .expect("a digest line");
    line.split('"').nth(3).expect("the digest").to_string()
}

fn pin(store: &std::path::Path, expect: &str, toml: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_progression-pin"))
        .args([
            "--store",
            &store.display().to_string(),
            "--expect",
            expect,
            &format!("reality={}", toml.display()),
        ])
        .output()
        .expect("pin runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

fn entries(p: &std::path::Path) -> Vec<String> {
    match std::fs::read_dir(p) {
        Ok(rd) => rd
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect(),
        Err(_) => Vec::new(),
    }
}

#[test]
fn a_matching_digest_pins_and_the_RULESET_digest_moves() {
    let (_c, toml, store) = Case::new("ok", OK_TOML);
    let d = digest_of(&toml);
    let (ok, out) = pin(&store, &d, &toml);

    assert!(ok, "{out}");
    assert!(out.contains("\"pinned\": true"), "{out}");
    assert!(out.contains(&d), "the progression digest is echoed: {out}");
    // POC-1's exit criterion is "the RULESET digest moves", not "a table appeared
    // in a directory" — so the pin has to report it.
    let rd = out
        .lines()
        .find(|l| l.contains("ruleset_digest"))
        .and_then(|l| l.split('"').nth(3))
        .unwrap_or("");
    assert_eq!(rd.len(), 64, "a real ruleset digest: {out}");

    let files = entries(&store);
    assert!(files.iter().any(|f| f.ends_with(".prog")), "{files:?}");
    assert!(files.iter().any(|f| f.ends_with(".labels.toml")), "{files:?}");
    assert!(files.iter().any(|f| f.ends_with(".canon")), "the ruleset landed: {files:?}");
}

#[test]
fn a_MISMATCHED_digest_refuses_and_leaves_the_real_store_untouched() {
    // **The bug this test exists for.** `resolve_and_pin` persists before it
    // returns, so a `--expect` compared after a real-store resolution left a table
    // nobody approved behind. Found by running it against an empty store.
    let (_c, toml, store) = Case::new("mismatch", OK_TOML);
    let (ok, out) = pin(&store, WRONG, &toml);

    assert!(!ok, "{out}");
    assert!(out.contains("digest mismatch"), "{out}");
    assert!(out.contains("was NOT touched"), "{out}");
    assert!(
        entries(&store).is_empty(),
        "a refused pin wrote into the real store: {:?}",
        entries(&store)
    );
}

#[test]
fn an_INVALID_ruleset_refuses_with_the_engines_own_finding_and_stores_nothing() {
    let (_c, toml, store) = Case::new("invalid", BAD_TOML);
    let (ok, out) = pin(&store, WRONG, &toml);
    assert!(!ok, "{out}");
    assert!(out.contains("progression.schema.cap_curve_invalid"), "{out}");
    assert!(entries(&store).is_empty(), "{:?}", entries(&store));
}

#[test]
fn expect_is_REQUIRED() {
    // Without it the pin would succeed on whatever the bytes happen to resolve to,
    // and the ruleset would carry a digest nobody saw.
    let (_c, toml, store) = Case::new("noexpect", OK_TOML);
    let out = Command::new(env!("CARGO_BIN_EXE_progression-pin"))
        .args([
            "--store",
            &store.display().to_string(),
            &format!("reality={}", toml.display()),
        ])
        .output()
        .expect("runs");
    let s = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success());
    assert!(s.contains("--expect"), "{s}");
    assert!(entries(&store).is_empty());
}

#[test]
fn a_pin_does_not_DESTROY_what_is_already_in_the_store() {
    // **Found by a bite-test that PASSED.** Pointing the scratch store at the real
    // one should have reddened `..._leaves_the_real_store_untouched` — it did not,
    // because the scratch cleanup then deleted the real store and the test's
    // "is it empty?" assertion was satisfied for the opposite reason.
    //
    // So the scratch/real separation had no test that could see it being
    // conflated, and the failure it hides is far worse than the bug it was written
    // for: every pin would wipe the whole store. This asserts the property that
    // actually matters — an earlier pin survives a later one.
    let (_c, first, store) = Case::new("keep-a", OK_TOML);
    let d1 = digest_of(&first);
    assert!(pin(&store, &d1, &first).0);
    let before = entries(&store);
    assert!(!before.is_empty());

    // A genuinely different ladder: same shape, one more tier.
    let second_body = OK_TOML.to_string()
        + "[[progression_kinds.tiers]]\nname = \"練氣三層\"\ntier_max = 900\n";
    let (_c2, second, _) = Case::new("keep-b", &second_body);
    let d2 = digest_of(&second);
    assert_ne!(d1, d2, "the two ladders must differ or this proves nothing");
    assert!(pin(&store, &d2, &second).0);

    let after = entries(&store);
    for f in &before {
        assert!(after.contains(f), "pinning `{d2}` destroyed `{f}`: {after:?}");
    }
    assert!(after.iter().any(|f| f.starts_with(&d2)), "{after:?}");
}

#[test]
fn pinning_the_same_bytes_twice_is_idempotent() {
    // The store is content-addressed and `put` never overwrites, so a re-pin must
    // be a no-op rather than an error — otherwise a retried deploy is a failure.
    let (_c, toml, store) = Case::new("twice", OK_TOML);
    let d = digest_of(&toml);
    let (a, _) = pin(&store, &d, &toml);
    let (b, out) = pin(&store, &d, &toml);
    assert!(a && b, "second pin: {out}");
}
