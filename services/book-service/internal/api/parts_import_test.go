package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/loreweave/book-service/internal/config"
)

// C-merge — groupImportedChaptersIntoParts creates a composition part (stubbed) per source part and
// homes its chapters via chapters.structure_node_id. Best-effort: a composition failure leaves them flat.
func TestGroupImportedChaptersIntoParts_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	ch1 := seedPartsChapter(t, ctx, pool, bookID, 1, nil)
	ch2 := seedPartsChapter(t, ctx, pool, bookID, 2, nil)

	partID := uuid.New()
	var gotTitle string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body struct{ Title string `json:"title"` }
		_ = json.NewDecoder(r.Body).Decode(&body)
		gotTitle = body.Title
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]any{"part_id": partID.String()})
	}))
	defer srv.Close()
	s.cfg = &config.Config{CompositionServiceURL: srv.URL}

	s.groupImportedChaptersIntoParts(ctx, "Bearer x", bookID.String(), []string{"Part One"}, map[int][]uuid.UUID{0: {ch1, ch2}})

	if gotTitle != "Part One" {
		t.Fatalf("composition got title %q, want Part One", gotTitle)
	}
	for _, ch := range []uuid.UUID{ch1, ch2} {
		var snid *uuid.UUID
		_ = pool.QueryRow(ctx, `SELECT structure_node_id FROM chapters WHERE id=$1`, ch).Scan(&snid)
		if snid == nil || *snid != partID {
			t.Fatalf("chapter %s structure_node_id = %v, want %s", ch, snid, partID)
		}
	}
}

// A composition failure (non-2xx) must NOT touch the chapters — they stay flat, import already succeeded.
func TestGroupImportedChaptersIntoParts_BestEffort_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	ch := seedPartsChapter(t, ctx, pool, bookID, 1, nil)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(500) }))
	defer srv.Close()
	s.cfg = &config.Config{CompositionServiceURL: srv.URL}

	s.groupImportedChaptersIntoParts(ctx, "Bearer x", bookID.String(), []string{"P"}, map[int][]uuid.UUID{0: {ch}})

	var snid *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT structure_node_id FROM chapters WHERE id=$1`, ch).Scan(&snid)
	if snid != nil {
		t.Fatalf("structure_node_id = %v, want NULL (flat) on composition failure", snid)
	}
}
