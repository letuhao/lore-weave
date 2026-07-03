package api

// DB-integration tests for the (8)-residual user-defined SORT ORDER feature:
//  1. the sort_order migration column is idempotent (integrationServer re-runs migrate.Up).
//  2. PUT /user-models/reorder assigns sort_order = index for the provided ids and
//     NULLs every other model the caller owns (partial reorder is well-defined).
//  3. listUserModels honors sort_order ASC NULLS LAST, then favorites-first.
//  4. reorder is owner-scoped: a foreign id in ordered_ids is silently ignored.
// Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer); skips otherwise.
// Reuses seedModelWithCapability + signedToken + listModels from the sibling tests.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func reorderModels(t *testing.T, srv *Server, owner uuid.UUID, orderedIDs []uuid.UUID) []listedModelOrdered {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"ordered_ids": orderedIDs})
	req := httptest.NewRequest(http.MethodPut, "/v1/model-registry/user-models/reorder", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.reorderUserModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("reorderUserModels: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var resp struct {
		Items []listedModelOrdered `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode reorder response: %v (%s)", err, rr.Body.String())
	}
	return resp.Items
}

type listedModelOrdered struct {
	UserModelID string `json:"user_model_id"`
	IsFavorite  bool   `json:"is_favorite"`
	SortOrder   *int   `json:"sort_order"`
}

func listOrdered(t *testing.T, srv *Server, owner uuid.UUID) []listedModelOrdered {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/model-registry/user-models", nil)
	req.Header.Set("Authorization", "Bearer "+signedToken(t, integrationJWTSecret, owner, ""))
	rr := httptest.NewRecorder()
	srv.listUserModels(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("listUserModels: expected 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var resp struct {
		Items []listedModelOrdered `json:"items"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode list response: %v (%s)", err, rr.Body.String())
	}
	return resp.Items
}

// Migration idempotency: integrationServer runs migrate.Up on every call, and the
// suite runs it many times against the same DB — so a plain green here IS the
// idempotency proof for the additive sort_order column. Assert the column exists.
func TestReorder_MigrationAddsSortOrderColumn(t *testing.T) {
	_, pool := integrationServer(t)
	var exists bool
	if err := pool.QueryRow(context.Background(), `
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_name='user_models' AND column_name='sort_order'
)`).Scan(&exists); err != nil {
		t.Fatalf("check sort_order column: %v", err)
	}
	if !exists {
		t.Fatalf("expected user_models.sort_order column to exist after migrate.Up")
	}
}

func TestReorder_AssignsIndexesAndNullsTheRest(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()

	a := seedModelWithCapability(t, pool, owner, "reorder-a", `{"chat": true}`)
	b := seedModelWithCapability(t, pool, owner, "reorder-b", `{"chat": true}`)
	c := seedModelWithCapability(t, pool, owner, "reorder-c", `{"chat": true}`)

	// Reorder as [c, a] — b is intentionally omitted so it must end up NULL.
	items := reorderModels(t, srv, owner, []uuid.UUID{c, a})

	// The response is the freshly-ordered list: c (0), a (1) first, then b (NULL).
	if len(items) != 3 {
		t.Fatalf("expected 3 models, got %d", len(items))
	}
	if items[0].UserModelID != c.String() || items[0].SortOrder == nil || *items[0].SortOrder != 0 {
		t.Errorf("expected c first with sort_order=0, got %+v", items[0])
	}
	if items[1].UserModelID != a.String() || items[1].SortOrder == nil || *items[1].SortOrder != 1 {
		t.Errorf("expected a second with sort_order=1, got %+v", items[1])
	}
	if items[2].UserModelID != b.String() || items[2].SortOrder != nil {
		t.Errorf("expected b last with NULL sort_order, got %+v", items[2])
	}

	// A second reorder that OMITS a previously-ordered id must NULL it (partial reorder
	// is well-defined). Reorder to just [b]; a and c must go back to NULL.
	items = reorderModels(t, srv, owner, []uuid.UUID{b})
	byID := map[string]listedModelOrdered{}
	for _, it := range items {
		byID[it.UserModelID] = it
	}
	if bo := byID[b.String()]; bo.SortOrder == nil || *bo.SortOrder != 0 {
		t.Errorf("expected b sort_order=0 after re-reorder, got %+v", bo)
	}
	if ao := byID[a.String()]; ao.SortOrder != nil {
		t.Errorf("expected a reset to NULL after re-reorder, got %+v", ao)
	}
	if co := byID[c.String()]; co.SortOrder != nil {
		t.Errorf("expected c reset to NULL after re-reorder, got %+v", co)
	}
}

func TestReorder_ListRespectsSortOrderThenFavorites(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()

	// fav is a favorite (would pin first with no explicit order), ordered1/ordered2
	// carry an explicit order, plain has neither.
	fav := seedModelWithCapability(t, pool, owner, "order-fav", `{"chat": true}`)
	ordered1 := seedModelWithCapability(t, pool, owner, "order-1", `{"chat": true}`)
	ordered2 := seedModelWithCapability(t, pool, owner, "order-2", `{"chat": true}`)
	plain := seedModelWithCapability(t, pool, owner, "order-plain", `{"chat": true}`)

	if _, err := pool.Exec(context.Background(),
		`UPDATE user_models SET is_favorite=true WHERE user_model_id=$1`, fav); err != nil {
		t.Fatalf("set favorite: %v", err)
	}
	// Explicit order [ordered1, ordered2]; fav + plain stay NULL.
	reorderModels(t, srv, owner, []uuid.UUID{ordered1, ordered2})

	items := listOrdered(t, srv, owner)
	if len(items) != 4 {
		t.Fatalf("expected 4 models, got %d", len(items))
	}
	// Explicitly-ordered models win regardless of favorite status.
	if items[0].UserModelID != ordered1.String() {
		t.Errorf("expected ordered1 first, got %s", items[0].UserModelID)
	}
	if items[1].UserModelID != ordered2.String() {
		t.Errorf("expected ordered2 second, got %s", items[1].UserModelID)
	}
	// Among the NULL-order models, favorites-first: fav before plain.
	if items[2].UserModelID != fav.String() || !items[2].IsFavorite {
		t.Errorf("expected favorite third (favorites-first among unordered), got %+v", items[2])
	}
	if items[3].UserModelID != plain.String() {
		t.Errorf("expected plain last, got %s", items[3].UserModelID)
	}
}

func TestReorder_OwnerScopedIgnoresForeignIDs(t *testing.T) {
	srv, pool := integrationServer(t)
	owner := uuid.New()
	other := uuid.New()

	mine := seedModelWithCapability(t, pool, owner, "reorder-mine", `{"chat": true}`)
	theirs := seedModelWithCapability(t, pool, other, "reorder-theirs", `{"chat": true}`)

	// Include the other tenant's id: it must be silently ignored, and it must NOT
	// receive a sort_order (owner-scoped UPDATE matches nothing).
	reorderModels(t, srv, owner, []uuid.UUID{theirs, mine})

	var theirOrder *int
	if err := pool.QueryRow(context.Background(),
		`SELECT sort_order FROM user_models WHERE user_model_id=$1`, theirs).Scan(&theirOrder); err != nil {
		t.Fatalf("read foreign model sort_order: %v", err)
	}
	if theirOrder != nil {
		t.Errorf("foreign model must not be reordered, got sort_order=%v", *theirOrder)
	}
	// mine is second in ordered_ids (index 1), because theirs at index 0 no-ops but the
	// loop counter still advances — so mine keeps index 1. Assert it got an order.
	var myOrder *int
	if err := pool.QueryRow(context.Background(),
		`SELECT sort_order FROM user_models WHERE user_model_id=$1`, mine).Scan(&myOrder); err != nil {
		t.Fatalf("read my model sort_order: %v", err)
	}
	if myOrder == nil {
		t.Fatalf("my model should have a sort_order after reorder")
	}
}
