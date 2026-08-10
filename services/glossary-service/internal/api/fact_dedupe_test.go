package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Write-time dedupe (plan T34 / design D7).
//
// Every chapter that mentions an entity re-asserts its attributes, and each assertion opened a
// NEW interval — even when nothing had changed. Measured: **11.7 % of all fact rows carried no
// new information**, `gender` alone **93.2 %**, and the share grows with chapter count because
// re-assertions scale with the book while real changes do not.
//
// The task's bite is the shape of these tests: *re-extract a processed chapter — fact count
// must not grow, evidence count must.*

func factCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, attr string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM entity_facts WHERE entity_id=$1 AND attr_or_predicate=$2`,
		entityID, attr).Scan(&n); err != nil {
		t.Fatalf("count facts: %v", err)
	}
	return n
}

func evidenceCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, attr string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(), `
		SELECT count(*) FROM entity_fact_evidence e
		  JOIN entity_facts f ON f.fact_id = e.fact_id
		 WHERE f.entity_id=$1 AND f.attr_or_predicate=$2`,
		entityID, attr).Scan(&n); err != nil {
		t.Fatalf("count evidence: %v", err)
	}
	return n
}

func TestFactDedupe_UnchangedValueAttachesEvidenceInsteadOfAnInterval(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	// Committed on purpose: the counts are read on the pool afterwards, which is also how a
	// second extraction run would see them.
	ep1, _, err := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 1, "h1", "")
	if err != nil {
		t.Fatalf("episode 1: %v", err)
	}
	ep2, _, err := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 2, "h2", "")
	if err != nil {
		t.Fatalf("episode 2: %v", err)
	}
	first, inserted1, err := appendFact(ctx, tx, appendFactParams{
		BookID: f.bookID, EntityID: f.entityID, FactKind: "attribute", Attr: "gender",
		Value: "female", ValidFrom: 1, Card: "single", SourceEpisodeID: &ep1,
	})
	if err != nil || !inserted1 {
		t.Fatalf("first append: err=%v inserted=%v", err, inserted1)
	}
	// Chapter 2 re-asserts the SAME value. This is the 93.2 % case.
	second, inserted2, err := appendFact(ctx, tx, appendFactParams{
		BookID: f.bookID, EntityID: f.entityID, FactKind: "attribute", Attr: "gender",
		Value: "female", ValidFrom: 2, Card: "single", SourceEpisodeID: &ep2,
	})
	if err != nil {
		t.Fatalf("second append: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}

	if inserted2 {
		t.Fatal("an unchanged re-assertion opened a NEW interval — this is the 11.7% of rows " +
			"that carry no information, and it is what T34 removes")
	}
	if second != first {
		t.Fatalf("the re-assertion returned a different fact (%s vs %s) — it must attach to the "+
			"OPEN fact, or the citation hangs off a row nothing reads", second, first)
	}
	if n := factCount(t, pool, f.entityID, "gender"); n != 1 {
		t.Fatalf("fact count must stay 1 across an unchanged re-assertion, got %d", n)
	}
	if n := evidenceCount(t, pool, f.entityID, "gender"); n != 1 {
		t.Fatalf("the re-assertion must be recorded as evidence (want 1 citation), got %d.\n"+
			"  Dropping it silently would lose WHERE the value was re-confirmed, which is the "+
			"half of the row that was worth keeping.", n)
	}
}

func TestFactDedupe_AChangedValueStillOpensAnInterval(t *testing.T) {
	// The control, and the one that stops this being data loss. Dedupe that swallowed a real
	// change would make the fact log claim a value held for the whole book — silently, because
	// the chain would still be well-formed.
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	ep1, _, _ := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 1, "c1", "")
	ep2, _, _ := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 5, "c2", "")
	if _, _, err := appendFact(ctx, tx, appendFactParams{
		BookID: f.bookID, EntityID: f.entityID, FactKind: "attribute", Attr: "rank",
		Value: "outer disciple", ValidFrom: 1, Card: "single", SourceEpisodeID: &ep1,
	}); err != nil {
		t.Fatalf("first: %v", err)
	}
	_, inserted, err := appendFact(ctx, tx, appendFactParams{
		BookID: f.bookID, EntityID: f.entityID, FactKind: "attribute", Attr: "rank",
		Value: "inner disciple", ValidFrom: 5, Card: "single", SourceEpisodeID: &ep2,
	})
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}
	if !inserted {
		t.Fatal("a CHANGED value was deduped away — the fact log would claim the old value " +
			"held for the whole book, and the chain would still look well-formed")
	}
	if n := factCount(t, pool, f.entityID, "rank"); n != 2 {
		t.Fatalf("a real change must open a second interval, got %d fact(s)", n)
	}
}

func TestFactDedupe_ReExtractingTheSameChapterGrowsNeitherTable(t *testing.T) {
	// The other half of idempotence. "The fact count did not grow" is only half a claim: if
	// the citation count grew on every re-run, the same unbounded growth would just have moved
	// to a different table.
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	ep1, _, _ := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 1, "r1", "")
	ep2, _, _ := ingestEpisode(ctx, tx, f.bookID, uuid.New(), 2, "r2", "")
	for _, ep := range []uuid.UUID{ep1, ep2, ep2, ep2} { // ch.2 extracted three times
		ord := int64(1)
		if ep == ep2 {
			ord = 2
		}
		e := ep
		if _, _, err := appendFact(ctx, tx, appendFactParams{
			BookID: f.bookID, EntityID: f.entityID, FactKind: "attribute", Attr: "gender",
			Value: "female", ValidFrom: ord, Card: "single", SourceEpisodeID: &e,
		}); err != nil {
			t.Fatalf("append: %v", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}

	if n := factCount(t, pool, f.entityID, "gender"); n != 1 {
		t.Fatalf("fact count after 3 re-extracts of ch.2 must be 1, got %d", n)
	}
	if n := evidenceCount(t, pool, f.entityID, "gender"); n != 1 {
		t.Fatalf("evidence count after 3 re-extracts of the SAME chapter must be 1, got %d — "+
			"unbounded growth just moved to another table", n)
	}
}
