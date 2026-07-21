package events

// wiki-llm Phase-2 — tests for the staleness capture. stalenessRule is pure;
// markArticlesStale is DB-integration (needs GLOSSARY_TEST_DB_URL, skips otherwise).

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// ── pure routing ──────────────────────────────────────────────────────────────

func TestStalenessRule(t *testing.T) {
	cases := []struct {
		event, reason, severity, sourceType string
		ok                                  bool
	}{
		{"glossary.entity_updated", "entity_changed", "content", "entity", true},
		{"glossary.entity_merged", "merged", "structural", "entity", true},
		{"chapter.published", "chapter_regrounded", "content", "block", true},
		{"chapter.deleted", "citation_broken", "hard", "block", true},
		{"chapter.trashed", "citation_broken", "hard", "block", true},
		// H1 (spec §4.6): a bulk book restore un-trashes chapters → the prose RETURNS, a re-grounding
		// trigger (content severity, like a re-publish), NOT another hard break.
		{"chapter.restored", "chapter_regrounded", "content", "block", true},
		{"chapter.saved", "", "", "", false}, // high-volume autosave — NOT a staleness trigger
		{"glossary.entity_created", "", "", "", false},
		{"some.other.event", "", "", "", false},
	}
	for _, c := range cases {
		reason, sev, st, ok := stalenessRule(c.event)
		if ok != c.ok || reason != c.reason || sev != c.severity || st != c.sourceType {
			t.Errorf("%s -> (%q,%q,%q,%v); want (%q,%q,%q,%v)",
				c.event, reason, sev, st, ok, c.reason, c.severity, c.sourceType, c.ok)
		}
	}
}

// ── DB-integration ────────────────────────────────────────────────────────────

func setupWikiDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	pool := setupDB(t) // skips when GLOSSARY_TEST_DB_URL unset; runs base migrations
	if err := migrate.UpWiki(context.Background(), pool); err != nil {
		t.Fatalf("migrate UpWiki: %v", err)
	}
	return pool
}

func seedArticle(t *testing.T, pool *pgxpool.Pool, bookID, entityID uuid.UUID) uuid.UUID {
	t.Helper()
	var aid uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO wiki_articles (entity_id, book_id, body_json, status, generation_status)
		 VALUES ($1,$2,'{}','draft','generated') RETURNING article_id`,
		entityID, bookID,
	).Scan(&aid); err != nil {
		t.Fatalf("seed article: %v", err)
	}
	return aid
}

func addSourceUsage(t *testing.T, pool *pgxpool.Pool, articleID uuid.UUID, sourceType, sourceID string) {
	t.Helper()
	if _, err := pool.Exec(context.Background(),
		`INSERT INTO wiki_article_source_usage (article_id, source_type, source_id) VALUES ($1,$2,$3)
		 ON CONFLICT DO NOTHING`,
		articleID, sourceType, sourceID,
	); err != nil {
		t.Fatalf("seed source_usage: %v", err)
	}
}

func stalenessCount(t *testing.T, pool *pgxpool.Pool, articleID uuid.UUID, reason string) int {
	t.Helper()
	var n int
	pool.QueryRow(context.Background(),
		`SELECT count(*) FROM wiki_staleness WHERE article_id=$1 AND reason_code=$2 AND status='pending'`,
		articleID, reason).Scan(&n)
	return n
}

func isStale(t *testing.T, pool *pgxpool.Pool, articleID uuid.UUID) bool {
	t.Helper()
	var s bool
	pool.QueryRow(context.Background(),
		`SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, articleID).Scan(&s)
	return s
}

func TestMarkArticlesStale_FlagsAndIsIdempotent(t *testing.T) {
	pool := setupWikiDB(t)
	ctx := context.Background()
	book := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM wiki_articles WHERE book_id=$1`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	entity := seedEntity(t, pool, book)
	art := seedArticle(t, pool, book, entity)
	addSourceUsage(t, pool, art, "entity", entity.String())

	// First entity change → one staleness row + flag.
	n, err := markArticlesStale(ctx, pool, "entity", entity.String(), "entity_changed", "content", "ev-1")
	if err != nil {
		t.Fatalf("markArticlesStale: %v", err)
	}
	if n != 1 {
		t.Fatalf("want 1 inserted, got %d", n)
	}
	if !isStale(t, pool, art) {
		t.Fatal("article should be flagged is_knowledge_stale")
	}
	if got := stalenessCount(t, pool, art, "entity_changed"); got != 1 {
		t.Fatalf("want 1 pending row, got %d", got)
	}

	// Redelivery of the SAME source change → no duplicate (idempotent ledger).
	n2, _ := markArticlesStale(ctx, pool, "entity", entity.String(), "entity_changed", "content", "ev-1-redelivery")
	if n2 != 0 {
		t.Fatalf("redelivery should insert 0, got %d", n2)
	}
	if got := stalenessCount(t, pool, art, "entity_changed"); got != 1 {
		t.Fatalf("still want 1 pending row after redelivery, got %d", got)
	}
}

func TestMarkArticlesStale_BlockSourceAndNoMatch(t *testing.T) {
	pool := setupWikiDB(t)
	ctx := context.Background()
	book := uuid.New()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM wiki_articles WHERE book_id=$1`, book)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, book)
	})
	entity := seedEntity(t, pool, book)
	art := seedArticle(t, pool, book, entity)
	chapterID := uuid.New().String()
	addSourceUsage(t, pool, art, "block", chapterID)

	// A chapter the article cites is deleted → citation_broken (hard).
	n, _ := markArticlesStale(ctx, pool, "block", chapterID, "citation_broken", "hard", "ev-ch")
	if n != 1 || !isStale(t, pool, art) {
		t.Fatalf("block-source change should flag the article (n=%d stale=%v)", n, isStale(t, pool, art))
	}

	// A change to a source NO article used → zero rows (no false positives).
	n2, _ := markArticlesStale(ctx, pool, "block", uuid.New().String(), "citation_broken", "hard", "ev-x")
	if n2 != 0 {
		t.Fatalf("unrelated source change should insert 0, got %d", n2)
	}
}
