package projcheck

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
)

// projTable names a projection table and the column holding its event_id, plus
// an optional WHERE predicate. The whole set is the L3.A canonical 10 (migration
// 0006) + canon_projection (the 11th, migration 0009).
type projTable struct {
	name     string
	eventCol string
	// where is an optional SQL predicate (no leading WHERE). Canon needs it:
	// `source_event_id` is NULLABLE — a cascade row legitimately has no source
	// event (it carries cascaded_from_reality_id instead), so those rows are
	// NOT orphans and must be excluded before the non-null UUID scan.
	where string
}

// projectionTables is every table LoadProjections sweeps. All exist after the
// per_reality migrations (0006 + 0009) are applied; an empty table contributes
// zero rows, so listing a table the current pipeline doesn't populate (e.g.
// canon, written by the meta-worker not the world rebuilder) is harmless.
//
// COVERAGE CAP — this list is MAINTAINED IN LOCKSTEP with the projection
// migrations: 0006_projections (the L3.A canonical 10) + 0009_canon_projection
// (the 11th). It is NOT derived from the live schema, so a NEW projection table
// added by a future migration is SILENTLY unchecked until its row is added here.
// When you add a projection table, add it here too (tracked: D-PROJCHECK-TABLE-DRIFT).
//
// SCOPE — no-orphan checks the WRITING event only: the VerificationMeta event_id
// (source_event_id for canon, the event that last upserted the row). It does NOT
// check secondary event references such as canon_projection.overridden_by_l3_event_id
// (a cross-reference, not the writing event) — those are a different invariant,
// out of this guard's scope.
var projectionTables = []projTable{
	{name: "pc_projection", eventCol: "event_id"},
	{name: "pc_inventory_projection", eventCol: "event_id"},
	{name: "pc_relationship_projection", eventCol: "event_id"},
	{name: "npc_projection", eventCol: "event_id"},
	{name: "npc_session_memory_projection", eventCol: "event_id"},
	{name: "npc_pc_relationship_projection", eventCol: "event_id"},
	{name: "npc_session_memory_embedding", eventCol: "event_id"},
	{name: "region_projection", eventCol: "event_id"},
	{name: "world_kv_projection", eventCol: "event_id"},
	{name: "session_participants", eventCol: "event_id"},
	{name: "canon_projection", eventCol: "source_event_id", where: "source_event_id IS NOT NULL"},
}

// LoadProjections fetches (table, event_id) for every row across all projection
// tables. A thin adapter: the check logic (CheckNoOrphan) carries the coverage;
// the loader itself is exercised by the live pipeline smoke.
func LoadProjections(ctx context.Context, db *sql.DB) ([]ProjRow, error) {
	var out []ProjRow
	for _, t := range projectionTables {
		// #nosec G201 — table/column names are compile-time constants from the
		// fixed list above, never user input; only literal identifiers interpolate.
		q := fmt.Sprintf("SELECT %s FROM %s", t.eventCol, t.name)
		if t.where != "" {
			q += " WHERE " + t.where
		}
		rows, err := db.QueryContext(ctx, q)
		if err != nil {
			return nil, fmt.Errorf("projcheck: query %s: %w", t.name, err)
		}
		for rows.Next() {
			var id uuid.UUID
			if err := rows.Scan(&id); err != nil {
				rows.Close()
				return nil, fmt.Errorf("projcheck: scan %s.%s: %w", t.name, t.eventCol, err)
			}
			out = append(out, ProjRow{Table: t.name, EventID: id})
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return nil, fmt.Errorf("projcheck: %s rows: %w", t.name, err)
		}
		rows.Close()
	}
	return out, nil
}

// LoadEventIDs fetches the set of event_ids that exist in the event store — the
// reference set CheckNoOrphan resolves projection event_ids against.
func LoadEventIDs(ctx context.Context, db *sql.DB) (map[uuid.UUID]bool, error) {
	rows, err := db.QueryContext(ctx, "SELECT event_id FROM events")
	if err != nil {
		return nil, fmt.Errorf("projcheck: query events: %w", err)
	}
	defer rows.Close()
	ids := map[uuid.UUID]bool{}
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("projcheck: scan event_id: %w", err)
		}
		ids[id] = true
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("projcheck: events rows: %w", err)
	}
	return ids, nil
}
