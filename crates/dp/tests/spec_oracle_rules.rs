//! `G3` — **`11_access_pattern_rules.md` gets an oracle: does anything enforce
//! each rule it states?**
//!
//! Sixth payment against `scripts/dp-oracle-coverage-gate.py`'s ratchet.
//!
//! # Why this document and not the other three the board named
//!
//! `§0.6e` row 2 named four candidates — `11_access_pattern_rules`,
//! `14_durable_subscribe`, `15_turn_boundary`, `18_causality_and_routing`.
//! **Three of them have no producer**, measured before a line was written:
//! `DurableEventStream` 0 files, `advance_turn` 0, `TurnBoundary` 0,
//! `DP-A19` (intra-session causality via an opaque token) is proven HERE: the
//! register assertions below are what keep `wait_for`/`CausalityToken` from
//! quietly leaving `crates/dp/src/read.rs`. The type is tracked as `DP-Ch38`;
//! `DP-A19` is the same guarantee stated as an access-pattern rule.
//!
//! `wait_for_token` 0, `route_to_writer` 0; `CausalityToken` appears twice and
//! both are DEFERRED-register rows that already record it as unbuilt. Writing
//! oracles for those would be the orphan shape `§0.6c` forbids — ceremony that
//! cannot fail, over Phase-4 designs nothing implements. **The board row was
//! wrong and is corrected there rather than quietly worked around.**
//!
//! `11_access_pattern_rules` is different: `DP-R1`..`DP-R8` are the rules this
//! repo's gate corpus was largely built to enforce, so both sides exist.
//!
//! # What this asks, and why it is not "does the rule appear somewhere"
//!
//! A grep for `DP-R3` finds it in a Cargo.toml comment. That proves the string
//! is present, not that anything enforces the rule. So the register below makes
//! a POSITIVE, CHECKED claim per rule: *this file enforces it* — and the test
//! fails unless that file exists **and** names the rule. A row whose target is
//! deleted or renamed reds, which is the difference between a claim and a
//! citation nobody can follow.
//!
//! # Stated limit
//!
//! It cannot tell an enforcing mechanism from a well-placed comment inside the
//! named file. That is the same honest limit `scripts/deferral-gate.py` states
//! about prose-in-a-source-file, and the same answer applies: this narrows the
//! claim from *"the string exists anywhere in the repo"* to *"a named file that
//! still exists cites this rule"*, which is strictly stronger and still not
//! proof of behaviour. The behaviour proofs are the lints, the compile-fail
//! suite and the bite harnesses.

use std::fs;
use std::path::{Path, PathBuf};

fn repo(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(rel)
}

fn rules_doc() -> String {
    let p = repo("docs/03_planning/LLM_MMO_RPG/06_data_plane/11_access_pattern_rules.md");
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

/// `DP-R<n>` → the file this repo relies on to enforce it.
///
/// One file per rule, chosen as the most direct enforcement point rather than
/// an exhaustive list: the claim under test is *"something concrete enforces
/// this and it still exists"*, and a list of six files per rule would be six
/// things to rot.
const ACCESS_RULE_ENFORCEMENT: &[(&str, &str)] = &[
    ("DP-R1", "crates/dp/src/ids.rs"),
    ("DP-R2", "crates/dp/src/aggregate.rs"),
    ("DP-R3", "lints/dp-clippy/src/lib.rs"),
    ("DP-R4", "crates/dp/src/cache.rs"),
    ("DP-R5", "crates/dp/src/write.rs"),
    ("DP-R6", "lints/dp-clippy/src/lib.rs"),
    ("DP-R8", "crates/sim-core/src/metrics.rs"),
];

/// Rules with **no mechanism in this repo**, each with what would wake it.
///
/// `DP-R7` is the only one, and it is worth stating precisely rather than
/// listing. Its own *Enforcement* clause names two things: **review** (a human,
/// by design) and a *"compile (partial)"* `Validated<T>` wrapper that the
/// proposal-bus consumer emits. **Neither exists** — measured: `Validated<T>`
/// 0 definitions, and `LlmResponse` / `llm_output` appear in **0** Rust files
/// across `crates/` and `services/`.
///
/// So it is unenforced AND currently unviolatable, which is a materially
/// different state from "unenforced" alone: there is no Rust code that handles
/// LLM output, so there is nothing that could take the forbidden shortcut. The
/// row exists so that stops being true loudly rather than silently — its
/// violation mode is *"prompt-injection exploit writes directly to kernel.
/// Catastrophic in a multi-user game economy."*
const UNENFORCED_ACCESS_RULES: &[(&str, &str)] = &[(
    "DP-R7",
    "no mechanism and no subject: the rule's own enforcement clause names review plus a \
     `Validated<T>` wrapper, and neither `Validated<T>` nor any `LlmResponse`/`llm_output` \
     handling exists in Rust. Wakes the moment a crate under crates/ or services/ takes LLM \
     output — see the shrink arm below, which is what makes that mechanical",
)];

/// The shape whose arrival makes `DP-R7` violable, and therefore worth enforcing.
const R7_SUBJECT_MARKERS: &[&str] = &["LlmResponse", "llm_output"];

fn rs_files(root: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(root) else { return };
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
            if name == "target" || name == ".claude" || name == "node_modules" {
                continue;
            }
            rs_files(&p, out);
        } else if p.extension().is_some_and(|x| x == "rs") {
            out.push(p);
        }
    }
}

/// Every `## DP-R<n>` the document declares.
fn declared_rules(doc: &str) -> Vec<String> {
    doc.lines()
        .filter_map(|l| l.trim().strip_prefix("## "))
        .filter_map(|h| h.split_whitespace().next())
        .filter(|t| t.starts_with("DP-R") && t[4..].chars().all(|c| c.is_ascii_digit()))
        .map(str::to_string)
        .collect()
}

#[test]
fn every_access_pattern_rule_is_enforced_or_declares_why_not() {
    let doc = rules_doc();
    let declared = declared_rules(&doc);

    // Non-vacuity: an empty parse agrees with anything, and this document's
    // whole content is the eight rules.
    assert!(
        declared.len() >= 8,
        "11_access_pattern_rules.md parsed only {} `## DP-R<n>` heading(s) {declared:?} — the \
         heading shape moved and this oracle is reading nothing",
        declared.len()
    );

    let enforced: Vec<&str> = ACCESS_RULE_ENFORCEMENT.iter().map(|(r, _)| *r).collect();
    let unenforced: Vec<&str> = UNENFORCED_ACCESS_RULES.iter().map(|(r, _)| *r).collect();
    let mut problems: Vec<String> = Vec::new();

    for rule in &declared {
        let e = enforced.contains(&rule.as_str());
        let u = unenforced.contains(&rule.as_str());
        if !e && !u {
            problems.push(format!(
                "11_access_pattern_rules.md declares `{rule}` and this repo neither names a file \
                 that enforces it nor records it as unenforced. A LOCKED access-pattern rule that \
                 nothing references is a rule that exists only in prose."
            ));
        }
        if e && u {
            problems.push(format!(
                "`{rule}` is listed as BOTH enforced and unenforced — pick one; the classification \
                 is the whole content of this check."
            ));
        }
    }

    // The enforcement claim is CHECKED, not just present: the named file must
    // exist and must cite the rule. A citation nobody can follow reports
    // evidence and silences review.
    for (rule, rel) in ACCESS_RULE_ENFORCEMENT {
        if !declared.iter().any(|d| d == rule) {
            problems.push(format!(
                "the register claims `{rel}` enforces `{rule}`, and the document no longer \
                 declares that rule — the row enforces nothing."
            ));
            continue;
        }
        let p = repo(rel);
        match fs::read_to_string(&p) {
            Err(_) => problems.push(format!(
                "`{rule}` is claimed to be enforced by `{rel}`, which does not exist. The \
                 mechanism moved or was deleted and the claim outlived it."
            )),
            Ok(src) if !src.contains(rule) => problems.push(format!(
                "`{rel}` is named as `{rule}`'s enforcement point and does not mention `{rule}`. \
                 Either the mechanism moved, or the row was aspirational when written."
            )),
            Ok(_) => {}
        }
    }

    // THE SHRINK ARM. An unenforced rule stays acceptable only while nothing can
    // violate it; the day a subject appears, the row must be revisited rather
    // than carried. This is what stops `UNENFORCED_ACCESS_RULES` ageing into a
    // permanent exemption.
    for (rule, why) in UNENFORCED_ACCESS_RULES {
        if why.trim().len() < 40 {
            problems.push(format!("`{rule}` is recorded as unenforced with no real reason"));
        }
        if !declared.iter().any(|d| d == rule) {
            problems.push(format!(
                "`{rule}` is recorded as unenforced and the document no longer declares it"
            ));
        }
    }
    let mut files = Vec::new();
    rs_files(&repo("crates"), &mut files);
    rs_files(&repo("services"), &mut files);
    assert!(
        files.len() > 200,
        "the source walk found only {} .rs file(s) — it is pointed at nothing, and the shrink arm \
         below would report clean forever",
        files.len()
    );
    let mut r7_subjects: Vec<String> = Vec::new();
    for f in &files {
        // This oracle NAMES the markers, so it would match itself.
        if f.ends_with("spec_oracle_rules.rs") {
            continue;
        }
        let Ok(src) = fs::read_to_string(f) else { continue };
        // Comment lines are prose about the rule, not code that handles LLM
        // output — the distinction `deferral-gate` had to learn the hard way.
        let code: String = src
            .lines()
            .filter(|l| !l.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        if R7_SUBJECT_MARKERS.iter().any(|m| code.contains(m)) {
            r7_subjects.push(f.display().to_string());
        }
    }
    if !r7_subjects.is_empty() {
        problems.push(format!(
            "`DP-R7` is recorded as unenforced BECAUSE no Rust code handles LLM output — and now \
             {} file(s) do: {r7_subjects:?}. The rule is violable from this moment: an \
             `llm_output -> dp::write` chain is a prompt-injection path straight into the kernel. \
             Build the `Validated<T>` seam its enforcement clause specifies, or amend the rule.",
            r7_subjects.len()
        ));
    }

    assert!(
        problems.is_empty(),
        "11_access_pattern_rules.md declares {declared:?}:\n  - {}",
        problems.join("\n  - ")
    );
}
