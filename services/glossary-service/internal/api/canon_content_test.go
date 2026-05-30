package api

// Tests for POST /internal/books/{book_id}/entities/{entity_id}/canon-content
// (lore-enrichment DEFERRED-053 / Q2 canon-content write).
//
// Unit tests (no DB) run always. DB integration tests require
// GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func newCanonContentServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "canon-content-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

const canonContentURL = "/internal/books/00000000-0000-0000-0000-000000000001/entities/00000000-0000-0000-0000-000000000002/canon-content"

// ── unit tests (no DB) ──────────────────────────────────────────────

func TestCanonContent_RequiresInternalToken(t *testing.T) {
	srv, _ := newCanonContentServer(t)
	req := httptest.NewRequest(http.MethodPost, canonContentURL,
		strings.NewReader(`{"short_description":"x"}`))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestCanonContent_WrongTokenReturns401(t *testing.T) {
	srv, _ := newCanonContentServer(t)
	req := httptest.NewRequest(http.MethodPost, canonContentURL,
		strings.NewReader(`{"short_description":"x"}`))
	req.Header.Set("X-Internal-Token", "wrong")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("wrong token: want 401, got %d", w.Code)
	}
}

func TestCanonContent_BadBookUUIDReturns400(t *testing.T) {
	srv, token := newCanonContentServer(t)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/not-a-uuid/entities/00000000-0000-0000-0000-000000000002/canon-content",
		strings.NewReader(`{"short_description":"x"}`))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad book uuid: want 400, got %d", w.Code)
	}
}

func TestCanonContent_InvalidBodyReturns400(t *testing.T) {
	srv, token := newCanonContentServer(t)
	req := httptest.NewRequest(http.MethodPost, canonContentURL,
		strings.NewReader(`not json`))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad body: want 400, got %d", w.Code)
	}
}

// The 500-rune cap is enforced BEFORE the DB write, so this runs without a DB.
// Uses CJK runes (each 3 bytes in UTF-8) to confirm the cap is measured in
// runes/characters, not bytes — 501 CJK chars must be rejected.
func TestCanonContent_TooLongReturns422(t *testing.T) {
	srv, token := newCanonContentServer(t)
	long := strings.Repeat("仙", 501)
	body := `{"short_description":"` + long + `"}`
	req := httptest.NewRequest(http.MethodPost, canonContentURL, strings.NewReader(body))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("501 CJK runes: want 422, got %d body=%s", w.Code, w.Body.String())
	}
}

// ── integration (requires DB) ──────────────────────────────────────

// runCanonContentMigrations applies the full chain needed for the canon-content
// path: base + snapshot + soft-delete + extraction (alive) + outbox (so the
// emit insert succeeds) + short_description_auto (the column the handler sets
// false) + the short_description constraints.
func runCanonContentMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.UpOutbox(ctx, pool); err != nil {
		t.Fatalf("migrate.UpOutbox: %v", err)
	}
	if err := migrate.UpShortDescAuto(ctx, pool); err != nil {
		t.Fatalf("migrate.UpShortDescAuto: %v", err)
	}
	if err := migrate.UpShortDescConstraints(ctx, pool); err != nil {
		t.Fatalf("migrate.UpShortDescConstraints: %v", err)
	}
}

// TestCanonContent_SetsColumnAndEmitsEvent is the DEFERRED-053 core proof:
//   - an EXISTING identity-only entity has NULL short_description (quarantine);
//   - POST canon-content populates the short_description COLUMN;
//   - short_description_auto flips to false (author-authored, sticky);
//   - a glossary.entity_updated outbox row is emitted (drives glossary_sync).
func TestCanonContent_SetsColumnAndEmitsEvent(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runCanonContentMigrations(t, pool)

	bookID := "00000000-0000-0000-0001-000000000053"

	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='location' LIMIT 1`).Scan(&kindID)
	if kindID == "" {
		// Fall back to character if the seed has no location kind.
		pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	}
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID,
	).Scan(&nameAttrID)

	// Seed an EXISTING identity-only entity: name set, short_description NULL.
	var eid string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags)
		 VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID,
	).Scan(&eid)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3)`,
		eid, nameAttrID, "蓬萊",
	)

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})

	// Pre-state: short_description MUST be NULL (quarantine — no canon content).
	var pre *string
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, eid).Scan(&pre)
	if pre != nil {
		t.Fatalf("pre-promote short_description must be NULL, got %q", *pre)
	}

	srv, token := newCanonContentServer(t)
	srv.pool = pool

	content := "蓬萊：东海仙山，云雾缭绕，乃上古仙人所居之地。"
	url := "/internal/books/" + bookID + "/entities/" + eid + "/canon-content"
	req := httptest.NewRequest(http.MethodPost, url,
		strings.NewReader(`{"short_description":"`+content+`"}`))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("set canon-content: want 200, got %d body=%s", w.Code, w.Body.String())
	}

	// Post-state: short_description POPULATED with the enriched content.
	var post *string
	var auto bool
	pool.QueryRow(ctx,
		`SELECT short_description, short_description_auto FROM glossary_entities WHERE entity_id=$1`, eid,
	).Scan(&post, &auto)
	if post == nil || *post != content {
		t.Fatalf("post-promote short_description: want %q, got %v", content, post)
	}
	if auto {
		t.Errorf("short_description_auto must be false (author-authored), got true")
	}

	// A glossary.entity_updated outbox row must exist (drives glossary_sync → Neo4j).
	var nEvents int
	pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`, eid,
	).Scan(&nEvents)
	if nEvents < 1 {
		t.Errorf("want >=1 glossary.entity_updated event, got %d", nEvents)
	}
}

// TestCanonContent_NonexistentEntityReturns404 confirms a stale/cross-book
// entity_id is a 404, not a silent no-op on the wrong row.
func TestCanonContent_NonexistentEntityReturns404(t *testing.T) {
	pool := openTestDB(t)
	runCanonContentMigrations(t, pool)

	srv, token := newCanonContentServer(t)
	srv.pool = pool

	url := "/internal/books/00000000-0000-0000-0001-000000000053/entities/00000000-0000-0000-0000-0000000000ff/canon-content"
	req := httptest.NewRequest(http.MethodPost, url, strings.NewReader(`{"short_description":"x"}`))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNotFound {
		t.Errorf("nonexistent entity: want 404, got %d", w.Code)
	}
}
