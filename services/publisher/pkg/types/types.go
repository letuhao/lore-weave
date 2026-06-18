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
	EventID          uuid.UUID
	RealityID        uuid.UUID
	Attempts         int
	EnqueuedAt       time.Time
	LastAttemptAt    time.Time
	DeadLetteredAt   time.Time
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
