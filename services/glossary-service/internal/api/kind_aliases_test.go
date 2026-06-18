package api

// Integration regression tests for the glossary kind-alias / unknown-kind epic
// (E1 resolution + E3 review actions) and the /review-impl follow-up fixes:
//   - unknown bucket: an unresolvable kind_code is PARKED under 'unknown' (never
//     dropped) remembering its source_kind_code;
//   - seeded alias resolves (generic → terminology) at extract time;
//   - merge (createKindAlias + reassign) re-keys the entity onto the target kind
//     and PRESERVES the display name across name↔term display attrs (#6);
//   - self-code merge (alias_code == the target kind's own code) is allowed: it
//     skips the redundant alias row but still reassigns (#2-glossary);
//   - deleteKind blocks on ACTIVE entities but PURGES soft-deleted ones so an
//     effectively-empty kind is deletable (#3).
//
// DB integration only — requires GLOSSARY_TEST_DB_URL, skips otherwise.

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
const kaUserID = "00000000-0000-0000-0aaa-000000000001"

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
	// deleteKind now reads wiki_articles + writes the wiki.deleted outbox row
	// (Bug-2 fix) — bring those tables up too.
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
// purge the test book's entities (children cascade), the test alias codes, and the
// test-created kinds. Seeded kinds/aliases (character, generic, …) are untouched.
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

func userReq(t *testing.T, srv *Server, method, url, body string) *httptest.ResponseRecorder {
	t.Helper()
	var r *http.Request
	if body == "" {
		r = httptest.NewRequest(method, url, nil)
	} else {
		r = httptest.NewRequest(method, url, bytes.NewReader([]byte(body)))
	}
	r.Header.Set("Authorization", "Bearer "+makeExportToken(t, kaUserID))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, r)
	return w
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
// parking it under 'unknown' (the escape hatch for a pipeline that emits noise kinds).
// Default (omitted) still parks — covered by TestKindResolution_ParksUnknownAndAliases.
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
	// Nothing landed (no 'unknown' parked row for this book).
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE book_id=$1`, book).Scan(&n)
	if n != 0 {
		t.Fatalf("park_unknown_kinds=false: expected no entity rows, got %d", n)
	}
}

// TestKindMerge_ReassignsAndPreservesNameAcrossTermKind proves the merge action
// (#6): reassigning a parked entity onto terminology (which uses a 'term' display
// attr, not 'name') keeps its display name via the name↔term re-key mapping.
func TestKindMerge_ReassignsAndPreservesNameAcrossTermKind(t *testing.T) {
	pool := openTestDB(t)
	srv := newKindAliasServer(t, pool)
	runKindAliasMigrations(t, pool)
	ctx := context.Background()
	book := "00000000-0000-0000-0aaa-000000000020"
	resetKindAliasFixture(t, pool, book)
	const name = "詞條測試-TERMMAP"

	eid := extractOne(t, srv, book, "termmap_smoke", name)
	termKind := kindIDByCode(t, pool, "terminology")

	w := userReq(t, srv, http.MethodPost, "/v1/glossary/kind-aliases",
		`{"alias_code":"termmap_smoke","kind_id":"`+termKind+`","reassign":true,"book_id":"`+book+`"}`)
	if w.Code != http.StatusCreated {
		t.Fatalf("merge: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var mres struct {
		Reassigned int `json:"reassigned"`
	}
	json.Unmarshal(w.Body.Bytes(), &mres)
	if mres.Reassigned < 1 {
		t.Fatalf("merge reassigned: want >=1, got %d", mres.Reassigned)
	}

	// Entity left 'unknown', landed on terminology, name preserved (re-key name→term).
	var nowKind string
	pool.QueryRow(ctx, `
		SELECT k.code FROM glossary_entities e JOIN system_kinds k ON k.kind_id=e.kind_id
		WHERE e.entity_id=$1`, eid).Scan(&nowKind)
	if nowKind != "terminology" {
		t.Fatalf("after merge: want 'terminology', got %q", nowKind)
	}
	// The display value survived the re-key: it now lives under terminology's
	// display attr ('name' or 'term') with the original value intact (#6). Asserted
	// via SQL — the entity detail endpoint needs book-service, absent in unit tests.
	var displayVal string
	pool.QueryRow(ctx, `
		SELECT eav.original_value
		FROM entity_attribute_values eav
		JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id=$1 AND ad.kind_id=(SELECT kind_id FROM system_kinds WHERE code='terminology')
		  AND ad.code IN ('name','term')`, eid).Scan(&displayVal)
	if displayVal != name {
		t.Fatalf("name LOST after name→term re-key: want %q, got %q", name, displayVal)
	}
}

// TestKindMerge_SelfCodeSkipsAliasButReassigns proves #2-glossary: aliasing a code
// to the kind that ALREADY owns it (new kind whose code == the parked source code)
// is allowed — it skips the redundant alias row but still reassigns. The dead-alias
// case (code is a DIFFERENT existing kind) still 409s.
func TestKindMerge_SelfCodeSkipsAliasButReassigns(t *testing.T) {
	pool := openTestDB(t)
	srv := newKindAliasServer(t, pool)
	runKindAliasMigrations(t, pool)
	ctx := context.Background()
	book := "00000000-0000-0000-0aaa-000000000030"
	resetKindAliasFixture(t, pool, book, "selfcode_smoke")

	eid := extractOne(t, srv, book, "selfcode_smoke", "自碼測試")
	// Create a new kind whose code == the parked source code.
	cw := userReq(t, srv, http.MethodPost, "/v1/glossary/kinds",
		`{"code":"selfcode_smoke","name":"Selfcode Smoke"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("create kind: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var ck struct {
		KindID string `json:"kind_id"`
	}
	json.Unmarshal(cw.Body.Bytes(), &ck)

	// Merge alias_code == the new kind's own code → 201, skip-alias, still reassign.
	mw := userReq(t, srv, http.MethodPost, "/v1/glossary/kind-aliases",
		`{"alias_code":"selfcode_smoke","kind_id":"`+ck.KindID+`","reassign":true,"book_id":"`+book+`"}`)
	if mw.Code != http.StatusCreated {
		t.Fatalf("self-code merge: want 201, got %d (%s)", mw.Code, mw.Body.String())
	}
	var mres struct {
		AliasID    string `json:"alias_id"`
		Reassigned int    `json:"reassigned"`
	}
	json.Unmarshal(mw.Body.Bytes(), &mres)
	if mres.AliasID != "" {
		t.Errorf("self-code merge: expected NO alias row (empty alias_id), got %q", mres.AliasID)
	}
	if mres.Reassigned < 1 {
		t.Errorf("self-code merge: want reassigned>=1, got %d", mres.Reassigned)
	}
	// No alias row persisted for the self-code.
	var aliasRows int
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_kind_aliases WHERE alias_code='selfcode_smoke'`).Scan(&aliasRows)
	if aliasRows != 0 {
		t.Errorf("self-code merge persisted a redundant alias row (%d)", aliasRows)
	}
	// Entity moved onto the new kind, name intact (new kind has a seeded 'name' attr).
	var nowKind string
	pool.QueryRow(ctx, `
		SELECT k.code FROM glossary_entities e JOIN system_kinds k ON k.kind_id=e.kind_id
		WHERE e.entity_id=$1`, eid).Scan(&nowKind)
	if nowKind != "selfcode_smoke" {
		t.Fatalf("after self-code merge: want 'selfcode_smoke', got %q", nowKind)
	}

	// Dead-alias guard: alias_code 'character' (a DIFFERENT existing kind) → 409.
	dw := userReq(t, srv, http.MethodPost, "/v1/glossary/kind-aliases",
		`{"alias_code":"character","kind_id":"`+ck.KindID+`"}`)
	if dw.Code != http.StatusConflict {
		t.Errorf("dead-alias guard: want 409, got %d (%s)", dw.Code, dw.Body.String())
	}
}

// TestDeleteKind_BlocksActiveButPurgesSoftDeleted proves #3: a kind with ACTIVE
// entities cannot be deleted, but once its entities are soft-deleted (recycle bin)
// the kind IS deletable (the soft-deleted rows are purged in the delete tx).
func TestDeleteKind_BlocksActiveButPurgesSoftDeleted(t *testing.T) {
	pool := openTestDB(t)
	srv := newKindAliasServer(t, pool)
	runKindAliasMigrations(t, pool)
	ctx := context.Background()
	book := "00000000-0000-0000-0aaa-000000000040"
	resetKindAliasFixture(t, pool, book, "deletekind_smoke")

	cw := userReq(t, srv, http.MethodPost, "/v1/glossary/kinds",
		`{"code":"deletekind_smoke","name":"DeleteKind Smoke"}`)
	var ck struct {
		KindID string `json:"kind_id"`
	}
	json.Unmarshal(cw.Body.Bytes(), &ck)
	eid := extractOne(t, srv, book, "deletekind_smoke", "待刪實體")

	// Active entity → delete blocked (409).
	if w := userReq(t, srv, http.MethodDelete, "/v1/glossary/kinds/"+ck.KindID, ""); w.Code != http.StatusConflict {
		t.Fatalf("delete kind with active entity: want 409, got %d (%s)", w.Code, w.Body.String())
	}

	// Soft-delete the entity (recycle bin) — done via SQL to mirror deleteEntity's
	// `SET deleted_at=now()` without the book-service call its endpoint makes (absent
	// in unit tests). Then deleting the kind must purge it and succeed.
	if _, err := pool.Exec(ctx, `UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, eid); err != nil {
		t.Fatalf("soft-delete entity (sql): %v", err)
	}
	// Bug-2 fix: give the soft-deleted entity a wiki_article (a product). With the
	// entity FK now RESTRICT, deleteKind must delete it EXPLICITLY (not FK-block),
	// surface a count, and emit wiki.deleted — instead of the prior silent CASCADE.
	if _, err := pool.Exec(ctx,
		`INSERT INTO wiki_articles (entity_id, book_id, body_json, status) VALUES ($1,$2,'{}','draft')`,
		eid, book); err != nil {
		t.Fatalf("seed wiki article: %v", err)
	}
	w := userReq(t, srv, http.MethodDelete, "/v1/glossary/kinds/"+ck.KindID, "")
	if w.Code != http.StatusOK {
		t.Fatalf("delete kind: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var delResp struct {
		DeletedWikiArticles int `json:"deleted_wiki_articles"`
	}
	json.Unmarshal(w.Body.Bytes(), &delResp)
	if delResp.DeletedWikiArticles != 1 {
		t.Errorf("deleted_wiki_articles = %d, want 1 (article must be deleted explicitly, not silently)", delResp.DeletedWikiArticles)
	}
	var nEvent, nArt int
	pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE event_type='wiki.deleted' AND payload->>'entity_id'=$1`, eid).Scan(&nEvent)
	if nEvent != 1 {
		t.Errorf("wiki.deleted events for entity = %d, want 1 (destruction must be observable)", nEvent)
	}
	pool.QueryRow(ctx, `SELECT count(*) FROM wiki_articles WHERE entity_id=$1`, eid).Scan(&nArt)
	if nArt != 0 {
		t.Errorf("wiki article not deleted (%d remain)", nArt)
	}
	var kindRows, entRows int
	pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds WHERE kind_id=$1`, ck.KindID).Scan(&kindRows)
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE entity_id=$1`, eid).Scan(&entRows)
	if kindRows != 0 {
		t.Errorf("kind not deleted (%d rows remain)", kindRows)
	}
	if entRows != 0 {
		t.Errorf("soft-deleted entity not purged (%d rows remain)", entRows)
	}
}
