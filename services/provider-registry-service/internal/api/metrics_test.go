package api

// D-K17.2a-01 — metrics endpoint + counter exposure tests.

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/config"
)

func newMetricsTestServer(t *testing.T) *Server {
	t.Helper()
	return NewServer(nil, &config.Config{
		JWTSecret:            "metrics-test-secret-32-characters",
		InternalServiceToken: "metrics-test-internal-token",
	}, nil)
}

func TestMetricsEndpointServes(t *testing.T) {
	srv := newMetricsTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("/metrics: expected 200, got %d", w.Code)
	}
	ct := w.Header().Get("Content-Type")
	if !strings.HasPrefix(ct, "text/plain") {
		t.Errorf("/metrics: expected text/plain content-type, got %q", ct)
	}
}

func TestMetricsEndpointExposesProxyCounters(t *testing.T) {
	srv := newMetricsTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	body := w.Body.String()
	for _, want := range []string{
		"provider_registry_proxy_requests_total",
		"provider_registry_invoke_requests_total",
		"provider_registry_embed_requests_total",
		"provider_registry_verify_requests_total",
	} {
		if !strings.Contains(body, want) {
			t.Errorf("/metrics missing %s series", want)
		}
	}
}

func TestMetricsEndpointPreSeedsAllOutcomeLabels(t *testing.T) {
	// Pre-seed ensures dashboards can rate() immediately without
	// waiting for the first non-zero increment.
	srv := newMetricsTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	body := w.Body.String()
	// Look for a handful of outcome labels on ProxyRequestsTotal.
	for _, outcome := range []string{
		OutcomeOK, OutcomeInvalidJSON, OutcomeMissingCredential,
		OutcomeDecryptFailed, OutcomeTooLarge,
	} {
		label := `outcome="` + outcome + `"`
		if !strings.Contains(body, label) {
			t.Errorf("proxy counter missing label %s in output", label)
		}
	}
}

func TestMetricsEndpointIsUnauthed(t *testing.T) {
	// /metrics deliberately has no auth — in-cluster scrapers only.
	// Same convention as every other Go service's metrics route.
	srv := newMetricsTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	// Don't set X-Internal-Token or Authorization.
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Errorf("/metrics should serve without auth, got %d", w.Code)
	}
}

func TestProxyMissingCredentialCounterIncrements(t *testing.T) {
	// Record the counter value, increment (mimicking the guard path),
	// and verify /metrics reflects the bump. We're testing the
	// instrument, not the business flow — the real guard path is
	// covered by the existing proxy integration tests.
	before := testCounterValue(t, "provider_registry_proxy_requests_total",
		`outcome="missing_credential"`)
	ProxyRequestsTotal.WithLabelValues(OutcomeMissingCredential).Inc()
	after := testCounterValue(t, "provider_registry_proxy_requests_total",
		`outcome="missing_credential"`)
	if after != before+1 {
		t.Errorf("missing_credential counter: expected +1 (%g -> %g), got delta %g",
			before, after, after-before)
	}
}

// testCounterValue scrapes /metrics and parses a line like
//
//	provider_registry_proxy_requests_total{outcome="ok"} 3
//
// returning the numeric value. Returns 0 if the series is absent.
func testCounterValue(t *testing.T, metricName, labelFragment string) float64 {
	t.Helper()
	srv := newMetricsTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	for _, line := range strings.Split(w.Body.String(), "\n") {
		if !strings.HasPrefix(line, metricName) {
			continue
		}
		if !strings.Contains(line, labelFragment) {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		var v float64
		if _, err := fmt.Sscanf(fields[len(fields)-1], "%g", &v); err != nil {
			continue
		}
		return v
	}
	return 0
}
