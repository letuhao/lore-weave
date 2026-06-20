package api

// G3 — book adopt (copy-down) + book-local ontology read. Requires GLOSSARY_TEST_DB_URL.
// Proves the spike's Moment A (copy-down from System) + Moment B (book-local read)
// through the real HTTP handlers, plus the Manage-grant gate (non-owner → 403).

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

// newAdoptServer builds a Server whose grant resolution is backed by a mock
// book-service projection where `owner` owns `book` (→ satisfies View/Edit/Manage).
func newAdoptServer(t *testing.T, pool *pgxpool.Pool, book, owner uuid.UUID) *Server {
	t.Helper()
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)
	return NewServer(pool, &config.Config{
		JWTSecret: exportTestSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok",
	})
}

func TestBookAdopt_CopyDownAndOntology(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	// ADOPT (Moment A): pick xianxia+romance genres, character+location kinds.
	aw := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["xianxia","romance"],"kinds":["character","location"]}`)
	if aw.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", aw.Code, aw.Body.String())
	}
	var ont bookOntologyResp
	if err := json.Unmarshal(aw.Body.Bytes(), &ont); err != nil {
		t.Fatalf("decode ontology: %v", err)
	}

	// Genres: picked xianxia+romance PLUS the mandatory universal (O4), universal active.
	genreCodes := map[string]bool{}
	universalActive := false
	for _, g := range ont.Genres {
		genreCodes[g.Code] = true
		if g.Code == "universal" && g.Active {
			universalActive = true
		}
		if g.SourceRef == nil {
			t.Fatalf("adopted genre %q missing source_ref", g.Code)
		}
	}
	for _, want := range []string{"universal", "xianxia", "romance"} {
		if !genreCodes[want] {
			t.Fatalf("adopt missing genre %q (got %v)", want, genreCodes)
		}
	}
	if !universalActive {
		t.Fatal("universal genre not active after adopt (O4)")
	}

	// Kinds: picked character+location PLUS the always-adopted unknown (E6).
	kindCodes := map[string]string{} // code → book_kind_id
	for _, k := range ont.Kinds {
		kindCodes[k.Code] = k.BookKindID
	}
	for _, want := range []string{"character", "location", "unknown"} {
		if _, ok := kindCodes[want]; !ok {
			t.Fatalf("adopt missing kind %q (got %v)", want, kindCodes)
		}
	}

	// Attributes: character's seeded attrs (lifted to universal) copied into the book,
	// referencing the BOOK character kind id (book-local FK, not the system id).
	charKindID := kindCodes["character"]
	var charNameAttr bool
	for _, a := range ont.Attributes {
		if a.KindID == charKindID && a.Code == "name" {
			charNameAttr = true
			if a.SourceRef == nil {
				t.Fatal("adopted attribute missing source_ref")
			}
		}
	}
	if !charNameAttr {
		t.Fatalf("adopt did not copy character's 'name' attribute (%d attrs total)", len(ont.Attributes))
	}

	// kind_genres links present (character linked to universal at least).
	if len(ont.KindGenres) == 0 {
		t.Fatal("adopt produced no kind_genres links")
	}

	// Moment B: GET /ontology returns the same book-local view.
	gw := ukReq(t, srv, http.MethodGet, base+"/ontology", owner.String(), "")
	if gw.Code != http.StatusOK {
		t.Fatalf("ontology read: want 200, got %d (%s)", gw.Code, gw.Body.String())
	}
	var ont2 bookOntologyResp
	json.Unmarshal(gw.Body.Bytes(), &ont2)
	if len(ont2.Genres) != len(ont.Genres) || len(ont2.Kinds) != len(ont.Kinds) || len(ont2.Attributes) != len(ont.Attributes) {
		t.Fatalf("ontology read mismatch adopt result: g=%d/%d k=%d/%d a=%d/%d",
			len(ont2.Genres), len(ont.Genres), len(ont2.Kinds), len(ont.Kinds), len(ont2.Attributes), len(ont.Attributes))
	}

	// Idempotent: a second adopt of the same set changes nothing (ON CONFLICT).
	aw2 := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["xianxia","romance"],"kinds":["character","location"]}`)
	if aw2.Code != http.StatusOK {
		t.Fatalf("re-adopt: want 200, got %d", aw2.Code)
	}
	var ont3 bookOntologyResp
	json.Unmarshal(aw2.Body.Bytes(), &ont3)
	if len(ont3.Genres) != len(ont.Genres) || len(ont3.Kinds) != len(ont.Kinds) || len(ont3.Attributes) != len(ont.Attributes) {
		t.Fatalf("re-adopt not idempotent: g=%d/%d k=%d/%d a=%d/%d",
			len(ont3.Genres), len(ont.Genres), len(ont3.Kinds), len(ont.Kinds), len(ont3.Attributes), len(ont.Attributes))
	}

	// A second adopt that ADDS a kind grows the set (item is item-kind).
	aw3 := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(), `{"genres":[],"kinds":["item"]}`)
	if aw3.Code != http.StatusOK {
		t.Fatalf("adopt-more: want 200, got %d", aw3.Code)
	}
	var ont4 bookOntologyResp
	json.Unmarshal(aw3.Body.Bytes(), &ont4)
	if _, ok := kindByCode(ont4, "item"); !ok {
		t.Fatal("adopt-more did not add the item kind")
	}
}

func TestBookAdopt_NonOwnerForbidden(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	other := uuid.NewString()
	// Non-owner (grant_level none) → 403 on adopt (Manage) and on ontology (View).
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", other, `{"genres":[],"kinds":["character"]}`); w.Code != http.StatusForbidden {
		t.Fatalf("non-owner adopt: want 403, got %d (%s)", w.Code, w.Body.String())
	}
	if w := ukReq(t, srv, http.MethodGet, base+"/ontology", other, ""); w.Code != http.StatusForbidden {
		t.Fatalf("non-owner ontology: want 403, got %d", w.Code)
	}
}

func kindByCode(o bookOntologyResp, code string) (bookKindResp, bool) {
	for _, k := range o.Kinds {
		if k.Code == code {
			return k, true
		}
	}
	return bookKindResp{}, false
}
