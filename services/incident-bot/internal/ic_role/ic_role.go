// Package ic_role implements L7.D.12 — Incident Commander role workflow.
//
// SR2 §12AE.2: the IC is SEPARATE from the fixer. The IC coordinates
// (comms, delegation, decision log); the fixer fixes. Conflating the two
// is a classic incident anti-pattern (the person debugging can't also run
// comms). This package enforces that separation and tracks the IC handoff
// chain + decision log.
package ic_role

import (
	"fmt"
	"time"
)

// Assignment is the current IC assignment for an incident.
type Assignment struct {
	IncidentID  string
	ICUserID    string
	FixerUserID string
	AssignedAt  time.Time
	// Handoffs is the ordered chain of IC handoffs (audit trail).
	Handoffs []Handoff
	// Decisions is the IC decision log.
	Decisions []Decision
}

// Handoff records an IC role transfer.
type Handoff struct {
	FromUserID string
	ToUserID   string
	At         time.Time
	Reason     string
}

// Decision records a command decision the IC made.
type Decision struct {
	At      time.Time
	By      string // IC user id at decision time
	Text    string
}

// Assign creates the initial IC assignment. ic and fixer MUST differ
// (SR2 §12AE.2 separation). Either may be empty at declare-time, but if
// both are set they must not be the same person.
func Assign(incidentID, ic, fixer string, at time.Time) (*Assignment, error) {
	if incidentID == "" {
		return nil, fmt.Errorf("ic_role: empty incident id")
	}
	if at.IsZero() {
		return nil, fmt.Errorf("ic_role: zero assigned_at")
	}
	if ic != "" && fixer != "" && ic == fixer {
		return nil, fmt.Errorf("ic_role: IC and fixer must be different people (SR2 §12AE.2 separation); both=%q", ic)
	}
	return &Assignment{
		IncidentID:  incidentID,
		ICUserID:    ic,
		FixerUserID: fixer,
		AssignedAt:  at,
	}, nil
}

// Handoff transfers the IC role to a new user. The new IC must differ from
// the current fixer (separation preserved across handoff).
func (a *Assignment) Handoff(toUserID, reason string, at time.Time) error {
	if toUserID == "" {
		return fmt.Errorf("ic_role: handoff to empty user")
	}
	if toUserID == a.FixerUserID {
		return fmt.Errorf("ic_role: cannot hand IC to the current fixer %q (separation)", toUserID)
	}
	if toUserID == a.ICUserID {
		return fmt.Errorf("ic_role: %q is already IC", toUserID)
	}
	a.Handoffs = append(a.Handoffs, Handoff{
		FromUserID: a.ICUserID,
		ToUserID:   toUserID,
		At:         at,
		Reason:     reason,
	})
	a.ICUserID = toUserID
	return nil
}

// AssignFixer sets/updates the fixer. The fixer must differ from the IC.
func (a *Assignment) AssignFixer(fixerUserID string) error {
	if fixerUserID != "" && fixerUserID == a.ICUserID {
		return fmt.Errorf("ic_role: fixer %q cannot also be IC (separation)", fixerUserID)
	}
	a.FixerUserID = fixerUserID
	return nil
}

// LogDecision appends a command decision to the IC log.
func (a *Assignment) LogDecision(text string, at time.Time) error {
	if text == "" {
		return fmt.Errorf("ic_role: empty decision text")
	}
	a.Decisions = append(a.Decisions, Decision{At: at, By: a.ICUserID, Text: text})
	return nil
}
