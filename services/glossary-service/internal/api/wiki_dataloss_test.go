package api

// Bug-fix DB-integration tests (data-loss guards) preceding the wiki-LLM feature.
//   Bug 1 — merge must NOT silently abandon a loser's wiki_article (merge AC4):
//           both sides have an article  -> loser's archived in place (superseded_by
//                                          -> winner), winner's untouched;
//           only the loser has one      -> repointed to winner (unchanged);
//           un-merge                    -> archive cleared (round-trip lossless).
//   Bug 2 — the wiki_articles entity FK is RESTRICT: a raw entity delete with an
//           article must FK-block (no silent ON DELETE CASCADE destruction).
// Reuse the merge fixture (newMergeFixture) — requires GLOSSARY_TEST_DB_URL; skips otherwise.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// mockBookOwner stands up a fake book-service serving /access (the E0-1 grant
// authority) + /projection so the HTTP guards pass for `owner`, points the
// fixture's server at it, and (re)wires the grant client (which captures the
// base URL at construction). Returns the owner id.
func mockBookOwner(t *testing.T, f *mergeFixture) string {
	t.Helper()
	owner := uuid.New()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasSuffix(r.URL.Path, "/access") {
			lvl := "none"
			if r.URL.Query().Get("user_id") == owner.String() {
				lvl = "owner"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": lvl, "lifecycle_state": "active"})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id": f.bookID.String(), "owner_user_id": owner.String(),
		})
	}))
	t.Cleanup(srv.Close)
	f.srv.cfg.BookServiceURL = srv.URL
	f.srv.cfg.InternalServiceToken = "tok"
	f.srv.grantClient = buildGrantClient(srv.URL, "tok")
	return owner.String()
}

func mkWikiArticle(t *testing.T, pool *pgxpool.Pool, ctx context.Context, bookID, entityID uuid.UUID) uuid.UUID {
	t.Helper()
	var aid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO wiki_articles (entity_id, book_id, body_json, status) VALUES ($1,$2,'{}','draft') RETURNING article_id`,
		entityID, bookID).Scan(&aid); err != nil {
		t.Fatalf("mkWikiArticle: %v", err)
	}
	return aid
}

func wikiSupersededBy(t *testing.T, pool *pgxpool.Pool, ctx context.Context, articleID uuid.UUID) *uuid.UUID {
	t.Helper()
	var s *uuid.UUID
	pool.QueryRow(ctx, `SELECT superseded_by_entity_id FROM wiki_articles WHERE article_id=$1`, articleID).Scan(&s)
	return s
}

func wikiEntityOf(t *testing.T, pool *pgxpool.Pool, ctx context.Context, articleID uuid.UUID) uuid.UUID {
	t.Helper()
	var e uuid.UUID
	pool.QueryRow(ctx, `SELECT entity_id FROM wiki_articles WHERE article_id=$1`, articleID).Scan(&e)
	return e
}

// cleanupWikiArticles registers AFTER newMergeFixture so it runs BEFORE the
// fixture's entity cleanup (LIFO) — with the FK now RESTRICT, deleting entities
// while their articles exist would FK-block.
func cleanupWikiArticles(t *testing.T, f *mergeFixture) {
	t.Cleanup(func() { f.pool.Exec(f.ctx, `DELETE FROM wiki_articles WHERE book_id=$1`, f.bookID) })
}

// Bug 1: both sides have an article -> the loser's is archived (superseded_by ->
// winner), never silently abandoned; the winner's stays live; journal records it.
func TestMergeOne_BothHaveArticle_ArchivesLoser(t *testing.T) {
	f := newMergeFixture(t, "00000000000a")
	cleanupWikiArticles(t, f)
	winner := f.mkEntity(t, "周文王", nil)
	loser := f.mkEntity(t, "姬昌", nil)
	winnerArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, winner)
	loserArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, loser)

	jid, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("mergeOne: reason=%q err=%v", reason, err)
	}
	if sb := wikiSupersededBy(t, f.pool, f.ctx, loserArt); sb == nil || *sb != winner {
		t.Errorf("loser article not archived to winner (silent abandon?): got %v", sb)
	}
	if sb := wikiSupersededBy(t, f.pool, f.ctx, winnerArt); sb != nil {
		t.Errorf("winner article wrongly superseded: %v", sb)
	}
	if e := wikiEntityOf(t, f.pool, f.ctx, loserArt); e != loser {
		t.Errorf("loser article entity changed: got %v want %v", e, loser)
	}
	var jSuperseded *uuid.UUID
	f.pool.QueryRow(f.ctx, `SELECT superseded_wiki_article_id FROM merge_journal WHERE journal_id=$1`, jid).Scan(&jSuperseded)
	if jSuperseded == nil || *jSuperseded != loserArt {
		t.Errorf("journal superseded_wiki_article_id = %v, want %v", jSuperseded, loserArt)
	}
}

// Bug 1: only the loser has an article -> still repointed to the winner (unchanged
// behaviour), NOT archived.
func TestMergeOne_OnlyLoserHasArticle_Repoints(t *testing.T) {
	f := newMergeFixture(t, "00000000000b")
	cleanupWikiArticles(t, f)
	winner := f.mkEntity(t, "姜子牙", nil)
	loser := f.mkEntity(t, "太公望", nil)
	loserArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, loser)

	if _, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New()); err != nil || reason != "" {
		t.Fatalf("mergeOne: reason=%q err=%v", reason, err)
	}
	if e := wikiEntityOf(t, f.pool, f.ctx, loserArt); e != winner {
		t.Errorf("article not repointed to winner: got %v", e)
	}
	if sb := wikiSupersededBy(t, f.pool, f.ctx, loserArt); sb != nil {
		t.Errorf("repointed article wrongly superseded: %v", sb)
	}
}

// Bug 1: un-merge clears the archive (superseded) flag — lossless round-trip.
func TestRevertMerge_RestoresSupersededArticle(t *testing.T) {
	f := newMergeFixture(t, "00000000000c")
	cleanupWikiArticles(t, f)
	winner := f.mkEntity(t, "哪吒", nil)
	loser := f.mkEntity(t, "中壇元帥", nil)
	_ = mkWikiArticle(t, f.pool, f.ctx, f.bookID, winner)
	loserArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, loser)

	jid, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New())
	if err != nil || reason != "" {
		t.Fatalf("mergeOne: reason=%q err=%v", reason, err)
	}
	if sb := wikiSupersededBy(t, f.pool, f.ctx, loserArt); sb == nil {
		t.Fatal("precondition: loser article should be superseded after merge")
	}
	if reason, err := f.srv.revertMergeCore(f.ctx, f.bookID, jid, uuid.Nil); err != nil || reason != "" {
		t.Fatalf("revertMergeCore: reason=%q err=%v", reason, err)
	}
	if sb := wikiSupersededBy(t, f.pool, f.ctx, loserArt); sb != nil {
		t.Errorf("un-merge did not clear superseded: %v", sb)
	}
	if del, _ := f.isSoftDeleted(t, loser); del {
		t.Errorf("loser still soft-deleted after un-merge")
	}
}

// Bug 2: the entity FK is RESTRICT — a raw entity delete with a live article must
// FK-block (proving the silent ON DELETE CASCADE destruction is gone).
func TestFK_WikiArticle_RestrictsEntityDelete(t *testing.T) {
	f := newMergeFixture(t, "00000000000d")
	cleanupWikiArticles(t, f)
	ent := f.mkEntity(t, "妲己", nil)
	_ = mkWikiArticle(t, f.pool, f.ctx, f.bookID, ent)
	f.pool.Exec(f.ctx, `UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, ent)
	if _, err := f.pool.Exec(f.ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, ent); err == nil {
		t.Fatal("entity delete with a wiki_article succeeded — FK is not RESTRICT (silent cascade still possible)")
	}
}

// Bug 1 (AC1.2): GET on an archived (superseded) article redirects to the winner's
// article, carrying redirected_from. HTTP path through verifyBookOwner (mocked).
func TestGetWikiArticle_RedirectsSupersededToWinner(t *testing.T) {
	f := newMergeFixture(t, "00000000000e")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)

	winner := f.mkEntity(t, "周文王", nil)
	loser := f.mkEntity(t, "姬昌", nil)
	winnerArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, winner)
	loserArt := mkWikiArticle(t, f.pool, f.ctx, f.bookID, loser)
	if _, reason, err := f.srv.mergeOne(f.ctx, f.bookID, winner, f.kindID, loser, uuid.New()); err != nil || reason != "" {
		t.Fatalf("mergeOne: reason=%q err=%v", reason, err)
	}

	req := httptest.NewRequest(http.MethodGet,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/"+loserArt.String(), nil)
	req.Header.Set("Authorization", "Bearer "+makeExportToken(t, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("getWikiArticle: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		ArticleID      string `json:"article_id"`
		EntityID       string `json:"entity_id"`
		RedirectedFrom string `json:"redirected_from"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.ArticleID != winnerArt.String() {
		t.Errorf("redirect served wrong article: got %s want winner %s", resp.ArticleID, winnerArt)
	}
	if resp.EntityID != winner.String() {
		t.Errorf("redirect entity: got %s want winner %s", resp.EntityID, winner)
	}
	if resp.RedirectedFrom != loserArt.String() {
		t.Errorf("redirected_from: got %s want loser %s", resp.RedirectedFrom, loserArt)
	}
}

// Bug 2: user-delete of an article emits wiki.deleted (reason=user_deleted) atomically.
func TestDeleteWikiArticle_EmitsWikiDeleted(t *testing.T) {
	f := newMergeFixture(t, "00000000000f")
	cleanupWikiArticles(t, f)
	owner := mockBookOwner(t, f)

	ent := f.mkEntity(t, "杨戬", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, ent)

	req := httptest.NewRequest(http.MethodDelete,
		"/v1/glossary/books/"+f.bookID.String()+"/wiki/"+art.String(), nil)
	req.Header.Set("Authorization", "Bearer "+makeExportToken(t, owner))
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNoContent {
		t.Fatalf("deleteWikiArticle: want 204, got %d (%s)", w.Code, w.Body.String())
	}
	var nEvent, nArt int
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM outbox_events WHERE event_type='wiki.deleted' AND payload->>'article_id'=$1`, art.String()).Scan(&nEvent)
	if nEvent != 1 {
		t.Errorf("wiki.deleted events = %d, want 1", nEvent)
	}
	f.pool.QueryRow(f.ctx, `SELECT count(*) FROM wiki_articles WHERE article_id=$1`, art.String()).Scan(&nArt)
	if nArt != 0 {
		t.Errorf("article not deleted (%d remain)", nArt)
	}
}
