package api

// Integration regression tests for the glossary kind-resolution epic (extraction
// parking/aliasing). Requires GLOSSARY_TEST_DB_URL, skips otherwise.
//
// SS-4 Milestone C removed the user-facing system-kind write routes, so the former
// merge/delete-kind review tests (which POSTed /v1/glossary/kinds + /kind-aliases)
// were dropped along with those endpoints. The extraction-time resolution below is
// unaffected — it READS the alias table + parks unknowns, it does not write kinds.
// The bulk-merge review action returns in SS-7, retargeted at the tiered model.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

const kaInternalToken = "kind-alias-test-internal-token"

func newKindAliasServer(t *testing.T, pool *pgxpool.Pool) *Server {
	t.Helper()
	srv := newExportServer(t, pool)
	srv.cfg.InternalServiceToken = kaInternalToken
	return srv
}

// runKindAliasMigrations brings up the full chain the resolution path needs
// (entities/kinds/attrs/soft-delete + the unknown kind & alias table from Up)
// plus the default kind aliases (SeedKindAliases — normally called after Seed in main).
func runKindAliasMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	runK2aMigrations(t, pool)
	ctx := context.Background()
	for _, m := range []struct {
		name string
		fn   func(context.Context, *pgxpool.Pool) error
	}{
		{"UpOutbox", migrate.UpOutbox},
		{"UpWiki", migrate.UpWiki},
		{"UpWikiSuggestions", migrate.UpWikiSuggestions},
	} {
		if err := m.fn(ctx, pool); err != nil {
			t.Fatalf("migrate.%s: %v", m.name, err)
		}
	}
	if err := migrate.SeedKindAliases(ctx, pool); err != nil {
		t.Fatalf("migrate.SeedKindAliases: %v", err)
	}
}

// extractOne posts a single entity with the given kind_code through the internal
// bulk extract-entities endpoint and returns its entity_id.
func extractOne(t *testing.T, srv *Server, bookID, kindCode, name string) string {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"source_language":   "zh",
		"attribute_actions": map[string]any{kindCode: map[string]any{}},
		"entities": []map[string]any{
			{"kind_code": kindCode, "name": name, "attributes": map[string]any{}, "evidence": ""},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID+"/extract-entities", bytes.NewReader(body))
	req.Header.Set("X-Internal-Token", kaInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("extract-entities %s: want 200, got %d (%s)", kindCode, w.Code, w.Body.String())
	}
	var resp struct {
		Entities []struct {
			EntityID string `json:"entity_id"`
		} `json:"entities"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode extract resp: %v (%s)", err, w.Body.String())
	}
	if len(resp.Entities) == 0 || resp.Entities[0].EntityID == "" {
		t.Fatalf("entity was SKIPPED (not parked): %s", w.Body.String())
	}
	return resp.Entities[0].EntityID
}

// resetKindAliasFixture makes a test idempotent against the shared test DB:
// purge the test book's entities (children cascade) and the test alias codes.
// Seeded kinds/aliases (character, generic, …) are untouched.
func resetKindAliasFixture(t *testing.T, pool *pgxpool.Pool, book string, createdKindCodes ...string) {
	t.Helper()
	ctx := context.Background()
	testCodes := []string{"mythical_smoke_kind", "termmap_smoke", "selfcode_smoke", "deletekind_smoke"}
	if _, err := pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book); err != nil {
		t.Fatalf("reset entities: %v", err)
	}
	if _, err := pool.Exec(ctx, `DELETE FROM entity_kind_aliases WHERE alias_code = ANY($1)`, testCodes); err != nil {
		t.Fatalf("reset aliases: %v", err)
	}
	for _, c := range createdKindCodes {
		if _, err := pool.Exec(ctx, `DELETE FROM system_kinds WHERE code=$1`, c); err != nil {
			t.Fatalf("reset kind %s: %v", c, err)
		}
	}
}

func kindIDByCode(t *testing.T, pool *pgxpool.Pool, code string) string {
	t.Helper()
	var id string
	if err := pool.QueryRow(context.Background(),
		`SELECT kind_id FROM system_kinds WHERE code=$1`, code).Scan(&id); err != nil {
		t.Fatalf("kindIDByCode %s: %v", code, err)
	}
	return id
}

// TestKindResolution_ParksUnknownAndAliases proves extract-entities never drops:
// an unresolvable kind parks under 'unknown' with source_kind_code; a seeded
// alias resolves straight to its target kind.
func TestKindResolution_ParksUnknownAndAliases(t *testing.T) {
	pool := openTestDB(t)
	srv := newKindAliasServer(t, pool)
	runKindAliasMigrations(t, pool)
	ctx := context.Background()
	book := "00000000-0000-0000-0aaa-000000000010"
	resetKindAliasFixture(t, pool, book)

	// (1) unresolvable kind → parked under 'unknown' with source_kind_code recorded.
	eid := extractOne(t, srv, book, "mythical_smoke_kind", "測試異兽")
	var kindCode, srcCode string
	pool.QueryRow(ctx, `
		SELECT k.code, COALESCE(e.source_kind_code,'')
		FROM glossary_entities e JOIN system_kinds k ON k.kind_id=e.kind_id
		WHERE e.entity_id=$1`, eid).Scan(&kindCode, &srcCode)
	if kindCode != "unknown" {
		t.Fatalf("unresolvable kind: want parked under 'unknown', got %q", kindCode)
	}
	if srcCode != "mythical_smoke_kind" {
		t.Fatalf("source_kind_code: want 'mythical_smoke_kind', got %q", srcCode)
	}

	// (2) a seeded alias (generic → terminology) resolves straight through.
	eid2 := extractOne(t, srv, book, "generic", "通用詞條")
	pool.QueryRow(ctx, `
		SELECT k.code FROM glossary_entities e JOIN system_kinds k ON k.kind_id=e.kind_id
		WHERE e.entity_id=$1`, eid2).Scan(&kindCode)
	if kindCode != "terminology" {
		t.Fatalf("alias generic→terminology: want 'terminology', got %q", kindCode)
	}
}

// TestKindResolution_ParkUnknownOptOutSkips proves D-GLOSSARY-UNKNOWN-BLAST-RADIUS:
// a caller may send park_unknown_kinds=false to SKIP an unrecognised kind instead of
// parking it under 'unknown'. Default (omitted) still parks.
func TestKindResolution_ParkUnknownOptOutSkips(t *testing.T) {
	pool := openTestDB(t)
	srv := newKindAliasServer(t, pool)
	runKindAliasMigrations(t, pool)
	ctx := context.Background()
	book := "00000000-0000-0000-0aaa-000000000050"
	resetKindAliasFixture(t, pool, book)

	body, _ := json.Marshal(map[string]any{
		"source_language":    "zh",
		"park_unknown_kinds": false,
		"attribute_actions":  map[string]any{"mythical_smoke_kind": map[string]any{}},
		"entities": []map[string]any{
			{"kind_code": "mythical_smoke_kind", "name": "略過異兽", "attributes": map[string]any{}, "evidence": ""},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+book+"/extract-entities", bytes.NewReader(body))
	req.Header.Set("X-Internal-Token", kaInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Created  int `json:"created"`
		Entities []struct {
			EntityID string `json:"entity_id"`
		} `json:"entities"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Created != 0 || len(resp.Entities) != 0 {
		t.Fatalf("park_unknown_kinds=false: want unknown kind SKIPPED, got created=%d entities=%d (%s)",
			resp.Created, len(resp.Entities), w.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE book_id=$1`, book).Scan(&n)
	if n != 0 {
		t.Fatalf("park_unknown_kinds=false: expected no entity rows, got %d", n)
	}
}
