package api

// 2026-11-21 model-surface audit — pins the MCP twin's inverted default: the
// settings_list_models tool now lists ACTIVE models only unless the caller
// passes include_inactive=true (parity with the HTTP GET /user-models
// inversion, user_models_include_inactive_default_test.go). The tool's former
// include-all default fed deactivated rows to the agent the same way the HTTP
// omission did.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedQAModel inserts a credential + one user_model with a DISTINCT provider
// model name (so list assertions can tell the rows apart) and the given
// is_active. Cleaned up after the test.
func seedQAModel(t *testing.T, srv *Server, pool *pgxpool.Pool, userID uuid.UUID, name string, active bool) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	cipher, _, err := srv.encryptSecret("qa-not-a-secret")
	if err != nil {
		t.Fatalf("encryptSecret: %v", err)
	}
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'openai','qa-cred','http://up',$2,'active') RETURNING provider_credential_id`,
		userID, cipher).Scan(&credID); err != nil {
		t.Fatalf("seed cred: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active)
VALUES ($1,$2,'openai',$3,$4) RETURNING user_model_id`,
		userID, credID, name, active).Scan(&modelID); err != nil {
		t.Fatalf("seed model: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
	return modelID
}

// listMCPModelNames marshals the whole tool reply and reports which of the two
// seeded provider model names it mentions — robust to the envelope shape.
func listMCPModelNames(t *testing.T, ts *httptest.Server, userID uuid.UUID, args map[string]any) map[string]bool {
	t.Helper()
	out, code := callTool(t, ts, userID.String(), "settings_list_models", args)
	if code != http.StatusOK {
		t.Fatalf("settings_list_models status %d: %v", code, out)
	}
	blob, _ := json.Marshal(out)
	return map[string]bool{
		"qa-active-model":   strings.Contains(string(blob), "qa-active-model"),
		"qa-inactive-model": strings.Contains(string(blob), "qa-inactive-model"),
	}
}

func TestSettingsMCP_ListModelsDefaultIsActiveOnly(t *testing.T) {
	srv, pool, ts := mcpDBServer(t)
	user := uuid.New()
	seedQAModel(t, srv, pool, user, "qa-active-model", true)
	seedQAModel(t, srv, pool, user, "qa-inactive-model", false)

	// The bare call is the contract: no flag means the agent sees live models.
	bare := listMCPModelNames(t, ts, user, nil)
	if !bare["qa-active-model"] {
		t.Fatalf("bare settings_list_models must return the active model")
	}
	if bare["qa-inactive-model"] {
		t.Fatalf("bare settings_list_models must NOT return the deactivated model — the default is active-only since 2026-11-21")
	}

	// Re-activation flows need the deactivated row: explicit opt-in sees both.
	optIn := listMCPModelNames(t, ts, user, map[string]any{"include_inactive": true})
	if !optIn["qa-active-model"] || !optIn["qa-inactive-model"] {
		t.Fatalf("include_inactive=true must return both models (got %v)", optIn)
	}

	// Explicit false keeps the active-only semantics (facade parity).
	off := listMCPModelNames(t, ts, user, map[string]any{"include_inactive": false})
	if !off["qa-active-model"] {
		t.Fatalf("include_inactive=false must return the active model")
	}
	if off["qa-inactive-model"] {
		t.Fatalf("include_inactive=false must not return the deactivated model")
	}
}
