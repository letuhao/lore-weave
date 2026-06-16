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
	"time"

	"github.com/google/uuid"
)

// EventRow is the subset of a stored event C3 reasons about.
type EventRow struct {
	EventID    uuid.UUID
	RealityID  uuid.UUID
	AggType    string
	AggID      string
	EventType  string
	Version    uint64
	RecordedAt time.Time // for W2.2 monotonicity; tie-aware so same-ts events don't false-flag
	Payload    map[string]any
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
	// KindStoredChecksumMismatch (W3.4): a row's frozen content_sha256 no longer
	// matches the hash re-derived from its payload+metadata — content was mutated
	// after write (byte-rot / tamper). Distinct from KindPayloadMismatch, which
	// compares against the SEEDED expected stream; this needs no seed/baseline,
	// only the row's own stored checksum.
	KindStoredChecksumMismatch = "stored-checksum-mismatch"
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

// CheckAggregateMonotonicity (W2.2 — closes D-S6-HISTORY-ORDERING) asserts that
// for each aggregate, recorded-time order is consistent with version order: an
// event written at a STRICTLY-LATER recorded_at must carry a strictly-higher
// version. A reorder (e.g. v3 recorded before v2) violates this; a gap or a
// backward version at a later time does too.
//
// This is the coverage version-completeness MISSES: completeness checks the
// SORTED set is 1..N (position-independent), so a reorder passes it; this check
// respects recorded order.
//
// TIE-AWARE (review #1): two events of one aggregate sharing a recorded_at are
// CONCURRENT — their relative (recorded_at, event_id) order is arbitrary, so we
// do NOT flag a version inversion WITHIN a same-timestamp cluster (that would be
// a false positive on real data where two appends can land in the same µs). We
// only compare across STRICTLY-LATER timestamps, carrying the max version seen
// at any earlier time. (LoadLog already orders by recorded_at, event_id.)
func CheckAggregateMonotonicity(log Log) Report {
	var r Report
	// Per aggregate: the max version among events at recorded_at STRICTLY before
	// the current event's timestamp, and the timestamp of the current cluster.
	type cursor struct {
		maxBefore   uint64    // max version at any strictly-earlier recorded_at
		clusterMax  uint64    // max version at clusterTime
		clusterTime time.Time // recorded_at of the current same-ts cluster
		started     bool
	}
	st := map[aggKey]*cursor{}
	reported := map[aggKey]bool{}
	for _, e := range log.Events {
		k := aggKey{e.RealityID.String(), e.AggType, e.AggID}
		c := st[k]
		if c == nil {
			c = &cursor{}
			st[k] = c
		}
		if !c.started {
			c.started = true
			c.clusterTime = e.RecordedAt
			c.clusterMax = e.Version
			continue
		}
		if e.RecordedAt.After(c.clusterTime) {
			// New, strictly-later cluster: everything in the prior cluster is now
			// "strictly before". Fold the prior cluster's max into maxBefore.
			if c.clusterMax > c.maxBefore {
				c.maxBefore = c.clusterMax
			}
			c.clusterTime = e.RecordedAt
			c.clusterMax = e.Version
			// A strictly-later event must out-rank everything seen earlier.
			if e.Version <= c.maxBefore && !reported[k] {
				r.add(KindVersionReorder, fmt.Sprintf(
					"aggregate %s: version %d at a later recorded_at is <= an earlier version %d (reorder/dup)",
					k, e.Version, c.maxBefore))
				reported[k] = true
			}
		} else {
			// Same timestamp (tie) — or, defensively, an out-of-sort row: treat
			// as part of the current concurrent cluster; do not flag.
			if e.Version > c.clusterMax {
				c.clusterMax = e.Version
			}
		}
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
