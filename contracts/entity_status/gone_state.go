package entity_status

import (
	"fmt"
)

// GoneState enumerates the lifecycle states a game entity can be in.
// Mirrors S10 §12Z's GoneState enum. Wire format = canonical snake_case
// string (matches Postgres CHECK constraints on cycle-13 projection tables).
type GoneState string

const (
	// StateActive — entity exists in its home reality and is reachable by
	// every read path. Default state for healthy entities.
	StateActive GoneState = "active"

	// StateSevered — entity used to live in this reality but has been moved
	// (cross-reality migration) OR explicitly disconnected from its parent
	// reality. Reads SHOULD return the entity's last-known state but MUST
	// flag it as not-live.
	StateSevered GoneState = "severed"

	// StateArchived — entity's home reality has been archived (R09 §12I);
	// reads only succeed via the cold-path archive replay. Hot reads return
	// the StatusEnvelope without payload data.
	StateArchived GoneState = "archived"

	// StateDropped — entity (or its home reality) has been hard-deleted.
	// Terminal — never transitions back. Reads return GoneState=dropped with
	// no payload.
	StateDropped GoneState = "dropped"

	// StateUserErased — entity's PII was crypto-shredded (GDPR Art. 17).
	// Distinct from StateDropped because the row may still exist with PII
	// zeroed. Reads MUST treat this as 'gone for all PII purposes'.
	StateUserErased GoneState = "user_erased"
)

// IsValid returns true iff s is one of the 5 enumerated states.
func (s GoneState) IsValid() bool {
	switch s {
	case StateActive, StateSevered, StateArchived, StateDropped, StateUserErased:
		return true
	}
	return false
}

// IsLive returns true iff the entity is reachable for normal hot-path reads.
// Only StateActive is live; everything else is gone in some way.
func (s GoneState) IsLive() bool {
	return s == StateActive
}

// IsTerminal returns true iff the state will never transition back to
// StateActive. StateDropped + StateUserErased are terminal.
func (s GoneState) IsTerminal() bool {
	return s == StateDropped || s == StateUserErased
}

// AllGoneStates returns every enumerated state (for tests + lints).
func AllGoneStates() []GoneState {
	return []GoneState{
		StateActive,
		StateSevered,
		StateArchived,
		StateDropped,
		StateUserErased,
	}
}

// ParseGoneState parses the wire format. Errors on any unknown string —
// callers MUST NOT default to StateActive on parse failure (that would mask
// projection corruption as "all good").
func ParseGoneState(s string) (GoneState, error) {
	g := GoneState(s)
	if !g.IsValid() {
		return "", fmt.Errorf("entity_status: unknown gone_state %q", s)
	}
	return g, nil
}
