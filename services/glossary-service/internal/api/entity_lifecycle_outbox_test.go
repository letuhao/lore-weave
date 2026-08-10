package api

import (
	"context"
	"net/http"
	"bytes"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Entity lifecycle events (plan T27).
//
// Delete, restore and purge each mutated `glossary_entities` and emitted NOTHING, so the KG
// mirror never learned about any of them. The restore half was the worst: a
// deleted-then-restored entity stayed archived downstream forever, and no retry converged
// it, because the corrective event did not exist.
//
// These tests assert on `outbox_events` rather than on the HTTP status, because the status
// was always 204 — the bug was invisible from the caller's side, which is exactly why it
// survived four call sites.

func lifecycleEventCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, eventType string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type=$2`,
		entityID, eventType).Scan(&n); err != nil {
		t.Fatalf("count %s: %v", eventType, err)
	}
	return n
}

func doLifecycle(t *testing.T, f *versionFixture, method, path string) int {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w.Code
}

func TestEntityDelete_EmitsDeletedEvent(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, base); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != 1 {
		t.Errorf("delete must emit exactly 1 glossary.entity_deleted, got %d", n)
	}
}

func TestEntityRestore_EmitsRestoredEvent(t *testing.T) {
	// The half that mattered most: without this event the entity stays ARCHIVED in the KG
	// while the glossary shows it live, and nothing ever corrects it.
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
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_restored"); n != 1 {
		t.Errorf("restore must emit exactly 1 glossary.entity_restored, got %d", n)
	}
}

func TestEntityPurge_EmitsPurgedEventNotDeleted(t *testing.T) {
	// `purged` is a DIFFERENT fact from `deleted`: soft-delete is reversible and maps to
	// archive, purge is not and maps to a cascading delete. If purge reused the deleted
	// event the consumer would have to infer which from a payload field.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}
	deletedBefore := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted")

	purge := "/v1/glossary/books/" + f.bookID.String() + "/recycle-bin/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, purge); code != http.StatusNoContent {
		t.Fatalf("purge: want 204, got %d", code)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_purged"); n != 1 {
		t.Errorf("purge must emit exactly 1 glossary.entity_purged, got %d", n)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != deletedBefore {
		t.Errorf("purge must not also emit entity_deleted (was %d, now %d)", deletedBefore, n)
	}
}

func TestEntityLifecycle_NoOpEmitsNothing(t *testing.T) {
	// An event announcing a transition that did not happen is worse than no event, because
	// a consumer acts on it. Deleting an already-deleted entity changes no row, so it must
	// stay silent — the `found=false` path.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("first delete: want 204, got %d", code)
	}
	after := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted")

	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNotFound {
		t.Fatalf("second delete: want 404, got %d", code)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != after {
		t.Errorf("a no-op delete must emit nothing (was %d, now %d)", after, n)
	}
}

func TestEntityDelete_EventCarriesActorAndBook(t *testing.T) {
	// A lifecycle audit trail that cannot say WHO deleted the entity is barely an audit
	// trail. `actor_type` must be "user" for a REST delete — the reason the actor is a
	// parameter rather than read from ctx, where only MCP sets it.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d", code)
	}
	var actorType, bookID, op string
	if err := pool.QueryRow(context.Background(),
		`SELECT payload->>'actor_type', payload->>'book_id', payload->>'op'
		 FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_deleted'`,
		f.entityID).Scan(&actorType, &bookID, &op); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if actorType != "user" {
		t.Errorf("actor_type: want user, got %q", actorType)
	}
	if bookID != f.bookID.String() {
		t.Errorf("book_id: want %s, got %s", f.bookID, bookID)
	}
	if op != "deleted" {
		t.Errorf("op: want deleted, got %q", op)
	}
}

func TestBulkDelete_EmitsOnePerEntityActuallyDeleted(t *testing.T) {
	// The count and the events come from the SAME `RETURNING` list, so they cannot
	// disagree. Passing an already-deleted id must not produce an event for it.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	entity := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	if code := doLifecycle(t, f, http.MethodDelete, entity); code != http.StatusNoContent {
		t.Fatalf("pre-delete: want 204, got %d", code)
	}
	before := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted")

	body := `{"entity_ids":["` + f.entityID.String() + `"]}`
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/bulk-delete",
		bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("bulk-delete: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != before {
		t.Errorf("bulk-delete of an already-deleted entity must emit nothing (was %d, now %d)",
			before, n)
	}
}
