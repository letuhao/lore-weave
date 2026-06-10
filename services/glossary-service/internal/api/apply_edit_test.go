package api

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// EDIT-ATOMIC — the multi-field, single-tx, single-version-gate apply-edit
// endpoint. DB-backed (real PG): one atomic write, 412-rolls-back-fully, and an
// attr that doesn't belong is rejected without a partial write.

func (f *versionFixture) applyEdit(t *testing.T, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost,
		"/v1/glossary/books/"+f.bookID.String()+"/entities/"+f.entityID.String()+"/apply-edit",
		bytes.NewBufferString(body))
	req.Header.Set("Authorization", "Bearer "+f.token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestApplyEntityEdit_MultiFieldAtomic(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	base := f.currentVersion(t, pool)

	body := `{"base_version":"` + base + `","short_description":"A fierce youth","attributes":[{"attr_value_id":"` + f.nameAttrVal.String() + `","original_value":"Nezha III"}]}`
	if w := f.applyEdit(t, body); w.Code != http.StatusOK {
		t.Fatalf("multi-field apply: want 200, got %d (%s)", w.Code, w.Body.String())
	}

	ctx := context.Background()
	var name, shortDesc string
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, f.nameAttrVal).Scan(&name)
	pool.QueryRow(ctx, `SELECT COALESCE(short_description,'') FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&shortDesc)
	if name != "Nezha III" {
		t.Errorf("name attr: want 'Nezha III', got %q", name)
	}
	if shortDesc != "A fierce youth" {
		t.Errorf("short_description: want 'A fierce youth', got %q", shortDesc)
	}
	// version advanced exactly once (the edit is now stale for a replay).
	if f.currentVersion(t, pool) == base {
		t.Error("apply-edit must bump updated_at")
	}
	// AC2: the whole multi-field edit emits exactly ONE glossary.entity_updated
	// event (not one per field).
	var nEvents int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&nEvents)
	if nEvents != 1 {
		t.Errorf("multi-field apply must emit exactly 1 entity_updated event, got %d", nEvents)
	}
}

func TestApplyEntityEdit_StaleVersionRollsBackFully(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	body := `{"base_version":"2000-01-01T00:00:00Z","short_description":"x","attributes":[{"attr_value_id":"` + f.nameAttrVal.String() + `","original_value":"CHANGED"}]}`
	if w := f.applyEdit(t, body); w.Code != http.StatusPreconditionFailed {
		t.Fatalf("stale base_version: want 412, got %d (%s)", w.Code, w.Body.String())
	}
	// NO partial write — the name attr is untouched.
	var name string
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, f.nameAttrVal).Scan(&name)
	if name != "Nezha" {
		t.Errorf("412 must roll back fully: name should stay 'Nezha', got %q", name)
	}
}

func TestApplyEntityEdit_UnknownAttrRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	base := f.currentVersion(t, pool)

	// a well-formed UUID that is not an attr of this entity → 422, whole tx rolls back.
	body := `{"base_version":"` + base + `","short_description":"y","attributes":[{"attr_value_id":"` + uuid.NewString() + `","original_value":"x"}]}`
	if w := f.applyEdit(t, body); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("unknown attr: want 422, got %d (%s)", w.Code, w.Body.String())
	}
	// short_description must NOT have been written (rollback).
	var sd string
	pool.QueryRow(ctx, `SELECT COALESCE(short_description,'') FROM glossary_entities WHERE entity_id=$1`, f.entityID).Scan(&sd)
	if sd == "y" {
		t.Error("422 must roll back the short_description write too")
	}
}
