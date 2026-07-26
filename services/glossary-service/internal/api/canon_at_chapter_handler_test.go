package api

// Tests for the M6 public "Canon at chapter N" read surface +
// the M7 chapter_entity_links.mention_count upsert/read path.
//
// Unit auth tests (no DB) run always.
// DB integration tests require GLOSSARY_TEST_DB_URL and skip otherwise (openTestDB).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// migrateUpOutbox runs the (idempotent) outbox migration. runK2aMigrations omits it,
// but the extract-entities writeback emits an outbox event, so an extract-driven DB
// test needs the table present on a fresh DB.
func migrateUpOutbox(t *testing.T, pool *pgxpool.Pool) error {
	t.Helper()
	return migrate.UpOutbox(context.Background(), pool)
}

// ── unit tests (no DB) ──────────────────────────────────────────────

// TestCanonAtChapter_RequireAuth — both new public routes reject a missing/invalid
// Bearer with 401 before any grant/DB work (mirrors listChapterLinks' guard order).
func TestCanonAtChapter_RequireAuth(t *testing.T) {
	srv := newExportServer(t, nil)
	book := "00000000-0000-0000-0000-000000000001"
	chap := "00000000-0000-0000-0000-000000000002"
	cases := []struct{ name, path string }{
		{"known-entities", "/v1/glossary/books/" + book + "/known-entities"},
		{"chapter-entities", "/v1/glossary/books/" + book + "/chapter-entities?chapter_id=" + chap},
	}
	for _, tc := range cases {
		t.Run(tc.name+"/no-token", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tc.path, nil)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("no token: want 401, got %d", w.Code)
			}
		})
		t.Run(tc.name+"/bad-token", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tc.path, nil)
			req.Header.Set("Authorization", "Bearer not.a.valid.token")
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("bad token: want 401, got %d", w.Code)
			}
		})
	}
}

// TestChapterEntities_BadChapterID — a valid token but a malformed chapter_id is a 400.
// (Grant resolves first; with a nil grant client requireGrant fails closed to 503, so we
// stub a View grant to reach the param-parse path.)
func TestChapterEntities_BadChapterID(t *testing.T) {
	srv := newExportServer(t, nil)
	grantStub := stubViewAccess(t)
	srv.cfg.BookServiceURL = grantStub.URL
	srv.cfg.InternalServiceToken = "tkn"
	srv.grantClient = buildGrantClient(grantStub.URL, "tkn")

	book := uuid.NewString()
	token := makeExportToken(t, uuid.NewString())
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+book+"/chapter-entities?chapter_id=not-a-uuid", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad chapter_id: want 400, got %d body=%s", w.Code, w.Body.String())
	}
}

// stubViewAccess returns a book-service stub that grants VIEW + an active book on /access
// and returns an empty chapter list on /chapters (so coverage degrades, never 503s).
func stubViewAccess(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.Contains(r.URL.Path, "/access"):
			_, _ = w.Write([]byte(`{"grant_level":"view","lifecycle_state":"active"}`))
		case strings.Contains(r.URL.Path, "/chapters"):
			_, _ = w.Write([]byte(`{"items":[]}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

// ── DB integration tests ────────────────────────────────────────────

// stubViewAccessWithChapters grants VIEW + returns `n` chapters (so coverage_pct has a
// real denominator).
func stubViewAccessWithChapters(t *testing.T, n int) *httptest.Server {
	t.Helper()
	items := make([]map[string]any, 0, n)
	for i := 0; i < n; i++ {
		items = append(items, map[string]any{
			"chapter_id": uuid.NewString(), "title": nil, "sort_order": i,
		})
	}
	body, _ := json.Marshal(map[string]any{"items": items})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.Contains(r.URL.Path, "/access"):
			_, _ = w.Write([]byte(`{"grant_level":"view","lifecycle_state":"active"}`))
		case strings.Contains(r.URL.Path, "/chapters"):
			_, _ = w.Write(body)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

// TestMentionCount_UpsertRoundTrip — the M7 producer field (chapterLinkIn.mention_count)
// persists on the extract-entities upsert and the ON CONFLICT path OVERWRITES it on a
// re-extract (recount lands the fresh value).
func TestMentionCount_UpsertRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	// The extract writeback emits an outbox event — needs the outbox table. runK2aMigrations
	// doesn't run UpOutbox (the shared CI DB has it from other suites); add it idempotently so
	// this test is self-sufficient on a fresh DB.
	if err := migrateUpOutbox(t, pool); err != nil {
		t.Fatalf("UpOutbox: %v", err)
	}

	bookID := "00000000-0000-0000-0001-0000000a7010"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	body := map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": chap, "chapter_index": 1, "mention_count": 7},
			}},
		},
	}
	if r := postExtract(t, srv, token, bookID, body); r["created"] != float64(1) {
		t.Fatalf("first apply: want created=1, got %v", r)
	}

	got := mentionCountFor(t, pool, ctx, bookID, chap)
	if got != 7 {
		t.Fatalf("mention_count after first extract: want 7, got %d", got)
	}

	// Re-extract the same (entity, chapter) with a different count → ON CONFLICT overwrites.
	body2 := map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": chap, "chapter_index": 1, "mention_count": 12},
			}},
		},
	}
	postExtract(t, srv, token, bookID, body2)
	if got := mentionCountFor(t, pool, ctx, bookID, chap); got != 12 {
		t.Fatalf("mention_count after re-extract: want 12 (overwritten), got %d", got)
	}

	// Omitting mention_count (legacy producer) defaults to 0 on a fresh (entity,chapter).
	chap2 := uuid.NewString()
	body3 := map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "青檀", "chapter_links": []map[string]any{
				{"chapter_id": chap2, "chapter_index": 2},
			}},
		},
	}
	postExtract(t, srv, token, bookID, body3)
	if got := mentionCountFor(t, pool, ctx, bookID, chap2); got != 0 {
		t.Fatalf("mention_count default when omitted: want 0, got %d", got)
	}
}

// mentionCountFor reads the mention_count on the single chapter link for a book+chapter.
func mentionCountFor(t *testing.T, pool *pgxpool.Pool, ctx context.Context, bookID, chapterID string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(ctx, `
		SELECT cel.mention_count
		FROM chapter_entity_links cel
		JOIN glossary_entities e ON e.entity_id = cel.entity_id
		WHERE e.book_id=$1 AND cel.chapter_id=$2`, bookID, chapterID).Scan(&n); err != nil {
		t.Fatalf("read mention_count: %v", err)
	}
	return n
}

// TestPublicChapterEntities_DB — the chapter-entities route returns the entities linked to
// a chapter with their relevance + mention_count, View-grant gated, book-scoped.
func TestPublicChapterEntities_DB(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	if err := migrateUpOutbox(t, pool); err != nil {
		t.Fatalf("UpOutbox: %v", err)
	}

	bookID := "00000000-0000-0000-0001-0000000a7020"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, intTok := newEntitiesListServer(t)
	srv.pool = pool

	chap := uuid.NewString()
	body := map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": chap, "chapter_index": 3, "relevance": "major", "mention_count": 9},
			}},
			{"kind_code": "character", "name": "青檀", "chapter_links": []map[string]any{
				{"chapter_id": chap, "chapter_index": 3, "relevance": "mentioned", "mention_count": 2},
			}},
		},
	}
	postExtract(t, srv, intTok, bookID, body)

	// Now the public route — wire a View grant.
	grantStub := stubViewAccessWithChapters(t, 10)
	srv.cfg.BookServiceURL = grantStub.URL
	srv.cfg.InternalServiceToken = "ptk"
	srv.grantClient = buildGrantClient(grantStub.URL, "ptk")

	token := makeExportToken(t, uuid.NewString())
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+bookID+"/chapter-entities?chapter_id="+chap, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("chapter-entities: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var out []chapterEntityOut
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 chapter entities, got %d (%+v)", len(out), out)
	}
	// major sorts before mentioned.
	if out[0].Relevance != "major" || out[0].MentionCount != 9 {
		t.Errorf("first entity: want {major,9}, got {%s,%d}", out[0].Relevance, out[0].MentionCount)
	}
	if out[1].Relevance != "mentioned" || out[1].MentionCount != 2 {
		t.Errorf("second entity: want {mentioned,2}, got {%s,%d}", out[1].Relevance, out[1].MentionCount)
	}
	if out[0].ChapterIndex == nil || *out[0].ChapterIndex != 3 {
		t.Errorf("chapter_index: want 3, got %v", out[0].ChapterIndex)
	}
	if out[0].Name == "" || out[0].KindCode == "" {
		t.Errorf("name/kind_code must be populated, got %+v", out[0])
	}
}

// TestPublicKnownEntities_DB — known-entities windows frequency to before_chapter_index,
// honors min_frequency, and folds in first/last/coverage.
func TestPublicKnownEntities_DB(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	if err := migrateUpOutbox(t, pool); err != nil {
		t.Fatalf("UpOutbox: %v", err)
	}

	bookID := "00000000-0000-0000-0001-0000000a7030"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() { cleanupExtractBook(pool, bookID) })

	srv, intTok := newEntitiesListServer(t)
	srv.pool = pool

	// 林动 appears in chapters 1 and 2 (freq 2); 青檀 appears only in chapter 5 (freq 1).
	ch1, ch2, ch5 := uuid.NewString(), uuid.NewString(), uuid.NewString()
	postExtract(t, srv, intTok, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": ch1, "chapter_index": 1, "mention_count": 4},
			}},
		},
	})
	postExtract(t, srv, intTok, bookID, map[string]any{
		"source_language": "zh",
		"entities": []map[string]any{
			{"kind_code": "character", "name": "林动", "chapter_links": []map[string]any{
				{"chapter_id": ch2, "chapter_index": 2, "mention_count": 3},
			}},
			{"kind_code": "character", "name": "青檀", "chapter_links": []map[string]any{
				{"chapter_id": ch5, "chapter_index": 5, "mention_count": 1},
			}},
		},
	})

	grantStub := stubViewAccessWithChapters(t, 10)
	srv.cfg.BookServiceURL = grantStub.URL
	srv.cfg.InternalServiceToken = "ptk"
	srv.grantClient = buildGrantClient(grantStub.URL, "ptk")
	token := makeExportToken(t, uuid.NewString())

	// min_frequency=2 → only 林动 qualifies (2 distinct chapters).
	out := getKnown(t, srv, token, bookID, "?min_frequency=2")
	if len(out) != 1 {
		t.Fatalf("min_frequency=2: want 1 entity, got %d (%+v)", len(out), out)
	}
	e := out[0]
	if e.Frequency != 2 {
		t.Errorf("frequency: want 2, got %d", e.Frequency)
	}
	if e.FirstChapterIndex == nil || *e.FirstChapterIndex != 1 ||
		e.LastChapterIndex == nil || *e.LastChapterIndex != 2 {
		t.Errorf("first/last: want 1/2, got %v/%v", e.FirstChapterIndex, e.LastChapterIndex)
	}
	if e.CoveragePct <= 0 || e.CoveragePct > 1 {
		t.Errorf("coverage_pct out of (0,1]: %v", e.CoveragePct)
	}

	// before_chapter_index=2 windows OUT chapter 2 (links strictly < 2) → 林动 freq drops to
	// 1, so min_frequency=2 yields nothing.
	out2 := getKnown(t, srv, token, bookID, "?min_frequency=2&before_chapter_index=2")
	if len(out2) != 0 {
		t.Errorf("windowed before_chapter_index=2 w/ min_freq=2: want 0, got %d (%+v)", len(out2), out2)
	}

	// min_frequency=1 → both entities.
	out3 := getKnown(t, srv, token, bookID, "?min_frequency=1")
	if len(out3) != 2 {
		t.Errorf("min_frequency=1: want 2 entities, got %d", len(out3))
	}
}

func getKnown(t *testing.T, srv *Server, token, bookID, query string) []knownEntityOut {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+bookID+"/known-entities"+query, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("known-entities%s: want 200, got %d body=%s", query, w.Code, w.Body.String())
	}
	var out []knownEntityOut
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return out
}
