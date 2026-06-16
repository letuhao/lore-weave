package adminjwt

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

// Break-glass policy constants (S11-D10). Pinned here as the single source of
// truth so admin-cli (which gates the command) and auth-service (which mints
// the token) enforce identical invariants.
const (
	// MinReasonLen is the minimum justification length for a break-glass token.
	MinReasonLen = 100
	// MaxBreakGlassTTL caps a break-glass token's lifetime.
	MaxBreakGlassTTL = 24 * time.Hour
)

// ErrBreakGlass is the sentinel wrapped by all break-glass policy violations.
var ErrBreakGlass = errors.New("adminjwt: break_glass")

// BreakGlassRequest is the input to the break-glass policy check. It is the
// shared shape; callers map their own request structs onto it.
type BreakGlassRequest struct {
	PrimaryActor   string        // user_ref initiating
	SecondaryActor string        // dual-actor approver (MUST differ from primary)
	Reason         string        // MUST be >= MinReasonLen chars (trimmed)
	IncidentTicket string        // e.g. INC-12345 (MUST be present)
	RequestedTTL   time.Duration // MUST be in (0, MaxBreakGlassTTL]
}

// ValidateBreakGlass enforces the S11-D10 invariants. It is pure (no I/O) so
// both modules can call it. Returns an error wrapping ErrBreakGlass on any
// violation.
func ValidateBreakGlass(r BreakGlassRequest) error {
	if r.PrimaryActor == "" {
		return fmt.Errorf("%w: primary_actor empty", ErrBreakGlass)
	}
	if r.SecondaryActor == "" {
		return fmt.Errorf("%w: secondary_actor empty (dual-actor required)", ErrBreakGlass)
	}
	if r.PrimaryActor == r.SecondaryActor {
		return fmt.Errorf("%w: primary and secondary actor must differ (dual-actor)", ErrBreakGlass)
	}
	if len(strings.TrimSpace(r.Reason)) < MinReasonLen {
		return fmt.Errorf("%w: reason must be >=%d chars (got %d)", ErrBreakGlass, MinReasonLen, len(strings.TrimSpace(r.Reason)))
	}
	if r.IncidentTicket == "" {
		return fmt.Errorf("%w: incident_ticket empty", ErrBreakGlass)
	}
	if r.RequestedTTL <= 0 || r.RequestedTTL > MaxBreakGlassTTL {
		return fmt.Errorf("%w: requested_ttl=%s out of (0, %s]", ErrBreakGlass, r.RequestedTTL, MaxBreakGlassTTL)
	}
	return nil
}
