package api

// DB-integration tests for the W5 shared-ModelPicker backend changes:
//  1. `pricing` JSONB is included in the user-models list/read response (additive).
//  2. listUserModels orders favorites first (is_favorite DESC, created_at DESC).
//  3. `chat` is whitelisted as a user_default_models capability (incl. the
//     undeclared-'{}'-is-chat-capable rule mirrored from the list filter).
// Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer); skips otherwise.
// Reuses seedModelWithCapability + signedToken from the capability test and
// putDefault/getDefaults from the default-models test.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

type listedModel struct {
	UserModelID string         `json:"user_model_id"`
	IsFavorite  bool           `json:"is_favorite"`
	Pricing     map[string]any `json:"pricing"`
}

func listModels(t *testing.T, srv *Server, owner uuid.UUID, query string) []listedModel {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-registry/user-models"+query, nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.listUserModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("listUserModels%s: expected 200, got %d (%s)", query, rr.Code, rr.Body.String())
	}
	var resp struct {
		Items []listedModel `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode list response: %v (%s)", err, rr.Body.String())
	}
	return resp.Items
}

func TestListUserModels_IncludesPricing(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	priced := seedModelWithCapability(t, pool, owner, "priced-model", `{"chat": true}`)
	unpriced := seedModelWithCapability(t, pool, owner, "unpriced-model", `{"chat": true}`)

	if _, err := pool.Exec(context.Background(),
		`UPDATE user_models SET pricing='{"input_per_mtok": 2.5, "output_per_mtok": 10}'::jsonb WHERE user_model_id=$1`,
		priced); err != nil {
		t.Fatalf("set pricing: %v", err)
	}

	byID := map[string]listedModel{}
	for _, it := range listModels(t, srv, owner, "") {
		byID[it.UserModelID] = it
	}
	p, ok := byID[priced.String()]
	if !ok {
		t.Fatalf("priced model missing from list")
	}
	if got := p.Pricing["input_per_mtok"]; got != 2.5 {
		t.Errorf("pricing.input_per_mtok: expected 2.5, got %v (pricing=%v)", got, p.Pricing)
	}
	if got := p.Pricing["output_per_mtok"]; got != float64(10) {
		t.Errorf("pricing.output_per_mtok: expected 10, got %v", got)
	}
	u, ok := byID[unpriced.String()]
	if !ok {
		t.Fatalf("unpriced model missing from list")
	}
	// The fail-closed default '{}' round-trips as an empty (non-nil) object.
	if u.Pricing == nil || len(u.Pricing) != 0 {
		t.Errorf("unpriced model: expected empty pricing object, got %v", u.Pricing)
	}
}

func TestListUserModels_FavoritesFirstOrdering(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()

	// Seeded in creation order: oldest first. The favorite is the OLDEST row, so
	// plain created_at DESC would put it last — favorites-first must hoist it.
	favorite := seedModelWithCapability(t, pool, owner, "fav-oldest", `{"chat": true}`)
	middle := seedModelWithCapability(t, pool, owner, "plain-middle", `{"chat": true}`)
	newest := seedModelWithCapability(t, pool, owner, "plain-newest", `{"chat": true}`)
	// Force a strict created_at order (same-transaction timestamps can tie).
	for i, id := range []uuid.UUID{favorite, middle, newest} {
		if _, err := pool.Exec(context.Background(),
			`UPDATE user_models SET created_at = now() - ($2::int * interval '1 hour') WHERE user_model_id=$1`,
			id, 3-i); err != nil {
			t.Fatalf("stagger created_at: %v", err)
		}
	}
	if _, err := pool.Exec(context.Background(),
		`UPDATE user_models SET is_favorite=true WHERE user_model_id=$1`, favorite); err != nil {
		t.Fatalf("set favorite: %v", err)
	}

	items := listModels(t, srv, owner, "")
	if len(items) != 3 {
		t.Fatalf("expected 3 models, got %d", len(items))
	}
	if items[0].UserModelID != favorite.String() || !items[0].IsFavorite {
		t.Errorf("favorites-first: expected favorite %s first, got %s (favorite=%v)",
			favorite, items[0].UserModelID, items[0].IsFavorite)
	}
	// Non-favorites keep newest-first among themselves.
	if items[1].UserModelID != newest.String() || items[2].UserModelID != middle.String() {
		t.Errorf("within non-favorites expected created_at DESC (%s, %s), got (%s, %s)",
			newest, middle, items[1].UserModelID, items[2].UserModelID)
	}
}

func TestDefaultModels_ChatCapabilityWhitelisted(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	chat := seedModelWithCapability(t, pool, owner, "chat-default", `{"chat": true}`)
	undeclared := seedModelWithCapability(t, pool, owner, "undeclared-default", `{}`)
	embed := seedModelWithCapability(t, pool, owner, "embed-not-chat", `{"embedding": true}`)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM user_default_models WHERE owner_user_id=$1`, owner)
	})

	// A chat-flagged model is a valid chat default.
	if rr := putDefault(t, srv, owner, "chat", `{"user_model_id":"`+chat.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("chat model as chat default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["chat"] != chat.String() {
		t.Fatalf("GET defaults: expected chat=%s, got %v", chat, got)
	}
	// An undeclared '{}' model is chat-capable by default (mirrors the list filter)
	// — the picker offers it, so the default validation must accept it too.
	if rr := putDefault(t, srv, owner, "chat", `{"user_model_id":"`+undeclared.String()+`"}`); rr.Code != http.StatusOK {
		t.Fatalf("undeclared model as chat default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	// A non-chat (embedding-only) model is NOT a valid chat default.
	if rr := putDefault(t, srv, owner, "chat", `{"user_model_id":"`+embed.String()+`"}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("embedding model as chat default: expected 400, got %d (%s)", rr.Code, rr.Body.String())
	}
	// Clearing works.
	if rr := putDefault(t, srv, owner, "chat", `{"user_model_id":null}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT clear chat default: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if got := getDefaults(t, srv, owner); got["chat"] != "" {
		t.Fatalf("after clear: expected no chat default, got %v", got)
	}
}
