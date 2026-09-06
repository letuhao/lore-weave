//! `SC1` — the Rust half of the `admin-cli` ↔ `actor-control` seam contract.
//!
//! `D-PC-SEAM-NO-CONTRACT`: argv is rendered by Go and parsed by Rust; the reply
//! is emitted by Rust and unmarshalled by Go. Two lists in two languages with no
//! compiler between them, so a rename on either side keeps BOTH unit suites
//! green and breaks the live loop. This file holds Rust to
//! `contracts/actor-control-worker.contract.json`; `actor_control_seam_test.go`
//! holds Go to the same file.
//!
//! # The two halves are checked DIFFERENTLY, and the difference is honest
//!
//! **The flags are checked BEHAVIOURALLY.** `Args::parse` runs before
//! `Config::from_env`, so running the real binary with a complete argv and an
//! empty environment reaches the env check — exit 2, *"missing required env"* —
//! while an argv the parser rejects dies earlier with *"unknown flag"*. Two
//! distinguishable messages, no database, the actual compiled parser. That is a
//! real test of the real thing.
//!
//! **The response keys are checked by reading the SOURCE.** Every branch of
//! `emit` needs a database to reach, so there is no way to observe the real JSON
//! here. Scanning the `json!` literals is weaker and is stated rather than
//! glossed: it proves the key NAMES agree, which is what a rename breaks, and it
//! does not prove a branch is reachable. The live run in the player-control
//! run-state (`P7`, twelve steps) is what exercises the branches.
//!
//! A source scan has a specific failure mode — matching nothing and reporting
//! success — so `the_scanner_can_see_its_subject` asserts the scan found the
//! keys it must find before any comparison is trusted.

use std::collections::BTreeSet;
use std::path::PathBuf;
use std::process::Command;

const WORKER: &str = env!("CARGO_BIN_EXE_actor-control");

fn repo_root() -> PathBuf {
    // `CARGO_MANIFEST_DIR` is services/world-service.
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn contract() -> serde_json::Value {
    let path = repo_root().join("contracts").join("actor-control-worker.contract.json");
    let raw = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("the seam contract must be readable at {path:?}: {e}"));
    serde_json::from_str(&raw).expect("the seam contract must be valid JSON")
}

fn strings(v: &serde_json::Value) -> BTreeSet<String> {
    v.as_array()
        .expect("expected a JSON array in the contract")
        .iter()
        .map(|s| s.as_str().expect("expected a string").to_string())
        .collect()
}

/// The worker source, for the key scan.
fn worker_source() -> String {
    let path = repo_root()
        .join("services").join("world-service").join("src").join("bin").join("actor_control.rs");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {path:?}: {e}"))
}

// ── the contract itself must have teeth ─────────────────────────────────────

/// A contract that parsed to nothing would make every assertion below vacuous.
///
/// `NV-3`: the scope reaching nothing is indistinguishable from the check
/// passing. Asserted first, and with real floors rather than `is_empty`, so a
/// contract truncated to one entry is caught too.
#[test]
fn the_contract_has_subjects() {
    let c = contract();
    assert!(strings(&c["ops"]).len() >= 3, "the contract declares fewer ops than exist");
    assert!(
        strings(&c["flags"]["valued"]).len() >= 5,
        "the contract declares almost no valued flags — is it truncated?"
    );
    assert!(!strings(&c["flags"]["valueless"]).is_empty(), "--dry-run must be declared");
    assert!(
        strings(&c["outcome_keys"]["always"]).len() >= 3,
        "the always-present key set is too small to be the real one"
    );
    assert!(strings(&c["outcome_keys"]["conditional"]).len() >= 10);
}

// ── the flags, behaviourally ────────────────────────────────────────────────

/// Run the real binary with an EMPTY worker environment.
///
/// Returns stderr. The env is cleared so the run cannot reach a database and
/// cannot depend on the developer's shell: every path ends at exit 2, and WHICH
/// exit-2 message comes back is the answer.
fn run_with_no_env(args: &[&str]) -> String {
    let out = Command::new(WORKER)
        .args(args)
        .env_clear()
        // PATH and SYSTEMROOT only — the worker needs them to start at all on
        // Windows, and neither carries a credential.
        .envs(std::env::vars().filter(|(k, _)| k == "PATH" || k == "SYSTEMROOT"))
        .output()
        .expect("the worker binary must be runnable");
    assert_eq!(
        out.status.code(),
        Some(2),
        "with no env every invocation must reach the config check and exit 2; stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stderr).to_string()
}

/// Every flag the contract declares must be ACCEPTED by the real parser.
///
/// The proof that it was accepted is that the run got past `Args::parse` and
/// died in `Config::from_env` instead — a different message, from a later line.
#[test]
fn every_declared_flag_is_accepted_by_the_parser() {
    let c = contract();
    // A complete, valid grant argv; each declared flag is then added to it, so
    // the only variable is the flag under test.
    let base = [
        "--op", "grant",
        "--reality-id", "11111111-1111-4111-8111-111111111111",
        "--user-ref-id", "22222222-2222-4222-8222-222222222222",
        "--actor-id", "33333333-3333-4333-8333-333333333333",
        "--reason", "seam contract: every declared flag must parse",
    ];
    let value_for = |f: &str| match f {
        "--op" => "grant",
        "--entity-id" => "7",
        "--reason" => "seam contract probe",
        _ => "44444444-4444-4444-8444-444444444444",
    };

    for flag in strings(&c["flags"]["valued"]) {
        let mut args: Vec<&str> = base.to_vec();
        let v = value_for(&flag);
        // `--op` and the ids are already in `base`; re-passing is harmless
        // (last wins) and keeps the loop uniform.
        args.push(&flag);
        args.push(v);
        let err = run_with_no_env(&args);
        assert!(
            err.contains("missing required env"),
            "flag {flag} did not reach the config check — the parser refused it: {err}"
        );
    }
    for flag in strings(&c["flags"]["valueless"]) {
        let mut args: Vec<&str> = base.to_vec();
        args.push(&flag);
        let err = run_with_no_env(&args);
        assert!(
            err.contains("missing required env"),
            "value-less flag {flag} was refused by the parser: {err}"
        );
    }
}

/// …and a flag the contract does NOT declare must be REFUSED.
///
/// The other direction, without which the test above is satisfied by a parser
/// that accepts everything — including the typo that would otherwise surface two
/// processes from where it was typed.
#[test]
fn an_undeclared_flag_is_refused() {
    let err = run_with_no_env(&[
        "--op", "grant",
        "--reality-id", "11111111-1111-4111-8111-111111111111",
        "--user-ref-id", "22222222-2222-4222-8222-222222222222",
        "--actor-id", "33333333-3333-4333-8333-333333333333",
        "--reason", "seam contract: an undeclared flag must be refused",
        "--controller-kind", "llm",
    ]);
    assert!(
        err.contains("unknown flag --controller-kind"),
        "an undeclared flag must be named and refused, got: {err}"
    );
}

/// Every op the contract declares is accepted, and one it does not is refused.
#[test]
fn the_op_set_is_closed_and_matches_the_contract() {
    let c = contract();
    for op in strings(&c["ops"]) {
        let mut args = vec![
            "--op", op.as_str(),
            "--reality-id", "11111111-1111-4111-8111-111111111111",
            "--reason", "seam contract: every declared op must parse",
        ];
        // Per-op required identifiers, or the parser refuses for a reason that
        // has nothing to do with the op name.
        if op == "grant" {
            args.extend(["--user-ref-id", "22222222-2222-4222-8222-222222222222"]);
        }
        if op == "grant" || op == "revoke" {
            args.extend(["--actor-id", "33333333-3333-4333-8333-333333333333"]);
        }
        let err = run_with_no_env(&args);
        assert!(
            err.contains("missing required env"),
            "declared op {op} was refused by the parser: {err}"
        );
    }
    let err = run_with_no_env(&[
        "--op", "possess",
        "--reality-id", "11111111-1111-4111-8111-111111111111",
        "--reason", "seam contract: an undeclared op must be refused",
    ]);
    assert!(err.contains("not one of"), "an undeclared op must be refused, got: {err}");
}

// ── the response keys, by source scan ───────────────────────────────────────

/// Every `"key":` literal inside the worker's emitted JSON.
///
/// Scoped to `json!` blocks and the `out[...]`/`json!({...})` sites so that a
/// string constant elsewhere in the file is not mistaken for a wire key — `§0.5`
/// of the reality-layer contract: *a string that looks like a subject is not the
/// subject*.
fn emitted_keys(src: &str) -> BTreeSet<String> {
    let mut keys = BTreeSet::new();
    let mut depth = 0usize;
    for line in src.lines() {
        let t = line.trim();
        if t.starts_with("//") {
            continue;
        }
        if t.contains("json!({") {
            depth += 1;
        }
        // `emit` writes the identifying keys through `json!` and one indexed
        // assignment; both are wire keys and both must be seen.
        if depth > 0 || t.starts_with("out[") {
            let mut rest = t;
            while let Some(i) = rest.find('"') {
                rest = &rest[i + 1..];
                let Some(j) = rest.find('"') else { break };
                let (word, after) = (&rest[..j], &rest[j + 1..]);
                let is_key = after.trim_start().starts_with(':')
                    || after.trim_start().starts_with(']');
                if is_key
                    && !word.is_empty()
                    && word.chars().all(|c| c.is_ascii_lowercase() || c == '_')
                {
                    keys.insert(word.to_string());
                }
                rest = after;
            }
        }
        if depth > 0 && (t.starts_with("})") || t == "});" || t.ends_with("})")) {
            depth = depth.saturating_sub(1);
        }
    }
    keys
}

/// The scan must find its subject before any comparison against it is trusted.
///
/// A scanner that matches nothing reports a perfect match with the contract.
/// This is the arm that would have caught it.
#[test]
fn the_scanner_can_see_its_subject() {
    let keys = emitted_keys(&worker_source());
    assert!(
        keys.len() >= 15,
        "the key scanner found only {} key(s) — it is not reading the emitted JSON: {keys:?}",
        keys.len()
    );
    for must in ["op", "status", "reality_id", "outcome", "conflict"] {
        assert!(keys.contains(must), "the scanner missed {must}: {keys:?}");
    }
}

/// The emitted keys and the contract are the SAME SET, both directions.
///
/// A key Rust emits that the contract omits is a field Go never reads — dropped
/// silently. A key the contract declares that Rust never emits is a Go field
/// frozen at its zero value, which is the write-only-behaviour bug one process
/// over. Neither is visible to either unit suite.
#[test]
fn the_emitted_keys_are_exactly_the_contract() {
    let c = contract();
    let declared: BTreeSet<String> = strings(&c["outcome_keys"]["always"])
        .union(&strings(&c["outcome_keys"]["conditional"]))
        .cloned()
        .collect();
    let emitted = emitted_keys(&worker_source());

    let undeclared: Vec<_> = emitted.difference(&declared).collect();
    assert!(
        undeclared.is_empty(),
        "the worker emits key(s) the contract does not declare: {undeclared:?} — Go will \
         drop them silently. Add them to contracts/actor-control-worker.contract.json AND \
         to ActorControlOutcome in the same commit."
    );
    let unemitted: Vec<_> = declared.difference(&emitted).collect();
    assert!(
        unemitted.is_empty(),
        "the contract declares key(s) the worker never emits: {unemitted:?} — the Go field \
         is frozen at its zero value. Remove them, or emit them."
    );
}

/// The closed-set VALUES are the ones the worker can actually produce.
///
/// `status` and `outcome` are what an operator's script matches on, so a rename
/// is a breaking change to something no compiler sees.
#[test]
fn the_closed_set_values_appear_in_the_worker() {
    let c = contract();
    let src = worker_source();
    for field in ["status", "outcome", "entity_id_source"] {
        for v in strings(&c["outcome_values"][field]) {
            // `outcome` words come from `Outcome::as_str` in the flow module, so
            // the four grant/revoke words are not literals here; only
            // `actor_created` is. Assert what this file can see and let the flow
            // module's own test hold the rest.
            if field == "outcome" && v != "actor_created" {
                continue;
            }
            assert!(
                src.contains(&format!("\"{v}\"")),
                "the contract declares {field}={v:?} and the worker never writes it"
            );
        }
    }
}
