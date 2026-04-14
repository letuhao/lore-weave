package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"regexp"
	"testing"
)

// Uses package `api` (not `api_test`) so we can reach the unexported
// traceIDMiddleware / TraceIDFromContext directly without building a
// full Server + router. The middleware is standalone — no DB, no config.

func TestTraceIDMiddleware_GeneratesWhenAbsent(t *testing.T) {
	var captured string
	handler := traceIDMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured = TraceIDFromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/ping", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if captured == "" {
		t.Fatal("expected middleware to populate trace id on context")
	}
	if got := rec.Header().Get("X-Trace-Id"); got != captured {
		t.Fatalf("response header %q did not match ctx id %q", got, captured)
	}
	if !regexp.MustCompile(`^[0-9a-f]{32}$`).MatchString(captured) {
		t.Fatalf("generated id %q is not 32-char hex", captured)
	}
}

func TestTraceIDMiddleware_AdoptsIncoming(t *testing.T) {
	var captured string
	handler := traceIDMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured = TraceIDFromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/ping", nil)
	req.Header.Set("X-Trace-Id", "caller-abc")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if captured != "caller-abc" {
		t.Fatalf("expected context id 'caller-abc', got %q", captured)
	}
	if got := rec.Header().Get("X-Trace-Id"); got != "caller-abc" {
		t.Fatalf("expected response header 'caller-abc', got %q", got)
	}
}

func TestTraceIDFromContext_EmptyWithoutMiddleware(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/ping", nil)
	if got := TraceIDFromContext(req.Context()); got != "" {
		t.Fatalf("expected empty trace id outside middleware, got %q", got)
	}
}

func TestJSONRecoverer_Returns500WithTraceId(t *testing.T) {
	// Stack middleware in the same order as server.go: trace_id then recoverer.
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("boom")
	})
	handler := traceIDMiddleware(jsonRecovererMiddleware(inner))

	req := httptest.NewRequest(http.MethodGet, "/ping", nil)
	req.Header.Set("X-Trace-Id", "panic-id")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", rec.Code)
	}
	if rec.Header().Get("X-Trace-Id") != "panic-id" {
		t.Fatalf("missing trace id in response header: %q", rec.Header().Get("X-Trace-Id"))
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("body is not json: %v\n%s", err, rec.Body.String())
	}
	if body["trace_id"] != "panic-id" {
		t.Fatalf("expected trace_id 'panic-id' in body, got %q", body["trace_id"])
	}
	if body["detail"] == "" {
		t.Fatal("expected non-empty detail in 500 body")
	}
}

func TestNewTraceID_Format(t *testing.T) {
	tid := newTraceID()
	if !regexp.MustCompile(`^[0-9a-f]{32}$`).MatchString(tid) {
		t.Fatalf("trace id %q is not 32-char lowercase hex", tid)
	}
	// Two calls should not collide (weak but catches constant bugs).
	if newTraceID() == tid {
		t.Fatal("newTraceID returned the same id twice")
	}
}
