package api

// Tests for POST /v1/glossary/books/{book_id}/entities/bulk-status.
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

type bulkStatusFixture struct {
	srv     *Server
	jwt     string
	ownerID uuid.UUID
	bookID  uuid.UUID
}

func newBulkStatusFixture(t *testing.T, pool *pgxpool.Pool) *bulkStatusFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	owner, book := uuid.New(), uuid.New()
	ts := httptest.NewServer(projection(book, owner)) // book owned by owner → edit grant
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
	return &bulkStatusFixture{srv: srv, jwt: signed, ownerID: owner, bookID: book}
}

func (f *bulkStatusFixture) post(t *testing.T, body any, bearer string) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/bulk-status", bytes.NewReader(b))
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func seedBulkEntity(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID, status string) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	adoptTestBook(t, pool, bookID)
	kindID := bookKindID(t, pool, bookID, "character")
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,$3,'{}') RETURNING entity_id`,
		bookID, kindID, status).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	return eid
}

func statusOf(t *testing.T, pool *pgxpool.Pool, id uuid.UUID) string {
	t.Helper()
	var s string
	if err := pool.QueryRow(context.Background(),
		`SELECT status FROM glossary_entities WHERE entity_id=$1`, id).Scan(&s); err != nil {
		t.Fatalf("status read: %v", err)
	}
	return s
}

func TestBulkSetStatus_ActivatesDraftsBookScoped(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)

	d1 := seedBulkEntity(t, pool, f.bookID, "draft")
	d2 := seedBulkEntity(t, pool, f.bookID, "draft")
	otherBook := uuid.New()
	dOther := seedBulkEntity(t, pool, otherBook, "draft") // must NOT be touched
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, otherBook)
	})

	w := f.post(t, map[string]any{
		"status":     "active",
		"entity_ids": []string{d1.String(), d2.String(), dOther.String(), "not-a-uuid", uuid.New().String()},
	}, f.jwt)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var resp struct {
		Updated int `json:"updated"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Updated != 2 {
		t.Errorf("updated: want 2 (only this book's two drafts), got %d", resp.Updated)
	}
	if statusOf(t, pool, d1) != "active" || statusOf(t, pool, d2) != "active" {
		t.Errorf("d1/d2 must be active")
	}
	if statusOf(t, pool, dOther) != "draft" {
		t.Errorf("cross-book entity must be untouched, got %s", statusOf(t, pool, dOther))
	}
}

func TestBulkSetStatus_DeactivatesActive(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)
	a1 := seedBulkEntity(t, pool, f.bookID, "active")
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})
	w := f.post(t, map[string]any{"status": "inactive", "entity_ids": []string{a1.String()}}, f.jwt)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	if statusOf(t, pool, a1) != "inactive" {
		t.Errorf("entity must be inactive, got %s", statusOf(t, pool, a1))
	}
}

func TestBulkSetStatus_SetsRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)
	d1 := seedBulkEntity(t, pool, f.bookID, "draft")
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})
	w := f.post(t, map[string]any{"status": "rejected", "entity_ids": []string{d1.String()}}, f.jwt)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	if statusOf(t, pool, d1) != "rejected" {
		t.Errorf("entity must be rejected, got %s", statusOf(t, pool, d1))
	}
}

func TestBulkSetStatus_BadStatusRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)
	w := f.post(t, map[string]any{"status": "bogus", "entity_ids": []string{uuid.New().String()}}, f.jwt)
	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("bad status: want 422, got %d", w.Code)
	}
}

func TestBulkSetStatus_EmptyIdsRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)
	w := f.post(t, map[string]any{"status": "active", "entity_ids": []string{}}, f.jwt)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("empty ids: want 400, got %d", w.Code)
	}
}

func TestBulkSetStatus_RequiresAuth(t *testing.T) {
	pool := openTestDB(t)
	f := newBulkStatusFixture(t, pool)
	w := f.post(t, map[string]any{"status": "active", "entity_ids": []string{uuid.New().String()}}, "")
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no token: want 401, got %d", w.Code)
	}
}
