package tasks

// 26 IX-12 — DB-gated test for writeBackSceneLinks' UPDATE, the load-bearing IX-5 rule-1 guard
// ("a parser-recovered anchor set at INSERT WINS over the decompile map, never clobbered"). The
// materialize_client_test.go covers only the HTTP surface; this pins the actual write against real
// Postgres — the `AND source_scene_id IS NULL` predicate + idempotency. Requires BOOK_TEST_DATABASE_URL
// (the book DB), else skipped; matches book-service's *_db_test.go gating.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func bookTestPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("BOOK_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("set BOOK_TEST_DATABASE_URL to a book DB to run the IX-12 write-back DB test")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect book DB: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// seedScene inserts one scenes row (book+chapter FKs must already exist). sourceSceneID nil → NULL.
func seedScene(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID, chapterID uuid.UUID, sortOrder int, sourceSceneID *uuid.UUID) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id)
		 VALUES($1,$2,$3,$4,'x','h',$5) RETURNING id`,
		chapterID, bookID, sortOrder, "/p", sourceSceneID).Scan(&id); err != nil {
		t.Fatalf("seed scene (sort=%d): %v", sortOrder, err)
	}
	return id
}

func sceneSourceID(t *testing.T, ctx context.Context, pool *pgxpool.Pool, id uuid.UUID) *uuid.UUID {
	t.Helper()
	var out *uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT source_scene_id FROM scenes WHERE id=$1`, id).Scan(&out); err != nil {
		t.Fatalf("read source_scene_id: %v", err)
	}
	return out
}

// mappingServer returns a composition materialize-scenes stub that maps every (chapter, sort) to a node.
func mappingServer(t *testing.T, chapterID uuid.UUID, sorts map[int]uuid.UUID) *httptest.Server {
	t.Helper()
	body := `{"work_resolved":true,"created":1,"matched":0,"mappings":[`
	first := true
	for so, node := range sorts {
		if !first {
			body += ","
		}
		first = false
		body += `{"chapter_id":"` + chapterID.String() + `","sort_order":` + strconv.Itoa(so) + `,"outline_node_id":"` + node.String() + `"}`
	}
	body += `]}`
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
}

func TestWriteBackSceneLinks_RecoveredAnchorWins_AndIdempotent(t *testing.T) {
	pool := bookTestPool(t)
	ctx := context.Background()

	// Seed a book + chapter (FK parents) then two scenes: one with a recovered anchor already set,
	// one with a NULL back-link.
	var bookID, chapterID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'ix12') RETURNING id`, uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) }) // CASCADE clears chapters+scenes
	if err := pool.QueryRow(ctx,
		`INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
		 VALUES($1,'c.txt','en','text/plain',1,'k','active','published') RETURNING id`, bookID).Scan(&chapterID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}

	recovered := uuid.New() // the parser-recovered anchor already on scene 0 (must NOT be clobbered)
	anchoredScene := seedScene(t, ctx, pool, bookID, chapterID, 0, &recovered)
	nullScene := seedScene(t, ctx, pool, bookID, chapterID, 1, nil)

	// The decompile map targets BOTH leaves with fresh node ids.
	nodeForAnchored, nodeForNull := uuid.New(), uuid.New()
	srv := mappingServer(t, chapterID, map[int]uuid.UUID{0: nodeForAnchored, 1: nodeForNull})
	defer srv.Close()

	proc := &ImportProcessor{BookDB: pool, materializeClient: NewMaterializeClient(srv.URL, "tok")}
	proc.writeBackSceneLinks(ctx, bookID.String(), uuid.New().String())

	// IX-5 r1: the recovered anchor is UNTOUCHED (the WHERE source_scene_id IS NULL excluded it).
	if got := sceneSourceID(t, ctx, pool, anchoredScene); got == nil || *got != recovered {
		t.Fatalf("recovered anchor was clobbered: want %s, got %v", recovered, got)
	}
	// The NULL leaf got the decompile map's node id.
	if got := sceneSourceID(t, ctx, pool, nullScene); got == nil || *got != nodeForNull {
		t.Fatalf("null scene not written: want %s, got %v", nodeForNull, got)
	}

	// Idempotent: a second run re-writes the same id and still never touches the anchored scene.
	proc.writeBackSceneLinks(ctx, bookID.String(), uuid.New().String())
	if got := sceneSourceID(t, ctx, pool, anchoredScene); got == nil || *got != recovered {
		t.Fatalf("re-run clobbered the recovered anchor: got %v", got)
	}
	if got := sceneSourceID(t, ctx, pool, nullScene); got == nil || *got != nodeForNull {
		t.Fatalf("re-run changed the written id: got %v", got)
	}
}
