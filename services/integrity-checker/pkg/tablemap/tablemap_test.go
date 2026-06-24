package tablemap

import (
	"sort"
	"testing"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// The map MUST cover exactly the 10 L3.A tables — no more, no less. A drift in
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
		// Only the one cross-aggregate table has a DeriveOwning.
		if spec.CrossAggregate != (spec.DeriveOwning != nil) {
			t.Errorf("%s: CrossAggregate=%v but DeriveOwning set=%v (must agree)", tbl, spec.CrossAggregate, spec.DeriveOwning != nil)
		}
	}
}

func TestCompositePKColumnsMatch0006(t *testing.T) {
	cases := map[string][]string{
		"pc_inventory_projection":        {"pc_id", "item_code"},
		"pc_relationship_projection":     {"pc_id", "other_entity_type", "other_entity_id"},
		"npc_pc_relationship_projection": {"npc_id", "other_entity_id"},
		"session_participants":           {"session_id", "participant_type", "participant_id"},
		"world_kv_projection":            {"key"},
		"npc_session_memory_projection":  {"npc_id", "session_id"},
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

func TestNpcSessionMemoryIsCrossAggregateAndDerivesBothOwners(t *testing.T) {
	spec, ok := Lookup("npc_session_memory_projection")
	if !ok || !spec.CrossAggregate || spec.DeriveOwning == nil {
		t.Fatal("npc_session_memory_projection must be cross-aggregate with DeriveOwning")
	}
	owners, err := spec.DeriveOwning(map[string]string{"npc_id": "n-1", "session_id": "s-2"})
	if err != nil {
		t.Fatal(err)
	}
	if len(owners) != 2 {
		t.Fatalf("expected 2 owners, got %v", owners)
	}
	// session (session_id) + npc (npc_id), in that order.
	if owners[0] != (OwningAggregate{Type: "session", ID: "s-2"}) {
		t.Errorf("owner[0] = %+v", owners[0])
	}
	if owners[1] != (OwningAggregate{Type: "npc", ID: "n-1"}) {
		t.Errorf("owner[1] = %+v", owners[1])
	}

	// Missing a PK component is an error (the sampler must supply both).
	if _, err := spec.DeriveOwning(map[string]string{"npc_id": "n-1"}); err == nil {
		t.Error("expected error when session_id missing")
	}
	if _, err := spec.DeriveOwning(map[string]string{"session_id": "s-2"}); err == nil {
		t.Error("expected error when npc_id missing")
	}
}

func TestSingleAggregateTablesHaveNoDeriveOwning(t *testing.T) {
	// All but npc_session_memory_projection are single-aggregate (owner resolved
	// at runtime via the row's event_id).
	for _, tbl := range types.L3ATables {
		if tbl == "npc_session_memory_projection" {
			continue
		}
		spec, _ := Lookup(tbl)
		if spec.CrossAggregate || spec.DeriveOwning != nil {
			t.Errorf("%s should be single-aggregate", tbl)
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
