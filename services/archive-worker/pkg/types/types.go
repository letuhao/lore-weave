// Package types holds shared data shapes used across the archive-worker's
// internal packages. Kept tiny + free of IO so the test fakes can compose
// freely (same pattern as services/publisher/pkg/types).
package types

import (
	"time"

	"github.com/google/uuid"
)

// Partition is a Postgres monthly partition descriptor — one row per known
// child of `events`. Populated by pkg/partition_picker via pg_inherits +
// regclass introspection.
type Partition struct {
	// RealityID — the per-reality DB this partition belongs to.
	RealityID uuid.UUID
	// Name — full Postgres relation name (e.g. "events_p_2025_11").
	Name string
	// LowerBound — partition lower bound (inclusive). Computed from name
	// suffix; cross-checked against pg_get_expr in production wiring.
	LowerBound time.Time
	// UpperBound — partition upper bound (exclusive).
	UpperBound time.Time
	// RowCountEstimate — pg_class.reltuples; used for budgeting + the
	// Parquet writer's pre-allocate sizing. May be 0 if ANALYZE hasn't
	// run; the writer treats it as a hint only.
	RowCountEstimate int64
}

// Eligible reports whether this partition is past the archive cutoff —
// i.e. UpperBound is strictly older than now()-cutoff. The picker uses
// this; tests override `now` for determinism.
func (p Partition) Eligible(now time.Time, cutoff time.Duration) bool {
	return p.UpperBound.Before(now.Add(-cutoff))
}

// ArchivedObject is the manifest entry written to the `archive_state` table
// once an upload completes + verifies. The same shape is the return value
// of pkg/archive_loop's per-iteration call.
type ArchivedObject struct {
	RealityID    uuid.UUID
	Partition    string    // e.g. "events_p_2025_11"
	ObjectKey    string    // e.g. "events/<reality_id>/2025-11.parquet"
	ByteSize     int64
	RowCount     int64
	ArchivedAt   time.Time
	FormatHeader [4]byte // 'LWP1' (LoreWeave Parquet v1) — verify-after-upload checks this
}

// EventRow is the wire shape of a single event row read out of `events`
// by the partition picker's row source. Matches contracts/events/envelope.go
// column-for-column (cycle 8). The Parquet writer encodes this struct
// into a row group; the reader reverses it on restore.
type EventRow struct {
	EventID          uuid.UUID
	RealityID        uuid.UUID
	AggregateType    string
	AggregateID      string
	AggregateVersion uint64
	EventType        string
	EventVersion     int
	Payload          []byte // JSONB raw (already encoded by Postgres)
	Metadata         []byte // JSONB raw
	OccurredAt       time.Time
	RecordedAt       time.Time
	AuditRef         *uuid.UUID // pointer (may be NULL per Q-L2-3)
	RegistryVersion  *int       // pointer (may be NULL pre-validator)
}
