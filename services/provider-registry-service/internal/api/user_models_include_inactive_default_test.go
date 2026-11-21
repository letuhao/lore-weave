package api

// 2026-11-21 model-surface audit — pins the INVERTED default of the list
// endpoint: OMITTING include_inactive returns ACTIVE models only; `true` opts
// in; `false` stays explicit. The old default (`!= "false"` — include
// everything when the param was omitted) silently fed deactivated rows to any
// caller that did not post-filter, which is exactly the deactivated-model leak
// class the 2026-11-08 user report came from.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedInactiveModel mirrors seedModelWithCapability but flips is_active=false.
func seedInactiveModel(t *testing.T, pool *pgxpool.Pool, owner uuid.UUID, name string) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'lm_studio','inactive-test','http://127.0.0.1:1','x','active')
RETURNING provider_credential_id`, owner).Scan(&credID); err != nil {
		t.Fatalf("seed provider_credentials: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active, capability_flags)
VALUES ($1,$2,'lm_studio',$3,false,$4::jsonb)
RETURNING user_model_id`, owner, credID, name, `{"chat": true}`).Scan(&modelID); err != nil {
		t.Fatalf("seed user_models: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return modelID
}

func listRawModels(t *testing.T, srv *Server, owner uuid.UUID, query string) map[string]bool {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-registry/user-models"+query, nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.listUserModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("listUserModels %q: expected 200, got %d (%s)", query, rr.Code, rr.Body.String())
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

func TestListUserModels_DefaultIsActiveOnly(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	active := seedModelWithCapability(t, pool, owner, "active-model", `{"chat": true}`)
	inactive := seedInactiveModel(t, pool, owner, "inactive-model")

	// The bare GET is the contract: no param means the caller wants live models.
	bare := listRawModels(t, srv, owner, "")
	if !bare[active.String()] {
		t.Fatalf("bare GET must return the active model %s", active)
	}
	if bare[inactive.String()] {
		t.Fatalf("bare GET must NOT return the deactivated model — the default is active-only since 2026-11-21")
	}

	// Management surfaces (Providers tab) opt in explicitly and see both.
	optIn := listRawModels(t, srv, owner, "?include_inactive=true")
	if !optIn[active.String()] || !optIn[inactive.String()] {
		t.Fatalf("include_inactive=true must return both models (got %v)", optIn)
	}

	// Explicit false keeps the active-only semantics (facade parity).
	off := listRawModels(t, srv, owner, "?include_inactive=false")
	if !off[active.String()] {
		t.Fatalf("include_inactive=false must return the active model")
	}
	if off[inactive.String()] {
		t.Fatalf("include_inactive=false must not return the deactivated model")
	}
}
