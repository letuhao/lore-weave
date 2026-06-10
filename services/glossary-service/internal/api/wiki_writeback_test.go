package api

// wiki-llm M5 — tests for the internal AI-writeback + clobber-guard.
// Validation tests run with a nil pool (no DB). The clobber-guard tests require
// GLOSSARY_TEST_DB_URL (openTestDB skips otherwise) and exercise the real SQL:
// write-new, overwrite-ai, overwrite-stub, and suggestion-over-human-edit.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

func newWritebackServer(pool *pgxpool.Pool) *Server {
	return NewServer(pool, &config.Config{JWTSecret: "test_jwt_secret_at_least_32_characters_long"})
}

func postWriteback(t *testing.T, srv *Server, bookID string, body map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	buf, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID+"/wiki/articles", bytes.NewReader(buf))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	return w
}

func validBody() map[string]any {
	return map[string]any{
		"entity_id":         uuid.NewString(),
		"user_id":           uuid.NewString(),
		"body_json":         json.RawMessage(`{"type":"doc","content":[]}`),
		"generation_status": "generated",
		"generated_by":      "ai",
		"source_usage":      []map[string]any{},
	}
}

// ── validation (no DB) ───────────────────────────────────────────────────────

func TestWriteback_InvalidEntityID(t *testing.T) {
	b := validBody()
	b["entity_id"] = "not-a-uuid"
	if w := postWriteback(t, newWritebackServer(nil), uuid.NewString(), b); w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestWriteback_InvalidUserID(t *testing.T) {
	b := validBody()
	b["user_id"] = "nope"
	if w := postWriteback(t, newWritebackServer(nil), uuid.NewString(), b); w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestWriteback_EmptyBodyJSON(t *testing.T) {
	b := validBody()
	delete(b, "body_json")
	if w := postWriteback(t, newWritebackServer(nil), uuid.NewString(), b); w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestWriteback_InvalidGenerationStatus(t *testing.T) {
	b := validBody()
	b["generation_status"] = "totally_published"
	if w := postWriteback(t, newWritebackServer(nil), uuid.NewString(), b); w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

// ── clobber-guard (DB) ───────────────────────────────────────────────────────

type wbFixture struct {
	pool   *pgxpool.Pool
	ctx    context.Context
	srv    *Server
	bookID uuid.UUID
	kindID uuid.UUID
}

func newWbFixture(t *testing.T, suffix string) *wbFixture {
	pool := openTestDB(t)
	runMergeMigrations(t, pool) // chain includes UpWiki (carries the M5 schema)
	ctx := context.Background()
	f := &wbFixture{pool: pool, ctx: ctx, srv: newWritebackServer(pool),
		bookID: uuid.MustParse("019e0000-0000-7000-cccc-" + suffix)}
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&f.kindID)
	if f.kindID == uuid.Nil {
		pool.Exec(ctx, `INSERT INTO entity_kinds(code,name,icon,color,is_default,is_hidden,sort_order)
			SELECT 'character','Character','user','#888888',true,false,0
			WHERE NOT EXISTS (SELECT 1 FROM entity_kinds WHERE code='character')`)
		pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&f.kindID)
	}
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID) })
	return f
}

func (f *wbFixture) seedEntity(t *testing.T) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := f.pool.QueryRow(f.ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		f.bookID, f.kindID,
	).Scan(&id); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	return id
}

// seedArticle inserts a prior article + a latest revision of the given author_type.
func (f *wbFixture) seedArticle(t *testing.T, entityID uuid.UUID, authorType string) uuid.UUID {
	t.Helper()
	var aid uuid.UUID
	if err := f.pool.QueryRow(f.ctx,
		`INSERT INTO wiki_articles(entity_id,book_id,body_json,status) VALUES($1,$2,'{"old":true}','draft') RETURNING article_id`,
		entityID, f.bookID,
	).Scan(&aid); err != nil {
		t.Fatalf("seed article: %v", err)
	}
	if _, err := f.pool.Exec(f.ctx,
		`INSERT INTO wiki_revisions(article_id,version,body_json,author_id,author_type,summary)
		 VALUES($1,1,'{"old":true}',$2,$3,'seed')`,
		aid, uuid.New(), authorType,
	); err != nil {
		t.Fatalf("seed revision: %v", err)
	}
	return aid
}

func (f *wbFixture) body(entityID uuid.UUID) map[string]any {
	return map[string]any{
		"entity_id":         entityID.String(),
		"user_id":           uuid.NewString(),
		"body_json":         json.RawMessage(`{"type":"doc","content":[{"type":"paragraph"}]}`),
		"generation_status": "generated",
		"generated_by":      "model-x",
		"spoiler_horizon":   12,
		"source_usage": []map[string]any{
			{"source_type": "entity", "source_id": entityID.String(), "source_version": "h1"},
			{"source_type": "block", "source_id": "ch1", "source_version": "h2"},
		},
	}
}

func decodeAction(t *testing.T, w *httptest.ResponseRecorder) (string, string) {
	t.Helper()
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Action    string `json:"action"`
		ArticleID string `json:"article_id"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return resp.Action, resp.ArticleID
}

func TestWriteback_WriteNewArticle(t *testing.T) {
	f := newWbFixture(t, "000000000001")
	ent := f.seedEntity(t)
	action, aid := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent)))
	if action != "written" {
		t.Fatalf("expected written, got %q", action)
	}
	// gen columns + 'ai' revision + source_usage + outbox.
	var genStatus, genBy string
	var spoiler int
	f.pool.QueryRow(f.ctx,
		`SELECT generation_status, generated_by, spoiler_horizon FROM wiki_articles WHERE article_id=$1`, aid,
	).Scan(&genStatus, &genBy, &spoiler)
	if genStatus != "generated" || genBy != "model-x" || spoiler != 12 {
		t.Fatalf("gen columns wrong: %s/%s/%d", genStatus, genBy, spoiler)
	}
	var revAuthor string
	f.pool.QueryRow(f.ctx,
		`SELECT author_type FROM wiki_revisions WHERE article_id=$1 ORDER BY version DESC LIMIT 1`, aid,
	).Scan(&revAuthor)
	if revAuthor != "ai" {
		t.Fatalf("expected ai revision, got %q", revAuthor)
	}
	var usageCount, outboxCount int
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM wiki_article_source_usage WHERE article_id=$1`, aid).Scan(&usageCount)
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM outbox_events WHERE event_type='wiki.generated' AND aggregate_id=$1`, aid).Scan(&outboxCount)
	if usageCount != 2 || outboxCount != 1 {
		t.Fatalf("usage=%d outbox=%d", usageCount, outboxCount)
	}
}

func TestWriteback_OverwritesAIDraft(t *testing.T) {
	f := newWbFixture(t, "000000000002")
	ent := f.seedEntity(t)
	f.seedArticle(t, ent, "ai") // a prior AI article — overwritable
	action, aid := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent)))
	if action != "written" {
		t.Fatalf("expected written (over ai draft), got %q", action)
	}
	var body string
	f.pool.QueryRow(f.ctx, `SELECT body_json::text FROM wiki_articles WHERE article_id=$1`, aid).Scan(&body)
	if body == `{"old":true}` {
		t.Fatalf("body not overwritten")
	}
}

func TestWriteback_OverwritesStub(t *testing.T) {
	f := newWbFixture(t, "000000000003")
	ent := f.seedEntity(t)
	f.seedArticle(t, ent, "system") // a deterministic stub — AI may overwrite
	action, _ := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent)))
	if action != "written" {
		t.Fatalf("expected written (over stub), got %q", action)
	}
}

func TestWriteback_SuggestionOverHumanEdit(t *testing.T) {
	f := newWbFixture(t, "000000000004")
	ent := f.seedEntity(t)
	aid := f.seedArticle(t, ent, "owner") // a HUMAN edit — must NOT be clobbered
	action, _ := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent)))
	if action != "suggestion" {
		t.Fatalf("expected suggestion (human edit guarded), got %q", action)
	}
	// the article body is UNCHANGED; a pending suggestion exists.
	var body string
	f.pool.QueryRow(f.ctx, `SELECT body_json::text FROM wiki_articles WHERE article_id=$1`, aid).Scan(&body)
	var bodyMap map[string]any
	if err := json.Unmarshal([]byte(body), &bodyMap); err != nil {
		t.Fatalf("body json: %v", err)
	}
	if bodyMap["old"] != true {
		t.Fatalf("human article was clobbered: %s", body)
	}
	var sugg int
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM wiki_suggestions WHERE article_id=$1 AND status='pending'`, aid).Scan(&sugg)
	if sugg != 1 {
		t.Fatalf("expected 1 pending suggestion, got %d", sugg)
	}
}

func TestWriteback_SuggestionOverUnknownAuthorType(t *testing.T) {
	// Allowlist fail-safe: a non-ai/non-system author_type (e.g. a future
	// human-ish 'editor') must NOT be clobbered — file a suggestion.
	f := newWbFixture(t, "000000000006")
	ent := f.seedEntity(t)
	aid := f.seedArticle(t, ent, "editor") // unknown / future type
	action, _ := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent)))
	if action != "suggestion" {
		t.Fatalf("expected suggestion (unknown author_type guarded), got %q", action)
	}
	var sugg, outbox int
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM wiki_suggestions WHERE article_id=$1`, aid).Scan(&sugg)
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM outbox_events WHERE event_type='wiki.generated' AND aggregate_id=$1`, aid).Scan(&outbox)
	if sugg != 1 || outbox != 1 {
		t.Fatalf("suggestion path: sugg=%d outbox=%d (both should be 1)", sugg, outbox)
	}
}

func TestWriteback_RegenReplacesSourceUsage(t *testing.T) {
	// A second AI write (over an ai draft) REPLACES the source_usage rows, never
	// appends — the §5.1 index reflects the CURRENT generation only.
	f := newWbFixture(t, "000000000007")
	ent := f.seedEntity(t)
	decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent))) // 1st write: 2 usage rows
	_, aid := decodeAction(t, postWriteback(t, f.srv, f.bookID.String(), f.body(ent))) // regen
	var usage int
	f.pool.QueryRow(f.ctx, `SELECT COUNT(*) FROM wiki_article_source_usage WHERE article_id=$1`, aid).Scan(&usage)
	if usage != 2 {
		t.Fatalf("expected 2 usage rows after regen (replaced), got %d", usage)
	}
}

func TestWriteback_EntityNotFound(t *testing.T) {
	f := newWbFixture(t, "000000000005")
	w := postWriteback(t, f.srv, f.bookID.String(), f.body(uuid.New())) // no such entity
	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}
