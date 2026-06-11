package api

// wiki-llm Phase-2 — tests for the recipe-drift sweep (DB-integration via
// newMergeFixture; needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func setProvenanceVersions(t *testing.T, f *mergeFixture, articleID uuid.UUID, promptV, pipelineV string) {
	t.Helper()
	if _, err := f.pool.Exec(f.ctx,
		`UPDATE wiki_articles
		   SET generation_provenance = jsonb_build_object('build_inputs',
		         jsonb_build_object('prompt_version',$2::text,'pipeline_version',$3::text))
		 WHERE article_id=$1`,
		articleID, promptV, pipelineV,
	); err != nil {
		t.Fatalf("set provenance: %v", err)
	}
}

func pendingStaleness(t *testing.T, f *mergeFixture, articleID uuid.UUID, reason string) int {
	t.Helper()
	var n int
	f.pool.QueryRow(f.ctx,
		`SELECT count(*) FROM wiki_staleness WHERE article_id=$1 AND reason_code=$2 AND status='pending'`,
		articleID, reason).Scan(&n)
	return n
}

func TestSweepRecipeDrift_FlagsLaggardsAndIsIdempotent(t *testing.T) {
	f := newMergeFixture(t, "00000000d0e1")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET generation_status='generated' WHERE article_id=$1`, art)
	setProvenanceVersions(t, f, art, "v1", "p1")

	// Current prompt bumped to v2 → the article (built on v1) is recipe-drifted.
	n, err := f.srv.sweepRecipeDrift(context.Background(), f.bookID, "v2", "p1")
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if n != 1 {
		t.Fatalf("want 1 flagged, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "recipe_drift"); got != 1 {
		t.Fatalf("want 1 recipe_drift row, got %d", got)
	}
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if !stale {
		t.Fatal("article should be flagged is_knowledge_stale")
	}

	// Re-sweep with the same current versions → idempotent (no duplicate row).
	n2, _ := f.srv.sweepRecipeDrift(context.Background(), f.bookID, "v2", "p1")
	if n2 != 0 {
		t.Fatalf("re-sweep should insert 0, got %d", n2)
	}
	if got := pendingStaleness(t, f, art, "recipe_drift"); got != 1 {
		t.Fatalf("still want 1 recipe_drift row, got %d", got)
	}
}

func TestSweepRecipeDrift_NoDriftNoRow(t *testing.T) {
	f := newMergeFixture(t, "00000000d0e2")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET generation_status='generated' WHERE article_id=$1`, art)
	setProvenanceVersions(t, f, art, "v2", "p1")

	// Current == stored → no drift, no staleness.
	n, _ := f.srv.sweepRecipeDrift(context.Background(), f.bookID, "v2", "p1")
	if n != 0 {
		t.Fatalf("matching versions should flag 0, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "recipe_drift"); got != 0 {
		t.Fatalf("want 0 recipe_drift rows, got %d", got)
	}
}

// ── resolve-on-write (F3 fix) ─────────────────────────────────────────────────

func TestWriteback_ResolvesPendingStaleness(t *testing.T) {
	f := newWbFixture(t, "00000000d0f1")
	entity := f.seedEntity(t)
	art := f.seedArticle(t, entity, "ai") // ai-authored → the AI overwrite path runs
	// a pending staleness row (as if a source had changed) + the flag
	if _, err := f.pool.Exec(f.ctx,
		`INSERT INTO wiki_staleness (article_id, reason_code, source_ref, severity)
		 VALUES ($1,'entity_changed', jsonb_build_object('source_id',$2::text), 'content')`,
		art, entity.String()); err != nil {
		t.Fatalf("seed staleness: %v", err)
	}
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	body := validBody()
	body["entity_id"] = entity.String()
	if w := postWriteback(t, f.srv, f.bookID.String(), body); w.Code != http.StatusOK {
		t.Fatalf("writeback: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	// the regen supersedes the staleness: ledger row resolved + flag cleared.
	var status string
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT status FROM wiki_staleness WHERE article_id=$1`, art).Scan(&status)
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if status != "regenerated" {
		t.Fatalf("staleness should be regenerated after a write, got %q", status)
	}
	if stale {
		t.Fatal("is_knowledge_stale should be cleared after a write")
	}
}

// ── feed + dismiss (JWT + owner-gated) ────────────────────────────────────────

func seedStalenessRow(t *testing.T, f *mergeFixture, articleID uuid.UUID, reason, severity string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := f.pool.QueryRow(f.ctx,
		`INSERT INTO wiki_staleness (article_id, reason_code, source_ref, severity)
		 VALUES ($1,$2,'{}',$3) RETURNING staleness_id`,
		articleID, reason, severity).Scan(&id); err != nil {
		t.Fatalf("seed staleness row: %v", err)
	}
	return id
}

func getFeed(t *testing.T, f *mergeFixture, owner string) []wikiStalenessRow {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness", nil)
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("feed: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Items []wikiStalenessRow `json:"items"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	return resp.Items
}

func TestStalenessFeedAndDismiss(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f2")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	// two pending rows of different severity → hard sorts before content.
	contentID := seedStalenessRow(t, f, art, "chapter_regrounded", "content")
	hardID := seedStalenessRow(t, f, art, "citation_broken", "hard")
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	feed := getFeed(t, f, owner)
	if len(feed) != 2 {
		t.Fatalf("want 2 feed rows, got %d", len(feed))
	}
	if feed[0].Severity != "hard" {
		t.Fatalf("hard severity should sort first, got %q", feed[0].Severity)
	}
	if feed[0].DisplayName != "Mina" {
		t.Fatalf("feed should carry the article name, got %q", feed[0].DisplayName)
	}

	// dismiss the hard one → resolves without spend.
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/"+hardID.String()+"/dismiss", nil)
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("dismiss: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if got := getFeed(t, f, owner); len(got) != 1 {
		t.Fatalf("feed should have 1 row after dismiss, got %d", len(got))
	}
	// one pending row remains → the article is still flagged outdated.
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if !stale {
		t.Fatal("flag should stay while a pending row remains")
	}
	// dismiss the LAST pending row → the outdated flag clears.
	dreq := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/"+contentID.String()+"/dismiss", nil)
	dreq.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	dw := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(dw, dreq)
	if dw.Code != http.StatusOK {
		t.Fatalf("dismiss last: want 200, got %d", dw.Code)
	}
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if stale {
		t.Fatal("flag should clear after the last pending row is dismissed")
	}
	// dismissing an already-resolved row → 404 (idempotent guard).
	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/"+hardID.String()+"/dismiss", nil)
	req2.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	f.srv.Router().ServeHTTP(w2, req2)
	if w2.Code != http.StatusNotFound {
		t.Fatalf("re-dismiss: want 404, got %d", w2.Code)
	}
}
