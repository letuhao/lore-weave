// Package projcheck is the structural projection oracle (C, slice S2).
//
// It checks the projection TABLES — independently of the differential oracle
// (B) and the from-spec golden battery (C2) — for one DB-level structural
// invariant: NO-ORPHAN. Every projection row carries the `event_id` of the
// event that last wrote it (VerificationMeta, per migration 0006/0009); the
// no-orphan check asserts that every such `event_id` resolves to a real row in
// the `events` table.
//
// HONEST SCOPE — this is a LATENT GUARD, tautological today.
//
// The only writer of projection rows today is the rebuilder, which copies
// `event_id` straight off the event it is replaying — so a freshly-rebuilt DB
// CANNOT contain an orphan, and a clean result proves nothing was already
// broken rather than catching a live bug. The check earns its keep the day a
// NON-rebuild writer appears (a streaming online projector, a manual backfill,
// a partial-replay tool): such a writer could stamp a row with an event_id that
// was never persisted (lost outbox, wrong reality, fat-fingered UUID), and this
// guard is what would fire. It is shipped cheap now so that surface is covered
// the moment it becomes real. Deterministic-rebuild (the other half of C
// structural) is deferred — pure projections over an ordered log are
// byte-deterministic by construction (D-C-DETERMINISTIC-REBUILD).
//
// CheckNoOrphan is PURE over in-memory sets (the rows are fetched by load.go),
// so the corruption-injection test that proves the check fires — a row with a
// dangling event_id — runs without a database.
package projcheck

import (
	"fmt"
	"sort"
	"strings"

	"github.com/google/uuid"
)

// ProjRow is one projection row reduced to what the no-orphan check reasons
// about: which table it lives in, and the event_id it claims wrote it.
//
// Canon's column is `source_event_id` (nullable for cascade rows); the loader
// maps it onto EventID and filters out the NULLs, so by the time a ProjRow
// exists its EventID is a real, non-nil claim to verify.
type ProjRow struct {
	Table   string
	EventID uuid.UUID
}

// Violation is one orphan: a projection row whose event_id is absent from the
// event store.
type Violation struct {
	Table   string
	EventID uuid.UUID
}

// CheckNoOrphan returns one Violation for every projection row whose EventID is
// not present in eventIDs (the set of event_ids that actually exist in the
// `events` table). Pure — no DB, no ordering assumptions.
//
// Violations are sorted by (table, event_id) so output is deterministic
// regardless of row-fetch order.
func CheckNoOrphan(eventIDs map[uuid.UUID]bool, rows []ProjRow) []Violation {
	var v []Violation
	for _, r := range rows {
		if !eventIDs[r.EventID] {
			v = append(v, Violation{Table: r.Table, EventID: r.EventID})
		}
	}
	sort.Slice(v, func(i, j int) bool {
		if v[i].Table != v[j].Table {
			return v[i].Table < v[j].Table
		}
		return v[i].EventID.String() < v[j].EventID.String()
	})
	return v
}

// Render formats a no-orphan result: a single clean line, or a header plus one
// line per orphan row. Trailing newline so it composes with fmt.Fprint.
func Render(v []Violation) string {
	if len(v) == 0 {
		return "projcheck: clean (0 orphan rows)\n"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "projcheck: %d orphan row(s) — projection event_id absent from events\n", len(v))
	for _, o := range v {
		fmt.Fprintf(&b, "  %-32s %s\n", o.Table, o.EventID)
	}
	return b.String()
}
