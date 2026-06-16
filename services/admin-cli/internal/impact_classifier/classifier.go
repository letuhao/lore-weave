// Package impact_classifier maps registry impact_class strings to enforcement
// policy (S5-D5).
//
// Used by the framework to derive:
//   - whether --dry-run is mandatory
//   - whether a second approval is required
//   - which audit-row sensitivity flag to set
package impact_classifier

import "errors"

// Tier enumerates S5-D5 tiers.
type Tier int

const (
	TierUnknown        Tier = 0
	Tier1Destructive   Tier = 1
	Tier2Griefing      Tier = 2
	Tier3Informational Tier = 3
)

// Policy is the derived enforcement policy for a tier.
type Policy struct {
	Tier                 Tier
	RequireDryRun        bool
	RequireDoubleApproval bool
	RequireTypedConfirm  bool
	AuditSensitivity     string // "high" | "med" | "low"
}

// ErrTier is returned by Of when the input string is unknown.
var ErrTier = errors.New("admin-cli/impact_classifier")

// Of returns the policy for the named tier string.
func Of(s string) (Policy, error) {
	switch s {
	case "tier-1-destructive":
		return Policy{
			Tier:                  Tier1Destructive,
			RequireDryRun:         true,
			RequireDoubleApproval: true,
			RequireTypedConfirm:   true,
			AuditSensitivity:      "high",
		}, nil
	case "tier-2-griefing":
		return Policy{
			Tier:                  Tier2Griefing,
			RequireDryRun:         false,
			RequireDoubleApproval: false,
			RequireTypedConfirm:   false,
			AuditSensitivity:      "med",
		}, nil
	case "tier-3-informational":
		return Policy{
			Tier:                  Tier3Informational,
			RequireDryRun:         false,
			RequireDoubleApproval: false,
			RequireTypedConfirm:   false,
			AuditSensitivity:      "low",
		}, nil
	}
	return Policy{}, ErrTier
}
