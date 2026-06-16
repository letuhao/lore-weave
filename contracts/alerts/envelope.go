package alerts

import (
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EnvelopeVersion is the wire-format version of the Envelope. Bump only
// for backward-incompatible changes; receivers MUST reject unknown
// versions (defense vs silent drift).
const EnvelopeVersion = 1

// Severity is the 4-step taxonomy per SR09 §12AL.
type Severity string

const (
	// SeverityPage — wake someone up. Auto-paged via PagerDuty.
	// Reserved for service-down + SLO-burn-fast.
	SeverityPage Severity = "page"

	// SeverityWarn — investigate within business hours. Slack #alerts.
	// SLO-burn-slow + capacity at 75% + degraded-mode triggers.
	SeverityWarn Severity = "warn"

	// SeverityInfo — heads-up. Slack #alerts-info. Capacity at 50% +
	// auto-mitigated drills.
	SeverityInfo Severity = "info"

	// SeveritySilence — fired but never delivered (used to keep the
	// timeseries alive without paging during silenced windows). NEVER
	// use for new alerts; reserved for the alert_silences ack flow.
	SeveritySilence Severity = "silence"
)

// IsValid mirrors the enum constraint.
func (s Severity) IsValid() bool {
	switch s {
	case SeverityPage, SeverityWarn, SeverityInfo, SeveritySilence:
		return true
	}
	return false
}

// Action is the 4-class routing destination per SR2 alert routing matrix.
type Action string

const (
	ActionPagerDuty Action = "pagerduty"
	ActionSlack     Action = "slack"
	ActionEmail     Action = "email"
	ActionLogOnly   Action = "log_only"
)

// IsValid mirrors the enum constraint.
func (a Action) IsValid() bool {
	switch a {
	case ActionPagerDuty, ActionSlack, ActionEmail, ActionLogOnly:
		return true
	}
	return false
}

// Envelope is the canonical alert wire format. Every alertmanager push
// + every alert-receiver consumer ships this exact shape.
//
// Field naming is the wire contract — DO NOT rename without bumping
// EnvelopeVersion + writing a migration receiver in the cycle that
// changes the shape.
type Envelope struct {
	// Version pins to EnvelopeVersion. Receivers reject mismatches.
	Version int `json:"v"`

	// AlertID is the global unique id for this firing of the alert.
	// Allows the receiver to dedupe + ack.
	AlertID uuid.UUID `json:"alert_id"`

	// RuleID identifies which alert rule fired (e.g.,
	// "LWMetaPostgresPrimaryDown"). Matches the cycle-7
	// infra/prometheus/alerts/*.yaml rule names.
	RuleID string `json:"rule_id"`

	// Severity drives the receiver's wake-someone-up decision.
	Severity Severity `json:"severity"`

	// Action is the canonical routing destination. Receivers MAY route
	// to additional destinations (e.g., audit-log every alert), but
	// MUST route to Action.
	Action Action `json:"action"`

	// Summary is a short human title (≤ 120 chars). Optimized for
	// pager screens.
	Summary string `json:"summary"`

	// Description is the long-form context with metric values + runbook
	// link. Receivers use this for the body of the page.
	Description string `json:"description,omitempty"`

	// Labels mirrors the Prometheus label set the alert fired with.
	// Drives team routing + correlation.
	Labels map[string]string `json:"labels,omitempty"`

	// Annotations holds runbook URLs, dashboard URLs, query expressions.
	Annotations map[string]string `json:"annotations,omitempty"`

	// CorrelationID is the request_id / trace_id the alert chains to (if
	// the alert was triggered by a request-scoped event). Empty for
	// background / cron-driven alerts. CRITICAL invariant: every
	// receiver downstream MUST preserve correlation_id end-to-end so
	// postmortem reconstruction works.
	CorrelationID string `json:"correlation_id,omitempty"`

	// FiredAtNanos is the firing wall-clock instant. Receivers SHOULD
	// reject envelopes with a future timestamp (clock skew defense).
	FiredAtNanos int64 `json:"fired_at_nanos"`
}

// Validate enforces the shape invariants in-process so receivers can
// fail BEFORE attempting to persist a malformed envelope.
func (e *Envelope) Validate() error {
	if e == nil {
		return errors.New("alerts: nil Envelope")
	}
	if e.Version != EnvelopeVersion {
		return fmt.Errorf("alerts: envelope version mismatch (got %d want %d)", e.Version, EnvelopeVersion)
	}
	if e.AlertID == uuid.Nil {
		return errors.New("alerts: alert_id required")
	}
	if e.RuleID == "" {
		return errors.New("alerts: rule_id required")
	}
	if !e.Severity.IsValid() {
		return fmt.Errorf("alerts: invalid severity %q", e.Severity)
	}
	if !e.Action.IsValid() {
		return fmt.Errorf("alerts: invalid action %q", e.Action)
	}
	if e.Summary == "" {
		return errors.New("alerts: summary required")
	}
	if len(e.Summary) > 120 {
		return fmt.Errorf("alerts: summary too long (%d > 120)", len(e.Summary))
	}
	if e.FiredAtNanos <= 1577836800000000000 {
		return fmt.Errorf("alerts: fired_at_nanos must be > 1577836800000000000 (got %d)", e.FiredAtNanos)
	}
	// Clock-skew defense — reject envelopes more than 1h in the future.
	if e.FiredAtNanos > time.Now().Add(1*time.Hour).UnixNano() {
		return fmt.Errorf("alerts: fired_at_nanos %d > 1h in the future (clock skew)", e.FiredAtNanos)
	}
	return nil
}
