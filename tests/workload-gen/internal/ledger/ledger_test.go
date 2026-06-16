package ledger

import (
	"testing"

	"github.com/google/uuid"
)

// buildClean returns a small valid log: npc/npc-1 at versions 1,2,3 and
// region/region-1 at version 1 — every event paired with an outbox row.
func buildClean() Log {
	reality := uuid.New()
	var log Log
	add := func(aggType, aggID string, version uint64) {
		id := uuid.New()
		log.Events = append(log.Events, EventRow{
			EventID: id, RealityID: reality, AggType: aggType, AggID: aggID,
			EventType: aggType + ".evt", Version: version, Payload: map[string]any{"v": version},
		})
		log.OutboxIDs = append(log.OutboxIDs, id)
	}
	add("npc", "npc-1", 1)
	add("npc", "npc-1", 2)
	add("npc", "npc-1", 3)
	add("region", "region-1", 1)
	return log
}

func TestCleanLogIsConsistent(t *testing.T) {
	r := CheckSelfConsistency(buildClean())
	if !r.OK() {
		t.Errorf("clean log should have 0 violations, got: %s", r)
	}
}

func TestVersionGapCaught(t *testing.T) {
	log := buildClean()
	// "lose" npc-1 version 2 (event + its outbox row) → versions become 1,3.
	var events []EventRow
	lost := uuid.UUID{}
	for _, e := range log.Events {
		if e.AggType == "npc" && e.Version == 2 {
			lost = e.EventID
			continue
		}
		events = append(events, e)
	}
	log.Events = events
	var outbox []uuid.UUID
	for _, id := range log.OutboxIDs {
		if id != lost {
			outbox = append(outbox, id)
		}
	}
	log.OutboxIDs = outbox

	r := CheckSelfConsistency(log)
	if !r.Has(KindVersionGap) {
		t.Errorf("a missing version must be a version-gap; got: %s", r)
	}
	if r.Has(KindCountMismatch) {
		t.Errorf("removing the event AND its outbox row keeps counts equal; got count-mismatch: %s", r)
	}
}

func TestMissingOutboxCaught(t *testing.T) {
	log := buildClean()
	log.OutboxIDs = log.OutboxIDs[:len(log.OutboxIDs)-1] // drop one outbox row, keep all events
	r := CheckSelfConsistency(log)
	if !r.Has(KindCountMismatch) || !r.Has(KindMissingOutbox) {
		t.Errorf("a dropped outbox row must be count-mismatch + missing-outbox; got: %s", r)
	}
}

func TestDuplicateEventCaught(t *testing.T) {
	log := buildClean()
	// A duplicated event row shares an event_id (the outbox PK keeps just one
	// outbox row). The id sets would collapse the dup — the raw-count check must
	// still flag it.
	log.Events = append(log.Events, log.Events[0])
	r := CheckSelfConsistency(log)
	if !r.Has(KindDuplicateEvent) {
		t.Errorf("a duplicated event row must be a duplicate-event; got: %s", r)
	}
}

func TestOrphanOutboxCaught(t *testing.T) {
	log := buildClean()
	log.OutboxIDs = append(log.OutboxIDs, uuid.New()) // an outbox row with no event
	r := CheckSelfConsistency(log)
	if !r.Has(KindCountMismatch) || !r.Has(KindOrphanOutbox) {
		t.Errorf("an orphan outbox row must be count-mismatch + orphan-outbox; got: %s", r)
	}
}

func TestReportHelpers(t *testing.T) {
	var r Report
	if !r.OK() || r.String() != "ledger: clean (0 violations)" {
		t.Errorf("empty report should be OK + clean string, got %q", r.String())
	}
	r.add(KindVersionGap, "x")
	if r.OK() || !r.Has(KindVersionGap) || r.Has(KindOrphanOutbox) {
		t.Errorf("report with a violation: OK=%v Has(gap)=%v", r.OK(), r.Has(KindVersionGap))
	}
}
