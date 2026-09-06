package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// The physical lifecycle ledger (plan T31 / design D5).
//
// `glossary_entities.deleted_at` answers "is it gone NOW" and forgets everything else. A
// delete followed by a restore leaves it NULL — byte-identical to an entity nobody ever
// touched — so the four services keeping four private notions of "gone" (D-ENTITY-LIFECYCLE)
// could never be reconciled after the fact. The ledger is the history those columns discard.
//
// These tests assert on rows in `entity_lifecycle_ledger`, not on HTTP status, for the same
// reason the T27 tests do: the status was always 204, which is precisely why the missing
// write survived four call sites.

// doLifecycle's sibling for the curation axis, which needs a JSON body.
func doLifecycleBody(t *testing.T, f *versionFixture, method, path, body string) int {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w.Code
}

func ledgerRows(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID) []string {
	t.Helper()
	rows, err := pool.Query(context.Background(),
		`SELECT op FROM entity_lifecycle_ledger WHERE entity_id=$1 ORDER BY ledger_id`, entityID)
	if err != nil {
		t.Fatalf("read ledger: %v", err)
	}
	defer rows.Close()
	var ops []string
	for rows.Next() {
		var op string
		if err := rows.Scan(&op); err != nil {
			t.Fatalf("scan ledger: %v", err)
		}
		ops = append(ops, op)
	}
	return ops
}

func TestLifecycleLedger_RecordsDeleteRestoreInOrder(t *testing.T) {
	// The pair is the point. Two rows survive a round trip that leaves `deleted_at` NULL and
	// therefore indistinguishable from an untouched entity.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}
	restore := "/v1/glossary/books/" + f.bookID.String() +
		"/recycle-bin/" + f.entityID.String() + "/restore"
	if code := doLifecycle(t, f, http.MethodPost, restore); code != http.StatusNoContent {
		t.Fatalf("restore: want 204, got %d", code)
	}

	ops := ledgerRows(t, pool, f.entityID)
	if len(ops) != 2 || ops[0] != "deleted" || ops[1] != "restored" {
		t.Fatalf("ledger must record both transitions in order, got %v", ops)
	}

	// And the column it is meant to outlive says nothing at all by now.
	var deletedAt *string
	if err := pool.QueryRow(context.Background(),
		`SELECT deleted_at::text FROM glossary_entities WHERE entity_id=$1`,
		f.entityID).Scan(&deletedAt); err != nil {
		t.Fatalf("read deleted_at: %v", err)
	}
	if deletedAt != nil {
		t.Fatalf("precondition: after a restore deleted_at should be NULL, got %q", *deletedAt)
	}
}

func TestLifecycleLedger_WrittenInTheSameTransactionAsTheEvent(t *testing.T) {
	// The invariant the architecture diagram draws as one `rect`: the ledger row, the outbox
	// row and the mutation commit together or not at all. Asserted as "the counts agree",
	// because a ledger row without its event (or the reverse) is the exact divergence both
	// mechanisms exist to prevent.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}
	events := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted")
	ops := ledgerRows(t, pool, f.entityID)
	if events != 1 || len(ops) != 1 {
		t.Fatalf("one delete must produce exactly one event and one ledger row; got %d event(s), %d ledger row(s)",
			events, len(ops))
	}
}

func TestLifecycleLedger_IsAppendOnly(t *testing.T) {
	// A ledger you can UPDATE is a cache with extra steps. Enforced in the schema rather than
	// by convention, because this is the audit trail for entity deletion and the day something
	// tries to rewrite it, failing loudly beats succeeding quietly.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}

	_, err := pool.Exec(context.Background(),
		`UPDATE entity_lifecycle_ledger SET op='tampered' WHERE entity_id=$1`, f.entityID)
	if err == nil {
		t.Fatal("UPDATE on the ledger succeeded — the append-only trigger is not installed, " +
			"so the deletion audit trail can be rewritten in place")
	}
	if !strings.Contains(err.Error(), "append-only") {
		t.Fatalf("UPDATE failed for the wrong reason (%v) — the test would pass on any error, "+
			"including a typo'd column name, so it must check the trigger spoke", err)
	}

	_, err = pool.Exec(context.Background(),
		`DELETE FROM entity_lifecycle_ledger WHERE entity_id=$1`, f.entityID)
	if err == nil {
		t.Fatal("DELETE on the ledger succeeded — history can be erased")
	}
	if !strings.Contains(err.Error(), "append-only") {
		t.Fatalf("DELETE failed for the wrong reason: %v", err)
	}
}

func TestLifecycleLedger_BulkDeleteIsRecordedToo(t *testing.T) {
	// Found by the bite, not by design: `bulkDeleteEntitiesCore` does not go through
	// `lifecycleEntityCore` — it emits per entity directly — so it emitted events and wrote no
	// ledger rows at all. The ledger would have been silently incomplete for precisely the
	// operation that removes the most entities at once, which is the worst place to have a
	// hole in an audit trail.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	body := `{"entity_ids":["` + f.entityID.String() + `"]}`
	path := "/v1/glossary/books/" + f.bookID.String() + "/entities/bulk-delete"
	if code := doLifecycleBody(t, f, http.MethodPost, path, body); code != http.StatusOK {
		t.Fatalf("bulk-delete: want 200, got %d", code)
	}

	var op, reason string
	if err := pool.QueryRow(context.Background(),
		`SELECT op, coalesce(reason,'') FROM entity_lifecycle_ledger
		  WHERE entity_id=$1 ORDER BY ledger_id DESC LIMIT 1`,
		f.entityID).Scan(&op, &reason); err != nil {
		t.Fatalf("a bulk delete wrote no ledger row: %v", err)
	}
	if op != "deleted" {
		t.Fatalf("bulk delete must record op=deleted, got %q", op)
	}
	// The reason distinguishes it from a single delete. Same transition, different route, and
	// an audit trail that cannot tell them apart cannot answer "was this one click or a sweep".
	if reason != "bulk_delete" {
		t.Fatalf("bulk delete must record how it happened, got reason=%q", reason)
	}
}

func TestLifecycleLedger_StatusChangeCarriesTheValueItCameFrom(t *testing.T) {
	// On the curation axis the PRIOR value is the whole point. `status` is a liveness
	// predicate — every consumer read filters `status='active'` — so "went from active to
	// rejected" and "was created rejected" are different facts, and the column alone cannot
	// tell them apart once the write has landed.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	body := `{"entity_ids":["` + f.entityID.String() + `"],"status":"rejected"}`
	path := "/v1/glossary/books/" + f.bookID.String() + "/entities/bulk-status"
	if code := doLifecycleBody(t, f, http.MethodPost, path, body); code != http.StatusOK {
		t.Fatalf("bulk-status: want 200, got %d", code)
	}

	var op, prior, next string
	if err := pool.QueryRow(context.Background(),
		`SELECT op, coalesce(prior_status,''), coalesce(new_status,'')
		   FROM entity_lifecycle_ledger WHERE entity_id=$1 ORDER BY ledger_id DESC LIMIT 1`,
		f.entityID).Scan(&op, &prior, &next); err != nil {
		t.Fatalf("read ledger: %v", err)
	}
	if op != "status_changed" || prior != "active" || next != "rejected" {
		t.Fatalf("ledger must record the transition it made: got op=%q %q -> %q", op, prior, next)
	}
}
