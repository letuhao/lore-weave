package api

// 22-A2/A3/A4/A5 DB-gated tests for the public scene READ surface + the A5 parse
// write path. Gated on BOOK_TEST_DATABASE_URL (dbTestServer skips when unset), so
// `go test` stays green on a machine with no DB. These cover the real surfaces the
// unit tests can't: the VIEW-gated routes, keyset paging, the source_scene_id join
// filter (28 AN-5b), and the parse writer now stamping book_id + source_scene_id.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedSceneRows inserts a book + one chapter + n scenes shaped the way the A5
// parse writer now writes them: book_id set, and source_scene_id set on the FIRST
// scene only (an anchored spec scene) — the rest carry NULL ("not yet planned").
// Returns the book, chapter, and the source_scene_id planted on scene[0].
func seedSceneRows(t *testing.T, ctx context.Context, pool *pgxpool.Pool, n int) (bookID, chapterID, sourceSceneID uuid.UUID) {
	t.Helper()
	owner := uuid.New()
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'scenes-read') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',1,'k','active','draft') RETURNING id`, bookID).Scan(&chapterID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	sourceSceneID = uuid.New()
	for i := 0; i < n; i++ {
		var src any
		if i == 0 {
			src = sourceSceneID
		}
		if _, err := pool.Exec(ctx, `
INSERT INTO scenes(chapter_id,book_id,sort_order,path,title,leaf_text,content_hash,source_scene_id)
VALUES($1,$2,$3,$4,$5,$6,$7,$8)`,
			chapterID, bookID, i+1, "/s/"+uuid.NewString(), "Scene "+uuid.NewString()[:4], "prose body here", "h"+uuid.NewString()[:8], src); err != nil {
			t.Fatalf("seed scene %d: %v", i, err)
		}
	}
	return bookID, chapterID, sourceSceneID
}

func sceneGetJSON(t *testing.T, s *Server, userID uuid.UUID, url string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, url, nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, userID))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	var out map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	return rr.Code, out
}

// A2/A3: the book-wide list returns the book's scenes (VIEW-gated) and each row
// carries source_scene_id — the browser's join key.
func TestGetBookScenes_ListAndJoinKey_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	bookID, _, sourceSceneID := seedSceneRows(t, ctx, pool, 3)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	code, out := sceneGetJSON(t, s, uuid.New(), "/v1/books/"+bookID.String()+"/scenes")
	if code != http.StatusOK {
		t.Fatalf("GET /scenes = %d, want 200", code)
	}
	items, _ := out["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("want 3 scenes, got %d (%v)", len(items), out)
	}
	// scene[0] carries the planted source_scene_id; at least one row must expose it.
	var found bool
	for _, it := range items {
		m := it.(map[string]any)
		if m["source_scene_id"] == sourceSceneID.String() {
			found = true
		}
		if _, ok := m["scene_id"]; !ok {
			t.Fatalf("scene row missing scene_id: %v", m)
		}
	}
	if !found {
		t.Fatalf("source_scene_id join key not surfaced in the book-wide list: %v", items)
	}
	if _, ok := out["total"]; !ok {
		t.Fatal("first page must carry total")
	}
}

// A3/AN-5b: the source_scene_id filter resolves a spec scene → its one index row.
func TestGetBookScenes_SourceSceneIDFilter_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	bookID, _, sourceSceneID := seedSceneRows(t, ctx, pool, 4)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	code, out := sceneGetJSON(t, s, uuid.New(),
		"/v1/books/"+bookID.String()+"/scenes?source_scene_id="+sourceSceneID.String())
	if code != http.StatusOK {
		t.Fatalf("filtered GET = %d, want 200", code)
	}
	items, _ := out["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("source_scene_id filter should match exactly the one anchored scene, got %d", len(items))
	}
	if items[0].(map[string]any)["source_scene_id"] != sourceSceneID.String() {
		t.Fatalf("filtered row has wrong source_scene_id: %v", items[0])
	}
}

// A2: the chapter-scoped rail lists the chapter's scenes.
func TestGetChapterScenes_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	bookID, chapterID, _ := seedSceneRows(t, ctx, pool, 2)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	code, out := sceneGetJSON(t, s, uuid.New(),
		"/v1/books/"+bookID.String()+"/chapters/"+chapterID.String()+"/scenes")
	if code != http.StatusOK {
		t.Fatalf("chapter scenes = %d, want 200", code)
	}
	if items, _ := out["items"].([]any); len(items) != 2 {
		t.Fatalf("want 2 chapter scenes, got %d", len(items))
	}
}

// A2: get one scene; a scene_id from another book 404s (scope check, no oracle).
func TestGetBookScene_ScopeCheck_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	bookA, _, _ := seedSceneRows(t, ctx, pool, 1)
	bookB, _, _ := seedSceneRows(t, ctx, pool, 1)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=ANY($1)`, []uuid.UUID{bookA, bookB}) })

	var sceneA uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT id FROM scenes WHERE book_id=$1`, bookA).Scan(&sceneA); err != nil {
		t.Fatalf("scene lookup: %v", err)
	}

	code, out := sceneGetJSON(t, s, uuid.New(), "/v1/books/"+bookA.String()+"/scenes/"+sceneA.String())
	if code != http.StatusOK {
		t.Fatalf("get own scene = %d, want 200", code)
	}
	if out["scene_id"] != sceneA.String() {
		t.Fatalf("wrong scene returned: %v", out)
	}
	// Same scene id, queried under book B → 404 (not found in book).
	code2, _ := sceneGetJSON(t, s, uuid.New(), "/v1/books/"+bookB.String()+"/scenes/"+sceneA.String())
	if code2 != http.StatusNotFound {
		t.Fatalf("cross-book scene get = %d, want 404", code2)
	}
}

// A4: the MCP tools mirror the routes — book_scene_list honours source_scene_id,
// book_scene_get returns the row incl. leaf_text + the join key.
func TestMCPSceneTools_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	bookID, _, sourceSceneID := seedSceneRows(t, ctx, pool, 3)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	// Inject the caller identity the kit middleware would set (SEC-1).
	uctx := identityCtxForTest(t, uuid.New())

	_, listOut, err := s.toolBookSceneList(uctx, nil, sceneListIn{
		BookID:        bookID.String(),
		SourceSceneID: sourceSceneID.String(),
	})
	if err != nil {
		t.Fatalf("book_scene_list: %v", err)
	}
	if len(listOut.Scenes) != 1 {
		t.Fatalf("source_scene_id filter should return 1 scene, got %d", len(listOut.Scenes))
	}
	got := listOut.Scenes[0]
	if got.SourceSceneID == nil || *got.SourceSceneID != sourceSceneID.String() {
		t.Fatalf("book_scene_list lost the source_scene_id join key: %+v", got)
	}

	_, getOut, err := s.toolBookSceneGet(uctx, nil, sceneGetIn{BookID: bookID.String(), SceneID: got.SceneID})
	if err != nil {
		t.Fatalf("book_scene_get: %v", err)
	}
	if getOut.Scene.LeafText == "" {
		t.Fatal("book_scene_get must return leaf_text")
	}
	if getOut.Scene.SourceSceneID == nil || *getOut.Scene.SourceSceneID != sourceSceneID.String() {
		t.Fatalf("book_scene_get lost the join key: %+v", getOut.Scene)
	}
}

// A5: a freshly-parsed .txt import lands every scene with book_id set (closing the
// A1 write-path window) and back-links the anchored scene via source_scene_id
// (SC7). Drives the real processTxtImport against a mock /internal/parse.
func TestProcessTxtImport_SetsBookIDAndSourceSceneID_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()

	anchor := uuid.New() // the data-scene-id the parser recovered for scene-1
	parseSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
  "source_format":"plain","walker_path":"headings","detected_language":"en","book_title":null,
  "parts":[{"sort_order":1,"title":null,"path":"book/part-1","chapters":[
    {"sort_order":1,"title":"Chapter 1","path":"book/part-1/chapter-1","html":"","scenes":[
      {"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"a","content_hash":"h1","source_scene_id":"` + anchor.String() + `"},
      {"sort_order":2,"path":"book/part-1/chapter-1/scene-2","leaf_text":"b","content_hash":"h2"}
    ]},
    {"sort_order":2,"title":"Chapter 2","path":"book/part-1/chapter-2","html":"","scenes":[
      {"sort_order":1,"path":"book/part-1/chapter-2/scene-1","leaf_text":"c","content_hash":"h3"}
    ]}
  ]}]
}`))
	}))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL
	s.cfg.QuotaBytesDefault = 1 << 30 // generous quota so the import isn't 507'd

	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'txt-import') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	req := httptest.NewRequest(http.MethodPost, "/x", nil)
	rr := httptest.NewRecorder()
	s.processTxtImport(rr, req, uuid.New(), owner, bookID, "novel.txt", "Chapter 1\nbody", "en")
	if rr.Code != http.StatusCreated {
		t.Fatalf("processTxtImport = %d, want 201\n%s", rr.Code, rr.Body.String())
	}

	// Every parsed scene carries the chapter's book_id — none NULL (the A1 gap).
	var total, nullBook int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE book_id=$1`, bookID).Scan(&total); err != nil {
		t.Fatalf("count: %v", err)
	}
	if total != 3 {
		t.Fatalf("want 3 scenes with book_id set, got %d", total)
	}
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM scenes s JOIN chapters c ON c.id=s.chapter_id WHERE c.book_id=$1 AND s.book_id IS NULL`,
		bookID).Scan(&nullBook); err != nil {
		t.Fatalf("null count: %v", err)
	}
	if nullBook != 0 {
		t.Fatalf("A5 window not closed: %d freshly-parsed scenes have NULL book_id", nullBook)
	}

	// The anchored scene got its source_scene_id back-link (SC7); the others stay NULL.
	var anchored int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE book_id=$1 AND source_scene_id=$2`, bookID, anchor).Scan(&anchored); err != nil {
		t.Fatalf("anchor count: %v", err)
	}
	if anchored != 1 {
		t.Fatalf("want exactly 1 scene back-linked to the anchor, got %d", anchored)
	}
}
