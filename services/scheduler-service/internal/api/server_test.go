package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The upsert endpoint is X-Internal-Token-gated and validates its inputs before touching the DB.
func TestUpsertSchedule_AuthAndValidation(t *testing.T) {
	s := &Server{internalToken: "tok"} // no pool: these paths return before any DB access
	r := s.Router()

	// no token → 401
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, httptest.NewRequest(http.MethodPut, "/internal/schedules", strings.NewReader(`{}`)))
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("no token = %d, want 401", rr.Code)
	}

	// token but missing user_id → 400
	rr = httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPut, "/internal/schedules", strings.NewReader(`{"job_kind":"eod_distill"}`))
	req.Header.Set("X-Internal-Token", "tok")
	r.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("missing user_id = %d, want 400. body=%s", rr.Code, rr.Body.String())
	}

	// token + bad cadence → 400
	rr = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodPut, "/internal/schedules",
		strings.NewReader(`{"user_id":"00000000-0000-0000-0000-000000000001","job_kind":"eod_distill","cadence":"hourly"}`))
	req.Header.Set("X-Internal-Token", "tok")
	r.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("bad cadence = %d, want 400", rr.Code)
	}
}

// A3 — the GET list is token-gated and requires a user_id before any DB access (both paths return early,
// so no pool is needed here).
func TestListSchedules_AuthAndValidation(t *testing.T) {
	s := &Server{internalToken: "tok"}
	r := s.Router()

	// no token → 401
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/internal/schedules?user_id=00000000-0000-0000-0000-000000000001", nil))
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("no token = %d, want 401", rr.Code)
	}

	// token but missing/invalid user_id → 400 (before any DB touch)
	rr = httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/internal/schedules", nil)
	req.Header.Set("X-Internal-Token", "tok")
	r.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("missing user_id = %d, want 400. body=%s", rr.Code, rr.Body.String())
	}
}
