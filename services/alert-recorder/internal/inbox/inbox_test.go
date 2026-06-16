package inbox

import (
	"context"
	"testing"
	"time"

	"github.com/loreweave/alert-recorder/internal/store"
	"github.com/loreweave/foundation/contracts/alerts"
)

func fixedNow() time.Time {
	return time.Unix(1_700_000_000, 0).UTC()
}

func TestToEnvelope_ExtractsCorrelationID(t *testing.T) {
	a := AlertmanagerAlert{
		Status: "firing",
		Labels: map[string]string{
			"alertname":      "LWSLOBurnPageSessionAvailability",
			"severity":       "page",
			"action":         "pagerduty",
			"sli_ref":        "sli_session_availability",
			"tier":           "paid",
			"correlation_id": "abc-123-explicit",
		},
		Annotations: map[string]string{
			"summary":     "SLO burn 75-90% — session availability (paid)",
			"description": "long description",
		},
		StartsAt: fixedNow().Format(time.RFC3339Nano),
	}
	env, err := ToEnvelope(a, fixedNow())
	if err != nil {
		t.Fatalf("ToEnvelope: %v", err)
	}
	if env.CorrelationID != "abc-123-explicit" {
		t.Errorf("correlation_id=%q; want abc-123-explicit (preserve end-to-end)", env.CorrelationID)
	}
	if env.Severity != alerts.SeverityPage {
		t.Errorf("severity=%v; want page", env.Severity)
	}
	if env.Action != alerts.ActionPagerDuty {
		t.Errorf("action=%v; want pagerduty", env.Action)
	}
}

func TestToEnvelope_GeneratesCorrelationIDWhenMissing(t *testing.T) {
	a := AlertmanagerAlert{
		Status: "firing",
		Labels: map[string]string{
			"alertname": "LWMetaPostgresPrimaryDown",
			"severity":  "page",
			"action":    "pagerduty",
		},
		Annotations: map[string]string{"summary": "meta-postgres primary down"},
		StartsAt:    fixedNow().Format(time.RFC3339Nano),
	}
	env, err := ToEnvelope(a, fixedNow())
	if err != nil {
		t.Fatalf("ToEnvelope: %v", err)
	}
	if env.CorrelationID == "" {
		t.Error("correlation_id auto-generation failed; envelope must always carry one for postmortem chain")
	}
}

func TestToEnvelope_RejectsMissingAlertname(t *testing.T) {
	a := AlertmanagerAlert{
		Status: "firing",
		Labels: map[string]string{"severity": "page"},
	}
	if _, err := ToEnvelope(a, fixedNow()); err == nil {
		t.Error("want error for missing alertname; got nil")
	}
}

func TestToEnvelope_TruncatesLongSummary(t *testing.T) {
	long := ""
	for i := 0; i < 200; i++ {
		long += "x"
	}
	a := AlertmanagerAlert{
		Status: "firing",
		Labels: map[string]string{"alertname": "Test", "severity": "warn"},
		Annotations: map[string]string{
			"summary": long,
		},
		StartsAt: fixedNow().Format(time.RFC3339Nano),
	}
	env, err := ToEnvelope(a, fixedNow())
	if err != nil {
		t.Fatalf("ToEnvelope: %v", err)
	}
	if len(env.Summary) > 120 {
		t.Errorf("summary len=%d; want <= 120 (envelope spec)", len(env.Summary))
	}
}

func TestHandler_ServeContext_PersistsOutcomesToStore(t *testing.T) {
	memStore := store.NewMemoryStore()
	h := &Handler{Store: memStore, Now: fixedNow}
	payload := AlertmanagerPayload{
		Version:  "4",
		GroupKey: "k",
		Status:   "firing",
		Receiver: "pagerduty-sre",
		Alerts: []AlertmanagerAlert{
			{
				Status: "firing",
				Labels: map[string]string{
					"alertname": "LWWsConnectionSaturation",
					"severity":  "page",
					"action":    "pagerduty",
				},
				Annotations: map[string]string{"summary": "WS sat"},
				StartsAt:    fixedNow().Format(time.RFC3339Nano),
			},
			{
				Status: "firing",
				Labels: map[string]string{
					"alertname": "LWSLOBurnWarnTurnCompletion",
					"severity":  "warn",
					"action":    "slack",
					"sli_ref":   "sli_turn_completion",
					"tier":      "paid",
				},
				Annotations: map[string]string{"summary": "turn burn warn"},
				StartsAt:    fixedNow().Format(time.RFC3339Nano),
			},
		},
	}
	ingested, err := h.ServeContext(context.Background(), payload)
	if err != nil {
		t.Fatalf("ServeContext: %v", err)
	}
	if ingested != 2 {
		t.Errorf("ingested=%d; want 2", ingested)
	}
	outs, err := memStore.ListOutcomes(context.Background(), 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(outs) != 2 {
		t.Errorf("store outcomes=%d; want 2", len(outs))
	}
	// Verify cycle-19 envelope fields preserved.
	// ListOutcomes returns newest-first; alert2 (with sli_ref) was ingested
	// second so it's outs[0].
	if outs[0].SLIRef != "sli_turn_completion" {
		t.Errorf("outcome sli_ref=%q; want sli_turn_completion", outs[0].SLIRef)
	}
	if outs[0].Tier != "paid" {
		t.Errorf("outcome tier=%q; want paid", outs[0].Tier)
	}
}

func TestHandler_ServeContext_SkipsMalformedAlerts(t *testing.T) {
	memStore := store.NewMemoryStore()
	h := &Handler{Store: memStore, Now: fixedNow}
	payload := AlertmanagerPayload{
		Version: "4",
		Alerts: []AlertmanagerAlert{
			// MALFORMED: no labels
			{Status: "firing"},
			// GOOD
			{
				Status: "firing",
				Labels: map[string]string{
					"alertname": "Good",
					"severity":  "page",
					"action":    "pagerduty",
				},
				Annotations: map[string]string{"summary": "ok"},
				StartsAt:    fixedNow().Format(time.RFC3339Nano),
			},
		},
	}
	ingested, err := h.ServeContext(context.Background(), payload)
	if err != nil {
		t.Fatalf("ServeContext: %v", err)
	}
	if ingested != 1 {
		t.Errorf("ingested=%d; want 1 (1 malformed skipped)", ingested)
	}
}

func TestSeverityFromLabel_AllValues(t *testing.T) {
	cases := []struct {
		in   string
		want alerts.Severity
	}{
		{"page", alerts.SeverityPage},
		{"warn", alerts.SeverityWarn},
		{"info", alerts.SeverityInfo},
		{"silence", alerts.SeveritySilence},
		{"unknown", alerts.SeverityWarn}, // default fallback
		{"", alerts.SeverityWarn},
	}
	for _, c := range cases {
		if got := severityFromLabel(c.in); got != c.want {
			t.Errorf("severityFromLabel(%q)=%v; want %v", c.in, got, c.want)
		}
	}
}

func TestActionFromLabel_FallbackToRoute(t *testing.T) {
	if got := actionFromLabel("", "pagerduty"); got != alerts.ActionPagerDuty {
		t.Errorf("empty action + route=pagerduty: got %v; want pagerduty", got)
	}
	if got := actionFromLabel("slack", "pagerduty"); got != alerts.ActionSlack {
		t.Errorf("explicit action wins: got %v; want slack", got)
	}
	if got := actionFromLabel("", ""); got != alerts.ActionLogOnly {
		t.Errorf("default: got %v; want log_only", got)
	}
}
