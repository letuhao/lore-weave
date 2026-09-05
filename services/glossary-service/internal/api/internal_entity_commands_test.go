package api

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// The KAL's entity-command surface (plan T29).
//
// T27/T28 made five transitions safe but left them reachable only from the browser's REST
// route and the agent's MCP tool. These tests pin the SERVICE path: that it reaches the same
// cores (so the same events are emitted), that the forwarded actor is honoured rather than
// invented, and that a no-op is distinguishable from a success.

func internalCmd(t *testing.T, f *versionFixture, path, body, userID string) *httptest.ResponseRecorder {
	t.Helper()
	var r *http.Request
	if body == "" {
		r = httptest.NewRequest(http.MethodPost, path, nil)
	} else {
		r = httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
		r.Header.Set("Content-Type", "application/json")
	}
	r.Header.Set("X-Internal-Token", "tok")
	if userID != "" {
		r.Header.Set("X-User-Id", userID)
	}
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, r)
	return w
}

func entityPath(f *versionFixture, verb string) string {
	return "/internal/books/" + f.bookID.String() + "/entities/" + f.entityID.String() + "/" + verb
}

func TestInternalEntityDelete_EmitsThroughTheSameCore(t *testing.T) {
	// The point of routing a service through the core rather than letting it write: the
	// lifecycle event is emitted here exactly as it is for a browser delete. A command surface
	// that reached the table directly would be the fourth silent writer T27 was written for.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if w := internalCmd(t, f, entityPath(f, "delete"), "", f.ownerID.String()); w.Code != http.StatusOK {
		t.Fatalf("delete: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != 1 {
		t.Errorf("a KAL delete must emit exactly 1 glossary.entity_deleted, got %d", n)
	}
}

func TestInternalEntityCommands_NoOpIs404NotSuccess(t *testing.T) {
	// "I did it" and "there was nothing to do" are different answers, and a caller that cannot
	// tell them apart will retry forever or stop too early. Restoring an entity that was never
	// deleted changes nothing, so it must not report success.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if w := internalCmd(t, f, entityPath(f, "restore"), "", f.ownerID.String()); w.Code != http.StatusNotFound {
		t.Errorf("restoring a live entity: want 404, got %d", w.Code)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_restored"); n != 0 {
		t.Errorf("a no-op restore must emit nothing, got %d", n)
	}
}

func TestInternalEntityDelete_ForwardedActorIsRecorded(t *testing.T) {
	// The KAL forwards X-User-Id when a caller identity exists. Honouring it is what keeps the
	// audit trail able to say WHO retired an entity through the service path.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if w := internalCmd(t, f, entityPath(f, "delete"), "", f.ownerID.String()); w.Code != http.StatusOK {
		t.Fatalf("delete: want 200, got %d", w.Code)
	}
	var actorType, actorID string
	if err := pool.QueryRow(context.Background(),
		`SELECT payload->>'actor_type', coalesce(payload->>'actor_id','')
		   FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_deleted'`,
		f.entityID).Scan(&actorType, &actorID); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if actorType != "user" || actorID != f.ownerID.String() {
		t.Errorf("forwarded actor lost: got actor_type=%q actor_id=%q", actorType, actorID)
	}
}

func TestInternalEntityDelete_AbsentActorIsPipelineNotAFakeUser(t *testing.T) {
	// A pipeline's own command carries no identity, and the event must say so. Recording the
	// nil UUID as a user would put an all-zero "user" in the audit trail — worse than silence,
	// because a downstream owner-guard would treat it as real.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if w := internalCmd(t, f, entityPath(f, "delete"), "", ""); w.Code != http.StatusOK {
		t.Fatalf("delete: want 200, got %d", w.Code)
	}
	var actorType, actorID string
	if err := pool.QueryRow(context.Background(),
		`SELECT payload->>'actor_type', coalesce(payload->>'actor_id','')
		   FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_deleted'`,
		f.entityID).Scan(&actorType, &actorID); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if actorType != "pipeline" {
		t.Errorf("actor_type: want pipeline, got %q", actorType)
	}
	if actorID != "" {
		t.Errorf("actor_id must be EMPTY for a pipeline command, got %q", actorID)
	}
}

func TestInternalEntityDelete_GarbledActorDegradesRatherThanRejects(t *testing.T) {
	// Authority comes from the internal token, not this header. A malformed id must not fail a
	// legitimate command — but it must not be silently promoted to a user either.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	if w := internalCmd(t, f, entityPath(f, "delete"), "", "not-a-uuid"); w.Code != http.StatusOK {
		t.Fatalf("delete with a garbled actor: want 200, got %d", w.Code)
	}
	var actorType string
	if err := pool.QueryRow(context.Background(),
		`SELECT payload->>'actor_type' FROM outbox_events
		  WHERE aggregate_id=$1 AND event_type='glossary.entity_deleted'`,
		f.entityID).Scan(&actorType); err != nil {
		t.Fatalf("read payload: %v", err)
	}
	if actorType != "pipeline" {
		t.Errorf("a garbled actor must degrade to pipeline, got %q", actorType)
	}
}

func TestInternalEntityStatus_EmitsThroughTheCuratedCore(t *testing.T) {
	// The T28 axis over the service path. `status` is a liveness predicate, so a service
	// retiring an entity must reach the same emission a human's retire does.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	body := `{"status":"rejected","entity_ids":["` + f.entityID.String() + `"]}`
	w := internalCmd(t, f, "/internal/books/"+f.bookID.String()+"/entities/status", body, f.ownerID.String())
	if w.Code != http.StatusOK {
		t.Fatalf("status: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed"); n != 1 {
		t.Errorf("a KAL status change must emit exactly 1 status_changed, got %d", n)
	}
}

func TestInternalEntityStatus_RejectsAnInvalidStatus(t *testing.T) {
	// The closed set is the same one the REST route enforces. A command surface that accepted
	// a status the browser route refuses would let a service write a value nothing can read.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	body := `{"status":"retired","entity_ids":["` + f.entityID.String() + `"]}`
	w := internalCmd(t, f, "/internal/books/"+f.bookID.String()+"/entities/status", body, f.ownerID.String())
	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("want 422 for an out-of-set status, got %d", w.Code)
	}
	if n := curationEventCount(t, pool, f.entityID, "glossary.entity_status_changed"); n != 0 {
		t.Errorf("a rejected command must emit nothing, got %d", n)
	}
}

func TestInternalEntityCommands_CannotReachAnotherBook(t *testing.T) {
	// Book scoping lives in the core, and this asserts the command surface does not route
	// around it: an entity addressed under the WRONG book must not be touched. A command
	// surface that leaked across books would be a tenancy hole reachable by any service.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	other := uuid.New()
	path := "/internal/books/" + other.String() + "/entities/" + f.entityID.String() + "/delete"
	if w := internalCmd(t, f, path, "", f.ownerID.String()); w.Code != http.StatusNotFound {
		t.Errorf("cross-book delete: want 404, got %d", w.Code)
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != 0 {
		t.Errorf("a cross-book command must emit nothing, got %d", n)
	}
	var deleted *string
	if err := pool.QueryRow(context.Background(),
		`SELECT deleted_at::text FROM glossary_entities WHERE entity_id=$1`,
		f.entityID).Scan(&deleted); err != nil {
		t.Fatalf("read entity: %v", err)
	}
	if deleted != nil {
		t.Error("a cross-book command must not have deleted the entity")
	}
}

func TestInternalEntityCommands_RequireTheInternalToken(t *testing.T) {
	// The whole authority model rests on this one header. If the router ever mounts these
	// outside the gated subtree, every service on the network gains entity deletion.
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)

	r := httptest.NewRequest(http.MethodPost, entityPath(f, "delete"), nil)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, r)
	if w.Code == http.StatusOK {
		t.Fatal("an untokened entity command must not succeed")
	}
	if n := lifecycleEventCount(t, pool, f.entityID, "glossary.entity_deleted"); n != 0 {
		t.Errorf("an untokened command must emit nothing, got %d", n)
	}
}
