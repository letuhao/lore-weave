package events

// @event       proposal.rejected
// @version     1
// @aggregate   combat_session
// @description A submitted proposal was refused by admission; the refusal is
//              COMMITTED to the channel rather than merely logged (CS-A4), so a
//              client can render why nothing happened.
//
// WHY THIS ARRIVES LATE, AND WHAT ITS ABSENCE COST.
//
// This event has been written by the live spine since S3b and read by TWO
// projectors in two languages — services/commit-service/src/wire.rs and
// services/game-server/src/wire/turnOutcome.ts, whose TURN_OUTCOME_TYPES set
// names it — and it was NOT in _registry.yaml. So the one domain event this
// system produces in anger had no schema, no validator entry, and no contract
// the two projectors could be checked against. Found by DF1b's measurement
// (docs/plans/2026-08-13-data-foundation-dataflow-RUN-STATE.md, DFO-4) while
// looking for a registered type the SDK could name; recorded as PRE-EXISTING
// because the measurement found it rather than caused it.
//
// WHY THE PAYLOAD IS TWO FIELDS AND turn_number IS NOT ONE OF THEM.
//
// Same rule as TurnBoundaryV1 next door: what the ENVELOPE carries does not get
// a second home in the payload. `turn_number` rides envelope metadata — and
// EVT-V4 is the reason it is worth stating here rather than assuming: a
// rejection is committed WITHOUT advancing the turn, so the value stamped on
// this event is the channel's CURRENT turn, deliberately unchanged. A reader
// who finds two rejections at the same turn_number is looking at correct data.
//
// CWC-A2 applies to that metadata field: it leaves as a decimal STRING, because
// a browser consuming it via the publisher loses precision on a JSON number
// past 2^53.
type ProposalRejectedV1 struct {
	// Which admission stage refused it — the pipeline position, not a free
	// string: signature, vocabulary, dedup, verb. Named `rejected_at_stage`
	// because `stage` alone reads like a lifecycle phase of the proposal.
	RejectedAtStage string `json:"rejected_at_stage"`

	// Why, in a form a client can show. Human-readable by design: the machine
	// answer is the stage above, and duplicating it as a code here would give
	// one fact two homes and no rule for which wins.
	Reason string `json:"reason"`
}
