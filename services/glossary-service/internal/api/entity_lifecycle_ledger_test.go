package api

import (
	"context"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// readSrc — the source-reading idiom this package already uses (see
// gate_task_expiry_message_test.go); a guard on shape needs the file, not a mock.
func readSrc(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(name)
	if err != nil {
		t.Fatalf("%s unreadable (%v) — the guard cannot run", name, err)
	}
	return string(b)
}

// 🔴 THESE TESTS LEAVE THEIR LEDGER ROWS BEHIND, ON PURPOSE, AND THE FIRST VERSION
// LIED ABOUT IT.
//
// db-safety-gate: ok — the next line is PROSE describing a cleanup that was REMOVED, not a
// statement this file runs; the real deletes below are scoped `WHERE entity_id=$1`. Marked
// rather than reworded, because a guard that reads source text will match the next accurate
// description of a defect too, and the description is worth more than the silence.
//
// Cleanup called `DELETE FROM entity_lifecycle_ledger` with //nolint:errcheck — and
// the table's trigger is `trg_ell_append_only` on DELETE, which RAISEs. So the delete always
// failed, the error was swallowed, and the test read as if it tidied up. An audit trail you can
// delete from is a cache; the rows stay, and saying so is better than a cleanup that cannot run.
// The entity rows themselves ARE removed, so nothing dangles.

// A guarded table that nothing writes is worse than no table.
//
// OWNER RULING 2026-08-31, DQ-T1: "(a) EVERY STATUS TRANSITION APPENDS a row to
// entity_lifecycle_ledger, making it the audit trail its columns describe. The deciding fact is
// that somebody paid for an append-only TRIGGER on that table: that is a deliberate integrity
// guarantee, and a guarded table nothing writes is the worse of the two failures."
//
// MEASURED 2026-08-13, re-derived 2026-09-01: the table ships with an append-only trigger and
// the columns op, prior_status, new_status, actor_type, actor_id, reason — the exact vocabulary
// of a curation status change — and held THREE rows, all from a single day in August, all
// op='deleted'/'restored' with both status columns NULL. A repo-wide search found NO writer in
// source. Four entities went draft -> active live in that cycle and the ledger gained nothing.

// requires a live DB; the integration harness supplies one.
func TestStatusChangeAppendsToTheLifecycleLedger(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()

	bookID := f.bookID
	entityID := uuid.New()
	actor := uuid.New()
	// 🔴 TWO ENTITIES, NOT ONE. The first version of this test seeded a single row and
	// asserted the returned count was 1 — which is ALSO what a broken count returns, because the
	// statement ends in `SELECT count(*)` and `RowsAffected` on a select is the number of rows
	// RETURNED. It passed while the count was wrong for every multi-entity caller, and a
	// pre-existing test caught what this one could not.
	second := uuid.New()
	kindID := bookKindID(t, pool, bookID, "character")
	if _, err := pool.Exec(ctx,
		`INSERT INTO glossary_entities (entity_id, book_id, kind_id, status)
		 VALUES ($1, $3, $4, 'draft'), ($2, $3, $4, 'draft')`,
		entityID, second, bookID, kindID); err != nil {
		t.Fatalf("seeding the entities failed, so nothing below is measurable: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, second) //nolint:errcheck
	})
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) //nolint:errcheck
	})

	n, err := f.srv.bulkSetEntityStatusCore(
		ctx, bookID, "active", []uuid.UUID{entityID, second}, actor)
	if err != nil {
		t.Fatalf("bulkSetEntityStatusCore: %v", err)
	}
	if n != 2 {
		t.Fatalf("expected 2 rows updated, got %d — the caller reports this number to the "+
			"author, and a `count(*)` statement returns ONE row however many it updated", n)
	}

	var op, prior, next, actorType string
	var gotActor uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT op, coalesce(prior_status,''), coalesce(new_status,''), actor_type, actor_id
		 FROM entity_lifecycle_ledger WHERE entity_id=$1`, entityID,
	).Scan(&op, &prior, &next, &actorType, &gotActor); err != nil {
		t.Fatalf("the transition left NO ledger row — the table is still guarded and unwritten: %v", err)
	}
	if prior != "draft" || next != "active" {
		t.Fatalf("the ledger recorded %q -> %q; the whole point is the TRANSITION, and both "+
			"columns were NULL on every pre-existing row", prior, next)
	}
	if op != "status_change" {
		t.Errorf("op = %q", op)
	}
	if actorType != "user" || gotActor != actor {
		t.Errorf("actor recorded as %q/%v, want user/%v — actor_type is NOT NULL and an audit "+
			"trail that cannot say who acted is not one", actorType, gotActor, actor)
	}
}

// 🔴 A NON-EVENT MUST NOT BE AUDITED. Setting `active` on a row already `active` changes
// nothing; an audit trail that records non-events teaches its reader to distrust it.
func TestSettingTheSameStatusAppendsNothing(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()

	bookID := f.bookID
	entityID := uuid.New()
	kindID := bookKindID(t, pool, bookID, "character")
	if _, err := pool.Exec(ctx,
		`INSERT INTO glossary_entities (entity_id, book_id, kind_id, status)
		 VALUES ($1, $2, $3, 'active')`, entityID, bookID, kindID); err != nil {
		t.Fatalf("seeding the entity failed, so nothing below is measurable: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) //nolint:errcheck
	})

	if _, err := f.srv.bulkSetEntityStatusCore(
		ctx, bookID, "active", []uuid.UUID{entityID}, uuid.New()); err != nil {
		t.Fatalf("bulkSetEntityStatusCore: %v", err)
	}
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM entity_lifecycle_ledger WHERE entity_id=$1`, entityID).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 0 {
		t.Fatalf("a no-op status set appended %d ledger row(s) — the trail now records "+
			"transitions that did not happen", n)
	}
}

// The write and the transition are the same fact, so they must be one statement: a follow-up
// INSERT could fail and leave a transition with no record, which is the gap being closed.
func TestTheLedgerWriteIsInTheSAMEStatementAsTheUpdate(t *testing.T) {
	src := readSrc(t, "entity_handler.go")
	i := strings.Index(src, "func (s *Server) bulkSetEntityStatusCore")
	if i < 0 {
		t.Fatal("the status chokepoint is gone — has it moved?")
	}
	body := src[i : i+3000]
	if !strings.Contains(body, "entity_lifecycle_ledger") {
		t.Fatal("the chokepoint no longer writes the ledger")
	}
	if !strings.Contains(body, "WITH prior AS") {
		t.Error("the ledger append is no longer part of the UPDATE's own statement; a separate " +
			"write can fail and leave a transition unrecorded")
	}
	if !strings.Contains(body, "FOR UPDATE") {
		t.Error("prior_status is read without FOR UPDATE — a concurrent writer can slip a " +
			"different prior between the read and the write")
	}
	if !strings.Contains(body, "IS DISTINCT FROM") {
		t.Error("every set is appended, including no-ops")
	}
}

// GUARD THE CALL SITES. Both callers must supply an actor, or the column that is NOT NULL is
// filled with whatever zero value compiles.
func TestEveryCallerSuppliesAnActor(t *testing.T) {
	for _, f := range []string{"entity_handler.go", "pipeline_confirm.go"} {
		src := readSrc(t, f)
		for _, line := range strings.Split(src, "\n") {
			if !strings.Contains(line, "bulkSetEntityStatusCore(") ||
				strings.Contains(line, "func (s *Server)") {
				continue
			}
			if strings.Count(line, ",") < 4 {
				t.Errorf("%s: a caller passes no actor: %s", f, strings.TrimSpace(line))
			}
		}
	}
}
