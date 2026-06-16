package turn

import (
	"errors"
	"fmt"
)

// TurnState enumerates the 8 SR11 §12AN turn-lifecycle states.
// Wire format = canonical snake_case (matches Postgres CHECK constraint on
// the future turn_outcomes table).
type TurnState string

const (
	// StatePending — turn accepted, queued; no work started.
	StatePending TurnState = "pending"

	// StateValidating — preflight checks (auth, quota, capacity admission)
	// in progress.
	StateValidating TurnState = "validating"

	// StateRouting — selecting downstream service or model.
	StateRouting TurnState = "routing"

	// StateExecuting — LLM call or projection write in flight.
	StateExecuting TurnState = "executing"

	// StateStreaming — partial response visible to user.
	StateStreaming TurnState = "streaming"

	// StateCompleted — terminal success. No further transitions.
	StateCompleted TurnState = "completed"

	// StateFailed — terminal failure. Inspect ErrorEnvelope for class.
	StateFailed TurnState = "failed"

	// StateCancelled — user-initiated abort OR upstream timeout.
	StateCancelled TurnState = "cancelled"
)

// AllTurnStates returns every enumerated state. Used by tests + lints to
// confirm the enum stays exhaustive.
func AllTurnStates() []TurnState {
	return []TurnState{
		StatePending,
		StateValidating,
		StateRouting,
		StateExecuting,
		StateStreaming,
		StateCompleted,
		StateFailed,
		StateCancelled,
	}
}

// IsValid returns true iff s is one of the 8 enumerated states.
func (s TurnState) IsValid() bool {
	for _, ok := range AllTurnStates() {
		if s == ok {
			return true
		}
	}
	return false
}

// IsTerminal returns true iff the state ends the turn. Terminal states:
// Completed, Failed, Cancelled.
func (s TurnState) IsTerminal() bool {
	return s == StateCompleted || s == StateFailed || s == StateCancelled
}

// ParseTurnState parses the wire format. Errors on unknown strings —
// callers MUST NOT silently default to Pending on parse failure.
func ParseTurnState(s string) (TurnState, error) {
	ts := TurnState(s)
	if !ts.IsValid() {
		return "", fmt.Errorf("turn: unknown state %q", s)
	}
	return ts, nil
}

// validTransitions lists the allowed forward transitions per SR11.
// Backwards transitions (e.g., Executing → Routing) are NOT allowed.
var validTransitions = map[TurnState]map[TurnState]struct{}{
	StatePending: {
		StateValidating: {},
		StateCancelled:  {},
	},
	StateValidating: {
		StateRouting:   {},
		StateFailed:    {},
		StateCancelled: {},
	},
	StateRouting: {
		StateExecuting: {},
		StateFailed:    {},
		StateCancelled: {},
	},
	StateExecuting: {
		StateStreaming: {},
		StateCompleted: {},
		StateFailed:    {},
		StateCancelled: {},
	},
	StateStreaming: {
		StateCompleted: {},
		StateFailed:    {},
		StateCancelled: {},
	},
	// Terminal states have no outgoing edges.
}

// ErrInvalidTransition is returned when the (from, to) pair is not in the
// allowed graph. Callers MUST NOT retry — this signals a logic bug.
var ErrInvalidTransition = errors.New("turn: invalid state transition")

// AssertTransition reports whether the transition is allowed.
func AssertTransition(from, to TurnState) error {
	if !from.IsValid() || !to.IsValid() {
		return fmt.Errorf("turn: states must be valid; from=%q to=%q", from, to)
	}
	if from.IsTerminal() {
		return fmt.Errorf("%w: terminal state %q has no outgoing transitions", ErrInvalidTransition, from)
	}
	tos, ok := validTransitions[from]
	if !ok {
		return fmt.Errorf("%w: %q has no defined transitions", ErrInvalidTransition, from)
	}
	if _, ok := tos[to]; !ok {
		return fmt.Errorf("%w: %q->%q", ErrInvalidTransition, from, to)
	}
	return nil
}
