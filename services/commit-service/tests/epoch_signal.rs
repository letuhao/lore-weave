//! `Q0b B3b/B3c` — the parts of the epoch path that need no I/O.
//!
//! The signal parsing, the `authorised_by` composition and the committed
//! payload's shape are all decidable from bytes, and they are where the
//! cross-service mistakes live: a stream field renamed, a composite key spelled
//! differently on two sides, a payload key that drifts from the Go contract. The
//! live path (real Postgres + real Redis) is `epoch_activation_live.rs`.

use commit_service::bus::BusMessage;
use commit_service::epoch_signal::{
    authorised_by, is_malformed_for_us, parse_binding_signal, signal_group, BINDING_EVENT,
};

const REALITY: &str = "11111111-1111-4111-8111-111111111111";
const OTHER: &str = "22222222-2222-4222-8222-222222222222";

/// Exactly what `meta-outbox-relay`'s `redisemit.xadd` writes to the home
/// stream: the generic envelope, payload passed through as the raw jsonb bytes
/// `meta_write` built.
fn entry(event_name: &str, reality: &str, epoch: u32) -> BusMessage {
    let payload = serde_json::json!({
        "table": "reality_ruleset_binding",
        "operation": "INSERT",
        "pk": { "epoch": epoch, "reality_id": reality },
        "after": { "ruleset_digest": "a".repeat(64), "reason": "rules updated" },
    });
    BusMessage {
        id: "1700000000000-0".into(),
        fields: vec![
            ("event_id".into(), "33333333-3333-4333-8333-333333333333".into()),
            ("event_name".into(), event_name.into()),
            ("aggregate_id".into(), format!("epoch={epoch}|reality_id={reality}")),
            ("payload".into(), payload.to_string()),
            ("recorded_at_nanos".into(), "1700000000000000000".into()),
        ],
    }
}

#[test]
fn a_binding_event_for_this_reality_is_recognised() {
    let sig = parse_binding_signal(&entry(BINDING_EVENT, REALITY, 4), REALITY)
        .expect("a well-formed bound event for our reality must parse");
    assert_eq!(sig.reality_id, REALITY);
    assert_eq!(sig.epoch, 4);
}

/// `lw.meta.events` carries EVERY meta write in the deployment. Another table's
/// event must not be read as ours.
#[test]
fn another_events_name_is_not_ours() {
    assert!(parse_binding_signal(&entry("reality.created", REALITY, 1), REALITY).is_none());
}

/// One stream, many realities. This is the filter that keeps a node from
/// switching because a DIFFERENT reality's rules changed — which would move it
/// onto an epoch its own binding table never authorised.
#[test]
fn another_realitys_binding_is_not_ours() {
    assert!(parse_binding_signal(&entry(BINDING_EVENT, OTHER, 7), REALITY).is_none());
}

/// The epoch arrives as a JSON NUMBER, because `meta_write` puts it in the
/// payload as `Value::from(u32)` and the relay passes the jsonb through without
/// re-marshalling. A string parse would work today only if someone quoted it.
#[test]
fn a_quoted_epoch_is_not_silently_accepted() {
    let mut m = entry(BINDING_EVENT, REALITY, 4);
    let payload = serde_json::json!({
        "pk": { "epoch": "4", "reality_id": REALITY },
    });
    m.fields.retain(|(k, _)| k != "payload");
    m.fields.push(("payload".into(), payload.to_string()));
    assert!(
        parse_binding_signal(&m, REALITY).is_none(),
        "a string epoch must not parse — if the wire type ever changes, this \
         test is the notification"
    );
}

// ── the ack-vs-dead-letter split ──────────────────────────────────────────
//
// `parse_binding_signal` returns `None` for three different situations and the
// caller treats two of them as "ack, not our business". The third — OUR event,
// broken — must reach a human. These two tests are the discriminator.

#[test]
fn our_own_malformed_binding_event_is_flagged() {
    let mut m = entry(BINDING_EVENT, REALITY, 4);
    m.fields.retain(|(k, _)| k != "payload");
    m.fields.push(("payload".into(), "{not json".into()));
    assert!(
        is_malformed_for_us(&m, REALITY),
        "an unparseable bound event whose aggregate_id names US is a defect, \
         and acking it would discard the only evidence"
    );
}

#[test]
fn someone_elses_malformed_event_is_not_our_problem() {
    let mut m = entry(BINDING_EVENT, OTHER, 4);
    m.fields.retain(|(k, _)| k != "payload");
    m.fields.push(("payload".into(), "{not json".into()));
    assert!(
        !is_malformed_for_us(&m, REALITY),
        "dead-lettering other realities' broken events would fill the dead \
         stream with traffic this node has no business judging"
    );
}

#[test]
fn a_healthy_event_is_never_flagged_as_malformed() {
    assert!(!is_malformed_for_us(&entry(BINDING_EVENT, REALITY, 4), REALITY));
}

// ── the composite key ─────────────────────────────────────────────────────

/// `authorised_by` must equal the `aggregate_id` the meta layer stamps on the
/// very same row, or the audit join an operator performs returns NO ROWS — and
/// a missing match reads as *"no such authorisation"* rather than as a bug.
///
/// The exact spelling (`epoch=N|reality_id=…`, sorted by column name) is pinned
/// against a live Postgres write in `crates/meta-rs/tests/pg_live.rs`.
#[test]
fn authorised_by_is_the_binding_rows_aggregate_id() {
    let m = entry(BINDING_EVENT, REALITY, 4);
    assert_eq!(
        authorised_by(REALITY, 4),
        m.field("aggregate_id").unwrap(),
        "the committed event's authorised_by and the meta event's aggregate_id \
         are the same primary key and must render identically"
    );
    assert_eq!(authorised_by(REALITY, 4), format!("epoch=4|reality_id={REALITY}"));
}

// ── the consumer group ────────────────────────────────────────────────────

/// **The load-bearing one.** A consumer group SPLITS work between its members.
/// Two channels of one reality sharing a group would each receive a different
/// subset of the binding events, and the channel that did not get the entry
/// would never switch — half the reality on stale rules, with no error anywhere.
#[test]
fn every_channel_gets_its_own_group() {
    assert_ne!(
        signal_group(REALITY, 1),
        signal_group(REALITY, 2),
        "two channels sharing a consumer group would split the binding events \
         between them and one of them would silently never switch"
    );
}

#[test]
fn every_reality_gets_its_own_group() {
    assert_ne!(signal_group(REALITY, 1), signal_group(OTHER, 1));
}
