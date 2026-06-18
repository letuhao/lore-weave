package events

import (
	"time"

	"github.com/google/uuid"
)

// Envelope is the cross-service event envelope (R03 §12C.1 wire format).
//
// Every event published via the L2.C outbox / L2.D publisher / xreality.*
// pub-sub uses this envelope as the OUTER wire shape; the inner Payload is
// schema-validated against the registered struct for (EventType, EventVersion).
//
// Field semantics:
//   - EventID         — UUIDv4; globally unique per emission
//   - EventType       — canonical name from `_registry.yaml` (e.g. "npc.said")
//   - EventVersion    — schema version; matches the @version annotation on the
//                       struct
//   - AggregateID     — entity id this event mutates (NPC id, region id, …)
//   - AggregateType   — string discriminator (e.g. "npc", "region", "pc")
//   - AggregateVersion— monotonic per-aggregate sequence number (optimistic CC)
//   - RealityID       — per-reality DB isolation key (R05)
//   - OccurredAt      — when the event actually happened (in-world time may
//                       differ; that lives in payload)
//   - RecordedAt      — server-side timestamp at append; used by ordering /
//                       lag metrics
//   - Payload         — schema-validated; the registry tells us which struct
//                       to deserialize into
//   - Metadata        — out-of-band context (request_id, actor_id, trace_id,
//                       privacy flags); NOT part of the canonical event shape
//
// The envelope is INTENTIONALLY identical in Go + Rust (see
// `crates/dp-kernel/src/upcaster.rs`) — having a single shape makes
// upcasters / validators / projectors language-portable.
type Envelope struct {
	EventID          uuid.UUID              `json:"event_id"`
	EventType        string                 `json:"event_type"`
	EventVersion     uint32                 `json:"event_version"`
	AggregateID      string                 `json:"aggregate_id"`
	AggregateType    string                 `json:"aggregate_type"`
	AggregateVersion uint64                 `json:"aggregate_version"`
	RealityID        uuid.UUID              `json:"reality_id"`
	OccurredAt       time.Time              `json:"occurred_at"`
	RecordedAt       time.Time              `json:"recorded_at"`
	Payload          map[string]any         `json:"payload"`
	Metadata         map[string]any         `json:"metadata,omitempty"`
}

// Validate runs the structural checks that don't require the registry:
//   - EventID non-zero
//   - EventType non-empty
//   - EventVersion >= 1
//   - AggregateID non-empty
//   - AggregateType non-empty
//   - RealityID non-zero
//   - RecordedAt non-zero
//
// Schema validation against the L2.F registry is L2.I — separate concern,
// uses validators_go/Validate(envelope, registry).
func (e *Envelope) Validate() error {
	if e.EventID == uuid.Nil {
		return ErrInvalidEnvelope("event_id is zero")
	}
	if e.EventType == "" {
		return ErrInvalidEnvelope("event_type is empty")
	}
	if e.EventVersion < 1 {
		return ErrInvalidEnvelope("event_version must be >= 1")
	}
	if e.AggregateID == "" {
		return ErrInvalidEnvelope("aggregate_id is empty")
	}
	if e.AggregateType == "" {
		return ErrInvalidEnvelope("aggregate_type is empty")
	}
	if e.RealityID == uuid.Nil {
		return ErrInvalidEnvelope("reality_id is zero")
	}
	if e.RecordedAt.IsZero() {
		return ErrInvalidEnvelope("recorded_at is zero")
	}
	return nil
}
