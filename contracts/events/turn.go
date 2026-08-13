package events

import (
	"encoding/json"
)

// @event       turn.resolved
// @version     1
// @aggregate   combat_session
// @description An admitted proposal was resolved by the island; the resulting
//              domain events are committed to the channel and advance the turn.
//
// THE THREE OUTCOMES ARE THREE EVENT TYPES, AND ONE STRUCT.
//
// `turn.resolved`, `turn.discarded` and `turn.buffered` are the three arms of
// sim-core's `Outcome`. They share this payload because they describe the same
// thing — what the island decided about one input — and differ in which fields
// carry meaning: `events` is populated only for Applied, `discard_reason` only
// for Discarded, and Buffered has neither (the input is held for a later tick).
//
// Three structs would have been three places to change `island_seq`, and the
// registry already distinguishes them by NAME, which is what the projectors
// dispatch on.
//
// ONLY AN APPLIED RESOLUTION CONSUMES THE TURN (DP-A17). A discard or a buffer
// leaves `turn_number` where it was — the same rule EVT-V4 states for a
// refusal, and the reason `turn_number` rides envelope metadata rather than
// this payload: it is a fact about the CHANNEL, not about the resolution.
//
// REGISTERED LATE, like proposal.rejected before it. These three have been
// written by the live spine since S3b and read by
// game-server/src/wire/turnOutcome.ts, with no schema and no validator entry.
// Found by DF5 while looking for the aggregate the actor hub actually reaches;
// recorded as PRE-EXISTING because the measurement found it, not caused it.
type TurnResolvedV1 struct {
	// The island's monotonic sequence for this resolution. CWC-A2: a decimal
	// STRING, because it is u64 server-side and a browser loses precision on a
	// JSON number past 2^53.
	IslandSeq string `json:"island_seq"`

	// The domain events the resolution produced — the actor hub's fold made
	// durable. Opaque here for the reason TurnBoundaryV1's `turn_data` is:
	// giving it a schema would make this contract the owner of a vocabulary
	// that belongs to whichever domain resolved the turn.
	Events json.RawMessage `json:"events"`

	// Why it was discarded, wire-shaped (`discard_reason_wire`). Null for
	// Applied and Buffered — a field that is meaningful for one of three arms,
	// which is why it is nullable rather than omitted.
	DiscardReason json.RawMessage `json:"discard_reason"`
}
