package api

// G6/D2 — per-entity genre override. Requires GLOSSARY_TEST_DB_URL.
// Proves: a fresh entity uses the book default (no override); a PUT replaces the set
// and always includes universal (O4); a non-book genre → 422; a missing entity → 404.

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestEntityGenres_SetGetAndGuards(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	ctx := context.Background()
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	adoptTestBook(t, pool, book)
	base := "/v1/glossary/books/" + book.String()

	// Create an entity on the book 'character' kind.
	bk := bookKindID(t, pool, book, "character")
	cw := ukReq(t, srv, http.MethodPost, base+"/entities", owner.String(), `{"kind_id":"`+bk.String()+`"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("create entity: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var created struct {
		EntityID string `json:"entity_id"`
	}
	if err := json.Unmarshal(cw.Body.Bytes(), &created); err != nil || created.EntityID == "" {
		t.Fatalf("decode entity: %v (%s)", err, cw.Body.String())
	}
	gbase := base + "/entities/" + created.EntityID + "/genres"

	// Fresh entity → no override, uses the book default.
	gw := ukReq(t, srv, http.MethodGet, gbase, owner.String(), "")
	if gw.Code != http.StatusOK {
		t.Fatalf("get genres: want 200, got %d (%s)", gw.Code, gw.Body.String())
	}
	var got entityGenresResp
	_ = json.Unmarshal(gw.Body.Bytes(), &got)
	if !got.UsesBookDefault || len(got.GenreIDs) != 0 {
		t.Fatalf("fresh entity: want uses_book_default + empty, got %+v", got)
	}

	// Look up two book genre ids (fantasy + universal) to set.
	var fantasyID, universalID string
	if err := pool.QueryRow(ctx, `SELECT genre_id::text FROM book_genres WHERE book_id=$1 AND code='fantasy'`, book).Scan(&fantasyID); err != nil {
		t.Fatalf("fantasy genre: %v", err)
	}
	if err := pool.QueryRow(ctx, `SELECT genre_id::text FROM book_genres WHERE book_id=$1 AND code='universal'`, book).Scan(&universalID); err != nil {
		t.Fatalf("universal genre: %v", err)
	}

	// PUT only fantasy → universal auto-included (O4), uses_book_default=false.
	pw := ukReq(t, srv, http.MethodPut, gbase, owner.String(), `{"genre_ids":["`+fantasyID+`"]}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("set genres: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	var set entityGenresResp
	_ = json.Unmarshal(pw.Body.Bytes(), &set)
	idset := map[string]bool{}
	for _, id := range set.GenreIDs {
		idset[id] = true
	}
	if set.UsesBookDefault || !idset[fantasyID] || !idset[universalID] {
		t.Fatalf("set genres: want fantasy+universal, got %+v", set)
	}

	// Persisted: GET reflects the override.
	gw2 := ukReq(t, srv, http.MethodGet, gbase, owner.String(), "")
	var got2 entityGenresResp
	_ = json.Unmarshal(gw2.Body.Bytes(), &got2)
	if got2.UsesBookDefault || len(got2.GenreIDs) != 2 {
		t.Fatalf("after set: want 2 ids, got %+v", got2)
	}

	// A non-book genre id → 422 (tenant boundary).
	bw := ukReq(t, srv, http.MethodPut, gbase, owner.String(), `{"genre_ids":["`+uuid.NewString()+`"]}`)
	if bw.Code != http.StatusUnprocessableEntity {
		t.Fatalf("foreign genre: want 422, got %d (%s)", bw.Code, bw.Body.String())
	}

	// A missing entity id → 404.
	mw := ukReq(t, srv, http.MethodPut, base+"/entities/"+uuid.NewString()+"/genres", owner.String(),
		`{"genre_ids":["`+fantasyID+`"]}`)
	if mw.Code != http.StatusNotFound {
		t.Fatalf("missing entity: want 404, got %d", mw.Code)
	}
}
