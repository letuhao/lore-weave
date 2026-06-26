package api

import (
	"context"
	"sort"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// researchSeed seeds N live entities of the character kind, each with a name attr value
// (so entityDisplayAttrValue + entityNameAndAliases resolve). Returns the ids sorted the
// way the worker visits them (ORDER BY entity_id).
func researchSeed(t *testing.T, pool *pgxpool.Pool, f *actionFixture, n int) (kindID uuid.UUID, ids []uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	kindID = bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, kindID, "name")
	for i := 0; i < n; i++ {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
			f.bookID, kindID).Scan(&id); err != nil {
			t.Fatalf("seed entity: %v", err)
		}
		if _, err := pool.Exec(ctx,
			`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'en',$3)`,
			id, nameAttr, "Entity "+id.String()); err != nil {
			t.Fatalf("seed name: %v", err)
		}
		ids = append(ids, id)
	}
	sort.Slice(ids, func(a, b int) bool { return ids[a].String() < ids[b].String() })
	return kindID, ids
}

// TestResearchWorker_DrainsAndCaps_RealPG drives the worker over a seeded kind with a
// stubbed web search: the paid-search cap (max_entities) is honoured, evidence is attached,
// the cursor advances, and the job completes.
func TestResearchWorker_DrainsAndCaps_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	if err := migrate.UpEntityResearchJobs(ctx, pool); err != nil {
		t.Fatalf("UpEntityResearchJobs: %v", err)
	}
	stub := stubProviderRegistry(t, `{"answer":"a","results":[
		{"title":"S1","url":"https://ex.com/1","content":"c1","score":0.9},
		{"title":"S2","url":"https://ex.com/2","content":"c2","score":0.8}
	]}`)
	f.srv.cfg.ProviderRegistryURL = stub.URL

	kindID, ids := researchSeed(t, pool, f, 3)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_research_jobs WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND kind_id=$2`, f.bookID, kindID)
	})

	// pending job: cap of 2 paid searches over 3 entities.
	view, err := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "who is {name}", 5, 2, 2, 0.02)
	if err != nil {
		t.Fatalf("insert job: %v", err)
	}
	jobID := uuid.MustParse(view.JobID)

	job, ok := f.srv.claimNextResearchJob(ctx)
	if !ok || job.JobID != jobID {
		t.Fatalf("claim: ok=%v job=%v want %v", ok, job.JobID, jobID)
	}
	f.srv.drainResearchJob(ctx, job)

	got, found, _ := f.srv.loadResearchJob(ctx, f.bookID, jobID)
	if !found || got.Status != "complete" {
		t.Fatalf("status=%q found=%v, want complete", got.Status, found)
	}
	if got.SearchesRun != 2 {
		t.Errorf("searches_run=%d, want 2 (cap)", got.SearchesRun)
	}
	if got.ItemsProcessed != 2 {
		t.Errorf("items_processed=%d, want 2", got.ItemsProcessed)
	}
	if got.SourcesAttached != 4 { // 2 entities × 2 sources
		t.Errorf("sources_attached=%d, want 4", got.SourcesAttached)
	}
	// exactly the first 2 entities (cursor order) got reference evidence; the 3rd did not.
	if n := refEvidenceCount(t, pool, ids[0]); n != 2 {
		t.Errorf("entity[0] evidence=%d, want 2", n)
	}
	if n := refEvidenceCount(t, pool, ids[2]); n != 0 {
		t.Errorf("entity[2] (beyond cap) evidence=%d, want 0", n)
	}
}

// TestResearchWorker_SkipsAlreadyResearched_RealPG: an entity that already carries
// reference evidence is skipped FREE (doesn't consume the paid-search budget), so the cap
// applies to NEW searches only.
func TestResearchWorker_SkipsAlreadyResearched_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	if err := migrate.UpEntityResearchJobs(ctx, pool); err != nil {
		t.Fatalf("UpEntityResearchJobs: %v", err)
	}
	stub := stubProviderRegistry(t, `{"answer":"a","results":[{"title":"S","url":"https://ex.com/x","content":"c","score":0.9}]}`)
	f.srv.cfg.ProviderRegistryURL = stub.URL

	kindID, ids := researchSeed(t, pool, f, 3)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_research_jobs WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND kind_id=$2`, f.bookID, kindID)
	})
	// Pre-attach a reference evidence row to the FIRST entity → the worker must skip it.
	avid, ok, _ := f.srv.entityDisplayAttrValue(ctx, ids[0])
	if !ok {
		t.Fatal("entity[0] has no display attr value")
	}
	note := "seed"
	if _, err := f.srv.createEvidenceCore(ctx, avid, "reference", "prior", "und", "", nil, nil, "https://prior.example/x", &note); err != nil {
		t.Fatalf("seed prior evidence: %v", err)
	}

	view, _ := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "q {name}", 5, 2, 2, 0.02)
	jobID := uuid.MustParse(view.JobID)
	job, _ := f.srv.claimNextResearchJob(ctx)
	f.srv.drainResearchJob(ctx, job)

	got, _, _ := f.srv.loadResearchJob(ctx, f.bookID, jobID)
	if got.Status != "complete" {
		t.Fatalf("status=%q, want complete", got.Status)
	}
	// 1 skipped (entity[0]) + 2 researched (entity[1],[2]) = items_processed 3; searches_run 2.
	if got.ItemsProcessed != 3 {
		t.Errorf("items_processed=%d, want 3 (1 skipped + 2 searched)", got.ItemsProcessed)
	}
	if got.SearchesRun != 2 {
		t.Errorf("searches_run=%d, want 2 (skip is free)", got.SearchesRun)
	}
}

// TestResearchWorker_WebSearchError_Fails_RealPG: a web-search error fails the job and
// leaves the cursor unadvanced so a resume retries the failing entity.
func TestResearchWorker_WebSearchError_Fails_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	if err := migrate.UpEntityResearchJobs(ctx, pool); err != nil {
		t.Fatalf("UpEntityResearchJobs: %v", err)
	}
	// A stub that 500s every search.
	stub := stubProviderRegistry(t, "")
	f.srv.cfg.ProviderRegistryURL = stub.URL + "/force-500" // path mismatch → 404 → webSearch error

	kindID, _ := researchSeed(t, pool, f, 2)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_research_jobs WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND kind_id=$2`, f.bookID, kindID)
	})

	view, _ := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "q {name}", 5, 2, 2, 0.02)
	jobID := uuid.MustParse(view.JobID)
	job, _ := f.srv.claimNextResearchJob(ctx)
	f.srv.drainResearchJob(ctx, job)

	got, _, _ := f.srv.loadResearchJob(ctx, f.bookID, jobID)
	if got.Status != "failed" {
		t.Fatalf("status=%q, want failed", got.Status)
	}
	if got.ErrorMessage == nil || *got.ErrorMessage == "" {
		t.Errorf("failed job must carry an error_message")
	}
	if got.SearchesRun != 0 {
		t.Errorf("searches_run=%d, want 0 (the first search failed)", got.SearchesRun)
	}
}

// TestResearchJob_Transitions_RealPG covers the pause/resume/cancel state machine via the
// shared transition core: allowed transitions change state, disallowed ones report
// found-but-unchanged (→409), and a bogus job reports not-found (→404).
func TestResearchJob_Transitions_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	if err := migrate.UpEntityResearchJobs(ctx, pool); err != nil {
		t.Fatalf("UpEntityResearchJobs: %v", err)
	}
	kindID, _ := researchSeed(t, pool, f, 1)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_research_jobs WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND kind_id=$2`, f.bookID, kindID)
	})
	view, _ := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "q", 5, 1, 1, 0.01)
	jobID := uuid.MustParse(view.JobID)

	// pending → paused_user (pause allows pending|running).
	if found, changed, err := f.srv.transitionResearchJob(ctx, f.bookID, jobID, "paused_user", []string{"pending", "running"}, false, false); err != nil || !found || !changed {
		t.Fatalf("pause: found=%v changed=%v err=%v", found, changed, err)
	}
	// pause again → found but NOT changed (already paused) → 409.
	if found, changed, _ := f.srv.transitionResearchJob(ctx, f.bookID, jobID, "paused_user", []string{"pending", "running"}, false, false); !found || changed {
		t.Fatalf("re-pause: want found+unchanged, got found=%v changed=%v", found, changed)
	}
	// resume (paused_user|failed → pending) clears error.
	pool.Exec(ctx, `UPDATE entity_research_jobs SET error_message='x' WHERE job_id=$1`, jobID)
	if found, changed, _ := f.srv.transitionResearchJob(ctx, f.bookID, jobID, "pending", []string{"paused_user", "failed"}, false, true); !found || !changed {
		t.Fatalf("resume: found=%v changed=%v", found, changed)
	}
	if got, _, _ := f.srv.loadResearchJob(ctx, f.bookID, jobID); got.ErrorMessage != nil {
		t.Errorf("resume must clear error_message, got %v", *got.ErrorMessage)
	}
	// cancel (any non-terminal → cancelled).
	if found, changed, _ := f.srv.transitionResearchJob(ctx, f.bookID, jobID, "cancelled", []string{"pending", "running", "paused_user", "failed"}, true, false); !found || !changed {
		t.Fatalf("cancel: found=%v changed=%v", found, changed)
	}
	// cancel a cancelled job → 409 (not in an allowed from-state).
	if found, changed, _ := f.srv.transitionResearchJob(ctx, f.bookID, jobID, "cancelled", []string{"pending", "running", "paused_user", "failed"}, true, false); !found || changed {
		t.Fatalf("re-cancel: want found+unchanged, got found=%v changed=%v", found, changed)
	}
	// a bogus job → not found (→404).
	if found, _, _ := f.srv.transitionResearchJob(ctx, f.bookID, uuid.New(), "cancelled", []string{"pending"}, true, false); found {
		t.Fatalf("bogus job: want not-found")
	}
}

func refEvidenceCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID) int {
	t.Helper()
	var n int
	pool.QueryRow(context.Background(), `
		SELECT count(*) FROM evidences e
		JOIN entity_attribute_values av ON av.attr_value_id = e.attr_value_id
		WHERE av.entity_id=$1 AND e.evidence_type='reference'`, entityID).Scan(&n)
	return n
}
