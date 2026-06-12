package api

import (
	"context"
	"net/http"
	"testing"
)

// D-WIKI-W2-ATTR-EMIT — the manual UI's primary edit path is the single-attribute
// PATCH (patchAttributeValue). Before this fix it wrote the value + bumped the
// entity version but emitted NO glossary.entity_updated event, so a manual
// attribute edit never reached the wiki-staleness consumer, glossary_sync→Neo4j,
// or learning-service. These DB-backed tests pin that an attr edit now emits
// exactly one USER-actor event, and that a rejected edit emits none.

func TestPatchAttributeValue_EmitsUserEntityUpdated(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	path := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String() +
		"/attributes/" + f.nameAttrVal.String()

	// No-If-Match success (the /v1 UI path) → 200 + exactly one event.
	if w := f.patch(t, path, `{"original_value":"Nezha III"}`, ""); w.Code != http.StatusOK {
		t.Fatalf("attr PATCH: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&n)
	if n != 1 {
		t.Fatalf("attr PATCH must emit exactly 1 entity_updated event, got %d", n)
	}

	// It is a USER correction (actor_type='user') so learning-service ingests it
	// AND the wiki-staleness consumer (actor-agnostic) fires.
	var actor string
	pool.QueryRow(ctx,
		`SELECT payload->>'actor_type' FROM outbox_events
		 WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&actor)
	if actor != "user" {
		t.Errorf("attr edit by the book owner must emit actor_type='user', got %q", actor)
	}
}

func TestPatchAttributeValue_StaleVersionEmitsNoEvent(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	path := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String() +
		"/attributes/" + f.nameAttrVal.String()

	// Stale If-Match → 412, the tx rolls back → NO event leaks.
	if w := f.patch(t, path, `{"original_value":"Nezha III"}`, "2000-01-01T00:00:00Z"); w.Code != http.StatusPreconditionFailed {
		t.Fatalf("stale If-Match: want 412, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&n)
	if n != 0 {
		t.Errorf("a rejected (412) attr edit must emit no event, got %d", n)
	}
}
