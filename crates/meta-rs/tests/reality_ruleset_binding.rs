//! Q1 B2 — the Rust half of a POLYGLOT contract check.
//!
//! `contracts/meta/events_allowlist.yaml` is parsed by two independently
//! written parsers: `contracts/meta/allowlist.go` and this crate's
//! `src/allowlist.rs`. They read the SAME bytes, so a disagreement can only
//! come from a parser difference — an enum spelling, a defaulted field, an
//! entry silently skipped. The mirror of this file is
//! `contracts/meta/allowlist_ruleset_binding_test.go`, asserting the identical
//! facts. If one parser drops the row and the other does not, exactly one side
//! reds, which is the signal wanted.
//!
//! Why this table matters enough to check twice: `MetaWrite` refuses any table
//! not in the allowlist *before SQL runs*. A row that parses in Go and not in
//! Rust means reality creation works from the Go services and fails from the
//! Rust ones, with a "table not allowlisted" error naming a table that is
//! plainly right there in the file.

use meta_rs::{Allowlist, MetaWriteOp};

const ALLOWLIST: &str = "../../contracts/meta/events_allowlist.yaml";
const TABLE: &str = "reality_ruleset_binding";

fn shipped() -> Allowlist {
    Allowlist::load(ALLOWLIST).expect("the shipped allowlist must parse")
}

#[test]
fn the_binding_table_is_allowlisted() {
    assert!(
        shipped().allows_table(TABLE),
        "{TABLE} is not allowlisted, so MetaWrite would refuse every binding \
         write and a reality could not be created at all"
    );
}

#[test]
fn an_insert_emits_the_bound_event() {
    assert_eq!(
        shipped().emits_event(TABLE, MetaWriteOp::Insert),
        Some("reality.ruleset.bound"),
        "binding a reality to its rules is exactly the kind of fact other \
         services subscribe to"
    );
}

/// The table is append-only in the DB — migration 033's trigger refuses UPDATE
/// and DELETE for every role, including the superuser a migration runs as.
/// Declaring an event for either op would advertise a write that cannot happen.
#[test]
fn no_event_is_declared_for_an_operation_the_table_refuses() {
    let a = shipped();
    for op in [MetaWriteOp::Update, MetaWriteOp::Delete] {
        assert_eq!(
            a.emits_event(TABLE, op),
            None,
            "{TABLE} declares an event for {op:?}, but migration 033 refuses \
             that operation"
        );
    }
}

/// Negative control for the three above. Without it they would all still pass
/// against a parser that answered "yes, allowlisted" and "no event" for every
/// input it was ever given — which is the shape a silently-empty parse takes.
#[test]
fn the_parser_is_not_answering_yes_to_everything() {
    let a = shipped();
    assert!(
        !a.allows_table("reality_ruleset_binding_typo"),
        "a table that is NOT in the file must be refused, or `allows_table` \
         proves nothing about the one that is"
    );
    assert_eq!(
        a.emits_event("instance_schema_migrations", MetaWriteOp::Insert),
        None,
        "a table declared with `events: []` must emit nothing"
    );
    assert_eq!(
        a.emits_event("reality_registry", MetaWriteOp::Insert),
        Some("reality.created"),
        "…while a sibling row with a real event still resolves, so `None` \
         above is a parsed fact and not a parse failure"
    );
}

/// **`xreality_topic` is part of the SoT and the Rust parser silently dropped
/// it.** `contracts/meta/allowlist.go` has read this field since the file was
/// written; `EventBinding` here had no such field, and serde ignores unknown
/// fields by default — so the two mirrors parsed the same bytes and disagreed
/// about what was in them, with nothing failing on either side.
///
/// The consequence was invisible by construction: a Rust service writing a
/// table whose event declares a topic would insert a `meta_outbox` row with
/// `xreality_topic` NULL, the relay would forward it to the normal stream, and
/// the cross-reality consumer would just stop receiving. No error, anywhere.
///
/// `pii_kek` is the one entry in the shipped SoT that declares a topic, so it
/// is the only input that can prove the field survives the parse.
#[test]
fn a_declared_xreality_topic_survives_the_rust_parser() {
    let a = shipped();
    assert_eq!(
        a.xreality_topic("user.erased"),
        Some("xreality.user.erased"),
        "the Rust mirror must see the same cross-reality topic Go's \
         LoadXRealityTopics sees"
    );
    assert_eq!(
        a.xreality_topic("reality.ruleset.bound"),
        None,
        "…and an event with no declared topic must resolve to None rather than \
         to some default, or every event would look cross-reality"
    );
}
