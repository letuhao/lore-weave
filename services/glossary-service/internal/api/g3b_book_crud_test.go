package api

// G3b — book-tier ontology CRUD. Requires GLOSSARY_TEST_DB_URL.
// Proves: book-native create/patch of genres/kinds/attributes; the book-local FK
// guard on attribute creation (a kind/genre id not of THIS book → 422); set-active
// + set-kind-genres replace-sets reflected in the book-local read; deprecate-on-
// delete cascades (genre→its attrs+links, kind→its attrs+links); and the Manage
// gate (non-owner → 403; an Edit-collaborator can READ /ontology but is 403 on
// every mutation).

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

func mustOntology(t *testing.T, srv *Server, base, userID string) bookOntologyResp {
	t.Helper()
	w := ukReq(t, srv, http.MethodGet, base+"/ontology", userID, "")
	if w.Code != http.StatusOK {
		t.Fatalf("ontology read: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var ont bookOntologyResp
	if err := json.Unmarshal(w.Body.Bytes(), &ont); err != nil {
		t.Fatalf("decode ontology: %v", err)
	}
	return ont
}

func bookGenreByCode(o bookOntologyResp, code string) (bookGenreResp, bool) {
	for _, g := range o.Genres {
		if g.Code == code {
			return g, true
		}
	}
	return bookGenreResp{}, false
}

func hasKindGenre(o bookOntologyResp, kindID, genreID string) bool {
	for _, l := range o.KindGenres {
		if l.KindID == kindID && l.GenreID == genreID {
			return true
		}
	}
	return false
}

func TestBookOntologyCRUD_FullLifecycle(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()
	uid := owner.String()

	// Scaffold from System so universal/xianxia genres + character/unknown kinds exist.
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", uid,
		`{"genres":["xianxia"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	// ── create book-native genre (active by default) ──────────────────────────
	gw := ukReq(t, srv, http.MethodPost, base+"/ontology/genres", uid, `{"name":"Faction"}`)
	if gw.Code != http.StatusCreated {
		t.Fatalf("create genre: want 201, got %d (%s)", gw.Code, gw.Body.String())
	}
	var faction bookGenreResp
	json.Unmarshal(gw.Body.Bytes(), &faction)
	if faction.Code != "faction" || !faction.Active || faction.SourceRef != nil {
		t.Fatalf("book-native genre: code=%q active=%v source_ref=%v (want faction/true/nil)",
			faction.Code, faction.Active, faction.SourceRef)
	}
	// dup code → 409
	if w := ukReq(t, srv, http.MethodPost, base+"/ontology/genres", uid, `{"name":"Faction"}`); w.Code != http.StatusConflict {
		t.Fatalf("dup genre: want 409, got %d", w.Code)
	}
	// create inactive genre
	gw2 := ukReq(t, srv, http.MethodPost, base+"/ontology/genres", uid, `{"name":"Hidden","active":false}`)
	var hidden bookGenreResp
	json.Unmarshal(gw2.Body.Bytes(), &hidden)
	if hidden.Active {
		t.Fatal("genre created with active:false should not be active")
	}

	// patch genre name
	if w := ukReq(t, srv, http.MethodPatch, base+"/ontology/genres/"+faction.GenreID, uid, `{"name":"Faction Realm"}`); w.Code != http.StatusOK {
		t.Fatalf("patch genre: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	// ── create book-native kind ───────────────────────────────────────────────
	kw := ukReq(t, srv, http.MethodPost, base+"/ontology/kinds", uid, `{"name":"Artifact"}`)
	if kw.Code != http.StatusCreated {
		t.Fatalf("create kind: want 201, got %d (%s)", kw.Code, kw.Body.String())
	}
	var artifact bookKindResp
	json.Unmarshal(kw.Body.Bytes(), &artifact)
	if artifact.Code != "artifact" {
		t.Fatalf("kind code = %q, want artifact", artifact.Code)
	}
	// patch kind is_hidden
	if w := ukReq(t, srv, http.MethodPatch, base+"/ontology/kinds/"+artifact.BookKindID, uid, `{"is_hidden":true}`); w.Code != http.StatusOK {
		t.Fatalf("patch kind: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	// ── create book attribute on (artifact × faction) ─────────────────────────
	aBody := `{"kind_id":"` + artifact.BookKindID + `","genre_id":"` + faction.GenreID + `","name":"Origin"}`
	aw := ukReq(t, srv, http.MethodPost, base+"/ontology/attributes", uid, aBody)
	if aw.Code != http.StatusCreated {
		t.Fatalf("create attr: want 201, got %d (%s)", aw.Code, aw.Body.String())
	}
	var origin bookAttrResp
	json.Unmarshal(aw.Body.Bytes(), &origin)
	if origin.KindID != artifact.BookKindID || origin.GenreID != faction.GenreID {
		t.Fatal("attr did not reference the book-local kind/genre ids")
	}
	// patch attr
	if w := ukReq(t, srv, http.MethodPatch, base+"/ontology/attributes/"+origin.AttrID, uid,
		`{"is_required":true,"options":["divine","cursed"]}`); w.Code != http.StatusOK {
		t.Fatalf("patch attr: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	// book-local FK guard: a kind id not of this book → 422
	stray := `{"kind_id":"` + uuid.NewString() + `","genre_id":"` + faction.GenreID + `","name":"Bad"}`
	if w := ukReq(t, srv, http.MethodPost, base+"/ontology/attributes", uid, stray); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("stray kind attr: want 422, got %d (%s)", w.Code, w.Body.String())
	}

	// ── set active-genres (replace-set): universal + faction only ─────────────
	ont := mustOntology(t, srv, base, uid)
	universal, _ := bookGenreByCode(ont, "universal")
	putActive := `{"genre_ids":["` + universal.GenreID + `","` + faction.GenreID + `"]}`
	if w := ukReq(t, srv, http.MethodPut, base+"/ontology/active-genres", uid, putActive); w.Code != http.StatusOK {
		t.Fatalf("set active: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	ont = mustOntology(t, srv, base, uid)
	if xn, _ := bookGenreByCode(ont, "xianxia"); xn.Active {
		t.Fatal("xianxia should be inactive after replace-set")
	}
	if u, _ := bookGenreByCode(ont, "universal"); !u.Active {
		t.Fatal("universal should be active after replace-set")
	}

	// ── set kind-genres (matrix row) for artifact → faction ───────────────────
	if w := ukReq(t, srv, http.MethodPut, base+"/ontology/kinds/"+artifact.BookKindID+"/genres", uid,
		`{"genre_ids":["`+faction.GenreID+`"]}`); w.Code != http.StatusOK {
		t.Fatalf("set kind-genres: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	ont = mustOntology(t, srv, base, uid)
	if !hasKindGenre(ont, artifact.BookKindID, faction.GenreID) {
		t.Fatal("artifact→faction link missing after set kind-genres")
	}

	// ── deprecate attribute → gone from ontology ──────────────────────────────
	if w := ukReq(t, srv, http.MethodDelete, base+"/ontology/attributes/"+origin.AttrID, uid, ""); w.Code != http.StatusNoContent {
		t.Fatalf("delete attr: want 204, got %d", w.Code)
	}
	ont = mustOntology(t, srv, base, uid)
	for _, a := range ont.Attributes {
		if a.AttrID == origin.AttrID {
			t.Fatal("deprecated attribute still in ontology")
		}
	}

	// ── deprecate genre cascades: attr on it + its links vanish ───────────────
	// Add a fresh attr on faction to prove cascade.
	caBody := `{"kind_id":"` + artifact.BookKindID + `","genre_id":"` + faction.GenreID + `","name":"Lineage"}`
	cw := ukReq(t, srv, http.MethodPost, base+"/ontology/attributes", uid, caBody)
	var lineage bookAttrResp
	json.Unmarshal(cw.Body.Bytes(), &lineage)

	if w := ukReq(t, srv, http.MethodDelete, base+"/ontology/genres/"+faction.GenreID, uid, ""); w.Code != http.StatusNoContent {
		t.Fatalf("delete genre: want 204, got %d (%s)", w.Code, w.Body.String())
	}
	ont = mustOntology(t, srv, base, uid)
	if _, ok := bookGenreByCode(ont, "faction"); ok {
		t.Fatal("deprecated genre still in ontology")
	}
	for _, a := range ont.Attributes {
		if a.AttrID == lineage.AttrID {
			t.Fatal("attr under deprecated genre not cascaded")
		}
	}
	if hasKindGenre(ont, artifact.BookKindID, faction.GenreID) {
		t.Fatal("kind-genre link to deprecated genre not removed")
	}

	// ── deprecate kind → gone ─────────────────────────────────────────────────
	if w := ukReq(t, srv, http.MethodDelete, base+"/ontology/kinds/"+artifact.BookKindID, uid, ""); w.Code != http.StatusNoContent {
		t.Fatalf("delete kind: want 204, got %d", w.Code)
	}
	ont = mustOntology(t, srv, base, uid)
	if _, ok := kindByCode(ont, "artifact"); ok {
		t.Fatal("deprecated kind still in ontology")
	}
}

func TestBookOntologyCRUD_NonOwnerForbidden(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()
	other := uuid.NewString()

	cases := []struct {
		method, path, body string
	}{
		{http.MethodPost, "/ontology/genres", `{"name":"X"}`},
		{http.MethodPost, "/ontology/kinds", `{"name":"X"}`},
		{http.MethodPut, "/ontology/active-genres", `{"genre_ids":[]}`},
		{http.MethodPost, "/ontology/attributes", `{"kind_id":"` + uuid.NewString() + `","genre_id":"` + uuid.NewString() + `","name":"X"}`},
		{http.MethodDelete, "/ontology/genres/" + uuid.NewString(), ""},
	}
	for _, c := range cases {
		if w := ukReq(t, srv, c.method, base+c.path, other, c.body); w.Code != http.StatusForbidden {
			t.Fatalf("non-owner %s %s: want 403, got %d (%s)", c.method, c.path, w.Code, w.Body.String())
		}
	}
}

// newGrantServer maps owner→owner and a single collaborator→collabLevel; all others→none.
func newGrantServer(t *testing.T, pool *pgxpool.Pool, book, owner, collab uuid.UUID, collabLevel string) *Server {
	t.Helper()
	h := func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasSuffix(r.URL.Path, "/access") {
			lvl := "none"
			switch r.URL.Query().Get("user_id") {
			case owner.String():
				lvl = "owner"
			case collab.String():
				lvl = collabLevel
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": lvl, "lifecycle_state": "active"})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"book_id": book.String(), "owner_user_id": owner.String()})
	}
	ts := httptest.NewServer(http.HandlerFunc(h))
	t.Cleanup(ts.Close)
	return NewServer(pool, &config.Config{
		JWTSecret: exportTestSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok",
	})
}

// An Edit collaborator can READ the ontology (View) but every WRITE needs Manage.
func TestBookOntologyCRUD_EditCollaboratorDeniedManage(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner, book, collab := uuid.New(), uuid.New(), uuid.New()
	srv := newGrantServer(t, pool, book, owner, collab, "edit")
	base := "/v1/glossary/books/" + book.String()

	// owner scaffolds
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":[],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	// edit collaborator: read OK
	if w := ukReq(t, srv, http.MethodGet, base+"/ontology", collab.String(), ""); w.Code != http.StatusOK {
		t.Fatalf("edit collaborator ontology read: want 200, got %d", w.Code)
	}
	// edit collaborator: writes denied (Manage required)
	if w := ukReq(t, srv, http.MethodPost, base+"/ontology/genres", collab.String(), `{"name":"X"}`); w.Code != http.StatusForbidden {
		t.Fatalf("edit collaborator create genre: want 403, got %d (%s)", w.Code, w.Body.String())
	}
	if w := ukReq(t, srv, http.MethodPut, base+"/ontology/active-genres", collab.String(), `{"genre_ids":[]}`); w.Code != http.StatusForbidden {
		t.Fatalf("edit collaborator set-active: want 403, got %d", w.Code)
	}
}
