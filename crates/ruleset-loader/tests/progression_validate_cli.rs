//! `PGN-A7` — the verdict records **which binary**, and the binary is real.
//!
//! Doc 39 §7 says the axiom *"stamps a version from nothing"* until something can
//! run the engine's validator from outside the workspace. These tests invoke the
//! **built binary** (`CARGO_BIN_EXE_*`), not the library, because a test that
//! called `resolve_and_pin` directly would prove the library works and say
//! nothing about whether the thing S5 shells out to does.
//!
//! What is deliberately **not** asserted here: that the emitted
//! `engine_schema_version` equals `RULESET_SCHEMA_VERSION`. The binary
//! interpolates that constant, so such a test compares a value to itself — `NV-2`,
//! the subject cannot vary. What can fail is the property that matters: **the
//! binary refuses exactly what the engine's validator refuses**, and says why.

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

/// `PROG_001` §5.5: a `Stage` curve with a `SoftCap` gives one kind two ceilings
/// that disagree. Both halves may be individually true of the book; the PAIR is
/// what is illegal.
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

fn write_temp(name: &str, body: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("pv-test-{}-{name}.toml", std::process::id()));
    let mut f = std::fs::File::create(&p).expect("temp file");
    f.write_all(body.as_bytes()).expect("write");
    p
}

fn run(path: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_progression-validate"))
        .arg(format!("reality={}", path.display()))
        .output()
        .expect("the binary runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn an_admissible_ruleset_is_admitted_and_carries_its_digest() {
    let p = write_temp("ok", OK_TOML);
    let (ok, stdout) = run(&p);
    let _ = std::fs::remove_file(&p);

    assert!(ok, "exit code 0 for admitted, so a shell sees the verdict:\n{stdout}");
    assert!(stdout.contains("\"verdict\": \"admitted\""), "{stdout}");
    assert!(stdout.contains("\"engine_schema_version\":"), "{stdout}");
    assert!(stdout.contains("\"engine_law_version\":"), "{stdout}");
    // The digest is what S6 would pin. A verdict with no digest is a verdict
    // about nothing addressable.
    assert!(
        !stdout.contains("\"progression_digest\": null"),
        "an admitted ruleset must name the table it admitted:\n{stdout}"
    );
}

#[test]
fn an_inadmissible_pair_is_refused_and_the_finding_is_the_engines_own() {
    let p = write_temp("bad", BAD_TOML);
    let (ok, stdout) = run(&p);
    let _ = std::fs::remove_file(&p);

    assert!(!ok, "exit code 1 for refused:\n{stdout}");
    assert!(stdout.contains("\"verdict\": \"refused\""), "{stdout}");
    // Not a paraphrase: the message is `ProgressionInvalid`'s own Display, so a
    // reviewer reads what the engine said rather than what the CLI thought it
    // meant.
    assert!(stdout.contains("progression.schema.cap_curve_invalid"), "{stdout}");
    assert!(stdout.contains("PROG_001"), "{stdout}");
    assert!(
        stdout.contains("\"progression_digest\": null"),
        "a refused ruleset must NOT name a digest - a digest beside a refusal is \
         something a later stage can pin:\n{stdout}"
    );
}

#[test]
fn a_missing_file_is_refused_rather_than_treated_as_empty() {
    let (ok, stdout) = run(std::path::Path::new("/definitely/not/here.toml"));
    assert!(!ok, "{stdout}");
    assert!(stdout.contains("\"verdict\": \"refused\""), "{stdout}");
    // An empty layer set resolves to the engine default, which is ADMISSIBLE —
    // so a missing file read as "nothing to add" would turn a typo in a path into
    // a clean bill of health for rules nobody validated.
    assert!(!stdout.contains("\"verdict\": \"admitted\""), "{stdout}");
}

#[test]
fn an_unknown_layer_name_is_refused_by_name() {
    let p = write_temp("ok2", OK_TOML);
    let out = Command::new(env!("CARGO_BIN_EXE_progression-validate"))
        .arg(format!("nonesuch={}", p.display()))
        .output()
        .expect("runs");
    let _ = std::fs::remove_file(&p);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success());
    assert!(stdout.contains("unknown layer `nonesuch`"), "{stdout}");
}

#[test]
fn the_validator_leaves_no_table_behind() {
    // Running the validator must never leave a table a later load could resolve:
    // this is a VERDICT, not an admission. The pipeline pins deliberately, at S6.
    // Asserted by the absence of any `progval-*` scratch directory afterwards.
    let p = write_temp("ok3", OK_TOML);
    let (ok, _) = run(&p);
    let _ = std::fs::remove_file(&p);
    assert!(ok);

    let leftovers: Vec<_> = std::fs::read_dir(std::env::temp_dir())
        .expect("temp dir")
        .filter_map(|e| e.ok())
        .filter(|e| e.file_name().to_string_lossy().starts_with("progval-"))
        .collect();
    assert!(
        leftovers.is_empty(),
        "the scratch store was not cleaned up: {:?}",
        leftovers.iter().map(|e| e.path()).collect::<Vec<_>>()
    );
}
