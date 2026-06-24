package api

// G4 regression — createEntity must validate kind_id against the BOOK tier.
// The cutover repointed glossary_entities.kind_id -> book_kinds; createEntity's
// kind check had been left validating system_kinds (no test exercised the POST,
// so it slipped through green). This guards: (1) a live book kind -> 201;
// (2) a non-book / foreign-book kind id -> 404 (never a 500 FK violation).
// Requires GLOSSARY_TEST_DB_URL.

import (
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestCreateEntity_ValidatesBookTierKind(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	adoptTestBook(t, pool, book)
	base := "/v1/glossary/books/" + book.String() + "/entities"

	// A live book kind → 201.
	bk := bookKindID(t, pool, book, "character")
	if w := ukReq(t, srv, http.MethodPost, base, owner.String(), `{"kind_id":"`+bk.String()+`"}`); w.Code != http.StatusCreated {
		t.Fatalf("create with book kind: want 201, got %d (%s)", w.Code, w.Body.String())
	}

	// A random id that is not a book kind of this book → 404 (not a 500 FK error).
	if w := ukReq(t, srv, http.MethodPost, base, owner.String(), `{"kind_id":"`+uuid.NewString()+`"}`); w.Code != http.StatusNotFound {
		t.Fatalf("create with non-book kind: want 404, got %d (%s)", w.Code, w.Body.String())
	}

	// A kind that exists but in ANOTHER book must not be accepted (tenant boundary).
	otherBook := uuid.New()
	adoptTestBook(t, pool, otherBook)
	otherKind := bookKindID(t, pool, otherBook, "character")
	if w := ukReq(t, srv, http.MethodPost, base, owner.String(), `{"kind_id":"`+otherKind.String()+`"}`); w.Code != http.StatusNotFound {
		t.Fatalf("create with another book's kind: want 404, got %d (%s)", w.Code, w.Body.String())
	}
}
