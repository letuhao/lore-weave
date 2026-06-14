package ledger

import (
	"testing"

	"github.com/google/uuid"
)

func ev(agg string, version uint64) EventRow {
	return EventRow{
		EventID:   uuid.New(),
		RealityID: uuid.Nil,
		AggType:   "npc",
		AggID:     agg,
		EventType: "npc.said",
		Version:   version,
	}
}

func TestMonotonicityCleanOnOrderedLog(t *testing.T) {
	log := Log{Events: []EventRow{ev("a", 1), ev("a", 2), ev("a", 3)}}
	if r := CheckAggregateMonotonicity(log); !r.OK() {
		t.Fatalf("ordered log must be clean, got %s", r.String())
	}
}

// The headline W2.2 distinction: a REORDER fails monotonicity but PASSES
// version-completeness (the set {1,2,3} has no gap). Proves the new check adds
// coverage version-completeness misses.
func TestMonotonicityCatchesReorderThatCompletenessMisses(t *testing.T) {
	// Loaded (recorded) order v1, v3, v2 — set is complete, order is not.
	log := Log{Events: []EventRow{ev("a", 1), ev("a", 3), ev("a", 2)}}

	mono := CheckAggregateMonotonicity(log)
	if mono.OK() || !mono.Has(KindVersionReorder) {
		t.Fatalf("reorder must raise version-reorder, got %s", mono.String())
	}

	// Same data through completeness (sorted set 1,2,3) → clean.
	var comp Report
	checkVersionCompleteness(log, &comp)
	if comp.Has(KindVersionGap) {
		t.Fatalf("completeness should NOT flag a complete-but-reordered set; got %s", comp.String())
	}
}

func TestMonotonicityOnePerAggregate(t *testing.T) {
	// Two aggregates, each reordered → exactly two violations (one each).
	log := Log{Events: []EventRow{
		ev("a", 1), ev("a", 3), ev("a", 2),
		ev("b", 2), ev("b", 1),
	}}
	r := CheckAggregateMonotonicity(log)
	if len(r.Violations) != 2 {
		t.Fatalf("want exactly 2 violations (one per aggregate), got %d: %s", len(r.Violations), r.String())
	}
}
