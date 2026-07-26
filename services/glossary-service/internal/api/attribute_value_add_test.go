package api

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// S-06 — POST /entities/{id}/attributes: add a value for an attr-def added after the entity
// existed. DB-backed + full HTTP path (auth + grant + verifyEntityInBook), so it proves the
// applicability gate, the insert-or-409, and the transactional entity_updated emission.

func (f *versionFixture) post(t *testing.T, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestAddAttributeValue(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	kindID := bookKindID(t, pool, f.bookID, "character")
	attrsPath := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String() + "/attributes"

	// ── happy path: the fixture seeded only a `name` value, so `description` has no row yet.
	descAttr := bookAttrID(t, pool, f.bookID, kindID, "description")
	w := f.post(t, attrsPath, `{"attribute_def_id":"`+descAttr.String()+`","value":"A fierce youth of Chentang Pass."}`)
	if w.Code != http.StatusCreated {
		t.Fatalf("add value: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	// the row landed (verified, human-authored) …
	var val, conf string
	if err := pool.QueryRow(ctx,
		`SELECT original_value, confidence FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`,
		f.entityID, descAttr).Scan(&val, &conf); err != nil {
		t.Fatalf("added row not found: %v", err)
	}
	if val != "A fierce youth of Chentang Pass." || conf != "verified" {
		t.Fatalf("added row: want verified value, got value=%q conf=%q", val, conf)
	}
	// … and it emitted exactly one USER entity_updated event (staleness/sync/learning consumers).
	var n int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&n)
	if n != 1 {
		t.Fatalf("add must emit exactly 1 entity_updated event, got %d", n)
	}

	// ── 409: a second add for the SAME (entity, attr-def) — the value already exists (PATCH is
	//    the edit path). No overwrite, no second event.
	if w := f.post(t, attrsPath, `{"attribute_def_id":"`+descAttr.String()+`","value":"OVERWRITE?"}`); w.Code != http.StatusConflict {
		t.Fatalf("duplicate add: want 409, got %d (%s)", w.Code, w.Body.String())
	}
	pool.QueryRow(ctx,
		`SELECT original_value FROM entity_attribute_values WHERE entity_id=$1 AND attr_def_id=$2`,
		f.entityID, descAttr).Scan(&val)
	if val != "A fierce youth of Chentang Pass." {
		t.Fatalf("409 must NOT overwrite; value is now %q", val)
	}
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&n)
	if n != 1 {
		t.Fatalf("a rejected (409) add must emit no further event, still want 1, got %d", n)
	}

	// ── 409 also covers the name attr the fixture already seeded.
	nameAttr := bookAttrID(t, pool, f.bookID, kindID, "name")
	if w := f.post(t, attrsPath, `{"attribute_def_id":"`+nameAttr.String()+`","value":"x"}`); w.Code != http.StatusConflict {
		t.Fatalf("add over seeded name: want 409, got %d (%s)", w.Code, w.Body.String())
	}

	// ── 422: an attr-def from a DIFFERENT kind is not applicable to this character entity.
	locKind := bookKindID(t, pool, f.bookID, "location")
	locName := bookAttrID(t, pool, f.bookID, locKind, "name")
	if w := f.post(t, attrsPath, `{"attribute_def_id":"`+locName.String()+`","value":"nope"}`); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("cross-kind attr add: want 422, got %d (%s)", w.Code, w.Body.String())
	}

	// ── 400: missing attribute_def_id.
	if w := f.post(t, attrsPath, `{"value":"orphan"}`); w.Code != http.StatusBadRequest {
		t.Fatalf("missing attribute_def_id: want 400, got %d (%s)", w.Code, w.Body.String())
	}
}
