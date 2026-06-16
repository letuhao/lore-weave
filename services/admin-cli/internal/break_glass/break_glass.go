// Package break_glass implements the S11-D10 break-glass flow:
//
//	POST /admin/break-glass → dual-actor + 100+ char reason + incident ticket
//	→ 24h TTL JWT with `break_glass=true` claim
//
// V1 (cycle 36) ships the policy CHECKS as a pure library + the request
// struct. Actual JWT issuance wires to auth-service (cycle 18+).
package break_glass

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/loreweave/foundation/contracts/adminjwt"
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

// Validate enforces the S11-D10 invariants. The policy itself lives in the
// shared contracts/adminjwt module (the single pinned source consumed by BOTH
// admin-cli and the auth-service issuer, so the two can never drift). We
// re-wrap under the local ErrBreakGlass sentinel to preserve this package's
// error contract for existing callers.
func (r Request) Validate() error {
	err := adminjwt.ValidateBreakGlass(adminjwt.BreakGlassRequest{
		PrimaryActor:   r.PrimaryActor,
		SecondaryActor: r.SecondaryActor,
		Reason:         r.Reason,
		IncidentTicket: r.IncidentTicket,
		RequestedTTL:   r.RequestedTTL,
	})
	if err != nil {
		detail := strings.TrimPrefix(err.Error(), adminjwt.ErrBreakGlass.Error()+": ")
		return fmt.Errorf("%w: %s", ErrBreakGlass, detail)
	}
	return nil
}

// Token is the issued break-glass token (V1 skeleton — auth-service wires JWT body).
type Token struct {
	Value     string // opaque
	IssuedAt  time.Time
	ExpiresAt time.Time
}
