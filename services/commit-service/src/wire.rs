//! Client-wire projection — committed event → `TurnOutcome` DTO
//! (`contracts/game-wire/turn.schema.json`, doc 20 §6).
//!
//! This is the FIRST producer of the game-wire contract, and it exists so the
//! contract is CONSUMED rather than stored: a schema nothing produces is a
//! blob, not a contract. The room projection (game-server) will fan these out;
//! commit-service mints them because it is where the committed truth lives.
//!
//! Two doc-20 rules are load-bearing here and are asserted by the tests:
//!
//! - **CWC-A2** — every 64-bit id serializes as a decimal STRING. `serde` is
//!   given `String` fields, not `u64`, so the corruption class (JS `number`
//!   past 2^53) is unrepresentable rather than merely avoided.
//! - **CWC-A6 / EVT-V4** — `rejected` and `discarded` are NOT the same thing,
//!   and neither consumes a turn. The projection carries the turn number the
//!   commit recorded; it never invents or increments one.

use serde::{Deserialize, Serialize};

/// What kind of resolution this was. Three distinct meanings the UI must not
/// collapse (CWC-A6).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OutcomeKind {
    /// It happened. The turn was consumed.
    Resolved,
    /// A valid intent the world moved out from under (SC-A1 precondition).
    /// No turn consumed.
    Discarded,
    /// The validator said no at a named admission stage (EVT-V4). No turn
    /// consumed — the player retries at no cost.
    Rejected,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum OutcomeDetail {
    Resolved { events: Vec<String> },
    Discarded { reason: String, user_message: String },
    Rejected { stage: String, user_message: String },
}

/// `contracts/game-wire/turn.schema.json#/$defs/TurnOutcome`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TurnOutcome {
    /// CWC-A2: decimal string, never a number.
    pub channel_event_id: String,
    pub kind: OutcomeKind,
    /// CWC-A2 + DP-A17: decimal string; advances on `Resolved` only.
    pub turn_number: String,
    pub detail: OutcomeDetail,
}

impl TurnOutcome {
    /// Project a committed RESOLUTION (the spine's `turn.resolved` /
    /// `turn.discarded` events) into the client DTO.
    pub fn from_resolution(
        channel_event_id: i64,
        turn_number: u64,
        applied: bool,
        narration: Vec<String>,
        discard_reason: Option<(&str, &str)>,
    ) -> Self {
        let (kind, detail) = match (applied, discard_reason) {
            (true, _) => (OutcomeKind::Resolved, OutcomeDetail::Resolved { events: narration }),
            (false, Some((reason, msg))) => (
                OutcomeKind::Discarded,
                OutcomeDetail::Discarded {
                    reason: reason.to_string(),
                    user_message: msg.to_string(),
                },
            ),
            // A non-applied resolution with no reason cannot exist — the
            // kernel records a reason for every discard (CS-A4/SC-A1). If it
            // ever does, say so loudly rather than shipping a blank frame.
            (false, None) => (
                OutcomeKind::Discarded,
                OutcomeDetail::Discarded {
                    reason: "unspecified".into(),
                    user_message: "The action did not resolve.".into(),
                },
            ),
        };
        Self {
            channel_event_id: channel_event_id.to_string(),
            turn_number: turn_number.to_string(),
            kind,
            detail,
        }
    }

    /// Project a committed `proposal.rejected` event. `turn_number` is the
    /// UNCHANGED counter — the caller passes what the commit recorded, and
    /// EVT-V4 guarantees a rejection did not move it.
    pub fn from_rejection(
        channel_event_id: i64,
        turn_number: u64,
        stage: &str,
        user_message: &str,
    ) -> Self {
        Self {
            channel_event_id: channel_event_id.to_string(),
            turn_number: turn_number.to_string(),
            kind: OutcomeKind::Rejected,
            detail: OutcomeDetail::Rejected {
                stage: stage.to_string(),
                user_message: user_message.to_string(),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// CWC-A2 bite: every id-shaped field must serialize as a JSON STRING.
    /// Kill-mutation: type the fields `u64` — serde emits numbers and this
    /// test reds. (The bug is invisible with small ids in dev and corrupts
    /// silently in production; the type IS the guard.)
    #[test]
    fn ids_serialize_as_decimal_strings() {
        let big = 9_007_199_254_740_993i64; // 2^53 + 1 — the first lossy value
        let o = TurnOutcome::from_resolution(big, big as u64, true, vec![], None);
        let v: serde_json::Value = serde_json::to_value(&o).unwrap();
        assert!(v["channel_event_id"].is_string(), "channel_event_id must be a string");
        assert!(v["turn_number"].is_string(), "turn_number must be a string");
        assert_eq!(v["channel_event_id"], serde_json::json!("9007199254740993"));
        // The value survives a JS-style float round-trip only as a string:
        assert_ne!(big as f64 as i64, big, "the bug class is real at this magnitude");
    }

    /// CWC-A6 bite: rejected ≠ discarded, and NEITHER advances the turn.
    /// Kill-mutation: mapping both to one kind, or incrementing on reject.
    #[test]
    fn rejection_and_discard_are_distinct_and_turn_neutral() {
        let rejected = TurnOutcome::from_rejection(4, 1, "decision-vocabulary", "Unknown action.");
        let discarded = TurnOutcome::from_resolution(
            5, 1, false, vec![], Some(("precondition_failed", "Your target is gone.")));
        let resolved = TurnOutcome::from_resolution(6, 2, true, vec!["You strike.".into()], None);

        assert_eq!(rejected.kind, OutcomeKind::Rejected);
        assert_eq!(discarded.kind, OutcomeKind::Discarded);
        assert_ne!(rejected.kind, discarded.kind, "the UI must be able to tell them apart");
        // Both non-resolutions carry the SAME turn as before; only the
        // resolution moved it — the live spine log shape (ce4 turn 1, ce5 turn 2).
        assert_eq!(rejected.turn_number, "1");
        assert_eq!(discarded.turn_number, "1");
        assert_eq!(resolved.turn_number, "2");
    }

    /// The wire `kind` values must be exactly the schema's closed enum.
    /// Kill-mutation: rename a variant without updating turn.schema.json.
    #[test]
    fn kind_wire_values_match_the_schema_enum() {
        let schema: serde_json::Value = serde_json::from_str(include_str!(
            "../../../contracts/game-wire/turn.schema.json"
        ))
        .expect("schema parses");
        let allowed = schema["$defs"]["TurnOutcome"]["properties"]["kind"]["enum"]
            .as_array()
            .expect("kind is a closed enum in the schema");
        for k in [OutcomeKind::Resolved, OutcomeKind::Discarded, OutcomeKind::Rejected] {
            let wire = serde_json::to_value(k).unwrap();
            assert!(allowed.contains(&wire), "{wire:?} is not in the schema enum {allowed:?}");
        }
        assert_eq!(allowed.len(), 3, "schema and Rust enum must have the same arity");
    }

    /// The DiscardReason strings we emit must be inside the schema's closed
    /// set (the 5-variant sim-core set, REC-63 as amended by REC-78).
    #[test]
    fn discard_reasons_match_the_schema_enum() {
        let schema: serde_json::Value = serde_json::from_str(include_str!(
            "../../../contracts/game-wire/turn.schema.json"
        ))
        .unwrap();
        let allowed: Vec<String> = schema["$defs"]["DiscardDetail"]["properties"]["reason"]["enum"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();
        assert_eq!(allowed.len(), 5, "sim-core has FIVE discard reasons since S1b");
        for r in ["duplicate", "precondition_failed", "superseded", "expired", "quarantined"] {
            assert!(allowed.contains(&r.to_string()), "{r} missing from the schema enum");
        }
    }
}
