package pgsource

import (
	"strings"
	"testing"
)

func TestSampleSQL_StripsMetaCastsPKAndOrdersRandom(t *testing.T) {
	sql := sampleSQL("pc_inventory_projection", []string{"pc_id", "item_code"})
	for _, k := range metaKeys {
		if !strings.Contains(sql, " - '"+k+"'") {
			t.Errorf("missing meta strip %q in: %s", k, sql)
		}
	}
	if !strings.Contains(sql, "to_jsonb(t)") || !strings.Contains(sql, "AS payload") {
		t.Errorf("payload projection missing: %s", sql)
	}
	if !strings.Contains(sql, "t.pc_id::text AS pc_id") || !strings.Contains(sql, "t.item_code::text AS item_code") {
		t.Errorf("pk ::text casts missing: %s", sql)
	}
	if !strings.Contains(sql, "t.event_id") || !strings.Contains(sql, "t.aggregate_version") {
		t.Errorf("boundary columns missing: %s", sql)
	}
	if !strings.Contains(sql, "FROM pc_inventory_projection t") {
		t.Errorf("from clause: %s", sql)
	}
	if !strings.HasSuffix(sql, "ORDER BY random() LIMIT $1") {
		t.Errorf("random-sample tail missing: %s", sql)
	}
}

func TestSampleSQL_SingleColumnPK(t *testing.T) {
	sql := sampleSQL("pc_projection", []string{"pc_id"})
	if !strings.Contains(sql, "t.pc_id::text AS pc_id") {
		t.Errorf("single pk: %s", sql)
	}
	// exactly one pk column → no stray comma before FROM
	if strings.Contains(sql, ", ,") {
		t.Errorf("malformed select list: %s", sql)
	}
}

func TestMetaKeysMatchTheFiveVerificationColumns(t *testing.T) {
	// MUST stay in lockstep with the Rust bin's META_KEYS + 0006.
	if len(metaKeys) != 5 {
		t.Fatalf("expected 5 meta keys, got %d: %v", len(metaKeys), metaKeys)
	}
	want := map[string]bool{
		"event_id": true, "aggregate_version": true, "applied_at": true,
		"last_verified_event_version": true, "last_verified_at": true,
	}
	for _, k := range metaKeys {
		if !want[k] {
			t.Errorf("unexpected meta key %q", k)
		}
	}
}

func TestOwnerLookupSQLShape(t *testing.T) {
	if !strings.Contains(ownerLookupSQL, "aggregate_type") ||
		!strings.Contains(ownerLookupSQL, "aggregate_id") ||
		!strings.Contains(ownerLookupSQL, "FROM events") ||
		!strings.Contains(ownerLookupSQL, "event_id = $1") {
		t.Errorf("owner lookup sql shape: %s", ownerLookupSQL)
	}
}

func TestNewRejectsNilPool(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Fatal("New(nil) must error")
	}
}
