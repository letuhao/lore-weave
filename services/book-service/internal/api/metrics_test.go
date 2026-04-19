package api

// T2-polish-2b — /metrics endpoint unit tests. Mirrors the glossary-
// service metrics_test.go (which absorbed the T2-polish-2a review
// lessons: value-delta assertion, trimmed outcome list, non-parallel
// delta test).

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestMetricsEndpointServesPrometheusText — /metrics returns 200
// with text/plain content-type and every declared counter name.
func TestMetricsEndpointServesPrometheusText(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("metrics endpoint: want 200, got %d", w.Code)
	}
	if ct := w.Header().Get("Content-Type"); !strings.Contains(ct, "text/plain") {
		t.Errorf("content-type: want text/plain, got %q", ct)
	}

	body := w.Body.String()
	for _, name := range []string{
		"book_service_projection_total",
		"book_service_chapters_list_total",
		"book_service_chapter_fetch_total",
	} {
		if !strings.Contains(body, name) {
			t.Errorf("metric %q not exposed in /metrics body", name)
		}
	}
}

// TestMetricsOutcomesPreSeeded — every declared outcome is zero-
// initialised on every counter so dashboards don't see empty series
// on first scrape.
func TestMetricsOutcomesPreSeeded(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	body := w.Body.String()
	counters := []string{
		"book_service_projection_total",
		"book_service_chapters_list_total",
		"book_service_chapter_fetch_total",
	}
	outcomes := []string{
		OutcomeOK, OutcomeValidationError,
		OutcomeNotFound, OutcomeQueryFailed,
	}
	for _, c := range counters {
		for _, o := range outcomes {
			marker := c + `{outcome="` + o + `"}`
			if !strings.Contains(body, marker) {
				t.Errorf("pre-seed missing: %s", marker)
			}
		}
	}
}

// TestMetricsCounterIncrements — a manual Inc() must reflect as a
// delta in the scraped value. Not t.Parallel() because the counter
// is a process-local global; concurrent tests would race.
func TestMetricsCounterIncrements(t *testing.T) {
	srv := &Server{}

	scrape := func() float64 {
		req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		for _, line := range strings.Split(w.Body.String(), "\n") {
			const prefix = `book_service_projection_total{outcome="ok"} `
			if strings.HasPrefix(line, prefix) {
				var v float64
				_, _ = fmt.Sscanf(strings.TrimPrefix(line, prefix), "%f", &v)
				return v
			}
		}
		t.Fatal("book_service_projection_total ok series missing from scrape")
		return 0
	}

	before := scrape()
	ProjectionTotal.WithLabelValues(OutcomeOK).Inc()
	ProjectionTotal.WithLabelValues(OutcomeOK).Inc()
	after := scrape()

	if after-before < 2 {
		t.Errorf("counter delta: want ≥ 2, got %.0f (before=%.0f after=%.0f)",
			after-before, before, after)
	}
}

// TestMetricsEndpointNoAuth — /metrics is mounted outside /internal
// so scrapers don't need X-Internal-Token. Regression guard: a
// future refactor moving it under /internal fails this test.
func TestMetricsEndpointNoAuth(t *testing.T) {
	t.Parallel()

	srv := &Server{}
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	// No X-Internal-Token header.
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("metrics without token: want 200, got %d body=%s", w.Code, w.Body.String())
	}
}
