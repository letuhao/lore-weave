// Package break_glass implements the S11-D10 break-glass flow:
//   POST /admin/break-glass → dual-actor + 100+ char reason + incident ticket
//   → 24h TTL JWT with `break_glass=true` claim
//
// V1 (cycle 36) ships the policy CHECKS as a pure library + the request
// struct. Actual JWT issuance wires to auth-service (cycle 18+).
package break_glass

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

// Request captures a break-glass token request.
type Request struct {
	PrimaryActor   string // user_ref initiating the request
	SecondaryActor string // dual-actor approver (different from primary)
	Reason         string // MUST be >= 100 chars
	IncidentTicket string // e.g. INC-12345
	RequestedTTL   time.Duration
}

// ErrBreakGlass is returned by Validate on policy violation.
var ErrBreakGlass = errors.New("admin-cli/break_glass")

// Validate enforces S11-D10 invariants. Returns ErrBreakGlass on failure.
func (r Request) Validate() error {
	if r.PrimaryActor == "" {
		return fmt.Errorf("%w: primary_actor empty", ErrBreakGlass)
	}
	if r.SecondaryActor == "" {
		return fmt.Errorf("%w: secondary_actor empty (dual-actor required)", ErrBreakGlass)
	}
	if r.PrimaryActor == r.SecondaryActor {
		return fmt.Errorf("%w: primary and secondary actor must differ (dual-actor)", ErrBreakGlass)
	}
	if len(strings.TrimSpace(r.Reason)) < 100 {
		return fmt.Errorf("%w: reason must be >=100 chars (got %d)",
			ErrBreakGlass, len(strings.TrimSpace(r.Reason)))
	}
	if r.IncidentTicket == "" {
		return fmt.Errorf("%w: incident_ticket empty", ErrBreakGlass)
	}
	if r.RequestedTTL <= 0 || r.RequestedTTL > 24*time.Hour {
		return fmt.Errorf("%w: requested_ttl=%s out of (0, 24h]", ErrBreakGlass, r.RequestedTTL)
	}
	return nil
}

// Token is the issued break-glass token (V1 skeleton — auth-service wires JWT body).
type Token struct {
	Value     string // opaque
	IssuedAt  time.Time
	ExpiresAt time.Time
}
