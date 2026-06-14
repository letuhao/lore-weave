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

// discoverProjectionTables derives the projection-table set from the LIVE schema
// (W3.2 — closes D-PROJCHECK-TABLE-DRIFT) instead of a hardcoded list that goes
// stale. The schema signal: every L3.A/canon projection table carries the
// VerificationMeta `last_verified_event_version` column (the integrity-checker's
// high-water; no non-projection table has it). The writing-event column is
// `event_id` where present, else `source_event_id` (canon). The WHERE
// `<col> IS NOT NULL` is applied to ALL tables — harmless for the NOT NULL
// event_id tables, and it correctly excludes canon's cascade rows (nullable
// source_event_id, which carry cascaded_from_reality_id instead).
//
// HARD ERROR on an empty result (review #4): a per-reality projection DB MUST
// have projection tables; empty = an un-migrated/misconfigured DB, NOT a reason
// to silently fall back to a curated list (which would re-introduce the drift).
//
// SCOPE — no-orphan checks the WRITING event only (the VerificationMeta event_id);
// secondary cross-references (e.g. canon_projection.overridden_by_l3_event_id) are
// a different invariant, out of this guard's scope.
func discoverProjectionTables(ctx context.Context, db *sql.DB) ([]projTable, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT c.table_name,
		       CASE WHEN EXISTS (
		         SELECT 1 FROM information_schema.columns c2
		          WHERE c2.table_schema = c.table_schema
		            AND c2.table_name   = c.table_name
		            AND c2.column_name  = 'event_id')
		            THEN 'event_id' ELSE 'source_event_id' END AS event_col
		  FROM information_schema.columns c
		 WHERE c.table_schema = 'public'
		   AND c.column_name  = 'last_verified_event_version'
		 ORDER BY c.table_name`)
	if err != nil {
		return nil, fmt.Errorf("projcheck: discover projection tables: %w", err)
	}
	defer rows.Close()
	var out []projTable
	for rows.Next() {
		var t projTable
		if err := rows.Scan(&t.name, &t.eventCol); err != nil {
			return nil, fmt.Errorf("projcheck: scan projection table: %w", err)
		}
		t.where = t.eventCol + " IS NOT NULL"
		out = append(out, t)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("projcheck: discover rows: %w", err)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("projcheck: no projection tables found (no table has a last_verified_event_version column) — the DB is un-migrated/misconfigured")
	}
	return out, nil
}

// LoadProjections fetches (table, event_id) for every row across all projection
// tables (discovered from the live schema). The check logic (CheckNoOrphan)
// carries the coverage; the loader is exercised by the live pipeline smoke.
func LoadProjections(ctx context.Context, db *sql.DB) ([]ProjRow, error) {
	projectionTables, err := discoverProjectionTables(ctx, db)
	if err != nil {
		return nil, err
	}
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
