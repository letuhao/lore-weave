//! `G3` — **`01_scope_and_boundary.md` gets an oracle: is the SDK surface the
//! one this LOCKED scope decision actually locks?**
//!
//! Seventh payment against `scripts/dp-oracle-coverage-gate.py`'s ratchet, and
//! the last coverable document in the corpus — after this the worklist is empty
//! and the remaining eleven are excluded with a reason, not unread.
//!
//! # The trap this document sets, said out loud before the code
//!
//! `01`'s most-cited clause is §4's boundary rule — *"if a service reads or
//! writes any aggregate in a per-reality database it is a game-layer service"* —
//! and its consumer is **`scripts/reality-id-adoption-gate.py`'s `IN_SCOPE`**, a
//! **Python** constant. This ratchet counts **Rust** readers only. Writing a
//! Rust test that reads a Python gate's tuple to make the number move would be
//! an arm whose subject is not the thing it names, which is `BDR-79` exactly —
//! a self-witness dressed as coverage.
//!
//! So the split is deliberate: **§4's boundary rule is checked in the Python
//! gate that consumes it**, beside `IN_SCOPE`, where a drift can actually be
//! read. **This file takes §2.4 and §3b**, where both sides are Rust and the
//! pair is real — the document names concrete primitives, and `crates/dp`
//! either exports them or does not.
//!
//! # What it found
//!
//! Two of the three primitives §3b names as shipping today do not exist:
//! `query_scoped_reality` and `t3_write_multi` are absent from the crate. They
//! are registered below rather than deleted from the doc, because the doc is
//! LOCKED and the gap is real work — and the register **shrinks**: the day
//! either symbol is exported, its row reds and must be removed.
//!
//! # Stated limit
//!
//! It reads `lib.rs`'s `pub use` door, not every `pub fn` in the crate. That is
//! the right subject — §2.4's claim is about *the surface exposed to game
//! services* — but it means a primitive made public without being re-exported at
//! the crate root is invisible here. `DP-R5`'s module privacy is what makes that
//! shape not-a-door in the first place.

use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;

fn repo(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(rel)
}

fn read(rel: &str) -> String {
    let p = repo(rel);
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

/// Short names, for messages only — never for opening anything.
const SCOPE_DOC: &str = "01_scope_and_boundary.md";
const DP_LIB: &str = "crates/dp/src/lib.rs";

/// The path literals live INSIDE these functions deliberately.
///
/// `scripts/dp-oracle-coverage-gate.py` counts a document as read only when its
/// name appears in a function **reachable from a `#[test]`** whose chain
/// asserts. A module-level `const` is a string that nothing necessarily reads,
/// so it does not qualify — and it should not: that is the difference between
/// an oracle and a file that merely mentions a document. Measured: while these
/// were `const`s the ratchet scored this file at zero and still reported
/// `01_scope_and_boundary.md` unread, correctly.
fn scope_doc() -> String {
    read("docs/03_planning/LLM_MMO_RPG/06_data_plane/01_scope_and_boundary.md")
}

fn dp_lib() -> String {
    read("crates/dp/src/lib.rs")
}

/// Primitives `01_scope_and_boundary.md` names as SDK surface that the crate
/// does not export, each with why the row exists and what would retire it.
///
/// This is the `CP_TABLES_WITHOUT_A_MIGRATION` shape, not a new category: a
/// prose-only gap becomes a counted row with a shrink arm. A row is a statement
/// that the doc is ahead of the code — never that the doc is wrong.
const SPECIFIED_NOT_BUILT: &[(&str, &str)] = &[
    (
        "query_scoped_reality",
        "§2.4 lists a `scoped-query primitive` and §3b gives its signature, but the crate exports \
         no scoped-query door — `crates/dp/src/scope.rs` defines the SCOPE types (`RealityScope`, \
         `ChannelScope`) that such a primitive would take, and nothing consumes them as a query. \
         Retires when a `query_scoped_*` appears in lib.rs's `pub use`.",
    ),
    (
        "t3_write_multi",
        "§2.4 and §3b both name an atomic multi-aggregate T3 write; `write.rs` exports the four \
         single-aggregate writes (`t0_write`..`t3_write`) and no multi form. The atomicity this \
         primitive promises is the part that needs designing — a loop over `t3_write` is not it. \
         Retires when `t3_write_multi` appears in lib.rs's `pub use`.",
    ),
];

/// Tier-family globs §2.4 declares for the typed write primitives.
///
/// Parsed shape, not a copy: the test pulls the backticked globs out of the
/// document, so deleting the bullet reds rather than silently agreeing.
const TIER_WRITE_PREFIXES: &[&str] = &["t0_", "t1_", "t2_", "t3_"];

/// Every concrete `dp::primitives::<name>` the document names.
fn doc_named_primitives(doc: &str) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    for (_, tail) in doc.match_indices("dp::primitives::").map(|(i, m)| (i, &doc[i + m.len()..])) {
        let name: String =
            tail.chars().take_while(|c| c.is_ascii_alphanumeric() || *c == '_').collect();
        if !name.is_empty() {
            out.insert(name);
        }
    }
    out
}

/// Every item `crates/dp/src/lib.rs` re-exports at the crate root — the door
/// §2.4's "surface exposed to game services" is a claim about.
fn crate_root_exports(lib: &str) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    let mut rest = lib;
    while let Some(i) = rest.find("pub use ") {
        rest = &rest[i + "pub use ".len()..];
        let Some(end) = rest.find(';') else { break };
        let stmt = &rest[..end];
        rest = &rest[end..];
        // `pub use read::{a, b, c};` and `pub use cache::KeyId;` both reduce to
        // their trailing item list once the path prefix is dropped.
        let items = match (stmt.find('{'), stmt.rfind('}')) {
            (Some(a), Some(b)) if b > a => stmt[a + 1..b].to_string(),
            _ => stmt.rsplit("::").next().unwrap_or("").to_string(),
        };
        for it in items.split(',') {
            // `X as Y` opens the door under the name Y — that is what a caller
            // can reach, so Y is the export. Splitting on ',' alone and then
            // demanding an all-alphanumeric token silently DROPS every aliased
            // re-export, which blinds both arms below: measured, adding
            // `t3_write as t3_write_multi` left this oracle perfectly green
            // while the crate exported a primitive the register calls unbuilt.
            let raw = it.trim();
            let name = match raw.rsplit_once(" as ") {
                Some((_, alias)) => alias.trim(),
                None => raw,
            };
            if !name.is_empty() && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
                out.insert(name.to_string());
            }
        }
    }
    out
}

/// A re-exported item is a *method* for §2.4's count when it is snake_case —
/// types and traits in this crate are UpperCamel without exception.
fn is_function_like(name: &str) -> bool {
    name.chars().next().is_some_and(|c| c.is_ascii_lowercase())
}

/// The `(~N methods)` ceiling §2.4 locks, read out of the document.
fn doc_method_ceiling(doc: &str) -> Option<usize> {
    let i = doc.find("methods)")?;
    let head = &doc[..i];
    let digits: String =
        head.chars().rev().skip_while(|c| !c.is_ascii_digit()).take_while(|c| c.is_ascii_digit()).collect();
    digits.chars().rev().collect::<String>().parse().ok()
}

#[test]
fn every_primitive_the_scope_doc_names_exists_or_is_registered_unbuilt() {
    let doc = scope_doc();
    let lib = dp_lib();
    let named = doc_named_primitives(&doc);
    let exports = crate_root_exports(&lib);
    let mut problems: Vec<String> = Vec::new();

    // Non-vacuity, both sides. An empty parse agrees with everything, and these
    // two numbers are the entire content of the check.
    //
    // THE FLOOR IS 2, NOT 3, AND THAT IS LOAD-BEARING — do not "tighten" it.
    // The document names exactly three primitives. A floor of 3 therefore makes
    // the register's "the doc no longer names it" arm UNREACHABLE: dropping any
    // one primitive trips the floor first, so the arm can never fire and reports
    // clean forever. Measured — the first bite of that arm produced a floor
    // failure instead, `BDR-56`'s shape. The floor's job is "the parse is
    // reading the table at all"; the arm's job is "a named primitive vanished".
    // They are only separable while floor < named.
    assert!(
        named.len() >= 2,
        "{SCOPE_DOC} parsed only {} `dp::primitives::<name>` mention(s) {named:?} — §3b's table \
         moved and this oracle is reading nothing",
        named.len()
    );
    assert!(
        exports.len() >= 20,
        "{DP_LIB} parsed only {} crate-root export(s) — the `pub use` shape moved and every arm \
         below would report clean forever",
        exports.len()
    );

    let registered: Vec<&str> = SPECIFIED_NOT_BUILT.iter().map(|(n, _)| *n).collect();

    for name in &named {
        let exported = exports.contains(name);
        let recorded = registered.contains(&name.as_str());
        if !exported && !recorded {
            problems.push(format!(
                "`01_scope_and_boundary.md` §3b names `dp::primitives::{name}` as SDK surface and \
                 `crates/dp/src/lib.rs` does not export it. Either the primitive was renamed and \
                 the LOCKED scope doc still advertises the old door, or it is unbuilt — in which \
                 case it belongs in SPECIFIED_NOT_BUILT with what would retire the row."
            ));
        }
        if exported && recorded {
            problems.push(format!(
                "`{name}` is BOTH exported by `crates/dp/src/lib.rs` and recorded in \
                 SPECIFIED_NOT_BUILT — pick one; the classification is the whole check."
            ));
        }
    }

    // THE SHRINK ARM. A register that only grows is a list of excuses. A row
    // whose symbol arrived must be removed, and the arm is what makes that
    // mechanical rather than remembered.
    for (name, why) in SPECIFIED_NOT_BUILT {
        if why.trim().len() < 60 {
            problems.push(format!(
                "`{name}` is recorded as specified-not-built with no real reason — a row whose \
                 reason cannot be audited is a row nobody will ever retire"
            ));
        }
        if !named.contains(*name) {
            problems.push(format!(
                "SPECIFIED_NOT_BUILT carries `{name}` and `01_scope_and_boundary.md` no longer \
                 names it. The doc dropped the primitive; the row now records a gap between \
                 nothing and nothing — delete it."
            ));
        }
        if exports.contains(*name) {
            problems.push(format!(
                "`{name}` is recorded as specified-not-built and `crates/dp/src/lib.rs` NOW \
                 EXPORTS IT. It was built — remove the row, so the register keeps shrinking."
            ));
        }
    }

    // The reverse direction: a write primitive the crate opens must live inside
    // a tier family §2.4 declares. This is what catches a door added to the SDK
    // that the LOCKED scope decision never authorised.
    let tier_writes: Vec<&String> = exports
        .iter()
        .filter(|n| TIER_WRITE_PREFIXES.iter().any(|p| n.starts_with(p)))
        .collect();
    assert!(
        tier_writes.len() >= 4,
        "found only {} tier-prefixed write primitive(s) {tier_writes:?} in the crate root — \
         `write.rs`'s re-export moved and the arm below reaches nothing",
        tier_writes.len()
    );
    for name in tier_writes {
        // §2.4 declares the families as backticked globs (`t0_*`, `t3_*_write`).
        // The document must still carry the family this door belongs to.
        let fam = &name[..3];
        if !doc.contains(&format!("`{fam}")) {
            problems.push(format!(
                "`crates/dp/src/lib.rs` exports `{name}` and `01_scope_and_boundary.md` §2.4 no \
                 longer declares the `{fam}*` family. The SDK opened a tier door the LOCKED scope \
                 decision does not list — §2.4 is the authority on what the surface may contain."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "01_scope_and_boundary.md names {named:?}; crates/dp exports {} item(s):\n  - {}",
        exports.len(),
        problems.join("\n  - ")
    );
}

#[test]
fn the_sdk_surface_stays_within_the_size_the_scope_doc_locks() {
    let doc = scope_doc();
    let lib = dp_lib();

    // The ceiling is READ FROM THE DOCUMENT, not copied here. Raising the limit
    // is then an edit to the LOCKED scope decision — visible, reviewable — and
    // never a quiet constant bump in a test file.
    let ceiling = doc_method_ceiling(&doc).unwrap_or_else(|| {
        panic!(
            "{SCOPE_DOC} §2.4 no longer states a `(~N methods)` ceiling. That number is the whole \
             content of DP-A10's \"primitives, not domain queries\" split — without it this check \
             has no subject."
        )
    });
    assert!(
        (5..=100).contains(&ceiling),
        "parsed a method ceiling of {ceiling} from {SCOPE_DOC}, which is not a plausible SDK \
         size — the parse latched onto the wrong number"
    );

    let exports = crate_root_exports(&lib);
    let methods: Vec<&String> = exports.iter().filter(|n| is_function_like(n)).collect();
    assert!(
        !methods.is_empty(),
        "{DP_LIB} parsed zero function-like exports — a ceiling nothing can reach is not a ceiling"
    );

    assert!(
        methods.len() <= ceiling,
        "`01_scope_and_boundary.md` §2.4 locks the SDK at a small, stable ~{ceiling}-method \
         surface, and `crates/dp/src/lib.rs` now re-exports {} function-like item(s): {methods:?}. \
         §2.4's \"Explicitly NOT in SDK\" clause names what this growth usually is — \
         feature-specific queries migrating into the primitives layer, which DP-A10 puts in \
         feature repos. Either the doc's ceiling moves deliberately, or the door does.",
        methods.len()
    );
}
