// Package severity_classifier implements L7.D.2 — auto-escalation rules.
//
// SR02 §12AE.2 auto-severity rules:
//   - data integrity loss        → SEV0
//   - audit hash mismatch        → SEV0
//   - personal data breach       → SEV0
//   - total outage               → SEV0
//   - canon injection            → SEV1
//   - core surface partial outage→ SEV1
//   - security exposure          → SEV1
//   - degraded feature           → SEV2
//   - elevated error rate        → SEV2
//   - cosmetic / single-user     → SEV3
//
// The classifier is a PURE function of (alert signal, severity matrix). It
// holds no clock and no I/O; the matrix is loaded once and injected. This
// keeps classification deterministic + unit-testable without a live stack.
package severity_classifier

import (
	"fmt"
	"strings"

	"github.com/loreweave/foundation/contracts/incidents"
)

// Signal is the normalized alert input the classifier reasons over. The
// incident-bot's alert ingress maps an Alertmanager webhook (or a manual
// declaration) onto this shape.
type Signal struct {
	// Trigger is a canonical trigger id (see severity_matrix.yaml
	// auto_classify_triggers). When set + known, it is authoritative.
	Trigger string
	// AlertName is the raw alert name (e.g. "AuditHashMismatch"). Used as a
	// fallback keyword match when Trigger is empty/unknown.
	AlertName string
	// Labels carries alert labels; a label `severity: SEV0` (operator
	// override) wins over keyword inference but never over an explicit
	// known Trigger downgrade-guard (see Classify).
	Labels map[string]string
	// UserVisible flags whether the signal indicates user-facing impact.
	UserVisible bool
}

// Result is the classifier output.
type Result struct {
	Severity    incidents.Severity
	UserVisible bool
	// Reason explains which rule fired (for audit + the war-room card).
	Reason string
	// MatchedTrigger is the canonical trigger that classified the signal,
	// or "" if classification fell back to a keyword/label rule.
	MatchedTrigger string
}

// keyword fallback table: substring (lowercased) → canonical trigger.
// Only used when Signal.Trigger is empty or not in the matrix.
var keywordTriggers = []struct {
	keyword string
	trigger string
}{
	{"audithashmismatch", "audit_hash_mismatch"},
	{"audit_hash", "audit_hash_mismatch"},
	{"dataintegrity", "data_integrity_loss"},
	{"data_integrity", "data_integrity_loss"},
	{"personaldatabreach", "personal_data_breach"},
	{"databreach", "personal_data_breach"},
	{"totaloutage", "total_outage"},
	{"caoninjection", "canon_injection"}, // tolerate a common typo seen in alert names
	{"canoninjection", "canon_injection"},
	{"canon_injection", "canon_injection"},
	{"securityexposure", "security_exposure"},
	{"partialoutage", "core_surface_partial_outage"},
	{"degraded", "degraded_feature"},
	{"errorrate", "elevated_error_rate"},
}

// Classifier wraps the loaded matrix.
type Classifier struct {
	matrix *incidents.SeverityMatrix
}

// New builds a classifier from a loaded matrix. Returns an error if matrix
// is nil so misuse is caught at startup, not at first alert.
func New(matrix *incidents.SeverityMatrix) (*Classifier, error) {
	if matrix == nil {
		return nil, fmt.Errorf("severity_classifier: nil matrix")
	}
	return &Classifier{matrix: matrix}, nil
}

// Classify maps a Signal to a Result. Precedence:
//  1. Explicit known Trigger → matrix lookup (authoritative).
//  2. Operator label override `severity: SEVx` (valid value).
//  3. Keyword inference from AlertName.
//  4. Default → SEV2 (moderate; never silently SEV3 an unknown alert — an
//     unknown alert is more likely under-classified than over, and SEV2
//     pages primary on-call without waking everyone).
func (c *Classifier) Classify(sig Signal) Result {
	// 1. Explicit known trigger.
	if sig.Trigger != "" {
		if sev, ok := c.matrix.SeverityForTrigger(sig.Trigger); ok {
			return Result{
				Severity:       sev,
				UserVisible:    sig.UserVisible,
				Reason:         fmt.Sprintf("trigger %q → %s (matrix rule)", sig.Trigger, sev),
				MatchedTrigger: sig.Trigger,
			}
		}
	}

	// 2. Operator label override.
	if raw, ok := sig.Labels["severity"]; ok {
		if sev, err := incidents.ParseSeverity(strings.ToUpper(strings.TrimSpace(raw))); err == nil {
			return Result{
				Severity:    sev,
				UserVisible: sig.UserVisible,
				Reason:      fmt.Sprintf("operator label severity=%s", sev),
			}
		}
	}

	// 3. Keyword inference.
	if sig.AlertName != "" {
		norm := normalize(sig.AlertName)
		for _, kt := range keywordTriggers {
			if strings.Contains(norm, kt.keyword) {
				if sev, ok := c.matrix.SeverityForTrigger(kt.trigger); ok {
					return Result{
						Severity:       sev,
						UserVisible:    sig.UserVisible,
						Reason:         fmt.Sprintf("alert %q keyword→trigger %q → %s", sig.AlertName, kt.trigger, sev),
						MatchedTrigger: kt.trigger,
					}
				}
			}
		}
	}

	// 4. Safe default.
	return Result{
		Severity:    incidents.SEV2,
		UserVisible: sig.UserVisible,
		Reason:      fmt.Sprintf("no rule matched alert=%q trigger=%q; default SEV2", sig.AlertName, sig.Trigger),
	}
}

// normalize lowercases and strips non-alphanumerics for keyword matching.
func normalize(s string) string {
	var b strings.Builder
	for _, r := range strings.ToLower(s) {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		}
	}
	return b.String()
}
