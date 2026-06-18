package metrics

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func scrape(t *testing.T, m *Metrics) string {
	t.Helper()
	rec := httptest.NewRecorder()
	m.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("scrape status %d", rec.Code)
	}
	return rec.Body.String()
}

func TestNewRegistersAllSeries(t *testing.T) {
	m := New()
	out := scrape(t, m)
	for _, name := range []string{
		"lw_canary_stage", "lw_canary_controller_observed_burn", "lw_canary_abort_total", "lw_deploy_freeze_active",
	} {
		if !strings.Contains(out, name) {
			t.Fatalf("metric %q not registered/rendered", name)
		}
	}
	// Stage starts at -1 (no active canary) so dashboards distinguish "none"
	// from "stage 0".
	if !strings.Contains(out, "lw_canary_stage -1") {
		t.Fatalf("lw_canary_stage must start at -1, got:\n%s", out)
	}
}

func TestSetters(t *testing.T) {
	m := New()
	m.SetStage(3)
	m.SetObservedBurn(0.25)
	m.IncAbort()
	m.IncAbort()
	m.SetFreeze(true)

	out := scrape(t, m)
	for _, want := range []string{
		"lw_canary_stage 3",
		"lw_canary_controller_observed_burn 0.25",
		"lw_canary_abort_total 2",
		"lw_deploy_freeze_active 1",
	} {
		if !strings.Contains(out, want) {
			t.Fatalf("expected %q in scrape:\n%s", want, out)
		}
	}

	m.SetFreeze(false)
	if !strings.Contains(scrape(t, m), "lw_deploy_freeze_active 0") {
		t.Fatal("freeze should reset to 0")
	}
}
