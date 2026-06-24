// Package deployclass implements SR05 §12AH.2 deploy classification.
//
// A deploy is classified from the set of changed files in a PR plus a few
// explicit signals (label + incident/security reference + distinct services
// touched). The four classes drive gating in deploy.yml + canary.yml:
//
//	patch     — single service, no schema, no contract change   → CI + 1 reviewer
//	minor     — single service + migration|config|new endpoint   → CI + 2 reviewers
//	major     — multi-service|contract-breaking|schema-breaking   → full gate + canary
//	emergency — security patch / incident response hotfix         → fast-track + post-review
//
// The classifier is PURE (no I/O, no clock, no globals) so deploy-class-check.sh
// and the canary-controller share one authoritative implementation and the unit
// tests are deterministic. The shell lint passes the changed-file list + signals
// in; the controller uses the resulting Class to decide whether canary is
// mandatory (major + user-traffic).
package deployclass

import (
	"sort"
	"strings"
)

// Class is the SR05 §12AH.2 4-class enum.
type Class string

const (
	Patch     Class = "patch"
	Minor     Class = "minor"
	Major     Class = "major"
	Emergency Class = "emergency"
)

// Valid reports whether c is one of the four classes.
func (c Class) Valid() bool {
	switch c {
	case Patch, Minor, Major, Emergency:
		return true
	}
	return false
}

// CanaryRequired reports whether this class mandates the L3 canary protocol.
// Per §12AH.4 canary applies to `major` class + any service handling user
// traffic. The controller treats `major` as canary-required; emergency
// fast-tracks (post-deploy review instead of canary).
func (c Class) CanaryRequired() bool { return c == Major }

// Signals is the input to classification: the union of explicit PR signals and
// the derived facts about the changed file set.
type Signals struct {
	// ChangedFiles is the repo-relative path list from `git diff --name-only`.
	ChangedFiles []string
	// EmergencyLabel is true when the PR carries the `emergency` label.
	EmergencyLabel bool
	// IncidentID / SecurityFindingID back an emergency classification per
	// §12AH.2 ("emergency: emergency label + incident_id OR security_finding_id").
	IncidentID         string
	SecurityFindingID  string
	// ContractBreaking / SchemaBreaking are set by upstream checks (contract
	// diff lint / migration breaking-change lint). When true they force major.
	ContractBreaking bool
	SchemaBreaking   bool
}

// Classify returns the deploy class for the given signals per §12AH.2.
//
// Decision order (most-restrictive-wins is NOT used; the spec gives emergency
// an explicit fast-track that must win even for multi-service changes):
//
//  1. emergency — `emergency` label AND (incident_id OR security_finding_id)
//  2. major     — >1 distinct service touched, OR contract-breaking, OR
//     schema-breaking, OR any contracts/* change, OR a privileged/security
//     -sensitive path
//  3. minor     — single service WITH a migration file OR config change OR a
//     new endpoint under contracts/api/*
//  4. patch     — everything else (single service, no schema/contract/iface)
func Classify(s Signals) Class {
	// 1. Emergency fast-track (explicit, wins over blast radius).
	if s.EmergencyLabel && (strings.TrimSpace(s.IncidentID) != "" || strings.TrimSpace(s.SecurityFindingID) != "") {
		return Emergency
	}

	services := ServicesTouched(s.ChangedFiles)
	hasMigration := false
	hasConfig := false
	hasContractNonAPI := false // contracts/* OUTSIDE contracts/api/ (internal wire shapes)
	hasContractAPI := false    // contracts/api/* (an endpoint spec change)
	for _, f := range s.ChangedFiles {
		f = filepathToSlash(f)
		switch {
		case isMigration(f):
			hasMigration = true
		case isConfig(f):
			hasConfig = true
		}
		if strings.HasPrefix(f, "contracts/api/") {
			hasContractAPI = true
		} else if strings.HasPrefix(f, "contracts/") {
			hasContractNonAPI = true
		}
	}

	// 2. Major — §12AH.2: multi-service OR contract-breaking OR schema-breaking
	// OR an internal contract (non-API) wire-shape change (interface-level →
	// at least major). A NON-breaking contracts/api/ endpoint change is MINOR
	// (handled in step 3), per the spec's "new endpoint in contracts/api/*".
	if len(services) > 1 || s.ContractBreaking || s.SchemaBreaking || hasContractNonAPI {
		return Major
	}

	// 3. Minor — §12AH.2: single service with a migration OR config change OR a
	// new (non-breaking) endpoint in contracts/api/*.
	if hasMigration || hasConfig || hasContractAPI {
		return Minor
	}

	// 4. Patch — single (or zero) service, no schema/contract/config.
	return Patch
}

// ServicesTouched returns the sorted distinct set of `services/<name>` prefixes
// in the changed-file list. A change with no services/ prefix yields an empty
// set (treated as 0 services touched — e.g. a docs-only PR).
func ServicesTouched(files []string) []string {
	set := map[string]struct{}{}
	for _, f := range files {
		f = filepathToSlash(f)
		const p = "services/"
		if !strings.HasPrefix(f, p) {
			continue
		}
		rest := f[len(p):]
		i := strings.IndexByte(rest, '/')
		if i <= 0 {
			continue
		}
		set[rest[:i]] = struct{}{}
	}
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func isMigration(f string) bool {
	f = filepathToSlash(f)
	return strings.HasPrefix(f, "migrations/") && (strings.HasSuffix(f, ".up.sql") || strings.HasSuffix(f, ".down.sql") || strings.HasSuffix(f, ".sql"))
}

func isConfig(f string) bool {
	f = filepathToSlash(f)
	if strings.HasPrefix(f, "config/") {
		return true
	}
	// A `config/` segment anywhere in a service tree also counts.
	return strings.Contains(f, "/config/")
}

// filepathToSlash normalises Windows-style separators so the classifier is
// platform-agnostic (git always emits forward slashes, but defensive).
func filepathToSlash(f string) string { return strings.ReplaceAll(f, "\\", "/") }
