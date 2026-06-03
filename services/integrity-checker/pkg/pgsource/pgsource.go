// Package pgsource is the production [live.RowSampler]: it samples N random rows
// per projection table from a per-reality shard DB and resolves each row's
// owning aggregate(s).
//
// Both the sample payload and the replay-aggregate bin's output are
// `to_jsonb(t) - meta_keys`, so the comparator's byte-compare is robust across
// Go/Rust. The PK columns are cast to `::text` so they round-trip as plain
// strings (matching the bin's PK predicate + the replayloader's PK map).
//
// The pure SQL builders are unit-tested here; the pgx round-trip is the deferred
// live-smoke (DEFERRED 147).
package pgsource

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/live"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
)

// metaKeys are the VerificationMeta + HWM columns stripped from the sampled
// payload. MUST match the Rust replay-aggregate bin's META_KEYS (and 0006) — a
// drift test guards the length; the live-smoke confirms byte-equality.
var metaKeys = []string{
	"event_id",
	"aggregate_version",
	"applied_at",
	"last_verified_event_version",
	"last_verified_at",
}

// ownerLookupSQL resolves the (aggregate_type, aggregate_id) that last wrote a
// row, from its event_id (events.event_id is globally unique; indexed).
const ownerLookupSQL = `SELECT aggregate_type, aggregate_id FROM events WHERE event_id = $1 LIMIT 1`

// sampleSQL builds the random-sample SELECT for a table: the meta-stripped
// canonical payload + each PK column (::text) + the row's event_id (replay
// boundary) + aggregate_version. `$1` is the LIMIT. PK column names come from the
// trusted per-table map but are identifier-validated by the caller (tablemap).
func sampleSQL(table string, pkColumns []string) string {
	var minusMeta strings.Builder
	for _, k := range metaKeys {
		minusMeta.WriteString(" - '")
		minusMeta.WriteString(k)
		minusMeta.WriteString("'")
	}
	pkSelects := make([]string, len(pkColumns))
	for i, c := range pkColumns {
		pkSelects[i] = fmt.Sprintf("t.%s::text AS %s", c, c)
	}
	return fmt.Sprintf(
		"SELECT to_jsonb(t)%s AS payload, %s, t.event_id, t.aggregate_version "+
			"FROM %s t ORDER BY random() LIMIT $1",
		minusMeta.String(), strings.Join(pkSelects, ", "), table,
	)
}

// PgRowSampler samples rows from ONE reality's shard pool. Implements
// [live.RowSampler] (the realityID + dsn args are carried for the Checker's
// replayer; the sampler itself is pool-scoped).
type PgRowSampler struct {
	pool *pgxpool.Pool
}

// New binds the per-reality shard pool.
func New(pool *pgxpool.Pool) (*PgRowSampler, error) {
	if pool == nil {
		return nil, errors.New("pgsource: nil pool")
	}
	return &PgRowSampler{pool: pool}, nil
}

var _ live.RowSampler = (*PgRowSampler)(nil)

// SampleRows samples up to `limit` rows from `table` and resolves each row's
// owning aggregate(s). `dsn` is unused here (the pool is the reality scope); it
// is threaded by the Checker to the replay-aggregate bin.
func (s *PgRowSampler) SampleRows(ctx context.Context, _ uuid.UUID, _ string, table string, limit int) ([]live.SampledRow, error) {
	pkColumns, err := tablemap.PKColumns(table)
	if err != nil {
		return nil, err
	}
	rows, err := s.pool.Query(ctx, sampleSQL(table, pkColumns), limit)
	if err != nil {
		return nil, fmt.Errorf("pgsource: sample %s: %w", table, err)
	}
	defer rows.Close()

	var out []live.SampledRow
	for rows.Next() {
		var payload []byte
		pkVals := make([]string, len(pkColumns))
		dest := make([]any, 0, len(pkColumns)+3)
		dest = append(dest, &payload)
		for i := range pkColumns {
			dest = append(dest, &pkVals[i])
		}
		var eventID uuid.UUID
		var aggVersion int64
		dest = append(dest, &eventID, &aggVersion)
		if err := rows.Scan(dest...); err != nil {
			return nil, fmt.Errorf("pgsource: scan %s: %w", table, err)
		}
		pk := make(map[string]string, len(pkColumns))
		for i, c := range pkColumns {
			pk[c] = pkVals[i]
		}
		owning, err := live.ResolveOwning(ctx, table, pk, eventID, s.lookupOwner)
		if err != nil {
			return nil, fmt.Errorf("pgsource: %s: %w", table, err)
		}
		out = append(out, live.SampledRow{
			PK:               pk,
			EventID:          eventID,
			AggregateVersion: uint64(aggVersion),
			Payload:          payload,
			Owning:           owning,
		})
	}
	return out, rows.Err()
}

// lookupOwner backs live.ResolveOwning for single-aggregate tables.
func (s *PgRowSampler) lookupOwner(ctx context.Context, eventID uuid.UUID) (string, string, error) {
	var aggType, aggID string
	err := s.pool.QueryRow(ctx, ownerLookupSQL, eventID).Scan(&aggType, &aggID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// The row's event_id is not in the events table — pruned/archived, or
			// a write-without-event bug. The checker treats a resolve failure as a
			// table-level error (the sample cannot be verified).
			return "", "", fmt.Errorf("pgsource: no event for event_id %s (pruned/archived?)", eventID)
		}
		return "", "", fmt.Errorf("pgsource: owner lookup event_id %s: %w", eventID, err)
	}
	return aggType, aggID, nil
}
