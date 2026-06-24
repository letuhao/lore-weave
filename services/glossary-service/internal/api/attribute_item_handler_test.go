package api

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

// D-GLOSSARY-MULTIROW-ATTR-VALUES slice 3 — the per-item verify/tombstone endpoint.
// Tombstoning one list item drops it from the cache (every reader excludes it); verify
// stamps a single item. Auth + grant + the (item,attr_value) ownership guard are exercised
// via the full router. Uses the version fixture's attr value as the item container (the
// handler is attribute-type-agnostic — it operates on item rows).
func TestPatchAttributeValueItem_TombstoneAndVerify(t *testing.T) {
	pool := openTestDB(t)
	f := newVersionFixture(t, pool)
	ctx := context.Background()

	// Seed a 2-item list on the fixture's attr value + its cache.
	if _, err := pool.Exec(ctx,
		`UPDATE entity_attribute_values SET original_value='["alpha","beta"]' WHERE attr_value_id=$1`,
		f.nameAttrVal); err != nil {
		t.Fatalf("seed cache: %v", err)
	}
	mkItem := func(val, norm string, order int) uuid.UUID {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO entity_attribute_value_items(attr_value_id,item_value,item_norm,sort_order,confidence,status)
			 VALUES($1,$2,$3,$4,'machine','active') RETURNING item_id`,
			f.nameAttrVal, val, norm, order).Scan(&id); err != nil {
			t.Fatalf("seed item %s: %v", val, err)
		}
		return id
	}
	alpha := mkItem("alpha", "alpha", 0)
	beta := mkItem("beta", "beta", 1)

	base := "/v1/glossary/books/" + f.bookID.String() + "/entities/" + f.entityID.String() +
		"/attributes/" + f.nameAttrVal.String() + "/items/"

	readCache := func() string {
		var v string
		pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, f.nameAttrVal).Scan(&v)
		return v
	}

	// Tombstone alpha → cache drops it (INV-MR1: only active items remain).
	if w := f.patch(t, base+alpha.String(), `{"status":"tombstoned"}`, ""); w.Code != http.StatusOK {
		t.Fatalf("tombstone: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if v := readCache(); v != `["beta"]` {
		t.Errorf("tombstone should drop alpha from the cache: want [\"beta\"], got %q", v)
	}
	// the entity-updated event fired (glossary-sync → Neo4j sees the change).
	var n int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
		f.entityID).Scan(&n)
	if n == 0 {
		t.Error("tombstone must emit a glossary.entity_updated event")
	}

	// Verify beta → its confidence flips; cache unchanged (still active).
	if w := f.patch(t, base+beta.String(), `{"confidence":"verified"}`, ""); w.Code != http.StatusOK {
		t.Fatalf("verify: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var conf string
	pool.QueryRow(ctx, `SELECT confidence FROM entity_attribute_value_items WHERE item_id=$1`, beta).Scan(&conf)
	if conf != "verified" {
		t.Errorf("verify: want confidence 'verified', got %q", conf)
	}
	if v := readCache(); v != `["beta"]` {
		t.Errorf("verify must not change the active cache: got %q", v)
	}

	// An item id that doesn't belong to this attr value → 404 (the ownership guard).
	if w := f.patch(t, base+uuid.NewString(), `{"status":"tombstoned"}`, ""); w.Code != http.StatusNotFound {
		t.Errorf("unknown item: want 404, got %d", w.Code)
	}
	// Empty body → 400 (must specify status and/or confidence).
	if w := f.patch(t, base+beta.String(), `{}`, ""); w.Code != http.StatusBadRequest {
		t.Errorf("empty body: want 400, got %d", w.Code)
	}
	// Invalid status → 400.
	if w := f.patch(t, base+beta.String(), `{"status":"deleted"}`, ""); w.Code != http.StatusBadRequest {
		t.Errorf("invalid status: want 400, got %d", w.Code)
	}
}
