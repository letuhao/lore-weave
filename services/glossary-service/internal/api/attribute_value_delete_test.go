package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// S-06 — DELETE /entities/{id}/attributes/{attr_value_id}: remove the value ROW (not just blank
// it). Proves the cascade to child rows (translations), the entity_updated emission, and the
// entity/attr-value scoping.

func (f *versionFixture) del(t *testing.T, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete, path, nil)
	req.Header.Set("Authorization", "Bearer "+f.token)
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestDeleteAttributeValue(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()
	kindID := bookKindID(t, pool, f.bookID, "character")
	descAttr := bookAttrID(t, pool, f.bookID, kindID, "description")

	// Seed a description value with a translation CHILD, so the delete proves the cascade.
	var avID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'en','A fierce youth') RETURNING attr_value_id`,
		f.entityID, descAttr).Scan(&avID); err != nil {
		t.Fatalf("seed desc value: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id,language_code,value,confidence)
		 VALUES($1,'zh','哪吒','draft')`, avID); err != nil {
		t.Fatalf("seed translation child: %v", err)
	}

	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String()
	path := base + "/attributes/" + avID.String()

	// ── 404 first: an attr-value NOT under a (random) entity is not found (entity scope).
	if w := f.del(t, "/v1/glossary/books/"+f.bookID.String()+"/entities/"+uuid.NewString()+"/attributes/"+avID.String()); w.Code != http.StatusNotFound {
		t.Fatalf("delete under wrong entity: want 404, got %d (%s)", w.Code, w.Body.String())
	}

	// ── happy path: 204, the row AND its child translation are gone (cascade).
	if w := f.del(t, path); w.Code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d (%s)", w.Code, w.Body.String())
	}
	var cnt int
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_attribute_values WHERE attr_value_id=$1`, avID).Scan(&cnt)
	if cnt != 0 {
		t.Fatalf("value row must be gone, found %d", cnt)
	}
	pool.QueryRow(ctx, `SELECT count(*) FROM attribute_translations WHERE attr_value_id=$1`, avID).Scan(&cnt)
	if cnt != 0 {
		t.Fatalf("child translation must cascade-delete, found %d", cnt)
	}
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&cnt)
	if cnt != 1 {
		t.Fatalf("delete must emit exactly 1 entity_updated event, got %d", cnt)
	}

	// ── re-delete the now-gone row → 404.
	if w := f.del(t, path); w.Code != http.StatusNotFound {
		t.Fatalf("re-delete: want 404, got %d (%s)", w.Code, w.Body.String())
	}
}
