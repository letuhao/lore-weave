package api

// Tests for the M7 backfill recount endpoint
// POST /internal/books/{book_id}/recount-mention-counts.
// Unit auth tests run always; the DB round-trip needs GLOSSARY_TEST_DB_URL.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func TestRecountMentions_RequiresInternalToken(t *testing.T) {
	srv, _ := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0000-000000000001/recount-mention-counts",
		bytes.NewReader([]byte(`{"counts":[]}`)))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestRecountMentions_EmptyCountsOK(t *testing.T) {
	srv, token := newEntitiesListServer(t)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0000-000000000001/recount-mention-counts",
		bytes.NewReader([]byte(`{"counts":[]}`)))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("empty counts: want 200, got %d", w.Code)
	}
	var r map[string]int
	_ = json.Unmarshal(w.Body.Bytes(), &r)
	if r["updated"] != 0 {
		t.Errorf("empty counts: want updated=0, got %v", r)
	}
}

// TestRecountMentions_DB — a recount UPDATE lands on an existing link, is idempotent on
// re-POST, and never touches a (entity,chapter) outside the target book.
func TestRecountMentions_DB(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrateUpOutbox(t, pool); err != nil {
		t.Fatalf("UpOutbox: %v", err)
	}

	bookID := "00000000-0000-0000-0001-0000000a7040"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": chap, "chapter_index": 1, "mention_count": 0},
			}},
		},
	})

	// Resolve the created entity id.
	var entityID string
	if err := pool.QueryRow(ctx,
		`SELECT entity_id FROM glossary_entities WHERE book_id=$1 AND deleted_at IS NULL LIMIT 1`,
		bookID).Scan(&entityID); err != nil {
		t.Fatalf("resolve entity: %v", err)
	}

	post := func(body string) map[string]int {
		req := httptest.NewRequest(http.MethodPost,
			"/internal/books/"+bookID+"/recount-mention-counts", bytes.NewReader([]byte(body)))
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("recount: want 200, got %d body=%s", w.Code, w.Body.String())
		}
		var r map[string]int
		_ = json.Unmarshal(w.Body.Bytes(), &r)
		return r
	}

	// First recount → 1 row updated, value lands.
	r1 := post(`{"counts":[{"entity_id":"` + entityID + `","chapter_id":"` + chap + `","mention_count":15}]}`)
	if r1["updated"] != 1 {
		t.Fatalf("first recount: want updated=1, got %v", r1)
	}
	var got int
	if err := pool.QueryRow(ctx,
		`SELECT mention_count FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`,
		entityID, chap).Scan(&got); err != nil {
		t.Fatalf("read count: %v", err)
	}
	if got != 15 {
		t.Errorf("mention_count after recount: want 15, got %d", got)
	}

	// Re-POST the same value → idempotent (still 1 row matched, value unchanged).
	post(`{"counts":[{"entity_id":"` + entityID + `","chapter_id":"` + chap + `","mention_count":15}]}`)
	if err := pool.QueryRow(ctx,
		`SELECT mention_count FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`,
		entityID, chap).Scan(&got); err != nil {
		t.Fatalf("read count 2: %v", err)
	}
	if got != 15 {
		t.Errorf("idempotent re-recount: want 15, got %d", got)
	}

	// A recount for a different book must NOT touch this link (book-scoped UPDATE → 0 rows).
	otherBook := uuid.NewString()
	rScoped := postToBook(t, srv, token, otherBook,
		`{"counts":[{"entity_id":"`+entityID+`","chapter_id":"`+chap+`","mention_count":99}]}`)
	if rScoped["updated"] != 0 {
		t.Errorf("cross-book recount must update 0 rows, got %v", rScoped)
	}
	if err := pool.QueryRow(ctx,
		`SELECT mention_count FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`,
		entityID, chap).Scan(&got); err != nil {
		t.Fatalf("read count 3: %v", err)
	}
	if got != 15 {
		t.Errorf("cross-book recount leaked: want 15 unchanged, got %d", got)
	}
}

func postToBook(t *testing.T, srv *Server, token, bookID, body string) map[string]int {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/recount-mention-counts", bytes.NewReader([]byte(body)))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("recount(%s): want 200, got %d body=%s", bookID, w.Code, w.Body.String())
	}
	var r map[string]int
	_ = json.Unmarshal(w.Body.Bytes(), &r)
	return r
}
