// Package ledger is the event-store integrity ledger (C3, slice S2b).
//
// It verifies the event LOG itself — independently of any projection — closing
// the blind spot the differential (B) and the structural oracle (C) both miss:
// they re-derive from the SAME `events` rows the projection consumed, so a lost,
// reordered, or byte-rotted event is invisible to both. C3 checks those rows.
//
// SCOPE — what C3 catches: a LOST event (version-gap / count-mismatch /
// missing-event), a DUPLICATED event (duplicate-event), a MUTATED field
// (field-mismatch), and a BYTE-ROTTED payload (payload-mismatch). It does NOT
// catch pure REORDERING: events are matched by event_id (position-independent)
// and version-completeness only sees a gap, so the same events stored in a
// different recorded_at order pass clean. Global / cross-aggregate ordering is
// the fault-history checker's job (S6).
//
// All check logic is PURE over an in-memory Log (fetched by load.go), so every
// check — and every corruption-injection test that proves a check fires — runs
// without a database. Two modes:
//
//   - self-consistency (any data, no baseline): per-aggregate version
//     completeness + events↔outbox count reconciliation.
//   - against-ledger (seeded data): reconcile against the deterministic
//     generator's expected stream, incl payload-hash byte-rot detection
//     (see CheckAgainstExpected).
package ledger

import (
	"fmt"
	"slices"
	"sort"
	"strings"

	"github.com/google/uuid"
)

// EventRow is the subset of a stored event C3 reasons about.
type EventRow struct {
	EventID   uuid.UUID
	RealityID uuid.UUID
	AggType   string
	AggID     string
	EventType string
	Version   uint64
	Payload   map[string]any
}

// Log is an in-memory snapshot of the event store + outbox.
type Log struct {
	Events    []EventRow
	OutboxIDs []uuid.UUID
}

// Violation kinds.
const (
	KindVersionGap      = "version-gap"
	KindDuplicateEvent  = "duplicate-event"
	KindCountMismatch   = "count-mismatch"
	KindOrphanOutbox    = "orphan-outbox"
	KindMissingOutbox   = "missing-outbox"
	KindUnexpectedEvent = "unexpected-event"
	KindMissingEvent    = "missing-event"
	KindPayloadMismatch = "payload-mismatch"
	KindFieldMismatch   = "field-mismatch"
	KindVersionReorder  = "version-reorder"
)

// Violation is one integrity failure.
type Violation struct {
	Kind   string
	Detail string
}

// Report aggregates the violations from a check run.
type Report struct {
	Violations []Violation
}

// OK reports whether the log is clean (no violations).
func (r Report) OK() bool { return len(r.Violations) == 0 }

func (r *Report) add(kind, detail string) {
	r.Violations = append(r.Violations, Violation{Kind: kind, Detail: detail})
}

// Merge appends another report's violations into r.
func (r *Report) Merge(o Report) { r.Violations = append(r.Violations, o.Violations...) }

// Has reports whether the report contains a violation of the given kind.
func (r Report) Has(kind string) bool {
	for _, v := range r.Violations {
		if v.Kind == kind {
			return true
		}
	}
	return false
}

// String renders the report: a clean line, or one line per violation.
func (r Report) String() string {
	if r.OK() {
		return "ledger: clean (0 violations)"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "ledger: %d violation(s)\n", len(r.Violations))
	for _, v := range r.Violations {
		fmt.Fprintf(&b, "  %-18s %s\n", v.Kind, v.Detail)
	}
	return b.String()
}

// CheckSelfConsistency runs the baseline-free checks: per-aggregate version
// completeness + events↔outbox count reconciliation.
//
// NOTE: an EMPTY log is vacuously clean (no events to be inconsistent). A caller
// that expects data must assert non-empty itself, or use CheckAgainstExpected
// (which reports every expected-but-absent event). The -verify CLI runs both.
func CheckSelfConsistency(log Log) Report {
	var r Report
	checkVersionCompleteness(log, &r)
	checkCountReconciliation(log, &r)
	return r
}

// CheckAggregateMonotonicity (W2.2 — closes D-S6-HISTORY-ORDERING) asserts that,
// walking the log in its LOADED order (LoadLog returns recorded_at, event_id —
// a non-version tiebreak, so this is not circular), each aggregate's version is
// strictly previous+1 — no reorder, no gap, no duplicate.
//
// This is the coverage version-completeness MISSES: completeness checks the
// SORTED set is 1..N (position-independent), so a REORDER (e.g. v3 recorded
// before v2) passes it; this check, which respects the stream order, catches it.
// It is the per-aggregate complement to the S6 global/cross-aggregate history
// checker.
func CheckAggregateMonotonicity(log Log) Report {
	var r Report
	last := map[aggKey]uint64{}
	reported := map[aggKey]bool{} // one violation per aggregate is enough
	for _, e := range log.Events {
		k := aggKey{e.RealityID.String(), e.AggType, e.AggID}
		want := uint64(1)
		if prev, ok := last[k]; ok {
			want = prev + 1
		}
		if e.Version != want && !reported[k] {
			r.add(KindVersionReorder, fmt.Sprintf(
				"aggregate %s: version %d out of order (expected %d) in recorded sequence", k, e.Version, want))
			reported[k] = true
		}
		last[k] = e.Version
	}
	return r
}

type aggKey struct{ reality, aggType, aggID string }

func (k aggKey) String() string { return k.reality + "/" + k.aggType + "/" + k.aggID }

// checkVersionCompleteness asserts that for every aggregate the versions are
// exactly 1..N with no gap. (Intra-aggregate duplicates are DB-prevented by the
// partial unique index, but a gap = a lost/missing event.)
func checkVersionCompleteness(log Log, r *Report) {
	groups := map[aggKey][]uint64{}
	for _, e := range log.Events {
		k := aggKey{e.RealityID.String(), e.AggType, e.AggID}
		groups[k] = append(groups[k], e.Version)
	}
	keys := make([]aggKey, 0, len(groups))
	for k := range groups {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i].String() < keys[j].String() })

	for _, k := range keys {
		vs := groups[k]
		slices.Sort(vs)
		for i, v := range vs {
			want := uint64(i + 1)
			if v != want {
				r.add(KindVersionGap, fmt.Sprintf("aggregate %s: expected version %d, got %d (have %v)", k, want, v, vs))
				break // one violation per aggregate is enough
			}
		}
	}
}

// checkCountReconciliation asserts events ↔ outbox is 1:1 (the I13 atomicity
// invariant): equal counts, no event without an outbox row, no orphan outbox.
func checkCountReconciliation(log Log, r *Report) {
	eventIDs := make(map[uuid.UUID]bool, len(log.Events))
	for _, e := range log.Events {
		eventIDs[e.EventID] = true
	}
	outboxIDs := make(map[uuid.UUID]bool, len(log.OutboxIDs))
	for _, id := range log.OutboxIDs {
		outboxIDs[id] = true
	}
	// A duplicated event row shares an event_id (the events table has no unique
	// index on event_id alone). The id sets below would silently collapse it, so
	// compare the RAW row count against the distinct-id count first.
	if len(log.Events) != len(eventIDs) {
		r.add(KindDuplicateEvent, fmt.Sprintf("%d event rows but %d distinct event_ids", len(log.Events), len(eventIDs)))
	}
	if len(eventIDs) != len(outboxIDs) {
		r.add(KindCountMismatch, fmt.Sprintf("events=%d outbox=%d", len(eventIDs), len(outboxIDs)))
	}

	var missing, orphan []string
	for id := range eventIDs {
		if !outboxIDs[id] {
			missing = append(missing, id.String())
		}
	}
	for id := range outboxIDs {
		if !eventIDs[id] {
			orphan = append(orphan, id.String())
		}
	}
	sort.Strings(missing)
	sort.Strings(orphan)
	for _, id := range missing {
		r.add(KindMissingOutbox, "event "+id+" has no outbox row")
	}
	for _, id := range orphan {
		r.add(KindOrphanOutbox, "outbox row "+id+" has no event")
	}
}
