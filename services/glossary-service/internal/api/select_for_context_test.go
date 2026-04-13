package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// seedContextEntities inserts N entities for a given book, each with a
// name attribute and optional short_description / pinned / aliases.
// Returns the generated entity_ids in insertion order.
type seedEntity struct {
	Name             string
	Aliases          string // raw JSON, e.g. `["alt1","alt2"]` or ""
	ShortDescription string
	Pinned           bool
}

func seedContextBook(t *testing.T, pool *pgxpool.Pool, bookID string, entities []seedEntity) []string {
	t.Helper()
	ctx := context.Background()
	var kindID, nameAttrID, aliasesAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID,
	).Scan(&nameAttrID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='aliases' LIMIT 1`, kindID,
	).Scan(&aliasesAttrID)

	ids := make([]string, 0, len(entities))
	for _, e := range entities {
		var eid string
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,short_description,is_pinned_for_context)
			 VALUES($1,$2,'active','{}',$3,$4) RETURNING entity_id`,
			bookID, kindID, nullIfEmpty(e.ShortDescription), e.Pinned,
		).Scan(&eid); err != nil {
			t.Fatalf("insert entity: %v", err)
		}
		if e.Name != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'zh',$3)`, eid, nameAttrID, e.Name)
		}
		if e.Aliases != "" && aliasesAttrID != "" {
			pool.Exec(ctx,
				`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
				 VALUES($1,$2,'zh',$3)`, eid, aliasesAttrID, e.Aliases)
		}
		ids = append(ids, eid)
	}

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	return ids
}

func nullIfEmpty(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}

// callSelectForContext issues a POST against the internal endpoint and
// decodes the JSON body. Internal-token header is set.
func callSelectForContext(t *testing.T, srv *Server, bookID string, body map[string]interface{}, token string) (*httptest.ResponseRecorder, *selectForContextResponse) {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/select-for-context", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("X-Internal-Token", token)
	}
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		return w, nil
	}
	var resp selectForContextResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v; body=%s", err, w.Body.String())
	}
	return w, &resp
}

// newContextTestServer builds a Server with a fixed internal token.
func newContextTestServer(t *testing.T, pool *pgxpool.Pool) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, pool)
	token := "ctx-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

// ── auth tests ──────────────────────────────────────────────────────────────

func TestSelectForContext_RequiresInternalToken(t *testing.T) {
	srv, _ := newContextTestServer(t, nil)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0000-000000000001/select-for-context",
		bytes.NewReader([]byte(`{}`)))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestSelectForContext_WrongTokenReturns401(t *testing.T) {
	srv, _ := newContextTestServer(t, nil)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0000-000000000001/select-for-context",
		bytes.NewReader([]byte(`{}`)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", "wrong")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: want 401, got %d", w.Code)
	}
}

func TestSelectForContext_BadUUIDReturns400(t *testing.T) {
	srv, token := newContextTestServer(t, nil)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/not-a-uuid/select-for-context",
		bytes.NewReader([]byte(`{}`)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad uuid: want 400, got %d", w.Code)
	}
}

// ── tier behaviour tests (real DB) ─────────────────────────────────────────

func TestSelectForContext_PinnedTierFirst(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4001"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "Unpinned Hero"},
		{Name: "Pinned Villain", Pinned: true},
		{Name: "Another Unpinned"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"user_id":      "11111111-1111-1111-1111-111111111111",
		"query":        "",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	if len(resp.Entities) < 1 {
		t.Fatalf("expected at least one entity, got 0")
	}
	if resp.Entities[0].Tier != tierPinned {
		t.Errorf("first result tier: want pinned, got %s", resp.Entities[0].Tier)
	}
	if !resp.Entities[0].IsPinned {
		t.Errorf("first result should have IsPinned=true")
	}
}

func TestSelectForContext_ExactNameMatch(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4002"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "李雲"},
		{Name: "王小明"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "李雲",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	// First result should be the exact-match entity
	if len(resp.Entities) == 0 {
		t.Fatal("expected ≥1 entity")
	}
	found := false
	for _, e := range resp.Entities {
		if e.CachedName != nil && *e.CachedName == "李雲" && e.Tier == tierExact {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected exact-tier match for 李雲; got %+v", resp.Entities)
	}
}

func TestSelectForContext_ExactAliasMatch(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4003"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "李雲", Aliases: `["小李","Li Yun"]`},
		{Name: "Unrelated"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "小李",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	var found bool
	for _, e := range resp.Entities {
		if e.Tier == tierExact {
			for _, a := range e.CachedAliases {
				if a == "小李" {
					found = true
				}
			}
		}
	}
	if !found {
		t.Errorf("expected exact-tier match via alias '小李'; got %+v", resp.Entities)
	}
}

func TestSelectForContext_FTSTierWhenNoExactMatch(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4004"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "Alice", ShortDescription: "a wandering swordsman of the Jianghu"},
		{Name: "Bob", ShortDescription: "a blacksmith"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "swordsman",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	var found bool
	for _, e := range resp.Entities {
		if e.Tier == tierFTS && e.CachedName != nil && *e.CachedName == "Alice" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected fts-tier match for 'swordsman' → Alice; got %+v", resp.Entities)
	}
}

func TestSelectForContext_RecentFallbackWhenNoQuery(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4005"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "One"},
		{Name: "Two"},
		{Name: "Three"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	// All three must come back, all labeled "recent" (none are pinned).
	if len(resp.Entities) != 3 {
		t.Errorf("want 3 entities, got %d", len(resp.Entities))
	}
	for _, e := range resp.Entities {
		if e.Tier != tierRecent {
			t.Errorf("entity %s: want tier=recent, got %s", e.EntityID, e.Tier)
		}
	}
}

func TestSelectForContext_ExcludeIDs(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4006"
	ids := seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "Keep"},
		{Name: "Skip"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "",
		"max_entities": 10,
		"exclude_ids":  []string{ids[1]},
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	for _, e := range resp.Entities {
		if e.EntityID == ids[1] {
			t.Errorf("excluded entity %s returned", ids[1])
		}
	}
}

func TestSelectForContext_MaxEntitiesBudget(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4007"
	entities := make([]seedEntity, 5)
	for i := range entities {
		entities[i] = seedEntity{Name: "E" + string(rune('A'+i))}
	}
	seedContextBook(t, pool, bookID, entities)

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "",
		"max_entities": 2,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	if len(resp.Entities) != 2 {
		t.Errorf("max_entities=2: got %d", len(resp.Entities))
	}
}

func TestSelectForContext_MaxTokensBudget(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4008"
	longDesc := ""
	for i := 0; i < 2000; i++ {
		longDesc += "x"
	}
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "BigA", ShortDescription: longDesc},
		{Name: "BigB", ShortDescription: longDesc},
		{Name: "BigC", ShortDescription: longDesc},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "",
		"max_entities": 10,
		"max_tokens":   300, // should fit ~1 of the big entities (~500 tokens each)
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	// At least one must be present (the budget check lets the first one in),
	// but we should NOT get all three.
	if len(resp.Entities) >= 3 {
		t.Errorf("max_tokens budget exceeded: got %d entities, tokens=%d",
			len(resp.Entities), resp.TotalTokensEstimate)
	}
}

// TestSelectForContext_PinnedOverlapsExact_AppearsOnceAsPinned is a
// regression for the dedupe path. An entity that is both pinned AND an
// exact match for the query must appear exactly once in the output and
// be labeled tier=pinned (earliest tier wins).
func TestSelectForContext_PinnedOverlapsExact_AppearsOnceAsPinned(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c400a"
	ids := seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "李雲", Pinned: true},
		{Name: "Other"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "李雲",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	// Count how many times the pinned+exact entity appears.
	var occurrences int
	var tier string
	for _, e := range resp.Entities {
		if e.EntityID == ids[0] {
			occurrences++
			tier = e.Tier
		}
	}
	if occurrences != 1 {
		t.Errorf("pinned+exact entity appeared %d times, want 1", occurrences)
	}
	if tier != tierPinned {
		t.Errorf("pinned+exact entity tier: want pinned, got %s", tier)
	}
}

// TestSelectForContext_RecentSkippedWhenQueryMatched verifies that a
// query with matching exact/FTS results does NOT pull in random recent
// entities. This is the K2b-I1 fix regression.
func TestSelectForContext_RecentSkippedWhenQueryMatched(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c400b"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "MatchingHero"},
		{Name: "Unrelated1"},
		{Name: "Unrelated2"},
		{Name: "Unrelated3"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "MatchingHero",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	// Should only contain the exact match — no recent-tier pollution.
	for _, e := range resp.Entities {
		if e.Tier == tierRecent {
			t.Errorf("recent-tier entity %s leaked into a query that matched", e.EntityID)
		}
	}
	if len(resp.Entities) == 0 {
		t.Fatal("expected at least the exact match")
	}
}

// TestSelectForContext_RecentFallbackWhenQueryMatchesNothing verifies
// the recent fallback STILL runs when a query was given but produced
// zero hits — otherwise callers would get an empty context.
func TestSelectForContext_RecentFallbackWhenQueryMatchesNothing(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c400c"
	seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "Alpha"},
		{Name: "Beta"},
	})

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "xxnotinanynamexx",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	if len(resp.Entities) != 2 {
		t.Errorf("expected 2 recent-fallback entities, got %d", len(resp.Entities))
	}
	for _, e := range resp.Entities {
		if e.Tier != tierRecent {
			t.Errorf("fallback tier: want recent, got %s", e.Tier)
		}
	}
}

func TestSelectForContext_DeletedEntitiesExcluded(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv, token := newContextTestServer(t, pool)

	bookID := "00000000-0000-0000-0000-0000000c4009"
	ids := seedContextBook(t, pool, bookID, []seedEntity{
		{Name: "Live"},
		{Name: "Dead"},
	})
	pool.Exec(context.Background(),
		`UPDATE glossary_entities SET deleted_at = now() WHERE entity_id = $1`, ids[1])

	_, resp := callSelectForContext(t, srv, bookID, map[string]interface{}{
		"query":        "",
		"max_entities": 10,
	}, token)
	if resp == nil {
		t.Fatal("nil response")
	}
	for _, e := range resp.Entities {
		if e.EntityID == ids[1] {
			t.Errorf("soft-deleted entity %s returned", ids[1])
		}
	}
}
