//! `DFO-5` — every field `recovery::WriterRecovery` produces is CONSUMED by the spine.
//!
//! # The bug this exists to stop happening again, which already happened once
//!
//! `recovery::WriterRecovery::turn_number` was added specifically to fix a restart
//! rewinding the channel's turn counter. Its own doc comment says so, in the
//! past tense: *"spine seeded it to 0 on every start, so a restart silently
//! rewound the turn number and every client's `turn_number` went backwards …
//! so it is fixed here rather than left as a known-broken sibling."*
//!
//! It was queried from the database, returned, **printed** — and then
//! `bin/spine.rs` went on seeding `turn_number: u64 = 0`. The producer landed,
//! the consumer did not, and the defect survived the commit that claimed to
//! have fixed it. Its sibling one line up, `aggregate_version`, was wired
//! correctly, so the two adjacent decisions disagreed in a diff nobody re-read.
//!
//! That is not a testing gap in the ordinary sense: every unit test passed,
//! because a value that is computed and dropped breaks nothing locally. What it
//! breaks is one process restart away, and
//! `game-server/src/wire/turnOutcome.ts` calls the resulting number
//! *"authoritative from the COMMIT — never recomputed here"* before rendering
//! it.
//!
//! # Why a SOURCE assertion rather than a behavioural test
//!
//! The seeding happens in a `main()` that needs Postgres, Redis, a bound
//! reality and a writer lease before it reaches the line in question. A test
//! that stood all that up would prove more, and it would also be the kind of
//! test that gets `#[ignore]`d and stops running — this repo has the receipts.
//!
//! This one is cheap, always runs, and fails for exactly one reason: a field
//! `Recovered` hands out stopped being used. It cannot prove the seeding is
//! CORRECT; it proves the value is not silently dropped, which is the specific
//! failure that happened. Stated rather than dressed up: it is a narrow check
//! for a narrow, recurring defect.

use std::path::Path;

/// Read a source file with comments stripped.
///
/// Existence measured on CODE, not on prose — `§0.5`'s rule, and the reason it
/// is not optional here: the whole bug was a value that appeared in a
/// `println!` and a doc comment while being absent from the assignment. A check
/// that counted those would have passed on the broken tree.
fn code_only(path: &Path) -> String {
    let raw = std::fs::read_to_string(path).unwrap_or_else(|e| panic!("read {path:?}: {e}"));
    raw.lines()
        .map(|l| {
            let t = l.trim_start();
            if t.starts_with("//") {
                ""
            } else {
                l
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn every_recovered_field_is_read_by_the_spine() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let recovery = code_only(&root.join("src/recovery.rs"));
    let spine = code_only(&root.join("src/bin/spine.rs"));

    // The producer's public fields, parsed from the struct rather than listed
    // here: a hand-written list is a second place to forget a field, which is
    // the defect's own shape.
    let start = recovery
        .find("pub struct WriterRecovery {")
        .expect("recovery::WriterRecovery is gone — this test's subject no longer exists");
    let body = &recovery[start..];
    let end = body.find("\n}").expect("unterminated struct WriterRecovery");
    let fields: Vec<&str> = body[..end]
        .lines()
        // Skip the declaration line itself: `pub struct WriterRecovery {` also
        // begins `pub `, and taking it produced a phantom "field" named
        // `struct WriterRecovery {` that the spine can obviously never read.
        // The check then reported a real-looking failure about a thing that
        // does not exist — a string that looks like a subject, inside the test
        // written to catch exactly that. Requiring a `:` is the second guard.
        .skip(1)
        .map(str::trim)
        .filter_map(|l| l.strip_prefix("pub "))
        .filter(|l| l.contains(':'))
        .filter_map(|l| l.split(':').next())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect();

    assert!(
        fields.len() >= 3,
        "expected at least the three fields WriterRecovery was built to carry, found {fields:?} — \
         if the struct shrank, this test is checking almost nothing"
    );

    // A field is CONSUMED when it is read somewhere that is not a `println!`.
    // The bug was precisely a field that appeared only in one.
    let mut dropped = Vec::new();
    for f in &fields {
        let needle = format!("recovered.{f}");
        let used_at_all = spine.contains(&needle);
        let used_outside_println = spine
            .lines()
            .filter(|l| l.contains(&needle))
            .any(|l| !l.contains("println!") && !l.trim().starts_with("recovered."));
        // `println!("{}", recovered.x)` spans lines, so also accept a read on a
        // line whose statement is an assignment or a call argument.
        let assigned = spine
            .lines()
            .any(|l| l.contains(&needle) && (l.contains('=') || l.contains("seed")));
        if !used_at_all || !(used_outside_println || assigned) {
            dropped.push(*f);
        }
    }

    assert!(
        dropped.is_empty(),
        "recovery::WriterRecovery produces {dropped:?}, and bin/spine.rs never READS \
         {}. A recovered value that is computed and dropped is not a fix — it is a \
         producer with no consumer, which is exactly how `turn_number` shipped: \
         queried from the DB, printed, and then overwritten with 0 on the next line.",
        if dropped.len() == 1 { "it" } else { "them" }
    );
}
