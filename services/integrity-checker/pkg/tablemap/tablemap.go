// Package tablemap is the per-table knowledge the L3.E/F integrity checker needs
// to turn a sampled projection ROW into a replay request: the table's
// primary-key columns, and how to resolve the OWNING event aggregate(s) for a
// row.
//
// Two resolution modes (see docs/plans/2026-06-03-l3ef-integrity-checker.md):
//
//   - SINGLE-aggregate tables (8 of 10, + the embedding table): the owning
//     aggregate is resolved generically at runtime from the row's `event_id`
//     (`SELECT aggregate_type, aggregate_id FROM events WHERE event_id=$1`), so
//     no static aggregate derivation is needed here — only the PK columns.
//   - CROSS-aggregate tables (npc_session_memory_projection): the row is built
//     from BOTH a `session` aggregate AND an `npc` aggregate, so a single
//     event_id (the last writer) is insufficient — the owning SET is derived
//     from the PK columns via DeriveOwning, and the replay-aggregate bin replays
//     both in global order.
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
var specs = map[string]TableSpec{
	"pc_projection":                  {PKColumns: []string{"pc_id"}},
	"pc_inventory_projection":        {PKColumns: []string{"pc_id", "item_code"}},
	"pc_relationship_projection":     {PKColumns: []string{"pc_id", "other_entity_type", "other_entity_id"}},
	"npc_projection":                 {PKColumns: []string{"npc_id"}},
	"npc_pc_relationship_projection": {PKColumns: []string{"npc_id", "other_entity_id"}},
	"npc_session_memory_embedding":   {PKColumns: []string{"npc_id", "session_id"}},
	"region_projection":              {PKColumns: []string{"region_id"}},
	"world_kv_projection":            {PKColumns: []string{"key"}},
	"session_participants":           {PKColumns: []string{"session_id", "participant_type", "participant_id"}},
	// CROSS-aggregate: npc_session_memory_projection is built from BOTH
	// session.* (INSERT/archive — aggregate `session`/session_id) AND
	// npc.memory_updated (facts/summary UPDATE — aggregate `npc`/npc_id). Both
	// must be replayed in global order. The bin orders by (recorded_at,
	// event_id) — an approximation tracked as DEFERRED 146.
	"npc_session_memory_projection": {
		PKColumns:      []string{"npc_id", "session_id"},
		CrossAggregate: true,
		DeriveOwning: func(pk map[string]string) ([]OwningAggregate, error) {
			sid, ok := pk["session_id"]
			if !ok || sid == "" {
				return nil, fmt.Errorf("tablemap: npc_session_memory_projection pk missing session_id: %v", pk)
			}
			nid, ok := pk["npc_id"]
			if !ok || nid == "" {
				return nil, fmt.Errorf("tablemap: npc_session_memory_projection pk missing npc_id: %v", pk)
			}
			return []OwningAggregate{
				{Type: "session", ID: sid},
				{Type: "npc", ID: nid},
			}, nil
		},
	},
}

// Lookup returns the TableSpec for an L3.A projection table.
func Lookup(table string) (TableSpec, bool) {
	s, ok := specs[table]
	return s, ok
}

// Tables returns the table names covered by the map (the 10 L3.A tables).
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
