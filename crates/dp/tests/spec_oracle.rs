//! `V.2` — **a mechanical oracle by a DIFFERENT METHOD.**
//!
//! Every number in `tier.rs` was transcribed by hand from a LOCKED document.
//! A second hand-written table agreeing with the first is not an oracle — it is
//! the same act done twice. This file computes the expected values by a
//! genuinely different route: **it parses the locked markdown**, and asserts the
//! parse equals the `const`.
//!
//! ## Why this test is the point of the whole audit
//!
//! `FLOW-2` measured that `17_game_data_architecture.md` decided four
//! corrections to LOCKED data-plane files on 2026-07-26 and **none were
//! applied** — the register's own words, *"none applied"*. `FLOW-20` found the
//! locked spec naming a table (`event_log`) that has never existed in this repo.
//! `FLOW-10` found dead vocabulary sitting inside a primitive's type signature.
//! Every one of those is the same failure: **a document and a fact drifting
//! apart with nothing watching.**
//!
//! Nothing was watching because nothing *could* — the code did not exist. Now it
//! does, so the alarm can. Edit a budget in `08_scale_and_slos.md` without
//! touching `tier.rs`, or the reverse, and this test goes red naming both sides.
//!
//! ## Stated limits, because a check that overclaims is worse than none
//!
//! **The previous version of this list was wrong in all four of its claims, and
//! a cold-start refuter proved each one (`V1-F4`). What it said, and what is
//! true now:**
//!
//! | it said | it was | now |
//! |---|---|---|
//! | covers `DP-S3`, `DP-X7`, `DP-S5` | true, and that was all — `03_tier_taxonomy.md` was **named by the DoD and never opened**; perturbing its T2 ack left the suite green | `03` is opened, for the thing it is authoritative for: **which tiers exist** |
//! | `Coherency` is *"prose"* | `DP-X1` is a **markdown table** this file's own helper parses as-is | parsed, against [`Coherency::doc_phrase`] |
//! | `SURVIVES_STORE_OUTAGE` is *"guarded by its own unit test"* | that test was a **second hand-written table** — the exact thing this docstring calls *"the same act done twice"*, on the one genuinely new decision in the crate | parsed out of `DP-F5`'s `REC-102c` table |
//! | an empty parse fails rather than passing | true for a missing *section*, false for a bad *cell*: `parse_ttl` returned `None` for an unrecognised unit, so `T0`'s cell could be edited to `1 h` and stay green | every parser returns `Result` and an unparseable cell **panics naming the cell** |
//!
//! **What each document is asked for is what it is authoritative for**, which is
//! the reason `03` is not also parsed for latency: its matrix cell reads
//! *"<1ms write to local, <10ms to Redis"* — two quantities in one cell, and
//! only `DP-S3` defines which one is the ack budget. A parser that took the
//! first number would have been comparing the wrong thing and agreeing anyway.
//!
//! Still **not** covered, stated so the next reader does not have to re-derive
//! it — and this list is where a limit belongs, because an inline comment is
//! not where anyone checks (`V2-F9`):
//!
//! * The per-tier *eligibility rules* and *examples* in `03`, prose by nature.
//! * `DP-S5`'s **read** ceilings — no `const` here mirrors them.
//! * **`REC-102c` is read from the BOLDED LEAD of its cell only.** A row whose
//!   lead says `REJECT` and whose following paragraph says the opposite stays
//!   green. That is deliberate — scanning the whole cell was the first
//!   implementation and it failed correctly, because T3's paragraph contains
//!   the word *"buffered"* while ruling the opposite — but it means the oracle
//!   watches the ruling, not the argument for it.
//! * **The unit of `DP-X7`'s TTL cells beyond `s`/`min`/`h`**, and anything in
//!   a cell after its first quantity.
//! * **`DP-S5`'s BURST column** (`R3-N4`). `table_cells` returns the second cell
//!   only, so `| T2 writes | 500 / s | 2 000 / s |` is compared on the sustained
//!   figure and the burst figure can be edited to anything. It was omitted from
//!   this list while the read ceilings were named, which is the worse half of
//!   the defect: an undisclosed omission in the one place a reader checks.
//! * **`DP-S4`**, a four-row per-tier READ-latency table in the same file and
//!   the same markdown shape as `DP-S3`, which *is* parsed. No `const` here
//!   mirrors it — but it was not mentioned anywhere either.
//!
//! **Closed since (`G10`):** `DP-F7` Bucket 1's second copy of `DP-S5`'s numbers
//! is now compared to the original by `dp_f7_rate_limits_match_dp_s5_ceilings` —
//! the first DOC-to-DOC check here. Every other test asks whether a document and
//! the CODE agree; that one asks whether the corpus agrees with itself, which is
//! `FLOW-2`'s shape and was the last unwatched instance of it in reach.
//!
//! **Now covered that was not, after `G3`:** `02_invariants.md` `DP-A5` — the
//! invariant the seal cites as its authority and which nothing had ever opened —
//! and `12_channel_primitives.md` `DP-Ch5`, so `as_key()` is no longer pinned
//! only against a second copy of itself. **22 of 26 LOCKED documents were read
//! by nothing** when a completeness pass measured it; these two were the
//! load-bearing ones.

use std::fs;
use std::path::PathBuf;
use std::time::Duration;

use dp::{ScopeKind, Tier, TierLevel, T0, T1, T2, T3};

/// `V1-F4(d)` — **the parsers' own teeth.**
///
/// Every test above compares a parse to a `const`. If the parser answers
/// "nothing" for a cell it cannot read, then an unreadable cell agrees with a
/// `const` of `None` and the oracle certifies the drift it exists to catch.
/// That was live: `parse_ttl` returned `None` for any unrecognised unit, so
/// `T0`'s `N/A` and a hypothetical `1 h` were the same answer.
///
/// These cases are the direct evidence that each parser distinguishes **absent**
/// from **unreadable**, in both directions.
#[test]
fn the_parsers_distinguish_absent_from_unreadable() {
    // Absent, legitimately — and the ONLY spelling accepted for it.
    assert_eq!(parse_ttl("N/A"), Ok(None));
    assert_eq!(parse_rate("Unbounded (in-process)"), Ok(None));

    // Readable.
    assert_eq!(parse_ttl("60 s"), Ok(Some(Duration::from_secs(60))));
    assert_eq!(parse_ttl("5 min"), Ok(Some(Duration::from_secs(300))));
    assert_eq!(parse_ms("<50 ms ack"), Ok(Duration::from_millis(50)));
    assert_eq!(parse_rate("5 000 / s"), Ok(Some(5_000)));

    // The exact V1-F4(d) case: an hour is LEGAL in DP-X7 (it caps overrides at
    // one) and used to be indistinguishable from "not cached".
    assert_eq!(parse_ttl("1 h"), Ok(Some(Duration::from_secs(3600))));
    assert_ne!(parse_ttl("1 h"), Ok(None));

    // Unreadable — must be an error, never a silent `None`.
    for bad in ["1 fortnight", "soon", "≤ 1 tick", "5 ms"] {
        assert!(parse_ttl(bad).is_err(), "parse_ttl({bad:?}) must not silently succeed");
    }
    assert!(parse_ms("<1 s").is_err(), "a seconds cell in a millisecond table must not parse");
    assert!(parse_rate("lots").is_err());

    // ── V2-F3: the cases above were all SINGLE-quantity, and every real DP-S3
    // cell for T2 is a TWO-quantity cell. `assert!(parse_ms("<1 s").is_err())`
    // held only because that fixture contains no `ms` at all — the guard's
    // subject could not vary in the direction that would fail it (`NV-2`). These
    // are the actual shapes, and the actual swap the refuter used.
    assert_eq!(parse_ms("<5 ms ack, ≤1 s to projection"), Ok(Duration::from_millis(5)));
    assert!(
        parse_ms("<5 s ack, ≤1 ms to projection").is_err(),
        "swapping the two units of a two-quantity cell is a 1000x drift and must not read as 5ms"
    );
    assert_eq!(parse_ms("<50 ms ack"), Ok(Duration::from_millis(50)));

    // ...and the same on the denominator side.
    assert_eq!(parse_rate("500 / s"), Ok(Some(500)));
    assert!(
        parse_rate("500 / min").is_err(),
        "a per-minute ceiling is a different quantity from a per-second one, not a smaller number"
    );
    assert!(parse_rate("500").is_err(), "a rate with no denominator is not a rate");
}

/// Every `declare_tier!` invocation's first argument, whichever delimiter it
/// uses. `R3-M2`.
fn declared_tiers(src: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = src;
    while let Some(i) = rest.find("declare_tier!") {
        let after = &rest[i + "declare_tier!".len()..];
        let after = after.trim_start();
        // A DEFINITION is `macro_rules! declare_tier {`; an INVOCATION opens
        // with a delimiter and is immediately followed by the tier name.
        if let Some(body) = after.strip_prefix(['(', '{', '[']) {
            let name: String = body
                .trim_start()
                .chars()
                .take_while(|c| c.is_alphanumeric() || *c == '_')
                .collect();
            if !name.is_empty() && name != "name" {
                out.push(name);
            }
        }
        rest = &rest[i + "declare_tier!".len()..];
    }
    out
}

fn dp_doc(name: &str) -> String {
    let p: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/03_planning/LLM_MMO_RPG/06_data_plane")
        .join(name);
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

/// Pull `| <row-label> | <first-cell> |` out of a markdown table, for every row
/// whose label contains `needle`. Returns the raw second cell.
fn table_cells(doc: &str, section: &str, needle_fn: impl Fn(&str) -> bool) -> Vec<(String, String)> {
    let start = doc.find(section).unwrap_or_else(|| panic!("section {section:?} not in doc"));
    let body = &doc[start..];
    // Stop at the next H2, so a later table cannot leak into this one.
    let end = body[section.len()..].find("\n## ").map(|i| i + section.len()).unwrap_or(body.len());
    body[..end]
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .filter_map(|l| {
            let cells: Vec<&str> = l.split('|').map(str::trim).collect();
            if cells.len() < 3 {
                return None;
            }
            let label = cells[1];
            needle_fn(label).then(|| (label.to_string(), cells[2].to_string()))
        })
        .collect()
}

/// `<1 ms` / `<10 ms` / `<5 ms ack, ...` / `<50 ms ack` → Duration.
///
/// `Err` rather than `None` on anything unexpected. `V1-F4(d)`: a parser that
/// returns "nothing" for an unreadable cell makes an unreadable cell agree with
/// a `const` of `None`, and the check that was supposed to catch the drift is
/// the thing that hides it.
/// **The unit is read off the QUANTITY, not looked for anywhere in the cell.**
///
/// `V2-F3`: the previous version asked only whether `"ms"` appeared *somewhere*
/// and then took the leading digits. `DP-S3`'s real cells are **two-quantity
/// cells** — `<5 ms ack, ≤1 s to projection` — so swapping the two units gives
/// `<5 s ack, ≤1 ms to projection`: still contains `ms`, still leads with `5`,
/// still **green**. A 1000× change to a LOCKED latency budget, certified by the
/// oracle written to catch exactly that.
///
/// And the guard that was supposed to prevent it was `NV-2`:
/// `assert!(parse_ms("<1 s").is_err())` passed only because that *fixture*
/// contains no `ms` at all. The property it named did not hold on the real
/// subject, and the test could not tell, because its subject could not vary in
/// the direction that would have failed it.
fn parse_ms(cell: &str) -> Result<Duration, String> {
    let (n, unit) = leading_quantity(cell)?;
    if unit != "ms" {
        return Err(format!(
            "{cell:?}: the leading quantity is {n} {unit}, not milliseconds. This is a p99 write-ack \
             budget; a cell whose FIRST number is in another unit is either a different quantity or \
             a 1000x drift, and the oracle must not guess which"
        ));
    }
    Ok(Duration::from_millis(n))
}

/// `<5 ms ack, …` → `(5, "ms")`. The FIRST number and the unit attached to it.
fn leading_quantity(cell: &str) -> Result<(u64, String), String> {
    let re = cell.trim_start_matches(['<', '≤', '~', ' ']);
    let digits: String = re.chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return Err(format!("{cell:?}: no leading number"));
    }
    let n: u64 = digits
        .parse()
        .map_err(|e| format!("{cell:?}: leading digits {digits:?} do not parse ({e})"))?;
    let rest = re[digits.len()..].trim_start();
    let unit: String = rest.chars().take_while(|c| c.is_ascii_alphabetic()).collect();
    if unit.is_empty() {
        return Err(format!("{cell:?}: the number {n} carries no unit"));
    }
    Ok((n, unit))
}

/// `N/A` → `Ok(None)` · `60 s` / `5 min` / `10 min` / `1 h` → `Ok(Some(_))` ·
/// anything else → `Err`.
///
/// The `1 h` case is not hypothetical padding: it is exactly what `V1-F4(d)`
/// used. `DP-X7` caps overrides at one hour, so an hour is a *legal* unit to
/// write in this table and the old parser mapped it to `None` — making
/// "cached for an hour" and "not cached at all" indistinguishable, on the tier
/// whose whole point is that it is never cached.
fn parse_ttl(cell: &str) -> Result<Option<Duration>, String> {
    let c = cell.trim();
    if !c.chars().any(|ch| ch.is_ascii_digit()) {
        return if c.eq_ignore_ascii_case("n/a") {
            Ok(None)
        } else {
            Err(format!("{cell:?}: no digits, and not the literal `N/A`"))
        };
    }
    let digits: String = c.chars().take_while(|ch| ch.is_ascii_digit()).collect();
    let n: u64 = digits
        .parse()
        .map_err(|e| format!("{cell:?}: leading digits {digits:?} do not parse ({e})"))?;
    let rest = c[digits.len()..].trim();
    // Longest unit first: `ms` before `min` before `s`, or `5 min` reads as `5 m`.
    let secs = if rest.starts_with("ms") {
        return Err(format!("{cell:?}: a TTL in milliseconds is not a TTL this table states"));
    } else if rest.starts_with("min") {
        n * 60
    } else if rest.starts_with('h') {
        n * 3600
    } else if rest.starts_with('s') {
        n
    } else {
        return Err(format!("{cell:?}: unit {rest:?} is not one of s / min / h"));
    };
    Ok(Some(Duration::from_secs(secs)))
}

/// `5 000 / s` / `500 / s` → `Some(u32)`; `Unbounded (in-process)` → `None`.
///
/// **The denominator is checked.** `V2-F3`: this used to concatenate every
/// digit in the cell and never look at what it was divided by, so
/// `500 / s` → `500 / min` — a 60× cut to a LOCKED throughput ceiling — read
/// identically. `DP-S5` states a *per-second* rate; a cell denominated in
/// anything else is a different quantity.
fn parse_rate(cell: &str) -> Result<Option<u32>, String> {
    let has_digit = cell.chars().any(|c| c.is_ascii_digit());
    if !has_digit {
        return if cell.to_ascii_lowercase().contains("unbounded") {
            Ok(None)
        } else {
            Err(format!("{cell:?}: no digits, and it does not say `Unbounded`"))
        };
    }
    let (num, denom) = cell
        .split_once('/')
        .ok_or_else(|| format!("{cell:?}: a rate must be written `<n> / <unit>`"))?;
    // The spec uses a thin space as the thousands separator.
    let digits: String = num.chars().filter(|c| c.is_ascii_digit()).collect();
    let denom = denom.trim();
    if denom != "s" {
        return Err(format!(
            "{cell:?}: denominated in {denom:?}, but DP-S5 states a PER-SECOND rate. A cell in \
             another unit is a different quantity, not a smaller number"
        ));
    }
    digits
        .parse()
        .map(Some)
        .map_err(|e| format!("{cell:?}: digits {digits:?} do not parse ({e})"))
}

#[test]
fn write_ack_budgets_match_dp_s3() {
    let doc = dp_doc("08_scale_and_slos.md");
    let rows = table_cells(&doc, "## DP-S3", |l| l.starts_with("DP-T"));
    assert_eq!(rows.len(), 4, "DP-S3 must have one row per tier; parsed {rows:?}");

    let expected = [
        ("DP-T0", T0::WRITE_ACK_P99),
        ("DP-T1", T1::WRITE_ACK_P99),
        ("DP-T2", T2::WRITE_ACK_P99),
        ("DP-T3", T3::WRITE_ACK_P99),
    ];
    for (label, konst) in expected {
        let cell = &rows.iter().find(|(l, _)| l == label).expect("row").1;
        // The document is NAMED in the panic. A drift alarm that says only
        // "5 s is not milliseconds" leaves the reader hunting for which of the
        // twenty-five locked files it came from.
        let parsed = parse_ms(cell)
            .unwrap_or_else(|e| panic!("{label}: 08_scale_and_slos.md DP-S3 — {e}"));
        assert_eq!(
            parsed, konst,
            "{label}: 08_scale_and_slos.md DP-S3 says {cell:?} ({parsed:?}), tier.rs says {konst:?}"
        );
    }
}

/// `V1-F2` — **the closed set, with a subject that can actually vary.**
///
/// `measure.rs` used to assert `[T0,T1,T2,T3].len() == 4`. That array has four
/// elements because the test wrote four: `NV-1`, the subject cannot vary. Adding
/// a fifth in-crate tier left it green.
///
/// Here both sides move. The left is **parsed out of `tier.rs`'s own source** —
/// one `declare_tier!` invocation per tier — and the right out of
/// `03_tier_taxonomy.md`, the document whose status line reads *"LOCKED. Four
/// tiers, closed set."* Mint a fifth tier and the source side grows while the
/// doc side does not; delete a row from the matrix and the reverse. Neither
/// number is written in this file, which is the property the old assertion
/// lacked.
#[test]
fn the_tier_set_in_source_matches_the_taxonomy_doc() {
    let src = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/tier.rs"),
    )
    .expect("tier.rs");
    // The macro DEFINITION also contains the token, so count invocations only:
    // an invocation is followed by a name and a comma, the definition by `(`.
    // **Delimiter-agnostic (`R3-M2`).** `declare_tier!{..}` is the same
    // invocation as `declare_tier!(..)`, and matching only `declare_tier!(`
    // let a refuter mint a fifth tier — 24-hour TTL, `REC-102c` inverted — by
    // changing ONE character. It passed this test, its sibling below, the gate
    // and clippy. The `const` block did not see it either, because that block
    // sums four NAMED tiers (`R2-9`).
    let declared: Vec<String> = declared_tiers(&src);

    let doc = dp_doc("03_tier_taxonomy.md");
    let matrix: Vec<String> = table_cells(&doc, "## Tier matrix", |l| l.starts_with("**DP-T"))
        .into_iter()
        .map(|(label, _)| label.trim_matches('*').trim_start_matches("DP-").to_string())
        .collect();

    assert!(
        !declared.is_empty() && !matrix.is_empty(),
        "one side parsed EMPTY (source {declared:?}, doc {matrix:?}) — an empty comparison agrees \
         with anything, which is the failure this test is named after"
    );
    // Order-insensitive: `03`'s matrix is LABEL-keyed, so reordering its rows is
    // meaning-preserving and must not red. `V2-N11` — a check that fires on a
    // harmless edit teaches "the oracle is noisy", and that is how red becomes
    // the normal colour.
    let (mut d, mut x) = (declared.clone(), matrix.clone());
    d.sort();
    x.sort();
    assert_eq!(
        d, x,
        "the tiers declared in crates/dp/src/tier.rs ({declared:?}) are not the tiers in \
         03_tier_taxonomy.md's matrix ({matrix:?}). DP-A5 closes this set; adding to it requires \
         a superseding decision in docs/03_planning/LLM_MMO_RPG/decisions/, not a new macro call"
    );
}

/// `V2-F4` — **a tier is a type implementing `Tier`, not a macro invocation.**
///
/// The test above parses `declare_tier!` invocations and calls that "the source
/// side". A cold-start refuter hand-wrote the impl instead:
///
/// ```ignore
/// pub(crate) struct T1p5;
/// impl sealed::SealedTier for T1p5 {}
/// impl Tier for T1p5 { /* its own TTL, ack budget, throughput */ }
/// ```
///
/// A genuine fifth tier, with `cargo test`, `clippy`, `dp-aggregate-gate` and
/// the oracle **all green** — because none of them was looking at the thing
/// that makes a tier a tier. (The *public* case reds, but only incidentally:
/// trybuild's pinned `.stderr` happens to contain rustc's *"the following other
/// types implement trait `Tier`"* enumeration. A guarantee resting on a
/// compiler diagnostic's formatting is not a guarantee.)
///
/// So this reads the definition site directly. `declare_tier!` is the ONLY
/// sanctioned way to add a tier; any `impl Tier for _` or `impl SealedTier for
/// _` appearing outside the macro's own body is a tier the closed set does not
/// know about.
#[test]
fn no_tier_is_implemented_outside_the_declare_tier_macro() {
    let src = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/tier.rs"),
    )
    .expect("tier.rs");

    // The macro's own body legitimately contains both impls, once, with `$name`.
    let body_start = src.find("macro_rules! declare_tier").expect("the declare_tier macro");
    let body_end = src[body_start..]
        .find("\n}\n")
        .map(|i| body_start + i + 3)
        .expect("the macro body must be terminated by a line-initial `}`");

    let mut stray: Vec<(usize, String)> = Vec::new();
    for (i, line) in src.lines().enumerate() {
        let off = src.lines().take(i).map(|l| l.len() + 1).sum::<usize>();
        if off >= body_start && off < body_end {
            continue;
        }
        let t = line.trim();
        if t.starts_with("//") {
            continue;
        }
        for pat in ["impl Tier for ", "impl sealed::SealedTier for ", "impl SealedTier for "] {
            if t.contains(pat) {
                stray.push((i + 1, t.to_string()));
            }
        }
    }

    assert!(
        stray.is_empty(),
        "a tier is implemented outside `declare_tier!`, so it is NOT in the set every other check \
         reads: {stray:?}. DP-A5 closes the taxonomy at four; a fifth tier needs a superseding \
         decision, and if one is made it goes through the macro so that the doc oracle, the gate \
         and the const block all see it"
    );

    // ...and the check must have a subject: the macro body itself must contain
    // the two impls, or the search above is scanning for something that has
    // moved and would report clean forever.
    let body = &src[body_start..body_end];
    assert!(
        body.contains("impl Tier for $name") && body.contains("impl sealed::SealedTier for $name"),
        "the declare_tier! body no longer contains the impls this test searches for — the search \
         has lost its subject and would report clean whatever the file said"
    );
}

/// `G10` — **the corpus contains its own drift, and this oracle was built for
/// exactly that shape and was not looking at it.**
///
/// `DP-F7` Bucket 1 is a rate-limiter table headed *"Enforces `DP-S5`
/// ceilings"* — and it **restates `DP-S5`'s numbers** rather than referring to
/// them. Two copies of one set of figures, in two LOCKED documents, agreeing
/// today because nobody has edited either.
///
/// That is `FLOW-2` verbatim: *a document and a fact drifting apart with nothing
/// watching*. The whole reason this file exists is that no such alarm existed
/// while `17_game_data_architecture.md` decided four corrections to LOCKED
/// data-plane files and none were applied. Every other test here compares a
/// **document to code**; this is the first that compares a **document to a
/// document**, and the corpus needed it more than the code did.
///
/// Only rows present in BOTH tables are compared. `T0` has no bucket — it is
/// `Unbounded (in-process)` in `DP-S5` and absent from `DP-F7` — and that
/// asymmetry is correct, not drift.
#[test]
fn dp_f7_rate_limits_match_dp_s5_ceilings() {
    let slos = dp_doc("08_scale_and_slos.md");
    let failure = dp_doc("07_failure_and_recovery.md");

    // Bound the section explicitly: `table_cells` stops at the next `## `, and
    // Bucket 2 is a `### `, so the default heuristic would read straight through
    // three more tables.
    let b1 = failure.find("### Bucket 1").expect("DP-F7's Bucket 1");
    let b2 = failure[b1..].find("### Bucket 2").map(|i| b1 + i).unwrap_or(failure.len());
    let bucket1 = &failure[b1..b2];

    let ceilings = table_cells(&slos, "## DP-S5", |l| !l.is_empty() && l != "Tier");
    let buckets = table_cells(bucket1, "### Bucket 1", |l| !l.is_empty() && l != "Tier");

    let mut compared = 0usize;
    for (label, bucket_cell) in &buckets {
        let Some((_, slo_cell)) = ceilings.iter().find(|(l, _)| l == label) else {
            continue;
        };
        let want = parse_rate(slo_cell)
            .unwrap_or_else(|e| panic!("08_scale_and_slos.md DP-S5 {label}: {e}"));
        let got = parse_rate(bucket_cell)
            .unwrap_or_else(|e| panic!("07_failure_and_recovery.md DP-F7 {label}: {e}"));
        assert_eq!(
            got, want,
            "{label}: 07_failure_and_recovery.md DP-F7 Bucket 1 says {bucket_cell:?} and \
             08_scale_and_slos.md DP-S5 says {slo_cell:?}. Bucket 1's own header reads \"Enforces \
             DP-S5 ceilings\" — a rate limiter that does not enforce the ceiling it names either \
             throttles healthy traffic or lets the ceiling be exceeded, and which one is a coin \
             flip on the direction of the drift"
        );
        compared += 1;
    }

    assert!(
        compared >= 3,
        "only {compared} row(s) matched between DP-S5 and DP-F7 Bucket 1 — the parse found \
         DP-S5 {ceilings:?} and Bucket 1 {buckets:?}. A cross-check that compares nothing agrees \
         with anything, and this one exists because the two tables can drift silently"
    );
}

/// `G3` — **`02_invariants.md` holds the authority this crate cites, and
/// nothing opened it.**
///
/// A completeness pass measured that **22 of the 26 LOCKED documents** are read
/// by no test and no gate — including this one, which defines `DP-A5`,
/// `DP-A9` and `DP-A14`: the three invariants the seal, the `const _` block and
/// the aggregate contract all name as the reason they exist. The oracle parsed
/// the documents that carry *numbers* and skipped the one that carries the
/// *rules*, which is the wrong way round for a closed-set claim.
///
/// `DP-A5`'s rule is a four-bullet list, one per tier, in the form
/// `**DP-T0 Ephemeral** — …`. That is as parseable as any table.
#[test]
fn the_tier_set_matches_dp_a5() {
    let doc = dp_doc("02_invariants.md");
    let start = doc.find("## DP-A5").expect("DP-A5 is not in 02_invariants.md");
    let body = &doc[start..];
    let end = body[8..].find("\n## ").map(|i| i + 8).unwrap_or(body.len());

    let mut from_doc: Vec<String> = body[..end]
        .lines()
        .filter_map(|l| l.trim().strip_prefix("- **DP-T"))
        .filter_map(|rest| {
            let n = rest.chars().next()?;
            n.is_ascii_digit().then(|| format!("T{n}"))
        })
        .collect();

    let src = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/tier.rs"),
    )
    .expect("tier.rs");
    let mut from_src = declared_tiers(&src);

    assert!(
        !from_doc.is_empty(),
        "DP-A5's `- **DP-Tn ..**` bullet list did not parse — the rule's shape moved, and a \
         comparison against nothing agrees with anything"
    );
    from_doc.sort();
    from_src.sort();
    assert_eq!(
        from_src, from_doc,
        "crates/dp/src/tier.rs declares {from_src:?}; 02_invariants.md DP-A5 — the invariant the \
         seal cites as its authority — enumerates {from_doc:?}"
    );
}

/// `G3`, second half — **`as_key()` was pinned only against itself.**
///
/// `TierLevel::as_key` and `ScopeKind::as_key` produce the tokens of the
/// `DP-Ch5` cache key. `V2-F6` pinned all four tier keys and `G9` all four scope
/// forms — but every one of those assertions is a *second hand-written table*,
/// which this file's own docstring calls *"the same act done twice"*. The
/// template they implement lives in `12_channel_primitives.md` and was never
/// opened.
///
/// This parses the two key templates and the worked example beside them, so the
/// `r`/`c` markers and the lowercase tier token are compared against the
/// document that defines them rather than against a copy of themselves.
#[test]
fn cache_key_tokens_match_dp_ch5() {
    let doc = dp_doc("12_channel_primitives.md");

    let reality = doc
        .lines()
        .find(|l| l.contains("Reality-scoped:") && l.contains("dp:{"))
        .expect("12_channel_primitives.md: DP-Ch5's reality-scoped key template");
    let channel = doc
        .lines()
        .find(|l| l.contains("Channel-scoped:") && l.contains("dp:{"))
        .expect("12_channel_primitives.md: DP-Ch5's channel-scoped key template");

    // Position 2 of the key — `dp:{reality_id}:<marker>:…` — is the scope token.
    let marker_of = |line: &str| -> String {
        line.split("dp:")
            .nth(1)
            .and_then(|k| k.split(':').nth(1))
            .unwrap_or("")
            .trim()
            .to_string()
    };
    assert_eq!(
        marker_of(reality),
        ScopeKind::Reality.as_key(),
        "12_channel_primitives.md DP-Ch5's reality template is {reality:?}; scope.rs's \
         ScopeKind::Reality.as_key() is {:?}",
        ScopeKind::Reality.as_key()
    );
    assert_eq!(
        marker_of(channel),
        ScopeKind::Channel.as_key(),
        "12_channel_primitives.md DP-Ch5's channel template is {channel:?}; scope.rs's \
         ScopeKind::Channel.as_key() is {:?}",
        ScopeKind::Channel.as_key()
    );

    // The worked example beside the template spells a tier token literally.
    let example = doc
        .lines()
        .find(|l| l.contains("\"dp:{reality}:r:") && l.contains("RealityScoped"))
        .expect("12_channel_primitives.md: DP-Ch5's worked reality-scoped example");
    let tier_token = example
        .split("\"dp:{reality}:r:")
        .nth(1)
        .and_then(|r| r.split(':').next())
        .expect("the tier token in DP-Ch5's example");
    assert_eq!(
        tier_token,
        TierLevel::T2.as_key(),
        "12_channel_primitives.md DP-Ch5's example key uses the tier token {tier_token:?}; \
         tier.rs's TierLevel::T2.as_key() is {:?}. \
         These are the same token in the same key, and until now each was checked only against a \
         copy of itself",
        TierLevel::T2.as_key()
    );
}

/// `G1` — **the same check for scopes, which did not have one.**
///
/// This is the gap a completeness pass found after two rounds of refutation had
/// closed everything either of them could break. `DP-A14` closes the scope set
/// at two exactly as `DP-A5` closes the tier set at four, and `V2-F4` gave the
/// tier set a door and a check — while the scope set was still hand-written.
///
/// The consequence was not "the gate misses a third scope". It is worse:
/// `dp-aggregate-gate` learns the legal scope names **by parsing this file**, so
/// writing `impl Scope for ZoneScope` makes `ZoneScope` legal, and the gate
/// reports `OK` while printing the widened set as though it were the taxonomy.
/// A check that reads its rule out of the file the violation is written in is
/// not a check — it is `BDR-36`, one file over from where it was found.
#[test]
fn no_scope_is_implemented_outside_the_declare_scope_macro() {
    let src = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/scope.rs"),
    )
    .expect("scope.rs");

    let body_start = src.find("macro_rules! declare_scope").expect("the declare_scope macro");
    let body_end = src[body_start..]
        .find("\n}\n")
        .map(|i| body_start + i + 3)
        .expect("the macro body must be terminated by a line-initial `}`");

    let mut stray: Vec<(usize, String)> = Vec::new();
    for (i, line) in src.lines().enumerate() {
        let off = src.lines().take(i).map(|l| l.len() + 1).sum::<usize>();
        if off >= body_start && off < body_end {
            continue;
        }
        let t = line.trim();
        if t.starts_with("//") {
            continue;
        }
        for pat in ["impl Scope for ", "impl sealed::SealedScope for ", "impl SealedScope for "] {
            if t.contains(pat) {
                stray.push((i + 1, t.to_string()));
            }
        }
    }

    assert!(
        stray.is_empty(),
        "a scope is implemented outside `declare_scope!`, so it is NOT in the set every other \
         check reads — and `dp-aggregate-gate` parses THIS FILE for its legal names, so the new \
         scope would be legal by existing: {stray:?}. DP-A14 closes the set at two"
    );

    let body = &src[body_start..body_end];
    assert!(
        body.contains("impl Scope for $name")
            && body.contains("impl sealed::SealedScope for $name"),
        "the declare_scope! body no longer contains the impls this test searches for — the search \
         has lost its subject and would report clean whatever the file said"
    );
}

#[test]
fn cache_ttls_match_dp_x7() {
    let doc = dp_doc("06_cache_coherency.md");
    let rows = table_cells(&doc, "## DP-X7", |l| matches!(l, "T0" | "T1" | "T2" | "T3"));
    assert_eq!(rows.len(), 4, "DP-X7 must have one row per tier; parsed {rows:?}");

    for (label, konst) in [
        ("T0", T0::CACHE_TTL),
        ("T1", T1::CACHE_TTL),
        ("T2", T2::CACHE_TTL),
        ("T3", T3::CACHE_TTL),
    ] {
        let cell = &rows.iter().find(|(l, _)| l == label).expect("row").1;
        let parsed = parse_ttl(cell).unwrap_or_else(|e| panic!("{label}: {e}"));
        assert_eq!(
            parsed, konst,
            "{label}: 06_cache_coherency.md DP-X7 says {cell:?} ({parsed:?}), tier.rs says {konst:?}"
        );
    }
}

/// `V1-F4(b)` — **`DP-X1` is a table, not prose.**
///
/// The previous docstring excused `Coherency` from the oracle by calling it
/// prose. It is a four-row markdown table that the helper above already parses,
/// and it was the only field of a tier with nothing watching it. `DP-X1`'s own
/// closing line is *"the model is the contract"*; a contract nothing reads is a
/// note.
#[test]
fn coherency_models_match_dp_x1() {
    let doc = dp_doc("06_cache_coherency.md");
    let rows = table_cells(&doc, "## DP-X1", |l| {
        matches!(l.trim_matches('*'), "T0" | "T1" | "T2" | "T3")
    });
    assert_eq!(rows.len(), 4, "DP-X1 must have one row per tier; parsed {rows:?}");

    for (label, konst) in [
        ("T0", T0::COHERENCY),
        ("T1", T1::COHERENCY),
        ("T2", T2::COHERENCY),
        ("T3", T3::COHERENCY),
    ] {
        let cell = &rows
            .iter()
            .find(|(l, _)| l.trim_matches('*') == label)
            .expect("row")
            .1;
        assert_eq!(
            cell.as_str(),
            konst.doc_phrase(),
            "{label}: 06_cache_coherency.md DP-X1 says {cell:?}, and tier.rs's \
             {konst:?}.doc_phrase() says {:?}",
            konst.doc_phrase()
        );
    }
}

/// `V1-F4(c)` — **`REC-102c` gets a real oracle, not a second copy of itself.**
///
/// `SURVIVES_STORE_OUTAGE` is the one genuinely new decision in this crate, and
/// it was the one thing with no independent check: the unit test guarding it was
/// another hand-written table listing the same four booleans. This reads the
/// verdict out of the amendment table in `DP-F5`, where the PO approved it.
///
/// The table is inside a blockquote and groups three tiers into one row, so the
/// parse is by tier TOKEN rather than by row label — and every tier must be
/// found exactly once, or the grouping changed underneath the check.
#[test]
fn survives_store_outage_matches_rec_102c() {
    let doc = dp_doc("07_failure_and_recovery.md");
    let start = doc.find("REC-102c").expect("REC-102c is not in 07_failure_and_recovery.md");

    let mut verdict: Vec<(String, bool)> = Vec::new();
    for line in doc[start..].lines() {
        let l = line.trim_start().trim_start_matches('>').trim();
        if !l.starts_with('|') {
            continue;
        }
        let cells: Vec<&str> = l.split('|').map(str::trim).collect();
        if cells.len() < 3 {
            continue;
        }
        let label = cells[1];
        // The verdict is the cell's **bolded lead**, not any occurrence of the
        // word in the paragraph that follows it. Scanning the whole cell was the
        // first implementation and it FAILED here, correctly: T3's row reads
        // "**REJECT — unchanged.** … a *buffered* T3 is an ack for a promise not
        // kept", so both words appear and only the lead says which one is the
        // ruling. A check that had guessed between them would have been deciding
        // the thing it is supposed to be reading.
        let Some(lead) = cells[2]
            .strip_prefix("**")
            .and_then(|r| r.split_once("**"))
            .map(|(l, _)| l.to_ascii_uppercase())
        else {
            // The header row and the `|---|---|` separator have no bolded lead.
            continue;
        };
        let buffers = match (lead.contains("BUFFER"), lead.contains("REJECT")) {
            (true, false) => true,
            (false, true) => false,
            _ => panic!(
                "REC-102c row {label:?}: the verdict {lead:?} says both BUFFER and REJECT, or \
                 neither. It must say exactly one — that partition IS the decision"
            ),
        };
        for tok in ["T0", "T1", "T2", "T3"] {
            if label.contains(tok) {
                verdict.push((tok.to_string(), buffers));
            }
        }
    }

    verdict.sort();
    let tiers: Vec<&str> = verdict.iter().map(|(t, _)| t.as_str()).collect();
    assert_eq!(
        tiers,
        ["T0", "T1", "T2", "T3"],
        "REC-102c's table must give a verdict for each tier exactly once; parsed {verdict:?}"
    );

    for (label, konst) in [
        ("T0", T0::SURVIVES_STORE_OUTAGE),
        ("T1", T1::SURVIVES_STORE_OUTAGE),
        ("T2", T2::SURVIVES_STORE_OUTAGE),
        ("T3", T3::SURVIVES_STORE_OUTAGE),
    ] {
        let doc_says = verdict.iter().find(|(t, _)| t == label).expect("tier").1;
        assert_eq!(
            doc_says, konst,
            "{label}: 07_failure_and_recovery.md REC-102c says buffer={doc_says}, tier.rs says \
             SURVIVES_STORE_OUTAGE={konst}. This is the PO-approved degraded-mode partition — the \
             document and the constant disagreeing means one of them was changed alone"
        );
    }
}

#[test]
fn sustained_write_ceilings_match_dp_s5() {
    let doc = dp_doc("08_scale_and_slos.md");
    let rows = table_cells(&doc, "## DP-S5", |l| l.ends_with("writes"));
    assert_eq!(rows.len(), 4, "DP-S5 must have one write row per tier; parsed {rows:?}");

    for (label, konst) in [
        ("T0 writes", T0::SUSTAINED_WRITES_PER_S),
        ("T1 writes", T1::SUSTAINED_WRITES_PER_S),
        ("T2 writes", T2::SUSTAINED_WRITES_PER_S),
        ("T3 writes", T3::SUSTAINED_WRITES_PER_S),
    ] {
        let cell = &rows.iter().find(|(l, _)| l == label).expect("row").1;
        // T0 is "Unbounded (in-process)" — no digits, and the const is None.
        let parsed = parse_rate(cell).unwrap_or_else(|e| panic!("{label}: {e}"));
        assert_eq!(
            parsed, konst,
            "{label}: 08_scale_and_slos.md DP-S5 says {cell:?} ({parsed:?}), tier.rs says {konst:?}"
        );
    }
}

/// The oracle's own non-vacuity guard. If a section heading is renamed the
/// parser silently returns an empty vec, and three tests comparing nothing to
/// nothing would pass. `NV-3` at the oracle's own scope: assert the parse found
/// the rows it claims to compare.
#[test]
fn the_parser_must_actually_find_something() {
    let slos = dp_doc("08_scale_and_slos.md");
    let coherency = dp_doc("06_cache_coherency.md");
    assert!(!table_cells(&slos, "## DP-S3", |l| l.starts_with("DP-T")).is_empty());
    assert!(!table_cells(&slos, "## DP-S5", |l| l.ends_with("writes")).is_empty());
    assert!(!table_cells(&coherency, "## DP-X7", |l| l.len() == 2).is_empty());
    // And the numbers must differ across tiers — a parser returning one value
    // four times would satisfy every equality above if the consts were wrong
    // in the same way.
    let acks = table_cells(&slos, "## DP-S3", |l| l.starts_with("DP-T"));
    let distinct: std::collections::HashSet<_> = acks.iter().map(|(_, c)| c).collect();
    assert_eq!(distinct.len(), 4, "four tiers must have four distinct ack budgets");
}
