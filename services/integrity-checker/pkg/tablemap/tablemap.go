// Package tablemap is the per-table knowledge the L3.E/F integrity checker needs
// to turn a sampled projection ROW into a replay request: the table's
// primary-key columns, and how to resolve the OWNING event aggregate(s) for a
// row.
//
// Two resolution modes (see docs/plans/2026-06-03-l3ef-integrity-checker.md):
//
//   - SINGLE-aggregate tables: the owning aggregate is resolved generically at
//     runtime from the row's `event_id` (`SELECT aggregate_type, aggregate_id
//     FROM events WHERE event_id=$1`), so no static aggregate derivation is
//     needed here — only the PK columns.
//   - CROSS-aggregate tables: the row is built from more than one aggregate, so
//     a single event_id (the last writer) is insufficient — the owning SET is
//     derived from the PK columns via DeriveOwning, and the replay-aggregate bin
//     replays both in global order.
//
// **No table is cross-aggregate today.** The only one ever was
// `npc_session_memory_projection` (`session.started` created the row,
// `npc.said` incremented it), dropped by 0017 with the rest of the pc/npc
// projections. The MODE is kept because it is a property of the checker, not of
// npc vocabulary — but its vacuity is asserted rather than assumed:
// `TestNoProductionSpecIsCrossAggregateYet` fails the moment a spec sets
// CrossAggregate, and tells that author to restore the derivation coverage.
//
// The PK columns MUST match contracts/migrations/per_reality/0006_projections
// exactly; a drift test asserts the table set matches types.L3ATables.
package tablemap

import (
	"fmt"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// OwningAggregate identifies one event aggregate to replay: its
// `events.aggregate_type` + `events.aggregate_id` (TEXT).
type OwningAggregate struct {
	Type string
	ID   string
}

// TableSpec is the per-table replay knowledge.
type TableSpec struct {
	// PKColumns are the projection table's primary-key columns, in 0006 order.
	// Used to read the row's PK (sampler) and to select the replayed row (bin).
	PKColumns []string
	// CrossAggregate marks a table whose rows are built from MORE THAN ONE
	// aggregate. For these the owning set is derived from the PK (DeriveOwning);
	// for single-aggregate tables it is resolved from the row's event_id.
	CrossAggregate bool
	// DeriveOwning is set ONLY for cross-aggregate tables. Given the row's PK
	// (column→value), it returns every owning aggregate to replay.
	DeriveOwning func(pk map[string]string) ([]OwningAggregate, error)
}

// specs is the canonical per-table map. Keys MUST equal types.L3ATables.
//
// Ten -> three (`0017`) -> ONE (`0018`). Every removed key was a table no
// production code could fill.
//
// NOTE the consequence for the COMPOSITE-PK path: `session_participants` was the
// last multi-column PK here, so `PKColumns` now has only single-column data. The
// machinery is unchanged and the DDL contract still governs it; there is simply
// nothing left to exercise it with, which is recorded rather than papered over.
var specs = map[string]TableSpec{
	"canon_projection": {PKColumns: []string{"canon_entry_id"}},
}

// Lookup returns the TableSpec for an L3.A projection table.
func Lookup(table string) (TableSpec, bool) {
	s, ok := specs[table]
	return s, ok
}

// Tables returns the table names covered by the map (the L3.A tables).
func Tables() []string {
	out := make([]string, 0, len(specs))
	for t := range specs {
		out = append(out, t)
	}
	return out
}

// PKColumns returns the primary-key columns for a table, or an error if the
// table is unknown.
func PKColumns(table string) ([]string, error) {
	s, ok := specs[table]
	if !ok {
		return nil, fmt.Errorf("tablemap: unknown projection table %q", table)
	}
	return s.PKColumns, nil
}

// compile-time anchor so a 0006/types drift is caught by the package test, not
// silently: every L3ATable MUST have a spec and vice-versa (TestSpecsCoverL3A).
var _ = types.L3ATables
