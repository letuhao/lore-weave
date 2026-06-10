package api

// wiki-llm Phase-2 — tests for the recipe-drift sweep (DB-integration via
// newMergeFixture; needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"context"
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
