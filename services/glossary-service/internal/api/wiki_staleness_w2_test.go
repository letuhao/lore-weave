package api

// W2 (gap-closure) — tests for the public staleness/sweep + dismiss-batch routes
// (DB-integration via newMergeFixture; needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func postDismissBatch(t *testing.T, f *mergeFixture, owner string, ids []string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"staleness_ids": ids})
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/dismiss-batch", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestDismissBatch_DismissesSelectedAndClearsFlag(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f3")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	r1 := seedStalenessRow(t, f, art, "chapter_regrounded", "content")
	r2 := seedStalenessRow(t, f, art, "citation_broken", "hard")
	f.pool.Exec(f.ctx, `UPDATE wiki_articles SET is_knowledge_stale=true WHERE article_id=$1`, art)

	var resp struct {
		Dismissed int `json:"dismissed"`
	}

	// Dismiss only r1 → 1 dismissed; flag stays (r2 still pending).
	w := postDismissBatch(t, f, owner, []string{r1.String()})
	if w.Code != http.StatusOK {
		t.Fatalf("dismiss-batch: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Dismissed != 1 {
		t.Fatalf("want dismissed=1, got %d", resp.Dismissed)
	}
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if !stale {
		t.Fatal("flag should stay while r2 is pending")
	}

	// Dismiss [r1 (already dismissed → skipped), r2] → only r2 counts; flag clears.
	w2 := postDismissBatch(t, f, owner, []string{r1.String(), r2.String()})
	json.Unmarshal(w2.Body.Bytes(), &resp)
	if resp.Dismissed != 1 {
		t.Fatalf("want dismissed=1 (only r2 was still pending), got %d", resp.Dismissed)
	}
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if stale {
		t.Fatal("flag should clear after the last pending row is dismissed")
	}
	if got := getFeed(t, f, owner); len(got) != 0 {
		t.Fatalf("feed should be empty after dismissing all, got %d", len(got))
	}
}

func TestDismissBatch_Unauthorized(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f4")
	cleanupWikiArticles(t, f)
	body, _ := json.Marshal(map[string]any{"staleness_ids": []string{uuid.New().String()}})
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/dismiss-batch", bytes.NewReader(body))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no-auth dismiss-batch: want 401, got %d", w.Code)
	}
}

func TestDismissBatch_RejectsOversizeArray(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f7")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	ids := make([]string, 501)
	for i := range ids {
		ids[i] = uuid.New().String()
	}
	w := postDismissBatch(t, f, owner, ids)
	if w.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("oversize dismiss-batch: want 413, got %d", w.Code)
	}
}

func TestSweepPublic_Unauthorized(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f6")
	cleanupWikiArticles(t, f)
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/sweep", nil)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no-auth sweep: want 401, got %d", w.Code)
	}
}

func TestSweepPublic_DegradesWithoutKnowledge(t *testing.T) {
	f := newMergeFixture(t, "00000000d0f5")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)
	// The test server has no KnowledgeServiceURL → getWikiGenConfig errs (recipe skipped)
	// and sweepKgDrift sees no qualifying articles → (0,nil). The owner-gated route should
	// still 200 with a honest recipe_swept=false rather than 500.
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/staleness/sweep", nil)
	req.Header.Set("Authorization", "Bearer "+feedbackToken(t, f, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("sweep: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Flagged     int  `json:"flagged"`
		KgFlagged   int  `json:"kg_flagged"`
		RecipeSwept bool `json:"recipe_swept"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.RecipeSwept {
		t.Fatal("recipe_swept should be false when knowledge is unconfigured")
	}
	if resp.Flagged != 0 || resp.KgFlagged != 0 {
		t.Fatalf("want 0/0 flagged, got %d/%d", resp.Flagged, resp.KgFlagged)
	}
}
