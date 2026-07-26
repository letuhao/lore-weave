package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/loreweave/book-service/internal/config"
)

// W11-M1 (spec §4.1) — the reading-position resolver feeds a reader's spoiler
// cutoff, so its pre-pool guards are load-bearing: a bad/missing user_id must NOT
// reach the query (it's the parent-scope vector — you only ever get your OWN
// position), and the route must sit behind the internal-token wall. The furthest-
// active-chapter SQL, the soft-deleted-chapter exclusion, and the empty-reader →
// null-position (fail-closed) paths are pinned in analytics_db_test.go against a
// real Postgres (BOOK_TEST_DATABASE_URL). The null-position → "reader sees nothing"
// INTERPRETATION is unit-tested in the knowledge facade (M2), where fail-closed is
// actually decided.

func TestInternalReadingPositionInvalidBookID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/internal/books/not-a-uuid/reading-position?user_id="+uuid.New().String(), "", "", map[string]string{"book_id": "not-a-uuid"})
	s.getInternalReadingPosition(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid book_id, got %d", rr.Code)
	}
}

func TestInternalReadingPositionMissingUserID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	bid := uuid.New()
	rr := httptest.NewRecorder()
	// valid book_id but NO user_id query param → 400 before the pool-backed
	// lookup (you can't omit the id to read some default reader's position).
	req := worldReq(http.MethodGet, "/internal/books/"+bid.String()+"/reading-position", "", "", map[string]string{"book_id": bid.String()})
	s.getInternalReadingPosition(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing user_id, got %d", rr.Code)
	}
}

func TestInternalReadingPositionRejectsMalformedUserID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	bid := uuid.New()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/internal/books/"+bid.String()+"/reading-position?user_id=not-a-uuid", "", "", map[string]string{"book_id": bid.String()})
	s.getInternalReadingPosition(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for malformed user_id, got %d", rr.Code)
	}
}

// Prove the route is INSIDE the requireInternalToken group — a refactor that moved
// it out would let any caller read any reader's position. No token → 401,
// short-circuited before any pool access (nil pool is fine).
func TestInternalReadingPositionRequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := &Server{cfg: &config.Config{InternalServiceToken: "secret-internal-token"}}
	srv := httptest.NewServer(s.Router())
	defer srv.Close()
	resp, err := http.Get(srv.URL + "/internal/books/" + uuid.New().String() + "/reading-position?user_id=" + uuid.New().String())
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 without internal token, got %d", resp.StatusCode)
	}
}
