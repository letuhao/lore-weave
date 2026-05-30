package api

// DB-integration test for the user-models capability filter (LW-PLAN-MVP-RELEASE F-4).
// Undeclared models (capability_flags '{}') must be treated as chat-capable by default
// — otherwise local/BYOK models that never self-declare capabilities are hidden from
// every chat/LLM picker (knowledge graph build, regenerate-bio, change-model), even
// though the same model works in chat/translation/extraction. Embedding stays strict.
// Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer); skips otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedModelWithCapability inserts a credential + one user_model with the given
// capability_flags JSONB, returning the model id. Cleans up after the test.
func seedModelWithCapability(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID, name, capabilityFlags string) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'lm_studio','cap-test','http://127.0.0.1:1','x','active')
RETURNING provider_credential_id`, owner).Scan(&credID); err != nil {
		t.Fatalf("seed provider_credentials: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active, capability_flags)
VALUES ($1,$2,'lm_studio',$3,true,$4::jsonb)
RETURNING user_model_id`, owner, credID, name, capabilityFlags).Scan(&modelID); err != nil {
		t.Fatalf("seed user_models: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return modelID
}

func listModelIDs(t *testing.T, srv *Server, owner uuid.UUID, capability string) map[string]bool {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-registry/user-models?include_inactive=false&capability="+capability, nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.listUserModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("listUserModels capability=%s: expected 200, got %d (%s)", capability, rr.Code, rr.Body.String())
	}
	var resp struct {
		Items []struct {
			UserModelID string `json:"user_model_id"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode list response: %v (%s)", err, rr.Body.String())
	}
	ids := make(map[string]bool, len(resp.Items))
	for _, it := range resp.Items {
		ids[it.UserModelID] = true
	}
	return ids
}

func TestListUserModels_CapabilityFilter_UndeclaredIsChatCapable(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()

	undeclared := seedModelWithCapability(t, pool, owner, "undeclared-llm", `{}`)
	embeddingOnly := seedModelWithCapability(t, pool, owner, "embed-only", `{"embedding": true}`)
	canonicalChat := seedModelWithCapability(t, pool, owner, "canonical-chat", `{"chat": true}`)
	legacyChat := seedModelWithCapability(t, pool, owner, "legacy-chat", `{"_capability": "chat"}`)

	// capability=chat must include all three chat-eligible schemas — canonical
	// {"chat":true}, legacy {"_capability":"chat"}, and undeclared '{}' (default) —
	// but NOT the embedding-only model.
	chat := listModelIDs(t, srv, owner, "chat")
	if !chat[undeclared.String()] {
		t.Errorf("capability=chat should include the undeclared '{}' model %s", undeclared)
	}
	if !chat[canonicalChat.String()] {
		t.Errorf("capability=chat should include the canonical {\"chat\":true} model %s", canonicalChat)
	}
	if !chat[legacyChat.String()] {
		t.Errorf("capability=chat should include the legacy {\"_capability\":\"chat\"} model %s", legacyChat)
	}
	if chat[embeddingOnly.String()] {
		t.Errorf("capability=chat should NOT include the embedding-only model %s", embeddingOnly)
	}

	// capability=embedding: only the explicitly-flagged model; undeclared must NOT
	// be silently offered as an embedding model.
	embedding := listModelIDs(t, srv, owner, "embedding")
	if !embedding[embeddingOnly.String()] {
		t.Errorf("capability=embedding should include the embedding-flagged model %s", embeddingOnly)
	}
	if embedding[undeclared.String()] {
		t.Errorf("capability=embedding must NOT include the undeclared '{}' model %s", undeclared)
	}
}
