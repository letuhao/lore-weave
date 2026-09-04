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

// funcBodyIn returns ONE function's body, from its declaration to the closing brace in
// column 0. Gofmt guarantees that brace's position, so this needs no brace counting and
// cannot be fooled by braces inside a composite literal or a raw SQL string.
//
// 🔴 It exists because the guard below used `src[i : i+3000]`. A fixed window measures the
// FILE'S LAYOUT, not the function: it covers too little the day the function grows and too
// much the day it shrinks, and in the shrinking direction it reads the NEXT function's code
// as if it were this one's. Both directions fail quietly.
func funcBodyIn(t *testing.T, file, decl string) string {
	t.Helper()
	// 🔴 CRLF-normalised, because this package is MIXED and a guard that is not agnostic
	// covers whichever half it was written on. Measured: entity_handler.go is 1780/1780 CRLF
	// while outbox_curation.go and lifecycle_ledger.go are pure LF, so a bare "\n}\n" search
	// finds the function end in two files and fails outright in the third.
	src := strings.ReplaceAll(readSrc(t, file), "\r\n", "\n")
	i := strings.Index(src, decl)
	if i < 0 {
		t.Fatalf("%s no longer declares %q — has it moved? Re-point this guard rather than "+
			"deleting it; that rename is exactly how this test came to read an empty wrapper", file, decl)
	}
	rest := src[i:]
	end := strings.Index(rest, "\n}\n")
	if end < 0 {
		t.Fatalf("no column-0 closing brace after %q in %s", decl, file)
	}
	return rest[:end]
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
	// 🔴 `status_changeD`. This asserted `status_change` and failed on every live run:
	//
	//     entity_lifecycle_ledger_test.go:130: op = "status_changed"
	//
	// TWO VOCABULARIES, and the test reached for the wrong one. `status_change` is the
	// CONFIRM-TOKEN / propose-tool action name (`descStatusChange` in
	// action_confirm_token.go; `curation_propose_tools.go` offers "status_change |
	// restore_revision | reassign_kind | merge"). The LEDGER's `op` is a different set, and
	// migration 0063 says which and why on the column itself:
	//
	//     "status_changed" / "kind_reassigned". Deliberately the same vocabulary as the
	//     outbox event's 'op', so a ledger row and its event can be read side by side
	//     without a mapping table that would itself drift.
	//
	// The event is `glossary.entity_status_changed`, so the ledger writes `status_changed`
	// and the two line up — which is the whole point. Asserting the propose-tool spelling
	// here would have forced the mapping table that comment exists to prevent.
	if op != "status_changed" {
		t.Errorf("op = %q, want \"status_changed\" — the ledger shares the outbox event's "+
			"vocabulary (glossary.entity_status_changed), NOT the propose-tool's "+
			"\"status_change\"", op)
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

// The write and the transition are the same fact, so they must commit together: a follow-up
// INSERT could fail and leave a transition with no record, which is the gap being closed.
//
// 🔴 THIS TEST WAS ANCHORED ON A FUNCTION THAT NO LONGER HOLDS THE SQL, and it failed with
// a message that was actively misleading:
//
//	entity_lifecycle_ledger_test.go:154: the chokepoint no longer writes the ledger
//
// The chokepoint still writes the ledger. T28 moved the write and its
// `glossary.entity_status_changed` emission together into `setEntityStatusCore`
// (outbox_curation.go), leaving `bulkSetEntityStatusCore` as a 214-character alias that
// "deliberately holds no SQL of its own". The old test read `src[i : i+3000]` from the WRAPPER,
// found nothing, and reported a lost audit trail.
//
// Two lessons are pinned below rather than written down. First, the guarantee is now the same
// TRANSACTION rather than the same STATEMENT — a stronger and more general form of the same
// property, and `appendLifecycleLedgerTx` enforces it in its signature by taking a `pgx.Tx` and
// no pool, so a caller cannot commit the ledger row independently. Second, the fixed-size
// window is gone: a guard that reads a fixed number of characters from a function start is
// measuring the file's layout, and it silently stops covering the code it names as soon as
// anything above it grows.
func TestTheLedgerWriteIsInTheSAMETransactionAsTheUpdate(t *testing.T) {
	ledger := funcBodyIn(t, "lifecycle_ledger.go", "func appendLifecycleLedgerTx(")
	// The structural guarantee, and the reason a same-statement check is no longer needed:
	// the appender cannot reach a pool, so its row can only commit with its caller's work.
	if !strings.Contains(ledger, "tx pgx.Tx") {
		t.Error("appendLifecycleLedgerTx no longer takes a pgx.Tx — handed a pool it could " +
			"commit independently, which is exactly the divergence the ledger exists to prevent")
	}
	if strings.Contains(ledger, "pgxpool") {
		t.Error("appendLifecycleLedgerTx reaches a pool")
	}
	if !strings.Contains(ledger, "INSERT INTO entity_lifecycle_ledger") {
		t.Fatal("appendLifecycleLedgerTx no longer inserts into entity_lifecycle_ledger")
	}

	core := funcBodyIn(t, "outbox_curation.go", "func (s *Server) setEntityStatusCore(")
	if !strings.Contains(core, "s.pool.Begin(ctx)") {
		t.Fatal("setEntityStatusCore no longer opens a transaction")
	}
	// Every write in the chokepoint must ride that tx. A stray pool call here commits outside
	// it and re-opens the gap from the other side.
	for _, stray := range []string{"s.pool.Exec(", "s.pool.Query(", "s.pool.QueryRow("} {
		if strings.Contains(core, stray) {
			t.Errorf("setEntityStatusCore calls %s — that write commits outside the transaction", stray)
		}
	}
	if !strings.Contains(core, "FOR UPDATE") {
		t.Error("prior_status is read without FOR UPDATE — a concurrent writer can slip a " +
			"different prior between the read and the write")
	}
	// The no-op skip. It used to be SQL (`IS DISTINCT FROM`) and is now the Go `continue`;
	// same property, and TestSettingTheSameStatusAppendsNothing proves it against a real DB.
	if !strings.Contains(core, "if r.status == status {") {
		t.Error("every set is appended, including no-ops")
	}

	// The emission and the ledger row are one fact, on the caller's tx.
	emit := funcBodyIn(t, "outbox_curation.go", "func emitEntityStatusChangedTx(")
	if !strings.Contains(emit, "appendLifecycleLedgerTx(ctx, tx,") {
		t.Error("the status emission no longer appends the ledger row on the same tx")
	}

	// The wrapper must stay empty. A status write that is separable from its event is a status
	// write that will be separated again — which is the whole reason T28 collapsed them.
	wrapper := funcBodyIn(t, "entity_handler.go", "func (s *Server) bulkSetEntityStatusCore(")
	if strings.Contains(wrapper, "INSERT") || strings.Contains(wrapper, "UPDATE ") {
		t.Error("bulkSetEntityStatusCore grew SQL of its own; it must delegate to setEntityStatusCore")
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
