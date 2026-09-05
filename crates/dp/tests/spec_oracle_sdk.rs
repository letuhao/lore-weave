//! `G3` — **`04d_capability_and_lifecycle.md` gets an oracle.**
//!
//! Third payment against `scripts/dp-oracle-coverage-gate.py`'s ratchet, after
//! `05_control_plane_spec.md`. Same argument as [`spec_oracle`]'s docstring, so
//! it is not repeated: a number transcribed by hand from a LOCKED document
//! needs a check by a **different method**, and a second hand-written table
//! agreeing with the first is the same act done twice.
//!
//! Two things in `04d` were transcriptions with nothing watching them.
//!
//! # `DP-K9`'s refresh lead
//!
//! [`dp::REFRESH_LEAD_MS`] is 60 000, and its own docstring **quotes the spec
//! sentence** — *"refresh 60s before `exp`"* — beside the constant. That is a
//! copy of the document sitting next to the copy of the number, which is
//! exactly the shape that makes drift invisible: edit the spec and both copies
//! here still agree with each other. `meta-rs` already asserts the lead is
//! shorter than the TTL, so the two constants are pinned to *each other*, and
//! until now neither was pinned to the file.
//!
//! # `DP-K11`'s lint set
//!
//! `DP-K11` names **four** lints. `lints/dp-clippy` ships **two**. That is not
//! a defect — slice 2 deliberately shipped one lint against a real subject and
//! stood up the toolchain — but the gap lived only in prose, which is the
//! `PROSE_ONLY` shape `scripts/deferral-gate.py` exists for, in a place it
//! cannot see. [`DEFERRED_LINTS`] gives it the three arms every register in
//! this repo carries, and the third is the one that matters: a row whose lint
//! **gets written** fails, so the list shrinks instead of ageing into a
//! permanent excuse.

use std::fs;
use std::path::PathBuf;

fn sdk_doc() -> String {
    let p: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/03_planning/LLM_MMO_RPG/06_data_plane/04d_capability_and_lifecycle.md");
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

/// `DP-K11` lints that are specified and **not written**, each with why.
///
/// Not a comment, for the reason `UNIMPLEMENTED_METHODS` gives one crate over:
/// a comment listing what is missing is right on the day it is written and
/// silently wrong afterwards. The oracle below reds when `DP-K11` names a lint
/// that is neither shipped nor listed here, when `dp-clippy` ships one
/// `DP-K11` does not name, and when a row here turns out to be implemented.
const DEFERRED_LINTS: &[(&str, &str)] = &[
    (
        "dp::forbid_manual_cache_key",
        "no subject yet — `cache_key!` is the only producer of a `dp:` key in the tree, so the \
         lint would have nothing to fire on (the orphan shape Phase 0 exists to catch)",
    ),
    (
        "dp::missing_instrumentation",
        "`dp::instrumented!` does not exist, and DP-K11's own skeleton was AMENDED in REC-101b \
         for naming the pre-Phase-4 matchers — writing it from that skeleton would ship a lint \
         that matches nothing",
    ),
];

/// `60s` out of *"refresh proactively 60s before expiry"*, in seconds.
///
/// `Err` on anything unexpected, never a default. `V1-F4(d)`, learned in the
/// sibling oracle: a parser that answers "nothing" for a sentence it cannot
/// read makes an unreadable sentence agree with whatever the constant says, and
/// the check written to catch the drift is the thing that hides it.
fn refresh_lead_seconds(doc: &str) -> Result<u64, String> {
    const LEAD: &str = "refresh proactively ";
    let i = doc.find(LEAD).ok_or_else(|| {
        "04d_capability_and_lifecycle.md no longer contains \"refresh proactively …\" — DP-K9's \
         refresh sentence has moved, and a comparison against nothing agrees with anything"
            .to_string()
    })?;
    let rest = &doc[i + LEAD.len()..];
    let cell = rest.split(" before expiry").next().unwrap_or("").trim();
    let digits: String = cell.chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return Err(format!("{cell:?}: no leading number"));
    }
    // The unit is read off the QUANTITY. `60s`, `60ms` and `60min` are three
    // different refresh policies and only one of them is this one.
    let unit = cell[digits.len()..].trim();
    if unit != "s" {
        return Err(format!(
            "{cell:?}: the lead is denominated in {unit:?}, not seconds. A refresh lead in \
             another unit is a different policy, not a smaller number — at `ms` every session \
             refreshes on its last tick, at `min` the lead can exceed the TTL and every \
             capability is due the instant it is issued"
        ));
    }
    digits.parse().map_err(|e| format!("{cell:?}: {digits:?} does not parse ({e})"))
}

/// `DP-K9` — the refresh lead, against the sentence that specifies it.
#[test]
fn the_refresh_lead_matches_dp_k9() {
    let doc = sdk_doc();
    let secs = refresh_lead_seconds(&doc).expect("DP-K9's refresh sentence");
    assert_eq!(
        dp::REFRESH_LEAD_MS,
        secs * 1000,
        "04d_capability_and_lifecycle.md DP-K9 says the SDK refreshes {secs}s before expiry \
         ({} ms), and crates/dp/src/session.rs's REFRESH_LEAD_MS is {} ms. Until now this \
         constant was pinned only against meta-rs's TTL and against a copy of the spec sentence \
         in its own docstring — two copies that agree with each other and not with the file",
        secs * 1000,
        dp::REFRESH_LEAD_MS
    );
}

/// The parser's own teeth, both directions.
#[test]
fn the_refresh_lead_parser_distinguishes_absent_from_unreadable() {
    assert_eq!(refresh_lead_seconds("refresh proactively 60s before expiry."), Ok(60));
    assert_eq!(refresh_lead_seconds("refresh proactively 5s before expiry x"), Ok(5));
    assert!(refresh_lead_seconds("refresh proactively 60ms before expiry").is_err());
    assert!(refresh_lead_seconds("refresh proactively 60min before expiry").is_err());
    assert!(refresh_lead_seconds("refresh proactively soon before expiry").is_err());
    assert!(refresh_lead_seconds("nothing about refreshing here").is_err());
}

/// `DP-K11` — the lint set, and the two that are specified and unwritten.
#[test]
fn the_dp_clippy_lint_set_matches_dp_k11_or_declares_why_not() {
    let doc = sdk_doc();

    // DP-K11's skeletons are `### `dp::<name>` (R-N)` headings, bounded by the
    // next H2 so DP-K12's table cannot leak in.
    let start = doc.find("## DP-K11").expect("DP-K11 is not in 04d_capability_and_lifecycle.md");
    let body = &doc[start..];
    let end = body[9..].find("\n## ").map(|i| i + 9).unwrap_or(body.len());
    let declared: Vec<String> = body[..end]
        .lines()
        .filter_map(|l| l.trim().strip_prefix("### `"))
        .filter_map(|r| r.split_once('`').map(|(name, _)| name.to_string()))
        .filter(|n| n.starts_with("dp::"))
        .collect();

    // The lint crate names its lints in SCREAMING_CASE inside `declare_lint!`;
    // the doc names them `dp::snake_case`. One is the other, lowercased and
    // prefixed, which is rustc's own convention rather than a mapping invented
    // here.
    let lint_src = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../lints/dp-clippy/src/lib.rs");
    let src = fs::read_to_string(&lint_src)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", lint_src.display()));
    let shipped: Vec<String> = src
        .lines()
        .map(str::trim)
        .filter(|l| !l.starts_with("//"))
        .filter_map(|l| l.strip_suffix(','))
        .filter_map(|l| l.strip_prefix("pub "))
        .filter(|n| !n.is_empty() && n.chars().all(|c| c.is_ascii_uppercase() || c == '_'))
        .map(|n| format!("dp::{}", n.to_ascii_lowercase()))
        .collect();

    // Non-vacuity on BOTH sides. Either parse coming back empty makes every set
    // comparison below true — and the shipped side is the one that would fail
    // silently, because two lints is a small enough number that "found none"
    // and "found both" look similar in a diff.
    assert!(
        declared.len() >= 4,
        "DP-K11 parsed only {} lint heading(s) {declared:?} — the `### `dp::name`` shape moved \
         and this oracle is no longer reading it",
        declared.len()
    );
    assert!(
        shipped.len() >= 2,
        "lints/dp-clippy/src/lib.rs parsed only {} declared lint(s) {shipped:?} — the \
         `declare_lint!` shape moved and this oracle is no longer reading it",
        shipped.len()
    );

    let deferred: Vec<&str> = DEFERRED_LINTS.iter().map(|(l, _)| *l).collect();
    let mut problems: Vec<String> = Vec::new();

    for lint in &declared {
        let is_shipped = shipped.iter().any(|s| s == lint);
        let is_deferred = deferred.contains(&lint.as_str());
        if !is_shipped && !is_deferred {
            problems.push(format!(
                "DP-K11 specifies `{lint}` and lints/dp-clippy neither declares it nor is it in \
                 DEFERRED_LINTS. A LOCKED rule with no lint and no recorded reason is a rule \
                 nothing enforces — write it or record why not."
            ));
        }
        if is_shipped && is_deferred {
            problems.push(format!(
                "`{lint}` is declared by lints/dp-clippy AND listed in DEFERRED_LINTS — delete \
                 its row; the register shrinks or it rots."
            ));
        }
    }

    for lint in &shipped {
        if !declared.iter().any(|d| d == lint) {
            problems.push(format!(
                "lints/dp-clippy declares `{lint}` and DP-K11 does not specify it. A lint with \
                 no rule behind it is enforcing somebody's preference — amend DP-K11 or drop it."
            ));
        }
    }

    for (lint, why) in DEFERRED_LINTS {
        if why.trim().is_empty() {
            problems.push(format!("deferred lint `{lint}` names no blocker"));
        }
        if !declared.iter().any(|d| d == lint) {
            problems.push(format!(
                "DEFERRED_LINTS defers `{lint}` and DP-K11 does not specify it — the row defers \
                 nothing."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "04d_capability_and_lifecycle.md DP-K11 specifies {declared:?} and lints/dp-clippy \
         declares {shipped:?}:\n  - {}",
        problems.join("\n  - ")
    );
}
