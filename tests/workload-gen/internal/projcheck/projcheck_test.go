package projcheck

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

// fixed UUIDs so failures name a stable value (no random churn across runs).
var (
	e1 = uuid.MustParse("00000000-0000-0000-0000-000000000001")
	e2 = uuid.MustParse("00000000-0000-0000-0000-000000000002")
	e3 = uuid.MustParse("00000000-0000-0000-0000-000000000003")
	// ghost is never in the event store — the orphan probe.
	ghost = uuid.MustParse("00000000-0000-0000-0000-0000000000ff")
)

func TestCheckNoOrphan_Clean(t *testing.T) {
	events := map[uuid.UUID]bool{e1: true, e2: true, e3: true}
	rows := []ProjRow{
		{Table: "pc_projection", EventID: e1},
		{Table: "npc_projection", EventID: e2},
		{Table: "world_kv_projection", EventID: e3},
	}
	if v := CheckNoOrphan(events, rows); len(v) != 0 {
		t.Fatalf("expected 0 violations on a clean set, got %d: %+v", len(v), v)
	}
}

// TestCheckNoOrphan_DanglingFires is the corruption-injection proof: a single
// projection row whose event_id is NOT in the event store must produce exactly
// one violation naming that table + id. This is the latent guard doing its job.
func TestCheckNoOrphan_DanglingFires(t *testing.T) {
	events := map[uuid.UUID]bool{e1: true, e2: true}
	rows := []ProjRow{
		{Table: "pc_projection", EventID: e1},
		{Table: "region_projection", EventID: ghost}, // <- orphan: ghost not persisted
		{Table: "npc_projection", EventID: e2},
	}
	v := CheckNoOrphan(events, rows)
	if len(v) != 1 {
		t.Fatalf("expected exactly 1 violation for the dangling row, got %d: %+v", len(v), v)
	}
	if v[0].Table != "region_projection" || v[0].EventID != ghost {
		t.Fatalf("violation misidentified the orphan: got %+v, want {region_projection %s}", v[0], ghost)
	}
}

// An empty event store with empty projections is vacuously clean.
func TestCheckNoOrphan_EmptyIsClean(t *testing.T) {
	if v := CheckNoOrphan(map[uuid.UUID]bool{}, nil); len(v) != 0 {
		t.Fatalf("empty inputs should be clean, got %d violations", len(v))
	}
}

// Every projection row dangling (event store empty but rows present) → every row
// is an orphan. Guards against an inverted membership test silently passing.
func TestCheckNoOrphan_AllDangling(t *testing.T) {
	rows := []ProjRow{
		{Table: "pc_projection", EventID: e1},
		{Table: "npc_projection", EventID: e2},
	}
	if v := CheckNoOrphan(map[uuid.UUID]bool{}, rows); len(v) != 2 {
		t.Fatalf("expected all %d rows flagged when the event store is empty, got %d", len(rows), len(v))
	}
}

func TestRender(t *testing.T) {
	if got := Render(nil); !strings.Contains(got, "clean (0 orphan rows)") {
		t.Fatalf("clean render missing the clean marker: %q", got)
	}
	out := Render([]Violation{{Table: "region_projection", EventID: ghost}})
	if !strings.Contains(out, "1 orphan row(s)") || !strings.Contains(out, "region_projection") || !strings.Contains(out, ghost.String()) {
		t.Fatalf("orphan render missing count/table/id: %q", out)
	}
}

// Violations are sorted by (table, event_id) regardless of input order, so CLI
// output and any golden comparison are deterministic.
func TestCheckNoOrphan_DeterministicOrder(t *testing.T) {
	events := map[uuid.UUID]bool{} // all dangling → all reported
	rows := []ProjRow{
		{Table: "world_kv_projection", EventID: e2},
		{Table: "world_kv_projection", EventID: e1},
		{Table: "npc_projection", EventID: e3},
	}
	v := CheckNoOrphan(events, rows)
	want := []Violation{
		{Table: "npc_projection", EventID: e3},
		{Table: "world_kv_projection", EventID: e1},
		{Table: "world_kv_projection", EventID: e2},
	}
	if len(v) != len(want) {
		t.Fatalf("got %d violations, want %d", len(v), len(want))
	}
	for i := range want {
		if v[i] != want[i] {
			t.Fatalf("violation[%d] = %+v, want %+v", i, v[i], want[i])
		}
	}
}
