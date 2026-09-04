package api

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Entity CURATION events (plan T28).
//
// `status` is a liveness predicate in this service, not a label: every consumer-facing read
// filters `status = 'active'` alongside `deleted_at IS NULL`. Retiring an entity therefore
// removed it from the glossary's own canon reads and emitted NOTHING, so the KG mirror kept
// the node and kept answering RAG queries about it. A kind reassignment was silent the same
// way, and `kind` is a field of the payload the mirror stores.
//
// These tests assert on `outbox_events`, not on the HTTP status, because both transitions
// already returned 200 while doing nothing observable — which is exactly why they survived.

func curationEventCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, eventType string) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type=$2`,
		entityID, eventType).Scan(&n); err != nil {
		t.Fatalf("count %s: %v", eventType, err)
	}
	return n
}

// bulkStatus drives the REST bulk-status route, the entry point a human uses.
func bulkStatus(t *testing.T, f *versionFixture, status string, ids ...uuid.UUID) int {
	t.Helper()
	body := `{"status":"` + status + `","entity_ids":[`
	for i, id := range ids {
		if i > 0 {
			body += ","
		}
		body += `"` + id.String() + `"`
	}
	body += `]}`
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/bulk-status",
		bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w.Code
}

func TestStatusChange_EmitsStatusChangedEvent(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if code := bulkStatus(t, f, "rejected", f.entityID); code != http.StatusOK {
		t.Fatalf("bulk-status: want 200, got %d", code)
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed"); n != 1 {
		t.Errorf("retiring an entity must emit exactly 1 status_changed, got %d", n)
	}
}

func TestStatusChange_EventCarriesBothStatusesAndActor(t *testing.T) {
	// Without `prior_status` the event is not auditable after the fact, and a consumer added
	// later cannot tell draft→active (a first publication) from rejected→active (a
	// reinstatement). `actor_type` must be "user" for a REST call — the reason the actor is a
	// parameter rather than read from ctx, where only MCP sets it.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	var before string
	if err := pool.QueryRow(context.Background(),
		`SELECT status FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&before); err != nil {
		t.Fatalf("read status: %v", err)
	}
	if before == "inactive" {
		t.Fatalf("fixture entity already inactive — the test would assert a no-op")
	}
	if code := bulkStatus(t, f, "inactive", f.entityID); code != http.StatusOK {
		t.Fatalf("bulk-status: want 200, got %d", code)
	}

	var status, prior, actorType, bookID string
	if err := pool.QueryRow(context.Background(),
		`SELECT payload->>'status', payload->>'prior_status',
		        payload->>'actor_type', payload->>'book_id'
		 FROM outbox_events
		 WHERE aggregate_id=$1 AND event_type='glossary.entity_status_changed'`,
		f.entityID).Scan(&status, &prior, &actorType, &bookID); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if status != "inactive" {
		t.Errorf("status: want inactive, got %q", status)
	}
	if prior != before {
		t.Errorf("prior_status: want %q (the value before the write), got %q", before, prior)
	}
	if actorType != "user" {
		t.Errorf("actor_type: want user, got %q", actorType)
	}
	if bookID != f.bookID.String() {
		t.Errorf("book_id: want %s, got %s", f.bookID, bookID)
	}
}

func TestStatusChange_NoOpEmitsNothing(t *testing.T) {
	// An event announcing a transition that did not happen is worse than no event, because a
	// consumer acts on it — here it would archive a KG node on every repeat of a status the
	// entity already has. The pre-T28 UPDATE had no `status <> target` guard at all, so it
	// reported every matched id as "updated"; the emission must not inherit that.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if code := bulkStatus(t, f, "rejected", f.entityID); code != http.StatusOK {
		t.Fatalf("first: want 200, got %d", code)
	}
	after := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed")
	if after != 1 {
		t.Fatalf("setup: want 1 event after the real change, got %d", after)
	}

	if code := bulkStatus(t, f, "rejected", f.entityID); code != http.StatusOK {
		t.Fatalf("second: want 200, got %d", code)
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed"); n != after {
		t.Errorf("re-setting the SAME status must emit nothing (was %d, now %d)", after, n)
	}
}

func TestStatusChange_BothEntryPointsEmitIdentically(t *testing.T) {
	// The REST bulk route and the confirm effect are the two entry points T28 exists to keep
	// converged. Asserting they produce the same emission is what stops the next change from
	// updating one and not the other — the drift the plan predicted, and the class this repo
	// has recorded twice (FastMCP strips undeclared fields; the REST mirror drops fields the
	// MCP tool accepts).
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	if code := bulkStatus(t, f, "inactive", f.entityID); code != http.StatusOK {
		t.Fatalf("REST bulk-status: want 200, got %d", code)
	}
	var restStatus, restPrior string
	if err := pool.QueryRow(ctx,
		`SELECT payload->>'status', payload->>'prior_status' FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_status_changed'
		  ORDER BY created_at DESC, id DESC LIMIT 1`, f.entityID).Scan(&restStatus, &restPrior); err != nil {
		t.Fatalf("REST payload: %v", err)
	}

	// The confirm effect reaches the same core with the token's book + user.
	updated, err := f.srv.bulkSetEntityStatusCore(ctx, f.bookID, "active", []uuid.UUID{f.entityID}, f.ownerID)
	if err != nil {
		t.Fatalf("confirm-effect core: %v", err)
	}
	if updated != 1 {
		t.Fatalf("confirm-effect core: want 1 updated, got %d", updated)
	}
	var effStatus, effPrior string
	if err := pool.QueryRow(ctx,
		`SELECT payload->>'status', payload->>'prior_status' FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_status_changed'
		  ORDER BY created_at DESC, id DESC LIMIT 1`, f.entityID).Scan(&effStatus, &effPrior); err != nil {
		t.Fatalf("confirm-effect payload: %v", err)
	}
	if effStatus != "active" || effPrior != restStatus {
		t.Errorf("the two entry points disagree: REST left status=%q, effect emitted %q→%q",
			restStatus, effPrior, effStatus)
	}
}

func TestStatusChange_CountAndEventsComeFromOneList(t *testing.T) {
	// The count returned to the caller and the events emitted are read off the SAME locked
	// row list, so they cannot disagree. An id outside the book must contribute to neither.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	stranger := uuid.New()
	if code := bulkStatus(t, f, "rejected", f.entityID, stranger); code != http.StatusOK {
		t.Fatalf("bulk-status: want 200, got %d", code)
	}
	if n := curationEventCount(t, pool, stranger, "glossary.entity_status_changed"); n != 0 {
		t.Errorf("an id outside the book must emit nothing, got %d", n)
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed"); n != 1 {
		t.Errorf("the in-book id must emit exactly 1, got %d", n)
	}
}

func TestReassignKind_EmitsUpdatedCarryingTheNewKind(t *testing.T) {
	// A re-key emitted nothing, and `kind` is a field of the entity_updated payload the KG
	// mirror stores — so an entity that moved kind kept the old one in the graph forever,
	// with no event that would ever correct it. Asserting the payload's kind (not merely that
	// an event exists) is the point: an event carrying the OLD kind would be no better.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	kinds, err := f.srv.loadKindMap(ctx, f.bookID)
	if err != nil {
		t.Fatalf("loadKindMap: %v", err)
	}
	var currentKind uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT kind_id FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&currentKind); err != nil {
		t.Fatalf("read kind: %v", err)
	}
	targetCode, targetID := "", uuid.Nil
	for code, id := range kinds {
		if id != currentKind {
			targetCode, targetID = code, id
			break
		}
	}
	if targetID == uuid.Nil {
		t.Skip("book ontology has only one kind — nothing to reassign to")
	}

	// 🔴 `ORDER BY created_at DESC` ALONE DOES NOT NAME A ROW. `outbox_events.created_at`
	// defaults to `now()`, which in Postgres is TRANSACTION START time — every row written in
	// one transaction carries a byte-identical timestamp, so "the latest" is a tie the planner
	// breaks however it likes. This entity already has earlier `entity_updated` rows (that is
	// what `before` counts), and the reads below take `LIMIT 1` off that tie.
	//
	// It went green here and RED in CI on consecutive runs of the same commit:
	//
	//     entity_curation_outbox_test.go:240: payload kind: want the NEW kind "generic",
	//     got "terminology"
	//
	// — the OLD event, read as the newest. `id` is `uuidv7()`, which is time-ordered, so
	// `, id DESC` is a real monotonic tiebreaker rather than an arbitrary one.
	// `entity_command_parity_test.go` in this package already orders that way; these three
	// reads did not.
	before := curationEventCount(t, pool, f.entityID, "glossary.entity_updated")
	if err := f.srv.reassignEntityKindCore(ctx, f.bookID, f.entityID, targetID, f.ownerID); err != nil {
		t.Fatalf("reassignEntityKindCore: %v", err)
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_updated"); n != before+1 {
		t.Fatalf("a re-key must emit exactly 1 entity_updated (was %d, now %d)", before, n)
	}
	var kind, actorType string
	if err := pool.QueryRow(ctx,
		`SELECT payload->>'kind', payload->>'actor_type' FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'
		  ORDER BY created_at DESC, id DESC LIMIT 1`, f.entityID).Scan(&kind, &actorType); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if kind != targetCode {
		t.Errorf("payload kind: want the NEW kind %q, got %q", targetCode, kind)
	}
	if actorType != "user" {
		t.Errorf("actor_type: want user, got %q", actorType)
	}
}

func TestAutoShortDescription_ReportsWhetherItActuallyMoved(t *testing.T) {
	// The two POST-COMMIT callers emit `entity_updated` INSIDE their transaction and then
	// rewrite `short_description` after the commit. Without a truthful "did it change" signal
	// they cannot know whether to announce the rewrite — and before T29 they did not announce
	// it at all, so the mirror kept the pre-edit summary forever, in the one field the
	// composition packer reads for a cast bio.
	//
	// This is the half a static gate cannot check. The gate proves a mirrored-content writer
	// emits or has a named emitting caller; it cannot prove the emit happens AFTER the write.
	// Only the return contract asserted here can.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	// A deliberately WRONG summary rather than an empty one: a CHECK constraint forbids
	// empty, and "stale" is the state this test is about anyway.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET short_description='stale placeholder',
		        short_description_auto=true
		  WHERE entity_id=$1`, f.entityID); err != nil {
		t.Fatalf("seed: %v", err)
	}

	changed, err := f.srv.regenerateAutoShortDescription(ctx, pool, f.entityID)
	if err != nil {
		t.Fatalf("regenerate: %v", err)
	}
	if !changed {
		t.Fatal("regenerating over a STALE summary must report changed=true")
	}

	// Idempotence is the other half: re-running must report false, or the post-commit callers
	// would emit an event on every edit that moved nothing — and a consumer acts on those.
	again, err := f.srv.regenerateAutoShortDescription(ctx, pool, f.entityID)
	if err != nil {
		t.Fatalf("regenerate again: %v", err)
	}
	if again {
		t.Error("re-running with nothing to change must report changed=false")
	}
}
