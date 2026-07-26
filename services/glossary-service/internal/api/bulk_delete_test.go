package api

// Tests for POST /v1/glossary/books/{book_id}/entities/bulk-delete.
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

type bulkDeleteFixture struct {
	srv     *Server
	jwt     string
	ownerID uuid.UUID
	bookID  uuid.UUID
}

func newBulkDeleteFixture(t *testing.T, pool *pgxpool.Pool) *bulkDeleteFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	owner, book := uuid.New(), uuid.New()
	// book owned by owner → the owner satisfies every grant tier incl. Manage.
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)
	srv := NewServer(pool, &config.Config{
		JWTSecret: versionTestSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok",
	})
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: owner.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return &bulkDeleteFixture{srv: srv, jwt: signed, ownerID: owner, bookID: book}
}

func (f *bulkDeleteFixture) post(t *testing.T, body any, bearer string) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/bulk-delete", bytes.NewReader(b))
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func isEntityDeleted(t *testing.T, pool *pgxpool.Pool, id uuid.UUID) bool {
	t.Helper()
	var deleted bool
	if err := pool.QueryRow(context.Background(),
		`SELECT deleted_at IS NOT NULL FROM glossary_entities WHERE entity_id=$1`, id).Scan(&deleted); err != nil {
		t.Fatalf("deleted_at read: %v", err)
	}
	return deleted
}

func TestBulkDelete_SoftDeletesBookScoped(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkDeleteFixture(t, pool)

	e1 := seedBulkEntity(t, pool, f.bookID, "active")
	e2 := seedBulkEntity(t, pool, f.bookID, "draft")
	otherBook := uuid.New()
	eOther := seedBulkEntity(t, pool, otherBook, "active") // must NOT be touched
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, otherBook)
	})

	// Mix in a cross-book id, a malformed id, and a random non-existent id — none
	// should count, proving book-scoping + the malformed-id drop.
	w := f.post(t, map[string]any{
		"entity_ids": []string{e1.String(), e2.String(), eOther.String(), "not-a-uuid", uuid.New().String()},
	}, f.jwt)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var resp struct {
		Deleted int `json:"deleted"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Deleted != 2 {
		t.Errorf("deleted: want 2 (only this book's two entities), got %d", resp.Deleted)
	}
	if !isEntityDeleted(t, pool, e1) || !isEntityDeleted(t, pool, e2) {
		t.Errorf("e1/e2 must be soft-deleted")
	}
	if isEntityDeleted(t, pool, eOther) {
		t.Errorf("cross-book entity must be untouched")
	}
}

func TestBulkDelete_AlreadyDeletedNotRecounted(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkDeleteFixture(t, pool)
	e1 := seedBulkEntity(t, pool, f.bookID, "active")
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})

	first := f.post(t, map[string]any{"entity_ids": []string{e1.String()}}, f.jwt)
	if first.Code != http.StatusOK {
		t.Fatalf("first delete want 200, got %d", first.Code)
	}
	var r1 struct {
		Deleted int `json:"deleted"`
	}
	json.Unmarshal(first.Body.Bytes(), &r1)
	if r1.Deleted != 1 {
		t.Fatalf("first delete: want 1, got %d", r1.Deleted)
	}

	// Re-deleting an already-soft-deleted entity is a no-op (deleted_at IS NULL
	// filter) — the count must be 0, never a double-delete.
	second := f.post(t, map[string]any{"entity_ids": []string{e1.String()}}, f.jwt)
	var r2 struct {
		Deleted int `json:"deleted"`
	}
	json.Unmarshal(second.Body.Bytes(), &r2)
	if r2.Deleted != 0 {
		t.Errorf("re-delete: want 0 (already deleted), got %d", r2.Deleted)
	}
}

func TestBulkDelete_EmptyIdsRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkDeleteFixture(t, pool)
	w := f.post(t, map[string]any{"entity_ids": []string{}}, f.jwt)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("empty ids: want 400, got %d", w.Code)
	}
}

func TestBulkDelete_AllMalformedReturnsZero(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkDeleteFixture(t, pool)
	w := f.post(t, map[string]any{"entity_ids": []string{"nope", "also-bad"}}, f.jwt)
	if w.Code != http.StatusOK {
		t.Fatalf("all-malformed: want 200, got %d", w.Code)
	}
	var resp struct {
		Deleted int `json:"deleted"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Deleted != 0 {
		t.Errorf("all-malformed: want deleted 0, got %d", resp.Deleted)
	}
}

func TestBulkDelete_RequiresAuth(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkDeleteFixture(t, pool)
	w := f.post(t, map[string]any{"entity_ids": []string{uuid.New().String()}}, "")
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no token: want 401, got %d", w.Code)
	}
}
