//! `G3` — **`05_control_plane_spec.md` gets an oracle.**
//!
//! # Why this file exists, and it is one measured incident
//!
//! `crates/dp/tests/spec_oracle.rs` parses LOCKED markdown and compares it to
//! `const`s, because *"a second hand-written table agreeing with the first is
//! not an oracle — it is the same act done twice."* It opened **nine of the
//! twenty-six** documents in `06_data_plane/`, and the one it most needed was
//! not among them.
//!
//! `05_control_plane_spec.md` governs everything slices `5B` and `5C` built.
//! The capability TTL shipped at **15 minutes** against a document that says
//! **5** in three independent places (`BDR-52`). That constant *is* the
//! revocation window — `DP-C8` reaches revocation through expiry rather than a
//! revocation list, because `DP-C3` budgets the control plane at ≤100 req/s
//! globally — so the drift was a threefold widening of how long a revoked
//! session keeps writing. It was found by a human reading the file. Nothing
//! compared the number to the document that governs it, and nothing could:
//! the document was read by no test and no gate.
//!
//! `scripts/dp-oracle-coverage-gate.py` now makes that denominator a ratchet.
//! This file is the first payment against it.
//!
//! # Why these tests live HERE and not in `crates/dp`
//!
//! Each rule needs the code side of its comparison, and all three code sides
//! are on this crate's side of the graph: the generated gRPC surface, the two
//! registers in [`dp_control_plane`], and `meta_rs`'s TTL. Putting them in
//! `crates/dp` would mean a dev-dependency from `dp` onto a crate that depends
//! on `dp` — legal in Cargo, and a cycle a reader has to hold in their head
//! for no gain. The coverage gate walks the tree, not one file, so the count
//! rises either way.
//!
//! # Stated limits, because a check that overclaims is worse than none
//!
//! * **`DP-C3`'s prose counts are not parsed.** The implementation note says
//!   *"six groups, fourteen RPCs"* in words. The RPC *set* below is compared
//!   exactly; the English numerals beside it are not, and editing "fourteen" to
//!   "twelve" stays green.
//! * **`DP-C2`'s table list is compared against `CREATE TABLE` statements in
//!   `migrations/meta/`, not against a live database.** A migration that exists
//!   and has never been applied counts as present here. That is the right
//!   answer for this question — the register is about what this repo declares —
//!   but it is not a statement about any running cluster.
//! * **The TTL rule reads three sentences of `DP-C8`/`DP-C9`.** A fourth place
//!   stating a different expiry would not be noticed unless it is one of those
//!   three phrasings.

use std::fs;
use std::path::PathBuf;

/// The LOCKED document, read from disk. Panics naming the path, because a
/// silently-empty read makes every comparison below agree with anything —
/// `V1-F4`, learned in the sibling oracle and applied here rather than
/// re-learned.
fn cp_doc() -> String {
    let p: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/03_planning/LLM_MMO_RPG/06_data_plane/05_control_plane_spec.md");
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

fn repo(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(rel)
}

/// Every `rpc Name (` in a `service DpControlPlane { … }` block.
///
/// One parser for both sides. The doc states the surface inside a ```protobuf
/// fence and the contract states it in a `.proto`; they are the same grammar,
/// and giving each its own parser would be two chances to read one of them
/// wrongly in a way that happens to agree.
fn rpcs_in(text: &str) -> Vec<String> {
    let Some(start) = text.find("service DpControlPlane") else {
        return Vec::new();
    };
    let body = &text[start..];
    let end = body.find("\n}").map(|i| i + 2).unwrap_or(body.len());
    body[..end]
        .lines()
        .filter_map(|l| {
            let t = l.trim();
            // A commented-out rpc is prose about a surface, not a surface.
            let t = t.strip_prefix("rpc ")?;
            let name: String = t.chars().take_while(|c| c.is_alphanumeric() || *c == '_').collect();
            (!name.is_empty()).then_some(name)
        })
        .collect()
}

/// `DP-C3` — **the declared surface, the shipped surface, and the register
/// between them.**
///
/// Four arms, and each one is a distinct way for a contract and a document to
/// come apart:
///
/// 1. the document declares an RPC the proto does not have and no row defers —
///    the surface silently shrank;
/// 2. the proto has an RPC the document does not declare — an **invented**
///    surface, which is the satellite-minting `REC-65` was filed about, one
///    layer up;
/// 3. a `DEFERRED_RPCS` row whose RPC is now in the proto — the register
///    outlived its subject, which this repo has caught rotting four times;
/// 4. a row naming an RPC `DP-C3` no longer declares — it defers nothing.
#[test]
fn the_grpc_surface_matches_dp_c3_or_declares_why_not() {
    let doc = cp_doc();
    let proto_path = repo("contracts/proto/dp_control_plane.proto");
    let proto = fs::read_to_string(&proto_path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", proto_path.display()));

    let declared = rpcs_in(&doc);
    let shipped = rpcs_in(&proto);

    // Non-vacuity first. Either side parsing empty (or nearly) makes every set
    // comparison below true, and the oracle certifies the drift it exists to
    // catch. `DP-C3` states 26; the proto ships the non-channel half.
    assert!(
        declared.len() >= 20,
        "05_control_plane_spec.md DP-C3's protobuf block parsed only {} rpc(s) {declared:?} — the \
         block's shape moved and this oracle is no longer reading it",
        declared.len()
    );
    assert!(
        shipped.len() >= 10,
        "contracts/proto/dp_control_plane.proto parsed only {} rpc(s) {shipped:?} — the contract's \
         shape moved and this oracle is no longer reading it",
        shipped.len()
    );

    let deferred: Vec<&str> = dp_control_plane::DEFERRED_RPCS.iter().map(|(r, _)| *r).collect();
    let mut problems: Vec<String> = Vec::new();

    for rpc in &declared {
        let in_proto = shipped.iter().any(|s| s == rpc);
        let in_register = deferred.contains(&rpc.as_str());
        if !in_proto && !in_register {
            problems.push(format!(
                "DP-C3 declares `{rpc}` and contracts/proto/dp_control_plane.proto neither serves \
                 it nor is it in DEFERRED_RPCS. An RPC cannot leave the surface silently."
            ));
        }
        if in_proto && in_register {
            problems.push(format!(
                "`{rpc}` is in the proto AND listed in DEFERRED_RPCS — delete its row; the \
                 register shrinks or it rots."
            ));
        }
    }

    for rpc in &shipped {
        if !declared.iter().any(|d| d == rpc) {
            problems.push(format!(
                "contracts/proto/dp_control_plane.proto serves `{rpc}` and \
                 05_control_plane_spec.md DP-C3 does not declare it. The contract is the thing \
                 clients generate from, so an undeclared RPC is a surface no LOCKED document \
                 governs — amend DP-C3 or drop the method."
            ));
        }
    }

    for (rpc, blocker) in dp_control_plane::DEFERRED_RPCS {
        if blocker.trim().is_empty() {
            problems.push(format!("deferred rpc `{rpc}` names no blocker"));
        }
        if !declared.iter().any(|d| d == rpc) {
            problems.push(format!(
                "DEFERRED_RPCS defers `{rpc}` and DP-C3 does not declare it — the row defers \
                 nothing."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "05_control_plane_spec.md DP-C3 ({} rpc) and contracts/proto/dp_control_plane.proto ({} \
         rpc) disagree:\n  - {}",
        declared.len(),
        shipped.len(),
        problems.join("\n  - ")
    );
}

/// Table names created by any up-migration in `migrations/meta/`.
fn meta_tables() -> Vec<String> {
    let dir = repo("migrations/meta");
    let mut out = Vec::new();
    let entries = fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()));
    for e in entries.flatten() {
        let p = e.path();
        if !p.to_string_lossy().ends_with(".up.sql") {
            continue;
        }
        let sql = fs::read_to_string(&p).unwrap_or_default().to_ascii_lowercase();
        let mut rest = sql.as_str();
        while let Some(i) = rest.find("create table") {
            let after = rest[i + "create table".len()..].trim_start();
            let after = after.strip_prefix("if not exists").unwrap_or(after).trim_start();
            let name: String = after
                .chars()
                .take_while(|c| c.is_alphanumeric() || *c == '_')
                .collect();
            if !name.is_empty() {
                out.push(name);
            }
            rest = &rest[i + "create table".len()..];
        }
    }
    out
}

/// `DP-C2` — **the control plane's own storage, and the five tables that are a
/// document and nothing else.**
///
/// Same three arms as every register in this repo, and the third is the one
/// that stops the list becoming permanent: a row whose table gains a migration
/// FAILS.
#[test]
fn cp_storage_tables_match_dp_c2_or_declare_why_not() {
    let doc = cp_doc();

    // The bullet list under `**Storage:**`, bounded by the next bold lead so a
    // later list cannot leak in.
    let start = doc
        .find("**Storage:**")
        .expect("05_control_plane_spec.md DP-C2 no longer has a **Storage:** block");
    let body = &doc[start..];
    let end = body["**Storage:**".len()..]
        .find("\n**")
        .map(|i| i + "**Storage:**".len())
        .unwrap_or(body.len());

    let declared: Vec<String> = body[..end]
        .lines()
        .filter_map(|l| l.trim().strip_prefix("- "))
        .filter_map(|r| r.trim().strip_prefix('`'))
        .filter_map(|r| r.split_once('`').map(|(name, _)| name.to_string()))
        .collect();

    assert!(
        declared.len() >= 5,
        "DP-C2's **Storage:** bullet list parsed only {} table(s) {declared:?} — the list's shape \
         moved and this oracle is no longer reading it",
        declared.len()
    );

    let present = meta_tables();
    // The scanner's own teeth. If the migration walk finds nothing — a wrong
    // path, a renamed suffix — then EVERY declared table looks missing, the
    // "row outlived its subject" arm can never fire, and this test passes while
    // measuring nothing. `reality_registry` is the table this repo demonstrably
    // has (`001`, and seven realities are registered in it).
    assert!(
        present.iter().any(|t| t == "reality_registry"),
        "the migrations/meta walk did not find `reality_registry`, which migration 001 creates — \
         the walk is broken, so every table below would look missing and the register could never \
         shrink. Found: {present:?}"
    );

    let register: Vec<&str> =
        dp_control_plane::CP_TABLES_WITHOUT_A_MIGRATION.iter().map(|(t, _)| *t).collect();
    let mut problems: Vec<String> = Vec::new();

    for table in &declared {
        let has_migration = present.iter().any(|t| t == table);
        let in_register = register.contains(&table.as_str());
        if !has_migration && !in_register {
            problems.push(format!(
                "DP-C2 lists `{table}` as control-plane storage, no migration in migrations/meta/ \
                 creates it, and CP_TABLES_WITHOUT_A_MIGRATION does not say so. A table named by a \
                 LOCKED document and backed by nothing is exactly the orphan Phase 0 exists to \
                 catch — build it or record it."
            ));
        }
        if has_migration && in_register {
            problems.push(format!(
                "`{table}` HAS a migration and is still in CP_TABLES_WITHOUT_A_MIGRATION — delete \
                 the row. The register shrinks or it rots."
            ));
        }
    }

    for (table, why) in dp_control_plane::CP_TABLES_WITHOUT_A_MIGRATION {
        if why.trim().is_empty() {
            problems.push(format!("`{table}` is recorded as unbuilt with no reason"));
        }
        if !declared.iter().any(|d| d == table) {
            problems.push(format!(
                "CP_TABLES_WITHOUT_A_MIGRATION names `{table}` and DP-C2 does not list it — the \
                 row records the absence of something nothing asks for."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "05_control_plane_spec.md DP-C2 lists {declared:?} and this repo disagrees:\n  - {}",
        problems.join("\n  - ")
    );
}

/// Pull the quantity out of `…<lead>(5 min)…`, in minutes.
///
/// `Err` rather than a default on anything unexpected: this number is the
/// revocation window, and a parser that shrugs at a cell it cannot read makes
/// an unreadable cell agree with whatever the constant says.
fn minutes_after(doc: &str, lead: &str) -> Result<u64, String> {
    let i = doc.find(lead).ok_or_else(|| {
        format!("05_control_plane_spec.md no longer contains {lead:?} — the sentence this oracle \
                 reads has moved, and a comparison against nothing agrees with anything")
    })?;
    let rest = &doc[i + lead.len()..];
    let open = rest.find('(').ok_or_else(|| format!("{lead:?}: no parenthesised quantity"))?;
    let close = rest.find(')').ok_or_else(|| format!("{lead:?}: unterminated parenthesis"))?;
    if close < open {
        return Err(format!("{lead:?}: a `)` before the `(`"));
    }
    let cell = rest[open + 1..close].trim();
    let digits: String = cell.chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return Err(format!("{lead:?}: {cell:?} has no leading number"));
    }
    let unit = cell[digits.len()..].trim();
    // The unit is read off the quantity, never assumed. `(5 s)` and `(5 min)`
    // are a 60x difference in the revocation window and must not both parse.
    if !(unit.starts_with("min") || unit.starts_with("minute")) {
        return Err(format!(
            "{lead:?}: {cell:?} is denominated in {unit:?}, not minutes. This is a capability \
             lifetime; a quantity in another unit is a different number, not a smaller one"
        ));
    }
    digits.parse().map_err(|e| format!("{lead:?}: {digits:?} does not parse ({e})"))
}

/// `DP-C8` — **the capability TTL, against the three places the spec states
/// it.**
///
/// This is `BDR-52` given a mechanism. The constant shipped at 15 minutes while
/// the document said 5 in three independent sentences, and the corollary is why
/// it mattered: `DP-C8` bounds a revoked session's remaining write access by
/// **expiry**, not by a revocation list, so the TTL *is* the revocation window.
///
/// All three sentences are read, and they are cross-checked against each other
/// as well as against the code. That is deliberate: the signing-key rule states
/// `2 ×` the maximum lifetime as its own absolute number, so the document can
/// contradict itself without any code changing — the `FLOW-2` shape, which this
/// corpus has been measured to contain.
#[test]
fn the_capability_ttl_matches_dp_c8() {
    let doc = cp_doc();

    let revocation = minutes_after(&doc, "Short expiry ").expect("DP-C8 Revocation");
    let degraded =
        minutes_after(&doc, "until capabilities expire ").expect("DP-C9 degraded mode");
    let retained =
        minutes_after(&doc, "2× the max capability lifetime ").expect("DP-C8 signing keys");

    assert_eq!(
        revocation, degraded,
        "05_control_plane_spec.md states the capability lifetime twice and disagrees with \
         itself: DP-C8's Revocation says {revocation} min, DP-C9's degraded-mode section says \
         {degraded} min"
    );
    assert_eq!(
        retained,
        revocation * 2,
        "05_control_plane_spec.md's signing-key rule retains verifying-only keys for \
         {retained} min, calling it \"2× the max capability lifetime\", while the lifetime it \
         states elsewhere is {revocation} min. Either the retention window is wrong or the \
         lifetime is — the document contradicts itself and nothing else in the repo would notice"
    );

    let konst_ms = meta_rs::control_plane::DEFAULT_CAPABILITY_TTL_MS;
    assert_eq!(
        konst_ms,
        revocation * 60 * 1000,
        "05_control_plane_spec.md DP-C8 says a capability lives {revocation} min \
         ({} ms), and crates/meta-rs/src/control_plane.rs's DEFAULT_CAPABILITY_TTL_MS is \
         {konst_ms} ms. That constant IS the revocation window — DP-C8 reaches revocation \
         through expiry rather than a revocation list, because DP-C3 budgets the control plane \
         at ≤100 req/s globally — so a constant larger than the spec's is a widening of how long \
         a revoked session keeps writing (BDR-52: it shipped at 3x)",
        revocation * 60 * 1000
    );
}

/// The TTL parser's own teeth, in both directions.
///
/// Every assertion above compares a parse to a constant. If `minutes_after`
/// answered something for a sentence it cannot read, an unreadable sentence
/// would agree with whatever the code says — the `V1-F4(d)` defect, which was
/// live in the sibling oracle and is cheaper to prevent here than to find here.
#[test]
fn the_ttl_parser_distinguishes_absent_from_unreadable() {
    assert_eq!(minutes_after("lifetime (5 min) ok", "lifetime "), Ok(5));
    assert_eq!(minutes_after("lifetime (10 minutes) ok", "lifetime "), Ok(10));

    // A different unit is a different quantity, not a smaller number.
    assert!(minutes_after("lifetime (5 s) x", "lifetime ").is_err());
    assert!(minutes_after("lifetime (300 ms) x", "lifetime ").is_err());
    // No number, no parenthesis, and a lead that is simply gone.
    assert!(minutes_after("lifetime (soon) x", "lifetime ").is_err());
    assert!(minutes_after("lifetime 5 min", "lifetime ").is_err());
    assert!(minutes_after("nothing here", "lifetime ").is_err());
}
