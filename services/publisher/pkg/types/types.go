// Package types holds the shared data shapes used across the publisher's
// internal packages. Kept tiny + free of IO so the test fakes can compose
// freely.
package types

import (
	"time"

	"github.com/google/uuid"
)

// OutboxRow mirrors `events_outbox` plus the joined event envelope fields
// needed to assemble the wire message. Populated by the poll loop's
// SELECT-with-join against the per-reality DB.
type OutboxRow struct {
	EventID        uuid.UUID
	RealityID      uuid.UUID
	Attempts       int
	EnqueuedAt     time.Time
	LastAttemptAt  time.Time
	DeadLetteredAt time.Time
	// Envelope fields (populated by JOIN events for the wire push).
	EventType        string
	EventVersion     int
	AggregateType    string
	AggregateID      string
	AggregateVersion uint64
	OccurredAt       time.Time
	RecordedAt       time.Time
	Payload          map[string]any
	Metadata         map[string]any
	// Channel ordering (DP-Ch11, migration 0014 — added 2026-07-27 with the
	// commit-service spine). NULL for reality-scoped events; set for every
	// channel-scoped one. `channel_event_id` is the client's ordering key and
	// the DP-Ch18 resume cursor, so it MUST reach the wire — without it a room
	// projection has no way to order or resume a channel.
	ChannelID      *int64
	ChannelEventID *int64
	WriterEpoch    *int64
	// RLS-A13 / QTY-A14 — the ruleset pin (migration 0016). NULL for
	// pre-migration rows and for non-simulation events; 64 lowercase hex
	// otherwise.
	//
	// THIS FIELD EXISTED ON THE ENVELOPE AND THE PUBLISHER DROPPED IT. The
	// SELECT below did not fetch the column and `envelope.go`'s json tag is
	// `omitempty`, so the pin vanished the moment an event left its reality DB
	// — invisibly, since nothing downstream was looking for it.
	//
	// Why that is not cosmetic: an L2 ordinal is MEANINGLESS without the digest
	// that gives it meaning (QTY-A14). Reality A declares ordinal 3 = qi,
	// reality B declares ordinal 3 = mana; an item minted in A and read in B
	// resolves against B's table and silently becomes a different item. Nothing
	// fails — no digest mismatch (nothing compares), no validator (3 resolves
	// locally), no length error. It is a wrong number in a committed,
	// replayable log, and both realities replay it "correctly" forever.
	//
	// Same reasoning as ChannelEventID above: a field that MUST reach the wire.
	RulesetDigest *string
}

// CrossReality reports whether the event's metadata carries the
// `cross_reality: true` flag — that flag selects the L2.L xreality fanout
// path AFTER the normal Redis Streams XADD.
func (r OutboxRow) CrossReality() bool {
	if r.Metadata == nil {
		return false
	}
	v, ok := r.Metadata["cross_reality"]
	if !ok {
		return false
	}
	b, _ := v.(bool)
	return b
}
