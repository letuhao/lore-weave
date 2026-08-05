package tablemap

import (
	"sort"
	"testing"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// The map MUST cover exactly the L3.A tables — no more, no less. A drift in
// either direction (0006 adds a table / types.L3ATables changes) fails here.
func TestSpecsCoverL3AExactly(t *testing.T) {
	got := Tables()
	sort.Strings(got)
	want := append([]string(nil), types.L3ATables...)
	sort.Strings(want)
	if len(got) != len(want) {
		t.Fatalf("table count: got %d, want %d (%v vs %v)", len(got), len(want), got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("table set drift at %d: got %q, want %q", i, got[i], want[i])
		}
	}
}

func TestEveryL3ATableHasNonEmptyPK(t *testing.T) {
	for _, tbl := range types.L3ATables {
		spec, ok := Lookup(tbl)
		if !ok {
			t.Errorf("%s: no spec", tbl)
			continue
		}
		if len(spec.PKColumns) == 0 {
			t.Errorf("%s: empty PKColumns", tbl)
		}
		// A cross-aggregate spec must carry a DeriveOwning, and only it may.
		if spec.CrossAggregate != (spec.DeriveOwning != nil) {
			t.Errorf("%s: CrossAggregate=%v but DeriveOwning set=%v (must agree)", tbl, spec.CrossAggregate, spec.DeriveOwning != nil)
		}
	}
}

func TestCompositePKColumnsMatch0006(t *testing.T) {
	cases := map[string][]string{
		"session_participants": {"session_id", "participant_type", "participant_id"},
		"world_kv_projection":  {"key"},
		"region_projection":    {"region_id"},
	}
	for tbl, want := range cases {
		got, err := PKColumns(tbl)
		if err != nil {
			t.Fatalf("%s: %v", tbl, err)
		}
		if len(got) != len(want) {
			t.Fatalf("%s pk: got %v want %v", tbl, got, want)
		}
		for i := range want {
			if got[i] != want[i] {
				t.Errorf("%s pk[%d]: got %q want %q", tbl, i, got[i], want[i])
			}
		}
	}
}

// TestNoProductionSpecIsCrossAggregateYet states a VACUITY out loud instead of
// letting it hide.
//
// `npc_session_memory_projection` was the only cross-aggregate table the checker
// ever had, and `0017` dropped it. So `live.ResolveOwning`'s `spec.CrossAggregate`
// branch is currently unreachable from production data — and the tests that used
// to cover the derivation went with the table.
//
// Deleting the MODE would have been wrong (it is a property of the checker, not
// of npc vocabulary), but keeping it silently is how dead machinery survives for
// two months. So the vacuity is asserted: **this test fails the moment anyone
// adds a cross-aggregate spec**, and the failure message tells that author what
// coverage they now owe. It is the smallest thing that can red on the event that
// matters.
func TestNoProductionSpecIsCrossAggregateYet(t *testing.T) {
	for _, tbl := range Tables() {
		spec, _ := Lookup(tbl)
		if spec.CrossAggregate || spec.DeriveOwning != nil {
			t.Fatalf(
				"%s is cross-aggregate — the first one since 0017 dropped "+
					"npc_session_memory_projection. This test is now obsolete: replace it with "+
					"real coverage of %s's DeriveOwning (both owners returned in order, and an "+
					"error for each missing PK component), and cover the CrossAggregate branch "+
					"in live.ResolveOwning, which no production table has reached since 0017.",
				tbl, tbl)
		}
	}
}

func TestLookupAndPKColumnsRejectUnknown(t *testing.T) {
	if _, ok := Lookup("reality_registry"); ok {
		t.Error("reality_registry must not be in the map")
	}
	if _, err := PKColumns("not_a_table"); err == nil {
		t.Error("PKColumns must reject an unknown table")
	}
}
