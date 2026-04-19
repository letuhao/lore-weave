package api

// T2-polish-2a — unit tests for the /metrics endpoint. Mirror the
// provider-registry coverage pattern.

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestMetricsEndpointServesPrometheusText — /metrics returns 200
// with a text/plain content-type and at least one of our counter
// series in the body. No auth needed (scraper is in-cluster).
func TestMetricsEndpointServesPrometheusText(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("metrics endpoint: want 200, got %d", w.Code)
	}

	contentType := w.Header().Get("Content-Type")
	if !strings.Contains(contentType, "text/plain") {
		t.Errorf("content-type: want text/plain, got %q", contentType)
	}

	body := w.Body.String()
	for _, name := range []string{
		"glossary_service_select_for_context_total",
		"glossary_service_bulk_extract_total",
		"glossary_service_known_entities_total",
		"glossary_service_entity_count_total",
	} {
		if !strings.Contains(body, name) {
			t.Errorf("metric %q not exposed in /metrics body", name)
		}
	}
}

// TestMetricsOutcomesPreSeeded — every declared outcome label
// appears on every counter vec, zero-initialized, so dashboards
// don't get "series not found" on first rate() query.
func TestMetricsOutcomesPreSeeded(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	body := w.Body.String()
	counters := []string{
		"glossary_service_select_for_context_total",
		"glossary_service_bulk_extract_total",
		"glossary_service_known_entities_total",
		"glossary_service_entity_count_total",
	}
	outcomes := []string{
		OutcomeOK, OutcomeValidationError,
		OutcomeInvalidBody, OutcomeQueryFailed,
	}
	for _, c := range counters {
		for _, o := range outcomes {
			// Prometheus text format for a 0-valued counter:
			// `counter_name{outcome="ok"} 0`
			marker := c + `{outcome="` + o + `"}`
			if !strings.Contains(body, marker) {
				t.Errorf("pre-seed missing: %s", marker)
			}
		}
	}
}

// TestMetricsCounterIncrements — instrument from a test directly
// and confirm the scrape reflects the bump. Proves the Inc()
// plumbing on the handler side actually affects the scrape we
// rely on for dashboards.
//
// Review-impl note: earlier version only asserted the series
// existed, which the pre-seed already guarantees — a broken
// Inc() would still have passed. Now parses the value and
// requires a delta of at least the number of Inc()s we issued.
// NOT t.Parallel() because the counter is a process-local
// shared global; a concurrent test that increments the same
// series would race our delta arithmetic.
func TestMetricsCounterIncrements(t *testing.T) {
	srv := &Server{}

	scrape := func() float64 {
		req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		for _, line := range strings.Split(w.Body.String(), "\n") {
			const prefix = `glossary_service_select_for_context_total{outcome="ok"} `
			if strings.HasPrefix(line, prefix) {
				var v float64
				// Ignore parse failure — absent counter returns 0.
				_, _ = fmt.Sscanf(strings.TrimPrefix(line, prefix), "%f", &v)
				return v
			}
		}
		t.Fatal("select_for_context ok series missing from scrape")
		return 0
	}

	before := scrape()
	SelectForContextTotal.WithLabelValues(OutcomeOK).Inc()
	SelectForContextTotal.WithLabelValues(OutcomeOK).Inc()
	after := scrape()

	if after-before < 2 {
		t.Errorf("counter delta: want ≥ 2, got %.0f (before=%.0f after=%.0f)",
			after-before, before, after)
	}
}

// TestMetricsEndpointNoAuth — /metrics is mounted outside the
// /internal route group so it doesn't require X-Internal-Token.
// Regression guard: if a future refactor moves it inside /internal,
// this test fails.
func TestMetricsEndpointNoAuth(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	// Deliberately NO X-Internal-Token header.
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("metrics without token: want 200, got %d body=%s", w.Code, w.Body.String())
	}
}
