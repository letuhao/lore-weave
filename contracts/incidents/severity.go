package incidents

import "fmt"

// Severity is the 4-level incident severity per SR02 §12AE.2.
//
//	SEV0 — critical: data integrity loss, audit hash mismatch, personal
//	       data breach, total outage. Wake everyone (5min TTA).
//	SEV1 — high: canon injection, partial outage of a core surface,
//	       security exposure. Primary+secondary (15min TTA).
//	SEV2 — moderate: degraded feature, elevated error rate (30min TTA).
//	SEV3 — low: cosmetic, single-user, no SLO impact (best-effort).
type Severity string

const (
	SEV0 Severity = "SEV0"
	SEV1 Severity = "SEV1"
	SEV2 Severity = "SEV2"
	SEV3 Severity = "SEV3"
)

// allSeverities is the canonical ordered set (most→least severe).
var allSeverities = []Severity{SEV0, SEV1, SEV2, SEV3}

// IsValid reports whether s is one of the 4 declared severities.
func (s Severity) IsValid() bool {
	switch s {
	case SEV0, SEV1, SEV2, SEV3:
		return true
	default:
		return false
	}
}

// Rank returns 0 for SEV0 (most severe) … 3 for SEV3 (least severe).
// Returns -1 for an invalid severity. Lower rank == more severe.
func (s Severity) Rank() int {
	for i, sev := range allSeverities {
		if sev == s {
			return i
		}
	}
	return -1
}

// AtLeastAsSevereAs reports whether s is equal or more severe than other
// (i.e. s.Rank() <= other.Rank()). Invalid severities are never
// "at least as severe" as a valid one.
func (s Severity) AtLeastAsSevereAs(other Severity) bool {
	if !s.IsValid() || !other.IsValid() {
		return false
	}
	return s.Rank() <= other.Rank()
}

// ParseSeverity validates and returns a Severity, or an error.
func ParseSeverity(v string) (Severity, error) {
	s := Severity(v)
	if !s.IsValid() {
		return "", fmt.Errorf("incidents: invalid severity %q (want SEV0..SEV3)", v)
	}
	return s, nil
}

// AllSeverities returns a copy of the canonical ordered severity set.
func AllSeverities() []Severity {
	out := make([]Severity, len(allSeverities))
	copy(out, allSeverities)
	return out
}
