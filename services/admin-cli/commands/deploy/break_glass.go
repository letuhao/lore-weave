// Package deploy implements admin-cli deploy-domain commands.
//
// L7.K.8 (RAID cycle 38) ships `admin deploy break-glass`: the SR05 §12AH.3
// break-glass-deploy workflow that lets an `emergency`-class deploy bypass an
// active freeze. Per §12AH.3 a break-glass deploy requires ALL of:
//
//   - the `break-glass-deploy` PR label present
//   - tech-lead CODEOWNERS approval (an approver in the tech-lead set)
//   - an incident_id OR security_finding_id (emergency justification)
//   - a mandatory post-deploy review obligation recorded (≤24h)
//
// This is a pure policy library + request validator (matches the cycle-7
// commands/capacity_override.go idiom): Validate() enforces the §12AH.3
// invariants and Apply() records the override to deploy_audit through the
// FreezeOverrideWriter so the same-TX audit row lands. The deploy-freeze-check.sh
// CI lint consumes the same label + approval signals; this command is the
// human-driven escape hatch when CI has blocked the merge.
package deploy

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// BreakGlassLabel is the PR label that signals a break-glass-deploy request.
const BreakGlassLabel = "break-glass-deploy"

// PostDeployReviewWindow is the §12AH.3 mandatory post-deploy review SLA.
const PostDeployReviewWindow = 24 * time.Hour

// FreezeType enumerates the four §12AH.3 freeze mechanisms a break-glass may
// override. All four are overridable by break-glass EXCEPT that the override
// still requires the per-type approver role (recorded in the audit row).
type FreezeType string

const (
	FreezeSLOBurn   FreezeType = "slo_burn"  // SR1-D3 burn ≥90%/7d
	FreezeScheduled FreezeType = "scheduled" // admin/deploy-freeze
	FreezeIncident  FreezeType = "incident"  // active SEV0/SEV1
	FreezeSecurity  FreezeType = "security"  // active attack / supply-chain
)

// ValidFreezeType reports whether ft is one of the four §12AH.3 types.
func ValidFreezeType(ft FreezeType) bool {
	switch ft {
	case FreezeSLOBurn, FreezeScheduled, FreezeIncident, FreezeSecurity:
		return true
	}
	return false
}

// BreakGlassRequest captures a break-glass-deploy invocation.
type BreakGlassRequest struct {
	DeployID          string     // the deploy_audit row being unblocked
	PRLabels          []string   // labels currently on the PR
	FreezeType        FreezeType // which active freeze is being overridden
	TechLeadApprover  string     // CODEOWNERS tech-lead who approved (user_ref)
	IncidentID        string     // emergency justification (one of these required)
	SecurityFindingID string
	Actor             string // who is running the command (user_ref)
	Reason            string // free-text justification (audit)
}

// ErrBreakGlass is returned by Validate / Apply on policy violation.
var ErrBreakGlass = errors.New("admin-cli/deploy: break-glass")

// Validate enforces the §12AH.3 break-glass-deploy invariants.
func (r BreakGlassRequest) Validate() error {
	if r.DeployID == "" {
		return fmt.Errorf("%w: deploy_id empty", ErrBreakGlass)
	}
	if !hasLabel(r.PRLabels, BreakGlassLabel) {
		return fmt.Errorf("%w: PR must carry the %q label", ErrBreakGlass, BreakGlassLabel)
	}
	if !ValidFreezeType(r.FreezeType) {
		return fmt.Errorf("%w: freeze_type %q invalid (slo_burn|scheduled|incident|security)", ErrBreakGlass, r.FreezeType)
	}
	if strings.TrimSpace(r.TechLeadApprover) == "" {
		return fmt.Errorf("%w: tech_lead_approver required (CODEOWNERS approval)", ErrBreakGlass)
	}
	if r.TechLeadApprover == r.Actor {
		return fmt.Errorf("%w: tech_lead_approver must differ from actor (no self-approval)", ErrBreakGlass)
	}
	if strings.TrimSpace(r.IncidentID) == "" && strings.TrimSpace(r.SecurityFindingID) == "" {
		return fmt.Errorf("%w: incident_id OR security_finding_id required (emergency justification)", ErrBreakGlass)
	}
	if strings.TrimSpace(r.Actor) == "" {
		return fmt.Errorf("%w: actor empty", ErrBreakGlass)
	}
	if strings.TrimSpace(r.Reason) == "" {
		return fmt.Errorf("%w: reason empty (audit requires explanation)", ErrBreakGlass)
	}
	return nil
}

// OverrideRecord is what gets written to deploy_audit on a successful override.
type OverrideRecord struct {
	DeployID            string
	FreezeType          FreezeType
	TechLeadApprover    string
	Actor               string
	IncidentRef         string // incident_id or security_finding_id
	Reason              string
	OverriddenAtNanos   int64
	PostReviewDueNanos  int64 // §12AH.3 mandatory ≤24h post-deploy review
}

// FreezeOverrideWriter persists the override row. The real binding goes through
// contracts/meta MetaWrite() so the deploy_audit + meta_write_audit rows land
// in one TX; the unit test stubs this.
type FreezeOverrideWriter interface {
	WriteFreezeOverride(ctx context.Context, rec OverrideRecord) error
}

// ClockFn returns "now"; injectable for tests.
type ClockFn func() time.Time

// Apply validates the request and records the freeze override to deploy_audit.
// It returns the written record (including the post-deploy review due time) so
// the operator is reminded of the §12AH.3 24h review obligation.
func Apply(ctx context.Context, req BreakGlassRequest, w FreezeOverrideWriter, clock ClockFn) (OverrideRecord, error) {
	if err := req.Validate(); err != nil {
		return OverrideRecord{}, err
	}
	now := clock()
	ref := req.IncidentID
	if ref == "" {
		ref = req.SecurityFindingID
	}
	rec := OverrideRecord{
		DeployID:           req.DeployID,
		FreezeType:         req.FreezeType,
		TechLeadApprover:   req.TechLeadApprover,
		Actor:              req.Actor,
		IncidentRef:        ref,
		Reason:             req.Reason,
		OverriddenAtNanos:  now.UnixNano(),
		PostReviewDueNanos: now.Add(PostDeployReviewWindow).UnixNano(),
	}
	if err := w.WriteFreezeOverride(ctx, rec); err != nil {
		return OverrideRecord{}, fmt.Errorf("admin-cli/deploy: write freeze override: %w", err)
	}
	return rec, nil
}

func hasLabel(labels []string, want string) bool {
	for _, l := range labels {
		if strings.EqualFold(strings.TrimSpace(l), want) {
			return true
		}
	}
	return false
}
