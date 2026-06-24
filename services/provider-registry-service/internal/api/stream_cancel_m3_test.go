package api

// M3 (chat disconnect-cancel) — the internal stream-cancel route + the optional
// stream_job_id request field. The full Insert→register→finalize lifecycle is the
// 2-service live-smoke (a real stream cancelled mid-flight); these lock the wiring.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// The new DELETE /internal/llm/jobs/{id} must be REGISTERED behind the
// X-Internal-Token middleware and reach doCancelLlmJob — a router-only server
// (nil jobsRepo) then returns 503, proving the route exists (not 404/405).
func TestInternalCancelLlmJob_RouteWired(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodDelete,
		"/internal/llm/jobs/"+uuid.NewString()+"?user_id="+uuid.NewString(),
		nil,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 (route wired, nil jobsRepo), got %d body=%s", w.Code, w.Body.String())
	}
}

// internal cancel requires the user_id query param (s2s owner scope).
func TestInternalCancelLlmJob_RequiresUserID(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodDelete,
		"/internal/llm/jobs/"+uuid.NewString(), // no ?user_id
		nil,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 (user_id required), got %d body=%s", w.Code, w.Body.String())
	}
}

// The optional stream_job_id field decodes (empty for every legacy caller).
func TestStreamRequest_DecodesStreamJobID(t *testing.T) {
	id := uuid.NewString()
	var in streamRequest
	body := `{"model_source":"user_model","model_ref":"` + id + `","stream_job_id":"` + id + `"}`
	if err := json.NewDecoder(strings.NewReader(body)).Decode(&in); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if in.StreamJobID != id {
		t.Fatalf("stream_job_id=%q want %q", in.StreamJobID, id)
	}

	// Absent → empty (today's behavior, no row created).
	var in2 streamRequest
	_ = json.NewDecoder(strings.NewReader(`{"model_source":"user_model","model_ref":"`+id+`"}`)).Decode(&in2)
	if in2.StreamJobID != "" {
		t.Fatalf("stream_job_id should default empty, got %q", in2.StreamJobID)
	}
}
