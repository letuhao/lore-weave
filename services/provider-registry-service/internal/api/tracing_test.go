package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/loreweave/observability/obstest"
)

// TestRouter_EmitsServerSpan regression-locks observability.ChiMiddleware
// being wired into Router(): if someone drops r.Use(ChiMiddleware()) this
// fails. ChiMiddleware's own behaviour is unit-tested in the observability
// module — this only proves provider-registry actually mounts it.
func TestRouter_EmitsServerSpan(t *testing.T) {
	sr := obstest.RecordingProvider(t)

	ts := httptest.NewServer(testServer("test-secret").Router())
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/health")
	if err != nil {
		t.Fatalf("GET /health: %v", err)
	}
	_ = resp.Body.Close()

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 SERVER span from ChiMiddleware, got %d", len(spans))
	}
	if got := spans[0].Name(); got != "GET /health" {
		t.Fatalf("span name = %q, want \"GET /health\" (route pattern)", got)
	}
}
