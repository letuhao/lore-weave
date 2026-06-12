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
	"encoding/json"
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
		if err != nil && !errors.Is(err, live.ErrOwnerPruned) {
			return nil, fmt.Errorf("pgsource: %s: %w", table, err)
		}
		// On ErrOwnerPruned, `owning` is nil → emit the row anyway so it is COUNTED
		// (CheckRow folds a nil-Owning row into skipped, not drift).
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

// scanSQL builds the cursor-paginated full-scan SELECT for monthly mode: the
// same meta-stripped canonical payload + PK columns (::text) + event_id +
// aggregate_version as sampleSQL, but ORDERED BY the PK columns (::text) and
// (when a cursor is supplied) filtered to rows AFTER the cursor via a row-value
// comparison. `$1` is the LIMIT (batch size); when `hasCursor`, `$2..$N+1` are
// the cursor's PK values in PK-column order. Ordering by `::text` of every PK
// gives a stable, deterministic pagination key (each row appears at most once
// across a sweep even under concurrent INSERTs).
func scanSQL(table string, pkColumns []string, hasCursor bool) string {
	var minusMeta strings.Builder
	for _, k := range metaKeys {
		minusMeta.WriteString(" - '")
		minusMeta.WriteString(k)
		minusMeta.WriteString("'")
	}
	pkSelects := make([]string, len(pkColumns))
	orderCols := make([]string, len(pkColumns))
	for i, c := range pkColumns {
		pkSelects[i] = fmt.Sprintf("t.%s::text AS %s", c, c)
		orderCols[i] = fmt.Sprintf("t.%s::text", c)
	}
	where := ""
	if hasCursor {
		binds := make([]string, len(pkColumns))
		for i := range pkColumns {
			binds[i] = fmt.Sprintf("$%d", i+2) // $1 is LIMIT; cursor binds start at $2
		}
		if len(pkColumns) == 1 {
			where = fmt.Sprintf(" WHERE %s > %s", orderCols[0], binds[0])
		} else {
			where = fmt.Sprintf(" WHERE (%s) > (%s)", strings.Join(orderCols, ", "), strings.Join(binds, ", "))
		}
	}
	return fmt.Sprintf(
		"SELECT to_jsonb(t)%s AS payload, %s, t.event_id, t.aggregate_version "+
			"FROM %s t%s ORDER BY %s LIMIT $1",
		minusMeta.String(), strings.Join(pkSelects, ", "), table, where, strings.Join(orderCols, ", "),
	)
}

// encodeCursor packs a row's PK text values (in PK-column order) into an opaque
// continuation token (a JSON array — robust to any TEXT PK content).
func encodeCursor(pkVals []string) (string, error) {
	b, err := json.Marshal(pkVals)
	if err != nil {
		return "", fmt.Errorf("pgsource: encode cursor: %w", err)
	}
	return string(b), nil
}

// decodeCursor reverses encodeCursor, validating the arity against the table's PK.
func decodeCursor(cursor string, pkCount int) ([]string, error) {
	var vals []string
	if err := json.Unmarshal([]byte(cursor), &vals); err != nil {
		return nil, fmt.Errorf("pgsource: decode cursor %q: %w", cursor, err)
	}
	if len(vals) != pkCount {
		return nil, fmt.Errorf("pgsource: cursor arity %d != table PK count %d", len(vals), pkCount)
	}
	return vals, nil
}

// NextBatch implements full_check.CursorSource: it walks `table` ordered by its
// PK columns, returning up to `batchSize` rows after `cursor` (empty = start),
// each with its owning aggregate(s) resolved. nextCursor is "" at end-of-table.
func (s *PgRowSampler) NextBatch(ctx context.Context, _ uuid.UUID, table, cursor string, batchSize int) ([]live.SampledRow, string, error) {
	pkColumns, err := tablemap.PKColumns(table)
	if err != nil {
		return nil, "", err
	}
	args := []any{batchSize}
	if cursor != "" {
		vals, derr := decodeCursor(cursor, len(pkColumns))
		if derr != nil {
			return nil, "", derr
		}
		for _, v := range vals {
			args = append(args, v)
		}
	}
	rows, err := s.pool.Query(ctx, scanSQL(table, pkColumns, cursor != ""), args...)
	if err != nil {
		return nil, "", fmt.Errorf("pgsource: scan %s: %w", table, err)
	}
	defer rows.Close()

	var out []live.SampledRow
	var lastPK []string
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
			return nil, "", fmt.Errorf("pgsource: scan %s: %w", table, err)
		}
		pk := make(map[string]string, len(pkColumns))
		for i, c := range pkColumns {
			pk[c] = pkVals[i]
		}
		owning, oerr := live.ResolveOwning(ctx, table, pk, eventID, s.lookupOwner)
		if oerr != nil && !errors.Is(oerr, live.ErrOwnerPruned) {
			return nil, "", fmt.Errorf("pgsource: %s: %w", table, oerr)
		}
		// On ErrOwnerPruned, `owning` is nil → still emit (and still advance the
		// cursor past it) so the full-scan does not abort on archived rows.
		out = append(out, live.SampledRow{
			PK:               pk,
			EventID:          eventID,
			AggregateVersion: uint64(aggVersion),
			Payload:          payload,
			Owning:           owning,
		})
		lastPK = pkVals
	}
	if err := rows.Err(); err != nil {
		return nil, "", err
	}
	// A full batch ⇒ more may remain ⇒ emit a continuation cursor; a short
	// batch ⇒ end-of-table ⇒ "".
	if len(out) == batchSize && lastPK != nil {
		next, eerr := encodeCursor(lastPK)
		if eerr != nil {
			return nil, "", eerr
		}
		return out, next, nil
	}
	return out, "", nil
}

var _ live.LagReader = (*PgRowSampler)(nil)

// TableLagSeconds implements [live.LagReader]: NOW() − max(applied_at) over the
// table (the freshness of the most-recent projection write, in seconds). `ok` is
// false when the table is empty (max(applied_at) IS NULL → no lag to report).
// The table name is validated against the L3.A map before interpolation.
func (s *PgRowSampler) TableLagSeconds(ctx context.Context, table string) (float64, bool, error) {
	if _, err := tablemap.PKColumns(table); err != nil {
		return 0, false, err // unknown table → not in the L3.A allowlist
	}
	var lag *float64 // nullable: NULL over an empty table
	err := s.pool.QueryRow(ctx,
		fmt.Sprintf("SELECT EXTRACT(EPOCH FROM (now() - max(applied_at)))::float8 FROM %s", table),
	).Scan(&lag)
	if err != nil {
		return 0, false, fmt.Errorf("pgsource: table lag %s: %w", table, err)
	}
	if lag == nil {
		return 0, false, nil
	}
	return *lag, true, nil
}

// lookupOwner backs live.ResolveOwning for single-aggregate tables.
func (s *PgRowSampler) lookupOwner(ctx context.Context, eventID uuid.UUID) (string, string, error) {
	var aggType, aggID string
	err := s.pool.QueryRow(ctx, ownerLookupSQL, eventID).Scan(&aggType, &aggID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// The row's event_id is not in the events table — its owning event was
			// archived/pruned by retention. Wrap the live.ErrOwnerPruned sentinel so
			// the sampler SKIPS this (unverifiable) row rather than failing the whole
			// sweep — critical for the monthly full-scan, which walks old rows whose
			// partitions have been detached.
			return "", "", fmt.Errorf("pgsource: no event for event_id %s: %w", eventID, live.ErrOwnerPruned)
		}
		return "", "", fmt.Errorf("pgsource: owner lookup event_id %s: %w", eventID, err)
	}
	return aggType, aggID, nil
}
