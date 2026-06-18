// Package gdpr_breach_flow implements L7.D.7 — GDPR Art.33 72-hour
// personal-data-breach notification flow.
//
// Per §12X: when an incident is classified as a personal-data breach, GDPR
// Art.33 starts a 72-hour clock to notify the supervisory authority. This
// package:
//   - records the breach timeline (detected_at → notification deadline)
//   - sends the DPO notice (via the injected Notifier)
//   - reports time-remaining + an "approaching deadline" alert flag
//
// The clock is injected (now func) so deadline math is deterministic in tests.
// The Notifier is abstracted so unit tests run without email infra.
package gdpr_breach_flow

import (
	"context"
	"fmt"
	"time"
)

// NotificationDeadline is the GDPR Art.33 window.
const NotificationDeadline = 72 * time.Hour

// ApproachingThreshold is when we start raising "deadline approaching"
// alerts (12h before the 72h deadline).
const ApproachingThreshold = 12 * time.Hour

// DPONotifier delivers the breach notice to the Data Protection Officer.
type DPONotifier interface {
	NotifyDPO(ctx context.Context, subject, body string) error
}

// BreachRecord captures the breach timeline (audited; persisted by caller).
type BreachRecord struct {
	IncidentID     string
	DetectedAt     time.Time
	Deadline       time.Time // DetectedAt + 72h
	DataCategories string
	AffectedCount  int
	DPONotifiedAt  *time.Time // set once the DPO notice is sent
}

// Flow orchestrates the breach notification.
type Flow struct {
	notifier DPONotifier
	now      func() time.Time
}

// New builds a Flow. Fails closed on nil deps.
func New(notifier DPONotifier, now func() time.Time) (*Flow, error) {
	if notifier == nil {
		return nil, fmt.Errorf("gdpr_breach_flow: nil DPO notifier")
	}
	if now == nil {
		return nil, fmt.Errorf("gdpr_breach_flow: nil clock")
	}
	return &Flow{notifier: notifier, now: now}, nil
}

// Open starts a breach record + sends the initial DPO notice. detectedAt is
// the authoritative breach detection time (the 72h clock anchor).
func (f *Flow) Open(ctx context.Context, incidentID string, detectedAt time.Time, dataCategories string, affectedCount int) (*BreachRecord, error) {
	if incidentID == "" {
		return nil, fmt.Errorf("gdpr_breach_flow: empty incident id")
	}
	if detectedAt.IsZero() {
		return nil, fmt.Errorf("gdpr_breach_flow: zero detected_at (72h clock needs an anchor)")
	}
	rec := &BreachRecord{
		IncidentID:     incidentID,
		DetectedAt:     detectedAt,
		Deadline:       detectedAt.Add(NotificationDeadline),
		DataCategories: dataCategories,
		AffectedCount:  affectedCount,
	}
	subject := fmt.Sprintf("GDPR Art.33 — personal data breach %s", incidentID)
	body := fmt.Sprintf(
		"Breach detected at %s UTC.\nData categories: %s\nAffected subjects: %d\n72h notification deadline: %s UTC.",
		detectedAt.UTC().Format(time.RFC3339), dataCategories, affectedCount,
		rec.Deadline.UTC().Format(time.RFC3339),
	)
	if err := f.notifier.NotifyDPO(ctx, subject, body); err != nil {
		// The record still exists for forensics even if the notice send
		// failed — the caller must retry/escalate.
		return rec, fmt.Errorf("gdpr_breach_flow: DPO notify failed (record retained): %w", err)
	}
	t := f.now()
	rec.DPONotifiedAt = &t
	return rec, nil
}

// TimeRemaining returns how long until the Art.33 deadline (may be negative
// if the deadline has passed).
func (f *Flow) TimeRemaining(rec *BreachRecord) time.Duration {
	return rec.Deadline.Sub(f.now())
}

// IsApproachingDeadline reports whether the deadline is within
// ApproachingThreshold (and not yet missed). Drives a reminder alert.
func (f *Flow) IsApproachingDeadline(rec *BreachRecord) bool {
	rem := f.TimeRemaining(rec)
	return rem > 0 && rem <= ApproachingThreshold
}

// IsDeadlineMissed reports whether the 72h deadline has elapsed.
func (f *Flow) IsDeadlineMissed(rec *BreachRecord) bool {
	return f.TimeRemaining(rec) <= 0
}
