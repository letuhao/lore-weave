// Package inbox is the HTTP handler that ingests alertmanager webhook
// payloads + converts them into cycle-19 alert envelopes for persistence.
//
// Alertmanager webhook contract (v4):
//
//	{
//	  "version": "4",
//	  "groupKey": "...",
//	  "status": "firing" | "resolved",
//	  "receiver": "pagerduty-sre",
//	  "alerts": [{
//	    "status": "firing",
//	    "labels": {...},
//	    "annotations": {...},
//	    "startsAt": "...",
//	    "fingerprint": "..."
//	  }]
//	}
//
// This handler converts each alert into an `alerts.Envelope` (cycle 19)
// and persists via store.Store. Cycle-19 invariant: correlation_id MUST
// be preserved end-to-end. We pull it from labels.correlation_id if
// present; otherwise generate a fresh UUID so postmortem reconstruction
// still has SOMETHING to chain by.
package inbox

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/alert-recorder/internal/store"
	"github.com/loreweave/foundation/contracts/alerts"
)

// AlertmanagerAlert is the per-alert struct in the alertmanager webhook v4 payload.
type AlertmanagerAlert struct {
	Status       string            `json:"status"`
	Labels       map[string]string `json:"labels"`
	Annotations  map[string]string `json:"annotations"`
	StartsAt     string            `json:"startsAt"`
	EndsAt       string            `json:"endsAt"`
	Fingerprint  string            `json:"fingerprint"`
	GeneratorURL string            `json:"generatorURL"`
}

// AlertmanagerPayload is the top-level alertmanager webhook body.
type AlertmanagerPayload struct {
	Version  string              `json:"version"`
	GroupKey string              `json:"groupKey"`
	Status   string              `json:"status"`
	Receiver string              `json:"receiver"`
	Alerts   []AlertmanagerAlert `json:"alerts"`
}

// Handler is the HTTP handler factory. now() override is for tests.
type Handler struct {
	Store store.Store
	Now   func() time.Time
}

// NewHandler constructs a Handler with the system clock.
func NewHandler(s store.Store) *Handler {
	return &Handler{Store: s, Now: time.Now}
}

// ServeHTTP is the POST /v1/alerts/inbox handler.
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST required", http.StatusMethodNotAllowed)
		return
	}
	var p AlertmanagerPayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	if p.Version != "4" {
		http.Error(w, fmt.Sprintf("alertmanager webhook version %q unsupported (want 4)", p.Version), http.StatusBadRequest)
		return
	}
	ingested := 0
	for _, a := range p.Alerts {
		env, err := ToEnvelope(a, h.Now())
		if err != nil {
			// Skip malformed alerts but keep ingesting the rest of the batch.
			// Operators can rely on lw_alert_recorder_malformed_total in V1+30d.
			continue
		}
		outcome := store.Outcome{
			AlertID:       env.AlertID,
			RuleID:        env.RuleID,
			Severity:      env.Severity,
			Action:        env.Action,
			SLIRef:        env.Labels["sli_ref"],
			Tier:          env.Labels["tier"],
			CorrelationID: env.CorrelationID,
			State:         stateFromStatus(a.Status),
			StateAt:       h.Now(),
			ReceivedAt:    h.Now(),
		}
		if err := h.Store.WriteOutcome(r.Context(), outcome); err != nil {
			http.Error(w, "store: "+err.Error(), http.StatusInternalServerError)
			return
		}
		ingested++
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int{"ingested": ingested}) //nolint:errcheck
}

// ToEnvelope converts an alertmanager alert into a cycle-19 envelope.
// Exported so tests can drive directly without HTTP.
func ToEnvelope(a AlertmanagerAlert, now time.Time) (alerts.Envelope, error) {
	if a.Labels == nil {
		return alerts.Envelope{}, errors.New("inbox: alert.labels nil")
	}
	ruleID := a.Labels["alertname"]
	if ruleID == "" {
		return alerts.Envelope{}, errors.New("inbox: alertname label required")
	}

	sev := severityFromLabel(a.Labels["severity"])
	act := actionFromLabel(a.Labels["action"], a.Labels["route"])

	summary := a.Annotations["summary"]
	if summary == "" {
		summary = ruleID
	}
	// Hard cap to envelope spec max 120
	if len(summary) > 120 {
		summary = summary[:120]
	}

	corr := a.Labels["correlation_id"]
	if corr == "" {
		// Generate one so postmortems still have a chain key.
		corr = uuid.New().String()
	}

	// Parse startsAt; default to "now" if missing/malformed (alertmanager
	// is supposed to set it but we don't want a missing field to drop the alert).
	firedAt := now
	if a.StartsAt != "" {
		if t, err := time.Parse(time.RFC3339Nano, a.StartsAt); err == nil {
			firedAt = t
		}
	}

	env := alerts.Envelope{
		Version:       alerts.EnvelopeVersion,
		AlertID:       uuid.New(),
		RuleID:        ruleID,
		Severity:      sev,
		Action:        act,
		Summary:       summary,
		Description:   a.Annotations["description"],
		Labels:        a.Labels,
		Annotations:   a.Annotations,
		CorrelationID: corr,
		FiredAtNanos:  firedAt.UnixNano(),
	}

	// Cycle-19 invariant: envelope must validate.
	if err := env.Validate(); err != nil {
		return alerts.Envelope{}, fmt.Errorf("inbox: envelope validate: %w", err)
	}
	return env, nil
}

func severityFromLabel(s string) alerts.Severity {
	switch s {
	case "page":
		return alerts.SeverityPage
	case "warn":
		return alerts.SeverityWarn
	case "info":
		return alerts.SeverityInfo
	case "silence":
		return alerts.SeveritySilence
	default:
		// Default to warn — we still ship it but don't page.
		return alerts.SeverityWarn
	}
}

func actionFromLabel(action, route string) alerts.Action {
	// Prefer explicit `action` label; fall back to legacy `route`.
	if action == "" {
		action = route
	}
	switch action {
	case "pagerduty":
		return alerts.ActionPagerDuty
	case "slack":
		return alerts.ActionSlack
	case "email":
		return alerts.ActionEmail
	default:
		return alerts.ActionLogOnly
	}
}

func stateFromStatus(s string) string {
	switch s {
	case "firing":
		return "dispatched"
	case "resolved":
		return "resolved"
	default:
		return "received"
	}
}

// ServeContext is a tiny helper for tests that want to invoke without an
// http.Server harness.
func (h *Handler) ServeContext(ctx context.Context, p AlertmanagerPayload) (ingested int, err error) {
	for _, a := range p.Alerts {
		env, err := ToEnvelope(a, h.Now())
		if err != nil {
			continue
		}
		outcome := store.Outcome{
			AlertID:       env.AlertID,
			RuleID:        env.RuleID,
			Severity:      env.Severity,
			Action:        env.Action,
			SLIRef:        env.Labels["sli_ref"],
			Tier:          env.Labels["tier"],
			CorrelationID: env.CorrelationID,
			State:         stateFromStatus(a.Status),
			StateAt:       h.Now(),
			ReceivedAt:    h.Now(),
		}
		if err := h.Store.WriteOutcome(ctx, outcome); err != nil {
			return ingested, err
		}
		ingested++
	}
	return ingested, nil
}
