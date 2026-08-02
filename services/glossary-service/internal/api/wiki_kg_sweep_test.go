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
	"github.com/loreweave/glossary-service/internal/guardstatus"
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
	if n.Flagged != 1 {
		t.Fatalf("want 1 flagged, got %d", n.Flagged)
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
	if n2.Flagged != 0 {
		t.Fatalf("re-sweep should flag 0, got %d", n2.Flagged)
	}
}

// D-WIKI-P2-SWEEP-DISMISS-RESWEEP: a dismissed kg_drift stays dismissed while its
// signature (storedHash → current_hash) is unchanged. kg_drift keys source_id on
// storedHash only, so current_hash is folded into the dismiss guard.
func TestSweepKgDrift_DismissedSameHashNotResurrected(t *testing.T) {
	f := newMergeFixture(t, "00000000e0a6")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Seward", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")

	stub := kgStub(t, map[string]string{entity.String(): "NEW"}, http.StatusOK)
	defer stub.Close()
	f.srv.cfg.KnowledgeServiceURL = stub.URL
	f.srv.cfg.InternalServiceToken = "tok"
	owner := uuid.New()

	if n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, owner); err != nil || n.Flagged != 1 {
		t.Fatalf("initial sweep: n=%d err=%v (want 1)", n.Flagged, err)
	}
	dismissStaleness(t, f, art, "kg_drift")
	if isStale(t, f, art) {
		t.Fatal("badge should be cleared after dismiss")
	}

	// Same current hash (still OLD→NEW) → suppressed, badge stays down.
	n2, err := f.srv.sweepKgDrift(f.ctx, f.bookID, owner)
	if err != nil {
		t.Fatalf("re-sweep: %v", err)
	}
	if n2.Flagged != 0 {
		t.Fatalf("dismissed same-hash must not re-insert, got %d", n2.Flagged)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("want 0 pending (stays dismissed), got %d", got)
	}
	if isStale(t, f, art) {
		t.Fatal("dismissed same-hash must NOT re-raise is_knowledge_stale")
	}
}

// A genuinely NEW current hash (the neighbourhood drifted further) is a new drift →
// re-surfaces despite the earlier dismissal (current_hash differs from the dismissed row).
func TestSweepKgDrift_DismissedNewHashResurfaces(t *testing.T) {
	f := newMergeFixture(t, "00000000e0a7")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Westenra", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")
	f.srv.cfg.InternalServiceToken = "tok"
	owner := uuid.New()

	stub1 := kgStub(t, map[string]string{entity.String(): "NEW"}, http.StatusOK)
	f.srv.cfg.KnowledgeServiceURL = stub1.URL
	if n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, owner); err != nil || n.Flagged != 1 {
		stub1.Close()
		t.Fatalf("initial sweep: n=%d err=%v (want 1)", n.Flagged, err)
	}
	stub1.Close()
	dismissStaleness(t, f, art, "kg_drift")

	// Neighbourhood drifts further: current hash is now NEWER (≠ the dismissed NEW).
	stub2 := kgStub(t, map[string]string{entity.String(): "NEWER"}, http.StatusOK)
	defer stub2.Close()
	f.srv.cfg.KnowledgeServiceURL = stub2.URL
	n2, err := f.srv.sweepKgDrift(f.ctx, f.bookID, owner)
	if err != nil {
		t.Fatalf("re-sweep: %v", err)
	}
	if n2.Flagged != 1 {
		t.Fatalf("new current hash must re-surface, got %d", n2.Flagged)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 1 {
		t.Fatalf("want 1 pending (new hash), got %d", got)
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
	if n.Flagged != 0 {
		t.Fatalf("matching hash should flag 0, got %d", n.Flagged)
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
	if n.Flagged != 0 {
		t.Fatalf("an omitted entity must not flag, got %d", n.Flagged)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("want 0 kg_drift rows, got %d", got)
	}
	// …and the half this test used to be silent about. Not flagging is correct; reporting the
	// same thing a fully-compared book reports is not. The entity was NEVER COMPARED, and
	// before the report existed there was no field able to say so.
	if n.Status != guardstatus.Degraded {
		t.Fatalf("an uncompared entity must degrade the sweep, got %q", n.Status)
	}
	if n.Unchecked != 1 || n.Checked != 0 {
		t.Fatalf("coverage must name the hole: %+v", n)
	}
}

func TestSweepKgDrift_ACleanSweepAndAnOUTAGEAreNoLongerIdenticalOutput(t *testing.T) {
	// THE defect, stated as a test. Both arms flag zero. Before the report, both returned the
	// integer 0 and the caller had no way to tell "nothing has drifted" from "the knowledge
	// service was down and nothing was compared" — the registry's own words for this row.
	//
	// Written as one test over two arms on purpose: asserting `degraded` alone passes for an
	// implementation that degrades everything, which is the permanently-amber failure and not
	// a signal. The pair is the property.
	f := newMergeFixture(t, "00000000e0a7")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Seward", nil)
	art := mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity)
	setKgHash(t, f, art, "OLD")
	f.srv.cfg.InternalServiceToken = "tok"

	clean := kgStub(t, map[string]string{entity.String(): "OLD"}, http.StatusOK)
	defer clean.Close()
	f.srv.cfg.KnowledgeServiceURL = clean.URL
	compared, err := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if err != nil {
		t.Fatalf("clean arm: %v", err)
	}

	// Same book, same article, same zero findings — knowledge is simply unreachable.
	down := kgStub(t, nil, http.StatusServiceUnavailable)
	defer down.Close()
	f.srv.cfg.KnowledgeServiceURL = down.URL
	outage, err := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if err != nil {
		t.Fatalf("outage arm must degrade, not error: %v", err)
	}

	if compared.Flagged != 0 || outage.Flagged != 0 {
		t.Fatalf("the premise is gone — both arms must flag zero: %+v / %+v", compared, outage)
	}
	if compared == outage {
		t.Fatalf("a clean sweep and an outage still produce identical output: %+v", compared)
	}
	if compared.Status != guardstatus.Checked || compared.Checked != 1 {
		t.Fatalf("clean arm should be a real answer over a real corpus: %+v", compared)
	}
	if outage.Status != guardstatus.Degraded || outage.Unchecked != 1 {
		t.Fatalf("outage arm should name what it could not compare: %+v", outage)
	}
}

func TestSweepKgDrift_ABookWithNothingInScopeIsNotACleanSweep(t *testing.T) {
	// The third state the integer collapsed. No article carries a stored KG hash, so there was
	// nothing to compare — which must not read as "I compared everything and it all matched".
	f := newMergeFixture(t, "00000000e0a8")
	cleanupWikiArticles(t, f)
	entity := f.mkEntity(t, "Harker", nil)
	mkWikiArticle(t, f.pool, f.ctx, f.bookID, entity) // no setKgHash → no baseline

	n, err := f.srv.sweepKgDrift(f.ctx, f.bookID, uuid.New())
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if n.Status != guardstatus.NoSubject {
		t.Fatalf("an empty scope must be no_subject, got %q (%+v)", n.Status, n)
	}
	if n.Unchecked != 0 {
		t.Fatalf("nothing was in scope, so nothing is UNCHECKED — that would be a hole "+
			"nobody can ever close: %+v", n)
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
	if n.Flagged != 0 {
		t.Fatalf("empty/null stored baseline must be skipped, got %d flagged", n.Flagged)
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
	if n.Flagged != 0 {
		t.Fatalf("want 0 flagged on degrade, got %d", n.Flagged)
	}
	if got := pendingStaleness(t, f, art, "kg_drift"); got != 0 {
		t.Fatalf("degrade must not flag, got %d", got)
	}
}
