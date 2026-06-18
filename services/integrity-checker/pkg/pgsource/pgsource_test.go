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

func TestScanSQL_NoCursor_OrdersByPKNoWhere(t *testing.T) {
	sql := scanSQL("pc_projection", []string{"pc_id"}, false)
	if strings.Contains(sql, "WHERE") {
		t.Errorf("first batch (no cursor) must have no WHERE: %s", sql)
	}
	if !strings.Contains(sql, "ORDER BY t.pc_id::text") {
		t.Errorf("must order by pk ::text: %s", sql)
	}
	if !strings.HasSuffix(sql, "LIMIT $1") {
		t.Errorf("batch LIMIT $1 tail missing: %s", sql)
	}
	// same meta-strip + payload + boundary shape as the sampler.
	for _, k := range metaKeys {
		if !strings.Contains(sql, " - '"+k+"'") {
			t.Errorf("missing meta strip %q in: %s", k, sql)
		}
	}
}

func TestScanSQL_Cursor_SingleVsCompositePK(t *testing.T) {
	// Single PK → scalar comparison, cursor bind at $2.
	one := scanSQL("pc_projection", []string{"pc_id"}, true)
	if !strings.Contains(one, "WHERE t.pc_id::text > $2") {
		t.Errorf("single-pk cursor predicate: %s", one)
	}
	// Composite PK → row-value comparison, binds $2,$3 in PK order.
	two := scanSQL("pc_inventory_projection", []string{"pc_id", "item_code"}, true)
	if !strings.Contains(two, "WHERE (t.pc_id::text, t.item_code::text) > ($2, $3)") {
		t.Errorf("composite-pk row-value cursor predicate: %s", two)
	}
	if !strings.Contains(two, "ORDER BY t.pc_id::text, t.item_code::text") {
		t.Errorf("composite order-by must match the cursor key columns/order: %s", two)
	}
}

func TestCursorCodec_RoundTripsAndValidatesArity(t *testing.T) {
	// Round-trips arbitrary TEXT PK values (commas, quotes, unicode).
	in := []string{"a,b", `c"d`, "日本語"}
	enc, err := encodeCursor(in)
	if err != nil {
		t.Fatal(err)
	}
	out, err := decodeCursor(enc, len(in))
	if err != nil {
		t.Fatal(err)
	}
	if len(out) != len(in) {
		t.Fatalf("round-trip arity: got %d want %d", len(out), len(in))
	}
	for i := range in {
		if out[i] != in[i] {
			t.Errorf("round-trip[%d]: got %q want %q", i, out[i], in[i])
		}
	}
	// Arity mismatch (cursor from a 2-col table fed to a 1-col PK) must error.
	if _, err := decodeCursor(enc, 1); err == nil {
		t.Error("expected arity-mismatch error")
	}
	// Garbage cursor must error.
	if _, err := decodeCursor("not-json", 1); err == nil {
		t.Error("expected decode error on garbage cursor")
	}
}
