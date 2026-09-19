package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// #286 / plan 2026-09-19 T10 — "serve one model at a time" is an OPT-IN per-credential setting.
// It is the user's statement about their own hardware (a local server that holds one model), so
// the platform never assumes it: absent means false, and a patch that does not mention it keeps
// what the user chose. Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer).

func providerCall(t *testing.T, srv *Server, owner uuid.UUID, method, path, body string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.Router().ServeHTTP(rr, req)
	var out map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	return rr.Code, out
}

func TestServeOneModelAtATime_IsOptIn_AndPatchKeepsWhatTheUserChose(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM provider_credentials WHERE owner_user_id=$1`, owner)
	})

	// Created without mentioning it → false. The platform does not decide this for the user.
	code, created := providerCall(t, srv, owner, http.MethodPost, "/v1/model-registry/providers",
		`{"provider_kind":"lm_studio","display_name":"local","endpoint_base_url":"http://host.docker.internal:1234"}`)
	if code != http.StatusCreated {
		t.Fatalf("create = %d %v", code, created)
	}
	if created["serve_one_model_at_a_time"] != false {
		t.Fatalf("a new credential must default to false, got %v", created["serve_one_model_at_a_time"])
	}
	id := created["provider_credential_id"].(string)

	// The user opts in.
	code, patched := providerCall(t, srv, owner, http.MethodPatch, "/v1/model-registry/providers/"+id,
		`{"serve_one_model_at_a_time":true}`)
	if code != http.StatusOK || patched["serve_one_model_at_a_time"] != true {
		t.Fatalf("patch true = %d %v", code, patched)
	}

	// A patch about something else must not reset the choice.
	code, other := providerCall(t, srv, owner, http.MethodPatch, "/v1/model-registry/providers/"+id,
		`{"display_name":"renamed"}`)
	if code != http.StatusOK || other["serve_one_model_at_a_time"] != true {
		t.Fatalf("an unrelated patch reset the setting: %d %v", code, other)
	}

	// The list shows it too (that is what the Settings UI reads).
	code, list := providerCall(t, srv, owner, http.MethodGet, "/v1/model-registry/providers", "")
	items, _ := list["items"].([]any)
	if code != http.StatusOK || len(items) != 1 || items[0].(map[string]any)["serve_one_model_at_a_time"] != true {
		t.Fatalf("list = %d %v", code, list)
	}

	// And the user can opt back out.
	code, off := providerCall(t, srv, owner, http.MethodPatch, "/v1/model-registry/providers/"+id,
		`{"serve_one_model_at_a_time":false}`)
	if code != http.StatusOK || off["serve_one_model_at_a_time"] != false {
		t.Fatalf("patch false = %d %v", code, off)
	}
}
