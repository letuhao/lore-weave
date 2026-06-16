package ledger

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

// LoadLog fetches the event store + outbox into an in-memory Log.
//
// It reads only the columns C3 reasons about, ordered by (recorded_at, event_id)
// — the spine's canonical event order. This is a thin adapter; the check logic
// (ledger.go, against.go) is what carries the coverage. LoadLog itself is
// exercised by the live pipeline smoke.
//
// SCOPE: LoadLog reads ALL realities and loads the whole log into memory, so
// `-verify` expects a DB containing exactly the seeded data (the smoke uses a
// fresh DB). A reality filter + streaming for production-scale logs is a future
// concern (the C3 ledger is a test tool, not a standing production sweep).
func LoadLog(ctx context.Context, db *sql.DB) (Log, error) {
	var log Log

	rows, err := db.QueryContext(ctx, `
		SELECT event_id, reality_id, aggregate_type, aggregate_id,
		       aggregate_version, event_type, recorded_at, payload
		FROM events
		ORDER BY recorded_at, event_id`)
	if err != nil {
		return Log{}, fmt.Errorf("ledger: query events: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var (
			e       EventRow
			version int64
			payload []byte
		)
		if err := rows.Scan(&e.EventID, &e.RealityID, &e.AggType, &e.AggID, &version, &e.EventType, &e.RecordedAt, &payload); err != nil {
			return Log{}, fmt.Errorf("ledger: scan event: %w", err)
		}
		e.Version = uint64(version)
		if err := json.Unmarshal(payload, &e.Payload); err != nil {
			return Log{}, fmt.Errorf("ledger: unmarshal payload %s: %w", e.EventID, err)
		}
		log.Events = append(log.Events, e)
	}
	if err := rows.Err(); err != nil {
		return Log{}, fmt.Errorf("ledger: events rows: %w", err)
	}

	orows, err := db.QueryContext(ctx, `SELECT event_id FROM events_outbox`)
	if err != nil {
		return Log{}, fmt.Errorf("ledger: query outbox: %w", err)
	}
	defer orows.Close()
	for orows.Next() {
		var id uuid.UUID
		if err := orows.Scan(&id); err != nil {
			return Log{}, fmt.Errorf("ledger: scan outbox: %w", err)
		}
		log.OutboxIDs = append(log.OutboxIDs, id)
	}
	if err := orows.Err(); err != nil {
		return Log{}, fmt.Errorf("ledger: outbox rows: %w", err)
	}
	return log, nil
}

// checksumExpr is the SINGLE Go-side copy of the content-checksum expression —
// it MUST stay byte-identical to the one the writers emit (event_store_pg.rs
// append + emit.go insertEventsSQL) and the migration comment, or the re-derive
// would diverge from the frozen value and false-flag every row. Covers payload
// AND metadata via jsonb_build_object (W3.4). Used twice below (mismatch filter
// + projected value) from one constant so the two can't drift from each other.
const checksumExpr = `encode(sha256(convert_to(jsonb_build_object('p', payload, 'm', metadata)::text, 'UTF8')), 'hex')`

// CheckStoredChecksum (W3.4) verifies the per-row stored content checksum:
// events.content_sha256 was frozen at INSERT as the hash of the canonical jsonb
// of {payload, metadata}; this re-derives that hash IN POSTGRES (the single
// canonicalizer the writers used) and flags any row where the frozen value no
// longer matches — i.e. payload OR metadata was mutated after write (byte-rot /
// tamper).
//
// DB-side ON PURPOSE: the hash is defined over Postgres's own jsonb text;
// re-hashing in Go would require reproducing PG's exact canonical form (key
// order, number/whitespace rendering) — the cross-language fragility the
// PG-canonicalizer design exists to avoid. So the check delegates the
// re-derivation to the same engine that wrote it; a row mismatches ONLY if its
// content changed, never because Go and PG canonicalize differently.
//
// Returns (covered, report): `covered` is the count of non-NULL-checksum rows
// actually compared, so a caller can detect a vacuous run (0 covered = no writer
// populated the column / pre-0013 DB). NULL content_sha256 rows (pre-migration)
// are SKIPPED — no baseline, the documented coverage boundary.
func CheckStoredChecksum(ctx context.Context, db *sql.DB) (int, Report, error) {
	var r Report

	var covered int
	if err := db.QueryRowContext(ctx,
		`SELECT count(*) FROM events WHERE content_sha256 IS NOT NULL`,
	).Scan(&covered); err != nil {
		return 0, r, fmt.Errorf("ledger: count checksum-covered rows: %w", err)
	}

	// Only mismatches come back. PG recomputes over the SAME stored jsonb the
	// writers hashed, so a row appears here iff its content was mutated after the
	// checksum was frozen.
	// #nosec G201 — checksumExpr is a compile-time constant (no user input); only
	// a fixed literal SQL expression is interpolated.
	rows, err := db.QueryContext(ctx, fmt.Sprintf(`
		SELECT event_id, content_sha256, %[1]s AS recomputed
		  FROM events
		 WHERE content_sha256 IS NOT NULL
		   AND content_sha256 <> %[1]s
		 ORDER BY event_id`, checksumExpr))
	if err != nil {
		return covered, r, fmt.Errorf("ledger: query stored-checksum mismatches: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var (
			id             uuid.UUID
			stored, recomp string
		)
		if err := rows.Scan(&id, &stored, &recomp); err != nil {
			return covered, r, fmt.Errorf("ledger: scan checksum row: %w", err)
		}
		r.add(KindStoredChecksumMismatch, fmt.Sprintf(
			"event %s: stored %s != re-derived %s (payload/metadata mutated after write — byte-rot/tamper)",
			id, stored, recomp))
	}
	if err := rows.Err(); err != nil {
		return covered, r, fmt.Errorf("ledger: checksum rows: %w", err)
	}
	return covered, r, nil
}
