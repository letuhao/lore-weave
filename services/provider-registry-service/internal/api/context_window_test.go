package api

// getModelContextWindow must never fabricate a context-window number on failure — a
// guessed value (the historical flat 8192) is indistinguishable from a real one to the
// caller and silently drives real chunk-sizing math with the wrong window. These unit
// tests cover the pre-DB path only (bad UUID). /review-impl LOW: unlike LW-69's
// patchUserModel tests, there is currently no docker-compose integration suite covering
// the DB-dependent branches here (platform_model/user_model resolution, adapter
// failure, ListModels failure, model-not-in-live-list, genuine context_length IS NULL) —
// this repo has no integration/ dir for provider-registry-service at all yet. Tracked
// as a coverage gap, not claimed as already covered.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetModelContextWindow_InvalidUUID_ReturnsUnresolvedNotFabricated(t *testing.T) {
	t.Parallel()

	srv := testServer("12345678901234567890123456789012")
	req := withRouteParam(
		httptest.NewRequest(http.MethodGet, "/", nil),
		"model_ref", "not-a-uuid",
	)
	rr := httptest.NewRecorder()
	srv.getModelContextWindow(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 (degrade-safe), got %d", rr.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body["context_window"] != nil {
		t.Fatalf("expected context_window: null (never a fabricated guess), got %v", body["context_window"])
	}
	if resolved, _ := body["resolved"].(bool); resolved {
		t.Fatalf("expected resolved: false, got %v", body["resolved"])
	}
}
