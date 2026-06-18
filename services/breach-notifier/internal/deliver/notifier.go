// Package deliver delivers the GDPR Art.33 DPO breach-notice obligation
// (gdpr.dpo_notice_required.v1) via a pluggable channel. Q-L7-1: incident-bot
// DECIDES + EMITS the obligation; THIS service (breach-notifier) DELIVERS it +
// records a confirmed timestamp distinct from "emitted".
package deliver

import (
	"context"
	"log/slog"
	"time"
)

// DPONotice is the obligation to deliver to the Data Protection Officer.
type DPONotice struct {
	IncidentID string
	Subject    string
	Body       string
	Deadline   time.Time
}

// Notifier delivers a DPO notice and returns the channel it was delivered on
// (e.g. "log", "slack:#compliance"). A non-nil error means delivery FAILED — the
// caller must NOT record it as confirmed and must NOT ack (so Redis re-delivers).
type Notifier interface {
	Deliver(ctx context.Context, n DPONotice) (channel string, err error)
}

// LogNotifier is the default no-creds Notifier: it writes the notice as a
// structured audit line and reports the "log" channel. This is a GENUINE delivery
// for dev / no-Slack environments (an auditable record), NOT a silent drop — the
// real Slack transport is a separate, opt-in scaffold (slack.go, D-BREACH-SLACK-LIVE).
type LogNotifier struct{ Logger *slog.Logger }

// NewLogNotifier builds a LogNotifier (defaults to slog.Default()).
func NewLogNotifier(l *slog.Logger) *LogNotifier {
	if l == nil {
		l = slog.Default()
	}
	return &LogNotifier{Logger: l}
}

var _ Notifier = (*LogNotifier)(nil)

// Deliver writes the DPO notice to the structured log — including the Body, which is
// the substantive Art.33 content (nature of the breach, categories, affected numbers).
// Logging only subject/deadline would make the "delivered" record an empty notice.
func (n *LogNotifier) Deliver(_ context.Context, notice DPONotice) (string, error) {
	n.Logger.Info("GDPR Art.33 DPO breach notice delivered (log channel)",
		"incident_id", notice.IncidentID,
		"subject", notice.Subject,
		"body", notice.Body,
		"deadline", notice.Deadline.UTC().Format(time.RFC3339))
	return "log", nil
}
