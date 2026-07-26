package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/notification-service/internal/category"
	"github.com/loreweave/notification-service/internal/config"
)

// postNotification POSTs a category to the internal ingress path and returns
// the response. The Server is built with a nil pool and empty internal token,
// so the category-validation gate (which runs BEFORE any DB access) is what
// the response distinguishes: a REJECTED category returns a 400
// NOTIF_VALIDATION_ERROR before touching the DB; an ACCEPTED category passes
// the gate and only then hits the nil pool, which panics → Recoverer → 500.
// So "status != 400" proves the category was accepted on HTTP ingest.
func postNotification(t *testing.T, ts *httptest.Server, cat string) (int, string) {
	t.Helper()
	payload, _ := json.Marshal(map[string]any{
		"user_id":  uuid.New().String(),
		"category": cat,
		"title":    "hello",
	})
	resp, err := http.Post(ts.URL+"/internal/notifications/", "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, string(b)
}

// TestHTTPIngest_AcceptsRealProducerCategories proves the P0-4 fix: the
// categories that were silently dropped (mcp_approval) and the consumer's
// own category (llm_job) now pass the HTTP ingress validation gate.
func TestHTTPIngest_AcceptsRealProducerCategories(t *testing.T) {
	srv := NewServer(nil, &config.Config{}) // nil pool, no internal token
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	for _, cat := range []string{"mcp_approval", "llm_job", "campaign", "billing"} {
		status, body := postNotification(t, ts, cat)
		if status == http.StatusBadRequest {
			t.Errorf("category %q was rejected on HTTP ingest (got 400: %s) — it must be accepted", cat, body)
		}
	}
}

// TestHTTPIngest_RejectsUnknownWithError proves an unknown category is
// rejected with a descriptive error body (never silently swallowed).
func TestHTTPIngest_RejectsUnknownWithError(t *testing.T) {
	srv := NewServer(nil, &config.Config{})
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	status, body := postNotification(t, ts, "totally_unknown_category")
	if status != http.StatusBadRequest {
		t.Fatalf("unknown category: status = %d, want 400 (%s)", status, body)
	}
	var eb errorBody
	if err := json.Unmarshal([]byte(body), &eb); err != nil {
		t.Fatalf("reject body is not JSON error: %v (%s)", err, body)
	}
	if eb.Code == "" || eb.Message == "" {
		t.Errorf("reject must carry a descriptive error, got code=%q message=%q", eb.Code, eb.Message)
	}
}

// TestValidCategory_SharesSourceOfTruth proves BOTH ingress paths validate
// against the same set: the api-layer gate (validCategory) is exactly the
// shared category.Valid the consumer also calls.
func TestValidCategory_SharesSourceOfTruth(t *testing.T) {
	for _, c := range []string{"translation", "social", "wiki", "system", "llm_job", "mcp_approval", "campaign", "billing", "bogus", ""} {
		if validCategory(c) != category.Valid(c) {
			t.Errorf("validCategory(%q)=%v drifted from category.Valid=%v — ingress paths must share one enum", c, validCategory(c), category.Valid(c))
		}
	}
}
