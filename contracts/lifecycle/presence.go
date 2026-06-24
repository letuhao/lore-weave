package lifecycle

import (
	"errors"
	"fmt"
	"strings"
)

// PresenceState is the session-scoped liveness enum per SR11-D3.
//
// Distinct from GoneState (entity existence — §12Z): a GoneState=active
// PC may have PresenceState=disconnected_ghost. Distinct from ServiceMode
// (system-wide health). PresenceState is the per-session, per-participant
// "what is this user doing RIGHT NOW" signal driving the multi-stream UX
// and other-participant-aware turn arbitration.
//
// The 6-variant set is FIXED per SR11-D3; adding a state requires SR11
// schema migration + WS close-code expansion + UI re-spec.
type PresenceState string

const (
	// PresenceActive — WS connected; recent input within idle threshold.
	PresenceActive PresenceState = "active"

	// PresenceIdle — WS connected; no input for 60s+. Still rendered as
	// "online" but other participants see an idle dot.
	PresenceIdle PresenceState = "idle"

	// PresenceTyping — WS connected; drafting state (input field has
	// content). Used for "X is typing" pinging.
	PresenceTyping PresenceState = "typing"

	// PresenceWaitingAI — one of their turns is in llm_processing or
	// streaming. Other participants see a "waiting for AI" indicator.
	PresenceWaitingAI PresenceState = "waiting_ai"

	// PresenceDisconnectedBrief — WS dropped < 5min (expected reconnect
	// window; we hold their seat).
	PresenceDisconnectedBrief PresenceState = "disconnected_brief"

	// PresenceDisconnectedGhost — WS dropped 5–30min. Seat at risk;
	// session_participants cleanup admin event fires at 30min.
	PresenceDisconnectedGhost PresenceState = "disconnected_ghost"
)

// ErrInvalidPresenceState is returned by ParsePresenceState on unknown
// wire values. Callers MUST drop/alert rather than silently default.
var ErrInvalidPresenceState = errors.New("lifecycle: invalid presence state")

// ParsePresenceState decodes the lowercase wire form produced by
// PresenceState.String. Tolerant of case (handler logs upper-case from
// some SDKs) and surrounding whitespace.
func ParsePresenceState(s string) (PresenceState, error) {
	switch PresenceState(strings.ToLower(strings.TrimSpace(s))) {
	case PresenceActive:
		return PresenceActive, nil
	case PresenceIdle:
		return PresenceIdle, nil
	case PresenceTyping:
		return PresenceTyping, nil
	case PresenceWaitingAI:
		return PresenceWaitingAI, nil
	case PresenceDisconnectedBrief:
		return PresenceDisconnectedBrief, nil
	case PresenceDisconnectedGhost:
		return PresenceDisconnectedGhost, nil
	}
	return "", fmt.Errorf("%w: %q", ErrInvalidPresenceState, s)
}

// AllPresenceStates returns the canonical ordered slice — exposed so
// tests + the SQL CHECK-constraint generator can assert exhaustiveness.
func AllPresenceStates() []PresenceState {
	return []PresenceState{
		PresenceActive,
		PresenceIdle,
		PresenceTyping,
		PresenceWaitingAI,
		PresenceDisconnectedBrief,
		PresenceDisconnectedGhost,
	}
}

// IsConnected returns true iff the participant has a live WS. The 3
// disconnected/non-connected states return false.
//
// Used by turn-arbitration: a disconnected participant doesn't block
// the next-speaker rotation; a connected idle participant DOES (they
// just chose not to type).
func (p PresenceState) IsConnected() bool {
	switch p {
	case PresenceActive, PresenceIdle, PresenceTyping, PresenceWaitingAI:
		return true
	}
	return false
}

// IsDisconnected returns the inverse of IsConnected — convenience for the
// `lw_session_disconnected_participants{session}` gauge.
func (p PresenceState) IsDisconnected() bool {
	return !p.IsConnected()
}
