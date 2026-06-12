package api

// wiki-llm Phase-2b (D-WIKI-P2B-SUGGESTION-RESOLVE) — accepting a suggestion
// resolves the article's pending staleness (symmetric with the direct-write
// resolve), and an AI-regeneration suggestion (clobber-guard envelope) is
// unwrapped + its generation metadata restored on accept. DB-integration via
// newMergeFixture (needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func seedSuggestion(t *testing.T, f *mergeFixture, articleID uuid.UUID, diff, reason string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := f.pool.QueryRow(f.ctx, `
		INSERT INTO wiki_suggestions (article_id, user_id, diff_json, reason, status)
		VALUES ($1, $2, $3, $4, 'pending') RETURNING suggestion_id`,
		articleID, uuid.New(), json.RawMessage(diff), reason).Scan(&id); err != nil {
		t.Fatalf("seed suggestion: %v", err)
	}
	t.Cleanup(func() { f.pool.Exec(f.ctx, `DELETE FROM wiki_suggestions WHERE article_id=$1`, articleID) })
	return id
}

func reviewSuggestion(t *testing.T, f *mergeFixture, owner string, articleID, sugID uuid.UUID, action string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"action": action})
	req := httptest.NewRequest(http.MethodPatch,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/"+articleID.String()+"/suggestions/"+sugID.String(),
		bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func latestRevAuthor(t *testing.T, f *mergeFixture, articleID uuid.UUID) string {
	t.Helper()
	var a string
	f.pool.QueryRow(f.ctx,
		`SELECT author_type FROM wiki_revisions WHERE article_id=$1 ORDER BY version DESC LIMIT 1`,
		articleID).Scan(&a)
	return a
}

func assertStalenessResolved(t *testing.T, f *mergeFixture, art uuid.UUID) {
	t.Helper()
	var pending, regen int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM wiki_staleness WHERE article_id=$1 AND status='pending'`, art).Scan(&pending)
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM wiki_staleness WHERE article_id=$1 AND status='regenerated'`, art).Scan(&regen)
	if pending != 0 {
		t.Fatalf("want 0 pending staleness after accept, got %d", pending)
	}
	if regen < 1 {
		t.Fatalf("want >=1 regenerated staleness row after accept, got %d", regen)
	}
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if stale {
		t.Fatal("is_knowledge_stale should be cleared after accept")
	}
}

// An AI regeneration filed as a suggestion (the clobber-guard envelope) is
// unwrapped to the real body, its generation metadata restored, logged as an 'ai'
// revision, and the pending staleness resolved.
func TestAcceptAIRegenSuggestion_UnwrapsBodyAndResolvesStaleness(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f3")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	// human-edited article (latest revision 'owner') → an AI regen lands as a suggestion.
	aiRevision(t, f, art, uuid.New(), "owner")
	seedStalenessRow(t, f, art, "entity_changed", "content")
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	realBody := `{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"fresh-regen-body"}]}]}`
	env := `{"body_json":` + realBody + `,"generation_status":"generated","generation_provenance":{"build_inputs":{"prompt_version":"v9"}}}`
	sug := seedSuggestion(t, f, art, env, "AI regeneration (article has human edits)")

	if w := reviewSuggestion(t, f, owner, art, sug, "accept"); w.Code != http.StatusOK {
		t.Fatalf("accept: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	var body, prov string
	var genStatus *string
	f.pool.QueryRow(f.ctx,
		`SELECT body_json::text, generation_status, COALESCE(generation_provenance::text,'') FROM wiki_articles WHERE article_id=$1`,
		art).Scan(&body, &genStatus, &prov)
	// the stored body is the UNWRAPPED doc, not the {body_json:...} envelope.
	if !strings.Contains(body, "fresh-regen-body") {
		t.Fatalf("body should be the unwrapped regen doc, got %s", body)
	}
	if strings.Contains(body, "body_json") {
		t.Fatalf("body should NOT be the envelope (no body_json key), got %s", body)
	}
	if genStatus == nil || *genStatus != "generated" {
		t.Fatalf("generation_status should be restored to 'generated', got %v", genStatus)
	}
	if prov == "" || prov == "null" || !strings.Contains(prov, "prompt_version") {
		t.Fatalf("generation_provenance should be restored, got %q", prov)
	}
	if a := latestRevAuthor(t, f, art); a != "ai" {
		t.Fatalf("an accepted AI regen should log an 'ai' revision, got %q", a)
	}
	assertStalenessResolved(t, f, art)
}

// A human community suggestion is applied verbatim as a 'community' revision, and
// accepting it still resolves the article's staleness (PO: any accept resolves).
func TestAcceptHumanSuggestion_ResolvesStalenessKeepsCommunity(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f4")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	aiRevision(t, f, art, uuid.New(), "owner")
	seedStalenessRow(t, f, art, "chapter_regrounded", "content")
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	doc := `{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"human-edit-body"}]}]}`
	sug := seedSuggestion(t, f, art, doc, "fix typo")

	if w := reviewSuggestion(t, f, owner, art, sug, "accept"); w.Code != http.StatusOK {
		t.Fatalf("accept: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var body string
	f.pool.QueryRow(f.ctx, `SELECT body_json::text FROM wiki_articles WHERE article_id=$1`, art).Scan(&body)
	if !strings.Contains(body, "human-edit-body") {
		t.Fatalf("body should be the applied human doc, got %s", body)
	}
	if a := latestRevAuthor(t, f, art); a != "community" {
		t.Fatalf("a human suggestion should log a 'community' revision, got %q", a)
	}
	assertStalenessResolved(t, f, art)
}

// A client-crafted diff carrying a top-level body_json but NO generation_status is
// NOT a clobber-guard envelope — it must stay on the community path and must not
// NULL out an existing article's generation metadata or mislabel the revision 'ai'.
func TestAcceptSuggestion_BodyJsonWithoutGenStatus_StaysCommunity(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f6")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Quincey", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET generation_status='generated' WHERE article_id=$1`, art)
	aiRevision(t, f, art, uuid.New(), "owner")

	crafted := `{"body_json":{"type":"doc","content":[]},"note":"not a real envelope"}`
	sug := seedSuggestion(t, f, art, crafted, "crafted")
	if w := reviewSuggestion(t, f, owner, art, sug, "accept"); w.Code != http.StatusOK {
		t.Fatalf("accept: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if a := latestRevAuthor(t, f, art); a != "community" {
		t.Fatalf("no generation_status → must stay community, got %q", a)
	}
	var genStatus *string
	f.pool.QueryRow(f.ctx, `SELECT generation_status FROM wiki_articles WHERE article_id=$1`, art).Scan(&genStatus)
	if genStatus == nil || *genStatus != "generated" {
		t.Fatalf("community path must not touch generation_status, got %v", genStatus)
	}
}

// Rejecting a suggestion intentionally leaves the staleness pending — the changed
// source is still unaddressed, so the article stays flagged Outdated.
func TestRejectSuggestion_LeavesStaleness(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f5")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Renfield", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	aiRevision(t, f, art, uuid.New(), "owner")
	seedStalenessRow(t, f, art, "entity_changed", "content")
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	sug := seedSuggestion(t, f, art, `{"type":"doc","content":[]}`, "nope")
	if w := reviewSuggestion(t, f, owner, art, sug, "reject"); w.Code != http.StatusOK {
		t.Fatalf("reject: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var pending int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM wiki_staleness WHERE article_id=$1 AND status='pending'`, art).Scan(&pending)
	if pending != 1 {
		t.Fatalf("reject should leave staleness pending, got %d", pending)
	}
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if !stale {
		t.Fatal("reject should leave the outdated flag set")
	}
}
