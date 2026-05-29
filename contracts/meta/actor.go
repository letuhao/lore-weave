package meta

import "time"

// ActorType enumerates the kinds of writers tracked in meta_write_audit
// (matches the CHECK constraint on lifecycle_transition_audit.actor_type and
// the L1.A audit-table actor_type column).
type ActorType string

const (
	ActorAdmin         ActorType = "admin"
	ActorSystem        ActorType = "system"
	ActorService       ActorType = "service"
	ActorRetentionCron ActorType = "retention_cron"
	ActorOwner         ActorType = "owner" // user-initiated, owns the resource
	ActorCron          ActorType = "cron"  // generic non-retention cron
)

// ValidActorTypes enumerates all known actor types for fail-fast validation.
func ValidActorTypes() []ActorType {
	return []ActorType{
		ActorAdmin, ActorSystem, ActorService,
		ActorRetentionCron, ActorOwner, ActorCron,
	}
}

// IsValid returns true for known actor types.
func (a ActorType) IsValid() bool {
	for _, ok := range ValidActorTypes() {
		if a == ok {
			return true
		}
	}
	return false
}

// Actor identifies who initiated a MetaWrite. ID is opaque to the library
// (UUID for human actors, service name for system actors).
//
// SVID is the optional SPIFFE Verifiable Identity (S11 §12AA) — populated by
// the service runtime, NOT by user code. Library checks presence on
// service-class writes (deferred to a later cycle that ships the SVID
// validation path; today the field is just carried through to audit).
type Actor struct {
	Type ActorType
	ID   string
	SVID string // optional; SPIFFE ID e.g. "spiffe://loreweave/world-service"
}

// RequestContext is the trace/request envelope carried through to audit
// for forensics correlation (S04 §12T.5 request_context column).
type RequestContext struct {
	TraceID       string
	RequestID     string
	SourceService string
	ReceivedAt    time.Time
}
