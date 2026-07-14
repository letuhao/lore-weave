package api

// DB-integration tests for the per-user default-model endpoints (D-RERANK-NOT-BYOK
// follow-up). Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer); skips
// otherwise. Reuses seedModelWithCapability + signedToken from the capability test.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

func withCapParam(req *http.Request, capability string) *http.Request {
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("capability", capability)
	return req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
}

func putDefault(t *testing.T, srv *Server, owner uuid.UUID, capability, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPut, "/v1/model-registry/default-models/"+capability, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	req = withCapParam(req, capability)
	rr := httptest.NewRecorder()
	srv.putDefaultModel(rr, req)
	return rr
}

func getDefaults(t *testing.T, srv *Server, owner uuid.UUID) map[string]string {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-registry/default-models", nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.getDefaultModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("getDefaultModels: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var resp struct {
		Defaults map[string]string `json:"defaults"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode defaults: %v (%s)", err, rr.Body.String())
	}
	return resp.Defaults
}

func internalDefault(t *testing.T, srv *Server, owner uuid.UUID, capability string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/internal/default-models/"+capability+"?user_id="+owner.String(), nil)
	req = withCapParam(req, capability)
	rr := httptest.NewRecorder()
	srv.internalGetDefaultModel(rr, req)
	return rr
}

func TestDefaultModels_SetGetClearAndResolve(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	model := seedModelWithCapability(t, pool, owner, "rerank-1", `{"rerank": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=$1`, owner)
	})

	// Set the default rerank model.
	if rr := putDefault(t, srv, owner, "rerank", `{"user_model_id":"`+model.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT set: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["rerank"] != model.String() {
		t.Fatalf("GET defaults: expected rerank=%s, got %v", model, got)
	}
	// Internal resolve returns it.
	rr := internalDefault(t, srv, owner, "rerank")
	if rr.Code != http.StatusOK {
		t.Fatalf("internal resolve: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var resolved struct {
		UserModelID string `json:"user_model_id"`
		ModelSource string `json:"model_source"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &resolved)
	if resolved.UserModelID != model.String() || resolved.ModelSource != "user_model" {
		t.Fatalf("internal resolve mismatch: %+v", resolved)
	}

	// Clear it (null).
	if rr := putDefault(t, srv, owner, "rerank", `{"user_model_id":null}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT clear: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["rerank"] != "" {
		t.Fatalf("after clear: expected no rerank default, got %v", got)
	}
	if rr := internalDefault(t, srv, owner, "rerank"); rr.Code != http.StatusNotFound {
		t.Fatalf("internal resolve after clear: expected 404, got %d", rr.Code)
	}
}

func TestDefaultModels_RejectsWrongCapabilityAndUnknownCapability(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	// An embedding-only model cannot be set as the rerank default.
	embed := seedModelWithCapability(t, pool, owner, "embed-only-2", `{"embedding": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=$1`, owner)
	})

	if rr := putDefault(t, srv, owner, "rerank", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("embedding model as rerank default: expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
	// But it IS valid as the embedding default.
	if rr := putDefault(t, srv, owner, "embedding", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("embedding model as embedding default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	// Unknown capability → 400.
	if rr := putDefault(t, srv, owner, "telepathy", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("unknown capability: expected 400, got %d", rr.Code)
	}
}

func TestDefaultModels_CriticAcceptsChatModelRejectsEmbedding(t *testing.T) {
	// WS-5.10 (P5 Gate-2) — `critic` is a ROLE validated against the chat flag (like
	// planner/distill), so a chat model is assignable but an embedding-only model is not.
	srv, pool := integrationServer(t)
	owner := uuid.New()
	chat := seedModelWithCapability(t, pool, owner, "chat-critic", `{"chat": true}`)
	embed := seedModelWithCapability(t, pool, owner, "embed-not-critic", `{"embedding": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=$1`, owner)
	})
	if rr := putDefault(t, srv, owner, "critic", `{"user_model_id":"`+chat.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("chat model as critic default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["critic"] != chat.String() {
		t.Fatalf("critic default not stored: %v", got)
	}
	if rr := putDefault(t, srv, owner, "critic", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("embedding model as critic default: expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
}

func TestDefaultModels_PlannerAcceptsChatModel(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	// `planner` is a role, not a model flag — a CHAT (tool-calling) model qualifies.
	chat := seedModelWithCapability(t, pool, owner, "chat-planner", `{"chat": true, "tool_calling": true}`)
	embed := seedModelWithCapability(t, pool, owner, "embed-not-planner", `{"embedding": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=$1`, owner)
	})

	// A chat model IS valid as the planner default (validated against the chat flag).
	if rr := putDefault(t, srv, owner, "planner", `{"user_model_id":"`+chat.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("chat model as planner default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["planner"] != chat.String() {
		t.Fatalf("planner default not stored: %v", got)
	}
	// An embedding-only model is NOT a valid planner (no chat flag) → 400.
	if rr := putDefault(t, srv, owner, "planner", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("embedding model as planner default: expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
	// The planner resolver returns the pinned default (source=planner_default), not the
	// arbitrary chat fallback.
	req := httptest.NewRequest(http.MethodGet, "/internal/planner-model?user_id="+owner.String(), nil)
	rr := httptest.NewRecorder()
	srv.internalResolvePlannerModel(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("planner-model resolve: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var resolved struct {
		UserModelID string `json:"user_model_id"`
		Source      string `json:"source"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &resolved)
	if resolved.UserModelID != chat.String() || resolved.Source != "planner_default" {
		t.Fatalf("planner resolve mismatch: %+v (want %s / planner_default)", resolved, chat)
	}
}

func TestDefaultModels_RejectsForeignModel(t *testing.T) {
	srv, pool := integrationServer(t)
	ownerA := uuid.New()
	ownerB := uuid.New()
	model := seedModelWithCapability(t, pool, ownerA, "rerank-foreign", `{"rerank": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=ANY($1)`, []uuid.UUID{ownerA, ownerB})
	})
	// Owner B cannot set owner A's model as their default.
	if rr := putDefault(t, srv, ownerB, "rerank", `{"user_model_id":"`+model.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("foreign model: expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
}
