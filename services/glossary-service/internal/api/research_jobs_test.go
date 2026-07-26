package api

import (
	"context"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// TestResearchJob_CRUD_RealPG covers the M1 cores against real PG: kind validation,
// live-entity count, insert→load round-trip (status/items_total/est_cost), the list,
// and the one-live-per-(book,kind) unique constraint (a second pending job → conflict).
func TestResearchJob_CRUD_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	if err := migrate.UpEntityResearchJobs(ctx, pool); err != nil {
		t.Fatalf("UpEntityResearchJobs: %v", err)
	}
	kindID := bookKindID(t, pool, f.bookID, "character")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_research_jobs WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND kind_id=$2`, f.bookID, kindID)
	})

	// seed 3 live entities of the kind + 1 soft-deleted (must NOT count).
	mkEntity := func(deleted bool) {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
			f.bookID, kindID).Scan(&id); err != nil {
			t.Fatalf("seed entity: %v", err)
		}
		if deleted {
			pool.Exec(ctx, `UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, id)
		}
	}
	mkEntity(false)
	mkEntity(false)
	mkEntity(false)
	mkEntity(true)

	// kind validation
	if live, err := f.srv.bookKindIsLive(ctx, f.bookID, kindID); err != nil || !live {
		t.Fatalf("bookKindIsLive(real) = %v err=%v, want true", live, err)
	}
	if live, _ := f.srv.bookKindIsLive(ctx, f.bookID, uuid.New()); live {
		t.Fatalf("bookKindIsLive(bogus) = true, want false")
	}

	// live count ignores the soft-deleted row.
	if n, err := f.srv.countLiveEntitiesOfKind(ctx, f.bookID, kindID); err != nil || n != 3 {
		t.Fatalf("countLiveEntitiesOfKind = %d err=%v, want 3", n, err)
	}

	// insert → load round-trip. items_total = min(max_entities=2, count=3) = 2 (handler logic;
	// here we pass the scoped value the handler would compute).
	view, err := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "history of {name}", 5, 2, 2, 0.02)
	if err != nil {
		t.Fatalf("insertResearchJob: %v", err)
	}
	if view.Status != "pending" || view.ItemsTotal != 2 || view.MaxResults != 5 || view.MaxEntities != 2 {
		t.Fatalf("created job fields wrong: %+v", view)
	}
	if view.EstCostUSD != "0.0200" {
		t.Errorf("est_cost rendered %q, want 0.0200", view.EstCostUSD)
	}
	if view.QueryTemplate != "history of {name}" {
		t.Errorf("query_template lost: %q", view.QueryTemplate)
	}

	jobID := uuid.MustParse(view.JobID)
	if got, found, err := f.srv.loadResearchJob(ctx, f.bookID, jobID); err != nil || !found || got.JobID != view.JobID {
		t.Fatalf("loadResearchJob round-trip: found=%v err=%v", found, err)
	}
	// a bogus job id (or another book) → not found, no error.
	if _, found, err := f.srv.loadResearchJob(ctx, f.bookID, uuid.New()); err != nil || found {
		t.Fatalf("loadResearchJob(bogus): found=%v err=%v, want not-found", found, err)
	}

	// list contains it.
	if jobs, err := f.srv.loadResearchJobs(ctx, f.bookID, ""); err != nil || len(jobs) != 1 {
		t.Fatalf("loadResearchJobs = %d jobs err=%v, want 1", len(jobs), err)
	}
	// status filter that matches none.
	if jobs, err := f.srv.loadResearchJobs(ctx, f.bookID, "complete"); err != nil || len(jobs) != 0 {
		t.Fatalf("loadResearchJobs(status=complete) = %d, want 0", len(jobs))
	}

	// one-live-per-(book,kind): a second PENDING job for the same kind violates the
	// partial unique index → the handler maps this to 409.
	if _, err := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "again", 5, 2, 2, 0.02); !isUniqueViolation(err) {
		t.Fatalf("second live job: want unique violation, got %v", err)
	}

	// once the first job is terminal, a new job is allowed (the partial index frees the slot).
	pool.Exec(ctx, `UPDATE entity_research_jobs SET status='complete', completed_at=now() WHERE job_id=$1`, jobID)
	if _, err := f.srv.insertResearchJob(ctx, f.bookID, f.ownerID, kindID, "after complete", 5, 1, 1, 0.01); err != nil {
		t.Fatalf("new job after the prior completed: %v", err)
	}
}
