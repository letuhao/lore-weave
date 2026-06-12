package api

// wiki-llm Phase-2 (D-WIKI-P2-KG-SWEEP) — DB-integration tests for the KG-drift
// sweep. The current-hash recompute is stubbed (a knowledge httptest server); these
// pin the COMPARE + insert + idempotency + the don't-false-flag guards. Need
// GLOSSARY_TEST_DB_URL (newMergeFixture skips otherwise).

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func setKgHash(t *testing.T, f *mergeFixture, articleID uuid.UUID, hash string) {
	t.Helper()
	if _, err := f.pool.Exec(f.ctx, `
		UPDATE wiki_articles
		   SET generation_status='generated',
		       generation_provenance = jsonb_build_object('build_inputs',
		         jsonb_build_object('kg_neighborhood_hash', $2::text))
		 WHERE article_id=$1`, articleID, hash); err != nil {
		t.Fatalf("set kg hash: %v", err)
	}
}

// kgStub serves the knowledge kg-hashes endpoint: returns {hashes} on 200, else code.
func kgStub(t *testing.T, hashes map[string]string, code int) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if code != http.StatusOK {
			w.WriteHeader(code)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"hashes": hashes})
	}))
}

func TestSweepKgDrift_FlagsChangedNeighbourhoodAndIsIdempotent(t *testing.T) {
	f := newMergeFixture(t, "00000000e0a1")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Mina", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")

	stub := kgStub(t, map[string]string{entity.String(): "NEW"}, http.StatusOK)
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL
	f.srv.cfg.InternalServiceToken = "tok"

	owner := uuid.New()
	n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, owner)
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if n != 1 {
		t.Fatalf("want 1 flagged, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 1 {
		t.Fatalf("want 1 kg_drift row, got %d", got)
	}
	var stale bool
	f.pool.QueryRow(f.ctx, `SELECT is_knowledge_stale FROM wiki_articles WHERE article_id=$1`, art).Scan(&stale)
	if !stale {
		t.Fatal("article should be flagged is_knowledge_stale")
	}

	// the stored hash hasn't changed (no regen) → re-sweep inserts no duplicate.
	n2, _ := f.srv.sweepKgDrift(f.ctx, f.bookID, owner)
	if n2 != 0 {
		t.Fatalf("re-sweep should flag 0, got %d", n2)
	}
}

func TestSweepKgDrift_NoChangeNoRow(t *testing.T) {
	f := newMergeFixture(t, "00000000e0a2")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Lucy", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "SAME")

	stub := kgStub(t, map[string]string{entity.String(): "SAME"}, http.StatusOK)
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL

	n, _ := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if n != 0 {
		t.Fatalf("matching hash should flag 0, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("want 0 kg_drift rows, got %d", got)
	}
}

func TestSweepKgDrift_OmittedEntityIsNotDrift(t *testing.T) {
	// knowledge omits an entity whose KG is UNAVAILABLE (Neo4j down) — it must NOT be
	// read as drift (the false-positive guard).
	f := newMergeFixture(t, "00000000e0a3")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Renfield", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")

	stub := kgStub(t, map[string]string{}, http.StatusOK) // entity omitted
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL

	n, _ := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if n != 0 {
		t.Fatalf("an omitted entity must not flag, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("want 0 kg_drift rows, got %d", got)
	}
}

func TestSweepKgDrift_NullStoredHashIsSkippedNotCrashed(t *testing.T) {
	// build_inputs has the key but a JSON-null value (malformed edge): COALESCE keeps
	// the scan from crashing and the empty baseline is skipped (no false drift).
	f := newMergeFixture(t, "00000000e0a5")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Quincey", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	if _, err := f.pool.Exec(f.ctx, `
		UPDATE wiki_articles
		   SET generation_status='generated',
		       generation_provenance = jsonb_build_object('build_inputs',
		         jsonb_build_object('kg_neighborhood_hash', null))
		 WHERE article_id=$1`, art); err != nil {
		t.Fatalf("seed null hash: %v", err)
	}

	stub := kgStub(t, map[string]string{entity.String(): "NEW"}, http.StatusOK)
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL

	n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if err != nil {
		t.Fatalf("a null stored hash must not error the sweep: %v", err)
	}
	if n != 0 {
		t.Fatalf("empty/null stored baseline must be skipped, got %d flagged", n)
	}
}

func TestSweepKgDrift_KnowledgeDownDegradesToZero(t *testing.T) {
	f := newMergeFixture(t, "00000000e0a4")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Arthur", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")

	stub := kgStub(t, nil, http.StatusInternalServerError)
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL

	n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if err != nil {
		t.Fatalf("knowledge-down should degrade to (0,nil), got err %v", err)
	}
	if n != 0 {
		t.Fatalf("want 0 flagged on degrade, got %d", n)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("degrade must not flag, got %d", got)
	}
}
