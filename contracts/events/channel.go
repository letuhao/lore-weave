package events

import (
	"encoding/json"
)

// @event       channel.turn_boundary
// @version     1
// @aggregate   channel
// @description A channel's turn counter advanced by one; every member of the
//              channel sees this in the channel's total order (DP-Ch21).
//
// WHICH "TURN" THIS IS — read this before adding anything near it.
//
// Four things in this repo are called a turn (see
// docs/plans/2026-08-11-turn-loop-RUN-STATE.md §1.1). This is DP-Ch21's: a
// per-channel, monotonic page-flip counter shared by every member of a
// channel, the "discrete page flips" of a reality-as-a-book.
//
// It is NOT contracts/turn/ + crates/dp-kernel/src/turn.rs, which is ONE
// REQUEST's lifecycle (pending -> validating -> ... -> completed) and carries
// reality_id/session_id/actor_id — the same scope keys, a different subject,
// and a mutator one word away (TurnContext.Advance vs advance_turn). Nothing
// mechanical separates them; only this comment and its twin in the SQL.
//
// WHY THE PAYLOAD IS ONLY TWO FIELDS, unlike RulesetEpochActivatedV1 next door.
//
// DP-Ch21 is explicit that channel_event_id, writer_epoch and causal_refs are
// carried by the ENVELOPE, and that {turn_number, turn_data} is "this file's
// contribution". Duplicating the envelope's fields into the payload would give
// each of them two homes and no rule for which wins — the shape DP-A15's total
// ordering exists to keep singular. RulesetEpochActivatedV1 repeats
// reality_id/channel_id because a single ruleset switch produces N events that
// must be joinable OUTSIDE their envelopes; a turn boundary is one event about
// one channel and has no such need.
//
// WHY THE NAME IS DOTTED WHEN THE SPEC WRITES A BARE STRING.
//
// 15_turn_boundary.md declares `const EVENT_TYPE: &'static str =
// "turn_boundary"`. This registry's 15 existing event types are dotted without
// exception, and it is the authoritative namespace for the events.event_type
// column — a bare name would be the only undotted value in it. The Rust
// constant does not exist yet (advance_turn is unbuilt), so this is a choice
// made once rather than a rename of shipped code, and the Rust side is written
// to match. Recorded as SF-5 in the run-state.
type TurnBoundaryV1 struct {
	// New turn number — strictly the channel's previous value plus one.
	TurnNumber uint64 `json:"turn_number"`

	// Opaque feature-defined payload: a D&D round, a narrative scene title,
	// "player A's turn". DP does not interpret it, which is why it is raw
	// rather than a typed struct — giving it a schema here would make DP the
	// owner of a vocabulary that belongs to whichever feature advances turns.
	TurnData json.RawMessage `json:"turn_data"`
}
