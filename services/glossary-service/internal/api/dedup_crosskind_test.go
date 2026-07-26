package api

// #43 — cross-kind dedup REMEDIATION. The write-time resolver now prevents new
// same-name/different-kind duplicates (#38/#39), but books extracted before that fix
// carry thousands of them. `POST /internal/books/{book}/dedup-name-variants?cross_kind=true`
// collapses each same-NAME cluster (across kinds) into one winner that keeps ITS kind,
// soft-deleting the losers — reusing the journaled (reversible) merge core.
//
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/textnorm"
)

// postDedup drives the remediation endpoint and returns the decoded response.
func postDedup(t *testing.T, srv *Server, token, bookID string, query string) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/dedup-name-variants"+query, bytes.NewReader([]byte("{}")))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("dedup-name-variants: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var r map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &r); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return r
}

// makeCrossKindDup creates two LIVE entities sharing a name under DIFFERENT kinds —
// the pre-fix duplicate state (the write path now prevents this, so we forge it).
// Returns the bookID. The character entity is given an evidence advantage so the
// richest-wins tie-break makes it the deterministic winner.
func makeCrossKindDup(t *testing.T, srv *Server, token string, pool *pgxpool.Pool, bookID string) {
	t.Helper()
	ctx := context.Background()
	// Two distinct names under two kinds → 2 entities (no write-time dedup).
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": "Li Yun"}},
	})
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "location", "name": "Cloud Peak"}},
	})
	// Forge the dup: rename the location entity to "Li Yun" (same normalized name as the
	// character one). Now both are live, same name, different kinds.
	norm := textnorm.Normalize("Li Yun")
	if _, err := pool.Exec(ctx, `
		UPDATE glossary_entities SET cached_name='Li Yun', normalized_name=$1
		WHERE book_id=$2 AND kind_id=(SELECT book_kind_id FROM book_kinds WHERE book_id=$2 AND code='location')`,
		norm, bookID); err != nil {
		t.Fatalf("forge location dup: %v", err)
	}
	// Give the character entity an evidence advantage so it wins deterministically
	// (richest wins) and the survivor's kind is predictable.
	if _, err := pool.Exec(ctx, `
		UPDATE glossary_entities SET cached_evidence_count=5
		WHERE book_id=$1 AND kind_id=(SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code='character')`,
		bookID); err != nil {
		t.Fatalf("bump character evidence: %v", err)
	}
}

func survivorKind(t *testing.T, pool *pgxpool.Pool, bookID string) string {
	t.Helper()
	var code string
	if err := pool.QueryRow(context.Background(), `
		SELECT bk.code FROM glossary_entities ge
		JOIN book_kinds bk ON bk.book_kind_id = ge.kind_id
		WHERE ge.book_id=$1 AND ge.deleted_at IS NULL`, bookID).Scan(&code); err != nil {
		t.Fatalf("read survivor kind: %v", err)
	}
	return code
}

func TestCrossKindRemediation_CollapsesSameNameDifferentKind(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	makeCrossKindDup(t, srv, token, pool, bookID)
	if n := liveEntityCount(t, pool, ctx, bookID); n != 2 {
		t.Fatalf("setup: want 2 live entities (the forged dup), got %d", n)
	}

	resp := postDedup(t, srv, token, bookID, "?apply=true&cross_kind=true")
	if resp["cross_kind"] != true {
		t.Errorf("response should echo cross_kind=true, got %v", resp["cross_kind"])
	}
	// One cluster, one loser merged.
	if resp["duplicate_group_count"] != float64(1) {
		t.Errorf("want 1 duplicate group, got %v", resp["duplicate_group_count"])
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 1 {
		t.Errorf("after cross-kind remediation: want 1 live entity, got %d", n)
	}
	// The winner keeps ITS kind (character — the richer one). The location loser is gone.
	if code := survivorKind(t, pool, bookID); code != "character" {
		t.Errorf("survivor kind: want character (richest wins, keeps its kind), got %q", code)
	}
	// The loser is SOFT-deleted (reversible), not hard-deleted.
	var softDeleted int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM glossary_entities
		WHERE book_id=$1 AND deleted_at IS NOT NULL`, bookID).Scan(&softDeleted); err != nil {
		t.Fatalf("count soft-deleted: %v", err)
	}
	if softDeleted != 1 {
		t.Errorf("want 1 soft-deleted loser (reversible), got %d", softDeleted)
	}
}

func TestCrossKindRemediation_DefaultModeKeepsKindsSeparate(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	bookID := uuid.NewString()
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	makeCrossKindDup(t, srv, token, pool, bookID)

	// WITHOUT ?cross_kind: the same-kind-only grouping leaves the two different-kind
	// entities in separate groups → nothing merges (no over-reach into the default path).
	resp := postDedup(t, srv, token, bookID, "?apply=true")
	if resp["cross_kind"] != false {
		t.Errorf("response should echo cross_kind=false, got %v", resp["cross_kind"])
	}
	if resp["duplicate_group_count"] != float64(0) {
		t.Errorf("same-kind mode: want 0 duplicate groups, got %v", resp["duplicate_group_count"])
	}
	if n := liveEntityCount(t, pool, ctx, bookID); n != 2 {
		t.Errorf("same-kind mode: want STILL 2 live entities, got %d", n)
	}
}
