// Package restore implements the archive read path: pull an archived Parquet
// blob from MinIO, decode it, and re-INSERT the events into a plain
// (non-partitioned) restore table on the per-reality DB so an operator can
// query historical events without un-archiving the live partition.
//
// Shared by cmd/archive-restore + the restore live-smoke.
package restore

import (
	"context"
	"fmt"
	"regexp"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// monthRe validates the YYYY-MM operator input before it reaches a table name.
var monthRe = regexp.MustCompile(`^[0-9]{4}-[0-9]{2}$`)

// Result summarizes a restore.
type Result struct {
	Table     string
	RowCount  int
	ObjectKey string
}

// List returns the archived manifest rows for a reality.
func List(ctx context.Context, pool *pgxpool.Pool, realityID uuid.UUID) ([]types.ArchivedObject, error) {
	return state.NewPostgres(pool).List(ctx, realityID)
}

// RestoreMonth downloads + decodes the archive object for (reality, month) and
// re-INSERTs its rows into `events_restore_<YYYYMM>` (created if absent) on the
// given per-reality pool. Returns the table name + row count.
func RestoreMonth(
	ctx context.Context,
	pool *pgxpool.Pool,
	store object_store.Store,
	bucket string,
	realityID uuid.UUID,
	month string,
) (Result, error) {
	if !monthRe.MatchString(month) {
		return Result{}, fmt.Errorf("restore: bad month %q (want YYYY-MM)", month)
	}
	key := object_store.ObjectKey(realityID.String(), month)
	blob, err := store.Get(ctx, bucket, key)
	if err != nil {
		return Result{}, fmt.Errorf("restore: get %s/%s: %w", bucket, key, err)
	}
	rows, err := parquet_writer.NewDecoder().Decode(blob)
	if err != nil {
		return Result{}, fmt.Errorf("restore: decode %s: %w", key, err)
	}

	table := "events_restore_" + month[:4] + month[5:7] // YYYYMM (validated)
	if err := createRestoreTable(ctx, pool, table); err != nil {
		return Result{}, err
	}
	if err := insertRows(ctx, pool, table, rows); err != nil {
		return Result{}, err
	}
	return Result{Table: table, RowCount: len(rows), ObjectKey: key}, nil
}

func createRestoreTable(ctx context.Context, pool *pgxpool.Pool, table string) error {
	// table name is derived from a regex-validated month → safe to interpolate.
	// #nosec G201
	_, err := pool.Exec(ctx, fmt.Sprintf(`
		CREATE TABLE IF NOT EXISTS %s (
			event_id          UUID NOT NULL,
			reality_id        UUID NOT NULL,
			aggregate_type    TEXT NOT NULL,
			aggregate_id      TEXT NOT NULL,
			aggregate_version BIGINT NOT NULL,
			event_type        TEXT NOT NULL,
			event_version     INTEGER NOT NULL,
			payload           JSONB NOT NULL,
			metadata          JSONB,
			occurred_at       TIMESTAMPTZ NOT NULL,
			recorded_at       TIMESTAMPTZ NOT NULL,
			audit_ref         UUID,
			registry_version  INTEGER,
			PRIMARY KEY (event_id)
		)`, table))
	if err != nil {
		return fmt.Errorf("restore: create %s: %w", table, err)
	}
	return nil
}

func insertRows(ctx context.Context, pool *pgxpool.Pool, table string, rows []types.EventRow) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("restore: begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// #nosec G201 — table validated.
	stmt := fmt.Sprintf(`
		INSERT INTO %s
		    (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
		     event_type, event_version, payload, metadata, occurred_at, recorded_at,
		     audit_ref, registry_version)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,$13)
		ON CONFLICT (event_id) DO NOTHING`, table)

	for _, r := range rows {
		var metadata *string
		if r.Metadata != nil {
			s := string(r.Metadata)
			metadata = &s
		}
		var auditRef *string
		if r.AuditRef != nil {
			s := r.AuditRef.String()
			auditRef = &s
		}
		if _, err := tx.Exec(ctx, stmt,
			r.EventID, r.RealityID, r.AggregateType, r.AggregateID, int64(r.AggregateVersion),
			r.EventType, r.EventVersion, string(r.Payload), metadata,
			r.OccurredAt.UTC(), r.RecordedAt.UTC(), auditRef, r.RegistryVersion,
		); err != nil {
			return fmt.Errorf("restore: insert %s event=%s: %w", table, r.EventID, err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("restore: commit %s: %w", table, err)
	}
	return nil
}

// FormatArchived renders one manifest row for the list CLI.
func FormatArchived(o types.ArchivedObject) string {
	return fmt.Sprintf("%s  rows=%d  bytes=%d  archived_at=%s  key=%s",
		o.Partition, o.RowCount, o.ByteSize, o.ArchivedAt.UTC().Format(time.RFC3339), o.ObjectKey)
}
