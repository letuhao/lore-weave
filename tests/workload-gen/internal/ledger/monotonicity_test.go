package ledger

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

var monoBase = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

// ev builds an event with a recorded_at `recSec` seconds after the base epoch,
// so the slice order matches the (recorded_at, event_id) order LoadLog produces.
func ev(agg string, version uint64, recSec int64) EventRow {
	return EventRow{
		EventID:    uuid.New(),
		RealityID:  uuid.Nil,
		AggType:    "npc",
		AggID:      agg,
		EventType:  "npc.said",
		Version:    version,
		RecordedAt: monoBase.Add(time.Duration(recSec) * time.Second),
	}
}

func TestMonotonicityCleanOnOrderedLog(t *testing.T) {
	log := Log{Events: []EventRow{ev("a", 1, 1), ev("a", 2, 2), ev("a", 3, 3)}}
	if r := CheckAggregateMonotonicity(log); !r.OK() {
		t.Fatalf("ordered log must be clean, got %s", r.String())
	}
}

// The headline W2.2 distinction: a REORDER (v2 recorded AFTER v3, distinct
// timestamps) fails monotonicity but PASSES version-completeness (set {1,2,3}
// has no gap). Proves the new check adds coverage completeness misses.
func TestMonotonicityCatchesReorderThatCompletenessMisses(t *testing.T) {
	// Recorded order v1@1s, v3@2s, v2@3s — set complete, recorded order inverted.
	log := Log{Events: []EventRow{ev("a", 1, 1), ev("a", 3, 2), ev("a", 2, 3)}}

	mono := CheckAggregateMonotonicity(log)
	if mono.OK() || !mono.Has(KindVersionReorder) {
		t.Fatalf("reorder must raise version-reorder, got %s", mono.String())
	}

	var comp Report
	checkVersionCompleteness(log, &comp)
	if comp.Has(KindVersionGap) {
		t.Fatalf("completeness should NOT flag a complete-but-reordered set; got %s", comp.String())
	}
}

// Review #1 — tie-aware: events of one aggregate sharing a recorded_at are
// CONCURRENT; their arbitrary (event_id) order must NOT be flagged as a reorder
// (else a false positive on real same-µs appends).
func TestMonotonicityDoesNotFlagSameTimestampCluster(t *testing.T) {
	// All at the SAME recorded_at (recSec=5), versions out of order in the slice.
	log := Log{Events: []EventRow{ev("a", 1, 5), ev("a", 3, 5), ev("a", 2, 5)}}
	if r := CheckAggregateMonotonicity(log); !r.OK() {
		t.Fatalf("same-timestamp cluster must NOT be flagged (concurrent), got %s", r.String())
	}
}

func TestMonotonicityOnePerAggregate(t *testing.T) {
	// Two aggregates, each reordered across distinct timestamps → one each.
	log := Log{Events: []EventRow{
		ev("a", 1, 1), ev("a", 3, 2), ev("a", 2, 3),
		ev("b", 2, 1), ev("b", 1, 2),
	}}
	r := CheckAggregateMonotonicity(log)
	if len(r.Violations) != 2 {
		t.Fatalf("want exactly 2 violations (one per aggregate), got %d: %s", len(r.Violations), r.String())
	}
}
