package resilience

import (
	"errors"
	"fmt"
	"time"
)

// EventType is the canonical event_type value for dependency_events rows
// per SR06 §12AI.9. The set is closed — any new value requires SR06
// schema migration + downstream alert rule update.
type EventType string

const (
	EventCircuitOpen           EventType = "circuit_open"
	EventCircuitHalfOpen       EventType = "circuit_half_open"
	EventCircuitClosed         EventType = "circuit_closed"
	EventTimeoutBurst          EventType = "timeout_burst"
	EventRetryExhausted        EventType = "retry_exhausted"
	EventDegradedModeActivated EventType = "degraded_mode_activated"
	EventDegradedModeCleared   EventType = "degraded_mode_cleared"
	EventFailoverUsed          EventType = "failover_used"
	EventManualOverride        EventType = "manual_override"
	EventBulkheadFullBurst     EventType = "bulkhead_full_burst"
)

// AllEventTypes returns the canonical ordered set — used by tests and
// the dependency_events.event_type CHECK constraint generator.
func AllEventTypes() []EventType {
	return []EventType{
		EventCircuitOpen,
		EventCircuitHalfOpen,
		EventCircuitClosed,
		EventTimeoutBurst,
		EventRetryExhausted,
		EventDegradedModeActivated,
		EventDegradedModeCleared,
		EventFailoverUsed,
		EventManualOverride,
		EventBulkheadFullBurst,
	}
}

// DependencyEvent is the typed audit row written through MetaWrite (I8)
// when a resilience-relevant state change occurs. The MetaWrite call site
// owns the INSERT — this struct exists so the constructor can validate
// required fields BEFORE the SQL.
//
// Wire mapping to the `dependency_events` table:
//
//	event_id            ← caller-supplied UUID
//	dep_name            ← DepName
//	service             ← Service
//	event_type          ← EventType
//	reason              ← Reason
//	metrics_snapshot    ← MetricsSnapshot (JSONB; can be nil)
//	occurred_at         ← OccurredAt
//	cleared_at          ← ClearedAt (nil for one-shot events)
//	related_incident_id ← RelatedIncidentID
//	actor               ← Actor (nil for automatic events)
type DependencyEvent struct {
	EventID           string
	DepName           string
	Service           string
	EventType         EventType
	Reason            string
	MetricsSnapshot   map[string]any
	OccurredAt        time.Time
	ClearedAt         *time.Time
	RelatedIncidentID *string
	Actor             *string
}

// ErrInvalidDependencyEvent is returned by NewDependencyEvent on missing
// or invalid required fields.
var ErrInvalidDependencyEvent = errors.New("resilience: invalid dependency event")

// NewDependencyEvent validates the required fields. event_id, dep, service,
// type, occurred_at MUST be non-empty / non-zero. Reason MUST be present
// for circuit + degraded-mode transitions (postmortem usability).
func NewDependencyEvent(eventID, dep, service string, t EventType, reason string, occurredAt time.Time) (DependencyEvent, error) {
	if eventID == "" {
		return DependencyEvent{}, fmt.Errorf("%w: event_id empty", ErrInvalidDependencyEvent)
	}
	if dep == "" {
		return DependencyEvent{}, fmt.Errorf("%w: dep_name empty", ErrInvalidDependencyEvent)
	}
	if service == "" {
		return DependencyEvent{}, fmt.Errorf("%w: service empty", ErrInvalidDependencyEvent)
	}
	if !isKnownEventType(t) {
		return DependencyEvent{}, fmt.Errorf("%w: unknown event_type %q", ErrInvalidDependencyEvent, t)
	}
	if occurredAt.IsZero() {
		return DependencyEvent{}, fmt.Errorf("%w: occurred_at must be non-zero", ErrInvalidDependencyEvent)
	}
	if reason == "" && requiresReason(t) {
		return DependencyEvent{}, fmt.Errorf("%w: event_type=%q requires reason for postmortem", ErrInvalidDependencyEvent, t)
	}
	return DependencyEvent{
		EventID:    eventID,
		DepName:    dep,
		Service:    service,
		EventType:  t,
		Reason:     reason,
		OccurredAt: occurredAt,
	}, nil
}

func isKnownEventType(t EventType) bool {
	for _, k := range AllEventTypes() {
		if k == t {
			return true
		}
	}
	return false
}

// requiresReason returns true for event types that MUST carry a reason
// string for postmortem usability per SR06 §12AI.9.
func requiresReason(t EventType) bool {
	switch t {
	case EventCircuitOpen, EventCircuitClosed, EventCircuitHalfOpen,
		EventDegradedModeActivated, EventDegradedModeCleared,
		EventManualOverride:
		return true
	}
	return false
}
